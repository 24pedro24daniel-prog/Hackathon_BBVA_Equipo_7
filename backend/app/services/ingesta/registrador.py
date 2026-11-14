"""★ INTERFAZ A (PLAN_MVP.md §4.1): escribe la transacción y sus tablas satélite (A1).

Casos (diccionario_datos.md §4): venta, venta fiada → cuaderno_fiado, cobro de fiado, compra a crédito → deudas,
pago a proveedor, préstamo recibido, pago de cuota, retiro personal (sueldo → programado_id), gasto (recurrente →
programado_id), pago de impuesto → impuestos. Respeta los CHECK de `transacciones` antes de llegar a la BD:
`metodo_pago = credito ⇒ afecta_caja = false`, un solo vínculo, y cada tipo con el vínculo que le toca.
Nada se borra: `anular_movimiento` marca `anulada = true`.
"""

import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflicto, NoEncontrado, Validacion
from app.core.ids import nuevo_id
from app.core.reloj import a_lima, ahora
from app.db import models as m
from app.schemas.common import Canal, Frecuencia, MetodoPago, RegistroCreado, TipoDeuda, TipoMovimiento
from app.schemas.ingesta import MovimientoPropuesto, RegistroResultado
from app.services.ingesta import catalogo as cat_mod
from app.services.ingesta.reglas import tipo_deuda_por_acreedor
from app.services.ingesta.texto import normalizar, soles

T = TipoMovimiento
CERO = Decimal("0")

CATEGORIA_POR_TIPO = {
    T.venta: "otros ingresos", T.cobro_fiado: "cobro de fiados", T.prestamo_recibido: "prestamos recibidos",
    T.otro_ingreso: "otros ingresos", T.compra: "mercaderia", T.gasto_negocio: "otros gastos",
    T.retiro_personal: "retiro personal", T.pago_proveedor: "mercaderia", T.pago_prestamo: "pago de prestamos",
    T.pago_impuesto: "impuestos",
}  # fmt: skip
DIAS_POR_FRECUENCIA = {Frecuencia.diaria: 1, Frecuencia.semanal: 7, Frecuencia.quincenal: 15, Frecuencia.mensual: 30}
PLAZO_PROVEEDOR_NUEVO = 15


class _Registro:
    def __init__(self, db: Session, empresa: m.Empresa, mov: MovimientoPropuesto, canal: Canal,
                 borrador_id: str | None, confianza: Decimal | None, fue_corregida: bool):  # fmt: skip
        self.db, self.empresa, self.mov = db, empresa, mov
        self.canal, self.borrador_id, self.confianza, self.fue_corregida = canal, borrador_id, confianza, fue_corregida
        self.tipo = T(mov.tipo)
        self.metodo = MetodoPago(mov.metodo_pago or MetodoPago.efectivo)
        self.fecha_hora = a_lima(mov.fecha_hora) if mov.fecha_hora else ahora().replace(microsecond=0)
        self.dia = self.fecha_hora.date()
        self.creados: list[RegistroCreado] = []
        self._cat: cat_mod.Catalogo | None = None

    @property
    def catalogo(self) -> cat_mod.Catalogo:
        if self._cat is None:
            self._cat = cat_mod.cargar(self.db, self.empresa.empresa_id)
        return self._cat

    def _crear(self, obj, tabla: str, id_: str):
        self.db.add(obj)
        self.db.flush()
        self.creados.append(RegistroCreado(tabla=tabla, id=id_))
        return obj

    # ── categoría ──
    def categoria_id(self) -> str:
        nombre = self.mov.categoria
        if not nombre and self.mov.items:
            prod = self.db.get(m.Producto, self.mov.items[0].producto_id) if self.mov.items[0].producto_id else None
            if prod:
                return prod.categoria_id
        nombre = nombre or CATEGORIA_POR_TIPO[self.tipo]
        clave = nombre.replace("_", " ")
        cat = self.db.scalars(select(m.Categoria).where(
            (m.Categoria.categoria_id == nombre) | (func.lower(m.Categoria.nombre) == clave.lower()))).first()  # fmt: skip
        if cat is None:
            cat = self.db.scalars(select(m.Categoria).where(m.Categoria.nombre == CATEGORIA_POR_TIPO[self.tipo])).first()
        if cat is None:
            raise Validacion(f"No existe la categoría '{nombre}'.", [{"campo": "categoria", "problema": "no existe"}])
        return cat.categoria_id

    # ── clientes y proveedores ──
    def cliente(self) -> m.Cliente:
        nombre = (self.mov.contraparte or "").strip()
        if not nombre:
            raise Validacion("¿A quién le fiaste? Falta el nombre del cliente.",
                             [{"campo": "contraparte", "problema": "obligatorio en una venta fiada"}])  # fmt: skip
        if encontrado := self.catalogo.buscar_cliente(nombre):
            return self.db.get(m.Cliente, encontrado.cliente_id)
        nuevo = m.Cliente(cliente_id=nuevo_id(self.db, m.Cliente, "CLI"), empresa_id=self.empresa.empresa_id,
                          nombre_ficticio=nombre[:100], alias=[normalizar(nombre)], creado_en=ahora())  # fmt: skip
        return self._crear(nuevo, "clientes", nuevo.cliente_id)

    def proveedor(self, crear: bool) -> m.Proveedor | None:
        nombre = (self.mov.contraparte or "").strip()
        if not nombre:
            if crear:
                raise Validacion("¿A qué proveedor? Falta el nombre del proveedor.",
                                 [{"campo": "contraparte", "problema": "obligatorio en un pedido a crédito"}])  # fmt: skip
            return None
        if encontrado := self.catalogo.buscar_proveedor(nombre):
            return self.db.get(m.Proveedor, encontrado.proveedor_id)
        if not crear:
            return None
        nuevo = m.Proveedor(proveedor_id=nuevo_id(self.db, m.Proveedor, "PRV"), empresa_id=self.empresa.empresa_id,
                            nombre_ficticio=nombre[:100], plazo_pago_dias=PLAZO_PROVEEDOR_NUEVO)  # fmt: skip
        return self._crear(nuevo, "proveedores", nuevo.proveedor_id)

    # ── cuentas por cobrar / pagar ──
    def _pendiente_fiado(self, fiado: m.CuadernoFiado) -> Decimal:
        cobrado = self.db.scalar(select(func.coalesce(func.sum(m.Transaccion.monto), 0)).where(
            m.Transaccion.fiado_id == fiado.fiado_id, m.Transaccion.tipo == T.cobro_fiado, ~m.Transaccion.anulada))  # fmt: skip
        return fiado.monto - Decimal(cobrado)

    def _pendiente_deuda(self, deuda: m.Deuda) -> Decimal:
        pagado = self.db.scalar(select(func.coalesce(func.sum(m.Transaccion.monto), 0)).where(
            m.Transaccion.deuda_id == deuda.deuda_id, ~m.Transaccion.anulada,
            m.Transaccion.tipo.in_([T.pago_proveedor, T.pago_prestamo])))  # fmt: skip
        return deuda.monto_total_a_pagar - Decimal(pagado)

    def fiados_a_cobrar(self) -> list[tuple[m.CuadernoFiado, Decimal]]:
        """Reparte el cobro entre los fiados pendientes del cliente, del más antiguo al más nuevo."""
        monto = self.mov.monto
        if self.mov.fiado_id:
            fiado = self.db.get(m.CuadernoFiado, self.mov.fiado_id)
            if fiado is None or fiado.empresa_id != self.empresa.empresa_id:
                raise NoEncontrado("No encontré ese fiado.")
            candidatos = [fiado]
        else:
            nombre = self.mov.contraparte
            cli = self.catalogo.buscar_cliente(nombre) if nombre else None
            if cli is None:
                raise Validacion("¿Quién te pagó? No encontré a ese cliente en tus fiados.",
                                 [{"campo": "contraparte", "problema": "cliente sin fiados"}])  # fmt: skip
            candidatos = self.db.scalars(select(m.CuadernoFiado).where(
                m.CuadernoFiado.empresa_id == self.empresa.empresa_id, m.CuadernoFiado.cliente_id == cli.cliente_id,
                m.CuadernoFiado.fecha_pago_total.is_(None)).order_by(m.CuadernoFiado.fecha_fiado,
                                                                     m.CuadernoFiado.fiado_id)).all()  # fmt: skip
        pendientes = [(f, self._pendiente_fiado(f)) for f in candidatos]
        pendientes = [(f, p) for f, p in pendientes if p > 0]
        total = sum((p for _, p in pendientes), CERO)
        if not pendientes:
            raise Validacion("Ese cliente no tiene fiados pendientes.", [{"campo": "contraparte", "problema": "sin deuda"}])
        if monto > total:
            raise Validacion(f"Solo te debe {soles(total, True)}. Revisa el monto.",
                             [{"campo": "monto", "problema": f"mayor que lo pendiente ({total})"}])  # fmt: skip
        partes, resto = [], monto
        for fiado, pend in pendientes:
            if resto <= 0:
                break
            importe = min(pend, resto)
            partes.append((fiado, importe))
            resto -= importe
            if importe == pend:
                fiado.fecha_pago_total = self.dia
                if fiado.fecha_compromiso:
                    fiado.pago_tardio = self.dia > fiado.fecha_compromiso
        return partes

    def deuda_a_pagar(self, de_proveedor: bool) -> m.Deuda:
        if self.mov.deuda_id:
            deuda = self.db.get(m.Deuda, self.mov.deuda_id)
            if deuda is None or deuda.empresa_id != self.empresa.empresa_id:
                raise NoEncontrado("No encontré esa deuda.")
        else:
            q = select(m.Deuda).where(m.Deuda.empresa_id == self.empresa.empresa_id, m.Deuda.fecha_pago_total.is_(None))
            if de_proveedor:
                prov = self.proveedor(crear=False)
                if prov is None:
                    raise Validacion("¿A qué proveedor le pagaste? No lo encontré.",
                                     [{"campo": "contraparte", "problema": "proveedor desconocido"}])  # fmt: skip
                q = q.where(m.Deuda.tipo == TipoDeuda.proveedor, m.Deuda.proveedor_id == prov.proveedor_id)
            else:
                q = q.where(m.Deuda.tipo != TipoDeuda.proveedor)
            candidatas = self.db.scalars(q.order_by(m.Deuda.fecha_vencimiento, m.Deuda.deuda_id)).all()
            if not de_proveedor and self.mov.contraparte and len(candidatas) > 1:
                clave = normalizar(self.mov.contraparte)
                por_nombre = [d for d in candidatas if d.acreedor_nombre and clave in normalizar(d.acreedor_nombre)]
                candidatas = por_nombre or candidatas
            if not candidatas:
                raise Validacion("No encontré una deuda pendiente para ese pago.",
                                 [{"campo": "deuda_id", "problema": "sin deuda pendiente"}])  # fmt: skip
            deuda = candidatas[0]
        pendiente = self._pendiente_deuda(deuda)
        if self.mov.monto > pendiente:
            raise Validacion(f"De esa deuda solo queda {soles(pendiente, True)}. Revisa el monto.",
                             [{"campo": "monto", "problema": f"mayor que lo pendiente ({pendiente})"}])  # fmt: skip
        if self.mov.monto == pendiente:
            deuda.fecha_pago_total = self.dia
        return deuda

    def crear_fiado(self) -> m.CuadernoFiado:
        cliente = self.cliente()
        detalle = ", ".join(f"{i.cantidad.normalize():f} {i.producto}" for i in self.mov.items if i.producto)
        detalle = (detalle or self.mov.descripcion or "")[:255] or None
        fiado = m.CuadernoFiado(fiado_id=nuevo_id(self.db, m.CuadernoFiado, "FIA"), empresa_id=self.empresa.empresa_id,
                                cliente_id=cliente.cliente_id, borrador_id=self.borrador_id, detalle=detalle,
                                monto=self.mov.monto, fecha_fiado=self.dia, fecha_compromiso=self.mov.fecha_vencimiento,
                                canal=self.canal)  # fmt: skip
        return self._crear(fiado, "cuaderno_fiado", fiado.fiado_id)

    def crear_pedido(self) -> m.Deuda:
        prov = self.proveedor(crear=True)
        vence = self.mov.fecha_vencimiento or self.dia + timedelta(days=prov.plazo_pago_dias)
        if vence < self.dia:
            raise Validacion("La fecha de pago no puede ser anterior al pedido.",
                             [{"campo": "fecha_vencimiento", "problema": "anterior a la fecha del pedido"}])  # fmt: skip
        total = self.mov.monto_total_a_pagar or self.mov.monto
        deuda = m.Deuda(deuda_id=nuevo_id(self.db, m.Deuda, "PED"), empresa_id=self.empresa.empresa_id,
                        tipo=TipoDeuda.proveedor, proveedor_id=prov.proveedor_id, borrador_id=self.borrador_id,
                        monto_recibido=self.mov.monto, monto_total_a_pagar=total, fecha_inicio=self.dia,
                        fecha_vencimiento=vence, canal=self.canal,
                        notas=(self.mov.descripcion or "Pedido a crédito")[:255])  # fmt: skip
        return self._crear(deuda, "deudas", deuda.deuda_id)

    def crear_prestamo(self) -> m.Deuda:
        total = self.mov.monto_total_a_pagar or self.mov.monto
        if total < self.mov.monto:
            raise Validacion("Lo que devuelves no puede ser menor que lo que recibiste.",
                             [{"campo": "monto_total_a_pagar", "problema": "menor que el monto"}])  # fmt: skip
        frecuencia = Frecuencia(self.mov.frecuencia_cuota) if self.mov.frecuencia_cuota else None
        vence = self.mov.fecha_vencimiento
        if vence is None:
            if frecuencia and self.mov.monto_cuota:
                n = math.ceil(total / self.mov.monto_cuota)
                vence = self.dia + timedelta(days=n * DIAS_POR_FRECUENCIA[frecuencia])
            else:
                vence = self.dia + timedelta(days=30)
        notas = None if self.mov.monto_total_a_pagar else "Total a devolver no informado: se asumió igual a lo recibido"
        acreedor = self.mov.contraparte or "Prestamista"
        deuda = m.Deuda(deuda_id=nuevo_id(self.db, m.Deuda, "DEU"), empresa_id=self.empresa.empresa_id,
                        tipo=TipoDeuda(tipo_deuda_por_acreedor(acreedor)), acreedor_nombre=acreedor[:100],
                        borrador_id=self.borrador_id, monto_recibido=self.mov.monto, monto_total_a_pagar=total,
                        frecuencia_cuota=frecuencia, monto_cuota=self.mov.monto_cuota, fecha_inicio=self.dia,
                        fecha_vencimiento=max(vence, self.dia), canal=self.canal, notas=notas)  # fmt: skip
        return self._crear(deuda, "deudas", deuda.deuda_id)

    def impuesto(self) -> m.Impuesto:
        emp = self.empresa.empresa_id
        if self.mov.impuesto_id:
            imp = self.db.get(m.Impuesto, self.mov.impuesto_id)
            if imp is None or imp.empresa_id != emp:
                raise NoEncontrado("No encontré ese impuesto.")
        else:
            imp = self.db.scalars(select(m.Impuesto).where(m.Impuesto.empresa_id == emp, m.Impuesto.fecha_pago.is_(None))
                                  .order_by(m.Impuesto.periodo)).first()  # fmt: skip
            if imp is None:
                periodo = self.dia.strftime("%Y-%m")
                if self.db.scalars(select(m.Impuesto).where(m.Impuesto.empresa_id == emp,
                                                            m.Impuesto.periodo == periodo)).first():  # fmt: skip
                    raise Conflicto("El impuesto de este mes ya figura como pagado.")
                imp_id = nuevo_id(self.db, m.Impuesto, "IMP")
                imp = self._crear(m.Impuesto(impuesto_id=imp_id, empresa_id=emp,
                                             regimen=self.empresa.regimen_tributario or "nuevo_rus", periodo=periodo,
                                             monto=self.mov.monto, fecha_vencimiento=vencimiento_impuesto(periodo),
                                             canal=self.canal), "impuestos", imp_id)  # fmt: skip
        pagado = self.db.scalar(select(m.Transaccion.transaccion_id).where(m.Transaccion.impuesto_id == imp.impuesto_id))
        if imp.fecha_pago is not None or pagado:
            raise Conflicto(f"El impuesto de {imp.periodo} ya figura como pagado.")
        imp.fecha_pago = self.dia
        return imp

    # ── recurrentes ──
    def _ya_vinculado(self, programado_id: str, desde: date, hasta: date) -> bool:
        return bool(self.db.scalar(select(func.count()).select_from(m.Transaccion).where(
            m.Transaccion.programado_id == programado_id, ~m.Transaccion.anulada,
            m.Transaccion.fecha_hora >= _inicio(desde), m.Transaccion.fecha_hora < _inicio(hasta + timedelta(days=1)))))  # fmt: skip

    def programado(self) -> str | None:
        vigentes = self.db.scalars(select(m.MovimientoProgramado).where(
            m.MovimientoProgramado.empresa_id == self.empresa.empresa_id, m.MovimientoProgramado.activo,
            m.MovimientoProgramado.fecha_inicio <= self.dia,
            (m.MovimientoProgramado.fecha_fin.is_(None)) | (m.MovimientoProgramado.fecha_fin >= self.dia))).all()  # fmt: skip
        if self.tipo == T.retiro_personal:
            sueldo = next((p for p in vigentes if p.es_sueldo), None)
            if sueldo and sueldo.monto == self.mov.monto:
                lunes = self.dia - timedelta(days=self.dia.weekday())
                if not self._ya_vinculado(sueldo.programado_id, lunes, lunes + timedelta(days=6)):
                    return sueldo.programado_id
            return None
        texto = normalizar(self.mov.descripcion or "")
        for p in vigentes:
            if p.es_sueldo:
                continue
            claves = {w for w in normalizar(p.descripcion).split() if len(w) >= 3 and w not in ("del", "las", "los")}
            if claves and any(re.search(rf"\b{re.escape(w)}\b", texto) for w in claves):
                inicio_mes = self.dia.replace(day=1)
                if not self._ya_vinculado(p.programado_id, inicio_mes, self.dia):
                    return p.programado_id
        return None

    # ── transacciones ──
    def transaccion(self, monto: Decimal, categoria_id: str, con_detalle: bool, **vinculo) -> m.Transaccion:
        afecta_caja = self.metodo != MetodoPago.credito
        tx = m.Transaccion(transaccion_id=nuevo_id(self.db, m.Transaccion, "MOV"), empresa_id=self.empresa.empresa_id,
                           borrador_id=self.borrador_id, fecha_hora=self.fecha_hora, tipo=self.tipo,
                           categoria_id=categoria_id,
                           descripcion=(self.mov.descripcion or "")[:255] or None, monto=monto, moneda="PEN",
                           metodo_pago=self.metodo, afecta_caja=afecta_caja, canal=self.canal,
                           confianza_extraccion=self.confianza if self.canal != Canal.manual else None,
                           fue_corregida=self.fue_corregida, creado_en=ahora(), **vinculo)  # fmt: skip
        self._crear(tx, "transacciones", tx.transaccion_id)
        if con_detalle:
            for item in self.mov.items:
                prod = self.db.get(m.Producto, item.producto_id) if item.producto_id else None
                if prod is not None and prod.empresa_id != self.empresa.empresa_id:
                    prod = None
                self.db.add(m.DetalleTransaccion(
                    detalle_id=nuevo_id(self.db, m.DetalleTransaccion, "DET"), transaccion_id=tx.transaccion_id,
                    producto_id=prod.producto_id if prod else None,
                    descripcion=None if prod else (item.producto or "sin nombre")[:100], cantidad=item.cantidad,
                    precio_unitario=item.precio_unitario, costo_unitario=prod.costo_unitario if prod else None,
                    subtotal=item.subtotal))  # fmt: skip
            self.db.flush()
        return tx

    def ejecutar(self) -> RegistroResultado:
        if self.metodo == MetodoPago.credito and self.tipo not in (T.venta, T.compra):
            raise Validacion("Solo una venta (fiado) o una compra (pedido) pueden ser a crédito.",
                             [{"campo": "metodo_pago", "problema": f"credito no aplica a {self.tipo.value}"}])  # fmt: skip
        categoria = self.categoria_id()
        credito = self.metodo == MetodoPago.credito
        detalle = self.tipo in (T.venta, T.compra)
        if self.tipo == T.venta and credito:
            self.transaccion(self.mov.monto, categoria, detalle, fiado_id=self.crear_fiado().fiado_id)
            self._mover_primero("transacciones")
        elif self.tipo == T.cobro_fiado:
            for fiado, importe in self.fiados_a_cobrar():
                self.transaccion(importe, categoria, False, fiado_id=fiado.fiado_id)
        elif self.tipo == T.compra and credito:
            self.transaccion(self.mov.monto, categoria, detalle, deuda_id=self.crear_pedido().deuda_id)
            self._mover_primero("transacciones")
        elif self.tipo == T.prestamo_recibido:
            self.transaccion(self.mov.monto, categoria, False, deuda_id=self.crear_prestamo().deuda_id)
            self._mover_primero("transacciones")
        elif self.tipo in (T.pago_proveedor, T.pago_prestamo):
            deuda = self.deuda_a_pagar(de_proveedor=self.tipo == T.pago_proveedor)
            self.transaccion(self.mov.monto, categoria, False, deuda_id=deuda.deuda_id)
        elif self.tipo == T.pago_impuesto:
            self.transaccion(self.mov.monto, categoria, False, impuesto_id=self.impuesto().impuesto_id)
            self._mover_primero("transacciones")
        elif self.tipo in (T.retiro_personal, T.gasto_negocio):
            self.transaccion(self.mov.monto, categoria, False, programado_id=self.programado())
        else:
            self.transaccion(self.mov.monto, categoria, detalle)
        movimiento_id = next(r.id for r in self.creados if r.tabla == "transacciones")
        return RegistroResultado(movimiento_id=movimiento_id, registros_creados=self.creados)

    def _mover_primero(self, tabla: str) -> None:
        """registros_creados empieza por la transacción (como en el contrato) y luego las satélite."""
        self.creados.sort(key=lambda r: r.tabla != tabla)


def _inicio(d: date) -> datetime:
    from app.core.reloj import inicio_del_dia

    return inicio_del_dia(d)


def vencimiento_impuesto(periodo: str) -> date:
    """Nuevo RUS (simplificado): vence el día 15 del mes siguiente al periodo."""
    anio, mes = map(int, periodo.split("-"))
    return date(anio + mes // 12, mes % 12 + 1, 15)


def registrar_movimiento(
    db: Session,
    empresa_id: str,
    mov: MovimientoPropuesto,
    *,
    canal: Canal,
    borrador_id: str | None = None,
    confianza: Decimal | None = None,
    fue_corregida: bool = False,
    commit: bool = True,
) -> RegistroResultado:
    """Crea la transacción, su detalle y la fila satélite que corresponda
    (cuaderno_fiado / deudas / impuestos) según diccionario §4. Hace commit (salvo `commit=False`).
    RegistroResultado = {movimiento_id, registros_creados: [{tabla, id}]}"""
    empresa = db.get(m.Empresa, empresa_id)
    if empresa is None:
        raise NoEncontrado("No encontré esa empresa.")
    if not isinstance(mov, MovimientoPropuesto):
        mov = MovimientoPropuesto.model_validate(mov)
    confianza = Decimal(str(confianza)).quantize(Decimal("0.001")) if confianza is not None else None
    try:
        resultado = _Registro(db, empresa, mov, Canal(canal), borrador_id, confianza, fue_corregida).ejecutar()
        if commit:
            db.commit()
        else:
            db.flush()
        return resultado
    except Exception:
        db.rollback()
        raise


def anular_movimiento(db: Session, empresa_id: str, movimiento_id: str) -> m.Transaccion:
    """Nada se borra: marca la transacción como anulada (y reabre el fiado o la deuda si ese pago los cerraba)."""
    tx = db.get(m.Transaccion, movimiento_id)
    if tx is None or tx.empresa_id != empresa_id:
        raise NoEncontrado("No encontré ese movimiento.")
    if tx.anulada:
        raise Conflicto("Ese movimiento ya estaba anulado.")
    tx.anulada = True
    if tx.tipo == T.cobro_fiado and tx.fiado_id:
        fiado = db.get(m.CuadernoFiado, tx.fiado_id)
        fiado.fecha_pago_total, fiado.pago_tardio = None, None
    if tx.tipo in (T.pago_proveedor, T.pago_prestamo) and tx.deuda_id:
        db.get(m.Deuda, tx.deuda_id).fecha_pago_total = None
    if tx.tipo == T.pago_impuesto and tx.impuesto_id:
        db.get(m.Impuesto, tx.impuesto_id).fecha_pago = None
    db.commit()
    return tx
