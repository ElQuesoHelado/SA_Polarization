# Combinación de modelos con revisiones aplazadas

El 2026-11-16 el usuario indicó continuar mejorando los resultados y realizar las revisiones después. Las 505 propuestas del piloto por usuario quedan **pendientes de confirmación**, y los otros 75 usuarios siguen sin anotar. Ninguna de esas propuestas se usa para ajustar o evaluar esta ronda.

La intervención aprovecha los dos BETO ya entrenados, sin repetir trabajos GPU: sus predicciones de validación difieren en 36 de 278 pares; el anterior acierta ocho que falla el ampliado IA, y este acierta 22 que falla el anterior. Esta complementariedad motiva combinar probabilidades; no demuestra de antemano que la combinación sea mejor.

## Decisiones fijadas antes de calcular las mezclas

Experimento `development_blend_20261116_v1`; protocolo `targeted-probability-blend-development-v1`; configuración `config/targeted_ensemble.toml`. Se sellaron configuración, fuentes y criterios antes de obtener resultados de candidatos.

- Tres candidatos: pesos del BETO ampliado IA de 0.25, 0.50 y 0.75. Para cada etiqueta, `p = (1 − peso) * p_anterior + peso * p_ampliado`. Los extremos 0/1 son controles, sin nuevas búsquedas de modelos.
- Mismo peso para todos los actores, bloques, usuarios y etiquetas. No se usan procedencia editorial, sentimiento histórico, resultados AP ni propuestas pendientes como entradas.
- Alineación exacta de los 278 pares de validación, verificando referencia, identidad y pesos; sin intersección selectiva de casos. Los objetivos omitidos siguen en el denominador de cobertura extremo a extremo.
- Se mantienen registro, etiquetas, pesos y todos los umbrales de calidad del estudio. La temperatura, cuadrícula de umbrales y mínimo de diez predicciones para calibrar una clase conservan el procedimiento existente.
- Cada candidato se calibra sobre el desarrollo completo y, adicionalmente, con **cinco folds por video**: orden SHA-256 con semilla 57, distribución cíclica a folds. Cada video queda fuera del ajuste de su propia temperatura/umbrales. Un contexto incompleto nunca se acepta; una mezcla requiere contexto completo en ambos componentes.
- Selección: cumplir todos los criterios de desarrollo en ambas modalidades, después macro-F1 ponderado, cobertura con calibración separada y menor peso IA. Se conserva `selected=null` si nadie cumple. No se promueve la mezcla al modelo canónico ni se habilitan prueba o inferencia de producción automáticamente.

La calibración separada aísla las etiquetas de cada video respecto de **su calibración**, pero los dos modelos y sus recetas ya usaron esta validación para selección y parada temprana. Tampoco elimina la selección de la propia mezcla. Por eso no es una evaluación independiente ni una validación de AP individual.

## Comando y conservación

```bash
.venv/bin/sa-polarization targeted blend-development \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --experiment-id development_blend_20261116_v1
```

**La ejecución ya terminó; no repetirla.** El comando rechaza sobrescribir el experimento y conserva cualquier preparación parcial. Trabaja localmente con probabilidades verificadas del padre `development_ai_augmentation_v1`; no carga los checkpoints para volver a inferir. Verifica los hashes de exportación del padre y utiliza únicamente `human_development.csv` (entrenamiento/validación), filtrando validación antes de puntuar. La referencia final se protege como bytes opacos, sin decodificar sus anotaciones.

En `data/targeted/targeted_20261115_v2/experiments/development_blend_20261116_v1/`:

| Artefacto | Contenido |
|---|---|
| `plan.json`, `source.json` | Decisiones, criterios, hashes de entradas y archivos protegidos. |
| `candidates/blend_*/` | Predicciones, calibración completa/por fold, informes y cobertura por grupo. |
| `selection.json` | Los tres candidatos y dos controles; mejor candidato descriptivo y selección condicionada a criterios. |
| `ensemble_spec.json` | Receta de la mejor mezcla en desarrollo y referencias selladas; solo desarrollo. |
| `paired_bootstrap.json` | Diferencias pareadas por video, 2,000 remuestreos. |
| `comparison.md`, `execution_report.json` | Resumen, alcance, conservación y hashes de resultados. |

Se verificaron 11 entradas y 40 archivos protegidos: cohorte y formulario pendientes, referencia original, configuración/registro, modelo canónico, manuscrito y contexto de producción. No hubo operaciones remotas, ajustes de modelos ni apertura de los 500 finales. La comprobación local terminó con **128 pruebas ejecutadas, una omitida**, incluidas alineación, separación de videos, exclusión de etiquetas de cada fold, contexto y bloqueo de prueba/sobrescrituras.

## Resultado completado

| Peso del modelo ampliado | Macro-F1 ponderado | Macro-F1 sin pesos | Cobertura calibración completa | Cobertura calibración separada |
|---:|---:|---:|---:|---:|
| 0: BETO anterior | 0.6724 | 0.6879 | 19.47% | 23.58% |
| 0.25 | 0.6768 | 0.7041 | 36.42% | 32.66% |
| **0.50** | **0.7037** | 0.7320 | **40.17%** | **36.16%** |
| 0.75 | 0.7019 | 0.7513 | 38.70% | 36.06% |
| 1: BETO ampliado IA | 0.6636 | 0.7316 | 49.99% | 45.30% |

La mezcla 50/50 mejora el macro-F1 ponderado puntual frente a ambos componentes y la cobertura frente al BETO anterior. **Cubre menos que el ampliado IA**; no mejora simultáneamente todas las métricas frente a este. Conserva el mayor macro-F1 ponderado observado en estas rondas, sin alcanzar 0.75 ni cobertura 60%.

Con calibración sobre todo desarrollo, las precisiones aceptadas de la mezcla son 85.94% positiva y 90.39% negativa. Al separar la calibración por video bajan a **80.25%/83.26%**, por debajo del 85% fijado. El fenómeno también aparece en los controles: anterior 81.02%/73.04%, ampliado 78.86%/80.84%. Esto diagnostica inestabilidad de la calibración en una validación pequeña y reutilizada; no atribuye por sí solo la causa a un canal, idioma o tipo de etiqueta ni demuestra sus valores en una nueva muestra.

La diferencia de macro-F1 de 50/50 frente al anterior es +0.0313, IC95% pareado por video [0.0052, 0.0668]. Para cobertura con calibración separada es +12.58 puntos, IC95% [5.04, 20.19]. Los IC son condicionales a modelos, calibraciones, selección y folds fijos; no se vuelven a seleccionar ni recalibrar en cada remuestreo y no incluyen incertidumbre de etiquetas. No deben presentarse como evidencia independiente de mejora poblacional.

`selection.json` conserva **`selected=null`**; `best_development_candidate=blend_0.50` es un resultado descriptivo. La receta queda disponible para trabajo posterior, con producción deshabilitada. Las revisiones siguen aplazadas; no se reclama otra revisión para completar esta ronda. Siguen pendientes la fiabilidad predictiva y la comprobación por usuario antes de afirmar polarización afectiva.
