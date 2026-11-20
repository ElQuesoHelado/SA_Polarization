# Bansal y Sharma (2023)

**Cita:** Bansal, P.; Sharma, A. *Large Language Models as Annotators: Enhancing Generalization of NLP Models at Minimal Cost*. arXiv:2306.15766v1, 27-06-2023. DOI: https://doi.org/10.48550/arXiv.2306.15766.

**PDF local:** `pdfs/contexto/bansal-sharma-2023.pdf`. **Rol:** contexto técnico de ampliación de entrenamiento mediante etiquetas IA; no benchmark de polarización.

## Hallazgos citables

- Resumen y §1: estudian usar anotaciones LLM para mejorar generalización con datos escasos. Sus experimentos son clasificación de similitud semántica y ranking de búsqueda semántica.
- §1: advierten que etiquetas LLM pueden contener ruido; la anotación aleatoria aporta mejoras limitadas e incluso puede perjudicar grupos con pocos datos en sus experimentos.
- Resumen y §1: proponen seleccionar ejemplos mediante diferencias entre puntuaciones de modelo base y ajustado; comparan con muestreo por incertidumbre. No afirman que cualquier aumento de anotaciones mejore automáticamente un modelo.

## Límites y uso local

No estudia comentarios políticos peruanos, sentimiento dirigido ni AP individual. Nuestra muestra usa cuotas de candidatos por bloque y equilibrio canal/mes; no reproduce su criterio de selección. No atribuir al paper el peso 0.25, las cuotas, los umbrales locales ni una mejora pendiente de medir. La evaluación humana local permanece separada de las etiquetas IA auxiliares, con las limitaciones de asistencia y reutilización ya documentadas.

Se consulta como motivación técnica de [la ampliación IA](../ampliacion_ia_dirigida.md), sin modificar la fuente metodológica principal Martínez-España et al. (2024).
