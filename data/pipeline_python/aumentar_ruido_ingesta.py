"""
TuCaserito — Variantes con ruido de las frases de evaluación de la ingesta (voz y foto del cuaderno).

Lee data/eval/frases_ingesta_eval.json (generado por el generador) y escribe data/eval/frases_ingesta_eval_ruido.json con
una variante ruidosa de las frases de voz (jerga y errores fonéticos del español peruano: "bendí", "chelas", "pa la casa") y
de las fotos del cuaderno (confusiones de dígitos 8/3, 5/6, 1/7). Son reglas determinísticas propias: NO usa la
librería nlpaug (el script anterior la nombraba pero no la usaba) y NO modifica el archivo original.

Cada variante conserva la verdad esperada y marca `requiere_doble_confirmacion = true` con confianza < 0.75, porque el
backend (UMBRAL_CONFIANZA) repregunta cuando la extracción es dudosa.

    python data/pipeline_python/aumentar_ruido_ingesta.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

FONETICA = [("vendí", "bendi"), ("vendió", "bendio"), ("cervezas", "serbesas"), ("cerveza", "serbesa"), ("para la casa", "pa la casa"),
            ("saqué", "sake"), ("aceite", "aseite"), ("arroz", "arros"), ("señora", "seño"), ("fié", "fie"), ("pagué", "pague"), ("préstamo", "prestamo")]
DIGITOS = {"8": "3", "3": "8", "5": "6", "6": "5", "1": "7"}


def ruido_voz(frase: str) -> str | None:
    salida = frase
    for origen, destino in FONETICA:
        if origen in salida:
            salida = salida.replace(origen, destino, 1)
            break  # un solo cambio por frase: el ruido es leve
    return salida if salida != frase else None


def ruido_ocr(frase: str) -> str | None:
    numeros = list(re.finditer(r"\d+", frase))
    if not numeros:
        return None
    m = numeros[-1]
    texto = m.group()
    cambiado = "".join(DIGITOS.get(c, c) if i == len(texto) - 1 else c for i, c in enumerate(texto))
    return frase[: m.start()] + cambiado + frase[m.end():] if cambiado != texto else None


def main() -> None:
    casos = json.loads((EVAL_DIR / "frases_ingesta_eval.json").read_text(encoding="utf-8"))
    nuevos = []
    for caso in casos:
        if not caso["dentro_alcance"]:
            continue
        frase = ruido_voz(caso["frase"]) if caso["canal"] in ("voz", "texto") else ruido_ocr(caso["frase"])
        if frase is None or frase == caso["frase"]:
            continue
        nuevos.append({**caso, "caso_id": f"{caso['caso_id']}-R", "frase": frase, "confianza_simulada": min(caso["confianza_simulada"], 0.72),
                       "requiere_doble_confirmacion": True,
                       "pregunta_aclaratoria": caso["pregunta_aclaratoria"] or "No estoy seguro de lo que entendí. ¿Me confirmas el monto y el tipo de movimiento?"})
    (EVAL_DIR / "frases_ingesta_eval_ruido.json").write_text(json.dumps(nuevos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(nuevos)} variantes con ruido escritas en frases_ingesta_eval_ruido.json (de {len(casos)} frases)")


if __name__ == "__main__":
    main()
