# antonakaki-2021 — survey de investigación en Twitter

**Cita completa:** Antonakaki, D.; Fragopoulou, P.; Ioannidis, S. (2021). *A survey of Twitter research: Data model, graph structure, sentiment analysis and attacks*. Expert Systems With Applications 164, 114006. DOI [10.1016/j.eswa.2020.114006](https://doi.org/10.1016/j.eswa.2020.114006).

**PDF:** `pdfs/16.antonakaki-2021.pdf`
**Rol:** `survey-sa` — panorama de la investigación en Twitter y de sus restricciones de datos.
**Clave en `doc.tex`:** `ANTONAKAKI2021114006`.
**Verificado:** 2026-11-09 (primera página y resumen).

## Qué aporta

Revisión amplia de la investigación sobre Twitter: modelo de datos, estructura de grafo, análisis de sentimiento y ataques/limitaciones. Útil para contextualizar la plataforma, sus APIs y los sesgos de los datos.

## Hallazgos citables

- Sintetiza métodos de SA sobre Twitter y las características del dato (brevedad, ruido, hashtags, retuits).
- Documenta límites de acceso a datos y cambios de API; en `doc.tex` se cita para justificar las restricciones de acceso a Twitter/X y la decisión de usar TikTok/YouTube.
- Cubre también ataques y cuentas automatizadas, relevante para discutir bots y manipulación.

## Límites para nuestro trabajo

- Survey, no un estudio empírico comparable.
- Centrado en Twitter; YouTube tiene otra estructura (comentarios, canales, respuestas).
- No aborda AP ni el contexto peruano.

## Uso en el proyecto

- `doc.tex` §Método (justificación de la fuente de datos por restricciones de API).
- `doc.tex` §Estado del Arte (panorama general de SA en redes).
- No usar para cifras de polarización.
