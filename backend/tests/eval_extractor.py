"""Set de evaluación del extractor (A13): frases sintéticas con su JSON esperado → exactitud por campo.

    python -m tests.eval_extractor              # fallback por reglas (offline, sin red ni BD)
    python -m tests.eval_extractor --llm        # además la ruta LLM (OpenRouter: 1 llamada por frase, cuesta)
    python -m tests.eval_extractor --llm --limite 10 --json

Dos conjuntos: CASOS (133 frases, escritas junto con las reglas → resultado optimista) y HOLDOUT (25 frases nuevas
que no se usaron para ajustar las reglas → estimación más honesta).

Catálogo: el de Pedro tal como lo siembra seed_demo (catalogo.desde_seed()), "hoy" = 14/11/2026.
Campos medidos: tipo, monto, metodo_pago, contraparte y, cuando el caso lo indica, fecha_vencimiento.
`tipo = None` significa que la frase NO debe registrarse (saludo, pregunta o gasto de la casa sin monto).
"% que requiere corrección" = casos con al menos un campo distinto del esperado.
No lo recoge pytest (no empieza con test_); tests/test_a_extractor.py corre la versión por reglas como regresión.
"""

import argparse
import json
import sys
from decimal import Decimal

from app.core.errors import NoInterpretable

R, C, L, A = "Vecina Rosa", "Sra. Carmen", "Don Luis", "Distribuidora Andina"
E, B, CR, T_, TJ = "efectivo", "billetera_digital", "credito", "transferencia", "tarjeta"

# (texto, tipo, monto, metodo_pago, contraparte[, fecha_vencimiento])
CASOS: list[tuple] = [
    # ventas
    ("vendí dos cervezas", "venta", 13, E, None),
    ("vendí 3 gaseosas", "venta", 7.5, E, None),
    ("vendí una cerveza", "venta", 6.5, E, None),
    ("vendí 10 panes", "venta", 3, E, None),
    ("vendí un kilo de arroz", "venta", 4, E, None),
    ("vendí 2 leches y 1 atún", "venta", 14.4, E, None),
    ("se vendieron 4 chelas", "venta", 26, E, None),
    ("vendí 2 cervezas por yape", "venta", 13, B, None),
    ("vendí 3 gaseosas a 2.50", "venta", 7.5, E, None),
    ("vendí 20 soles de pan", "venta", 20, E, None),
    ("vendí una gaseosa grande", "venta", 11, E, None),
    ("vendí 2 aguas", "venta", 3, E, None),
    ("vendí un yogurt y un queso", "venta", 13.5, E, None),
    ("vendí media docena de huevos", "venta", 3.6, E, None),
    ("vendí 5 galletas", "venta", 5, E, None),
    ("me compraron 2 detergentes", "venta", 11, E, None),
    ("vendí 150 en total hoy", "venta", 150, E, None),
    ("hice una venta de 35 soles", "venta", 35, E, None),
    ("vendí 2 cervezas, me pagaron con tarjeta", "venta", 13, TJ, None),
    ("vendí 3 cervezas por transferencia", "venta", 19.5, T_, None),
    ("vendí 4 jabones", "venta", 12.8, E, None),
    ("vendí 2 aceites", "venta", 19, E, None),
    ("vendí 3 fideos y 2 atunes", "venta", 20.4, E, None),
    ("vendí un papel higiénico", "venta", 6.8, E, None),
    ("vendí 6 cervezas en efectivo", "venta", 39, E, None),
    ("salieron 5 gaseosas", "venta", 12.5, E, None),
    ("vendí 2 chocolates", "venta", 4, E, None),
    ("me yapearon 18.50", "venta", 18.5, B, None),
    ("me plinearon 25 por unas cervezas", "venta", 25, B, None),
    ("ayer vendí 3 cervezas", "venta", 19.5, E, None),
    ("vendí 4 cervezas a 7 cada una", "venta", 28, E, None),
    ("me compraron 3 chelas por plin", "venta", 19.5, B, None),
    ("vendí 2 yogures", "venta", 15, E, None),
    ("vendí tres atunes", "venta", 18, E, None),
    ("anota 30 soles de venta", "venta", 30, E, None),
    ("vendí dos panes y una gaseosa", "venta", 3.1, E, None),
    ("vendí 2 kilos de azúcar", "venta", 7.6, E, None),
    ("vendí cuarenta soles en abarrotes", "venta", 40, E, None),
    ("vendí 3 aguas y 2 galletas con yape", "venta", 6.5, B, None),
    ("vendí 1 detergente y 1 jabón", "venta", 8.7, E, None),
    # ventas fiadas
    ("le fié 20 a Rosa", "venta", 20, CR, R),
    ("le fié a la señora Carmen 2 panes y una leche", "venta", 4.8, CR, C),
    ("fiado a don Luis 15 soles", "venta", 15, CR, L),
    ("Don Luis se llevó 3 cervezas fiado", "venta", 19.5, CR, L),
    ("le fié 2 arroces a Carmen", "venta", 8, CR, C),
    ("a cuenta de Rosa 12 soles", "venta", 12, CR, R),
    ("le fié 30 a la vecina Rosa para el viernes", "venta", 30, CR, R, "2026-11-20"),
    ("le fié 10 a Juana", "venta", 10, CR, "Juana"),
    ("fié una leche a la señora Carmen", "venta", 4.2, CR, C),
    ("le fié 50 soles a don Luis", "venta", 50, CR, L),
    ("le vendí fiado 3 panes a Rosa", "venta", 0.9, CR, R),
    ("Carmen se llevó 25 soles a cuenta", "venta", 25, CR, C),
    ("vendí 12 panes y 2 leches a Rosa fiado", "venta", 12, CR, R),
    ("Rosa me debe 15 de gaseosas", "venta", 15, CR, R),
    ("le fié un aceite a Luis", "venta", 9.5, CR, L),
    ("fié 8 soles a la señora Marta", "venta", 8, CR, "Marta"),
    # cobros de fiado
    ("me pagó Rosa", "cobro_fiado", 95, E, R),
    ("la señora Carmen me pagó 50", "cobro_fiado", 50, E, C),
    ("don Luis me pagó 95", "cobro_fiado", 95, E, L),
    ("Rosa me pagó 20 por yape", "cobro_fiado", 20, B, R),
    ("me pagó Carmen 120", "cobro_fiado", 120, E, C),
    ("cobré el fiado de don Luis, 40 soles", "cobro_fiado", 40, E, L),
    ("Luis pagó su fiado", "cobro_fiado", 95, E, L),
    ("me pagó la vecina Rosa 95 soles", "cobro_fiado", 95, E, R),
    ("Carmen me abonó 30", "cobro_fiado", 30, E, C),
    ("me pagó don Luis lo que debía", "cobro_fiado", 95, E, L),
    ("la señora Carmen me pagó todo", "cobro_fiado", 120, E, C),
    ("Rosa me yapeó 50", "cobro_fiado", 50, B, R),
    # retiros personales
    ("saqué 100 para la casa", "retiro_personal", 100, E, None),
    ("saqué 50 para la casa", "retiro_personal", 50, E, None),
    ("retiré 200 de la caja", "retiro_personal", 200, E, None),
    ("saqué 400 de mi sueldo", "retiro_personal", 400, E, None),
    ("agarré 30 soles para el almuerzo de la casa", "retiro_personal", 30, E, None),
    ("saqué 150 de la caja para el colegio", "retiro_personal", 150, E, None),
    ("me llevé 80 para mi familia", "retiro_personal", 80, E, None),
    ("saqué cien soles para la casa", "retiro_personal", 100, E, None),
    ("tomé 20 de la caja", "retiro_personal", 20, E, None),
    ("saqué 60 para la casa por yape", "retiro_personal", 60, B, None),
    ("saqué 250", "retiro_personal", 250, E, None),
    # pedidos a crédito
    ("pedí 2 400 a Andina para el 30", "compra", 2400, CR, A, None),
    ("pedí 2400 a andina para el 30 de noviembre", "compra", 2400, CR, A, "2026-11-30"),
    ("hice un pedido de 800 a Andina", "compra", 800, CR, A, "2026-11-29"),
    ("pedí 500 a Gloria para el 5", "compra", 500, CR, "Gloria", "2026-12-05"),
    ("Andina me fió 1 200 en bebidas", "compra", 1200, CR, A),
    ("encargué 300 de gaseosas a Andina para el viernes", "compra", 300, CR, A, "2026-11-20"),
    ("pedí mercadería a Andina por 1 500 a crédito", "compra", 1500, CR, A),
    ("compré a crédito 600 a Andina", "compra", 600, CR, A),
    ("le hice un pedido a Andina de 2 mil para el 15 de diciembre", "compra", 2000, CR, A, "2026-12-15"),
    ("pedí 1 800 a Andina, lo pago en 15 días", "compra", 1800, CR, A, "2026-11-29"),
    # compras al contado
    ("compré 20 panes en la panadería", "compra", 4.4, E, None),
    ("compré mercadería por 300 en el mercado", "compra", 300, E, None),
    ("fui al mercado y gasté 250", "compra", 250, E, None),
    ("compré fideos y arroz por 120", "compra", 120, E, None),
    ("repuse gaseosas por 180", "compra", 180, E, None),
    ("compré 2 cajas de leche a 100", "compra", 100, E, None),
    # gastos del negocio
    ("pagué la luz, 80", "gasto_negocio", 80, E, None),
    ("pagué el agua 45", "gasto_negocio", 45, E, None),
    ("pagué 8 de mototaxi", "gasto_negocio", 8, E, None),
    ("pagué el alquiler del local, 350", "gasto_negocio", 350, E, None),
    ("gasté 20 en bolsas", "gasto_negocio", 20, E, None),
    ("pagué 50 de internet", "gasto_negocio", 50, E, None),
    ("pagué el flete 30", "gasto_negocio", 30, E, None),
    ("pagué 15 de recarga del celular", "gasto_negocio", 15, E, None),
    ("pagué al técnico de la congeladora 70", "gasto_negocio", 70, E, None),
    ("pagué la luz 80 con yape", "gasto_negocio", 80, B, None),
    ("compré 2 balones de gas, 96 soles", "gasto_negocio", 96, E, None),
    ("saqué 300 para pagar la luz", "gasto_negocio", 300, E, None),
    # préstamos
    ("me prestaron 1 000, pago 40 diarios", "prestamo_recibido", 1000, E, None),
    ("me prestó mi hermano 500", "prestamo_recibido", 500, E, "Mi hermano"),
    ("saqué un préstamo de 2 000 en la caja", "prestamo_recibido", 2000, E, "Caja"),
    ("me dieron un préstamo de 1500 del gota a gota, devuelvo 1800", "prestamo_recibido", 1500, E,
     "Prestamista (gota a gota)"),
    ("pagué la cuota del préstamo, 40", "pago_prestamo", 40, E, None),
    ("le pagué 40 al prestamista", "pago_prestamo", 40, E, "Prestamista (gota a gota)"),
    ("pagué 200 de la cuota al banco", "pago_prestamo", 200, E, "Banco"),
    # pagos a proveedor
    ("le pagué 1 200 a Andina", "pago_proveedor", 1200, E, A),
    ("pagué 2400 a la distribuidora Andina", "pago_proveedor", 2400, E, A),
    ("le aboné 500 a Andina por yape", "pago_proveedor", 500, B, A),
    ("cancelé el pedido de Andina, 2 400", "pago_proveedor", 2400, E, A),
    ("deposité 500 a Andina", "pago_proveedor", 500, T_, A),
    # impuestos
    ("pagué mi RUS, 20 soles", "pago_impuesto", 20, E, None),
    ("pagué el RUS de octubre 20", "pago_impuesto", 20, E, None),
    ("pagué 20 a la sunat", "pago_impuesto", 20, E, None),
    ("pagué impuestos 20 soles", "pago_impuesto", 20, E, None),
    # otros ingresos
    ("me regalaron 50 soles", "otro_ingreso", 50, E, None),
    ("recibí 100 por alquilar la congeladora", "otro_ingreso", 100, E, None),
    # gastos de la casa (alcance) y frases que no se registran
    ("pagué el colegio 150", "retiro_personal", 150, E, None),
    ("pagué la pensión de mi hija, 300", "retiro_personal", 300, E, None),
    ("pagué el colegio de mi hijo", None, None, None, None),
    ("compré medicinas para mi mamá", None, None, None, None),
    ("hola", None, None, None, None),
    ("¿cómo va mi caja?", None, None, None, None),
    ("gracias", None, None, None, None),
    ("buenos días, don Pedro por aquí", None, None, None, None),
]  # fmt: skip

# Frases NUEVAS escritas después de ajustar las reglas y que NO se usaron para ajustarlas: miden mejor cómo le va al
# fallback con formas de decir que no vio. Se reportan aparte (la regresión de pytest usa solo CASOS).
HOLDOUT: list[tuple] = [
    ("hoy vendí 5 cervezas y 3 gaseosas", "venta", 40, E, None),
    ("despaché 4 aguas", "venta", 6, E, None),
    ("la vecina Rosa se llevó 2 panes fiados", "venta", 0.6, CR, R),
    ("don Luis me dejó a deber 18 soles", "venta", 18, CR, L),
    ("Carmencita me pagó 40", "cobro_fiado", 40, E, C),
    ("saqué 70 lucas para el mercado de la casa", "retiro_personal", 70, E, None),
    ("pagué el pasaje del mototaxi, 6 soles", "gasto_negocio", 6, E, None),
    ("pagué 120 de alquiler", "gasto_negocio", 120, E, None),
    ("le debo 600 a Andina por un pedido para el 28", "compra", 600, CR, A, None),
    ("me fiaron 900 en Andina hasta el 30 de noviembre", "compra", 900, CR, A, "2026-11-30"),
    ("vendí 8 soles de caramelos", "venta", 8, E, None),
    ("cobré 30 a la señora Carmen", "cobro_fiado", 30, E, C),
    ("Rosa ya me pagó lo de las gaseosas", "cobro_fiado", 95, E, R),
    ("pagué 20 soles del nuevo rus", "pago_impuesto", 20, E, None),
    ("le di 40 al prestamista de la cuota", "pago_prestamo", 40, E, "Prestamista (gota a gota)"),
    ("mi tío me prestó 300", "prestamo_recibido", 300, E, "Mi tio"),
    ("gasté 12 en la balanza nueva", "gasto_negocio", 12, E, None),
    ("vendí 2 gaseosas de 3 litros", "venta", 22, E, None),
    ("pagué la planilla de luz 180", "gasto_negocio", 180, E, None),
    ("compré 50 de pan para vender", "compra", 50, E, None),
    ("un cliente me pagó con yape 26 por 4 cervezas", "venta", 26, B, None),
    ("retiré 100 para pagar la luz de mi casa", "retiro_personal", 100, E, None),
    ("aboné 1000 a Andina", "pago_proveedor", 1000, E, A),
    ("vendí al por mayor 300 soles de abarrotes", "venta", 300, E, None),
    ("qué tal", None, None, None, None),
]  # fmt: skip

CAMPOS = ("tipo", "monto", "metodo_pago", "contraparte", "fecha_vencimiento")


def _esperado(caso: tuple) -> dict:
    texto, tipo, monto, metodo, contraparte, *resto = caso
    esperado = {"tipo": tipo, "monto": None if monto is None else Decimal(str(monto)).quantize(Decimal("0.01")),
                "metodo_pago": metodo, "contraparte": contraparte}  # fmt: skip
    if resto:
        esperado["fecha_vencimiento"] = resto[0]
    return esperado


def _obtenido(texto: str, catalogo, usar_llm: bool) -> tuple[dict, bool]:
    from app.services.ingesta import extractor

    try:
        e = extractor.extraer(texto, empresa_id="EMP-0001", catalogo=catalogo, usar_llm=usar_llm)
    except NoInterpretable:
        return {"tipo": None, "monto": None, "metodo_pago": None, "contraparte": None, "fecha_vencimiento": None}, False
    mov = e.movimiento
    monto = mov.get("monto")
    venc = mov.get("fecha_vencimiento")
    return {"tipo": mov["tipo"], "monto": None if monto is None else Decimal(str(monto)).quantize(Decimal("0.01")),
            "metodo_pago": mov["metodo_pago"], "contraparte": mov.get("contraparte"),
            "fecha_vencimiento": venc.isoformat() if hasattr(venc, "isoformat") else venc}, e.fallback_usado  # fmt: skip


def evaluar(usar_llm: bool = False, limite: int | None = None, conjunto: str = "principal") -> dict:
    from app.services.ingesta import catalogo as cat_mod

    catalogo = cat_mod.desde_seed()
    base = HOLDOUT if conjunto == "holdout" else CASOS
    casos = base[:limite] if limite else base
    aciertos = {c: 0 for c in CAMPOS}
    evaluados = {c: 0 for c in CAMPOS}
    errores, con_correccion, fallbacks = [], 0, 0
    for caso in casos:
        esperado = _esperado(caso)
        obtenido, fallback = _obtenido(caso[0], catalogo, usar_llm)
        fallbacks += fallback
        mal = []
        for campo, valor in esperado.items():
            if esperado["tipo"] is None and campo != "tipo":
                continue
            evaluados[campo] += 1
            if obtenido.get(campo) == valor:
                aciertos[campo] += 1
            else:
                mal.append({"campo": campo, "esperado": str(valor), "obtenido": str(obtenido.get(campo))})
        if mal:
            con_correccion += 1
            errores.append({"texto": caso[0], "errores": mal})
    exactitud = {c: round(aciertos[c] / evaluados[c], 3) for c in CAMPOS if evaluados[c]}
    total = sum(aciertos.values()) / sum(evaluados.values())
    return {
        "ruta": "llm" if usar_llm else "reglas",
        "conjunto": conjunto,
        "n": len(casos),
        "exactitud_por_campo": exactitud,
        "exactitud_total": round(total, 3),
        "frases_exactas": round(1 - con_correccion / len(casos), 3),
        "pct_requiere_correccion": round(100 * con_correccion / len(casos), 1),
        "fallbacks": fallbacks,
        "errores": errores,
    }


def _imprimir(r: dict) -> None:
    print(f"[{r['conjunto']}] Ruta {r['ruta']} · {r['n']} frases · exactitud total por campo {r['exactitud_total']:.1%} · "
          f"frases 100 % correctas {r['frases_exactas']:.1%} · requieren corrección {r['pct_requiere_correccion']} %"
          + (f" · fallbacks {r['fallbacks']}" if r["ruta"] == "llm" else ""))  # fmt: skip
    for campo, v in r["exactitud_por_campo"].items():
        print(f"  {campo:18} {v:.1%}")
    for e in r["errores"]:
        detalle = "; ".join(f"{x['campo']}: esperado {x['esperado']}, obtuvo {x['obtenido']}" for x in e["errores"])
        print(f"  ✗ {e['texto']!r}: {detalle}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exactitud por campo del extractor de CajaClara.")
    parser.add_argument("--llm", action="store_true", help="evaluar también la ruta LLM (llama a OpenRouter)")
    parser.add_argument("--limite", type=int, default=None, help="evaluar solo las primeras N frases")
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    args = parser.parse_args(argv)

    resultados = [evaluar(usar_llm=False, limite=args.limite, conjunto=c) for c in ("principal", "holdout")]
    if args.llm:
        from app.core.config import settings

        if not settings.llm_configurado:
            print("--llm pide OPENROUTER_API_KEY en backend/.env", file=sys.stderr)
            return 2
        resultados += [evaluar(usar_llm=True, limite=args.limite, conjunto=c) for c in ("principal", "holdout")]
    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2, default=str))
    else:
        for r in resultados:
            _imprimir(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
