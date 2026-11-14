"""Cada cifra de la respuesta del LLM debe existir en los resultados de las herramientas (A10).

Si alguna no se verifica → verificacion_cifras.ok = false y la respuesta se reemplaza por la plantilla.
Se ignoran fechas (30/11, "30 de noviembre") y conteos pequeños (≤ 10: "2 partes", "3 fiados").
"""

import re
from decimal import Decimal, InvalidOperation

from app.services.ingesta.texto import MESES

_RE_FECHA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_RE_DIA_MES = re.compile(r"\b\d{1,2}\s+de\s+(?:" + "|".join(MESES) + r")\b", re.IGNORECASE)
_RE_NUMERO = re.compile(r"-?\d{1,3}(?:[   .,]\d{3})+(?:[.,]\d{1,2})?|-?\d+(?:[.,]\d{1,2})?")
CONTEO_MAXIMO_LIBRE = 10


def _a_decimal(crudo: str) -> Decimal | None:
    s = crudo.replace(" ", " ").replace(" ", " ")
    if re.fullmatch(r"-?\d{1,3}(?:[ .,]\d{3})+", s):
        s = re.sub(r"[ .,]", "", s)
    elif m := re.fullmatch(r"(-?\d{1,3}(?:[ .,]\d{3})+)[.,](\d{1,2})", s):
        s = re.sub(r"[ .,]", "", m.group(1)) + "." + m.group(2)
    else:
        s = s.replace(",", ".")
    try:
        return abs(Decimal(s))
    except InvalidOperation:
        return None


def cifras_en_texto(texto: str) -> list[Decimal]:
    limpio = _RE_DIA_MES.sub(" ", _RE_FECHA.sub(" ", texto or ""))
    limpio = limpio.replace("−", "-")
    valores = []
    for m in _RE_NUMERO.finditer(limpio):
        v = _a_decimal(m.group(0))
        if v is not None:
            valores.append(v)
    return valores


def _numeros(dato, salida: set[Decimal]) -> None:
    if isinstance(dato, bool) or dato is None:
        return
    if isinstance(dato, (int, float, Decimal)):
        salida.add(abs(Decimal(str(dato))).quantize(Decimal("0.01")))
    elif isinstance(dato, dict):
        for v in dato.values():
            _numeros(v, salida)
    elif isinstance(dato, (list, tuple)):
        for v in dato:
            _numeros(v, salida)
    elif isinstance(dato, str):
        if re.fullmatch(r"-?\d+(?:\.\d+)?", dato.strip()):
            salida.add(abs(Decimal(dato.strip())).quantize(Decimal("0.01")))


def permitidas(resultados_herramientas: list) -> set[Decimal]:
    salida: set[Decimal] = set()
    _numeros(resultados_herramientas, salida)
    return salida


def verificar_cifras(respuesta: str, resultados_herramientas: list) -> dict:
    """{"ok": bool, "no_verificadas": [cifras]} comparando con todas las cifras de las herramientas."""
    validas = permitidas(resultados_herramientas)
    no_verificadas = []
    for v in cifras_en_texto(respuesta):
        if v <= CONTEO_MAXIMO_LIBRE and v == v.to_integral_value():
            continue
        q = v.quantize(Decimal("0.01"))
        entero = v == v.to_integral_value()
        if q in validas or (entero and any(abs(x - v) < Decimal("0.5") for x in validas)):
            continue
        no_verificadas.append(float(v))
    return {"ok": not no_verificadas, "no_verificadas": no_verificadas}
