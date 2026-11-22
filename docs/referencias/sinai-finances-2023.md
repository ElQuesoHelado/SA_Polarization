# SINAI en FinancES 2023

**Cita:** Salud María Jiménez-Zafra, Daniel García-Baena, Miguel Ángel
García-Cumbreras y Manuel García-Vega (2023), *SINAI at FinancES@IberLEF2023:
Evaluating Popular Tools and Transformers Models for Financial Target Detection
and Sentiment Analysis*, CEUR Workshop Proceedings 3496.
**Clave:** `SINAI2023FinancES`.
**Fuente:** [PDF editorial](https://ceur-ws.org/Vol-3496/finances-paper3.pdf).
**PDF local:** `pdfs/contexto/sinai-finances-2023.pdf`.
Procedencia/hash en `encoder-extension-downloads.json`. Consulta: 2026-11-22.

## Hallazgos citables

La sección 2 describe sentimiento favorable, desfavorable y neutral hacia
objetivos en titulares financieros en español. La tabla 3 compara variantes de
desarrollo; las tablas 7 y 8 identifican los sistemas de evaluación. La tabla 8
y la sección 5 documentan la elección de un extractor NER más mDeBERTa para la
participación del equipo. Sustenta un antecedente de sentimiento dirigido en
español y la separación entre extracción y clasificación.

## Límites de transferencia

Son titulares financieros, no comentarios políticos de YouTube; hay diferencias
de objetivos, etiquetas, muestra y anotación. No transferir su F1 al proyecto ni
usar su clasificación de sistemas como garantía de que mDeBERTa supere localmente
a RoBERTuito o BETO. El artículo denomina al clasificador mDeBERTa sin identificar
un SHA del recurso: no afirmar identidad exacta con el checkpoint local.
