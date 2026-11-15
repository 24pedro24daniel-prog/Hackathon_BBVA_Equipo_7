"""Extractor por reglas/regex (fallback del LLM, A3). Funciona sin red y sin BD: solo texto + `Catalogo`.

Devuelve un `Crudo`: lo que se entendió de la frase, sin completar ni validar. extractor.py lo normaliza igual
que la salida del LLM (monto por catálogo, campos faltantes, confianza y pregunta aclaratoria).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.schemas.common import Frecuencia, MetodoPago, TipoMovimiento
from app.services.ingesta.catalogo import Catalogo, ClienteCat, ProductoCat, ProveedorCat
from app.services.ingesta.texto import Numero, ResultadoFecha, normalizar, numeros, parsear_fecha

T = TipoMovimiento


@dataclass
class ItemCrudo:
    producto: ProductoCat | None
    cantidad: Decimal = Decimal(1)
    nombre: str | None = None
    precio_dicho: Decimal | None = None


@dataclass
class Crudo:
    tipo: TipoMovimiento | None = None
    items: list[ItemCrudo] = field(default_factory=list)
    monto: Decimal | None = None
    metodo_pago: MetodoPago | None = None
    contraparte: str | None = None
    cliente: ClienteCat | None = None
    proveedor: ProveedorCat | None = None
    fecha: ResultadoFecha = field(default_factory=ResultadoFecha)
    monto_total_a_pagar: Decimal | None = None
    frecuencia_cuota: Frecuencia | None = None
    monto_cuota: Decimal | None = None
    categoria: str | None = None
    descripcion: str | None = None
    fuera_de_alcance: bool = False
    dias_atras: int = 0
    confianza: float = 0.0
    # Cifras de dinero dichas (sin fechas, cantidades ni precios unitarios), en orden de preferencia. El extractor
    # con LLM las usa para validar o corregir el monto que propone el modelo.
    montos_dichos: list[Decimal] = field(default_factory=list)


# ── patrones ────────────────────────────────────────────────────────────────────────────────────

_HOGAR = re.compile(
    r"\b(colegio|escuela|universidad|pension(es)?|matricula|uniformes?|utiles|mis? hij[oa]s?|mi esposa|mi esposo|"
    r"doctor|medico|farmacia|medicinas?|pastillas|clinica|dentista|cumpleanos|"
    r"(luz|agua|alquiler|cable|internet|gas) de (la|mi) casa|mercado de la casa|para mi mama|para mi papa)\b"
)
_RETIRO = re.compile(r"\b(saque|retire|agarre|cogi|tome|me lleve|me servi|separe)\b|\bde la caja\b|\bde la tienda\b|"
                     r"\bdel negocio\b|\bpara la casa\b|\bpara (mi|la) familia\b|\bpara los gastos de (la )?casa\b|"
                     r"\b(mi|el) sueldo\b")  # fmt: skip
_PRESTAMO = re.compile(r"\bme (prestaron|presto|han prestado|dieron un prestamo)\b|\b(saque|pedi|recibi|tome|agarre|"
                       r"consegui) (un |el )?prestamo\b|\bprestamo de\b|\bgota a gota\b.*\b(me dio|me dieron|recibi)\b")  # fmt: skip
_PAGO_PRESTAMO = re.compile(r"\b(pague|di|abone|cancele|deposite|pago)\b.*\b(cuotas?|prestamo|prestamista|gota a gota)\b|"
                            r"\bcuota del\b")  # fmt: skip
_IMPUESTO = re.compile(r"\b(rus|nuevo rus|sunat|impuestos?|tributos?|igv)\b")
_ME_FIARON = re.compile(r"\bme (fiaron|fio|dieron a credito|dejaron a credito|dejaron mercaderia)\b")
_COBRO_FUERTE = re.compile(r"\bme (pago|pagaron|cancelo|abono|devolvio|yapeo|plineo|dio lo que (me )?debia)\b|"
                           r"\b(pago|cancelo|abono) (su|el|lo que) (fiado|debia|me debia)\b|\bya (me )?pago\b|"
                           r"\bcobre (el |su )?fiado\b")  # fmt: skip
_COBRO_DEBIL = re.compile(r"\b(pago|pagaron|cancelo|abono|cobre|devolvio)\b")
_FIADO = re.compile(r"\b(le )?fie\b|\bfiado\b|\bfiao\b|\ba cuenta\b|\bquedo debiendo\b|\bme debe\b|"
                    r"\bapunte\b|\banote en el cuaderno\b|\bse llevo\b|\bvend\w*\b.*\ba credito\b")  # fmt: skip
_PEDIDO = re.compile(r"\bpedi\b|\bhice (un |el )?pedido\b|\bencargue\b|\bpedido (a|de|para)\b|\ba credito\b|\ba plazo\b")
_PAGO_PROVEEDOR = re.compile(r"\b(le )?(pague|cancele|abone|deposite|pago)\b")
_VENTA = re.compile(r"\b(vendi|vendimos|vendio|vendieron|vendo|se vendio|se vendieron|me compro|me compraron|"
                    r"salieron|salio|cobre|despache|venta|ventas|hice)\b")  # fmt: skip
_YAPE_INGRESO = re.compile(r"\bme (yapearon|yapeo|plinearon|plineo|depositaron|transfirieron)\b")
_COMPRA = re.compile(r"\b(compre|compramos|repuse|surti|abasteci|me trajeron|traje|fui al mercado|compra de)\b")
_OTRO_INGRESO = re.compile(r"\b(me dieron|recibi|gane|me regalaron|propina|entro|entraron)\b")
_GASTO_VERBO = re.compile(r"\b(pague|gaste|pagamos|pago)\b")

# (patrón, categoría)
_GASTOS = [
    (re.compile(r"\b(luz|agua|internet|telefono|cable|recibo|celular|recarga)\b"), "servicios"),
    (re.compile(r"\b(mototaxi|taxi|flete|pasaje|pasajes|movilidad|combi|carrera|delivery)\b"), "transporte_flete"),
    (re.compile(r"\b(alquiler|local|renta del local)\b"), "alquiler_local"),
    (re.compile(r"\b(gas|balon|bolsas|descartables|focos?|escoba|reparacion|arreglo|pintura|municipalidad|"
                r"licencia|limpieza|tecnico|candado|vitrina|congeladora|refrigeradora)\b"), "otros_gastos"),
]  # fmt: skip

_METODOS = [
    (re.compile(r"\b(yape|yapeo|yapearon|yapee|plin|plineo|plinearon|billetera|celular|digital|qr)\b"),
     MetodoPago.billetera_digital),
    (re.compile(r"\b(transferencia|transfirio|transferi|transfirieron|deposito|depositaron|deposite)\b"),
     MetodoPago.transferencia),
    (re.compile(r"\b(tarjeta|pos|visa|mastercard)\b"), MetodoPago.tarjeta),
    (re.compile(r"\b(efectivo|en mano|cash|sencillo|billete)\b"), MetodoPago.efectivo),
]  # fmt: skip

_FRECUENCIAS = [
    (r"diari[oa]s?|al dia|cada dia|por dia", Frecuencia.diaria),
    (r"semanal(es)?|a la semana|por semana|cada semana", Frecuencia.semanal),
    (r"quincenal(es)?|cada quincena|a la quincena", Frecuencia.quincenal),
    (r"mensual(es)?|al mes|cada mes|por mes", Frecuencia.mensual),
]
_RE_CUOTA = re.compile(r"^\s*(?:soles\s+|lucas\s+)?(" + "|".join(p for p, _ in _FRECUENCIAS) + r")\b")
_RE_TOTAL_PRESTAMO = re.compile(r"(?:devolver|devuelvo|devolvere|tengo que (?:pagar|devolver)|pagar en total|"
                                r"en total|total de|me cobra|me cobran|pagare)\s+(?:s/\s*)?$")  # fmt: skip
_RE_CANTIDAD = re.compile(r"^\s*(?:(?:kilos?|kg|bolsas?|paquetes?|botellas?|latas?|tarros?|unidades?|cajas?|sobres?|"
                          r"litros?|packs?|six|sixpack)\s+(?:de\s+)?)?$")  # fmt: skip
_RE_PRECIO_UNIT = re.compile(r"^\s*(?:a|de a|a s/|de a s/)\s*(?:s/\s*)?$")
_RE_MONEDA_DESPUES = re.compile(r"^\s*(soles|sol|lucas|luca|s/|nuevos soles)\b")

_NO_NOMBRES = {"la", "el", "los", "las", "un", "una", "mi", "su", "sus", "de", "del", "por", "para", "que", "me", "le",
               "se", "en", "con", "casa", "caja", "todo", "plata", "soles", "sol", "lucas", "credito", "cuenta",
               "senora", "senor", "sra", "sr", "don", "dona", "vecina", "vecino", "tia", "tio", "pedido", "fiado",
               "deuda", "y", "a", "al", "ya", "hoy", "ayer", "lo", "les", "nos", "pagar", "pago", "pague", "dia",
               "distribuidora", "proveedor", "mercado", "tienda", "bodega", "medio", "media", "otro", "otra",
               "cliente", "vecinos", "semana", "mes", "fin", "quincena", "manana", "tarde", "noche"}  # fmt: skip


def _metodo(t: str) -> MetodoPago | None:
    for patron, metodo in _METODOS:
        if patron.search(t):
            return metodo
    return None


def _capturar_nombre(t: str, patron: str, cat: Catalogo) -> str | None:
    if not (m := re.search(patron, t)):
        return None
    nombre = m.group(1)
    if nombre in _NO_NOMBRES or nombre.isdigit() or cat.buscar_producto(nombre):
        return None
    if numeros(nombre):
        return None
    return nombre.title()


def _contraparte_cliente(t: str, cat: Catalogo) -> tuple[ClienteCat | None, str | None]:
    if cliente := cat.buscar_cliente(t):
        return cliente, cliente.nombre
    tratamiento = r"(?:(?:la|el)\s+)?(?:(?:senora|senor|sra|sr|don|dona|vecina|vecino|tia|tio|joven|nina|nino)\s+)?"
    for patron in (rf"\b(?:fie|fiado|fiao|a cuenta|debiendo|apunte|llevo)\b.*?\ba\s+{tratamiento}([a-z]+)",
                   rf"\ble fie\s+(?:\S+\s+)*?a\s+{tratamiento}([a-z]+)",
                   rf"\bme (?:pago|pagaron|cancelo|abono|devolvio|yapeo)\s+{tratamiento}([a-z]+)",
                   rf"^{tratamiento}([a-z]+)\s+(?:ya\s+)?(?:me\s+)?(?:pago|cancelo|abono|devolvio|quedo)\b",
                   rf"\bcobre\s+(?:\S+\s+)*?a\s+{tratamiento}([a-z]+)",
                   rf"\b(?:fiado|deuda|cuenta) de\s+{tratamiento}([a-z]+)"):  # fmt: skip
        if nombre := _capturar_nombre(t, patron, cat):
            return None, nombre
    return None, None


def _contraparte_proveedor(t: str, cat: Catalogo) -> tuple[ProveedorCat | None, str | None]:
    if prov := cat.buscar_proveedor(t):
        return prov, prov.nombre
    for patron in (r"\b(?:pedi|pedido|encargue|pague|cancele|abone|compre|deposite|fiaron|dejaron)\b.*?\b(?:a|al|de|del)\s+"
                   r"(?:(?:la|el)\s+)?(?:(?:distribuidora|proveedor|senor|don)\s+)?([a-z]+)",):  # fmt: skip
        if nombre := _capturar_nombre(t, patron, cat):
            return None, nombre
    return None, None


def _contraparte_prestamo(t: str) -> str | None:
    if re.search(r"\b(gota a gota|prestamista)\b", t):
        return "Prestamista (gota a gota)"
    if m := re.search(r"\b(?:mi|el|la)\s+(hermano|hermana|mama|papa|tio|tia|primo|prima|cunado|cunada|suegra|suegro|"
                      r"compadre|comadre|amigo|amiga|vecino|vecina)\b", t):  # fmt: skip
        return f"Mi {m.group(1)}"
    if m := re.search(r"\b(caja|banco|financiera|cooperativa|mibanco|bcp|interbank|bbva)\b", t):
        return m.group(1).title()
    return None


def tipo_deuda_por_acreedor(acreedor: str | None) -> str:
    a = normalizar(acreedor or "")
    if re.search(r"\b(hermano|hermana|mama|papa|tio|tia|primo|prima|cunado|cunada|suegra|suegro)\b", a):
        return "familiar"
    if re.search(r"\b(caja|banco|financiera|cooperativa|mibanco|bcp|interbank|bbva)\b", a):
        return "entidad_financiera"
    return "prestamo_informal"


def _clasificar(t: str, hay_productos: bool, cliente: ClienteCat | None,
                proveedor: ProveedorCat | None) -> tuple[TipoMovimiento | None, float, bool]:  # fmt: skip
    """(tipo, confianza base, fuera_de_alcance)."""
    if _PRESTAMO.search(t):
        return T.prestamo_recibido, 0.9, False
    if _PAGO_PRESTAMO.search(t) and not _IMPUESTO.search(t):
        return T.pago_prestamo, 0.88, False
    if _HOGAR.search(t):
        if _RETIRO.search(t):
            return T.retiro_personal, 0.85, False
        return T.retiro_personal, 0.55, True
    if _IMPUESTO.search(t):
        return T.pago_impuesto, 0.92, False
    if _ME_FIARON.search(t):
        return T.compra, 0.88, False
    if _COBRO_FUERTE.search(t) and not (re.search(r"\bvend", t) and not re.search(r"\bfiado\b", t)):
        return T.cobro_fiado, 0.92, False
    if _FIADO.search(t):
        return T.venta, 0.92, False
    if cliente and _COBRO_DEBIL.search(t) and not _PEDIDO.search(t):
        return T.cobro_fiado, 0.85, False
    if re.search(r"\bcobre\b", t) and re.search(r"\b(fiado|debia|debe|deuda)\b", t):
        return T.cobro_fiado, 0.85, False
    pago_de_pedido = re.search(r"\b(pague|cancele|abone)\b", t) and re.search(r"\b(el|mi|su) pedido\b", t)
    if _PEDIDO.search(t) and not re.search(r"\bvend", t) and not pago_de_pedido:
        return T.compra, 0.9, False
    if _PAGO_PROVEEDOR.search(t) and (proveedor or re.search(r"\b(proveedor|distribuidora|el pedido|la deuda)\b", t)):
        return T.pago_proveedor, 0.88, False
    if re.search(r"\b(saque|retire|agarre|cogi|tome|me lleve)\b", t) and re.search(r"\bpara (pagar|comprar)\b", t):
        if any(p.search(t) for p, _ in _GASTOS):
            return T.gasto_negocio, 0.8, False
    if _RETIRO.search(t):
        return T.retiro_personal, 0.92, False
    if _YAPE_INGRESO.search(t):
        return T.venta, 0.75, False
    if _COMPRA.search(t):
        if not hay_productos and any(p.search(t) for p, _ in _GASTOS):
            return T.gasto_negocio, 0.85, False
        return T.compra, 0.88, False
    if _GASTO_VERBO.search(t) or re.search(r"\bgasto\b", t):
        conf = 0.9 if any(p.search(t) for p, _ in _GASTOS) else 0.7
        return T.gasto_negocio, conf, False
    if _VENTA.search(t):
        return T.venta, 0.92, False
    if _OTRO_INGRESO.search(t):
        return T.otro_ingreso, 0.8, False
    if hay_productos:
        return T.venta, 0.7, False
    return None, 0.0, False


def _categoria_gasto(t: str) -> str:
    for patron, categoria in _GASTOS:
        if patron.search(t):
            return categoria
    return "otros_gastos"


def _roles_de_numeros(t: str, nums: list[Numero], coincidencias, fecha: ResultadoFecha):
    """Separa los números en cantidades (por producto), precios unitarios, cuota, total del préstamo y montos."""
    cantidades: dict[int, Decimal] = {}
    precios: dict[int, Decimal] = {}
    cuota = frecuencia = total = None
    montos: list[Numero] = []
    for n in nums:
        if fecha.inicio is not None and fecha.inicio <= n.inicio < (fecha.fin or 0):
            continue
        despues, antes = t[n.fin:], t[:n.inicio]
        prod_siguiente = next((i for i, c in enumerate(coincidencias) if c.inicio >= n.fin), None)
        entre = t[n.fin:coincidencias[prod_siguiente].inicio] if prod_siguiente is not None else None
        if entre is not None and "docena" in n.texto:
            entre = re.sub(r"^\s*de\b", "", entre)
        if entre is not None and _RE_CANTIDAD.match(entre):
            if prod_siguiente not in cantidades:
                cantidades[prod_siguiente] = n.valor
                continue
        prod_anterior = next((i for i in range(len(coincidencias) - 1, -1, -1) if coincidencias[i].fin <= n.inicio),
                             None)  # fmt: skip
        if prod_anterior is not None and _RE_PRECIO_UNIT.match(t[coincidencias[prod_anterior].fin:n.inicio]):
            precios[prod_anterior] = n.valor
            continue
        if m := _RE_CUOTA.match(despues):
            cuota = n.valor
            frecuencia = next(f for p, f in _FRECUENCIAS if re.fullmatch(p, m.group(1)))
            continue
        if _RE_TOTAL_PRESTAMO.search(antes) and montos:
            total = n.valor
            continue
        if n.texto in ("un", "una", "uno") and not _RE_MONEDA_DESPUES.match(despues):
            continue
        if n.texto in ("medio", "media"):
            continue
        montos.append(n)
    # Prefiere el número que lleva moneda ("20 soles", "S/ 20")
    con_moneda = [n for n in montos if _RE_MONEDA_DESPUES.match(t[n.fin:]) or re.search(r"s/\s*$", t[:n.inicio])]
    ordenados = con_moneda + [n for n in montos if n not in con_moneda]
    return cantidades, precios, cuota, frecuencia, total, ordenados


def interpretar(texto: str, cat: Catalogo, hoy: date) -> Crudo:
    t = normalizar(texto)
    coincidencias = cat.encontrar_productos(t)
    fecha = parsear_fecha(t, hoy)
    cliente = cat.buscar_cliente(t)
    proveedor = cat.buscar_proveedor(t)
    tipo, confianza, fuera = _clasificar(t, bool(coincidencias), cliente, proveedor)
    crudo = Crudo(tipo=tipo, confianza=confianza, fuera_de_alcance=fuera, fecha=fecha)
    usa_productos = tipo in (T.venta, T.compra) or tipo is None
    cantidades, precios, cuota, frecuencia, total, montos = _roles_de_numeros(
        t, numeros(t), coincidencias if usa_productos else [], fecha
    )
    crudo.montos_dichos = [n.valor for n in montos]
    if tipo is None:
        return crudo
    if usa_productos:
        for i, c in enumerate(coincidencias):
            crudo.items.append(ItemCrudo(c.producto, cantidades.get(i, Decimal(1)), c.producto.nombre, precios.get(i)))
    crudo.monto = montos[0].valor if montos else None

    if tipo == T.prestamo_recibido:
        crudo.monto_cuota, crudo.frecuencia_cuota, crudo.monto_total_a_pagar = cuota, frecuencia, total
        if crudo.monto is None and len(montos) > 1:
            crudo.monto = montos[0].valor
        crudo.contraparte = _contraparte_prestamo(t)
    elif tipo == T.pago_prestamo:
        crudo.contraparte = _contraparte_prestamo(t)
    elif tipo in (T.compra, T.pago_proveedor):
        crudo.proveedor, crudo.contraparte = _contraparte_proveedor(t, cat)
    elif tipo in (T.venta, T.cobro_fiado):
        crudo.cliente, crudo.contraparte = _contraparte_cliente(t, cat)
        if tipo == T.venta and not (_FIADO.search(t)):
            crudo.cliente, crudo.contraparte = None, None
    if tipo == T.gasto_negocio:
        crudo.categoria = _categoria_gasto(t)

    explicito = _metodo(t)
    if tipo == T.venta and _FIADO.search(t):
        crudo.metodo_pago = MetodoPago.credito
    elif tipo == T.compra and (_PEDIDO.search(t) or _ME_FIARON.search(t)) and explicito is None:
        crudo.metodo_pago = MetodoPago.credito
    elif tipo == T.venta and _YAPE_INGRESO.search(t):
        crudo.metodo_pago = explicito or MetodoPago.billetera_digital
    else:
        crudo.metodo_pago = explicito

    if re.search(r"\banteayer\b", t):
        crudo.dias_atras = 2
    elif re.search(r"\bayer\b", t):
        crudo.dias_atras = 1
    return crudo
