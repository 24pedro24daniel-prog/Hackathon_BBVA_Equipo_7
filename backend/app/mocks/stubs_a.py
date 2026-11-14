"""STUBS de rutas de Dev A (ingesta / asistente / salud). Port de frontend/src/mocks/handlers.js.

Existen solo para el checkpoint C0 (el front con VITE_USE_MOCK=false funciona). Dev A los reemplaza
por servicios reales dentro de sus routers; al terminar, este archivo se borra.
"""
import re
from datetime import datetime

from app.core.meta import construir_meta
from app.core.reloj import ahora
from app.mocks import data as mock


def _meta(modelo: str, version: str, **kw) -> dict:
    return construir_meta(modelo, version, **kw).model_dump(mode="json")


def _soles(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def interpretar_texto(texto: str) -> dict | None:
    t = (texto or "").lower()
    base = {"moneda": "PEN", "contraparte": None, "fecha_hora": ahora().isoformat(), "fecha_vencimiento": None}
    if "cerveza" in t:
        c = mock.CATALOGO["cerveza"]
        cant = 2 if re.search(r"\b(dos|2)\b", t) else 3 if re.search(r"\b(tres|3)\b", t) else 1
        sub = c["precio_unitario"] * cant
        return {
            "movimiento_propuesto": {**base, "tipo": "venta", "metodo_pago": "efectivo", "monto": sub,
                                     "items": [{**c, "cantidad": cant, "subtotal": sub}]},
            "origen_monto": "catalogo", "confianza": 0.93, "campos_faltantes": [], "pregunta_aclaratoria": None,
        }
    m = re.search(r"saqu[eé]\s+(\d+)", t)
    if m:
        return {
            "movimiento_propuesto": {**base, "tipo": "retiro_personal", "metodo_pago": "efectivo",
                                     "monto": float(m.group(1)), "items": []},
            "origen_monto": "dicho_por_usuario", "confianza": 0.95, "campos_faltantes": [], "pregunta_aclaratoria": None,
        }
    m = re.search(r"ped[ií]\s+([\d\s.]+)\s+a\s+(\w+)", t)
    if m:
        monto = float(re.sub(r"[\s.]", "", m.group(1)))
        prov = "Distribuidora Andina" if m.group(2) == "andina" else m.group(2)
        return {
            "movimiento_propuesto": {**base, "tipo": "compra", "metodo_pago": "credito", "monto": monto,
                                     "items": [], "contraparte": prov},
            "origen_monto": "dicho_por_usuario", "confianza": 0.7, "campos_faltantes": ["fecha_vencimiento"],
            "pregunta_aclaratoria": "¿Lo pagas el 30 de noviembre o el 30 de diciembre?",
            "opciones_aclaracion": [{"valor": "2026-11-30", "texto": "30/11"}, {"valor": "2026-12-30", "texto": "30/12"}],
        }
    m = re.search(r"pagu[eé].*?(\d+)", t)
    if "rus" in t and m:
        return {
            "movimiento_propuesto": {**base, "tipo": "pago_impuesto", "metodo_pago": "efectivo",
                                     "monto": float(m.group(1)), "items": []},
            "origen_monto": "dicho_por_usuario", "confianza": 0.9, "campos_faltantes": [], "pregunta_aclaratoria": None,
        }
    return None


def asistente(mensaje: str, conversacion_id: str | None) -> dict:
    m = (mensaje or "").lower()
    saldo = mock.ESTADO["saldo"]
    base = {
        "conversacion_id": conversacion_id or "CNV-0031", "herramientas_llamadas": [], "cifras_usadas": [],
        "verificacion_cifras": {"ok": True, "no_verificadas": []}, "fuera_de_alcance": False, "ofrecer_humano": False,
        "disclaimer": "Orientación educativa · no es asesoría",
        "meta": _meta("llm-local", "qwen2.5-7b-instruct", prompt_version="asistente-v2"),
    }
    if re.search(r"pr[eé]stamo|prestar|gota", m):
        return {**base, "intencion": "prestamo", "fuera_de_alcance": True, "ofrecer_humano": True,
                "respuesta": "No te puedo recomendar un préstamo ni una entidad, pero sí mostrarte el costo:",
                "ejemplo_prestamo_informal": {"recibes": 1000, "devuelves": 1200, "dias": 30, "cuota_diaria": 40},
                "respuesta_post": "Antes, prueba esto: pedir menos, pagar en 2 partes y cobrar fiados. Con eso ya llegas al 30/11.",
                "acciones": [{"tipo": "abrir_simulador", "texto": "Ver mi plan"}, {"tipo": "hablar_humano", "texto": "Hablar con una persona"}],
                "cifras_usadas": [{"valor": 1000, "fuente": "microexplicaciones.prestamo_informal.ejemplo"}]}
    if re.search(r"c[oó]mo va|mi caja|cu[aá]nto tengo", m):
        return {**base, "intencion": "estado_caja",
                "respuesta": f"Hoy tienes S/ {_soles(saldo)} en la caja del negocio. Te deben S/ 310 en fiados y el 30/11 pagas S/ 2 400 a Andina. Si no cambias nada, ese día te faltarían S/ 650.",
                "tabla": [{"etiqueta": "Caja del negocio", "valor": saldo}, {"etiqueta": "Te deben (fiados)", "valor": 310},
                          {"etiqueta": "Debes (30/11)", "valor": 2400}],
                "herramientas_llamadas": [{"nombre": "obtener_resumen", "args": {"periodo": "2026-11"}},
                                          {"nombre": "obtener_forecast", "args": {"horizonte_dias": 30}}],
                "cifras_usadas": [{"valor": saldo, "fuente": "resumen.saldo_caja_negocio"},
                                  {"valor": 650, "fuente": "forecast.dia_critico.saldo_p50"}]}
    if re.search(r"por qu[eé]|falta|alcanza", m):
        return {**base, "intencion": "explicar_alerta", "ofrecer_humano": True,
                "respuesta": "El 30/11 vence tu pago de S/ 2 400 a Distribuidora Andina. Este mes sacaste S/ 700 más de lo usual para la casa, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ 310 en fiados sin cobrar. Si pides S/ 1 800 y pagas en 2 partes, ese día tendrías S/ 850.",
                "herramientas_llamadas": [{"nombre": "obtener_alertas", "args": {"estado": "activa"}},
                                          {"nombre": "simular", "args": {"acciones": ["reducir_pedido:1800", "pagar_en_partes:2"]}}],
                "cifras_usadas": [{"valor": 2400, "fuente": "pedidos.PED-0012.monto"},
                                  {"valor": 850, "fuente": "simular.con_acciones.saldo_minimo"}]}
    if re.search(r"2 partes|dos partes|si pago", m):
        v = mock.simular_saldo(partes=2)
        return {**base, "intencion": "simular",
                "respuesta": f"Si pagas a Andina en 2 partes (30/11 y 15/12), ese día te quedarían S/ {_soles(v)}. Tendrías que pedírselo a Andina.",
                "herramientas_llamadas": [{"nombre": "simular", "args": {"acciones": ["pagar_en_partes:2"]}}],
                "cifras_usadas": [{"valor": v, "fuente": "simular.con_acciones.saldo_minimo"}]}
    return {**base, "intencion": "otro",
            "respuesta": "Puedo ayudarte con: cómo va tu caja, por qué te faltaría plata, o qué pasa si cambias un pedido. ¿Qué quieres saber?"}


def aplicar_al_saldo(mov: dict) -> None:
    """Mueve el saldo en memoria como lo hace el mock del front."""
    if mov.get("tipo") == "venta" and mov.get("metodo_pago") != "credito":
        mock.ESTADO["saldo"] += float(mov["monto"])
    if mov.get("tipo") in ("retiro_personal", "pago_impuesto"):
        mock.ESTADO["saldo"] -= float(mov["monto"])


def cuaderno() -> dict:
    return {
        "borrador_id": mock.siguiente_borrador(),
        "fiados_propuestos": [
            {"cliente": "Sra. Carmen", "detalle": "panes, leche", "monto": 120.0, "fecha": "2026-10-27", "confianza": 0.81},
            {"cliente": "Don Luis", "detalle": "arroz, aceite", "monto": 95.0, "fecha": "2026-11-02", "confianza": 0.64, "alternativas_monto": [95, 35]},
            {"cliente": "Vecina Rosa", "detalle": "gaseosas", "monto": 95.0, "fecha": "2026-11-05", "confianza": 0.88},
        ],
        "lineas_no_legibles": 1,
        "meta": _meta("ocr-manuscrito + llm-estructurador", "0.1.0", prompt_version="cuaderno-v1"),
    }


def interpretar_respuesta(canal: str, texto: str | None) -> dict | None:
    """Arma la respuesta de /ingesta/interpretar (o None si no se entiende)."""
    texto_final = texto or ("vendí dos cervezas" if canal == "voz" else "")
    res = interpretar_texto(texto_final)
    if res is None:
        return None
    borrador_id = mock.siguiente_borrador()
    mock.BORRADORES[borrador_id] = res["movimiento_propuesto"]
    return {
        "borrador_id": borrador_id,
        "transcripcion": texto_final if canal == "voz" else None,
        **res,
        "meta": _meta("whisper-small + llm-extractor", "0.2.0", prompt_version="extractor-v3"),
    }
