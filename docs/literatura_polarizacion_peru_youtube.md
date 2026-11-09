# Polarización política en Perú y estudios comparables de YouTube

**Revisión bibliográfica y orientación para interpretar el pipeline**  
**Consultada:** 2026-11-08

## Propósito y conclusión

El objetivo del proyecto es interpretar la polarización política en Perú a partir de comentarios públicos de YouTube. No se plantea aumentar los valores de AP ni hacer etiquetado manual. La revisión sirve para contextualizar qué patrones son frecuentes, cuáles varían entre países y qué afirmaciones permite el corpus actual.

La literatura muestra algunas similitudes generales —favoritismo hacia el grupo propio y rechazo hacia grupos externos—, pero no un patrón universal en la magnitud de la polarización, en el lado político con mayor AP o en su evolución temporal. El contexto, el sistema de partidos, el momento electoral, la plataforma y la definición operacional importan. Por eso el paper español es un antecedente metodológico, no un valor esperado para Perú.

También hay estudios sobre polarización afectiva en Perú, aunque en esta búsqueda no se identificó un estudio que mida AP con comentarios peruanos de YouTube. La novedad que puede sostenerse es estudiar este fenómeno en ese medio, corpus y periodo; no afirmar que no exista investigación peruana sobre AP.

## Estudios peruanos y latinoamericanos

### Perú

- **Ponte Torrel (2022), “La campaña peruana en Twitter. Análisis de la polarización afectiva durante la segunda vuelta de las elecciones generales 2021”.** Analiza 1,202,297 tuits de menciones a Pedro Castillo y Keiko Fujimori, usando datos del monitoreo de redes del JNE. El resumen reporta sentimientos extremos hacia candidaturas y variación temporal de las cargas emocionales de apoyo/rechazo. Es el antecedente peruano más próximo por plataforma social y concepto; estudia Twitter y una campaña electoral, no YouTube ni comentarios clasificados por canal. [Artículo y resumen](https://cuadernos.info/index.php/cdi/article/view/49539), [DOI](https://doi.org/10.7764/cdi.53.49539).
- **Mejía Navarrete (2024), “Polarización política en el Perú, 2000–2023”.** Es un análisis preliminar de las dimensiones ideológica, afectiva y social. Describe un aumento de la polarización afectiva entre 2016 y 2021 y niveles mayores en segunda vuelta que en primera; su medida afectiva se basa en agrado/desagrado hacia partidos y en datos electorales comparativos. Es contexto nacional, no una réplica computacional del pipeline. [Artículo completo](https://www.scielo.org.pe/scielo.php?pid=S2617-22912024000200236&script=sci_arttext), [DOI](https://doi.org/10.15381/dds.n14.29843).
- **Comparaciones electorales que incluyen Perú.** La síntesis de la literatura latinoamericana reporta que una comparación de seis países (Argentina, Brasil, Chile, México, Perú y Uruguay) sitúa a Perú con el promedio más alto de AP entre esos seis, aunque el promedio regional está en un rango medio al compararlo con la serie internacional del CSES. Para Perú describe una trayectoria en U entre 2001 y 2017. Son resultados basados en encuestas/termómetros afectivos y periodos históricos distintos del corpus de YouTube. [“Latin America’s Polarization in Comparative Perspective”](https://www.cambridge.org/core/journals/latin-american-politics-and-society/article/latin-americas-polarization-in-comparative-perspective/D121017EDA82C92BC42794D15BC910E9).
- **Bergman y Fernández (publicado en línea en 2024; número 2025), “Affective polarization in Latin America: A research note”.** Usa datos de encuestas posteriores a diez ciclos electorales en seis países. Informa que el promedio regional no es particularmente alto frente a otros países occidentales, hay señales de aumento y la AP estaría impulsada más por minorías intensas que distribuida uniformemente. [Artículo y resumen](https://www.cambridge.org/core/journals/latin-american-politics-and-society/article/abs/affective-polarization-in-latin-america-a-research-note/BE795D2EAD877198C06840D13B3692A3), [DOI](https://doi.org/10.1017/lap.2024.51).

### YouTube y estudios multinacionales

- **Miehling, Dakota y Kübler (RANLP 2025), “Investigating Polarization in YouTube Comments via Aspect-Based Sentiment Analysis”.** Analiza más de tres millones de comentarios y respuestas sobre el conflicto Israel–Hamas. En una muestra anotada de alrededor de 5,000 comentarios modela sentimiento hacia aspectos/entidades; reporta F1 global de 77.9 y variación por aspecto. Es el antecedente más cercano para sentimiento dirigido a objetivos en YouTube, pero no valida el modelo actual ni se transfiere automáticamente a español peruano. [ACL Anthology](https://aclanthology.org/2025.ranlp-1.83/).
- **Wu y Resnick (ICWSM 2021), “Cross-Partisan Discussions on YouTube”.** Analiza 134 millones de comentarios de 274,241 videos y 973 canales políticos de EE. UU. Estudia interacción entre grupos, toxicidad de respuestas y visibilidad; muestra que hay cruces entre grupos y asimetrías de participación/visibilidad. Mide interacción partidista, no AP directamente. [Artículo](https://doi.org/10.1609/icwsm.v15i1.18105).
- **Tran et al. (2022), “Understanding Political Polarization Based on User Activity: A Case Study in Korean Political YouTube Channels”.** Usa actividad y solapamiento de usuarios en canales semilla para inferir afinidad entre grupos. Es precedente para medidas de cruce de audiencias, pero comentar en un canal no demuestra identidad o apoyo político. [Artículo](https://journals.sagepub.com/doi/10.1177/21582440221094587).
- **Mall et al. (2024), “Politics on YouTube: Detecting Online Group Polarization Based on News Videos’ Comments”.** Propone una medida de polarización operacionalizada a partir de toxicidad en unos 180,000 comentarios. Es una alternativa para estudiar hostilidad/tóxico, no una medida intercambiable con AP. [Artículo](https://journals.sagepub.com/doi/10.1177/21582440241256438).
- **Elfes, Bastos y Aiello (2026), “Measuring narrative polarization in online discourse”.** Analiza 90,029 comentarios en 212 videos sobre Israel–Palestina mediante estructura narrativa y validación humana. Encuentra que las narrativas de los videos pueden estar más polarizadas que los comentarios sobre sus narrativas centrales. Mide polarización narrativa, no AP. [PNAS Nexus](https://academic.oup.com/pnasnexus/article/5/8/pgag270/8758080).
- **Falkenberg et al. (preprint), “Affective and interactional polarization align across countries”.** Estudia Twitter en nueve países y reporta más toxicidad en interacciones entre grupos, a la vez que señala excepciones y límites del eje binario izquierda-derecha. Es evidencia relacionada, pero toxicidad/estructura de interacción no equivalen a sentimiento afectivo dirigido y debe citarse como preprint. [Preprint](https://arxiv.org/abs/2311.18535).
- **Boxell, Gentzkow y Shapiro; y estudios comparativos europeos.** Las tendencias de AP no son uniformes entre países: hay aumentos, estabilidad y descensos según país/medida. La literatura europea también encuentra bloques afectivos que pueden agrupar varios partidos y no coincidir siempre con una simple división izquierda-derecha. [Tendencias en 12 países](https://www.nber.org/papers/w26669), [revisión comparativa europea](https://resolve.cambridge.org/core/services/aop-cambridge-core/content/view/36BDBF804365FE0B350E610E9E7C714E/S1755773923000383a.pdf/affective-polarization-in-europe.pdf).

## Contraste con la corrida actual

Resultados de la corrida documentada en `AGENTS.md` (552,456 comentarios; usuarios AP determinados: 34,389):

| Indicador | Derecha | Izquierda | Lectura descriptiva |
|---|---:|---:|---|
| AP_In medio | 0.493 | -0.839 | Diferencia de signo: positivo para usuarios asignados a derecha y negativo para izquierda. |
| AP_Out medio | -0.991 | -0.580 | Negativo en ambos grupos; más negativo para derecha en esta corrida. |
| AP medio | 1.484 | -0.259 | Mayor para derecha bajo la definición y muestra actuales. |
| spread medio | 1.098 | 1.133 | Cercanos; izquierda ligeramente mayor. |

La similitud más defendible con el estudio español es que AP_Out resulta negativo en ambos bloques y AP es mayor para la derecha en esa coyuntura. La discrepancia importante es AP_In de izquierda, negativo en el pipeline mientras que en el paper español predomina la interacción positiva intragrupo en todos los grupos. No concluir que Perú reproduce el resultado español ni que la izquierda peruana rechaza su propio grupo: el pipeline asigna grupos por la fuente del video y sentimiento general predicho, no por postura del comentario hacia un objetivo político identificado.

Las cifras brutas no son comparables entre sí: difieren plataforma, unidad de análisis, periodo, cantidad/definición de grupos, oportunidades de interacción y denominadores. El estudio peruano de Twitter 2021 y las series electorales nacionales ofrecen contexto convergente sobre polarización y variación temporal, no validación numérica de estas salidas.

## Qué afirmaciones y análisis son apropiados

### Afirmaciones apropiadas

- Describir distribución de sentimiento predicho en comentarios recolectados bajo videos de los pools de fuentes clasificados.
- Describir AP y spread como indicadores operacionales calculados con estas etiquetas, usuarios, fuentes y periodo; comparar componentes entre grupos con las cautelas anteriores.
- Presentar el estudio como evidencia exploratoria sobre comentarios de YouTube en Perú. No generalizar a todos los votantes o a toda la población peruana.

### Prioridades para fortalecer la interpretación sin etiquetado manual

1. **Triangular con evidencia peruana:** contrastar la interpretación cualitativa con el estudio de Twitter de la segunda vuelta de 2021, el análisis peruano 2000–2023 y las series de encuestas/CSES. Respetar que población, plataforma, periodo e instrumento difieren; no presentar correlación o equivalencia donde no existe.
2. **Evaluar robustez del corpus actual:** recalcular comparaciones con contribución equilibrada por video/canal, separar el pool `neutral`, variar umbrales de actividad para usuarios y examinar sensibilidad al tope de 2,000 comentarios/video. Mantener la definición oficial como análisis principal y etiquetar variantes como sensibilidad.
3. **Informar incertidumbre con el nivel de muestreo adecuado:** usar remuestreo por video o canal, no asumir independencia de comentarios, y mostrar tamaños de muestra y distribución además de promedios por grupo.
4. **Analizar tiempo con la variable correcta:** `stage` actual se basa en la fecha de publicación del video. Si los datos conservan fecha del comentario, usarla para tendencias de expresión temporal y documentar ventanas/coyunturas; si no, limitar la interpretación temporal a la publicación del video.
5. **Mantener las categorías como hipótesis operacionales:** izquierda/derecha describen la clasificación editorial de canales. En Perú, identidades partidarias débiles, personalismo, anti-partidismo y divisiones coyunturales pueden hacer que el conflicto no se reduzca al eje ideológico estable. No forzar equivalencias con las cuatro familias partidarias del paper español.

No se recomienda etiquetado manual como requisito del siguiente paso. Sin una medida dirigida al objetivo, el alcance de AP debe comunicarse como exploratorio y condicionado por el uso de sentimiento general sobre comentarios en fuentes etiquetadas. Las mejoras priorizadas aquí son robustez, triangulación contextual, temporalidad y límites explícitos de inferencia; no maximizar el valor de la métrica.

## Referencia metodológica española

Martínez-España et al. (2024), *Methodology for Measuring Individual Affective Polarization Using Sentiment Analysis in Social Networks*, IEEE Access 12, DOI [10.1109/ACCESS.2024.3431999](https://doi.org/10.1109/ACCESS.2024.3431999). El estudio de Twitter en las elecciones regionales de Murcia en 2023 encuentra favoritismo intragrupo positivo predominante y AP_Out en general negativo; reporta mayor AP para la derecha de ese contexto y tensiones internas, especialmente en la izquierda radical. Sus tablas, figuras, fórmulas y límites se documentan en la sección del paper de referencia en `AGENTS.md`. Es un comparador conceptual y metodológico, no un benchmark numérico para Perú.
