---
tags: [evaluacion, protocolo, gatekeeper]
estado: v1 — para revisión
---

# Protocolo del conjunto de evaluación

## Por qué existe

Los siete ejemplares del repo son **fixtures de demostración**, no un instrumento de medición. Fueron escritos por el mismo proceso que escribió los anchors, y sus puntuaciones de referencia se redactaron para ser fieles a esos anchors. Cada número reportado hasta hoy —2/6, 3/6, 4/5, 7/7 offline— se mide contra un blanco que dibujó quien dispara.

Eso hace de ellos una prueba de humo perfectamente válida y una medida de calidad inservible.

Además, el marcador cuenta **veredictos**, no dimensiones. Un caso puede acertar el veredicto con tres dimensiones mal puntuadas que se cancelan. Nunca hemos medido si las puntuaciones son buenas — solo si el resultado final coincide.

Este conjunto existe para poder contestar dos preguntas que hoy no tienen respuesta:

1. **¿El instrumento está bien definido?** Es decir: dos evaluadores independientes aplicando los anchors al mismo caso, ¿llegan al mismo número?
2. **¿El sistema puntúa bien?** No si acierta el veredicto — si acierta **cada dimensión**.

---

## Diseño

### Tamaño y partición

**30 casos**, divididos así y **la partición se fija antes de puntuar nada**:

| Partición | Casos | Uso |
|---|---|---|
| **Desarrollo** | 20 | Se inspeccionan, se iteran, se usan para diagnosticar y ajustar |
| **Reserva** | 10 | **Se corren una sola vez, al final.** No se inspeccionan, no se usan para ajustar nada |

La reserva es lo que impide que "mejorar el sistema" degenere en "ajustarlo a los casos que ya vi". Si al final el desempeño en desarrollo es mucho mejor que en reserva, eso mismo es el resultado: el sistema se sobreajustó y no generaliza.

### Distribución

**No balanceada por veredicto a propósito.** Un Hub real recibe muchos más casos rechazables que aprobables, y un conjunto 50/50 mediría un mundo que no existe. Distribución objetivo sobre los 30:

| Veredicto esperado | Casos | Por qué esa proporción |
|---|---|---|
| `not_ai` | 9 | Es lo que más llega: soluciones pre-decididas, reportes disfrazados, cosas que una licencia ya cubre |
| `no_go` | 8 | Casos legítimos de IA que no valen la pena ahora |
| `go` | 7 | Menos de los que uno quisiera, que es el punto |
| `incomplete` | 6 | Requests genuinamente sub-especificados, que es como llega la mitad de lo real |

### Alcance funcional

Los casos viven en **funciones corporativas y servicios compartidos** — RH, Finanzas, Legal, Compras indirecta, Ventas, Marketing, Comunicación Interna, Cumplimiento, y el propio IT. Es donde un Hub de IT interno recibe peticiones de verdad.

No es una restricción cosmética: una petición de planta llega por otro canal, la evalúa otra gente y compite por otro presupuesto. Meterlas al conjunto mediría un Hub distinto del que se está diseñando.

Se admiten **dos casos con sabor a manufactura** en los 30, marcados con `alcance: manufactura` dentro del archivo, para poderlos incluir o excluir sin reescribir nada si el alcance del Hub cambia.

### Dificultad

Un conjunto de casos obvios no mide nada. Cada partición lleva:

- **~40% claros** — para detectar fallas gruesas
- **~40% cerca del umbral** — total esperado entre 3.2 y 3.8, donde una dimensión mal puntuada voltea el veredicto
- **~20% genuinamente ambiguos** — donde dos evaluadores razonables pueden discrepar, y esa discrepancia es el dato

### Cómo tienen que estar escritos

Los requests se escriben **como los escribe la gente**, no como especificaciones:

- Formulados como solución, no como problema ("queremos un chatbot que…")
- Con información faltante, sin señalar cuál falta
- Con beneficios afirmados sin cifra
- Con jerga interna, incoherencias menores y detalles irrelevantes
- Algunos largos y divagantes, otros de tres líneas

**Un request limpio y bien especificado invalida el caso.** Si el conjunto está redactado con claridad de spec, mide algo que nunca va a llegar por la puerta.

Los campos estructurados del intake se llenan **solo cuando el solicitante lo diría de forma natural**. Dejar campos en blanco es parte del diseño: es lo que ejercita el camino a `incomplete`.

---

## Procedimiento de puntuación

**El orden importa y está pre-registrado.**

### Paso 1 — escribir los textos, sin pensar en puntuaciones

Los 30 requests se redactan completos **antes** de que nadie asigne un número. Esto evita escribir el caso para que dé el resultado que uno quiere.

Revisión de Arturo en este punto: ¿suenan a peticiones reales?

### Paso 2 — dos puntuadores independientes

**Puntuador A** y **Puntuador B** puntúan los 30 casos por separado, cada uno con acceso a `rubric.yaml` y `patterns.yaml`, **sin ver las puntuaciones del otro** y sin ver ninguna predicción del sistema.

Cada puntuación exige: el número del 1 al 5, el **nivel de anchor que satisface**, y la frase del request en la que se basa. Sin justificación anclada, la puntuación no cuenta.

> **Limitación declarada:** ambos puntuadores son modelos de lenguaje, no personas. Esto **no** es acuerdo entre evaluadores humanos y no debe reportarse como tal. Mide algo más estrecho pero real: si dos evaluadores independientes y cuidadosos aplicando los mismos anchors llegan al mismo número. Cuando haya un humano disponible, el protocolo es idéntico y los materiales ya están listos.

### Paso 3 — medir acuerdo antes de reconciliar

Se calcula, **antes** de resolver ninguna discrepancia:

- **Acuerdo exacto** por dimensión: % de casos donde A y B dan el mismo número
- **Acuerdo ±1**: % dentro de un nivel
- **Acuerdo de veredicto**: % donde el veredicto resultante coincide
- **Acuerdo por dimensión individual** — cuál dimensión concentra el desacuerdo

**Ese último es el entregable más valioso de todo el ejercicio.** Una dimensión con acuerdo bajo tiene anchors mal escritos, y eso es un defecto del instrumento que ninguna cantidad de trabajo sobre el modelo arregla.

### Paso 4 — reconciliar, y registrar por qué

Cada discrepancia se resuelve y se registra: qué decía cada uno, cuál se adoptó, y **si el anchor necesita reescribirse**. Las reescrituras de anchor se acumulan y se aplican en un solo pase, después de que la reconciliación esté completa.

La referencia reconciliada es el blanco contra el que se mide el sistema.

### Paso 5 — recién ahora, correr el sistema

Y medir **dos cosas distintas**:

- **Exactitud por dimensión**: por cada una de las siete, % de casos donde el sistema da el mismo número que la referencia, y % dentro de ±1
- **Exactitud de veredicto**, reportada como **matriz de confusión con orden de costo declarado**, nunca como un escalar

Un escalar ponderado sobre errores de veredicto permite cambiar un error severo por dos leves y leerlo como progreso — el mismo defecto de unidad que este proyecto ya cometió cuatro veces. Orden de costo:

```
falso go        > falso not_ai > falso no_go > incomplete espurio
(aprueba algo    (cierra una    (rechaza      (pide información
 que no debía)    puerta)        algo bueno)   de más)
```

---

## Qué NO hace este conjunto

Declarado desde el inicio para que nadie tenga que descubrirlo:

- **No son requests reales de una organización.** Son sintéticos, escritos para parecer reales. Un conjunto de peticiones reales anonimizadas valdría más que este, y sigue siendo el siguiente paso.
- **No hay evaluadores humanos** en la primera ronda. Ver la limitación declarada arriba.
- **No mide utilidad**, mide concordancia. Que el sistema coincida con la referencia no prueba que la referencia sea buena — prueba que el instrumento es reproducible. Son cosas distintas y solo la segunda es demostrable sin datos de resultados reales.
- **No se usa para ajustar la rúbrica**, salvo por las reescrituras de anchor que salgan del Paso 4, que se documentan una por una.

---

## Ubicación y separación

Los casos de evaluación **no van a `examples/`**. Esa carpeta alimenta el menú de la interfaz y sus archivos son fixtures de demostración; mezclarlos convertiría el instrumento de medición en material de demo y garantizaría que se contaminen.

```
evals/
  cases/          los 30 casos, con partición marcada en cada archivo
  scores_a/       puntuaciones del puntuador A
  scores_b/       puntuaciones del puntuador B
  reference/      la referencia reconciliada
  runs/           salidas del sistema, con fecha y modelo
```

La partición (`development` / `holdout`) se marca dentro de cada archivo de caso y **se fija en el Paso 1**.
