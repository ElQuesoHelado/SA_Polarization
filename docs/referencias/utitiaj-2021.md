# utitiaj-2021 — herramienta de SA para español ecuatoriano

**Cita completa:** Utitiaj, I.; Morillo, P.; Vallejo-Huanga, D. (2021). *Sentiment Analysis Tool for Spanish Tweets in the Ecuadorian Context*. En *Proceedings of the 2020 3rd International Conference on Algorithms, Computing and Artificial Intelligence (ACAI 2020)*, ACM. DOI [10.1145/3446132.3446424](https://doi.org/10.1145/3446132.3446424).

**PDF:** `pdfs/17.utitiaj-2021.pdf`
**Rol:** `contexto-idioma` — evidencia de que el español general no cubre bien las variantes regionales.
**Clave en `doc.tex`:** `10.1145/3446132.3446424`.
**Verificado:** 2026-11-10 (resumen, método y Tabla 2).

## Qué aporta

Presenta **SAET**, una herramienta web en R-Shiny para analizar sentimiento en tuits en español con dialecto o modismos ecuatorianos. Usa un enfoque basado en léxico personalizable, permite descargar tuits por lugar, fecha y tema, y compara su desempeño con Azure Text Analytics, IBM Watson NLU y una puntuación manual en tres corpus.

## Hallazgos citables

- Los autores argumentan que hay pocas herramientas para español y que la dificultad aumenta por contextos, dialectos, estructuras gramaticales y variaciones semánticas regionales.
- **Tabla 2:** SAET obtiene un rendimiento comparable a las herramientas comerciales; el artículo reporta precisión, recall y accuracy por clase y corpus, sin un único valor agregado.
- La tendencia de polaridad de SAET se parece a la evaluación manual; la evaluación manual tiende a ser más negativa.
- Los léxicos adaptados al contexto mejoran la detección de dialectos, coloquialismos y negaciones.

## Límites para nuestro trabajo

- Ecuador, léxico y tuits; no YouTube, Perú ni un Transformer.
- No mide polarización afectiva ni AP.
- Su comparación es con herramientas comerciales de su periodo, no con RoBERTuito.
- El congreso es ACAI 2020 y el `.bib` lo registra como 2021; usar la fecha de publicación del DOI.

## Uso en el proyecto

- `doc.tex` §Introducción y §Estado del arte: sustenta que los modelos y recursos generales del español no capturan bien la jerga regional; junto con Calizaya-Milla et al. (2026) justifica la elección de un modelo adaptado al español peruano.
- No usar sus valores de accuracy como benchmark del pipeline.
