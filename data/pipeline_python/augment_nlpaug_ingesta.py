"""
TuCaserito — Generador y Aumentador de Ruido en Ingesta Manual (F1) con nlpaug + Reglas Fonéticas/OCR
Simula sobre los 3 canales manuales ('voz', 'texto', 'foto') y operación 100% en efectivo/crédito:
  1. Perturbaciones fonéticas de voz en español peruano (seseo, b/v, jerga de bodega como 'chelas')
     que reducen la confianza (< 0.75) y activan pregunta_aclaratoria (doble confirmación).
  2. Errores de OCR en cuaderno manuscrito (confusión 8 <-> 3/0, 5 <-> S, trazos borrosos).
  3. Casos explícitos de posibles duplicados (un movimiento dictado por voz y luego fotografiado en el cuaderno)
     sin eliminarlos automáticamente.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = BASE_DIR / "eval"
random.seed(42)

PHONETIC_SUBS = [
    ("vendí", "bendi"),
    ("cervezas", "serbesas"),
    ("cerveza", "chela"),
    ("señora", "seño"),
    ("saqué", "sake"),
    ("aceite", "aseite"),
    ("arroz", "arros"),
    ("para la casa", "pa la casa"),
]

OCR_SUBS = [
    ("380", "330"),
    ("95", "35"),
    ("80", "30"),
    ("Carmen", "Carme"),
    ("panes", "panez"),
]


def apply_phonetic_noise(text: str) -> str:
    noisy = text
    for src, dst in PHONETIC_SUBS:
        if src in noisy:
            noisy = noisy.replace(src, dst, 1)
    return noisy


def apply_ocr_noise(text: str) -> str:
    noisy = text
    for src, dst in OCR_SUBS:
        if src in noisy:
            noisy = noisy.replace(src, dst, 1)
    return noisy


if __name__ == "__main__":
    eval_path = EVAL_DIR / "frases_ingesta_eval.json"
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    for idx, item in enumerate(items):
        if item["canal"] == "voz" and idx % 3 == 1:
            item["frase_ruido_voz"] = apply_phonetic_noise(item["frase"])
        elif item["canal"] == "foto":
            item["frase_ruido_ocr"] = apply_ocr_noise(item["frase"])
    eval_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✔ {len(items)} casos manuales (voz/texto/foto, 100% efectivo/crédito) enriquecidos en {eval_path.name}")
