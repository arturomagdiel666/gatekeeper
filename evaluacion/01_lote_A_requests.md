---
tags: [evaluacion, casos, gatekeeper]
estado: lote A v2 — recentrado a funciones corporativas
---

# Lote A — 12 requests (v2)

**Escritos sin asignar puntuaciones.** Ninguno lleva veredicto esperado; eso viene en el Paso 2 del protocolo y lo hacen dos puntuadores por separado.

## Qué cambió respecto de v1

Arturo validó **A-01, A-03, A-07 y A-09** como realistas. Los demás sonaban reales pero vivían en manufactura, y no está claro que el Hub alcance esa división.

Recentrado a **funciones corporativas y servicios compartidos**: RH, Finanzas, Legal, Compras indirecta, Ventas, Marketing, Comunicación Interna, Cumplimiento, y el propio IT. Ahí es donde un Hub de IT interno recibe peticiones de verdad.

Los casos con sabor a planta se marcan con `alcance: manufactura` para poderlos incluir o excluir sin reescribir nada. En el lote completo de 30 quedan **dos**, no más.

---

## A-01 · Notas de reunión

**Área:** Finanzas · **Solicitante:** Laura Bermúdez (Gerente de Planeación Financiera)

> Pasamos muchísimo tiempo en juntas de revisión mensual y siempre alguien tiene que tomar notas y luego repartir los acuerdos. Casi nunca salen el mismo día y para cuando llegan ya nadie se acuerda del contexto. Queremos una IA que escuche la junta y saque los acuerdos y los responsables automáticamente.

**Cómo se hace hoy:** Alguien del equipo toma notas en Word y las manda por correo. Son unas ocho juntas al mes entre revisión mensual, forecast y cierre. Las juntas son en Teams y quedan grabadas porque ya lo tenemos activado.
**Beneficio afirmado:** Que los acuerdos salgan el mismo día y no se pierda seguimiento.

Personas: 12 · Frecuencia: 8 al mes · Datos: Teams · Clasificación: interno

---

## A-02 · Captura de facturas de proveedor

**Área:** Cuentas por Pagar (Centro de Servicios Compartidos) · **Solicitante:** Rodrigo Cantú (Supervisor de CxP)

> Recibimos facturas en PDF de unos 400 proveedores de servicios e indirectos y cada una viene distinta. El equipo captura a mano el folio, la fecha, el RFC, el subtotal, el IVA y los conceptos. Son unas 2,800 facturas al mes. Los errores de captura nos generan rechazos y retrabajos que a veces detectamos hasta la conciliación.
>
> Ya intentamos con plantillas por proveedor pero se rompen cada que alguien cambia su formato, y de los 400 proveedores solo los 30 más grandes tienen plantilla.

**Cómo se hace hoy:** Cuatro capturistas. La factura llega por correo a un buzón, se descarga, se captura en SAP y se archiva. Tenemos todas las facturas de los últimos cuatro años en el repositorio con su captura correspondiente ya validada contra el pago.
**Beneficio afirmado:** Bajar el tiempo de captura y los rechazos por error de dedo.

Personas: 4 · Frecuencia: 2,800 al mes · Datos: Repositorio documental + SAP · Clasificación: confidencial

---

## A-03 · Asistente de intranet

**Área:** Comunicación Interna · **Solicitante:** (no indicado)

> Nos gustaría tener un chatbot con IA en la intranet, algo tipo ChatGPT pero de la empresa, para que la gente pueda preguntar lo que sea y no ande buscando en carpetas. Vimos que otras empresas ya lo tienen y creemos que se ve moderno y ayudaría bastante a la experiencia del empleado.

**Cómo se hace hoy:** La gente busca en la intranet o le pregunta a alguien.
**Beneficio afirmado:** Mejor experiencia del empleado, imagen de innovación.

Personas: — · Frecuencia: — · Datos: — · Clasificación: —

---

## A-04 · Revisión inicial de contratos de proveedor

**Área:** Legal · **Solicitante:** Lic. Diego Arriaga (Gerente Legal Corporativo)

> A Legal le llegan contratos de proveedor que las áreas ya negociaron y nos piden revisión. Somos tres abogados y llegan entre 60 y 80 contratos al mes, la mayoría sobre plantillas conocidas pero con cambios que el proveedor metió.
>
> Lo que quisiéramos es que algo lea el contrato y nos marque dónde se apartó de nuestra plantilla y qué cláusulas de riesgo trae — limitación de responsabilidad, indemnización, jurisdicción, terminación anticipada. No queremos que apruebe nada, queremos llegar a la revisión sabiendo dónde ver.

**Cómo se hace hoy:** El abogado lee el contrato completo. Entre 40 minutos y dos horas según el tamaño. Tenemos las plantillas aprobadas y unos tres años de contratos revisados en el repositorio, pero los comentarios de revisión quedaron en los Word con control de cambios, no en un sistema.
**Beneficio afirmado:** Que los abogados dediquen su tiempo a negociar y no a leer buscando diferencias. Hoy tenemos rezago de dos semanas y las áreas se quejan.

Personas: 3 · Frecuencia: 70 al mes · Datos: Repositorio documental de Legal · Clasificación: confidencial

---

## A-05 · Visibilidad de pipeline comercial

**Área:** Ventas · **Solicitante:** Gabriel Montaño (Director Comercial)

> Necesito que la IA me diga cómo va el pipeline por región y por vendedor, y que me avise cuando algo se salga de lo normal. Ahorita cada gerente regional arma su propio Excel y cada quien lo calcula distinto, entonces las juntas de forecast se van en discutir de quién es el número bueno.
>
> Quiero abrir algo el lunes en la mañana y saber en qué estamos parados sin pedirle nada a nadie.

**Cómo se hace hoy:** Cada gerente regional descarga de Salesforce y arma su Excel. Cuatro regiones, junta semanal de forecast.
**Beneficio afirmado:** Que dejemos de discutir números y tengamos una sola versión.

Personas: 18 · Frecuencia: semanal · Datos: Salesforce · Clasificación: confidencial

---

## A-06 · Localización de contenido a español

**Área:** Marketing · **Solicitante:** Ing. Paola Guerra (Gerente de Marketing LATAM)

> El material que nos manda corporativo llega en inglés — fichas de producto, casos de éxito, presentaciones de campaña, contenido de blog. Hoy lo mandamos a una agencia y tarda entre dos y tres semanas, lo que nos hace llegar tarde a los lanzamientos.
>
> Queremos poder traducir y adaptar internamente. No necesita quedar listo para publicar; necesita quedar lo bastante bien para que alguien de mi equipo lo ajuste en una hora en vez de escribirlo desde cero. De todas formas alguien lo revisa antes de que salga.

**Cómo se hace hoy:** Se manda a agencia externa. Unos 150 piezas al año entre todo. Costo aproximado 240 mil pesos al año.
**Beneficio afirmado:** Llegar a tiempo a los lanzamientos y bajar el gasto de agencia.

Personas: 7 · Frecuencia: 150 al año · Datos: SharePoint de Marketing · Clasificación: interno

---

## A-07 · Rotación de personal

**Área:** Recursos Humanos · **Solicitante:** Ing. Fernanda Ríos (Gerente de Talento)

> Queremos predecir qué colaboradores tienen mayor probabilidad de renunciar en los próximos seis meses, para que el jefe directo pueda actuar antes.
>
> Tenemos los datos de nómina, antigüedad, evaluaciones de desempeño, incrementos, ausentismo y las encuestas de clima de los últimos cinco años. También tenemos quién renunció y cuándo.

**Cómo se hace hoy:** No se hace. Nos enteramos cuando entregan la carta.
**Beneficio afirmado:** Cada reemplazo nos cuesta alrededor de 90 mil pesos entre reclutamiento, curva de aprendizaje y cobertura. Perdemos unas 140 personas al año.

Personas: 3,000 · Frecuencia: — · Datos: SuccessFactors + nómina · Clasificación: regulado

---

## A-08 · Reseteo de contraseñas

**Área:** Mesa de Servicio · **Solicitante:** Óscar Delgado (Coordinador de Soporte)

> El 30% de los tickets que recibimos son reseteos de contraseña. Queremos ponerle IA para que el usuario le escriba a un asistente y este le resetee la contraseña sin que un agente intervenga.

**Cómo se hace hoy:** El usuario levanta ticket, el agente verifica identidad con dos preguntas del directorio y ejecuta el reseteo en Active Directory. Toma unos cuatro minutos. Son como 1,300 tickets al mes.
**Beneficio afirmado:** Liberar al equipo de mesa de servicio de trabajo repetitivo.

Personas: 6 · Frecuencia: 1,300 al mes · Datos: Active Directory · Clasificación: confidencial

---

## A-09 · Clasificación de reportes de incidentes

`alcance: manufactura`

**Área:** Seguridad e Higiene · **Solicitante:** Ing. Teresa Landa (Coordinadora de EHS)

> Los reportes de casi-accidente los captura el supervisor en texto libre y luego alguien de EHS los clasifica por tipo de riesgo y área del cuerpo para el reporte mensual y para STPS. Se nos juntan y a veces se clasifican mal o se clasifican semanas después.
>
> Queremos que se clasifiquen solos al momento de capturarlos.

**Cómo se hace hoy:** Un analista de EHS clasifica manualmente. Llegan entre 60 y 90 reportes al mes. Tenemos ocho años de reportes ya clasificados, aunque los primeros tres años usaban un catálogo distinto al de ahora.
**Beneficio afirmado:** Reportes a tiempo y clasificación consistente.

Personas: 2 · Frecuencia: 75 al mes · Datos: Sistema EHS · Clasificación: —

---

## A-10 · Asistente de configuración y precios

**Área:** Ventas · **Solicitante:** Ing. Ramón Escutia (Gerente de Soporte Comercial)

> Los vendedores pierden mucho tiempo buscando qué configuración aplica para un cliente y qué precio de lista corresponde. Son como 900 documentos entre catálogos, guías de configuración, boletines de precio y notas de compatibilidad, en PDF, en una biblioteca de SharePoint.
>
> Queremos preguntarle en lenguaje natural, por ejemplo "qué opciones son compatibles con esta línea para un cliente de este segmento", y que nos diga la respuesta y de qué documento la sacó.

**Cómo se hace hoy:** Búsqueda en SharePoint y preguntarle al de soporte comercial con más años. Cuando no encuentran, asumen o copian de una cotización anterior. Eso nos ha generado cotizaciones con opciones incompatibles que se detectan hasta ingeniería.
**Beneficio afirmado:** Menos tiempo buscando y menos cotizaciones que se caen después.

Personas: 45 · Frecuencia: — · Datos: SharePoint · Clasificación: confidencial

---

## A-11 · Revisión de gastos contra política

**Área:** Contraloría · **Solicitante:** (no indicado)

> Queremos que la IA revise los reportes de gastos y detecte los que no cumplen la política, para que el equipo de contraloría solo revise los que tienen problema.

**Cómo se hace hoy:** Se revisa una muestra del 15%.
**Beneficio afirmado:** Mejor cobertura de revisión.

Personas: — · Frecuencia: — · Datos: Concur · Clasificación: —

---

## A-12 · Proveedores duplicados en el maestro

**Área:** Datos Maestros · **Solicitante:** Alejandra Ponce (Analista Senior de Datos Maestros)

> Tenemos proveedores dados de alta varias veces con nombres distintos — "Servicios Integrales del Norte SA de CV", "SERV INT DEL NORTE", "Servicios Integrales Del Norte S.A." — y eso nos rompe los reportes de gasto por proveedor y a veces nos hace pagar dos veces con condiciones distintas.
>
> Queremos que se detecten los duplicados en el maestro y que cuando alguien dé de alta uno nuevo nos avise si ya existe.

**Cómo se hace hoy:** Cuando alguien lo nota. Hicimos una limpieza hace dos años con filtros de Excel y encontramos como 600 duplicados de 11 mil registros. Desde entonces no se ha vuelto a hacer.
**Beneficio afirmado:** Reportes de gasto confiables y evitar pagos duplicados.

Personas: 6 · Frecuencia: 250 altas al mes · Datos: SAP maestro de proveedores · Clasificación: confidencial

---

## Notas de diseño

Deliberado, para que lo evalúes con criterio.

**Sub-especificados a propósito:** A-03 y A-11. A-03 además no trae solicitante nombrado. Ejercitan `incomplete` y la compuerta de dueño.

**Con candidato de anti-patrón:** A-01, A-05, A-08 y A-10. Capacidad ya licenciada, reporte disfrazado, automatización determinista, y uno que puede irse a cualquiera de dos lados. No digo cuál es cuál.

**Cerca del umbral:** A-04, A-06, A-07 y A-09. A-07 sigue siendo el más interesante del lote — valor de negocio altísimo y exposición regulatoria seria al mismo tiempo, que es exactamente donde una suma ponderada se equivoca sola.

**Trampa de datos sin señalar:** A-09 tiene ocho años de histórico pero los primeros tres usan otro catálogo. A-04 tiene una parecida: hay tres años de contratos revisados, pero los comentarios quedaron en control de cambios de Word y no en un sistema, así que no son un conjunto de referencia utilizable sin trabajo. Un puntuador cuidadoso lo nota; uno descuidado ve "tres años de histórico" y puntúa alto.

**Piso del lote:** A-02 y A-12 deberían ser los más limpios.

**Alcance:** solo A-09 lleva sabor a planta y está marcado. En los 30 finales quedan dos así, no más.

Faltan 18 casos. Escribo el lote B en cuanto me confirmes que estos sí caen dentro de lo que el Hub recibiría.
