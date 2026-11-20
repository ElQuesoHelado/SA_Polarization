# Preparación de una comprobación por usuario

El usuario eligió mantener la AP individual como objetivo principal. Después de cerrar la ampliación IA, `design-user-validation` dimensiona y prepara una cohorte para comprobar la medida, sin generar etiquetas, asignar afinidad, calcular AP ni iniciar entrenamiento. La continuación añade un piloto de propuestas IA y un formulario humano separado, descritos al final. Los 500 comentarios finales siguen reservados.

## Diseño

- Fuente: exclusivamente `corpus_main.csv` íntegro del estudio v2, con registro congelado y referencia humana cerrada. No se mezcla el panel ni se consulta YouTube/Kaggle.
- Exclusiones: usuarios, videos, identificadores de comentario y textos normalizados de los manifiestos de muestreo humano original/v2 y de las muestras auxiliares de los experimentos. Se aplican a todas las particiones, incluida prueba, usando solo metadata; no se decodifican sus anotaciones. Los modelos no se vuelven a entrenar.
- Elegibilidad: después de excluir filas se recalcula la oportunidad estructural. A requiere al menos dos menciones de un mismo bloque en dos videos; B, menciones de ambos bloques, al menos tres eventos comentario–bloque y dos videos. Una mención puede resultar falsa, neutral o negativa: estos requisitos no confirman afinidad ni comparación afectiva válida.
- La partición A/B conserva la función por video y semilla 42 del método. `--seed 57` gobierna únicamente la selección de usuarios, no cambia esa partición.
- Los usuarios elegibles se ordenan por SHA-256 de `user-cohort:<semilla>:<user_id>`. Se seleccionan los primeros `--users`, sin usar sentimientos, afinidad, fuentes editoriales o AP. La probabilidad de inclusión operacional es `n/N` dentro de este marco; su inversa corresponde a usuarios. No reutilizar los pesos originales de muestreo por comentario como pesos de esta cohorte.
- Se exportan **todos sus comentarios disponibles en los videos elegibles**, sin tope, sin truncar textos y sin filtrar por coincidencias del extractor. Se conservan textos sin candidatos para poder comprobar omisiones. No se trata del historial completo de esos usuarios en YouTube.

El valor por defecto de **100 usuarios** es un tamaño operativo para dimensionar el trabajo, no una justificación de potencia estadística ni un compromiso de revisión humana. Los escenarios anidados de 25/50/100/200 usuarios muestran el número real de comentarios a leer. No se eligen usuarios por el signo de un resultado.

## Comando y artefactos

```bash
.venv/bin/sa-polarization targeted design-user-validation \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --cohort-id user_validation_20261116_v1 --users 100 --seed 57
```

El comando rechaza sobrescribir cualquiera de las carpetas de la cohorte. Una preparación fallida conserva su manifiesto de error; usar otro identificador después de resolver el motivo. Rechaza referencia/corpus/registro alterados, prueba abierta y tamaños mayores al marco elegible; no sustituye silenciosamente el tamaño ni las exclusiones.

En `data/targeted/<run_id>/cohorts/<cohort_id>/`:

| Archivo | Contenido |
|---|---|
| `eligible_users.csv` | Marco posterior a exclusiones, actividad y orden reproducible. No contiene afinidad. |
| `selected_users.csv` | Selección y probabilidad/peso por usuario, condicionados a ese marco. |
| `comments.csv` | Texto íntegro, identidad, fold A/B e indicios del extractor para todos los comentarios elegibles seleccionados. Sin predicciones afectivas. |
| `reading_queue.csv` | Texto e indicios de objetivo (identidad/nombre/offsets), sin usuario, fuente, fold, bloque, sentimiento ni confirmaciones humanas. No es una referencia anotada. |
| `protected_inputs.json` | Hashes de archivos que deben conservarse durante la preparación. |

En `outputs/targeted/<run_id>/cohorts/<cohort_id>/`: `report.md`, `summary.json`, `cost_scenarios.csv`, `fold_workload.csv` y `manifest.json`. El manifiesto se cierra solo tras verificar originales y artefactos. Los datos/salidas permanecen ignorados por Git. El manuscrito y el bloque productivo generado no se actualizan porque esta etapa no produce análisis de producción.

## Comprobación prevista y límites

La referencia futura debe distinguir propuestas IA y decisiones humanas, con procedencia explícita; una anotación IA sola no valida el modelo. Esta preparación no solicita otra revisión ni llena `review_complete`. Se mantiene la política de objetivos explícitos: los indicios del extractor no son etiquetas correctas por definición y una mención omitida debe poder registrarse sin modificar los alias congelados.

La comprobación posterior debe evaluar asignación de afinidad en A, número de usuarios realmente comparables en B, errores/signo de AP y `gap`, exclusión por abstenciones y precisión por bloque/valencia. La regla actual de afinidad también exige mayoría única, al menos dos positivos, al menos dos videos y proporción positiva del bloque dominante ≥2/3. En B se conservan los mínimos originales. Usuarios sin evidencia suficiente permanecen indeterminados, no se convierten en neutrales ni en ausencia de polarización.

No usar la misma cohorte para corregir/entrenar el método y luego presentarla como su evaluación independiente. Antes de nuevas anotaciones o contrastes, fijar protocolo, presupuesto y separación de desarrollo/comprobación. Cualquier entrenamiento/inferencia de producción conserva los criterios vigentes y la prueba final reservada; esta preparación no los elude.

La inferencia eventual quedaría condicionada a participantes activos con menciones recuperadas y a los videos elegibles después de exclusiones. No representa a los 805,039 comentarios completos, a todos sus autores ni a votantes peruanos. Comprobar la medida puede encontrar favoritismo, rechazo, apertura o evidencia insuficiente; el diseño no presupone un resultado afirmativo.

## Preparación completada el 2026-11-16

Identificador: `user_validation_20261116_v1`. La auditoría reproduce los **3,714 usuarios potenciales** del corpus sin exclusiones. Al retirar usuarios/videos/textos ya muestreados quedan **304 usuarios estructuralmente elegibles** para esta cohorte separada. La reducción no mide pérdida de polarización: refleja las exclusiones para evitar reutilizar observaciones del desarrollo y de la prueba.

Se seleccionaron **100 usuarios y 1,887 comentarios**, con probabilidad condicional por usuario `100/304`. De esos textos, **814** tienen candidatos explícitos de bloques conocidos y **1,073** no los tienen; estos últimos permanecen en la cola para comprobar omisiones y referencias ajenas. A contiene 959 comentarios de 626 videos; B, 928 comentarios de 591 videos. Los 100 usuarios tienen comentarios en ambas particiones, sin compartir videos entre A/B. Eso no confirma valoraciones positivas ni afinidad.

| Usuarios, muestra anidada | Comentarios a leer |
|---:|---:|
| 25 | 505 |
| 50 | 905 |
| 100 | 1,887 |
| 200 | 4,712 |

Se verificaron **350 archivos protegidos sin cambios**. Pruebas locales: 116 ejecutadas, una omitida; incluyen exclusiones, selección reproducible, integridad de historias elegibles, textos largos, colas sin etiquetas y metadata de prueba con anotaciones deliberadamente no decodificables. Los nueve artefactos de la preparación quedan sellados en el manifiesto. No se generaron anotaciones ni resultados AP, no hubo operaciones remotas y los 500 finales siguen reservados.

## Piloto de propuestas preparado el 2026-11-16

Al autorizar el siguiente paso se fijaron los **primeros 25 usuarios del orden ya sellado**, con **todos sus 505 comentarios elegibles**. No se escogieron por sus propuestas, predicciones o resultados. Los otros 75 usuarios/1,382 comentarios se mantienen pendientes. Se conservan A/B y los mínimos del método. El orden de lectura se mezcla con semilla 57 y oculta usuario, fold, canal, bloque y predicciones.

Protocolo `targeted-user-cohort-assisted-pilot-v1`: lectura directa del texto completo por el agente, propuestas IA explícitas y posterior confirmación/corrección por un humano. La asistencia y menor independencia deben declararse. Las propuestas solas no son referencia ni permiten medir exactitud del modelo, asignación correcta de afinidad o error de AP. No se rellenan campos humanos ni se reutiliza la referencia original como si correspondiera a estos usuarios. El piloto no autoriza reentrenamiento, apertura de prueba o inferencia de producción.

Los indicios del extractor pueden rechazarse: «Sánchez Carrión» es un lugar y «Diego Acuña» no es César Acuña. Se anotan también omisiones y objetivos ajenos al registro mediante `unregistered:nombre`, conservando su bloque desconocido. No se amplía el registro ni se deduce apoyo a un candidato por criticar su cobertura mediática. Los nombres incompletos, apodos dudosos, referencias extranjeras y sarcasmo se explican en las notas para revisión. Los recuentos de propuestas no estiman precisión/recall. Una lista vacía también requiere lectura humana.

**Separación y pesos:** los usuarios pendientes comparten **138 videos** con el piloto, por lo que no se presentan automáticamente como prueba independiente. Antes de cualquier comparación se debe fijar el papel de cada subconjunto y controlar la dependencia por video/usuario. La probabilidad de selección operacional del piloto es **25/304**; la columna heredada de `pilot_sample.csv` conserva **100/304**, correspondiente a la cohorte completa. No usar esa columna como peso del piloto. La aclaración queda en `pilot_proposals.json`, sin reescribir la muestra sellada. No hay estimaciones por usuario en esta etapa.

### Comandos

La inicialización ya se ejecutó; no repetirla ni regenerar el piloto:

```bash
.venv/bin/sa-polarization targeted cohort-annotation-init \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --cohort-id user_validation_20261116_v1 --pilot-users 25
```

Las 505 propuestas quedaron importadas en cinco lotes, con procedencia y spans explícitos. `cohort-proposals --batch <archivo.json>` admite lotes de esta muestra con `sample_sha256`, `origin` y `proposals` (cada una con `sample_id`, `annotations`, `note`). Rechaza IDs ajenos/duplicados, spans inválidos, cambios en la muestra/registro/criterios y sobrescrituras; nunca escribe decisiones humanas. `scripts/view_cohort_annotation.py` sirve para leer los textos completos sin metadata de usuario o predicciones.

Cuando se realice la revisión humana:

```bash
.venv/bin/sa-polarization targeted cohort-review \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --cohort-id user_validation_20261116_v1
```

El formulario solicita tu identificador y muestra cada texto, menciones, etiquetas y nota. `a` acepta, `e` rehace todos los objetivos (incluidas omisiones), `s` deja pendiente y `q` sale. Para guardar pide confirmar con `s` que revisaste el texto completo. Guarda cada decisión y reanuda con el mismo comando. No se ejecutó ese formulario en nombre del usuario. Esta etapa deja la revisión disponible y no obliga a iniciarla inmediatamente.

Comprobar sin escribir ni cerrar la referencia:

```bash
.venv/bin/sa-polarization targeted cohort-reference-import \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --cohort-id user_validation_20261116_v1 --check-only
```

Estado al cierre de esta preparación: **505 propuestas, cero confirmaciones humanas, 505 pendientes, `ready=false`**. Solo después de completar la revisión, el mismo comando sin `--check-only` puede crear `pilot_gold.csv` y su manifiesto; no abre prueba ni habilita entrenamiento. Verifica identidad, texto, decisiones, huellas de la propuesta aceptada/corregida y conservación de una referencia ya cerrada.

En `annotations/`, bajo la cohorte: `pilot_sample.csv`, `pending_ids.csv`, `plan.json`, `state.json`, `ai_proposals.json`, `annotation_batches/` y `human_review.csv`. Los campos de decisión humana permanecen vacíos. Informes adicionales: `pilot_proposals.md/json` junto al informe de diseño; los nueve artefactos originales siguen sellados e intactos. Se auditaron los 350 archivos anteriores: 349 sin cambios y un cambio autorizado de la CLI para ofrecer este flujo. Datos originales, revisiones, registro, modelos, manuscrito y bloque generado se conservan. Pruebas locales: **122 ejecutadas, una omitida**. No hubo operaciones remotas ni nuevo AP.
