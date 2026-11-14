# CajaClara — Sistema de diseño (aplicado)

Fuente: `frontend/patrones ux ui.pdf` (patrones de Revolut adaptados) + decisiones del equipo del 14/11.
Tokens en `frontend/src/index.css`. Las pantallas usan siempre los tokens, nunca hex sueltos.

## Principios visuales

- **Plana, sin sombras.** La profundidad sale del contraste entre fondo (`--bg`) y tarjetas blancas con borde suave (`--border`).
- **Pocos colores, una acción clara.** Un solo botón primario por tarjeta. Los colores de estado solo comunican estado.
- **Botones en píldora** (`--radius-pill`), tarjetas de 20 px (`--radius-lg`), elementos pequeños 12 px. Hover = opacidad 0.85.
- **Espaciado base 8 px** (4, 8, 12, 16, 24, 32, 40, 48).
- **Toques de 44 px o más**, contraste alto para usar a pleno sol.
- Propia identidad: no se usa logo, nombre, tipografía ni valores oficiales de ningún banco.

## Paleta

| Rol | Token | Hex | Uso |
|---|---|---|---|
| Base | `--title` | `#0B2447` | Títulos, cifras clave |
| Acción | `--brand` | `#1464A5` | Botón principal, enlaces, línea del forecast |
| Acción suave | `--brand-soft` | `#E3EEF9` | Tarjetas informativas, chip/opción elegida |
| Positivo | `--ok` / `--ok-bg` | `#096B67` / `#D3F2F0` | "Te alcanza", metas, montos a favor |
| Alerta | `--danger` / `--danger-bg` | `#B5450B` / `#FCE9DF` | Faltante de caja, días en riesgo |
| Atención | `--warning` / `--warning-bg` | `#6F4A00` / `#FFF2CC` | "Justo", por vencer |
| Fondo | `--bg` | `#F4F6F9` | Fondo general |
| Borde | `--border` | `#D5DCE5` | Bordes y divisores |
| Texto | `--text` / `--text-muted` | `#13202F` / `#4A5868` | Cuerpo / etiquetas, fechas, notas |

Naranja vs. aqua para alerta vs. éxito: se distinguen también en claridad (daltonismo).
El violeta "Casa" de la propuesta **no se usa**: la app ya no muestra plata de la casa.

## Tipografía

- Títulos y cifras: Bricolage Grotesque 600 (`--font-display`, `--display-weight`). Cifras con `.num` (tabulares).
- Texto: Inter 400/600, 16 px base.

## Contenido para una persona poco digital

Pedro piensa en soles, días y nombres. Por eso:

- **No mostrar porcentajes ni probabilidades.** En vez de "74% probable" → "Es muy probable" o nada. En vez de "▼ 6%" → "S/ 565 menos que el mes pasado".
- **No mostrar métricas técnicas** (error del modelo, cobertura, pesos del score, nombre/versión del modelo). La trazabilidad (`meta`) existe en la API y se ve solo con *Demo → Ver detalles técnicos*.
- La explicabilidad se da en palabras: "¿De dónde sale este número?" → de dónde sale, lo que no sabe, y "Es un cálculo aproximado".
- Sin "plata de la casa" en la interfaz: se habla solo de la caja del negocio.

## Responsive

| Ancho | Navegación | Contenido |
|---|---|---|
| < 768 px | Barra inferior (oculta en el chat) | 1 columna, gutter 16 px |
| 768–1099 px | Riel lateral con íconos | hasta 760 px, 2 columnas donde ayuda, gutter 24 px |
| ≥ 1100 px | Barra lateral con marca | hasta 1120 px, dashboard en grilla, gutter 32 px |

El contenido de cada página se centra con `max-width: var(--content-max)`.
