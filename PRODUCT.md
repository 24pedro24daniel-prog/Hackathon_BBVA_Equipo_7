# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (mobile-first), plus a conversational surface: a simulated WhatsApp chat (Twilio sandbox or our own chat UI) where most data entry happens.

## Users
**Primary: the bodeguero / informal micro-business owner ("Pedro").** A natural person running a neighborhood store (bodega) in Peru, not banked as a business: no RUC, no business account, no financial records. Sells and buys stock every day, mostly in cash. Keeps sales and *fiados* (store credit to neighbors) in a paper notebook or from memory, and mixes household money with the shop's ("caja única").

What this means for design:
- Low financial literacy and little patience for forms. Comfortable with WhatsApp, voice notes and photos; not with spreadsheets or banking apps.
- Uses the phone standing behind the counter, one-handed, in 10–60 second bursts between customers. Often in bright light, sometimes on a low-end Android with a small screen and slow data.
- Distrusts formality and banks, and is used to informal lenders. Trust must be earned by being right and transparent, not by looking "corporate".
- Thinks in soles, days and names ("Don Luis", "Andina", "el 30"), not in categories, percentages or accounting terms.

**Secondary (roadmap only):** a bank business advisor who, with Pedro's explicit consent, could read his ordered history to evaluate a working-capital loan faster. Not designed for in the MVP.

## Product Purpose
**CajaClara** is a cash-flow manager for unbanked bodegas and small businesses. It helps Pedro order his cash flow, see shortfalls coming before they happen, and build healthy money habits, so that over time he builds the history he needs to reach formal credit instead of informal "gota a gota" loans.

The problem it breaks: *no le alcanza → pide prestado → paga cuotas diarias con la venta del día → vuelve a no alcanzarle.*

Core jobs, in priority order for the MVP demo:
1. **Register without changing his routine** (F1): voice or text in WhatsApp ("vendí dos cervezas", "saqué 50 para la casa", "pedí 2 400 a Andina para el 30"); photos of the fiado notebook. The bot confirms what it understood and offers ✏️ Corregir.
2. **Know where he stands** (F2): business cash (separate from home money), income and expenses this month, approximate profit, personal withdrawals vs. a fixed salary, money owed to him (fiados), money he owes (suppliers, taxes).
3. **See the next 30 days** (F3): projected daily balance with a pessimistic / expected / optimistic band, minimum operating balance, days at risk highlighted, and **"disponible para gastar"** ("Hoy puedes sacar hasta S/ 120 para la casa sin arriesgar el pago del 30/11").
4. **Control what's owed** (F4): fiados by age and risk, one-tap friendly reminder to a neighbor; supplier debts and taxes by due date; a check *before* placing a supplier order.
5. **Get warned in time** (F6): proactive alerts, at most 2 per day, each one insight + one reason + one button.
6. **Ask and simulate** (F7): an assistant in the same chat that explains numbers and simulates scenarios ("¿y si pago a Andina en 2 partes?"). It never calculates figures itself.
7. **Track progress** (F8): a 0–100 cash-health score broken into simple sub-indicators, with goals (Organizar → Estabilizar → Proteger → Crecer) and streaks.

Simplified for the demo: notebook photos, taxes via buttons, assistant with 3–4 intents, score with 3 sub-indicators, 2 analysis charts (F5).

Success for Pedro: he stops running out of cash, understands his business, and leaves the informal-loan cycle. Measurable MVP targets live in `context.md` §3.

## Positioning
CajaClara is a **door in**, not a bank app. Existing business banking tools see only what flows through bank channels (POS, QR, accounts) and assume the user already has a RUC and a business account. CajaClara serves the person before that point and captures what the bank can't see: cash sales, fiados, supplier credit and personal withdrawals, entered through WhatsApp.

Its edge is **anticipation, not bookkeeping**: it tells Pedro what will happen on the 30th and what he can do about it today, in his own words.

It must not present itself as a BBVA product: no BBVA name or logo in the UI. Team decision (14/11, hackathon): the UI uses the BBVA 2025 colour palette (Electric #001391, Midnight #070E46) and banking-app interface patterns (Nu, Monzo, SoFi) so it reads as a natural step towards formal banking; typography uses free look-alikes, not BBVA fonts. Bank products may only be mentioned in the pitch as the user's natural next step (roadmap).

## Operating Context
- Two surfaces that must feel like one product:
  - **Chat (primary input):** registering, confirming, alerts and questions. Short messages, buttons over free text, emoji used functionally (✅ ✏️), never decoratively.
  - **Dashboard (primary reading):** the home screen answers "¿cómo va mi caja?" at a glance; deeper views for forecast, fiados/payables, analysis and progress.
- Pedro rarely opens the dashboard on his own; alerts reach him in the chat. The dashboard must still make sense when opened cold, days later.
- Presented live at the BBVA Engineering Hackathon "AI Financial Life" (14–15 Nov 2026) through a scripted story (`context.md` §9): the S/ 2 340 home screen, a voice entry, the 30/11 shortfall of S/ 650 with its three causes, scenario simulation, informal-loan cost, and the score going up. The UI must carry that story on a projected screen as well as on a phone.
- Judging weights UX/product value (20%) and Responsible AI (10%); explainability is visible in the interface, not hidden in docs.

## Capabilities and Constraints
- **Language:** all UI copy in Spanish, Peruvian register, informal "tú". Plain words: *plata de la casa*, *fiado*, *te faltarían*, *te deben*. Avoid *liquidez*, *cuentas por cobrar*, *EBITDA* in user-facing copy.
- **Money format:** soles as `S/ 2 340` (space as thousands separator in copy, two decimals only where cents matter). Dates as `30/11` or "el martes", in America/Lima time.
- **Mobile-first:** design at ~360px wide first; tap targets ≥ 44px; key numbers readable at arm's length and in sunlight (high contrast). Larger screens adapt up, and the demo screen should read well when projected.
- **Performance:** assume slow networks and modest devices. Light pages, no heavy decorative media.
- **Frontend:** React + Vite in `frontend/`. Backend: FastAPI + pydantic (see `contract.md`, base `/api/v1`). Models run locally (faster-whisper, local LLM via Ollama).
- **Data:** synthetic data only. All people, businesses and amounts are fictional.
- **Every model output carries traceability** (`meta`: model, version, fallback used) and **every recommendation carries `fundamento`, `limites` and `confianza`**. The UI must have a place to show these.
- **States to design for:** loading while a voice note is transcribed; low-confidence extraction (bot re-asks); correction; LLM/Whisper unavailable (template fallback); empty first days with little history; "approximate" figures shown as a range.
- **Alert limits:** max 2 per day, quiet hours, and never a link that asks for credentials.
- **Out of scope for the product's voice:** investment, crypto or specific loan/bank recommendations; tax or legal opinion beyond general information; executing any real financial operation. The app never offers or grants credit.

## Evidence on Hand
Public, cited context (allowed in the pitch and in explanatory copy, always with source):
- More than 100,000 SMEs close each year in Peru; ~40% stop operating because they can't sustain cash flow (Cámara de Comercio de Lima, via Infobae, Aug 2025).
- Only 1 in 4 micro-businesses accesses formal credit, and missing financial information raises its cost (IPE, via Infobae, Mar 2026).
- Team conversations with bank business advisors: evaluating an unbanked business is manual (≈1 h visit + 1 day report). Primary source, qualitative.

Not on hand: real users, testimonials, usage metrics, partner endorsements or model results. Demo numbers come from the synthetic dataset and must be labeled as such. Never invent customers, figures, accuracy claims or BBVA endorsement.

## Product Principles
1. **Anticipate, don't just record.** The most important thing on any screen is what is about to happen to Pedro's cash and when. History supports the forecast, not the other way around.
2. **One insight, one reason, one action.** Every alert and card answers: what's happening, why, and what he can do with one tap. No dashboards of equal-weight numbers.
3. **Speak like a neighbor, not a bank.** Plain Spanish, names and dates instead of categories and periods. Teach concepts just in time (30–60 seconds), in context, only when needed.
4. **Every number shows where it comes from.** Figures are traceable to his own records; estimates show a range and a confidence level; nothing the assistant says is a number the engines didn't produce.
5. **He decides.** Recommendations are guidance and simulations with clear assumptions, never orders or promises. Always offer to correct, undo, or talk to a person.
6. **Zero friction input.** Registering must be as easy as sending a voice note. Confirm what was understood, make fixing it one tap, and never ask for data the system can infer.
7. **Separate home from business, visibly.** The split between *plata del negocio* and *plata de la casa* is the habit the product exists to build; the interface should always make it clear which is which.
8. **Encourage soberly.** Celebrate streaks and goals with a calm, adult tone. No confetti, no gamified cartoonishness, no shame or alarmism in warnings: urgent is clear, not scary.
9. **Independent and honest.** Its own identity, not a bank's. Synthetic data labeled as such; limits stated openly.
