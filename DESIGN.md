# CajaClara — Sistema de diseño (aplicado)

Versión 2 (14/11). Estructura tomada de apps bancarias de referencia (Nu, Monzo, SoFi) y color de la paleta BBVA 2025.
Tokens en `frontend/src/index.css`, primitivas en `frontend/src/components/ui/`. Las pantallas usan siempre los tokens, nunca hex sueltos.

## Qué tomamos de cada app

| App | Patrón | Dónde lo usamos |
|---|---|---|
| Monzo | Tarjeta de cuenta de color con el saldo; tarjeta "Actividad" blanca con filas; "Left to spend"; línea de saldo con proyección y valor final etiquetado | Inicio, 30 días |
| Nu | 90 % blanco/gris/navy; color de marca solo para la acción; círculos grises para íconos; alertas en tres partes (qué pasa, por qué, qué puedes hacer); recibo en filas etiqueta/valor | Inicio, Chat, Cuentas |
| SoFi | Etiqueta debajo del número; tarjeta de puntaje (número + calificación + frase de tendencia + barra recta con marcador); frase de estado en color ("Pacing high"); línea de meta punteada | Progreso, 30 días |

## Reglas

- **Fondo off-white, tarjetas blancas sin borde** con sombra suave (`--shadow`), radio 16. Un tema por tarjeta.
- **Una sola superficie de color en toda la app**: la tarjeta de cuenta Electric de Inicio. Además, el color de marca solo aparece en el botón principal, enlaces, pestaña activa, selección y la línea del gráfico.
- **Nada de tarjetas tintadas** (rojas, verdes, celestes) para alertas, resultados o selecciones. El estado es **texto de color + ícono** (`Status`, `Money tone`).
- **Sin botones duplicados**: ningún atajo que solo lleve a una pestaña que ya está en la barra. Máximo un botón principal por pantalla.
- **Montos** con `<Money>`: "S/" al 60 %, entero dominante, cifras tabulares. Entradas en verde con "+"; salidas en navy con "−" (no en rojo, salvo que sean un problema).
- **Filas** (`List` + `ListRow`): 64 px, círculo gris de 40 px con ícono o iniciales, título 16, línea secundaria 14 en slate, monto a la derecha, divisor inset.
- **Frases en vez de etiquetas**: títulos de sección en frase; prohibido rótulos en mayúsculas espaciadas, cifras en cajas de color, etiquetas con fondo, íconos decorativos, emoji como ícono.
- **Sub-pantallas**: botón circular "volver" + título centrado de 17 px. Pantallas de pestaña: título serif grande a la izquierda.
- Toques ≥ 44 px; botones principales 48 px.

## Paleta (BBVA 2025, tokens "Spherica")

| Rol | Token | Hex | Contraste |
|---|---|---|---|
| Acción / tarjeta de cuenta | `--brand` | `#001391` Electric | 14:1 con blanco |
| Títulos, texto, montos | `--title`, `--text` | `#070E46` Midnight | 18:1 sobre blanco |
| Texto secundario | `--text-muted` | `#46536D` Slate | 7.7:1 |
| Fondo | `--bg` | `#F7F8F8` | — |
| Superficie | `--surface` | `#FFFFFF` | — |
| Relleno gris (círculos, pistas) | `--surface-sunken` | `#EFF1F4` | — |
| Divisores | `--hairline` / `--border-strong` | `#E9ECEF` / `#CAD1D8` | decorativo |
| Light blue (solo relleno o texto sobre Electric) | `--accent` | `#85C8FF` | 7.8:1 sobre Electric |
| Positivo | `--ok` | `#024700` | AAA |
| Alerta | `--danger` | `#C30A0A` | 5.9:1 |
| Atención | `--warning` | `#906401` | 5.0:1 |

## Tipografía

- Interfaz y montos: **Libre Franklin** 400/500/600 (equivalente libre de Benton Sans).
- Títulos de pantalla y saludo: **Source Serif 4** 600 (equivalente libre de Tiempos Headline).
- Escala: monto principal 40–48 / título 26–30 / sección 18 / cuerpo 16 / nota 14.

## Contenido para una persona poco digital

Pedro piensa en soles, días y nombres. Por eso:

- **No mostrar porcentajes ni probabilidades.** En vez de "74% probable" → "Es muy probable" o nada. En vez de "▼ 6%" → "S/ 565 menos que el mes pasado".
- **No mostrar métricas técnicas** (error del modelo, cobertura, pesos del score, nombre/versión del modelo). La trazabilidad (`meta`) existe en la API y se ve solo con *Demo → Ver detalles técnicos*.
- La explicabilidad se da en palabras: "¿De dónde sale este número?" → de dónde sale, lo que no sabe, y "Es un cálculo aproximado".
- Sin "plata de la casa" en la interfaz: se habla solo de la caja del negocio.

## Responsive

| Ancho | Navegación | Contenido |
|---|---|---|
| < 768 px | Barra inferior; pestaña activa con cápsula celeste (oculta en el chat) | 1 columna, gutter 16 px |
| 768–1099 px | Riel lateral con íconos | hasta 760 px, gutter 24 px |
| ≥ 1100 px | Barra lateral con marca | hasta 1120 px, 2 columnas, gutter 32 px |
