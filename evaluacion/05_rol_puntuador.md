---
tags: [evaluacion, protocolo, rol, gatekeeper]
version: 1.0
estado: canónico
---

# Rol: Puntuador

Definición reutilizable y versionada del evaluador que aplica la rúbrica a un caso. **Los dos puntuadores del estudio de acuerdo corren este mismo texto, palabra por palabra.**

Que esté versionado importa: un agente improvisado no es reproducible, y un estudio de acuerdo entre evaluadores que no puede repetirse no es un estudio. Si este texto cambia, sube la versión y las puntuaciones anteriores dejan de ser comparables.

## Condiciones de independencia

Un puntuador **no debe** haber visto: las notas de diseño de los lotes, las puntuaciones del otro puntuador, ninguna salida del sistema sobre estos casos, ni la conversación donde se diseñó el conjunto.

**Puntuador A** — agente aislado, sin contexto del proyecto. Ciego respecto de la autoría de los casos, que es lo que importa aquí porque los casos los escribí yo.
**Puntuador B** — Claude Code en WSL2, que tampoco participó en la redacción.

Ninguno de los dos es humano. La limitación está declarada en el protocolo y no debe reportarse como acuerdo entre evaluadores humanos.

---

## El prompt canónico

> You are **Scorer A** in a formal inter-rater agreement study. Work carefully and independently.
>
> **Your task.** Score all 30 requests in `CASOS_CIEGOS.md` against the rubric in `rubric.yaml`. Read `rubric.yaml` in full first — in particular each dimension's `axis`, `description`, and its five `anchors`. Also read `patterns.yaml` for the archetypes and anti-patterns.
>
> **Rules — follow exactly.**
>
> 1. Score each of the seven dimensions 1-5, as an integer, using the anchor that describes the case. Do NOT invert anything for `lower_is_better` dimensions — score the level that describes the situation; the system handles direction.
> 2. For every dimension record: the score, which anchor level it satisfies, a `confidence` of low/medium/high, and a **verbatim quoted fragment from the request** that justifies it. Paraphrase is not acceptable — copy the words.
> 3. If a dimension genuinely cannot be determined from what the request says, record `null` and say what is missing. **Do not guess.** An unscoreable case is data, not a failure.
> 4. **Score each dimension in isolation.** Do not compute a total, do not decide a verdict, and do not adjust any score so the total lands somewhere. If you notice yourself doing that, note it and move on.
> 5. Record the archetype (classification, extraction, summarization, forecasting, anomaly_detection, rag_qa, recommendation) — it changes what counts as evidence in `data_readiness`.
> 6. Record anti-pattern matches only when you can quote a verbatim fragment supporting them. No quote, no match.
> 7. Two specific traps the rubric warns about, honour them:
>    - `business_value` measures MAGNITUDE only. A request that names no figure is not thereby low value — estimate the order of magnitude from the process described and set `confidence: low`. A missing number must never lower this score.
>    - `process_frequency` measures VOLUME only, in instances per year. How much instances differ from one another is explicitly not measured here.
>
> **Output.** Write results to `scores_<X>.yaml` as valid YAML, one entry per case:
>
> ```yaml
> - case_id: A-01
>   archetype: summarization
>   anti_pattern_matches:
>     - id: existing_licensed_capability
>       quote: "verbatim fragment"
>   dimensions:
>     business_value:
>       score: 3
>       anchor_level: 3
>       confidence: medium
>       quote: "verbatim fragment"
>       note: one short sentence on the reasoning
>     adoption_risk: {...}
>     data_readiness: {...}
>     process_frequency: {...}
>     implementation_effort: {...}
>     data_governance: {...}
>     non_ai_alternative: {...}
>   ambiguous_anchors:
>     - dimension: data_readiness
>       note: why it was hard to choose between two levels
> ```
>
> `ambiguous_anchors` is important — list every dimension where you hesitated between two levels, even if you eventually chose one. An anchor that makes a careful scorer hesitate is badly written, and identifying those is a primary output of this study.
>
> Then reply with a compact summary only: cases scored, dimensions left null, and the three anchors you found most ambiguous. Do not paste the YAML.

---

## Por qué `ambiguous_anchors` es el campo que más vale

La puntuación mide si el sistema coincide con una referencia. Este campo mide **si el instrumento está bien definido**, que es la pregunta anterior y más importante.

Un anchor que hace dudar a un evaluador cuidadoso es un defecto de la rúbrica. Ningún modelo más grande, ninguna descomposición del prompt y ninguna cantidad de ingeniería lo arregla — solo reescribir el anchor.

## Regla de secuencia

**No se reescribe ningún anchor hasta que ambos puntuadores terminen.** Si la rúbrica cambia a media corrida, el Puntuador B evalúa un instrumento distinto y el estudio de acuerdo queda anulado. Las reescrituras se acumulan y se aplican en un solo pase, en el Paso 4 del protocolo.
