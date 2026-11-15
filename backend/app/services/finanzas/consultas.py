"""B1 — Consultas a fecha de corte: saldo, fiados, deudas (pedidos), impuestos y piezas que reutilizan el forecast,
el chequeo, el simulador y las alertas.

Reglas (PLAN §8, context.md §8):
- Nada calculado se guarda: saldo, pendiente, atraso y estados salen de aquí al momento de responder.
- A una fecha de corte solo cuenta lo registrado (`creado_en`) y ocurrido (`fecha_hora`) antes del fin de ese día en
  Lima, y nunca lo anulado. `metodo_pago = credito` ⇒ `afecta_caja = false`: lo fiado o pedido a crédito no mueve caja.
- `pago_tardio`, `deficit_14d`, `eventos` y `clientes.perfil_pago` nunca se leen aquí.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errors import NoEncontrado
from app.db import models as m
from app.schemas.common import TIPOS_INGRESO, EstadoCuenta, Frecuencia, TipoDeuda, TipoMovimiento, redondear
from app.services.ingesta.texto import NOMBRE_MES, normalizar

Tx = m.Transaccion
T = TipoMovimiento
CERO = Decimal("0.00")

DIAS_POR_VENCER = 3          # estado `por_vencer`: vence dentro de 3 días (contrato §4.3/§4.4)
DIAS_COMPROMISO_FIADO = 14   # si el fiado no tiene fecha de compromiso, se asume a 14 días


# ── utilidades de fecha de corte ────────────────────────────────────────────────────────────────


def corte_de(fecha_corte: date | None) -> date:
    return fecha_corte or reloj.hoy()


def fin_del_dia(d: date) -> datetime:
    return reloj.inicio_del_dia(d + timedelta(days=1))


def dia_lima(dt: datetime) -> date:
    return reloj.a_lima(dt).date()


def vigentes(empresa_id: str, corte: date) -> list:
    """Condiciones de una transacción que existe a la fecha de corte."""
    fin = fin_del_dia(corte)
    return [Tx.empresa_id == empresa_id, ~Tx.anulada, Tx.fecha_hora < fin, Tx.creado_en < fin]


CON_SIGNO = case((Tx.tipo.in_(list(TIPOS_INGRESO)), Tx.monto), else_=-Tx.monto)
SIN_VINCULO = and_(Tx.fiado_id.is_(None), Tx.deuda_id.is_(None), Tx.impuesto_id.is_(None), Tx.programado_id.is_(None))


def empresa_o_404(db: Session, empresa_id: str) -> m.Empresa:
    empresa = db.get(m.Empresa, empresa_id) if db is not None else None
    if empresa is None:
        raise NoEncontrado("No encontré esa empresa.")
    return empresa


def estado_por_fecha(pendiente: Decimal, vence: date, corte: date) -> EstadoCuenta:
    if pendiente <= 0:
        return EstadoCuenta.pagado
    if vence < corte:
        return EstadoCuenta.vencido
    if (vence - corte).days <= DIAS_POR_VENCER:
        return EstadoCuenta.por_vencer
    return EstadoCuenta.pendiente


def coincide_estado(estado_item: EstadoCuenta, filtro: str | None) -> bool:
    """`pendiente` en los endpoints = todo lo que falta pagar (pendiente, por vencer y vencido)."""
    if filtro in (None, "", "todos"):
        return True
    if filtro == EstadoCuenta.pendiente.value:
        return estado_item != EstadoCuenta.pagado
    return estado_item.value == filtro


def sumar_meses(d: date, meses: int) -> date:
    total = d.year * 12 + (d.month - 1) + meses
    anio, mes = divmod(total, 12)
    mes += 1
    ultimo = (date(anio + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).day
    return date(anio, mes, min(d.day, ultimo))


def ultimo_dia_mes(anio: int, mes: int) -> int:
    return (date(anio + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).day


# ── saldo de caja ───────────────────────────────────────────────────────────────────────────────


def _saldo(db: Session, empresa: m.Empresa, corte: date) -> Decimal:
    if corte < empresa.fecha_saldo_inicial:
        return redondear(empresa.saldo_inicial)
    neto = db.scalar(select(func.coalesce(func.sum(CON_SIGNO), 0)).where(
        *vigentes(empresa.empresa_id, corte), Tx.afecta_caja,
        Tx.fecha_hora >= reloj.inicio_del_dia(empresa.fecha_saldo_inicial)))  # fmt: skip
    return redondear(empresa.saldo_inicial + Decimal(neto))


def saldo_caja(db: Session, empresa_id: str, fecha_corte: date | None = None) -> Decimal:
    """Saldo de la caja del negocio al cierre del día de corte = saldo inicial + Σ movimientos que afectan caja."""
    return _saldo(db, empresa_o_404(db, empresa_id), corte_de(fecha_corte))


def dias_con_datos(db: Session, empresa_id: str, corte: date) -> int:
    filas = db.scalars(select(Tx.fecha_hora).where(*vigentes(empresa_id, corte))).all()
    return len({dia_lima(f) for f in filas})


# ── fiados (cuentas por cobrar) ─────────────────────────────────────────────────────────────────


@dataclass
class FiadoCalc:
    fiado: m.CuadernoFiado
    cliente: str
    cobrado: Decimal
    pendiente: Decimal
    compromiso: date
    fecha_pago: date | None  # día en que quedó pagado del todo (a la fecha de corte)
    estado: EstadoCuenta
    dias_transcurridos: int
    cobros: list[tuple[date, Decimal]] = field(default_factory=list)

    @property
    def atrasado(self) -> bool | None:
        """Atraso conocido a la fecha de corte: pagado tarde, o impago con el compromiso ya vencido. None si aún no se sabe."""
        if self.fecha_pago is not None:
            return self.fecha_pago > self.compromiso
        if self.estado == EstadoCuenta.vencido:
            return True
        return None


def _origen_vigente(filas: list[tuple], corte: date) -> bool:
    """El registro existe al corte si no tiene transacción de origen o si alguna está vigente."""
    if not filas:
        return True
    fin = fin_del_dia(corte)
    return any(not anulada and creado < fin and fh < fin for anulada, creado, fh in filas)


def cuentas_fiado(db: Session, empresa_id: str, corte: date) -> list[FiadoCalc]:
    fiados = db.execute(select(m.CuadernoFiado, m.Cliente.nombre_ficticio)
                        .join(m.Cliente, m.Cliente.cliente_id == m.CuadernoFiado.cliente_id)
                        .where(m.CuadernoFiado.empresa_id == empresa_id, m.CuadernoFiado.fecha_fiado <= corte)
                        .order_by(m.CuadernoFiado.fecha_fiado, m.CuadernoFiado.fiado_id)).all()  # fmt: skip
    if not fiados:
        return []
    origen: dict[str, list] = defaultdict(list)
    for fid, anulada, creado, fh in db.execute(select(Tx.fiado_id, Tx.anulada, Tx.creado_en, Tx.fecha_hora).where(
            Tx.empresa_id == empresa_id, Tx.fiado_id.is_not(None), Tx.tipo == T.venta)):  # fmt: skip
        origen[fid].append((anulada, creado, fh))
    cobros: dict[str, list] = defaultdict(list)
    for fid, fh, monto in db.execute(select(Tx.fiado_id, Tx.fecha_hora, Tx.monto).where(
            *vigentes(empresa_id, corte), Tx.tipo == T.cobro_fiado, Tx.fiado_id.is_not(None))
            .order_by(Tx.fecha_hora, Tx.transaccion_id)):  # fmt: skip
        cobros[fid].append((dia_lima(fh), Decimal(monto)))

    salida = []
    for fiado, cliente in fiados:
        if not _origen_vigente(origen.get(fiado.fiado_id, []), corte):
            continue
        acumulado, fecha_pago = CERO, None
        for dia, monto in cobros.get(fiado.fiado_id, []):
            acumulado += monto
            if fecha_pago is None and acumulado >= fiado.monto:
                fecha_pago = dia
        pendiente = max(CERO, redondear(fiado.monto - acumulado))
        compromiso = fiado.fecha_compromiso or fiado.fecha_fiado + timedelta(days=DIAS_COMPROMISO_FIADO)
        salida.append(FiadoCalc(
            fiado=fiado, cliente=cliente, cobrado=redondear(acumulado), pendiente=pendiente, compromiso=compromiso,
            fecha_pago=fecha_pago if pendiente <= 0 else None, estado=estado_por_fecha(pendiente, compromiso, corte),
            dias_transcurridos=(corte - fiado.fecha_fiado).days, cobros=cobros.get(fiado.fiado_id, []),
        ))  # fmt: skip
    return salida


def fiados_pendientes(db: Session, empresa_id: str, corte: date) -> list[FiadoCalc]:
    return [f for f in cuentas_fiado(db, empresa_id, corte) if f.pendiente > 0]


# ── deudas (pedidos a crédito y préstamos) ──────────────────────────────────────────────────────


@dataclass
class DeudaCalc:
    deuda: m.Deuda
    nombre: str
    pagado: Decimal
    pendiente: Decimal
    estado: EstadoCuenta
    dias_para_vencer: int
    creado_en: datetime | None  # creado_en de la transacción que la originó (si existe)

    @property
    def es_proveedor(self) -> bool:
        return self.deuda.tipo == TipoDeuda.proveedor


def cuentas_deuda(db: Session, empresa_id: str, corte: date, solo_proveedor: bool = False) -> list[DeudaCalc]:
    q = (select(m.Deuda, m.Proveedor.nombre_ficticio)
         .outerjoin(m.Proveedor, m.Proveedor.proveedor_id == m.Deuda.proveedor_id)
         .where(m.Deuda.empresa_id == empresa_id, m.Deuda.fecha_inicio <= corte)
         .order_by(m.Deuda.fecha_vencimiento, m.Deuda.deuda_id))  # fmt: skip
    if solo_proveedor:
        q = q.where(m.Deuda.tipo == TipoDeuda.proveedor)
    deudas = db.execute(q).all()
    if not deudas:
        return []
    origen: dict[str, list] = defaultdict(list)
    for did, anulada, creado, fh in db.execute(select(Tx.deuda_id, Tx.anulada, Tx.creado_en, Tx.fecha_hora).where(
            Tx.empresa_id == empresa_id, Tx.deuda_id.is_not(None),
            Tx.tipo.in_([T.compra, T.prestamo_recibido]))):  # fmt: skip
        origen[did].append((anulada, creado, fh))
    pagos = dict(db.execute(select(Tx.deuda_id, func.sum(Tx.monto)).where(
        *vigentes(empresa_id, corte), Tx.tipo.in_([T.pago_proveedor, T.pago_prestamo]), Tx.deuda_id.is_not(None))
        .group_by(Tx.deuda_id)).all())  # fmt: skip

    salida = []
    for deuda, proveedor in deudas:
        filas = origen.get(deuda.deuda_id, [])
        if not _origen_vigente(filas, corte):
            continue
        pagado = redondear(Decimal(pagos.get(deuda.deuda_id) or 0))
        pendiente = max(CERO, redondear(deuda.monto_total_a_pagar - pagado))
        creado = min((c for an, c, _ in filas if not an), default=None)
        salida.append(DeudaCalc(
            deuda=deuda, nombre=proveedor or deuda.acreedor_nombre or "Prestamista", pagado=pagado, pendiente=pendiente,
            estado=estado_por_fecha(pendiente, deuda.fecha_vencimiento, corte),
            dias_para_vencer=(deuda.fecha_vencimiento - corte).days, creado_en=creado,
        ))  # fmt: skip
    return salida


DIAS_FRECUENCIA = {Frecuencia.diaria: 1, Frecuencia.semanal: 7, Frecuencia.quincenal: 15}


def _fechas_cuota(deuda: m.Deuda, hasta: date) -> list[date]:
    frecuencia = Frecuencia(deuda.frecuencia_cuota)
    fechas, k = [], 1
    while True:
        d = (sumar_meses(deuda.fecha_inicio, k) if frecuencia == Frecuencia.mensual
             else deuda.fecha_inicio + timedelta(days=DIAS_FRECUENCIA[frecuencia] * k))  # fmt: skip
        if d > hasta or k > 400:
            return fechas
        fechas.append(d)
        k += 1


def cronograma_pagos(dc: DeudaCalc, corte: date, hasta: date) -> list[tuple[date, Decimal]]:
    """Pagos esperados de lo pendiente, a partir de mañana. Lo atrasado se proyecta para mañana (conservador)."""
    if dc.pendiente <= 0:
        return []
    manana = corte + timedelta(days=1)
    deuda = dc.deuda
    if not (deuda.frecuencia_cuota and deuda.monto_cuota):
        fecha = max(deuda.fecha_vencimiento, manana)
        return [(fecha, dc.pendiente)] if fecha <= hasta else []
    cuota = Decimal(deuda.monto_cuota)
    fechas = _fechas_cuota(deuda, max(hasta, deuda.fecha_vencimiento))
    esperado_al_corte = min(deuda.monto_total_a_pagar, cuota * sum(1 for d in fechas if d <= corte))
    pagos, restante = [], dc.pendiente
    atraso = max(CERO, redondear(esperado_al_corte - dc.pagado))
    if atraso > 0:
        pagos.append((manana, min(atraso, restante)))
        restante -= pagos[-1][1]
    for d in fechas:
        if restante <= 0:
            break
        if d <= corte:
            continue
        monto = min(cuota, restante)
        pagos.append((d, monto))
        restante -= monto
    if restante > 0:
        pagos.append((max(deuda.fecha_vencimiento, manana), restante))
    return [(d, redondear(mo)) for d, mo in pagos if d <= hasta and mo > 0]


# ── impuestos ───────────────────────────────────────────────────────────────────────────────────


PREFIJO_ANULADO = "anulado_"  # impuestos no tienen columna `anulada`: se marca el régimen (nada se borra)


def impuesto_anulado(imp: m.Impuesto) -> bool:
    return imp.regimen.startswith(PREFIJO_ANULADO)


@dataclass
class ImpuestoCalc:
    impuesto: m.Impuesto
    pagado: bool
    estado: str  # al_dia (pagado) | pendiente | vencido

    @property
    def nombre(self) -> str:
        anio, mes = map(int, self.impuesto.periodo.split("-"))
        regimen = "RUS" if "rus" in self.impuesto.regimen.lower() else self.impuesto.regimen.replace("_", " ").upper()
        return f"{regimen} de {NOMBRE_MES[mes]}"


def _impuestos(db: Session, empresa_id: str, con_anulados: bool = False) -> list[m.Impuesto]:
    filas = db.scalars(select(m.Impuesto).where(m.Impuesto.empresa_id == empresa_id)
                       .order_by(m.Impuesto.fecha_vencimiento, m.Impuesto.impuesto_id)).all()  # fmt: skip
    return list(filas) if con_anulados else [i for i in filas if not impuesto_anulado(i)]


def cuentas_impuesto(db: Session, empresa_id: str, corte: date) -> list[ImpuestoCalc]:
    impuestos = _impuestos(db, empresa_id)
    con_pago = set(db.scalars(select(Tx.impuesto_id).where(*vigentes(empresa_id, corte), Tx.tipo == T.pago_impuesto,
                                                           Tx.impuesto_id.is_not(None))).all())  # fmt: skip
    salida = []
    for imp in impuestos:
        pagado = imp.impuesto_id in con_pago or (imp.fecha_pago is not None and imp.fecha_pago <= corte)
        if pagado:
            estado = "al_dia"
        else:
            estado = "vencido" if imp.fecha_vencimiento < corte else "pendiente"
        salida.append(ImpuestoCalc(imp, pagado, estado))
    return salida


def _vencimiento_periodo(periodo: str) -> date:
    anio, mes = map(int, periodo.split("-"))
    return date(anio + mes // 12, mes % 12 + 1, 15)


# ── movimientos programados (luz, alquiler, sueldo) ─────────────────────────────────────────────


def programados(db: Session, empresa_id: str) -> list[m.MovimientoProgramado]:
    return db.scalars(select(m.MovimientoProgramado).where(m.MovimientoProgramado.empresa_id == empresa_id)
                      .order_by(m.MovimientoProgramado.programado_id)).all()  # fmt: skip


def vigente_en(p: m.MovimientoProgramado, d: date) -> bool:
    if not p.activo and p.fecha_fin is None:
        return False
    return p.fecha_inicio <= d and (p.fecha_fin is None or d <= p.fecha_fin)


def _dia_mes(d: date, dia: int) -> int:
    return min(dia, ultimo_dia_mes(d.year, d.month))


def ocurre_en(p: m.MovimientoProgramado, d: date) -> bool:
    if not vigente_en(p, d):
        return False
    frecuencia = Frecuencia(p.frecuencia)
    if frecuencia == Frecuencia.diaria:
        return True
    if frecuencia == Frecuencia.semanal:
        return d.isoweekday() == (p.dia_semana or 6)
    dia = p.dia_mes or 1
    if frecuencia == Frecuencia.mensual:
        return d.day == _dia_mes(d, dia)
    return d.day in (_dia_mes(d, dia), _dia_mes(d, dia + 15))  # quincenal


def ocurrencias(p: m.MovimientoProgramado, desde: date, hasta: date) -> list[date]:
    salida, d = [], desde
    while d <= hasta:
        if ocurre_en(p, d):
            salida.append(d)
        d += timedelta(days=1)
    return salida


def periodo_de(p: m.MovimientoProgramado, d: date) -> tuple[date, date]:
    """Periodo al que pertenece una ocurrencia (para no proyectar lo que ya se pagó en ese periodo)."""
    frecuencia = Frecuencia(p.frecuencia)
    if frecuencia == Frecuencia.diaria:
        return d, d
    if frecuencia == Frecuencia.semanal:
        lunes = d - timedelta(days=d.weekday())
        return lunes, lunes + timedelta(days=6)
    if frecuencia == Frecuencia.mensual:
        return d.replace(day=1), d.replace(day=ultimo_dia_mes(d.year, d.month))
    if d.day <= 15:
        return d.replace(day=1), d.replace(day=15)
    return d.replace(day=16), d.replace(day=ultimo_dia_mes(d.year, d.month))


def dias_pagados_programado(db: Session, empresa_id: str, corte: date) -> dict[str, list[date]]:
    filas = db.execute(select(Tx.programado_id, Tx.fecha_hora).where(*vigentes(empresa_id, corte),
                                                                     Tx.programado_id.is_not(None))).all()  # fmt: skip
    salida: dict[str, list[date]] = defaultdict(list)
    for pid, fh in filas:
        salida[pid].append(dia_lima(fh))
    return salida


def sueldo_vigente(db: Session, empresa_id: str, d: date) -> m.MovimientoProgramado | None:
    return next((p for p in programados(db, empresa_id) if p.es_sueldo and vigente_en(p, d)), None)


def sueldo_esperado(db: Session, empresa_id: str, desde: date, hasta: date) -> Decimal | None:
    """Σ de las ocurrencias del sueldo fijo en el rango (None si nunca hubo sueldo fijo en ese rango)."""
    sueldos = [p for p in programados(db, empresa_id) if p.es_sueldo]
    total, alguno = CERO, False
    for p in sueldos:
        n = len(ocurrencias(p, desde, hasta))
        if n or any(vigente_en(p, d) for d in (desde, hasta)):
            alguno = True
        total += Decimal(p.monto) * n
    return redondear(total) if alguno else None


# ── sumas por periodo (resumen, análisis, alertas) ──────────────────────────────────────────────


def suma(db: Session, empresa_id: str, desde: date, hasta: date, corte: date, *condiciones) -> Decimal:
    valor = db.scalar(select(func.coalesce(func.sum(Tx.monto), 0)).where(
        *vigentes(empresa_id, corte), Tx.fecha_hora >= reloj.inicio_del_dia(desde), Tx.fecha_hora < fin_del_dia(hasta),
        *condiciones))  # fmt: skip
    return redondear(Decimal(valor))


def retiros(db: Session, empresa_id: str, desde: date, hasta: date, corte: date) -> Decimal:
    return suma(db, empresa_id, desde, hasta, corte, Tx.tipo == T.retiro_personal, Tx.afecta_caja)


def mismo_corte_en_meses_previos(empresa: m.Empresa, corte: date, meses: int = 3) -> list[tuple[date, date]]:
    """Rangos [día 1, mismo día de corte] de los meses anteriores con datos completos desde el día 1."""
    rangos = []
    for k in range(1, meses + 1):
        inicio = sumar_meses(corte.replace(day=1), -k)
        if inicio < empresa.fecha_saldo_inicial:
            continue
        fin = inicio.replace(day=min(corte.day, ultimo_dia_mes(inicio.year, inicio.month)))
        rangos.append((inicio, fin))
    return rangos


@dataclass
class Retiros:
    mes: Decimal
    promedio_historico: Decimal | None
    meses_comparados: int

    @property
    def exceso(self) -> Decimal:
        if self.promedio_historico is None:
            return CERO
        return max(CERO, redondear(self.mes - self.promedio_historico))


def retiros_del_mes(db: Session, empresa: m.Empresa, corte: date) -> Retiros:
    actual = retiros(db, empresa.empresa_id, corte.replace(day=1), corte, corte)
    previos = [retiros(db, empresa.empresa_id, a, b, corte) for a, b in mismo_corte_en_meses_previos(empresa, corte)]
    promedio = redondear(sum(previos, CERO) / len(previos)) if previos else None
    return Retiros(actual, promedio, len(previos))


# ── flujo ordinario diario (base del forecast) ──────────────────────────────────────────────────


@dataclass
class FlujoDia:
    ingreso: Decimal = CERO
    egreso: Decimal = CERO
    retiro: Decimal = CERO  # parte del egreso que es retiro personal

    @property
    def neto(self) -> Decimal:
        return self.ingreso - self.egreso


def flujos_ordinarios(db: Session, empresa_id: str, desde: date, hasta: date, corte: date) -> dict[date, FlujoDia]:
    """Movimientos que afectan caja sin vínculo a fiado/deuda/impuesto/programado (esos se proyectan aparte)."""
    filas = db.execute(select(Tx.fecha_hora, Tx.tipo, Tx.monto).where(
        *vigentes(empresa_id, corte), Tx.afecta_caja, SIN_VINCULO,
        Tx.fecha_hora >= reloj.inicio_del_dia(desde), Tx.fecha_hora < fin_del_dia(hasta))).all()  # fmt: skip
    salida: dict[date, FlujoDia] = {}
    d = desde
    while d <= hasta:
        salida[d] = FlujoDia()
        d += timedelta(days=1)
    for fh, tipo, monto in filas:
        f = salida.setdefault(dia_lima(fh), FlujoDia())
        if TipoMovimiento(tipo) in TIPOS_INGRESO:
            f.ingreso += Decimal(monto)
        else:
            f.egreso += Decimal(monto)
            if tipo == T.retiro_personal:
                f.retiro += Decimal(monto)
    return salida


def primer_dia_con_datos(db: Session, empresa_id: str, corte: date) -> date | None:
    primera = db.scalar(select(func.min(Tx.fecha_hora)).where(*vigentes(empresa_id, corte)))
    return dia_lima(primera) if primera else None


# ── ventas por producto (chequeo de pedidos) ────────────────────────────────────────────────────


def productos_de_proveedor(db: Session, empresa_id: str, proveedor_id: str, corte: date) -> set[str]:
    """Productos que ese proveedor trajo antes (detalle de los pedidos a crédito vinculados a sus deudas)."""
    filas = db.scalars(select(m.DetalleTransaccion.producto_id)
                       .join(Tx, Tx.transaccion_id == m.DetalleTransaccion.transaccion_id)
                       .join(m.Deuda, m.Deuda.deuda_id == Tx.deuda_id)
                       .where(*vigentes(empresa_id, corte), m.Deuda.proveedor_id == proveedor_id,
                              m.DetalleTransaccion.producto_id.is_not(None))).all()  # fmt: skip
    return set(filas)


def ventas_de_productos(db: Session, empresa_id: str, productos: set[str] | None, desde: date, hasta: date,
                        corte: date) -> Decimal:  # fmt: skip
    """Ventas (a precio de venta, al contado o fiadas) de esos productos; `None` = todas las ventas."""
    if productos is None:
        return suma(db, empresa_id, desde, hasta, corte, Tx.tipo == T.venta)
    if not productos:
        return CERO
    valor = db.scalar(select(func.coalesce(func.sum(m.DetalleTransaccion.subtotal), 0))
                      .join(Tx, Tx.transaccion_id == m.DetalleTransaccion.transaccion_id)
                      .where(*vigentes(empresa_id, corte), Tx.tipo == T.venta,
                             Tx.fecha_hora >= reloj.inicio_del_dia(desde), Tx.fecha_hora < fin_del_dia(hasta),
                             m.DetalleTransaccion.producto_id.in_(productos)))  # fmt: skip
    return redondear(Decimal(valor))


PALABRAS_GENERICAS = {"distribuidora", "distribuidor", "distribuciones", "comercial", "comercializadora", "mayorista",
                      "proveedor", "empresa", "negocio", "sac", "eirl", "srl", "del", "los", "las"}


def buscar_proveedor(db: Session, empresa_id: str, nombre: str | None) -> m.Proveedor | None:
    clave = normalizar(nombre or "")
    if not clave:
        return None
    proveedores = db.scalars(select(m.Proveedor).where(m.Proveedor.empresa_id == empresa_id)).all()
    for p in proveedores:
        n = normalizar(p.nombre_ficticio)
        if clave == n or clave in n or n in clave:
            return p
    palabras = {w for w in clave.split() if len(w) >= 3} - PALABRAS_GENERICAS
    return next((p for p in proveedores if palabras & (set(normalizar(p.nombre_ficticio).split()) - PALABRAS_GENERICAS)),
                None)  # fmt: skip


# ── interfaz B (§4.2): fiados, pedidos e impuestos ─────────────────────────────────────────────


def fiados(db: Session, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None):
    from app.services.finanzas.riesgo import respuesta_fiados

    return respuesta_fiados(db, empresa_id, estado, corte_de(fecha_corte))


def estado_impuestos(db: Session, empresa_id: str, fecha_corte: date | None = None):
    from app.schemas.cuentas import EstadoImpuestos

    corte = corte_de(fecha_corte)
    empresa_o_404(db, empresa_id)
    calc = cuentas_impuesto(db, empresa_id, corte)
    vencidos = [c for c in calc if c.estado == "vencido"]
    impagos = [c for c in calc if not c.pagado]
    if impagos:
        proximo = min(impagos, key=lambda c: c.impuesto.fecha_vencimiento)
        return EstadoImpuestos(estado="vencido" if vencidos else "al_dia", impuesto_id=proximo.impuesto.impuesto_id,
                               proximo_vencimiento=proximo.impuesto.fecha_vencimiento,
                               monto_estimado=proximo.impuesto.monto, nombre=proximo.nombre)  # fmt: skip
    if not calc:
        return EstadoImpuestos(estado="al_dia", proximo_vencimiento=None, monto_estimado=None)
    ultimo = max(calc, key=lambda c: c.impuesto.periodo)
    # El siguiente mes estimado va después del último periodo registrado, aunque se haya anulado (no reaparece).
    ultimo_periodo = max(i.periodo for i in _impuestos(db, empresa_id, con_anulados=True))
    siguiente = sumar_meses(date.fromisoformat(f"{ultimo_periodo}-01"), 1).strftime("%Y-%m")
    return EstadoImpuestos(estado="al_dia", proximo_vencimiento=_vencimiento_periodo(siguiente),
                           monto_estimado=ultimo.impuesto.monto, nombre=f"RUS de {NOMBRE_MES[int(siguiente[5:])]}")  # fmt: skip


def pedidos(db: Session, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None):
    """Cuentas por pagar a proveedores (deudas con tipo = proveedor). `pedido_id` es el `deuda_id`."""
    from app.schemas.cuentas import PedidoItem, PedidosResponse

    corte = corte_de(fecha_corte)
    empresa_o_404(db, empresa_id)
    items = [PedidoItem(pedido_id=dc.deuda.deuda_id, proveedor=dc.nombre, monto=dc.deuda.monto_total_a_pagar,
                        monto_pendiente=dc.pendiente, fecha_pedido=dc.deuda.fecha_inicio,
                        fecha_vencimiento=dc.deuda.fecha_vencimiento, estado=dc.estado,
                        dias_para_vencer=dc.dias_para_vencer)
             for dc in cuentas_deuda(db, empresa_id, corte, solo_proveedor=True) if coincide_estado(dc.estado, estado)]  # fmt: skip
    return PedidosResponse(total_pendiente=sum((i.monto_pendiente for i in items), CERO), items=items,
                           impuestos=estado_impuestos(db, empresa_id, corte))  # fmt: skip
