---
tags: [evaluacion, puntuacion, gatekeeper]
puntuador: Arturo Magdiel (humano, experto de dominio en Ventas)
estado: sin llenar
---

# Hoja de puntuación — los 5 casos de Ventas

**Para Arturo. Puntuador humano independiente.**

Los casos son **A-05, A-10, B-06, B-11, B-15**, en `01_lote_A_requests.md` y `02_lote_B_requests.md`.

---

## Reglas del ejercicio

**No mires ninguna puntuación mía ni de Code.** No existen todavía; yo puntúo después de que tú termines. Si lo hago antes, deja de ser independiente y el ejercicio no mide nada.

**No corras el sistema sobre estos casos antes de puntuar.** Ver una predicción ancla el juicio.

Por cada dimensión y cada caso registras tres cosas:

1. **El número, del 1 al 5.**
2. **El nivel de anchor que satisface** — cuál de los cinco textos describe la situación del caso.
3. **La frase del request en la que te basaste.** Copiada, no parafraseada.

Sin la frase, la puntuación no cuenta. Es lo que permite después distinguir "discrepamos de criterio" de "leímos cosas distintas".

**Si genuinamente no puedes determinar una dimensión con lo que dice el request, escribe `desconocido`.** No adivines. Que un caso no se pueda puntuar es un dato, no una falla tuya.

**Puntúa cada dimensión por separado, sin pensar en el veredicto.** Si te descubres ajustando un número para que el total dé lo que crees que debería dar, ese es exactamente el sesgo que el ejercicio existe para detectar — anótalo y sigue.

Los anchors están **en inglés textual, sin traducir**, a propósito: Code va a puntuar contra este mismo texto, y una traducción metería una diferencia que no es de criterio.

---

## Escala y dirección

Todas las dimensiones son enteros del 1 al 5.

En cuatro de ellas **un número más alto es peor** (`adoption_risk`, `implementation_effort`, `data_governance`, `non_ai_alternative`). No inviertas nada tú — puntúa el nivel que describe la situación y el sistema hace la conversión.

---

## Las siete dimensiones

### 1 · `business_value` — peso 0.22 — más alto es mejor

**Eje:** MAGNITUD del beneficio, anualizada. Nada más.

Juzga el tamaño del premio, no la probabilidad de ganarlo. Que nadie haya cuantificado el beneficio es cuestión de *confianza*, no de tamaño — si el request no da cifra, estima el orden de magnitud a partir del proceso descrito y marca confianza baja. **Una cifra faltante nunca debe bajar este número.**

```
1  Under about 200 person-hours a year reclaimed, under about 10k USD avoided,
   or fewer than about 50 cases or tickets a year affected.
2  About 200-1,000 person-hours a year (roughly 0.1-0.5 FTE), about 10k-50k USD,
   or about 50-500 cases or tickets a year.
3  About 1,000-5,000 person-hours a year (roughly 0.5-2.5 FTE), about 50k-250k USD,
   or about 500-5,000 cases or tickets a year.
4  About 5,000-20,000 person-hours a year (roughly 2.5-10 FTE), about 250k-1M USD,
   about 5,000-50,000 cases or tickets a year, or a cycle-time reduction on a
   process the business already reports on.
5  More than about 20,000 person-hours a year (10+ FTE), more than about 1M USD,
   tens of thousands of cases a year, or direct influence on revenue or on a
   regulatory obligation the company already reports.
```

### 2 · `adoption_risk` — peso 0.17 — **más alto es peor**

**Eje:** Probabilidad ORGANIZACIONAL de que los usuarios no cambien su forma de trabajar. No riesgo técnico, no riesgo de entrega.

```
1  The intended users asked for this themselves. It sits inside a workflow they
   already use daily, a named owner has committed to driving adoption, and a
   previous tool built for these same users was adopted and is still in use.
2  Users were consulted and are supportive. The change fits an existing workflow
   with minor adjustment, and an owner has committed to driving adoption.
3  Users were consulted but did not shape it. It adds a new step to an existing
   workflow, and adoption depends on a manager asking people to use it.
4  The intended users were not consulted, or the change requires them to adopt a
   new tool or a new workflow, or a previous tool built for these same users was
   quietly abandoned.
5  The intended users were not consulted and have not been told. It replaces or
   overrides a way of working they chose themselves, no owner has committed to
   driving adoption, and a previous tool for these users was rejected or abandoned.
```

### 3 · `data_readiness` — peso 0.15 — más alto es mejor

**Eje:** Si los datos EXISTEN, son OBTENIBLES por este equipo, y si puedes DISTINGUIR UNA BUENA SALIDA DE UNA MALA. El permiso para usar los datos es otra dimensión.

El constructo es *"¿puedes evaluarlo?"*, no *"¿tienes labels?"*. Qué cuenta como evidencia depende del arquetipo:

- **Predictivos** — clasificación, extracción, forecasting, detección de anomalías, recomendación → labels o una variable de resultado inequívoca.
- **Generativos** — resumen, RAG-QA, y redacción → un conjunto de referencia curado con criterios de calidad acordados.

```
1  The data does not exist in retrievable form. It is in people's heads, in
   undigitized paper, or it would have to be collected from scratch before any
   work could begin.
2  Data exists but is spread across systems nobody has joined, or is locked
   inside attachments and free text with no access path. Obtaining it is a
   project with its own budget.
3  Data exists in one or two systems and a plausible access path exists, but its
   quality has not been checked on real records, or there is no agreed way yet to
   tell whether an output is good.
4  Data is centralized, its quality has been checked on a real sample, and a named
   owner can grant access. A partial way to judge output quality exists: for a
   predictive archetype, some labelled examples or a usable proxy for the outcome;
   for a generative archetype, a handful of reference outputs or draft quality
   criteria.
5  Sufficient clean, accessible history with verified quality and an owner who can
   grant access this quarter without an exception, plus a settled way to judge an
   output: for a predictive archetype, labels or an unambiguous outcome variable;
   for a generative archetype, a curated reference set with agreed quality criteria
   and someone qualified to apply them.
```

### 4 · `process_frequency` — peso 0.13 — más alto es mejor

**Eje:** VOLUMEN del proceso objetivo, en instancias por año. Nada más. Qué tanto difiere cada instancia de la anterior **no se mide aquí**.

```
1  Fewer than about a dozen instances a year.
2  About 12 to 100 instances a year — roughly monthly.
3  About 100 to 1,000 instances a year — roughly weekly.
4  About 1,000 to 10,000 instances a year — roughly daily.
5  More than about 10,000 instances a year — many times an hour, or continuous.
```

### 5 · `implementation_effort` — peso 0.13 — **más alto es peor**

**Eje:** COSTO TOTAL para llegar a producción y mantenerse ahí: construcción, integración, y la gestión del cambio necesaria para que la gente lo use. Puntúa el camino completo, no el prototipo.

```
1  Days to two weeks. Configuration of a platform already licensed, or one
   integration against an API that already exists. No new infrastructure, one
   team affected.
2  Two to six weeks. A couple of integrations, minor data plumbing, one existing
   process to adjust, no new vendor or licence needed.
3  About one quarter. A new data pipeline plus a UI or workflow change, two or
   three teams to coordinate, or a new licence to procure.
4  Two or more quarters. Several system integrations, a new platform component to
   stand up, or retraining how a whole team works.
5  A year or more, or blocked on something outside this team's control: replacing
   a system of record, a vendor negotiation, an organisational change, or a
   labelling effort measured in person-months.
```

### 6 · `data_governance` — peso 0.10 — **más alto es peor**

**Eje:** Si los datos PUEDEN SER PROCESADOS por la plataforma de modelo disponible, y a qué costo en controles. No es la calidad del dato.

> El nivel 5 es compuerta: si el dato no puede procesarse legal o contractualmente, **ninguna cantidad de valor de negocio lo compensa**.

```
1  Public or internal-unclassified data with no personal data. Processing by the
   approved model platform is already covered, and an access path exists that
   needs no exception.
2  Internal data with limited personal fields such as names and work contact
   details. Covered by existing processing agreements; access is granted through
   a standard request.
3  Confidential business data, or personal data beyond basic identifiers.
   Processing is permitted but requires a documented assessment, and access needs
   the data owner's approval.
4  Restricted data — regulated personal data, financial records, HR or health
   information. Processing externally requires a specific contractual clause or an
   impact assessment that is not yet in place, and access requires a formal
   exception.
5  The data may not be processed by the available model platform at all: a
   prohibited classification, a contractual bar, a residency restriction, or a
   regulator or works council approval that has not been obtained. No compliant
   access path exists today.
```

### 7 · `non_ai_alternative` — peso 0.10 — **más alto es peor**

**Eje:** Qué tan COMPLETAMENTE resolvería el mismo problema una solución sin IA — una regla, una consulta, un reporte, un arreglo de proceso, o una capacidad que la empresa ya licencia.

> Un 4 o un 5 dispara compuerta y el veredicto se vuelve `Not-AI` sin importar el resto.

```
1  No deterministic alternative exists. The input is unstructured or genuinely
   ambiguous, and rule-based attempts have been tried and are known to fail.
2  A rules-based approach handles a minority of cases; the remaining volume is
   judgement-heavy in a way rules have not captured.
3  Rules, a query, or a report would cover roughly half the cases. An agent would
   extend coverage rather than create the capability.
4  A well-written query, a report, a process change, or configuration of a tool the
   company already owns would solve most of it. An agent would mostly add
   convenience.
5  A deterministic rule, a lookup, a form field, an upstream process fix, or an
   already-licensed capability solves it completely — more cheaply, more
   predictably, and with less to maintain.
```

---

## Además de las siete dimensiones

Por cada caso, anota también:

**Arquetipo** — cuál de los siete describe mejor lo que se pide: `classification`, `extraction`, `summarization`, `forecasting`, `anomaly_detection`, `rag_qa`, `recommendation`. Importa porque cambia qué cuenta como evidencia en `data_readiness`.

**¿Aplica algún anti-patrón?** Si crees que sí, escribe cuál y **la frase textual del request** que lo sustenta. Si no puedes citar una frase, no lo marques — esa es la misma regla que el sistema se aplica a sí mismo.

Los cuatro que bloquean duro: una capacidad ya licenciada lo cubre; una regla determinista basta; el request real es un reporte o tablero; es automatización determinista con etiqueta de IA. Los tres advisory: chatbot sin trabajo definido; los datos todavía no existen; solución primero sin problema medible.

---

## Plantilla

Copia este bloque cinco veces, uno por caso. **No pongas veredicto** — eso lo calcula el sistema.

```
CASO: ___________  (A-05 / A-10 / B-06 / B-11 / B-15)
Arquetipo: ___________
Anti-patrón (si aplica): ___________
  frase textual: "..."

business_value        : _   nivel _   confianza: baja/media/alta
  frase: "..."
adoption_risk         : _   nivel _   confianza: baja/media/alta
  frase: "..."
data_readiness        : _   nivel _   confianza: baja/media/alta
  frase: "..."
process_frequency     : _   nivel _   confianza: baja/media/alta
  frase: "..."
implementation_effort : _   nivel _   confianza: baja/media/alta
  frase: "..."
data_governance       : _   nivel _   confianza: baja/media/alta
  frase: "..."
non_ai_alternative    : _   nivel _   confianza: baja/media/alta
  frase: "..."

Dudas o anchors que se sintieron ambiguos:
```

**Ese último campo es el más valioso de la hoja.** Si un anchor te obligó a dudar entre dos niveles, anótalo aunque hayas elegido uno. Un anchor que hace dudar a un experto de dominio está mal escrito, y eso es un defecto del instrumento que ninguna mejora al modelo arregla.

---

## Qué pasa después

Cuando termines me pasas la hoja llena. Entonces yo puntúo los 30 —incluidos estos cinco— sin ver la tuya, y le paso los mismos 30 a Code para que puntúe por separado. Con eso salen tres cosas:

- **Acuerdo humano contra modelo** en los cinco casos donde tienes expertise de dominio. Es lo que hoy el paper declara como su limitación más seria.
- **Acuerdo modelo contra modelo** en los treinta.
- **Qué dimensión concentra el desacuerdo** — el hallazgo que vale más que cualquiera de los dos números.
