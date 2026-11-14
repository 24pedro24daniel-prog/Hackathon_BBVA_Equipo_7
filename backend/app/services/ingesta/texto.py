"""Utilidades de texto en español para la ingesta: normalización, números dichos o escritos y fechas.

Todo es determinístico: el extractor por reglas las usa para entender la frase y el extractor con LLM para
verificar que los montos que devuelve el modelo de verdad aparecen en lo que dijo el usuario.
"""

import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin signos (salvo los que forman números y fechas)."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"s/\.?\s*", " s/ ", t)
    t = re.sub(r"[¿?¡!;:\"“”()«»]", " ", t)
    t = re.sub(r"(?<!\d)[.,](?!\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ── números ─────────────────────────────────────────────────────────────────────────────────────

_UNIDADES = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
             "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
             "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
             "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
             "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}  # fmt: skip
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
            "noventa": 90}  # fmt: skip
_CENTENAS = {"cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
             "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
             "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700, "ochocientos": 800,
             "ochocientas": 800, "novecientos": 900, "novecientas": 900}  # fmt: skip
_PALABRAS_NUM = set(_UNIDADES) | set(_DECENAS) | set(_CENTENAS) | {"mil", "y", "medio", "media", "docena", "docenas"}

_RE_DIGITOS = re.compile(r"(?<![\d/])(\d{1,3}(?:[ .,]\d{3})+(?![\d/])|\d+(?:[.,]\d{1,2})?(?![\d/]))(?:\s*mil\b)?")
_RE_FECHA_BARRA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")


@dataclass
class Numero:
    valor: Decimal
    inicio: int
    fin: int
    texto: str


def _a_decimal(crudo: str) -> Decimal | None:
    s = crudo.strip()
    multiplicador = Decimal(1)
    if s.endswith("mil"):
        s, multiplicador = s[:-3].strip(), Decimal(1000)
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", s):
        s = re.sub(r"[ .,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s) * multiplicador
    except InvalidOperation:
        return None


def _palabras_a_valor(palabras: list[str]) -> Decimal | None:
    total, actual = 0, 0
    vistos = False
    for p in palabras:
        if p == "y":
            continue
        if p in _UNIDADES:
            actual += _UNIDADES[p]
        elif p in _DECENAS:
            actual += _DECENAS[p]
        elif p in _CENTENAS:
            actual += _CENTENAS[p]
        elif p == "mil":
            total += (actual or 1) * 1000
            actual = 0
        else:
            return None
        vistos = True
    return Decimal(total + actual) if vistos else None


def numeros(texto_norm: str) -> list[Numero]:
    """Números escritos con dígitos o con palabras ("dos mil cuatrocientos"), en orden de aparición.

    "media docena" = 6, "docena" = 12, "medio"/"media" sueltos = 0.5. Las fechas con barra (30/11) se excluyen.
    """
    encontrados: list[Numero] = []
    ocupado = [False] * len(texto_norm)
    for m in _RE_FECHA_BARRA.finditer(texto_norm):
        for i in range(m.start(), m.end()):
            ocupado[i] = True
    for m in _RE_DIGITOS.finditer(texto_norm):
        if any(ocupado[m.start():m.end()]):
            continue
        valor = _a_decimal(m.group(0))
        if valor is not None:
            encontrados.append(Numero(valor, m.start(), m.end(), m.group(0)))
            for i in range(m.start(), m.end()):
                ocupado[i] = True

    # Palabras: secuencias de tokens numéricos contiguos
    tokens = [(t.group(0), t.start(), t.end()) for t in re.finditer(r"[a-zñ]+", texto_norm)]
    i = 0
    while i < len(tokens):
        palabra, ini, fin = tokens[i]
        if palabra in ("media", "medio") and i + 1 < len(tokens) and tokens[i + 1][0] == "docena":
            encontrados.append(Numero(Decimal(6), ini, tokens[i + 1][2], texto_norm[ini:tokens[i + 1][2]]))
            i += 2
            continue
        if palabra in ("docena", "docenas") and not re.search(r"\d\s*$", texto_norm[:ini]):
            encontrados.append(Numero(Decimal(12), ini, fin, palabra))
            i += 1
            continue
        if palabra in ("medio", "media"):
            encontrados.append(Numero(Decimal("0.5"), ini, fin, palabra))
            i += 1
            continue
        if palabra in _PALABRAS_NUM and palabra not in ("y", "docena", "docenas", "medio", "media"):
            j = i
            grupo = []
            while j < len(tokens) and tokens[j][0] in _PALABRAS_NUM - {"medio", "media", "docena", "docenas"}:
                if tokens[j][0] == "y" and (j + 1 >= len(tokens) or tokens[j + 1][0] not in _UNIDADES):
                    break
                grupo.append(tokens[j][0])
                j += 1
            # "una docena" / "dos docenas"
            if j < len(tokens) and tokens[j][0] in ("docena", "docenas"):
                valor = _palabras_a_valor(grupo)
                if valor is not None:
                    encontrados.append(Numero(valor * 12, ini, tokens[j][2], texto_norm[ini:tokens[j][2]]))
                    i = j + 1
                    continue
            valor = _palabras_a_valor(grupo)
            if valor is not None and not any(ocupado[ini:tokens[j - 1][2]]):
                encontrados.append(Numero(valor, ini, tokens[j - 1][2], texto_norm[ini:tokens[j - 1][2]]))
            i = max(j, i + 1)
            continue
        i += 1
    # "2 docenas" con dígitos
    for n in encontrados:
        resto = texto_norm[n.fin:]
        if re.match(r"\s+docenas?\b", resto) and n.texto[0].isdigit():
            n.valor *= 12
            n.fin += len(re.match(r"\s+docenas?\b", resto).group(0))
    return sorted(encontrados, key=lambda n: n.inicio)


def valores_en_texto(texto: str) -> set[Decimal]:
    """Todos los números que aparecen en el texto (para verificar montos que propone el LLM)."""
    return {n.valor.quantize(Decimal("0.01")) for n in numeros(normalizar(texto))}


# ── fechas ──────────────────────────────────────────────────────────────────────────────────────

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}  # fmt: skip
NOMBRE_MES = {v: k for k, v in MESES.items() if k != "setiembre"}
DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}

_PREFIJO_FECHA = r"(?:para el|hasta el|vence el|venza el|pago el|pagar el|pagarlo el|pagarle el|pagare el|" \
                 r"lo pago el|le pago el|el dia|para el dia|al)"  # fmt: skip


@dataclass
class ResultadoFecha:
    fecha: date | None = None
    opciones: list[date] = field(default_factory=list)
    inicio: int | None = None
    fin: int | None = None

    @property
    def ambigua(self) -> bool:
        return self.fecha is None and len(self.opciones) > 1


def _sumar_meses(d: date, meses: int) -> tuple[int, int]:
    total = d.month - 1 + meses
    return d.year + total // 12, total % 12 + 1


def _fecha_valida(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def _proxima_con_mes(dia: int, mes: int, hoy: date) -> date | None:
    candidata = _fecha_valida(hoy.year, mes, dia)
    if candidata and candidata < hoy:
        candidata = _fecha_valida(hoy.year + 1, mes, dia)
    return candidata


def parsear_fecha(texto_norm: str, hoy: date) -> ResultadoFecha:
    """Fecha de vencimiento o compromiso dicha en la frase.

    "el 30 de noviembre", "30/11", "en 15 dias", "el viernes", "fin de mes" → fecha exacta.
    "para el 30" (sin mes) → si ese día aún no pasó este mes, es ambigua entre este mes y el siguiente.
    """
    t = texto_norm
    if m := _RE_FECHA_BARRA.search(t):
        dia, mes = int(m.group(1)), int(m.group(2))
        anio = m.group(3)
        if anio:
            a = int(anio) + (2000 if len(anio) == 2 else 0)
            f = _fecha_valida(a, mes, dia)
        else:
            f = _proxima_con_mes(dia, mes, hoy)
        if f:
            return ResultadoFecha(f, [f], m.start(), m.end())
    meses = "|".join(MESES)
    if m := re.search(rf"\b(?:el\s+)?(\d{{1,2}}|[a-z]+)\s+de\s+({meses})\b", t):
        dia_txt = m.group(1)
        dia = int(dia_txt) if dia_txt.isdigit() else _UNIDADES.get(dia_txt) or _DECENAS.get(dia_txt)
        if dia:
            f = _proxima_con_mes(int(dia), MESES[m.group(2)], hoy)
            if f:
                return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"\bpasado manana\b", t):
        f = hoy + timedelta(days=2)
        return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"(?<!la )(?<!esta )\b(?:para |hasta )?manana\b", t):
        f = hoy + timedelta(days=1)
        return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"\bfin(?:al)? de mes\b", t):
        f = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
        return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"\b(?:la )?(?:proxima|siguiente) semana\b", t):
        f = hoy + timedelta(days=7)
        return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"\b(?:el|este|para el|hasta el)\s+(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", t):
        delta = (DIAS_SEMANA[m.group(1)] - hoy.weekday()) % 7 or 7
        f = hoy + timedelta(days=delta)
        return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(r"\b(?:en|dentro de|a)\s+(\d+|[a-z]+)\s+(dias|semanas|semana|meses|mes)\b", t):
        crudo = m.group(1)
        n = int(crudo) if crudo.isdigit() else (_UNIDADES.get(crudo) or _DECENAS.get(crudo))
        if crudo in ("un", "una"):
            n = 1
        if n:
            unidad = m.group(2)
            if unidad.startswith("dia"):
                f = hoy + timedelta(days=n)
            elif unidad.startswith("semana"):
                f = hoy + timedelta(weeks=n)
            else:
                anio, mes = _sumar_meses(hoy, n)
                f = date(anio, mes, min(hoy.day, calendar.monthrange(anio, mes)[1]))
            return ResultadoFecha(f, [f], m.start(), m.end())
    if m := re.search(rf"\b{_PREFIJO_FECHA}\s+(\d{{1,2}})\b(?!\s*(?:soles|lucas|s/|%|de\b(?!\s+(?:{meses}))))", t):
        dia = int(m.group(1))
        if 1 <= dia <= 31:
            opciones = []
            este = _fecha_valida(hoy.year, hoy.month, dia)
            if este and este > hoy:
                opciones.append(este)
            for k in (1, 2):
                anio, mes = _sumar_meses(hoy, k)
                sig = _fecha_valida(anio, mes, dia)
                if sig:
                    opciones.append(sig)
                    break
            opciones = opciones[:2]
            if len(opciones) == 1:
                return ResultadoFecha(opciones[0], opciones, m.start(), m.end())
            if opciones:
                return ResultadoFecha(None, opciones, m.start(), m.end())
    return ResultadoFecha()


def fecha_corta(d: date) -> str:
    return d.strftime("%d/%m")


def fecha_larga(d: date) -> str:
    return f"{d.day} de {NOMBRE_MES[d.month]}"


def soles(monto: Decimal | float | int, decimales: bool = False) -> str:
    """S/ 2 340 · S/ 13.00 · −S/ 650 (espacio fino como separador de miles, igual que el front)."""
    valor = Decimal(str(monto))
    signo = "−" if valor < 0 else ""
    valor = abs(valor)
    if decimales or valor != valor.to_integral_value():
        cuerpo = f"{valor:,.2f}"
    else:
        cuerpo = f"{valor:,.0f}"
    return f"{signo}S/ {cuerpo.replace(',', ' ')}"
