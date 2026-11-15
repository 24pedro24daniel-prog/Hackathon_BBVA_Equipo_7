"""Dataset sintético de la demo: Pedro, "Bodega Don Pedro" (EMP-0001). Todo es ficticio.

Historia que debe cuadrar (context.md §9), con "hoy" = 14/11/2026 (sábado):
- 92 días de registros: del 15/08 al 13/11 (el 14/11 aún no tiene movimientos).
- Saldo de caja del negocio al 14/11: exactamente S/ 2 340.00. Se logra fijando
  `empresas.saldo_inicial` = 2 340 − Σ(movimientos con signo que afectan caja).
- Pedido a crédito PED-0012 de S/ 2 400 a Distribuidora Andina, hecho el 13/11, vence el 30/11.
- Fiados pendientes: FIA-0045 (Sra. Carmen, 120), FIA-0046 (Don Luis, 95), FIA-0047 (Vecina Rosa, 95) = S/ 310.
- Retiros para la casa del 1 al 13 de noviembre: S/ 1 900, contra S/ 1 200 al mismo corte de sep. y oct. (+700).
- Sueldo fijo programado de S/ 400 por semana (sábados) desde el 01/11. Luz y agua S/ 180 el día 16 de cada mes.
- Nuevo RUS de S/ 20: agosto a octubre pagados; noviembre vence el 15/12.

Faltante del 30/11 (≈ −650). La proyección de referencia con la que se calibra el generador es:
    saldo_30/11 = saldo_14/11 + Σ_{15/11..30/11} media_mismo_día_de_semana(flujo_ordinario, 4 semanas)
                  − deudas que vencen hasta el 30/11 − programados hasta el 30/11
`flujo_ordinario` = movimientos que afectan caja sin vínculo a fiado/deuda/impuesto/programado (esos se
proyectan aparte). Los cobros de fiados NO se suman (son la palanca "cobrar fiados" del simulador, +310).
El generador ajusta las compras al contado de las últimas 4 semanas para que esa proyección dé −650.00.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.ids import formatear_id
from app.db import models as m
from app.db.base import Base
from app.schemas.common import (
    Canal,
    EstadoMeta,
    Frecuencia,
    MetodoPago,
    PerfilPago,
    PlantillaMeta,
    TipoDeuda,
    TipoEvento,
    TipoFlujo,
    TipoMovimiento,
    TipoRegla,
    redondear,
    signo,
)

LIMA = ZoneInfo("America/Lima")
SEMILLA = 20261114

EMPRESA_ID = "EMP-0001"
NOMBRE_EMPRESA = "Bodega Don Pedro"
INICIO = date(2026, 8, 15)
FIN_HISTORIA = date(2026, 11, 13)
CORTE = date(2026, 11, 14)
SALDO_CORTE = Decimal("2340.00")
MINIMO_OPERATIVO = Decimal("800.00")
SALDO_OBJETIVO_30_11 = Decimal("-650.00")
FECHA_CRITICA = date(2026, 11, 30)

PEDIDO_ANDINA_ID = "PED-0012"
MONTO_PEDIDO_ANDINA = Decimal("2400.00")
FIADOS_PENDIENTES = ("FIA-0045", "FIA-0046", "FIA-0047")
SUELDO_SEMANAL = Decimal("400.00")
LUZ_AGUA = Decimal("180.00")
RUS_MENSUAL = Decimal("20.00")

PRG_LUZ = "PRG-0001"
PRG_SUELDO = "PRG-0002"
PRV_ANDINA = "PRV-0001"

RUBROS = [("RUB-01", "bodega"), ("RUB-02", "restaurante"), ("RUB-03", "taller"), ("RUB-04", "distribuidora")]

# (id, nombre, tipo, es_del_negocio)
CATEGORIAS = [
    ("CAT-01", "bebidas", TipoFlujo.ingreso, True),
    ("CAT-02", "abarrotes", TipoFlujo.ingreso, True),
    ("CAT-03", "lacteos", TipoFlujo.ingreso, True),
    ("CAT-04", "panaderia", TipoFlujo.ingreso, True),
    ("CAT-05", "limpieza", TipoFlujo.ingreso, True),
    ("CAT-06", "golosinas", TipoFlujo.ingreso, True),
    ("CAT-07", "cobro de fiados", TipoFlujo.ingreso, True),
    ("CAT-08", "prestamos recibidos", TipoFlujo.ingreso, True),
    ("CAT-09", "otros ingresos", TipoFlujo.ingreso, True),
    ("CAT-10", "mercaderia", TipoFlujo.egreso, True),
    ("CAT-11", "servicios", TipoFlujo.egreso, True),
    ("CAT-12", "transporte", TipoFlujo.egreso, True),
    ("CAT-13", "alquiler", TipoFlujo.egreso, True),
    ("CAT-14", "impuestos", TipoFlujo.egreso, True),
    ("CAT-15", "retiro personal", TipoFlujo.egreso, False),
    ("CAT-16", "pago de prestamos", TipoFlujo.egreso, True),
    ("CAT-17", "otros gastos", TipoFlujo.egreso, True),
]
CAT = {nombre: cid for cid, nombre, _, _ in CATEGORIAS}

# (nombre, categoría, precio, costo o None, alias). IDs desde PRD-0021: la cerveza queda en PRD-0031 (contrato).
PRODUCTOS = [
    ("Pan francés", "panaderia", "0.30", "0.22", ["pan", "panes", "pancito", "pan francés"]),
    ("Leche evaporada 400 g", "lacteos", "4.20", "3.50", ["leche", "tarro de leche", "leche gloria"]),
    ("Arroz 1 kg", "abarrotes", "4.00", "3.40", ["arroz", "kilo de arroz"]),
    ("Azúcar 1 kg", "abarrotes", "3.80", "3.30", ["azucar", "azúcar", "kilo de azúcar"]),
    ("Aceite vegetal 1 L", "abarrotes", "9.50", "8.20", ["aceite", "botella de aceite"]),
    ("Fideos 500 g", "abarrotes", "2.80", "2.20", ["fideos", "tallarines", "spaghetti"]),
    ("Huevo", "abarrotes", "0.60", "0.48", ["huevo", "huevos"]),
    ("Atún en lata", "abarrotes", "6.00", "4.90", ["atún", "atun", "lata de atún"]),
    ("Gaseosa 500 ml", "bebidas", "2.50", "1.80", ["gaseosa", "gaseosita", "coca", "inca kola chica"]),
    ("Gaseosa 3 L", "bebidas", "11.00", "8.60", ["gaseosa grande", "gaseosa de tres litros", "tres litros"]),
    ("Cerveza 620 ml", "bebidas", "6.50", "4.80", ["cerveza", "cervezas", "chela", "chelas", "cerveza grande"]),
    ("Agua 625 ml", "bebidas", "1.50", "0.90", ["agua", "agüita", "botella de agua"]),
    ("Yogurt 1 L", "lacteos", "7.50", None, ["yogurt", "yogur"]),
    ("Queso fresco 250 g", "lacteos", "6.00", None, ["queso", "queso fresco"]),
    ("Galletas paquete", "golosinas", "1.00", "0.70", ["galleta", "galletas", "paquete de galletas"]),
    ("Chocolate", "golosinas", "2.00", None, ["chocolate", "chocolatito"]),
    ("Caramelo", "golosinas", "0.10", "0.06", ["caramelo", "caramelos", "dulces"]),
    ("Detergente 350 g", "limpieza", "5.50", "4.40", ["detergente", "ace", "bolsa de detergente"]),
    ("Papel higiénico x4", "limpieza", "6.80", None, ["papel", "papel higiénico", "papel higienico"]),
    ("Jabón de tocador", "limpieza", "3.20", "2.50", ["jabón", "jabon"]),
]
PRODUCTO_ID = {nombre: formatear_id("PRD", 21 + i) for i, (nombre, *_) in enumerate(PRODUCTOS)}
PRODUCTO = {nombre: (cat, Decimal(p), Decimal(c) if c else None) for nombre, cat, p, c, _ in PRODUCTOS}

# Cantidades típicas por ticket (mín, máx)
CANTIDADES = {"Pan francés": (5, 20), "Huevo": (3, 15), "Caramelo": (5, 20), "Cerveza 620 ml": (1, 6)}
PESO_CATEGORIA = {"bebidas": 30, "abarrotes": 30, "panaderia": 12, "lacteos": 12, "limpieza": 8, "golosinas": 8}

# (id, nombre, alias, teléfono, perfil oculto)
CLIENTES = [
    ("CLI-0102", "Sra. Carmen", ["carmen", "la señora carmen", "señora carmen", "doña carmen"], "+51900000102",
     PerfilPago.moroso),
    ("CLI-0087", "Don Luis", ["luis", "don luis", "el señor luis"], "+51900000087", PerfilPago.ocasional),
    ("CLI-0110", "Vecina Rosa", ["rosa", "la vecina rosa", "señora rosa"], "+51900000110", PerfilPago.puntual),
]  # fmt: skip
DIAS_PAGO_POR_PERFIL = {PerfilPago.puntual: (4, 12), PerfilPago.ocasional: (7, 20), PerfilPago.moroso: (12, 30)}

# Retiros para la casa que no son el sueldo (fecha, monto). Sep y oct al día 13: 800 de sábados + 400 = 1 200.
# Noviembre al 13: 400 de sueldo (sáb 7) + 1 500 = 1 900.
RETIROS_EXTRA = {
    date(2026, 8, 20): 150, date(2026, 8, 27): 200,
    date(2026, 9, 3): 150, date(2026, 9, 9): 250,
    date(2026, 9, 17): 200, date(2026, 9, 24): 150, date(2026, 9, 29): 100,
    date(2026, 10, 6): 200, date(2026, 10, 12): 200,
    date(2026, 10, 19): 150, date(2026, 10, 23): 100, date(2026, 10, 28): 200,
    date(2026, 11, 2): 200, date(2026, 11, 4): 300, date(2026, 11, 6): 150,
    date(2026, 11, 9): 350, date(2026, 11, 11): 250, date(2026, 11, 13): 250,
}  # fmt: skip
INICIO_SUELDO = date(2026, 11, 1)

# Proporción de lo vendido que se repone al contado (mercado mayorista + panadería). Andina repone ~8 % a crédito.
REPOSICION_CONTADO = Decimal("0.79")


@dataclass
class _Linea:
    producto: str | None
    cantidad: Decimal
    precio: Decimal
    costo: Decimal | None
    descripcion: str | None = None

    @property
    def subtotal(self) -> Decimal:
        return redondear(self.cantidad * self.precio)


@dataclass
class _Mov:
    fecha_hora: datetime
    tipo: TipoMovimiento
    categoria: str
    monto: Decimal
    metodo: MetodoPago = MetodoPago.efectivo
    canal: Canal = Canal.voz
    descripcion: str | None = None
    confianza: Decimal | None = None
    fiado_id: str | None = None
    deuda_id: str | None = None
    impuesto_id: str | None = None
    programado_id: str | None = None
    lineas: list[_Linea] = field(default_factory=list)

    @property
    def afecta_caja(self) -> bool:
        return self.metodo != MetodoPago.credito

    @property
    def ordinario(self) -> bool:
        return self.afecta_caja and not (self.fiado_id or self.deuda_id or self.impuesto_id or self.programado_id)

    @property
    def con_signo(self) -> Decimal:
        return self.monto * signo(self.tipo)


def _dt(d: date, h: int, mi: int = 0) -> datetime:
    return datetime.combine(d, time(h, mi), tzinfo=LIMA)


def _dias(desde: date, hasta: date):
    d = desde
    while d <= hasta:
        yield d
        d += timedelta(days=1)


class _Generador:
    def __init__(self, semilla: int = SEMILLA):
        self.rng = random.Random(semilla)
        self.movs: list[_Mov] = []
        self.fiados: list[m.CuadernoFiado] = []
        self.deudas: list[m.Deuda] = []
        self.impuestos: list[m.Impuesto] = []
        self.compras_mayorista: dict[date, _Mov] = {}

    # ── utilidades ──
    def _canal_y_confianza(self) -> tuple[Canal, Decimal | None]:
        r = self.rng.random()
        canal = Canal.voz if r < 0.55 else Canal.texto if r < 0.80 else Canal.manual
        if canal == Canal.manual:
            return canal, None
        return canal, Decimal(str(round(self.rng.uniform(0.80, 0.99), 3)))

    def _linea(self, nombre: str, cantidad: int | Decimal) -> _Linea:
        _, precio, costo = PRODUCTO[nombre]
        return _Linea(nombre, Decimal(cantidad), precio, costo)

    @staticmethod
    def _linea_costo(nombre: str, cantidad: int) -> _Linea:
        """Línea de un pedido al proveedor: se paga al costo del catálogo."""
        costo = PRODUCTO[nombre][2]
        return _Linea(nombre, Decimal(cantidad), costo, costo)

    def _agregar(self, mov: _Mov) -> _Mov:
        self.movs.append(mov)
        return mov

    # ── ventas al contado ──
    def _ticket(self) -> tuple[str, list[_Linea]]:
        cats = list(PESO_CATEGORIA)
        cat = self.rng.choices(cats, weights=[PESO_CATEGORIA[c] for c in cats])[0]
        candidatos = [n for n, (c, _, _) in PRODUCTO.items() if c == cat]
        elegidos = self.rng.sample(candidatos, k=min(len(candidatos), self.rng.randint(1, 3)))
        lineas = []
        for nombre in elegidos:
            lo, hi = CANTIDADES.get(nombre, (1, 4))
            lineas.append(self._linea(nombre, self.rng.randint(lo, hi)))
        return cat, lineas

    def ventas_del_dia(self, d: date) -> Decimal:
        factor = {5: 1.20, 6: 1.15, 4: 1.05}.get(d.weekday(), 0.95)
        objetivo = 640 * factor * self.rng.uniform(0.9, 1.1)
        total = Decimal("0")
        minutos = 7 * 60
        while total < Decimal(str(objetivo)):
            cat, lineas = self._ticket()
            monto = sum((ln.subtotal for ln in lineas), Decimal("0"))
            minutos = min(minutos + self.rng.randint(20, 60), 21 * 60 + 30)
            canal, conf = self._canal_y_confianza()
            metodo = MetodoPago.efectivo if self.rng.random() < 0.78 else MetodoPago.billetera_digital
            descripcion = ", ".join(f"{int(ln.cantidad)} {ln.producto}" for ln in lineas)
            self._agregar(
                _Mov(_dt(d, minutos // 60, minutos % 60), TipoMovimiento.venta, cat, monto, metodo, canal,
                     descripcion[:255], conf, lineas=lineas)
            )  # fmt: skip
            total += monto
        return total

    # ── egresos ordinarios ──
    def compras_del_dia(self, d: date, ventas: Decimal) -> None:
        reposicion = redondear(ventas * REPOSICION_CONTADO)
        pan = redondear(reposicion * Decimal("0.12"))
        self._agregar(_Mov(_dt(d, 6, 0), TipoMovimiento.compra, "mercaderia", pan, canal=Canal.texto,
                           descripcion="Pan del día (panadería)"))  # fmt: skip
        self.compras_mayorista[d] = self._agregar(
            _Mov(_dt(d, 6, 40), TipoMovimiento.compra, "mercaderia", reposicion - pan, canal=Canal.voz,
                 descripcion="Compra en el mercado mayorista", confianza=Decimal("0.910"))
        )  # fmt: skip

    def gastos_del_dia(self, d: date) -> None:
        wd = d.weekday()
        if wd in (0, 2, 4):
            self._agregar(_Mov(_dt(d, 6, 20), TipoMovimiento.gasto_negocio, "transporte",
                               Decimal(self.rng.choice([6, 7, 8, 10])), descripcion="Mototaxi al mercado"))  # fmt: skip
        if wd == 0:
            self._agregar(_Mov(_dt(d, 9, 0), TipoMovimiento.gasto_negocio, "otros gastos",
                               Decimal(self.rng.choice([15, 18, 20, 25])), descripcion="Bolsas y descartables"))  # fmt: skip
        if (d - INICIO).days % 21 == 10:
            self._agregar(_Mov(_dt(d, 11, 0), TipoMovimiento.gasto_negocio, "otros gastos", Decimal("48.00"),
                               descripcion="Balón de gas"))  # fmt: skip

    def retiros_del_dia(self, d: date) -> None:
        if d.weekday() == 5:
            es_sueldo = d >= INICIO_SUELDO
            self._agregar(_Mov(_dt(d, 20, 30), TipoMovimiento.retiro_personal, "retiro personal", SUELDO_SEMANAL,
                               descripcion="Sueldo de la semana" if es_sueldo else "Para la casa",
                               programado_id=PRG_SUELDO if es_sueldo else None))  # fmt: skip
        if d in RETIROS_EXTRA:
            self._agregar(_Mov(_dt(d, 20, 45), TipoMovimiento.retiro_personal, "retiro personal",
                               Decimal(RETIROS_EXTRA[d]), descripcion="Saqué para la casa"))  # fmt: skip

    # ── obligaciones ──
    def luz_y_agua(self) -> None:
        for d in (date(2026, 8, 16), date(2026, 9, 16), date(2026, 10, 16)):
            self._agregar(_Mov(_dt(d, 10, 0), TipoMovimiento.gasto_negocio, "servicios", LUZ_AGUA,
                               descripcion="Luz y agua", programado_id=PRG_LUZ))  # fmt: skip

    def impuestos_rus(self) -> None:
        pagos = {"2026-08": date(2026, 9, 12), "2026-09": date(2026, 10, 13), "2026-10": date(2026, 11, 12),
                 "2026-11": None}  # fmt: skip
        for i, (periodo, pagado) in enumerate(pagos.items(), start=1):
            anio, mes = map(int, periodo.split("-"))
            vence = date(anio + mes // 12, mes % 12 + 1, 15)
            imp_id = formatear_id("IMP", i)
            self.impuestos.append(m.Impuesto(impuesto_id=imp_id, empresa_id=EMPRESA_ID, regimen="nuevo_rus",
                                             periodo=periodo, monto=RUS_MENSUAL, fecha_vencimiento=vence,
                                             fecha_pago=pagado, canal=Canal.texto))  # fmt: skip
            if pagado:
                self._agregar(_Mov(_dt(pagado, 11, 30), TipoMovimiento.pago_impuesto, "impuestos", RUS_MENSUAL,
                                   canal=Canal.texto, descripcion=f"Nuevo RUS {periodo}", impuesto_id=imp_id))  # fmt: skip

    def _deuda_andina(self, deuda_id: str, fecha: date, lineas: list[_Linea], vence: date, pagada: date | None):
        monto = sum((ln.subtotal for ln in lineas), Decimal("0"))
        self.deudas.append(m.Deuda(deuda_id=deuda_id, empresa_id=EMPRESA_ID, tipo=TipoDeuda.proveedor,
                                   proveedor_id=PRV_ANDINA, monto_recibido=monto, monto_total_a_pagar=monto,
                                   fecha_inicio=fecha, fecha_vencimiento=vence, fecha_pago_total=pagada,
                                   canal=Canal.voz, notas="Pedido de bebidas"))  # fmt: skip
        self._agregar(_Mov(_dt(fecha, 10, 0), TipoMovimiento.compra, "mercaderia", monto, MetodoPago.credito,
                           descripcion="Pedido a Distribuidora Andina", confianza=Decimal("0.880"),
                           deuda_id=deuda_id, lineas=lineas))  # fmt: skip
        if pagada:
            self._agregar(_Mov(_dt(pagada, 19, 0), TipoMovimiento.pago_proveedor, "mercaderia", monto,
                               descripcion="Pago a Distribuidora Andina", deuda_id=deuda_id))  # fmt: skip

    def pedidos_andina(self) -> None:
        # Andina trae solo cerveza y gaseosa chica (lo mismo que PED-0012); la gaseosa grande y el agua se reponen en el
        # mercado. Así "lo que vendes de lo que te trae Andina" hasta el 30/11 ronda S/ 2 000 (contrato §4.5).
        for i in range(11):
            fecha = date(2026, 8, 17) + timedelta(days=8 * i)
            cantidades = {"Cerveza 620 ml": 12 * self.rng.randint(3, 5), "Gaseosa 500 ml": 12 * self.rng.randint(2, 5)}
            lineas = [self._linea_costo(n, c) for n, c in cantidades.items()]
            self._deuda_andina(formatear_id("PED", i + 1), fecha, lineas, fecha + timedelta(days=15),
                               fecha + timedelta(days=7))  # fmt: skip
        pedido = [self._linea_costo("Cerveza 620 ml", 350), self._linea_costo("Gaseosa 500 ml", 400)]
        self._deuda_andina(PEDIDO_ANDINA_ID, date(2026, 11, 13), pedido, FECHA_CRITICA, None)

    # ── fiados ──
    def _fiado(self, fiado_id: str, cliente: tuple, fecha: date, lineas: list[_Linea], detalle: str,
               pago: date | None, parcial: bool = False) -> None:  # fmt: skip
        cli_id, nombre, *_ = cliente
        monto = sum((ln.subtotal for ln in lineas), Decimal("0"))
        compromiso = fecha + timedelta(days=14)
        self.fiados.append(m.CuadernoFiado(fiado_id=fiado_id, empresa_id=EMPRESA_ID, cliente_id=cli_id,
                                           detalle=detalle, monto=monto, fecha_fiado=fecha,
                                           fecha_compromiso=compromiso, fecha_pago_total=pago,
                                           canal=Canal.voz, pago_tardio=None if pago is None else pago > compromiso))  # fmt: skip
        cat = PRODUCTO[lineas[0].producto][0]
        self._agregar(_Mov(_dt(fecha, 18, 15), TipoMovimiento.venta, cat, monto, MetodoPago.credito,
                           descripcion=f"Fiado a {nombre}: {detalle}", confianza=Decimal("0.900"),
                           fiado_id=fiado_id, lineas=lineas))  # fmt: skip
        if pago is None:
            return
        cobros = [(pago, monto)]
        if parcial:
            primera = redondear(monto / 2)
            mitad = fecha + (pago - fecha) / 2
            cobros = [(mitad, primera), (pago, monto - primera)]
        for dia, importe in cobros:
            self._agregar(_Mov(_dt(dia, 17, 30), TipoMovimiento.cobro_fiado, "cobro de fiados", importe,
                               descripcion=f"{nombre} pagó su fiado", fiado_id=fiado_id))  # fmt: skip

    def fiados_historicos(self) -> None:
        candidatos = [n for n, (c, _, _) in PRODUCTO.items() if c in ("abarrotes", "lacteos", "panaderia")]
        for i in range(44):
            fecha = date(2026, 8, 16) + timedelta(days=round(i * 70 / 44))
            cliente = self.rng.choices(CLIENTES, weights=[40, 35, 25])[0]
            elegidos = self.rng.sample(candidatos, k=self.rng.randint(1, 3))
            lineas = [self._linea(n, self.rng.randint(*CANTIDADES.get(n, (1, 4)))) for n in elegidos]
            lo, hi = DIAS_PAGO_POR_PERFIL[cliente[4]]
            pago = min(fecha + timedelta(days=self.rng.randint(lo, hi)), date(2026, 11, 12))
            parcial = cliente[4] == PerfilPago.moroso and sum(ln.subtotal for ln in lineas) > 20
            detalle = ", ".join(n.split(" ")[0].lower() for n in elegidos)
            self._fiado(formatear_id("FIA", i + 1), cliente, fecha, lineas, detalle, pago, parcial)

    def fiados_pendientes(self) -> None:
        carmen, luis, rosa = CLIENTES
        self._fiado("FIA-0045", carmen, date(2026, 10, 27),
                    [self._linea("Pan francés", 120), self._linea("Leche evaporada 400 g", 20)], "panes, leche", None)
        self._fiado("FIA-0046", luis, date(2026, 11, 2),
                    [self._linea("Arroz 1 kg", 19), self._linea("Aceite vegetal 1 L", 2)], "arroz, aceite", None)
        self._fiado("FIA-0047", rosa, date(2026, 11, 5),
                    [self._linea("Gaseosa 3 L", 5), self._linea("Gaseosa 500 ml", 16)], "gaseosas", None)  # fmt: skip

    # ── calibración ──
    def proyeccion_referencia(self) -> Decimal:
        """Proyección del docstring del módulo, con los movimientos ya generados."""
        ventana = [CORTE - timedelta(days=k) for k in range(28, 0, -1)]
        neto = {d: Decimal("0") for d in ventana}
        for mov in self.movs:
            d = mov.fecha_hora.date()
            if d in neto and mov.ordinario:
                neto[d] += mov.con_signo
        media = {wd: sum(v for d, v in neto.items() if d.weekday() == wd) / 4 for wd in range(7)}
        flujo = sum((media[d.weekday()] for d in _dias(CORTE + timedelta(days=1), FECHA_CRITICA)), Decimal("0"))
        return SALDO_CORTE + flujo - self.obligaciones_hasta_30_11()

    @staticmethod
    def obligaciones_hasta_30_11() -> Decimal:
        sabados = sum(1 for d in _dias(CORTE + timedelta(days=1), FECHA_CRITICA) if d.weekday() == 5)
        return MONTO_PEDIDO_ANDINA + LUZ_AGUA + SUELDO_SEMANAL * sabados

    def calibrar(self) -> None:
        dias_proyectados = (FECHA_CRITICA - CORTE).days
        ajuste_diario = (self.proyeccion_referencia() - SALDO_OBJETIVO_30_11) / dias_proyectados
        ajuste_diario = redondear(ajuste_diario)
        for k in range(28, 0, -1):
            compra = self.compras_mayorista[CORTE - timedelta(days=k)]
            compra.monto = compra.monto + ajuste_diario
            if compra.monto <= 0:
                raise ValueError("La calibración dejó una compra sin monto; revisa los parámetros del generador")
        # Redondear el ajuste diario deja un residuo (−649.96): múltiplo de S/ 0.0025 porque la media es de 4 semanas.
        # Subir x una compra de un día de semana que aparece c veces entre el 15 y el 30/11 baja la proyección x·c/4.
        # Con a céntimos en un día que aparece 2 veces y b en uno que aparece 3: baja (2a + 3b)·0.0025, y 2a + 3b = n
        # siempre tiene solución entera → la proyección queda en −650.00 exacto, con montos en céntimos.
        residuo = self.proyeccion_referencia() - SALDO_OBJETIVO_30_11
        n = residuo / Decimal("0.0025")
        if n != n.to_integral_value():
            raise ValueError("Residuo de calibración inesperado")
        n = int(n)
        b = n % 2  # 0 o 1 céntimo en el día que aparece 3 veces
        a = (n - 3 * b) // 2
        proyectados = list(_dias(CORTE + timedelta(days=1), FECHA_CRITICA))
        for veces, centimos in ((2, a), (3, b)):
            if not centimos:
                continue
            dia_semana = next(wd for wd in range(7) if sum(1 for d in proyectados if d.weekday() == wd) == veces)
            dia = max(d for d in self.compras_mayorista if d < CORTE and d.weekday() == dia_semana)
            self.compras_mayorista[dia].monto += Decimal(centimos) / 100
        if self.proyeccion_referencia() != SALDO_OBJETIVO_30_11:
            raise ValueError("La calibración no dejó la proyección del 30/11 en el objetivo exacto")

    def generar(self) -> None:
        for d in _dias(INICIO, FIN_HISTORIA):
            ventas = self.ventas_del_dia(d)
            self.compras_del_dia(d, ventas)
            self.gastos_del_dia(d)
            self.retiros_del_dia(d)
        self.luz_y_agua()
        self.impuestos_rus()
        self.pedidos_andina()
        self.fiados_historicos()
        self.fiados_pendientes()
        self.calibrar()
        self.movs.sort(key=lambda mv: (mv.fecha_hora, mv.tipo.value, mv.monto))

    @property
    def saldo_inicial(self) -> Decimal:
        return SALDO_CORTE - sum((mv.con_signo for mv in self.movs if mv.afecta_caja), Decimal("0"))


def _maestras() -> list:
    objs: list = [m.Rubro(rubro_id=r, nombre=n) for r, n in RUBROS]
    objs += [m.Categoria(categoria_id=c, nombre=n, tipo=t, es_del_negocio=e) for c, n, t, e in CATEGORIAS]
    return objs


def construir_objetos(semilla: int = SEMILLA) -> list:
    """Todos los objetos ORM del dataset, en un orden compatible con las FK."""
    gen = _Generador(semilla)
    gen.generar()
    alta = _dt(INICIO, 8, 0)

    objs = _maestras()
    objs.append(m.Empresa(empresa_id=EMPRESA_ID, rubro_id="RUB-01", nombre_ficticio=NOMBRE_EMPRESA,
                          telefono_whatsapp="+51900000001", zona="SJL", n_trabajadores=1, tiene_ruc=True,
                          regimen_tributario="nuevo_rus", saldo_inicial=gen.saldo_inicial,
                          fecha_saldo_inicial=INICIO, minimo_operativo=MINIMO_OPERATIVO, fecha_alta=alta))  # fmt: skip
    objs.append(m.PreferenciasAlertas(empresa_id=EMPRESA_ID, canales=["whatsapp", "app"], max_por_dia=2,
                                      silencio_desde=time(21, 0), silencio_hasta=time(7, 0), resumen_semanal=True))  # fmt: skip
    for nombre, cat, precio, costo, alias in PRODUCTOS:
        objs.append(m.Producto(producto_id=PRODUCTO_ID[nombre], empresa_id=EMPRESA_ID, categoria_id=CAT[cat],
                               nombre=nombre, alias=alias, precio_venta=Decimal(precio),
                               costo_unitario=Decimal(costo) if costo else None, activo=True))  # fmt: skip
    for cli_id, nombre, alias, tel, perfil in CLIENTES:
        objs.append(m.Cliente(cliente_id=cli_id, empresa_id=EMPRESA_ID, nombre_ficticio=nombre, alias=alias,
                              telefono_ficticio=tel, perfil_pago=perfil, creado_en=alta))  # fmt: skip
    objs.append(m.Proveedor(proveedor_id=PRV_ANDINA, empresa_id=EMPRESA_ID, nombre_ficticio="Distribuidora Andina",
                            telefono_ficticio="+51900000201", plazo_pago_dias=15))  # fmt: skip
    objs.append(m.MovimientoProgramado(programado_id=PRG_LUZ, empresa_id=EMPRESA_ID, categoria_id=CAT["servicios"],
                                       tipo=TipoFlujo.egreso, descripcion="Luz y agua", monto=LUZ_AGUA,
                                       frecuencia=Frecuencia.mensual, dia_mes=16, fecha_inicio=INICIO))  # fmt: skip
    objs.append(m.MovimientoProgramado(programado_id=PRG_SUELDO, empresa_id=EMPRESA_ID,
                                       categoria_id=CAT["retiro personal"], tipo=TipoFlujo.egreso,
                                       descripcion="Sueldo de Pedro", monto=SUELDO_SEMANAL,
                                       frecuencia=Frecuencia.semanal, dia_semana=6, es_sueldo=True,
                                       fecha_inicio=INICIO_SUELDO))  # fmt: skip
    objs += gen.impuestos + gen.deudas + gen.fiados

    n_det = 0
    for i, mov in enumerate(gen.movs, start=1):
        tid = formatear_id("MOV", i)
        objs.append(m.Transaccion(transaccion_id=tid, empresa_id=EMPRESA_ID, fecha_hora=mov.fecha_hora,
                                  tipo=mov.tipo, categoria_id=CAT[mov.categoria], descripcion=mov.descripcion, monto=mov.monto,
                                  metodo_pago=mov.metodo, afecta_caja=mov.afecta_caja, canal=mov.canal,
                                  confianza_extraccion=None if mov.canal == Canal.manual else mov.confianza,
                                  fiado_id=mov.fiado_id, deuda_id=mov.deuda_id, impuesto_id=mov.impuesto_id,
                                  programado_id=mov.programado_id,
                                  creado_en=mov.fecha_hora + timedelta(minutes=2)))  # fmt: skip
        for ln in mov.lineas:
            n_det += 1
            objs.append(m.DetalleTransaccion(detalle_id=formatear_id("DET", n_det), transaccion_id=tid,
                                             producto_id=PRODUCTO_ID.get(ln.producto), descripcion=ln.descripcion,
                                             cantidad=ln.cantidad, precio_unitario=ln.precio,
                                             costo_unitario=ln.costo, subtotal=ln.subtotal))  # fmt: skip

    objs += _saldo_diario(gen)
    objs.append(m.ReglaMeta(meta_id="MET-0001", empresa_id=EMPRESA_ID, plantilla=PlantillaMeta.apartar_para_pedido,
                            tipo_regla=TipoRegla.porcentaje_de_venta, valor=Decimal("0.1000"),
                            destino="fondo_pedidos", acumulado=Decimal("420.00"),
                            recordatorio_frecuencia=Frecuencia.semanal, recordatorio_dia=1,
                            estado=EstadoMeta.activa, fecha_inicio=date(2026, 10, 19)))  # fmt: skip
    for mes, score, sub in [("2026-08", 38, (40, 30, 100)), ("2026-09", 52, (75, 40, 100)),
                            ("2026-10", 64, (88, 55, 100))]:  # fmt: skip
        objs.append(m.ScoreSalud(empresa_id=EMPRESA_ID, mes=mes, score=score, version_formula="score-v1",
                                 subindicadores={"constancia_registro": sub[0], "separacion_personal": sub[1],
                                                 "impuestos_al_dia": sub[2]}))  # fmt: skip
    objs.append(m.Evento(evento_id="EVT-0001", empresa_id=EMPRESA_ID, tipo_evento=TipoEvento.retiro_excesivo,
                         fecha_inicio=date(2026, 11, 1), fecha_fin=FIN_HISTORIA,
                         descripcion="Retiros para la casa S/ 700 por encima de lo usual"))  # fmt: skip
    objs.append(m.Evento(evento_id="EVT-0002", empresa_id=EMPRESA_ID, tipo_evento=TipoEvento.cliente_no_paga,
                         fecha_inicio=date(2026, 10, 27), descripcion="La Sra. Carmen no paga su fiado de S/ 120"))  # fmt: skip
    return objs


def _saldo_diario(gen: _Generador) -> list[m.SaldoDiario]:
    """Serie materializada de saldo de cierre + etiqueta deficit_14d (null si la ventana pasa del corte)."""
    neto: dict[date, Decimal] = {}
    for mov in gen.movs:
        if mov.afecta_caja:
            d = mov.fecha_hora.date()
            neto[d] = neto.get(d, Decimal("0")) + mov.con_signo
    saldo, cierres = gen.saldo_inicial, {}
    for d in _dias(INICIO, FIN_HISTORIA):
        saldo += neto.get(d, Decimal("0"))
        cierres[d] = saldo
    filas = []
    for d, s in cierres.items():
        fin = d + timedelta(days=14)
        deficit = None if fin > FIN_HISTORIA else any(
            cierres[x] < MINIMO_OPERATIVO for x in _dias(d + timedelta(days=1), fin)
        )
        filas.append(m.SaldoDiario(empresa_id=EMPRESA_ID, fecha=d, saldo_cierre=s, deficit_14d=deficit))
    return filas


def sembrar(db: Session, semilla: int = SEMILLA) -> int:
    """Inserta el dataset de Pedro. Devuelve el número de filas. No hace commit."""
    objs = construir_objetos(semilla)
    # Sin relationships el ORM no ordena por FK entre tablas: se inserta tabla por tabla en orden de dependencias.
    por_tabla: dict[str, list] = {}
    for obj in objs:
        por_tabla.setdefault(obj.__table__.name, []).append(obj)
    for tabla in Base.metadata.sorted_tables:
        if tabla.name in por_tabla:
            db.add_all(por_tabla.pop(tabla.name))
            db.flush()
    return len(objs)


def resumen_calibracion(semilla: int = SEMILLA) -> dict:
    """Cifras de control de la historia (útil para depurar el generador sin BD)."""
    gen = _Generador(semilla)
    gen.generar()
    ret = lambda d1, d2: sum(mv.monto for mv in gen.movs if mv.tipo == TipoMovimiento.retiro_personal  # noqa: E731
                             and d1 <= mv.fecha_hora.date() <= d2)  # fmt: skip
    return {
        "saldo_inicial": gen.saldo_inicial,
        "proyeccion_30_11": redondear(gen.proyeccion_referencia()),
        "n_movimientos": len(gen.movs),
        "retiros_nov_1_13": ret(date(2026, 11, 1), date(2026, 11, 13)),
        "retiros_sep_1_13": ret(date(2026, 9, 1), date(2026, 9, 13)),
        "retiros_oct_1_13": ret(date(2026, 10, 1), date(2026, 10, 13)),
        "fiados_pendientes": sum(f.monto for f in gen.fiados if f.fecha_pago_total is None),
        "saldo_minimo_historico": min(f.saldo_cierre for f in _saldo_diario(gen)),
    }

