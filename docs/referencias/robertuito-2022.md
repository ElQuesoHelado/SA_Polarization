# robertuito-2022 — modelo base de clasificación

**Cita completa:** Pérez, J. M.; Furman, D. A.; Alonso Alemany, L.; Luque, F. (2022). *RoBERTuito: a pre-trained language model for social media text in Spanish*. LREC 2022. arXiv:2111.09453v3. DOI [10.48550/arXiv.2111.09453](https://doi.org/10.48550/arXiv.2111.09453).

**PDF:** `pdfs/02.robertuito-2022.pdf` (arXiv v3)
**Rol:** `modelo-sa` — modelo Transformer base del pipeline.
**Clave en `doc.tex`:** `robertuito`.
**Verificado:** 2026-11-10 (resumen, Tabla 2 y discusión).

## Qué aporta

Presenta RoBERTuito, un modelo de lenguaje preentrenado sobre aproximadamente **500 millones de tuits en español**. Lo evalúa en tareas de texto generado por usuarios (odio, sentimiento, emoción, ironía) y en el benchmark bilingüe LinCE, y lo publica junto con el corpus de preentrenamiento.

## Hallazgos citables

- Entrenado con ~500 millones de tuits; arquitectura RoBERTa y tokenizador adaptado a texto informal.
- **Tabla 2 (Macro F1 medio de 10 ejecuciones):** en sentimiento obtiene **68.4**, frente a BERTweet 70.3, RoBERTa 69.5, BERT 68.9, mBERT 66.6 y XLM-R 68.0. Es decir, no gana esa tarea puntual, pero sí el rendimiento agregado del benchmark.
- En las tareas de LinCE y en las tareas en inglés reporta resultados competitivos; el resumen destaca que supera a modelos previos en el conjunto del benchmark.
- Modelo y datos disponibles públicamente en Hugging Face.

## Límites para nuestro trabajo

- Describe el modelo base, **no** el checkpoint `pyupeu/robertuito-peruvian-sentiment` ni su calibración para comentarios políticos.
- No evalúa YouTube, Perú ni polarización afectiva; sus métricas no se transfieren al corpus local.
- El 68.4 de sentimiento es un promedio de sus tareas y anotaciones, no una estimación del desempeño del pipeline.

## Uso en el proyecto

- `doc.tex` §Introducción y §Método: justifica el uso de RoBERTuito como modelo de lenguaje para español informal.
- Citar el modelo y su benchmark; no presentar sus cifras como validación del clasificador local.
