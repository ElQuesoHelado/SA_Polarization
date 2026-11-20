# Auditoría de suficiencia y sesgos de los datos dirigidos

Esta etapa cierra el diagnóstico de los datos existentes antes de decidir nuevas anotaciones o entrenamientos. Separa composición del corpus, oportunidad de observación por usuario y calidad predictiva. No calcula AP ni habilita inferencia de producción.

## Ejecutar localmente

```bash
.venv/bin/sa-polarization targeted diagnose-data \
  --config config/targeted_v2.toml \
  --run-id targeted_20261115_v2 \
  --diagnostic-id data_sufficiency_20261115_v3
```

No llama a YouTube, Kaggle ni Hugging Face. No requiere GPU. Cada identificador genera un directorio nuevo en `outputs/targeted/<run_id>/diagnostics/<diagnostic_id>/`; rechaza sobrescribirlo. Una ejecución interrumpida o fallida conserva `manifest.json` con estado distinto de `complete`; para corregirla se utiliza otro identificador.

## Qué comprueba

- Frecuencias por fuente editorial, canal, mes, tipo de comentario y número de objetivos explícitos. Cuenta actores y concentración de actividad; no interpreta actividad como afinidad. El panel conserva su identidad `audit_panel` y se resume por separado.
- Coincidencias explícitas con el registro revisado y congelado, respetando vigencia y reglas de alias. Los objetivos `unknown` se contabilizan, pero no entran al contraste de bloques.
- Oportunidad estructural por usuario: en A deben existir al menos dos eventos potencialmente positivos hacia un mismo bloque y el mínimo configurado de videos; en B, ambos bloques, el mínimo de eventos y el mínimo de videos. Cada comentario cuenta una vez por bloque, aunque mencione varios actores del mismo bloque.
- La oportunidad supone que las menciones podrían resultar evaluables y que habría suficientes positivos. Es un **techo dentro del marco explícito recuperado**, no una afinidad asignada ni un techo para otros métodos de extracción. Una omisión del extractor también reduce este marco. No se considera neutralidad la ausencia de comentarios sobre el bloque contrario.
- Mantiene la partición primaria existente y reporta por separado su inversión y las semillas 43–52. Las sensibilidades no se eligen por el resultado afectivo. Los umbrales de actividad son descriptivos.
- Soporte humano en entrenamiento/validación por clase, actor, bloque, fuente y tipo; pesos y oportunidad por usuario dentro del desarrollo revisado. Las celdas con menos de diez unidades se señalan como alertas descriptivas, sin cambiar requisitos de aprobación.
- Reutiliza exclusivamente predicciones de validación ya existentes. Verifica identidades, etiquetas, pesos, procedencia y conjunto completo de candidatos contra el extractor congelado. Desglosa omisión, contexto incompleto, abstención y aceptación; incluye confusiones y métricas por subgrupo.

El tamaño efectivo `sum(w)^2 / sum(w^2)` resume solo dispersión de pesos. No considera dependencia por video, usuario o canal, ni demuestra representatividad. Los pesos y resultados de desarrollo conservan el alcance condicional y la reutilización documentados en el protocolo v2.

## Artefactos y decisión

| Archivo | Contenido |
|---|---|
| `report.md`, `summary.json`, `decision.json` | Hallazgos, denominadores, límites y siguiente intervención priorizada. |
| `main_composition.csv`, `panel_composition.csv` | Composición separada de ambos corpus. |
| `main_actors.csv`, `panel_actors.csv` | Frecuencias de candidatos explícitos por actor y bloque. |
| `user_opportunity.csv` | Recuentos estructurales locales por usuario; sin etiquetas afectivas. |
| `opportunity_partitions.csv`, `opportunity_activity.csv` | Sensibilidad de oportunidad a partición y actividad. |
| `annotation_support.csv` | Soporte humano, pesos y alertas por celda de desarrollo. |
| `validation_coverage.csv` | Cobertura por actor, bloque, valencia, fuente, tipo y número de objetivos humanos. |
| `validation_performance.csv`, `validation_confusion.csv` | Rendimiento estratificado y matriz de confusión global por modelo. |
| `protected_inputs.json`, `manifest.json` | Hashes de entradas, código, archivos protegidos y artefactos generados. |

Si hay usuarios estructuralmente comparables, la prioridad es dimensionar una comprobación humana por usuario; el recuento por sí solo no garantiza suficiencia estadística. Si no los hay, se documenta qué observaciones faltan y se estudia su recuperación mediante YouTube o una alternativa agregada con validación propia. Las carencias predictivas se localizan antes de decidir una ampliación focalizada de desarrollo. No hay selección automática de nuevos modelos ni un presupuesto de anotación inventado.

## Conservación de la prueba y resultados

Las filas finales se descartan antes de decodificar sus anotaciones. Solo se consulta su metadata de partición para comprobar separación por video. No se puntúan, exportan ejemplos ni cambian sus etiquetas. El recorrido del corpus aplica únicamente coincidencias del registro, sin producir sentimientos nuevos. El comando exige que la prueba final siga reservada.

Se verifican hashes antes y después de los corpus, anotaciones, registro, configuraciones, modelos, experimentos anteriores, código dirigido, `docs/doc.tex` y `AGENTS.md`. No se modifica el bloque generado de resultados ni se integra el diagnóstico como evidencia afirmativa de polarización. La referencia sigue siendo la de un humano asistido por IA; no se estima acuerdo entre humanos.

## Cierre de la ejecución del 2026-11-15

Diagnóstico completo: `outputs/targeted/targeted_20261115_v2/diagnostics/data_sufficiency_20261115_v3/`. El sufijo del diagnóstico no cambia la versión del estudio ni de su referencia. Para repetir el comando debe elegirse otro `--diagnostic-id`; la salida existente permanece inmutable.

- Corpus principal: 805,039 comentarios, 219,185 usuarios identificados y 11,676 videos representados. Hay 155,830 comentarios con candidatos explícitos de bloques conocidos.
- Techo estructural primario: **3,714 usuarios (1.69%)**. Invirtiendo A/B: 3,718. Con semillas 43–52: entre 3,631 y 3,763. Estos números no asignan afinidad ni prueban polarización.
- Desarrollo humano principal: **cero usuarios potencialmente comparables** bajo los mínimos y partición actuales, considerando únicamente sus comentarios revisados de entrenamiento/validación. No describe el corpus completo ni abre los 500 finales.
- BETO previo conserva macro-F1 ponderado 0.6724 y cobertura global 19.47%. La cobertura ponderada de objetivos evaluables es **22.66% en derecha (123 unidades), 4.60% en izquierda (48) y 21.91% en unknown (120)**. El denominador incluye omisiones humanas del registro. Soportes y pesos distintos impiden atribuir estas diferencias automáticamente a sesgo del modelo.
- La celda izquierda/neutral tiene cuatro unidades humanas de validación. Los indicadores globales mezclan objetivos conocidos y desconocidos; estos últimos no entran al cálculo dirigido de AP.
- El panel se mantuvo separado: 29,087 filas y 189 videos con comentarios representados. Este número cuenta videos presentes en el CSV, no todos los videos seleccionados o capturados, incluidos aquellos sin filas.

Decisión: **dimensionar una comprobación humana por usuario antes de otra ronda de entrenamiento**. El marco explícito ofrece candidatos para diseñarla, pero la referencia actual por comentario no verifica el indicador individual. La cobertura desigual debe abordarse expresamente al diseñar y validar esa comprobación; no se resuelve suponiendo que las abstenciones son neutrales.

El cierre verificó 15 artefactos y conservación de 280 archivos protegidos. La suite local terminó con 99 pruebas ejecutadas y una omitida. No hubo entrenamiento, evaluación final, inferencia de producción, cambios de registro, manuscrito ni contexto productivo.
