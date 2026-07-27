---
tags: [evaluacion, casos, ventas, gatekeeper]
puntuador: Arturo Magdiel
estado: para puntuar
---

# Los 5 casos de Ventas

**Solo los textos.** Sin notas de diseño, sin pistas, sin nada que indique dificultad o resultado esperado.

> [!warning] No abras `01_lote_A_requests.md` ni `02_lote_B_requests.md` hasta terminar
> Esos archivos traen al final notas de diseño que señalan cuáles casos están cerca del umbral, cuáles esconden una trampa de datos y cuáles tienen candidato de anti-patrón. Leerlas antes de puntuar arruina el ejercicio.

Los criterios están en `03_hoja_puntuacion_ventas.md`. Puntúa cada caso con la plantilla de ahí.

---

## A-05 · Visibilidad de pipeline comercial

**Área:** Ventas · **Solicitante:** Gabriel Montaño (Director Comercial)

> Necesito que la IA me diga cómo va el pipeline por región y por vendedor, y que me avise cuando algo se salga de lo normal. Ahorita cada gerente regional arma su propio Excel y cada quien lo calcula distinto, entonces las juntas de forecast se van en discutir de quién es el número bueno.
>
> Quiero abrir algo el lunes en la mañana y saber en qué estamos parados sin pedirle nada a nadie.

**Cómo se hace hoy:** Cada gerente regional descarga de Salesforce y arma su Excel. Cuatro regiones, junta semanal de forecast.

**Beneficio afirmado:** Que dejemos de discutir números y tengamos una sola versión.

Personas afectadas: 18 · Frecuencia: semanal · Dónde viven los datos: Salesforce · Clasificación: confidencial · Herramienta previa para estos usuarios: —

---

## A-10 · Asistente de configuración y precios

**Área:** Ventas · **Solicitante:** Ing. Ramón Escutia (Gerente de Soporte Comercial)

> Los vendedores pierden mucho tiempo buscando qué configuración aplica para un cliente y qué precio de lista corresponde. Son como 900 documentos entre catálogos, guías de configuración, boletines de precio y notas de compatibilidad, en PDF, en una biblioteca de SharePoint.
>
> Queremos preguntarle en lenguaje natural, por ejemplo "qué opciones son compatibles con esta línea para un cliente de este segmento", y que nos diga la respuesta y de qué documento la sacó.

**Cómo se hace hoy:** Búsqueda en SharePoint y preguntarle al de soporte comercial con más años. Cuando no encuentran, asumen o copian de una cotización anterior. Eso nos ha generado cotizaciones con opciones incompatibles que se detectan hasta ingeniería.

**Beneficio afirmado:** Menos tiempo buscando y menos cotizaciones que se caen después.

Personas afectadas: 45 · Frecuencia: — · Dónde viven los datos: SharePoint · Clasificación: confidencial · Herramienta previa para estos usuarios: —

---

## B-06 · Respuestas a licitaciones

**Área:** Ventas · **Solicitante:** Ing. Valeria Nájera (Gerente de Propuestas)

> Las licitaciones que nos llegan traen entre 40 y 200 requisitos y tenemos que responder uno por uno diciendo si cumplimos, cómo, y con qué evidencia. Hoy eso lo arma un equipo de tres personas jalando de propuestas anteriores, y siempre bajo presión porque el cliente da dos semanas.
>
> Queremos que a partir del pliego se genere un borrador de respuesta por requisito, con la referencia de dónde salió, y que la persona lo edite.

**Cómo se hace hoy:** Búsqueda manual en propuestas anteriores y copiar-pegar-adaptar. Participamos en unas 45 licitaciones al año. Tenemos siete años de propuestas presentadas en SharePoint, y sabemos cuáles ganamos.

**Beneficio afirmado:** Más licitaciones atendidas con el mismo equipo, y menos respuestas fuera de tiempo. Cada licitación grande vale entre 8 y 30 millones de pesos.

Personas afectadas: 3 · Frecuencia: 45 al año · Dónde viven los datos: SharePoint de Propuestas · Clasificación: confidencial · Herramienta previa para estos usuarios: —

---

## B-11 · Higiene de datos en CRM

**Área:** Ventas · **Solicitante:** Ing. Rubén Castañeda (Gerente de Operaciones Comerciales)

> El CRM está sucio. Hay cuentas duplicadas, contactos con correos que ya rebotan, oportunidades que llevan dos años sin moverse y siguen en el forecast, y campos obligatorios llenados con "n/a".
>
> Queremos que la IA lo limpie y lo mantenga limpio.

**Cómo se hace hoy:** Cada quien limpia lo suyo cuando se acuerda. Hicimos un esfuerzo el año pasado con un consultor y duró tres meses limpio.

**Beneficio afirmado:** Que el forecast sea creíble.

Personas afectadas: 60 · Frecuencia: — · Dónde viven los datos: Salesforce · Clasificación: confidencial · Herramienta previa para estos usuarios: —

---

## B-15 · Priorización de leads

**Área:** Ventas · **Solicitante:** Ing. Rubén Castañeda (Gerente de Operaciones Comerciales)

> Nos entran unos 800 leads al mes entre web, ferias y campañas, y el equipo de desarrollo comercial los trabaja en el orden en que llegan. Sabemos que no todos valen lo mismo pero no tenemos forma de saber cuáles antes de llamarles.
>
> Queremos que se ordenen por probabilidad de convertirse, para que los primeros que se llamen sean los que sí van a comprar.

**Cómo se hace hoy:** Orden de llegada, con algo de criterio del que los trabaja. Tenemos cuatro años de leads en Salesforce con su desenlace — cuáles se convirtieron en oportunidad y cuáles en venta. El equipo de desarrollo comercial rota mucho, este año se fueron cuatro de siete.

**Beneficio afirmado:** Mismo equipo, más conversión. Hoy convertimos 4% de leads a oportunidad.

Personas afectadas: 7 · Frecuencia: 800 al mes · Dónde viven los datos: Salesforce · Clasificación: confidencial · Herramienta previa para estos usuarios: —

---

## Nota de partición

**B-06 y B-15 pertenecen a la partición de reserva.** Puntuarlos para construir la referencia es correcto y necesario — la reserva se trata de no usarlos para *ajustar* el sistema, no de no tener referencia para ellos.

Lo que sí aplica: una vez puntuados, esos dos no se usan para diagnosticar ni para decidir cambios. Se corren una sola vez, al final.

---

## Cuando termines

Pásame la hoja llena. Yo no puntúo nada hasta entonces.
