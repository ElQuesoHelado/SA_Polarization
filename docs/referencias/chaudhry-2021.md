# chaudhry-2021 — SA antes/después de elecciones (EE. UU. 2020)

**Cita completa:** Chaudhry, H. N.; Javed, Y.; Kulsoom, F.; Mehmood, Z.; Khan, Z. I.; Shoaib, U.; Janjua, S. H. (2021). *Sentiment Analysis of before and after Elections: Twitter Data of U.S. Election 2020*. Electronics 10(17), 2082. DOI [10.3390/electronics10172082](https://doi.org/10.3390/electronics10172082).

**PDF:** `pdfs/12.chaudhry-2021.pdf`
**Rol:** `polarizacion-sa` — SA electoral con clasificador clásico y comparación pre/post.
**Clave en `doc.tex`:** `chaudhry2022sentiment` (aunque el año correcto de publicación es 2021).
**Verificado:** 2026-11-09 (resumen).

## Qué aporta

Analiza sentimiento en Twitter antes, durante y después de las elecciones presidenciales de EE. UU. de 2020, y lo compara con las de 2016. Pipeline: recolección vía API, preprocesamiento, TF-IDF y clasificador Naive Bayes. Identifica outliers, estados disputados/swing y contrasta con resultados oficiales.

## Hallazgos citables

- Los resultados electorales coinciden con el sentimiento expresado en la mayoría de los casos.
- Se observa *sentimental drift* en los outliers antes/después de la elección.
- **Exactitud del clasificador: 94.58 %; precisión: 93.19 %.**
- El análisis distingue periodos y estados, no solo el agregado nacional.

## Límites para nuestro trabajo

- Twitter, EE. UU., 2020; no YouTube ni Perú.
- TF-IDF + Naive Bayes sobre tuits; el pipeline usa un Transformer.
- Mide sentimiento agregado, no AP individual.
- La exactitud reportada es de su tarea y dataset; no se transfiere al pipeline.

## Uso en el proyecto

- `doc.tex` §Estado del Arte: antecedente de SA electoral y de comparación temporal pre/post.
- Citar la exactitud solo como resultado del estudio.
