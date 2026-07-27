---
tags: [evaluacion, hallazgos, rubrica, gatekeeper]
puntuador: A (agente aislado)
estado: registrado — NO aplicar correcciones hasta que B termine
---

# Hallazgos del Puntuador A

30 casos puntuados, 210 casillas de dimensión, **5 nulos** — todos en `process_frequency`, en casos donde el request no menciona volumen ni periodicidad en ninguna parte (A-03, A-10, A-11, B-11, B-14). Ninguna dimensión de `never_unknown` quedó sin puntuar.

**89 entradas de ambigüedad**, repartidas así:

| Dimensión | Ambigüedades | Peso |
|---|---|---|
| `non_ai_alternative` | 20 | 0.10 · **con compuerta** |
| `business_value` | 17 | 0.22 |
| `data_readiness` | 16 | 0.15 · **con compuerta** |
| `adoption_risk` | 11 | 0.17 |
| `implementation_effort` | 10 | 0.13 |
| `process_frequency` | 8 | 0.13 |
| `data_governance` | 7 | 0.10 · **con compuerta** |

**Las dos dimensiones con más ambigüedad son también las dos que más deciden**: `non_ai_alternative` porque dispara compuerta, y `business_value` porque carga el peso más alto. Eso no es casualidad estadística — son las que se aplican con más frecuencia y por tanto donde más se nota una definición floja.

---

## 1 · `business_value`: las denominaciones no son intercambiables

La rúbrica declara que horas-persona, moneda y casos son *"denominaciones alternativas de la misma magnitud"*. **No lo son.** Divergen sistemáticamente cuando el costo por instancia es bajo:

| Caso | Por horas | Por casos | Divergencia |
|---|---|---|---|
| A-08 reseteo de contraseñas | 3 (1,040 h/año) | 4 (15,600 tickets/año) | 1 nivel |
| B-02 categorización de quejas | 2 | 4 | 2 niveles |
| B-10 clasificación contable | 3 | 5 | 2 niveles |
| B-16 órdenes de trabajo | 1 | 3 | 2 niveles |

El evaluador tiene que elegir denominación, y la elección mueve el resultado hasta dos niveles en la dimensión de mayor peso. La rúbrica dice "usa la que el request soporte" sin decir qué hacer cuando soporta dos.

**Y hay algo peor en el nivel 5.** Sus cláusulas *"direct influence on revenue or on a regulatory obligation the company already reports"* se disparan en casos de magnitud trivial: **B-07** es un cruce trimestral de Excel cuyo beneficio declarado es cumplimiento de auditoría — lee como nivel 5 por esa cláusula y como nivel 1 por horas.

Eso es exactamente la violación que nombramos en la Fase 2.1 y creímos corregida: **un anchor que usa "o" para admitir un caso alterno introduce un segundo eje de medición.** El nivel 5 mide magnitud *y* importancia estratégica a la vez. Sobrevivió a la corrección anterior.

## 2 · `non_ai_alternative`: los niveles 3 y 4 miden la cobertura equivocada

Ambos están redactados como cobertura **de casos** — "roughly half", "most of it". Pero las alternativas sin IA reales suelen cubrir **una parte del problema en todos los casos**, no todos los aspectos en una parte de los casos:

- **B-01** descripciones de puesto: una plantilla arregla el tono, no el esfuerzo de redacción
- **A-01** notas de reunión: un arreglo de proceso arregla la tardanza, no el esfuerzo
- **B-09** borradores de respuesta: las respuestas enlatadas cubren exactamente 60%, que cae justo en el hueco entre los dos anchors

**Y esta es la dimensión con compuerta en ≥4.** La redacción no está decidiendo un ajuste de décimas: está decidiendo veredictos. El puntuador reporta dos casos casi idénticos aterrizando en niveles distintos (A-09 en 4, B-02 en 3) **sobre una distinción que los anchors no proveen**.

Es el hallazgo más grave de los tres, por la asimetría que ya está documentada en ADR-020: un error en una dimensión con compuerta no puede ser sobrevotado por nada.

## 3 · `data_readiness`: la cláusula de acceso y el constructo doble

**El nivel 5 exige** *"an owner who can grant access this quarter without an exception"* — algo que un request casi nunca dice. Resultado: casos con labels perfectas quedan topados en 4 **por una cláusula sobre papeleo** (A-02, B-09, B-15).

**Y la dimensión mezcla dos constructos**: *"¿existen los datos?"* y *"¿puedes evaluar la salida?"*. Los casos los contestan distinto:

- **A-04** y **B-12** tienen documentos fuente completamente accesibles y **ninguna etiqueta**
- **B-04** tiene las cifras de variación en SAP y la explicación causal solo en la cabeza de la gente

Otra vez el mismo patrón: **un eje por dimensión**, violado en la dimensión que además tiene compuerta.

## Mención aparte · `process_frequency` no define la unidad de instancia

No es ambigüedad de juicio, es una unidad indefinida, y mueve entre 2 y 3 niveles:

| Caso | Una lectura | Otra lectura |
|---|---|---|
| B-06 licitaciones | 45 licitaciones → **2** | ~4,500 requisitos respondidos → **4** |
| B-03 licencias | 1 reconciliación anual → **1** | 90 productos → **2** |
| A-07 rotación | renuncias al año | empleados puntuados |

La rúbrica dice "instancias por año" sin decir **qué es una instancia**. Para un instrumento que presume de anchors observables en los que dos personas coinciden, eso es un hueco de definición, no de criterio.

---

## Lo que NO se hace todavía

**No se reescribe ningún anchor.** El Puntuador B tiene que evaluar exactamente el mismo instrumento o el estudio de acuerdo queda anulado. Las correcciones se acumulan aquí y se aplican en un solo pase en el Paso 4, después de medir el acuerdo.

Y hay una razón adicional para esperar: **la lista de ambigüedades de A es una hipótesis, no un hallazgo.** Si B tropieza con los mismos anchors de forma independiente, el defecto está confirmado. Si B no tropieza, puede ser idiosincrasia de un evaluador — que también es información, porque significa que el anchor admite lecturas distintas sin que ninguna sea obviamente errónea, y eso es justamente lo que un instrumento reproducible no debe permitir.

## Sobre el conteo de instancias del patrón

Dos de los tres hallazgos —el nivel 5 de `business_value` y el constructo doble de `data_readiness`— son la **misma violación de "un eje por dimensión"** que nombramos y corregimos en la Fase 2.1. Volvió a aparecer en anchors que se reescribieron *después* de nombrar la regla.

No lo cuento como una quinta instancia del patrón de unidad equivocada — es una familia vecina pero distinta. Lo que sí demuestra es más incómodo: **nombrar una regla no basta para dejar de violarla.** Hizo falta un evaluador independiente aplicando el instrumento a 30 casos para que apareciera.
