# Medición anotada independiente del clasificador

Contingencia aprobada e implementada el 18 de noviembre de 2026. La prioridad es cerrar la medición de polarización desde historiales revisados aunque los clasificadores no alcancen los umbrales. No promete mejorar macro-F1, obtener un efecto positivo ni aceptación editorial. Los criterios de automatización siguen intactos.

## Dos comprobaciones diferentes

```bash
.venv/bin/sa-polarization targeted publication measurement-preflight
.venv/bin/sa-polarization targeted publication evaluation-preflight
```

Ambos comandos son de solo lectura. `measurement-preflight` comprueba la preparación del análisis humano sin cargar modelos, predicciones ni etiquetas reservadas; `evaluation-preflight` comprueba la comparación de clasificadores. El primero no depende de la preparación del segundo ni del benchmark. El benchmark sigue siendo necesario para cerrar la comparación independiente del paper.

Estados de medición: `waiting_snapshot`, `waiting_cohort`, `waiting_human_review`, `waiting_comparable_users`, `ready_for_analysis` e `insufficient_eligible_frame`. Los datos/modelos protegidos originales se verifican según el manifiesto del estudio; los nuevos checkpoints y predicciones no son una condición de medición. Un archivo protegido alterado sigue siendo un error, no una condición que se pueda ignorar.

Después de congelar, se comprueban la secuencia de lotes, el prefijo de usuarios por hash y todos los comentarios de esos usuarios en el snapshot: IDs, texto y metadata deben coincidir. Las propuestas no cuentan como revisión humana. Un lote incompleto bloquea el cierre; un lote completo también debe superar las validaciones de anotación y procedencia. La verificación no completa formularios ni cierra referencias.

Al alcanzar 800 comparables o agotar el marco, el comando indica `ready_for_analysis`. Esto permite analizar; no garantiza la precisión estadística ni un efecto. Si no hay usuarios elegibles, informa insuficiencia en lugar de recomendar un bucle de lotes vacío. No se recalcula ni altera el marco por estos resultados.

## Orden operativo

1. Completar `collect` con presupuesto disponible y ejecutar `freeze` cuando todos los videos estén completos o tengan indisponibilidad registrada.
2. Inicializar el benchmark, anotar sus 3,000 comentarios a ciegas y cerrar su referencia **antes de revisar las propuestas de cohorte**. Este orden reduce exposición previa cuando coinciden comentarios. El benchmark no se usa para entrenar ni elegir umbrales.
3. Preparar propuestas y revisar lotes completos de cohorte, en el orden congelado. Se revisan también textos sin candidatos y omisiones. El número de comentarios depende de los historiales observados; 800 es la meta de usuarios comparables, no de comentarios.
4. Consultar `measurement-preflight`; continuar con `next --stage final` si faltan comparables. Con la referencia completa y la meta o el marco agotado, ejecutar `analyze --stage final`.
5. Completar por separado la comparación de los cuatro modelos, con los checkpoints existentes y la referencia independiente. Si fallan, publicar la limitación de automatización y mantener inhabilitada la inferencia de producción.

Los datos históricos siguen siendo el marco de participación e historiales. No se asigna polarización afectiva a los aproximadamente 800,000 comentarios mediante clasificadores insuficientemente validados. El registro congelado y la exigencia de evidencia explícita delimitan también la medición humana; esta no identifica automáticamente la ideología de todos los usuarios.

El orden de anotación es una instrucción operativa: no invalida revisiones previas legítimas ni bloquea el cálculo primario por ausencia del benchmark. La auditoría de exposición de `evaluation-preflight` conserva las coincidencias y fechas registradas; ausencia de registro no prueba ausencia de lectura.

## Resultados y lectura de la precisión

`analysis_final/` conserva los artefactos anteriores y añade:

- `screened_user_scores.csv`: comentarios observados, eventos evaluables, pertenencia a la muestra principal y motivos de exclusión. Los motivos pueden concurrir: no sumarlos como usuarios distintos.
- `coverage.csv`: comentarios, usuarios con ID, videos y canales del snapshot, los historiales examinados y la muestra principal, por fuente. Son conteos del marco observado, no probabilidades de inclusión.
- `event_composition.csv`: eventos colapsados por comentario/bloque, valencia y ámbito examinado/principal; incluye neutral, mixed y not_evaluable cuando estén presentes.
- `annotation_support.csv`: unidades objetivo antes del colapso, objetivos desconocidos y comentarios sin objetivos explícitos. La ausencia de objetivo no se convierte en neutralidad.
- `summary.json`: base humana/provisional, independencia de modelos, denominadores y evaluación separada de la precisión del gap.

Se conservan AP_In, AP_Out, AP y spread, así como el gap principal, la partición A/B, el bootstrap cruzado de usuarios/canales y las sensibilidades. Las métricas no se redefinen. Los neutrales evaluables permanecen en los denominadores.

El semiancho observado es `(ci_high-ci_low)/2`. `precision_status` es `target_met` si no supera la meta prevista .20, `target_not_met` si la supera y `not_estimable` si no hay un intervalo válido. Es una comparación con una meta de planificación propia, no una norma de revista, y no incluye el error no cuantificado de un único anotador.

`gap_evidence` distingue intervalo totalmente positivo (`positive_relative_favoritism`), totalmente negativo (`negative_relative_favoritism`), intervalo que incluye cero (`inconclusive`) y ausencia de estimación. Estos códigos describen el intervalo; las sensibilidades y los componentes intragrupo/externo siguen siendo necesarios para la interpretación. Un gap positivo no demuestra por sí solo rechazo externo. Un intervalo que incluye cero tampoco demuestra ausencia de efecto.

Si falta precisión o el efecto no es concluyente, se informa tal resultado. No se activan nuevos muestreos, entrenamientos, cambios de criterios o ajustes de umbrales. Una futura ampliación requeriría otro diseño explícito; no se repite el análisis hasta obtener significación.

La actualización del bloque generado de AGENTS ocurre solo al terminar correctamente un análisis final real. La implementación y los preflight no sustituyen resultados existentes ni modifican el manuscrito. Los informes existentes no se sobrescriben.
