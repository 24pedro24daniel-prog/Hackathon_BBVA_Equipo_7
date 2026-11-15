"""Plantillas de fallback y microexplicaciones fijas revisadas por el equipo (A10).

Cada plantilla arma la respuesta SOLO con cifras de los resultados de las herramientas (funciones de B) y devuelve
de dónde salió cada una (`cifras_usadas`). Son la respuesta cuando no hay LLM o cuando su texto no pasa el
verificador de cifras.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.ingesta.texto import fecha_corta, soles

DISCLAIMER = "Orientación educativa. No es asesoría financiera."

MICROEXPLICACIONES: dict[str, str] = {
    "separar_caja": "Si sacas de la caja sin un monto fijo, es difícil saber cuánto puedes pedir.",
    "flujo_caja": "El flujo de caja es la plata que entra y sale de tu negocio día a día. Aunque ganes, si los pagos "
                  "llegan antes que los cobros, un día te puede faltar.",
    "fiado": "Un fiado es plata que ya es tuya pero que todavía no está en tu caja. Mientras no la cobres, no la "
             "puedes usar para pagar.",
    "prestamo_informal": "Un préstamo informal (gota a gota) parece rápido, pero cobra mucho: lo que devuelves "
                         "puede ser bastante más de lo que recibes, y la cuota diaria sale de la venta del día.",
    "sueldo_fijo": "Ponerte un sueldo fijo es sacar siempre lo mismo de la caja para ti; el resto se queda "
                   "trabajando en el negocio.",
    "colchon_caja": "Un colchón de caja es un monto que no tocas, para los días malos o para un pago que se adelanta.",
    "disponible": "Lo disponible para gastar es lo que te queda después de separar tus pagos que vienen, tu mínimo "
                  "para operar y tus impuestos.",
}
TEMAS_CONCEPTO = {"flujo": "flujo_caja", "caja": "flujo_caja", "fiado": "fiado", "gota": "prestamo_informal",
                  "prestamo": "prestamo_informal", "sueldo": "sueldo_fijo", "colchon": "colchon_caja",
                  "disponible": "disponible", "separar": "separar_caja", "mezcl": "separar_caja"}  # fmt: skip

# Ejemplo ilustrativo fijo (context.md §9, paso 5): recibes 1 000 y devuelves 1 200 en 30 días.
PRESTAMO_INFORMAL_EJEMPLO = {"recibes": 1000, "devuelves": 1200, "dias": 30, "cuota_diaria": 40, "costo": 200,
                             "costo_pct": 20}  # fmt: skip

FUERA_DE_ALCANCE = ("Eso está fuera de lo que puedo orientarte: no recomiendo créditos ni entidades específicas, "
                    "inversiones, criptomonedas ni temas tributarios o legales. Para eso conviene hablar con un "
                    "asesor de una entidad supervisada o con un contador. Si quieres, te paso con una persona del "
                    "equipo.")  # fmt: skip
AYUDA = ("Cuéntame un poquito más: ¿es sobre tu caja, tus fiados o algún pago que se viene? Con gusto lo vemos "
         "juntos.")  # fmt: skip
SALUDO = "¡Hola! ¿Qué tal va el día en la bodega? Si quieres, vemos cómo va tu caja o algún pago que se viene."
GRACIAS = "¡De nada! Aquí estoy para cuando quieras revisar tu caja o tus cuentas."
DESPEDIDA = "¡Cuídate! Aquí estaré cuando quieras revisar tu caja."
CREAR_META = ("Puedes activar una meta: anotar 30 días seguidos, ponerte un sueldo fijo, armar un colchón de caja, "
              "apartar para el pedido o reservar para impuestos. Elige una en «Tu progreso» y la sigo contigo.")  # fmt: skip
SIMULAR_AYUDA = ("¿Qué quieres probar? Por ejemplo: «¿y si pago en 2 partes?», «¿y si pido menos?» o «¿y si cobro "
                 "los fiados?».")  # fmt: skip


@dataclass
class Borrador:
    texto: str
    cifras: list[tuple[float, str]] = field(default_factory=list)
    extras: dict = field(default_factory=dict)
    ofrecer_humano: bool = False
    conversacional: bool = False  # charla (saludo, gracias, poco claro): el LLM puede responder libre, sin cifras

    def cifra(self, valor, fuente: str) -> str:
        self.cifras.append((float(valor), fuente))
        return soles(Decimal(str(valor)))


def _fecha(valor) -> str:
    return fecha_corta(date.fromisoformat(str(valor)))


def estado_caja(resumen: dict, forecast: dict) -> Borrador:
    b = Borrador("")
    ind = resumen["indicadores"]
    saldo = ind["saldo_caja_negocio"]["valor"]
    fiados = ind["pendiente_cobro"]["valor"]
    partes = [f"Hoy tienes {b.cifra(saldo, 'resumen.indicadores.saldo_caja_negocio')} en la caja del negocio."]
    tabla = [{"etiqueta": "Caja del negocio", "valor": saldo}]
    if fiados:
        partes.append(f"Te deben {b.cifra(fiados, 'resumen.indicadores.pendiente_cobro')} en fiados.")
        tabla.append({"etiqueta": "Te deben (fiados)", "valor": fiados})
    dc = forecast.get("dia_critico")
    if dc:
        fecha = _fecha(dc["fecha"])
        ob = dc.get("obligacion_asociada")
        if ob:
            quien = f" a {ob['proveedor']}" if ob.get("proveedor") else ""
            partes.append(f"El {fecha} pagas {b.cifra(ob['monto'], 'forecast.dia_critico.obligacion_asociada.monto')}"
                          f"{quien}.")  # fmt: skip
            tabla.append({"etiqueta": f"Debes ({fecha})", "valor": ob["monto"]})
        p50 = dc["saldo_p50"]
        if p50 < 0:
            partes.append(f"Si no cambias nada, ese día te faltarían {b.cifra(abs(p50), 'forecast.dia_critico.saldo_p50')}.")
        else:
            partes.append(f"Ese día tu caja quedaría en {b.cifra(p50, 'forecast.dia_critico.saldo_p50')}.")
    else:
        partes.append(f"Por ahora tu caja alcanza para los próximos {forecast.get('horizonte_dias', 30)} días.")
    b.texto = " ".join(partes)
    b.extras["tabla"] = tabla
    return b


def _abrir_simulador(texto: str, pedido_id: str | None) -> dict:
    """Acción del asistente que lleva al simulador; con `pedido_id` el front abre ese pedido."""
    return {"tipo": "abrir_simulador", "texto": texto, **({"pedido_id": pedido_id} if pedido_id else {})}


def explicar_alerta(alerta: dict | None, simulacion: dict | None, nuevo_monto) -> Borrador:
    if alerta is None:
        return Borrador("No tienes alertas activas ahora. Si quieres, te digo cómo va tu caja.")
    b = Borrador("", ofrecer_humano=True)
    aid = alerta["alerta_id"]
    partes = [alerta.get("insight") or alerta.get("titulo") or "Tienes una alerta activa."]
    for i, c in enumerate(alerta.get("causas") or []):
        b.cifras.append((float(c["monto"]), f"alertas.{aid}.causas[{i}]"))
    if alerta.get("monto") is not None:
        b.cifras.append((float(alerta["monto"]), f"alertas.{aid}.monto"))
    causas = alerta.get("causas") or []
    if causas:
        detalle = "; ".join(f"{c['descripcion'][:1].lower()}{c['descripcion'][1:]} ({soles(Decimal(str(c['monto'])))})"
                            for c in causas)  # fmt: skip
        partes.append(f"Las causas: {detalle}.")
    if simulacion and nuevo_monto:
        con = simulacion["con_acciones"]
        partes.append(f"Si pides {b.cifra(nuevo_monto, 'chequear_pedido.sugerencias.reducir_pedido.monto_sugerido')} "
                      f"y pagas en 2 partes, el {_fecha(con['fecha'])} tendrías "
                      f"{b.cifra(con['saldo_minimo'], 'simular.con_acciones.saldo_minimo')}.")  # fmt: skip
    b.texto = " ".join(partes)
    pedido_id = ((alerta.get("accion") or {}).get("payload") or {}).get("pedido_id")
    b.extras["acciones"] = [_abrir_simulador("Ver qué puedo hacer", pedido_id)]
    return b


_ESTADO_TXT = {"te_alcanza": "Te alcanza.", "justo": "Te alcanza justo, sin colchón.",
               "no_te_alcanza": "Todavía no te alcanzaría."}  # fmt: skip


def simular(simulacion: dict, descripcion: str, con_partes: bool, pedido_id: str | None = None) -> Borrador:
    b = Borrador("")
    con, sin = simulacion["con_acciones"], simulacion["sin_acciones"]
    texto = (f"Si {descripcion}, el {_fecha(con['fecha'])} tendrías "
             f"{b.cifra(con['saldo_minimo'], 'simular.con_acciones.saldo_minimo')} en caja (sin cambios: "
             f"{b.cifra(sin['saldo_minimo'], 'simular.sin_acciones.saldo_minimo')}). "
             f"{_ESTADO_TXT.get(con.get('estado_caja'), '')}")  # fmt: skip
    if con_partes:
        texto += " Pagar en partes depende de que el proveedor acepte."
    b.texto = texto.strip()
    b.extras["acciones"] = [_abrir_simulador("Probar opciones", pedido_id)]
    return b


def prestamo(ejemplo: dict, simulacion: dict | None, pedido_id: str | None = None) -> Borrador:
    b = Borrador("No te puedo recomendar un préstamo ni una entidad, pero sí mostrarte cuánto cuesta uno informal:",
                 ofrecer_humano=True)  # fmt: skip
    for clave in ("recibes", "devuelves", "dias", "cuota_diaria", "costo", "costo_pct"):
        b.cifras.append((float(ejemplo[clave]), f"microexplicaciones.prestamo_informal.ejemplo.{clave}"))
    post = (f"Recibir {soles(ejemplo['recibes'])} y devolver {soles(ejemplo['devuelves'])} te cuesta "
            f"{soles(ejemplo['costo'])} más en solo {ejemplo['dias']} días, pagando "
            f"{soles(ejemplo['cuota_diaria'])} cada día.")  # fmt: skip
    if simulacion:
        con = simulacion["con_acciones"]
        post += (f" Antes, prueba con tus propias opciones: pedir menos, pagar en 2 partes y cobrar tus fiados. "
                 f"Con eso, el {_fecha(con['fecha'])} tendrías "
                 f"{b.cifra(con['saldo_minimo'], 'simular.con_acciones.saldo_minimo')}.")  # fmt: skip
    b.extras["ejemplo_prestamo_informal"] = {k: ejemplo[k] for k in ("recibes", "devuelves", "dias", "cuota_diaria")}
    b.extras["respuesta_post"] = post
    b.extras["acciones"] = [_abrir_simulador("Ver mi plan", pedido_id),
                            {"tipo": "hablar_humano", "texto": "Hablar con una persona"}]  # fmt: skip
    return b
