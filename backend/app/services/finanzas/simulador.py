"""B9 — Simulador determinístico sobre la serie del forecast (contract.md §4.6).

Cada acción transforma los eventos con fecha de la proyección (o el flujo diario, para los retiros) y se recalcula
la línea esperada (p50). Acciones: `reducir_pedido`, `pagar_en_partes`, `diferir_pago`, `cobrar_fiados`,
`limitar_retiros`, `ajustar_gasto`. Se aplican en ese orden, sin importar el orden del request.

Qué se compara: el saldo más bajo en la ventana de decisión, desde mañana hasta el día crítico de la proyección
(si no hay día crítico, hasta el final del horizonte). Si una acción mueve un pago a una fecha posterior que todavía
cae dentro del horizonte, la ventana se alarga hasta esa fecha (no se esconde el problema). Un pago que queda fuera del
horizonte (p. ej. la 2.ª parte el 15/12 con horizonte al 14/12) no se evalúa y se avisa en `limites`/`notas`.
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import Validacion
from app.schemas.common import TipoAccionSimulador as TA
from app.schemas.common import redondear
from app.schemas.simulador import Accion, PuntoSimulado, ResultadoSaldo, SimulacionResponse
from app.services.finanzas import proyeccion as fc
from app.services.finanzas.modelo_ml import meta_b
from app.services.ingesta.texto import fecha_corta, soles

MODELO = "simulador-deterministico"
VERSION = "0.1.0"
DIAS_ENTRE_PARTES = 15
ORDEN = [TA.reducir_pedido, TA.pagar_en_partes, TA.diferir_pago, TA.cobrar_fiados, TA.limitar_retiros, TA.ajustar_gasto]
CERO = Decimal("0.00")


@dataclass
class Escenario:
    proy: fc.Proyeccion
    eventos: list[fc.Evento]
    menos_egreso: dict[int, Decimal] = field(default_factory=dict)
    fechas_movidas: list[date] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)

    def copia(self) -> "Escenario":
        return Escenario(self.proy, list(self.eventos), dict(self.menos_egreso), list(self.fechas_movidas),
                         list(self.notas))  # fmt: skip

    def puntos(self) -> list[fc.Punto]:
        return self.proy.puntos(self.eventos, self.menos_egreso)

    def pendiente(self, deuda_id: str) -> Decimal:
        return sum((-e.monto for e in self.eventos if e.deuda_id == deuda_id), CERO)


def _repartir(total: Decimal, partes: int) -> list[Decimal]:
    base = redondear(total / partes)
    montos = [base] * (partes - 1)
    return montos + [redondear(total - sum(montos, CERO))]


def reducir(esc: Escenario, deuda_id: str, nuevo_total: Decimal, pagado: Decimal = CERO) -> None:
    eventos = [e for e in esc.eventos if e.deuda_id == deuda_id]
    actual = esc.pendiente(deuda_id)
    if not eventos or actual <= 0:
        return
    nuevo = max(CERO, redondear(Decimal(nuevo_total) - pagado))
    montos = [redondear(-e.monto * nuevo / actual) for e in eventos]
    montos[-1] = nuevo - sum(montos[:-1], CERO)
    cambio = {id(e): mo for e, mo in zip(eventos, montos, strict=True)}
    esc.eventos = [replace(e, monto=-cambio[id(e)]) if id(e) in cambio else e for e in esc.eventos]


def _reprogramar(esc: Escenario, deuda_id: str, fechas: list[date], montos: list[Decimal]) -> None:
    plantilla = next(e for e in esc.eventos if e.deuda_id == deuda_id)
    esc.eventos = [e for e in esc.eventos if e.deuda_id != deuda_id]
    manana = esc.proy.corte + timedelta(days=1)
    for i, (d, mo) in enumerate(zip(fechas, montos, strict=True), start=1):
        d = max(d, manana)
        if d > esc.proy.fin:
            esc.notas.append(f"El pago de {soles(mo)} del {fecha_corta(d)} queda fuera de esta proyección "
                             f"(llega hasta el {fecha_corta(esc.proy.fin)}): revisa tu caja antes de esa fecha.")  # fmt: skip
            continue
        esc.fechas_movidas.append(d)
        concepto = plantilla.concepto if len(fechas) == 1 else f"{plantilla.concepto} ({i}/{len(fechas)})"
        esc.eventos.append(replace(plantilla, fecha=d, monto=-mo, concepto=concepto))


def en_partes(esc: Escenario, deuda_id: str, partes: int, fechas: list[date] | None, vencimiento: date) -> None:
    total = esc.pendiente(deuda_id)
    if total <= 0:
        return
    fechas = list(fechas or [])
    if fechas and len(fechas) != partes:
        raise Validacion("Indica una fecha por cada parte.", [{"campo": "fechas", "problema": "no coincide con partes"}])
    fechas = fechas or [vencimiento + timedelta(days=DIAS_ENTRE_PARTES * i) for i in range(partes)]
    _reprogramar(esc, deuda_id, sorted(fechas), _repartir(total, partes))


def diferir(esc: Escenario, deuda_id: str, fecha: date) -> None:
    total = esc.pendiente(deuda_id)
    if total > 0:
        _reprogramar(esc, deuda_id, [fecha], [total])


def cobrar(esc: Escenario, montos: dict[str, tuple[str, Decimal]], fecha: date) -> None:
    fecha = max(fecha, esc.proy.corte + timedelta(days=1))
    if fecha > esc.proy.fin:
        esc.notas.append(f"El cobro del {fecha_corta(fecha)} queda fuera de esta proyección.")
        return
    for fid, (cliente, monto) in montos.items():
        esc.eventos.append(fc.Evento(fecha, f"Cobro del fiado de {cliente}", monto, "cobro_fiado", ref_id=fid))


def limitar_retiros(esc: Escenario, tope_semanal: Decimal) -> None:
    """Retiros fuera del sueldo fijo: como máximo `tope_semanal` por semana (0 = solo el sueldo)."""
    semanal = sum(esc.proy.media_ret.values(), CERO)
    if semanal <= tope_semanal or semanal <= 0:
        return
    factor = 1 - Decimal(tope_semanal) / semanal
    for wd, ret in esc.proy.media_ret.items():
        esc.menos_egreso[wd] = esc.menos_egreso.get(wd, CERO) + ret * factor


def ajustar_gasto(esc: Escenario, monto: Decimal, fecha: date) -> None:
    fecha = max(fecha, esc.proy.corte + timedelta(days=1))
    if fecha <= esc.proy.fin and monto:
        esc.eventos.append(fc.Evento(fecha, "Ajuste de gasto", -Decimal(monto), "ajuste_manual"))


def minimo_hasta(puntos: list[fc.Punto], hasta: date) -> fc.Punto:
    ventana = [p for p in puntos if p.fecha <= hasta] or puntos[:1]
    return min(ventana, key=lambda p: (p.p50, p.fecha))


# ── API ─────────────────────────────────────────────────────────────────────────────────────────


def _pedido_por_defecto(proy: fc.Proyeccion, critico) -> str | None:
    if critico is not None and critico.obligacion_asociada is not None:
        return critico.obligacion_asociada.id
    proveedor = [e for e in proy.eventos if e.deuda_id and e.proveedor]
    return proveedor[0].deuda_id if proveedor else None


def _deuda(proy: fc.Proyeccion, deuda_id: str | None):
    dc = next((d for d in proy.deudas if d.deuda.deuda_id == deuda_id and d.pendiente > 0), None)
    if dc is None:
        raise Validacion("No encontré ese pedido pendiente.", [{"campo": "pedido_id", "problema": "no existe o ya se pagó"}])
    return dc


def aplicar(esc: Escenario, acciones: list[Accion], critico) -> None:
    proy = esc.proy
    for accion in sorted(acciones, key=lambda a: ORDEN.index(TA(a.tipo))):
        tipo = TA(accion.tipo)
        if tipo in (TA.reducir_pedido, TA.pagar_en_partes, TA.diferir_pago):
            dc = _deuda(proy, accion.pedido_id or _pedido_por_defecto(proy, critico))
            did = dc.deuda.deuda_id
            if tipo == TA.reducir_pedido:
                if accion.nuevo_monto is None or accion.nuevo_monto < 0:
                    raise Validacion("Indica el nuevo monto del pedido.", [{"campo": "nuevo_monto", "problema": "obligatorio"}])
                reducir(esc, did, accion.nuevo_monto, dc.pagado)
            elif tipo == TA.pagar_en_partes:
                en_partes(esc, did, accion.partes or 2, accion.fechas, dc.deuda.fecha_vencimiento)
            else:
                destino = accion.fecha or (accion.fechas[0] if accion.fechas else None)
                destino = destino or dc.deuda.fecha_vencimiento + timedelta(days=DIAS_ENTRE_PARTES)
                diferir(esc, did, destino)
        elif tipo == TA.cobrar_fiados:
            pendientes = {f.fiado.fiado_id: (f.cliente, f.pendiente) for f in proy.fiados if f.pendiente > 0}
            ids = accion.fiado_ids or list(pendientes)
            desconocidos = [i for i in ids if i not in pendientes]
            if desconocidos:
                raise Validacion(f"No encontré el fiado pendiente {desconocidos[0]}.",
                                 [{"campo": "fiado_ids", "problema": f"{i} no existe o ya se pagó"} for i in desconocidos])  # fmt: skip
            cobrar(esc, {i: pendientes[i] for i in ids}, accion.fecha or proy.corte + timedelta(days=1))
        elif tipo == TA.limitar_retiros:
            limitar_retiros(esc, Decimal(accion.monto or 0))
        elif tipo == TA.ajustar_gasto:
            if accion.monto is None:
                raise Validacion("Indica el monto del ajuste de gasto.", [{"campo": "monto", "problema": "obligatorio"}])
            ajustar_gasto(esc, accion.monto, accion.fecha or proy.corte + timedelta(days=1))


def ventana(proy: fc.Proyeccion, critico, esc: Escenario | None = None) -> date:
    base = critico.fecha if critico is not None else proy.fin
    movidas = [d for d in (esc.fechas_movidas if esc else []) if d <= proy.fin]
    return max([base, *movidas])


def simular(db: Session, empresa_id: str, acciones: list[Accion], fecha_corte: date | None = None,
            horizonte_dias: int = 30) -> SimulacionResponse:  # fmt: skip
    proy = fc.proyectar(db, empresa_id, fecha_corte, horizonte_dias)
    base = Escenario(proy, list(proy.eventos))
    puntos_base = base.puntos()
    critico = fc.dia_critico(proy, puntos_base)
    esc = base.copia()
    aplicar(esc, acciones, critico)
    puntos = esc.puntos()
    fin_base, fin_con = ventana(proy, critico), ventana(proy, critico, esc)
    sin, con = minimo_hasta(puntos_base, fin_base), minimo_hasta(puntos, fin_con)
    limites = "Tú decides; nada se ejecuta solo. Pagar en partes o mover una fecha depende de que el proveedor acepte."
    if esc.notas:
        limites += " " + " ".join(dict.fromkeys(esc.notas))
    return SimulacionResponse(
        sin_acciones=ResultadoSaldo(saldo_minimo=sin.p50, fecha=sin.fecha, estado_caja=proy.estado_caja(sin.p50)),
        con_acciones=ResultadoSaldo(saldo_minimo=con.p50, fecha=con.fecha, estado_caja=proy.estado_caja(con.p50)),
        mejora=con.p50 - sin.p50,
        serie_con_acciones=[PuntoSimulado(fecha=p.fecha, p50=p.p50) for p in puntos],
        fundamento=(f"Simulación sobre tu proyección (ventas y gastos de las últimas 4 semanas y tus pagos con fecha): "
                    f"se compara el saldo más bajo hasta el {fecha_corta(fin_con)}."),
        limites=limites, confianza=fc.confianza(proy), ventana_hasta=fin_con, notas=list(dict.fromkeys(esc.notas)),
        meta=meta_b(MODELO, VERSION, fallback=True,
                    motivo="La serie base es el baseline naive estacional (el modelo LightGBM no es integrable)."),
    )  # fmt: skip
