# Polarización afectiva expresada con comentarios de YouTube

## Estado y alcance

El método `targeted-v1` amplía el pipeline histórico. Separa fuente editorial, objetivo político y valoración dirigida. Su interpretación científica requiere una referencia humana completada bajo el protocolo autorizado y superar la prueba final; disponer de código no significa que el modelo ya esté validado. El protocolo activo es un humano asistido por IA, incluida la prueba.

El universo es el conjunto observado de participantes y comentarios conservados por YouTube, bajo los canales y ventanas configurados. La muestra de canales es intencional y los comentarios históricos tienen un tope: los intervalos describen incertidumbre condicional a este diseño, no una muestra representativa de votantes. El remuestreo no corrige por sí solo selección, contenido eliminado o errores de medición.

La fundamentación y sus límites están en las notas de Chae y Lee (2024), Miehling et al. (2025), Tran et al. (2022), Bessi et al. (2016), Lee y Kim (2026) y Martínez-España et al. (2024), vinculadas en el registro bibliográfico.

## Datos y contratos

`party` identifica la fuente y conserva su significado histórico. `target_id`, `target_group`, `entity_type`, `mention_start`, `mention_end` y `candidate_origin` identifican el objetivo. Los bloques admitidos son izquierda/derecha; `unknown` y `not_political` quedan fuera del contraste político sin eliminar sus registros de auditoría.

`comment_id`, `post_id`, `channel_id` y `user_id` conservan identidades; `parent_id` documenta la relación API con el comentario raíz. YouTube no garantiza un árbol de destinatarios discursivos: una respuesta al hilo no prueba que el ataque se dirija al autor raíz. `comment_type` distingue respuesta y primer nivel.

La fecha real de publicación del video se verifica con `videos.list`. La fecha del comentario determina `comment_stage`; la etapa histórica se conserva aparte. Solo videos y comentarios dentro de las ventanas configuradas entran al corpus principal. Las exclusiones se conservan con motivo.

Los nombres configurados `antes`, `durante` y `despues` no se equiparan automáticamente con rondas electorales: los análisis nuevos usan meses de publicación del comentario. El texto corresponde a lo recuperado en la extracción; una edición posterior no permite reconstruir su versión histórica. Se conserva `updated_at` para auditar esa limitación, y la publicación dentro de la ventana no garantiza que el texto actual sea idéntico al de esa fecha.

El panel selecciona dos videos por canal configurado y mes entre los videos observados disponibles, no de un censo completo de YouTube. Su probabilidad de selección se registra. Captura todas las páginas disponibles de comentarios/respuestas hasta completar o interrumpirse. Solo los videos terminados entran en su tabla normalizada. No se mezclan sus nuevos comentarios con el corpus histórico para fingir un diseño homogéneo.

## Clasificación y validación

Registro inicial de objetivos con fuentes externas y vigencia; alias y descubrimiento NER generan candidatos para revisión. NER no asigna ideología. El análisis principal usa menciones explícitas. Las referencias implícitas quedan fuera hasta disponer de una validación específica; no se resuelven automáticamente usando el canal.

Se anotan 2,000 comentarios (1,600 de primer nivel, 400 respuestas), sin duplicados textuales. Particiones por video: 1,200 entrenamiento, 300 validación y 500 prueba. La mitad de la asignación muestral es proporcional y la otra enriquece estratos con menciones/posibles positivos; las probabilidades de inclusión permiten ponderar la evaluación. El piloto de 200 forma parte del entrenamiento.

**Cambio autorizado el 2026-11-14:** se sustituye para la ejecución actual el acuerdo de dos revisores por propuestas de IA y confirmación/corrección individual de los 2,000 textos por un humano. Incluye la prueba final, por elección explícita del usuario. El formulario oculta fuente editorial, partición y predicciones del clasificador entrenado, pero muestra la propuesta IA. Esta referencia tiene menor independencia: aceptación o corrección de propuestas no mide acuerdo entre humanos, y el rendimiento contra ella no elimina un posible sesgo compartido o de anclaje. Propuestas, decisiones y procedencia se guardan por separado. El modo original de dos humanos sigue disponible para otras ejecuciones. No se entrenará antes de confirmar todos los textos y revisar el registro.

Tras el piloto se confirmó que las identificaciones que requieren título o comentario padre se conservan para sensibilidad y se excluyen del principal, aunque el humano haya reconocido su referente. Las anotaciones humanas no se reescriben: una política de evidencia vinculada al muestreo separa objetivos contextuales al producir `gold.csv` y `contextual_annotations.csv`. Los hashes de política y ambos artefactos se verifican antes de entrenar. La referencia contextual por sí sola no valida la resolución de referencias en todo el corpus.

Se ajusta RoBERTuito base como clasificador de pares objetivo–texto, con cinco etiquetas: positiva, negativa, neutral, mixta y no evaluable. Entrena cinco épocas como máximo, batch 16, AdamW 2e-5, regularización 0.01, parada por pérdida de validación y tres semillas (42–44), fijando la misma revisión de Hugging Face. RoBERTuito puede admitir menos de 512 tokens: se excluyen del entrenamiento los ejemplos que no caben completos. Se conserva una predicción diagnóstica sobre la ventana de la mención, pero los contextos recortados se abstienen siempre en la inferencia principal y cuentan en el denominador de cobertura de la evaluación. No se acepta una predicción que solo vio parte de la valoración.

Las probabilidades del ensemble se calibran mediante temperatura en validación. Se selecciona el umbral mínimo de cada clase que alcance precisión ponderada ≥0.85 con al menos diez predicciones de validación; si no hay umbral, esa clase se abstiene. La confianza no mide intensidad afectiva.

La prueba incluye una comparación contra la etiqueta histórica de Robertuito de sentimiento general, restringida a exactamente los mismos pares que tengan esa salida disponible. Las respuestas nuevas sin baseline no se imputan. Esta comparación permite comprobar los errores de trasladar una etiqueta global a cada objetivo, además de reportar métricas por bloque e intervalos de validación remuestreados por video.

Criterios predictivos predefinidos: precisión/recall de objetivos ≥0.90/0.80; macro-F1 positiva/negativa/neutral ≥0.75; precisión positiva y negativa aceptadas ≥0.85; cobertura de objetivos evaluables ≥0.60. Son decisiones de diseño, no estándares universales. κ ≥0.70 se exige solo en el modo original de dos humanos; no se aplica a una revisión asistida individual. Los objetivos omitidos por alias/NER se contabilizan como falsos negativos en la evaluación de extracción y cobertura.

Antes de preparar o abrir la prueba se comprueba que la calibración íntegra de desarrollo permita aceptar tanto positivos como negativos. El umbral 1.01 significa abstención total: si alguna de esas clases queda deshabilitada, la prueba no puede superar sus criterios y permanece reservada mientras se mejora el modelo con desarrollo. Esta comprobación no puntúa la prueba ni sustituye sus métricas, y no modifica los mínimos establecidos.

## Revisión v2 y procedencia de etiquetas

La [ejecución v2](estado_targeted_20261115_v2.md), autorizada tras completar los 2,000 originales, usa registro/configuración independientes. El extractor se amplió con los 1,500 originales de desarrollo; la prueba anterior se retiró sin puntuación. La identidad no documentada permanece `unknown` y no entra al contraste de bloques. Fuentes y límites en [registro de actores v2](referencias/registro-actores-v2.md).

Para aprovechar anotaciones confirmadas, desarrollo se selecciona prioritariamente dentro del marco revisado, repartiendo sus videos 80/20 con semilla 43 y completando cuotas cuando falta disponibilidad. Las probabilidades registran selección original por selección condicional. El desarrollo reutilizado no estima rendimiento independiente. La prueba nueva usa la partición por video con semilla 43 y excluye todos los videos y textos normalizados de la muestra anterior: 400 comentarios principales y 100 respuestas. Se mantienen 1,200/300/500 y 1,600 principales/400 respuestas. El rendimiento final se limita a ese marco elegible; no es una estimación poblacional de YouTube.

Solo se heredan decisiones con contexto idéntico, transformación explícita de identidad y mención comprobable; nuevos candidatos o identidades incompatibles requieren confirmación. Las decisiones originales se conservan sin modificar y las herencias se guardan aparte, sin crear valores humanos de `review_complete`. La integridad de fuentes, herencias y política contextual se verifica antes de cerrar y entrenar. Las notas de asistencia y procedencia se conservan en los manifiestos locales y remotos.

`annotation-revise --from-run` prepara la ejecución derivada sin sobrescribir el origen. `assisted-import --check-only` diagnostica sin escribir ni consumir prueba. No se muestran precisión/recall sobre un subconjunto pendiente seleccionado por compatibilidad. La preparación del entrenamiento v2 exige también que la extracción en entrenamiento y validación completos supere sus mínimos; así se detiene un fallo conocido antes de usar GPU o abrir prueba. Los umbrales predictivos originales no cambian.

## Afinidad y resultados

Una partición determinista por video separa A (asignación) y B (evaluación), con semilla 42. El hash da probabilidad 1/2 a cada video y no consulta sus etiquetas de sentimiento. La afinidad requiere dos positivos dirigidos en videos distintos y al menos dos tercios de los positivos hacia un bloque. Empates y ausencia de evidencia producen `Undetermined`.

La unidad de conteo es comentario–bloque objetivo. Menciones repetidas no duplican el evento; signos contrarios dentro del mismo bloque se consideran mixtos. Una abstención no se convierte en neutralidad. Solo positivos, negativos y neutrales aceptados entran al balance.

En B, `AP_In=Pos_in−Neg_in`, `AP_Out=Pos_out−Neg_out`, `AP_target=AP_In−AP_Out`. El grupo externo es únicamente el bloque opuesto, independientemente del canal. Los conteos de cobertura parcial conservan `out_observed=false`; un cero por ausencia de datos no se interpreta como neutralidad afectiva.

El contraste normalizado es `gap=(Pos_in−Neg_in)/N_in − (Pos_out−Neg_out)/N_out`, definido solo con ambos bloques observados, tres eventos y dos videos de evaluación. Las medias dan igual contribución a cada usuario. Los neutrales de sentimiento sí cuentan en N; mixtos y abstenciones se informan aparte. Spread conserva la fórmula acumulativa adaptada con el total de eventos políticos evaluables: no es distancia ideológica ni elimina totalmente volumen.

Contrastes preespecificados: medias de valoración propia y externa, gap global, gap por afinidad y diferencia derecha−izquierda. IC95% mediante 2,000 remuestreos cruzados: se remuestrean canales dentro del pool de fuente y usuarios independientemente. La contribución duplicada de un usuario pondera su promedio, no multiplica artificialmente sus conteos individuales. La dependencia por video está contenida en el canal. Valores p de bootstrap centrado, aproximados, y ajuste Holm; informar réplicas sin cobertura.

Sensibilidades: invertir A/B, semillas 43–52, requisitos de actividad, canales omitidos, umbrales de confianza, actores dominantes, contexto largo y panel. Se repondera además la evaluación por el inverso del volumen de cada canal o video, manteniendo la afinidad primaria, para examinar desequilibrios de contribución; esas variantes no redefinen los conteos oficiales. Los resultados mensuales describen cambios de expresión y composición; no prueban que un evento causó cambios individuales.

Participación: proporción de comentarios por fuente, participación en ambos bloques, concentración y Jaccard de usuarios entre canales. El modelo nulo permuta fuentes dentro de mes conservando actividad individual y volumen de fuente/mes (999 permutaciones). No equivale a historial de visualización ni valida identidad partidaria.

Como comprobación adicional, se permutan las etiquetas izquierda/derecha entre canales conservando su número y toda la red de participación fija. Este segundo nulo mantiene la agrupación por video/canal que rompe el primero; exige intercambiabilidad de las etiquetas bajo su hipótesis nula, no un muestreo aleatorio de canales de Perú. Los dos estadísticos (participación cruzada y concentración) bajo los dos nulos forman una familia de cuatro pruebas con Holm. Se reportan además umbrales de 1, 3, 5, 10 y 20 comentarios. La prueba principal de participación se restringe a ≥5 comentarios políticos para evitar interpretar a quienes solo comentaron una vez como evidencia de segregación.

## Ejecución

Para continuar el trabajo ya preparado, usar los comandos con `--config config/targeted_v2.toml` del [estado activo](estado_targeted_20261115_v2.md). Los ejemplos generales siguientes corresponden a crear otro estudio desde cero; no repetirlos sobre las ejecuciones existentes.

```bash
sa-polarization targeted audit --run-id estudio
sa-polarization targeted collect-context --run-id estudio --metadata-only
sa-polarization targeted collect-context --run-id estudio
sa-polarization targeted targets --run-id estudio
# Revisar actores/alias. --ner requiere instalar transformers y descargar su modelo.
sa-polarization targeted annotation-export --run-id estudio
# Modo vigente: propuestas IA y confirmación individual de un humano.
sa-polarization targeted assisted-init --run-id estudio
# El agente lee los textos e importa lotes JSON, sin servicios de pago adicionales.
sa-polarization targeted assisted-proposals --run-id estudio --batch lote.json
sa-polarization targeted assisted-review --run-id estudio --pilot-only
sa-polarization targeted assisted-import --run-id estudio --pilot-only
# Tras revisar el piloto, importar propuestas restantes y completar todas las revisiones.
sa-polarization targeted assisted-review --run-id estudio
sa-polarization targeted assisted-import --run-id estudio
sa-polarization targeted kaggle-prepare --run-id estudio --task train
```

Los archivos preparados contienen instrucciones para publicación privada y ejecución. `kaggle-prepare` no llama a Kaggle. Confirmar versión ready y conectividad efectiva antes del push. Importar el archivo `targeted_result.tar.gz` con `targeted kaggle-import`. Repetir preparación/importación para `--task evaluate` y luego `--task infer`; en un entorno GPU también existen `targeted train`, `evaluate` e `infer`.

El modo original omite los comandos `assisted-*`: usa dos formularios independientes, `annotation-import`, acuerdo κ y adjudicación según el protocolo. No mezclar los dos modos en una ejecución. Los lotes asistidos tienen forma `{"origin":"procedencia de IA", "proposals":[{"sample_id":"id", "annotations":[], "note":"explicación"}]}`; cada objetivo de `annotations` usa el mismo contrato de ID, valencia y offsets del código de anotación. Las importaciones validan IDs, menciones y etiquetas y no sobrescriben propuestas anteriores.

La CLI también permite `targeted kaggle-submit --task train --create-dataset` para la primera publicación (omitir `--create-dataset` en versiones posteriores), `kaggle-status`, `kaggle-start` y `kaggle-fetch`, siempre con `--run-id` y `--task`. `kaggle-start` exige la versión exacta esperada en estado ready; el kernel comprueba el SHA del payload montado. Una versión anterior no puede aceptarse silenciosamente.

Kaggle descomprime el archivo de entrada al publicar el dataset. El kernel verifica el SHA del manifiesto y de todos sus archivos, tanto si están expandidos como si el servidor conserva el archivo original. El paquete de entrenamiento retiene únicamente etiquetas de entrenamiento/validación; las 500 etiquetas finales no se envían hasta la etapa `evaluate`. Un fallo de la prueba conserva su estado de apertura y sus artefactos; no habilita producción.

`--task smoke` prepara una prueba GPU sintética aislada que no necesita anotaciones, no valida el constructo y nunca actualiza el contexto productivo. La inferencia de producción exige evaluación superada. `targeted analyze` produce artefactos nuevos y actualiza el bloque generado de AGENTS conservando la comparación histórica, solo después de escribirlos y verificarlos.

`targeted analyze-activity --run-id estudio` permite ejecutar el componente conductual antes de recibir las anotaciones. Genera tablas, dos contrastes nulos, sensibilidad a actividad, solapamiento de canales y una gráfica. Actualiza su propia subsección del bloque generado después de completar los artefactos y conserva los otros estudios. No habilita AP dirigido ni se presenta como validación afectiva.

No se deben reescribir resultados o conclusiones del manuscrito como si el método dirigido ya hubiese sido validado. Su integración definitiva depende de los resultados humanos, del modelo y de la cobertura de ambas audiencias.
