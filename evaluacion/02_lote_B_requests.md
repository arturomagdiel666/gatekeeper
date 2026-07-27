---
tags: [evaluacion, casos, gatekeeper]
estado: lote B — 18 casos, sin puntuar
---

# Lote B — 18 requests

Completan los 30. Sin puntuaciones, igual que el lote A.

## Partición desarrollo / reserva

**Regla mecánica, fijada antes de puntuar nada: cada tercer caso en orden de archivo va a reserva.**

Es decir A-03, A-06, A-09, A-12, B-03, B-06, B-09, B-12, B-15, B-18 → **reserva (10)**. Los otros veinte → **desarrollo**.

La regla es mecánica a propósito. Si eligiera yo cuáles apartar, podría —sin querer— mandar a reserva los fáciles y hacer que el sistema se vea mejor de lo que es. Cualquiera puede verificar la regla contando.

**Advertencia metodológica que hay que declarar:** yo escribí los 30 casos y también soy el Puntuador A. Eso significa que la reserva no es ciega para mí. Es una debilidad real del diseño y no tiene arreglo con un solo autor. Se mitiga parcialmente porque el Puntuador B no participó en la redacción, y porque la regla de partición es verificable. Queda registrada, no absorbida.

---

## B-01 · Descripciones de puesto

**Área:** Recursos Humanos · **Solicitante:** Mónica Treviño (Especialista de Atracción de Talento)

> Cada vacante nueva necesita una descripción de puesto y hoy cada reclutador la escribe desde cero o copia una parecida y la edita. Salen muy dispares en tono y a veces se nos van requisitos que legalmente no deberíamos pedir.
>
> Queremos que a partir del título, el nivel y las responsabilidades que nos da el hiring manager, se genere el borrador con nuestro formato y nuestro lenguaje.

**Cómo se hace hoy:** El reclutador escribe en Word y la revisa el HRBP. Unas 25 vacantes nuevas al mes. Tenemos como 400 descripciones aprobadas de los últimos años en SuccessFactors, aunque de calidad variable.
**Beneficio afirmado:** Consistencia y ahorrarle tiempo al reclutador.

Personas: 8 · Frecuencia: 25 al mes · Datos: SuccessFactors · Clasificación: interno

---

## B-02 · Categorización de quejas de cliente

**Área:** Servicio a Clientes · **Solicitante:** Ing. Sergio Ávalos (Gerente de Experiencia de Cliente)

> Las quejas llegan por correo, portal y teléfono, y el agente escribe qué pasó en texto libre. Para el reporte mensual alguien tiene que leerlas todas y clasificarlas por motivo — producto, entrega, facturación, servicio, garantía — y por severidad.
>
> Se hace tarde y se hace con criterio distinto según quién lo hizo ese mes, entonces las tendencias que reportamos no son comparables entre meses.

**Cómo se hace hoy:** Un analista clasifica manualmente al cierre de mes. Llegan unas 1,100 quejas al mes. Tenemos tres años clasificadas con el mismo catálogo de motivos, que no ha cambiado.
**Beneficio afirmado:** Tendencias comparables y detectar problemas antes del cierre de mes.

Personas: 3 · Frecuencia: 1,100 al mes · Datos: Salesforce Service Cloud · Clasificación: confidencial

---

## B-03 · Reconciliación de licencias de software

`reserva`

**Área:** IT · **Solicitante:** Ing. Néstor Camarena (Coordinador de Activos de TI)

> Pagamos licencias de como 90 productos de software y no sabemos con certeza cuántas estamos usando realmente. Queremos que la IA compare lo que compramos contra lo que está instalado y contra quién lo usa, y nos diga dónde estamos pagando de más.

**Cómo se hace hoy:** Una vez al año, alguien exporta el inventario de SCCM, lo cruza contra las facturas en Excel y arma un reporte. Tarda como tres semanas y para cuando sale ya cambió.
**Beneficio afirmado:** Dejar de pagar licencias que nadie usa. La última vez encontramos 1.4 millones de pesos al año.

Personas: 2 · Frecuencia: anual · Datos: SCCM + contratos · Clasificación: confidencial

---

## B-04 · Comentario de variaciones de cierre

**Área:** Finanzas · **Solicitante:** Andrés Villalobos (Gerente de Contraloría Financiera)

> Cada cierre mensual, el analista tiene que explicar por qué cada línea del P&L se movió contra presupuesto y contra el mes anterior. Los primeros cinco días del mes se van en eso.
>
> Queremos que la IA lea las variaciones y escriba el comentario, y que el analista lo valide.

**Cómo se hace hoy:** El analista abre el reporte de variaciones, busca en el detalle qué causó cada movimiento, le pregunta al dueño del centro de costos si no es obvio, y escribe el comentario. Son unas 60 líneas comentadas por cierre, doce cierres al año.
**Beneficio afirmado:** Cerrar más rápido y liberar a los analistas de redacción.

Personas: 5 · Frecuencia: 720 al año · Datos: SAP + archivos de cierre · Clasificación: confidencial

---

## B-05 · Cuestionarios de proveedores

**Área:** Compras Indirecta · **Solicitante:** Karla Zepeda (Especialista de Abastecimiento Estratégico)

> Cuando evaluamos un proveedor nuevo le mandamos un cuestionario de 80 preguntas sobre capacidades, certificaciones, seguridad de la información y cumplimiento. Cuando ellos nos evalúan a nosotros, nos mandan el suyo, y ahí es donde se nos va el tiempo: cada cliente pregunta lo mismo con palabras distintas y alguien de aquí tiene que contestar de cero.
>
> Queremos algo que conteste esos cuestionarios usando lo que ya hemos contestado antes.

**Cómo se hace hoy:** Se buscan respuestas anteriores en una carpeta compartida y se adaptan. Nos llegan unos 15 cuestionarios al año, cada uno toma entre uno y tres días de alguien.
**Beneficio afirmado:** Contestar más rápido y con menos inconsistencias entre respuestas.

Personas: 4 · Frecuencia: 15 al año · Datos: Carpeta compartida · Clasificación: confidencial

---

## B-06 · Respuestas a licitaciones

`reserva`

**Área:** Ventas · **Solicitante:** Ing. Valeria Nájera (Gerente de Propuestas)

> Las licitaciones que nos llegan traen entre 40 y 200 requisitos y tenemos que responder uno por uno diciendo si cumplimos, cómo, y con qué evidencia. Hoy eso lo arma un equipo de tres personas jalando de propuestas anteriores, y siempre bajo presión porque el cliente da dos semanas.
>
> Queremos que a partir del pliego se genere un borrador de respuesta por requisito, con la referencia de dónde salió, y que la persona lo edite.

**Cómo se hace hoy:** Búsqueda manual en propuestas anteriores y copiar-pegar-adaptar. Participamos en unas 45 licitaciones al año. Tenemos siete años de propuestas presentadas en SharePoint, y sabemos cuáles ganamos.
**Beneficio afirmado:** Más licitaciones atendidas con el mismo equipo, y menos respuestas fuera de tiempo. Cada licitación grande vale entre 8 y 30 millones de pesos.

Personas: 3 · Frecuencia: 45 al año · Datos: SharePoint de Propuestas · Clasificación: confidencial

---

## B-07 · Seguimiento de capacitaciones obligatorias

**Área:** Cumplimiento · **Solicitante:** Lic. Ismael Pardo (Coordinador de Cumplimiento)

> Necesitamos saber quién no ha completado las capacitaciones obligatorias de código de conducta, anticorrupción y protección de datos, por área y por jefe, y que le llegue recordatorio a quien falta.
>
> Queremos que la IA nos dé eso automáticamente en lugar de estar persiguiendo a la gente.

**Cómo se hace hoy:** Se exporta el reporte del sistema de capacitación, se cruza con la plantilla vigente en Excel y se mandan correos manualmente. Cada trimestre.
**Beneficio afirmado:** Subir el porcentaje de cumplimiento antes de auditoría.

Personas: 2 · Frecuencia: trimestral · Datos: Sistema de capacitación + nómina · Clasificación: confidencial

---

## B-08 · Asistente de onboarding

**Área:** Recursos Humanos · **Solicitante:** Diana Requena (Coordinadora de Experiencia del Colaborador)

> Queremos un asistente de IA que acompañe al colaborador nuevo durante sus primeros 90 días, que le resuelva dudas y lo haga sentir acompañado. Algo conversacional, con la personalidad de la empresa.

**Cómo se hace hoy:** Hay un correo de bienvenida con ligas y el jefe directo hace lo que puede.
**Beneficio afirmado:** Mejor experiencia de ingreso y que la gente se integre más rápido.

Personas: — · Frecuencia: 40 ingresos al mes · Datos: — · Clasificación: —

---

## B-09 · Borrador de respuestas a tickets de cliente

`reserva`

**Área:** Servicio a Clientes · **Solicitante:** Ing. Sergio Ávalos (Gerente de Experiencia de Cliente)

> Los agentes contestan tickets escribiendo de cero cada vez, aunque el 60% son variaciones de las mismas veinte situaciones. Queremos que el sistema le proponga un borrador de respuesta al agente, que él edita y manda.
>
> El agente decide siempre. No queremos respuestas automáticas al cliente sin que alguien las vea.

**Cómo se hace hoy:** El agente escribe cada respuesta. Hay plantillas pero están en un documento que nadie abre. Son 3,400 tickets al mes y tenemos cuatro años de conversaciones con su desenlace, incluyendo si el cliente reabrió el ticket.
**Beneficio afirmado:** Bajar el tiempo de primera respuesta, que hoy es de 6 horas y el compromiso con el cliente son 4.

Personas: 22 · Frecuencia: 3,400 al mes · Datos: Salesforce Service Cloud · Clasificación: confidencial

---

## B-10 · Clasificación contable de gastos

**Área:** Contabilidad · **Solicitante:** C.P. Norma Estrada (Jefa de Contabilidad)

> Cada gasto que entra hay que asignarlo a una cuenta contable y a un centro de costos. Hoy lo hace el analista leyendo el concepto, y cuando se equivoca lo detectamos en la revisión de cierre o no lo detectamos.
>
> Queremos que se sugiera la cuenta automáticamente.

**Cómo se hace hoy:** Manual. Unos 9,000 movimientos al mes. Tenemos seis años de movimientos ya clasificados y auditados, con el catálogo de cuentas actual desde hace cuatro.
**Beneficio afirmado:** Menos reclasificaciones en cierre y cierre más limpio.

Personas: 6 · Frecuencia: 9,000 al mes · Datos: SAP · Clasificación: confidencial

---

## B-11 · Higiene de datos en CRM

**Área:** Ventas · **Solicitante:** Ing. Rubén Castañeda (Gerente de Operaciones Comerciales)

> El CRM está sucio. Hay cuentas duplicadas, contactos con correos que ya rebotan, oportunidades que llevan dos años sin moverse y siguen en el forecast, y campos obligatorios llenados con "n/a".
>
> Queremos que la IA lo limpie y lo mantenga limpio.

**Cómo se hace hoy:** Cada quien limpia lo suyo cuando se acuerda. Hicimos un esfuerzo el año pasado con un consultor y duró tres meses limpio.
**Beneficio afirmado:** Que el forecast sea creíble.

Personas: 60 · Frecuencia: — · Datos: Salesforce · Clasificación: confidencial

---

## B-12 · Triage de acuerdos de confidencialidad

`reserva`

**Área:** Legal · **Solicitante:** Lic. Diego Arriaga (Gerente Legal Corporativo)

> Nos llegan NDAs de contraparte para firmar. La mayoría son estándar y podrían firmarse sin abogado, pero alguien tiene que revisarlas para saber cuáles sí necesitan revisión.
>
> Queremos que se clasifiquen en "estándar, se puede firmar" y "necesita abogado", con la razón.

**Cómo se hace hoy:** Un abogado las revisa todas. Llegan unas 25 al mes y estima que 18 son estándar. Tenemos las NDAs firmadas de los últimos años pero no está registrado cuáles requirieron negociación y cuáles no.
**Beneficio afirmado:** Que Legal deje de leer 18 documentos estándar al mes.

Personas: 3 · Frecuencia: 25 al mes · Datos: Repositorio de Legal · Clasificación: confidencial

---

## B-13 · Riesgo de solicitudes de cambio

**Área:** IT · **Solicitante:** Ing. Héctor Munguía (Coordinador de Gestión de Cambios)

> Cada cambio a sistemas productivos pasa por el comité semanal, que clasifica el riesgo en bajo, medio o alto. El comité se junta dos horas cada semana y buena parte del tiempo se va en los cambios obvios de riesgo bajo.
>
> Queremos que la IA proponga la clasificación de riesgo leyendo la solicitud, para que el comité solo discuta los que importan.

**Cómo se hace hoy:** El comité revisa todo. Entran unos 90 cambios al mes. Tenemos dos años de cambios con su clasificación y también sabemos cuáles causaron incidente después, aunque eso último está en otro sistema y nadie los ha cruzado.
**Beneficio afirmado:** Comité más corto y enfocado.

Personas: 9 · Frecuencia: 90 al mes · Datos: ServiceNow · Clasificación: interno

---

## B-14 · Resumen de reportes de campaña

**Área:** Marketing · **Solicitante:** (no indicado)

> Queremos que la IA nos resuma cómo fue cada campaña y nos diga qué funcionó, sin tener que abrir cinco plataformas distintas.

**Cómo se hace hoy:** Alguien entra a cada plataforma, baja números y arma una lámina.
**Beneficio afirmado:** Ahorrar tiempo en reportes.

Personas: — · Frecuencia: — · Datos: — · Clasificación: —

---

## B-15 · Priorización de leads

`reserva`

**Área:** Ventas · **Solicitante:** Ing. Rubén Castañeda (Gerente de Operaciones Comerciales)

> Nos entran unos 800 leads al mes entre web, ferias y campañas, y el equipo de desarrollo comercial los trabaja en el orden en que llegan. Sabemos que no todos valen lo mismo pero no tenemos forma de saber cuáles antes de llamarles.
>
> Queremos que se ordenen por probabilidad de convertirse, para que los primeros que se llamen sean los que sí van a comprar.

**Cómo se hace hoy:** Orden de llegada, con algo de criterio del que los trabaja. Tenemos cuatro años de leads en Salesforce con su desenlace — cuáles se convirtieron en oportunidad y cuáles en venta. El equipo de desarrollo comercial rota mucho, este año se fueron cuatro de siete.
**Beneficio afirmado:** Mismo equipo, más conversión. Hoy convertimos 4% de leads a oportunidad.

Personas: 7 · Frecuencia: 800 al mes · Datos: Salesforce · Clasificación: confidencial

---

## B-16 · Ruteo de órdenes de trabajo de instalaciones

**Área:** Servicios Generales · **Solicitante:** Arq. Lucía Fentanes (Coordinadora de Instalaciones)

> Las solicitudes de mantenimiento de oficinas llegan por un formulario y las asignamos a uno de seis proveedores según de qué se trate — aire acondicionado, eléctrico, plomería, mobiliario, limpieza profunda, jardinería.
>
> Queremos que se asigne solo, porque hoy se atora cuando la persona que asigna está de vacaciones.

**Cómo se hace hoy:** Una persona lee y asigna. Entran unas 140 solicitudes al mes. Tenemos el histórico de asignaciones de tres años.
**Beneficio afirmado:** Que no se atore cuando ella no está.

Personas: 1 · Frecuencia: 140 al mes · Datos: Formulario + hoja de cálculo · Clasificación: interno

---

## B-17 · Redacción de comunicados internos

**Área:** Comunicación Interna · **Solicitante:** Renata Ochoa (Especialista de Comunicación)

> Redactamos comunicados para anuncios de la organización — cambios de estructura, nuevos beneficios, resultados trimestrales. Cada uno lo escribe alguien del equipo y luego pasa por revisión de RH y a veces de Legal.
>
> Queremos que la IA nos dé el primer borrador a partir de los puntos clave, en el tono de la empresa.

**Cómo se hace hoy:** Se escribe desde cero. Unos 6 comunicados al mes. Tenemos el archivo de comunicados de los últimos cinco años.
**Beneficio afirmado:** Que el primer borrador salga más rápido.

Personas: 3 · Frecuencia: 6 al mes · Datos: SharePoint · Clasificación: interno

---

## B-18 · Gasto fuera de contrato

`reserva`

**Área:** Compras Indirecta · **Solicitante:** Ing. Mauricio Bañuelos (Gerente de Compras Indirectas)

> Negociamos contratos con proveedores preferentes y aun así la gente compra por fuera — a veces por urgencia, a veces porque no sabe que existe el contrato. Eso nos hace perder el descuento por volumen y nos rompe la negociación del año siguiente.
>
> Queremos identificar ese gasto fuera de contrato y saber quién lo está generando.

**Cómo se hace hoy:** No se mide de forma sistemática. Lo detectamos cuando el proveedor preferente reclama que le bajó el volumen. Tenemos todas las órdenes de compra en SAP y la lista de contratos vigentes con sus proveedores y categorías.
**Beneficio afirmado:** Recuperar descuento por volumen. Estimamos que el gasto fuera de contrato anda entre 8% y 15% del indirecto.

Personas: 5 · Frecuencia: 3,000 órdenes al mes · Datos: SAP + repositorio de contratos · Clasificación: confidencial

---

## Cobertura del conjunto completo

| Función | Casos |
|---|---|
| Ventas / Operaciones Comerciales | A-05, A-10, B-06, B-11, B-15 |
| Recursos Humanos | A-07, B-01, B-08 |
| Finanzas / Contabilidad / Contraloría | A-01, A-02, A-11, B-04, B-10 |
| IT / Mesa de Servicio | A-08, B-03, B-13 |
| Legal | A-04, B-12 |
| Compras Indirecta / Datos Maestros | A-12, B-05, B-18 |
| Servicio a Clientes | B-02, B-09 |
| Marketing | A-06, B-14 |
| Comunicación Interna | A-03, B-17 |
| Cumplimiento | B-07 |
| Servicios Generales | B-16 |
| EHS `alcance: manufactura` | A-09 |

**Ventas: 5 de 30 (17%).** Bien representada sin dominar. Es el bloque donde Arturo tiene expertise de dominio, y por eso es el candidato natural para puntuación humana independiente en el Paso 2.

**Manufactura: 1 de 30.** Por debajo del tope de 2 que fija el protocolo.

## Lo que trae escondido cada bloque

Sin decir cuál es cuál, porque los puntuadores no deben verlo:

- **Cuatro casos** tienen histórico aparentemente abundante que no sirve como referencia sin trabajo previo. A-04 y A-09 ya lo traían; hay dos más en el lote B.
- **Tres casos** tienen un dato de resultado disponible que el solicitante no menciona como tal, y que un puntuador atento reconoce como la variable de salida.
- **Dos casos** describen un beneficio real cuya causa no es lo que el solicitante cree.
- **Un caso** menciona de pasada una rotación de personal que debería mover una dimensión y que es fácil pasar por alto.
