# Estudio ampliado: polarización afectiva expresada en YouTube

Diagnóstico local ya ejecutado: [hallazgos y comprobación de requisitos de evaluación](diagnostico_desarrollo_publicacion.md). Los comandos `targeted publication diagnose-development` y `targeted publication evaluation-preflight` examinan artefactos guardados sin entrenar, consultar servicios ni abrir la prueba reservada. El informe existente del diagnóstico no se sobrescribe.

## Estado y decisiones

Estudio `ap_publication_20261117_v1`, protocolo `targeted-publication-v1`, configuración `config/targeted_publication.toml`. Deriva de `targeted_20261115_v2` sin sustituir su registro, referencia, modelos ni resultados. Las revisiones aplazadas del piloto anterior se conservan. Los 500 finales siguen reservados y no se decodifican sus anotaciones para este flujo.

El objetivo es medir **800 usuarios realmente comparables**, no 800 usuarios con menciones ni un número fijo de comentarios. El cálculo aproximado `1.96 * sqrt(4 * 2 / 800) = 0.196` usa la varianza máxima de gap en [-2,2] y **supone** efecto de diseño 2. No garantiza el margen alcanzado, un efecto positivo, diferencias entre bloques ni aceptación editorial. Véase [Lakens (2022)](referencias/lakens-2022.md).

La publicación separa la medida anotada por usuario y la comparación de clasificadores. La primera puede cerrarse aunque los modelos no sean aptos para inferencia automática del corpus. La afinidad es operacional y las inferencias corresponden a expresiones observadas en el marco de canales/videos/actores; no a votantes ni a toda la población peruana.

La [contingencia de medición anotada](contingencia_medicion_anotada.md) concreta esta separación: `measurement-preflight` comprueba la preparación humana sin exigir modelos ni predicciones. El cierre añade cobertura, motivos de exclusión y precisión estadística observada sin modificar métricas ni criterios.

## Datos y captura

`prepare` conserva el histórico y el panel con procedencia, excluye los videos de la prueba reservada por metadata y prepara los videos de canales configurados. La preparación real contiene **11,280 videos para recapturar**; no cambia canales ni enero–junio de 2026. El histórico canónico conserva sus **805,039 comentarios** y su análisis de participación anterior; no se reemplaza por la muestra anotada.

La captura enumera todas las páginas de comentarios y completa respuestas faltantes mediante `parentId`. Preserva una fila por ID, la primera observación local para duplicados y las versiones posteriores por separado. Los conflictos de autor/video detienen la integración. Las filas nuevas de videos incompletos quedan fuera del snapshot; recursos indisponibles se documentan. Capturar hoy no reconstruye textos eliminados o editados anteriormente. `parent_id` identifica el hilo API, no necesariamente el destinatario discursivo.

La configuración conserva un presupuesto de 2,500 solicitudes; la opción operativa `collect --daily-api-budget 9000` autoriza 9,000 para esta ejecución con la cuota de 10,000 confirmada por el usuario, reservando 1,000 para otros usos. No cambia el archivo de configuración ni su hash protegido. El saldo oficial del proyecto puede ser menor y la respuesta de cuota de YouTube sigue deteniendo la captura.

Todos los recolectores dirigidos contabilizan ahora por día de `America/Los_Angeles`, incluida la variación estacional, y comparten un bloqueo entre procesos. `data/targeted/api_usage_pt.json` es el contador principal; `api_usage.json` conserva el registro UTC y se sigue incrementando como espejo compatible. En la primera reserva se migra conservadoramente la suma de las fechas UTC que intersectan el día del Pacífico actual. No se borran consumos anteriores; después, los nuevos periodos PT tienen contadores propios. La reserva PT se guarda antes del espejo UTC y de la llamada a YouTube: un fallo local puede sobrecontar, pero no libera una reserva ya guardada. No ejecutar procesos con código anterior durante esta transición.

Cada ejecución deja un informe bajo `outputs/targeted/<study_id>/collection_runs/`, con presupuesto configurado/efectivo, consumo local, periodo PT, próxima renovación UTC y resultado. Los resultados distinguen `local_budget`, `youtube_quota`, `transport_error`, `api_error`, `max_videos` y `completed`; `capture_error` identifica otros errores locales y `running` un proceso todavía activo. El informe local no verifica el saldo de Google. No se prometen 282,847 comentarios nuevos: esa cifra es la suma de respuestas registradas en metadata histórica.

```bash
# Ya preparado; no repetir prepare sobre el mismo study_id.
.venv/bin/sa-polarization targeted publication status
# Reanuda sin repetir videos terminados. Se pausa al agotar cuota/presupuesto.
.venv/bin/sa-polarization targeted publication collect
# Presupuesto ampliado autorizado, sin modificar config/targeted_publication.toml:
.venv/bin/sa-polarization targeted publication collect --daily-api-budget 9000
# Solo después de completar toda la captura o registrar indisponibilidad.
.venv/bin/sa-polarization targeted publication freeze
```

`freeze` crea la unión versionada, el marco de usuarios y la muestra independiente. Una cuota sin soporte produce un error, no una sustitución silenciosa. Se puede corregir una preparación fallida antes de sellar; una vez congelado, sus archivos y registro son inmutables.

## Cohorte y referencia independiente

La oportunidad estructural y A/B conservan semilla 42 y mínimos anteriores. Los usuarios se ordenan por SHA-256 de `ap-publication:57:<user_id>`. Cada lote incorpora los siguientes 100 usuarios, con **todos** sus comentarios disponibles en el marco, incluidos aquellos sin candidatos. Se examina el prefijo completo: no se seleccionan usuarios por sus propuestas, AP, precisión del modelo ni significación.

`next` exige propuestas completas de los lotes previos; `next --stage final` exige decisiones humanas completas. Detiene nuevas propuestas al alcanzar 800 comparables provisionales; las correcciones humanas pueden exigir continuar el mismo orden. Si se agota el marco, se informa el tamaño alcanzado. El análisis primario usa los primeros 800 que califican, manteniendo todos los demás examinados en la auditoría. No se atribuye la probabilidad ficticia 800/N a los usuarios potenciales ni se aplican pesos de muestreo por comentario a esta cohorte.

La referencia independiente contiene 3,000 comentarios: 1,000 con candidatos de izquierda, 1,000 de derecha, 500 solo desconocidos y 500 sin candidatos. Menciones a ambos bloques se asignan por hash a una cuota. La selección es proporcional por fuente/mes/tipo dentro de cada cuota, con al menos una observación por estrato y probabilidades explícitas. Excluye videos/textos utilizados antes en referencias y entrenamiento auxiliar. Todos los objetivos del texto requieren anotación; no solo los candidatos mostrados.

```bash
.venv/bin/sa-polarization targeted publication benchmark-init
.venv/bin/sa-polarization targeted publication next
.venv/bin/sa-polarization targeted publication proposals --sample cohort_0001 --batch lote.json
# Completar primero el benchmark a ciegas para reducir exposición previa.
.venv/bin/sa-polarization targeted publication review --sample benchmark
.venv/bin/sa-polarization targeted publication reference-close --sample benchmark
# Después repetir propuestas/next y revisiones completas de cohorte en orden.
.venv/bin/sa-polarization targeted publication review --sample cohort_0001
```

La [guía de anotación por tandas de 50](guia_anotacion_publicacion.md) explica exportación, progreso y reanudación; `review` procesa la primera tanda pendiente o la indicada con `--batch-number`. Cada carpeta de anotación tiene muestra sellada, cola sin usuario/fuente/bloque/fold, propuestas IA, lotes con procedencia y formulario humano separado. Lote JSON: `sample_sha256`, `origin`, `proposals`; cada propuesta contiene `sample_id`, `annotations`, `note`. Cada anotación usa `target_id`, `valence`, `mention_start`, `mention_end`; `unregistered:nombre` permite registrar omisiones sin ampliar el registro. Las etiquetas son `positive`, `negative`, `neutral`, `mixed`, `not_evaluable`. La política principal es explícita; no resolver pronombres por título/padre ni usar intensidad de confianza como intensidad afectiva.

La cohorte utiliza revisión asistida; el benchmark solicita anotación humana ciega, ocultando propuestas y predicciones. Puede avanzarse con propuestas IA y análisis **provisionales**, que no se denominan referencia humana ni exactitud independiente. Un único revisor no permite estimar acuerdo entre humanos. Las referencias cerradas no se reescriben.

## Comparación cerrada de modelos

RoBERTuito, BETO, BERTIN/RoBERTa y XLM-RoBERTa; tres semillas 42/43/44: máximo **12 ajustes completados**. Revisiones de Hugging Face congeladas en la configuración. No se repiten búsquedas previas ni se incorporan etiquetas de la cohorte o del benchmark al entrenamiento.

Desarrollo procede exclusivamente de la referencia humana v2 ya cerrada. Sus hashes se verifican; las filas `test` se descartan **antes de decodificar annotation_json**. La preparación real recuperó **1,291 pares de entrenamiento y 278 de validación**; los comentarios sin candidatos no producen pares de entrenamiento. El contexto completo común a los cuatro tokenizadores se determina en GPU y reduce ambos conjuntos de la misma forma antes de ajustar o seleccionar checkpoints. Se exportan los IDs de ese subconjunto.

Receta común: pares objetivo/texto y cinco clases; AdamW 2e-5, weight decay .01, lote efectivo 16 mediante microbatches de 4, clip 1, máximo ocho épocas y paciencia dos. Pesos de clase inversos a raíz de frecuencias. RoBERTuito usa `pysentimiento==0.7.3`, `preprocess_tweet(lang="es", preprocess_handles=False)`; los demás, texto original. Se conserva la fuente original de texto y offsets. Entradas recortadas siempre abstienen; sus ventanas son diagnósticas. Temperatura y umbrales solo con validación, promedio de probabilidades de tres semillas.

```bash
# Prepara archivos privados; por sí solo no inicia GPU.
.venv/bin/sa-polarization targeted publication train
# Primera publicación del recurso privado; omitir --create-dataset en versiones posteriores.
.venv/bin/sa-polarization targeted publication remote --task train --operation submit --create-dataset
.venv/bin/sa-polarization targeted publication remote --task train --operation status
# Solo arranca cuando la versión exacta publicada está ready.
.venv/bin/sa-polarization targeted publication remote --task train --operation start
.venv/bin/sa-polarization targeted publication remote --task train --operation fetch
# Recalcula el diagnóstico local desde los logits importados, sin GPU ni prueba.
.venv/bin/sa-polarization targeted publication training-report
```

El kernel comprueba hashes del payload, GPU efectiva y descarga de modelos; conserva versiones reales de paquetes. Usa Transformers 4.57.6 y pysentimiento 0.7.3. Los checkpoints parciales se conservan; un ajuste interrumpido no se repite automáticamente. Los recursos son distintos de los históricos y dirigidos previos. La descarga exige la versión exacta del kernel y verifica integridad/procedencia antes de importar.

`training-report` escribe una comparación sellada en `outputs/targeted/<study_id>/training_development/` y no sobrescribe un informe existente. Verifica el macro-F1 remoto, reconstruye el promedio de probabilidades de las tres semillas y aplica la temperatura y los umbrales guardados. Su cobertura es **condicional a los pares candidatos con contexto común**; no incluye las omisiones del extractor ni equivale a cobertura integral. No modifica calibración, selecciona modelos ni habilita producción.

**Ejecución iniciada:** dataset privado versión 1 confirmado ready; kernel privado real `josealvacornejo/sa-polarization-publication-train/1` enviado una sola vez. Kaggle derivó el slug del título; se verificaron código y privacidad mediante pull de esa versión y se corrigió exclusivamente la referencia local. No reenviar el entrenamiento ni usar otro slug/latest para consultar o descargar. La captura quedó pausada por presupuesto con 1,176 videos completos y uno parcial; `collect` reanuda al disponer de presupuesto diario.

**Cierre del entrenamiento, 2026-11-18:** versión 1 COMPLETE, resultados importados, 99 archivos verificados y 12 ajustes completados. El conjunto común contiene 1,148/1,291 pares de entrenamiento y 264/278 de validación: la capacidad efectiva de RoBERTuito es 128 tokens; BETO, BERTIN y XLM-RoBERTa admiten 512. Los cuatro modelos usan los mismos pares completos.

| Modelo | Macro-F1 de desarrollo | Precisión positiva/negativa aceptada | Cobertura condicional de pares candidatos |
|---|---:|---:|---:|
| RoBERTuito | 0.6439 | 85.76% / 95.35% | 24.46% |
| BETO | 0.4768 | 86.22% / 88.44% | 37.16% |
| BERTIN | 0.4553 | 85.02% / sin predicciones | 3.70% |
| XLM-RoBERTa | 0.4278 | 85.11% / sin predicciones | 14.95% |

Los cuatro deshabilitan neutrales por calibración. BERTIN y XLM-RoBERTa también deshabilitan negativos. Ninguno alcanza macro-F1 .75; no se habilita producción ni se abren los 500 finales. Son cifras de validación reutilizada/asistida; la cobertura condicional no sustituye la evaluación integral independiente. El informe local incluye denominadores, umbrales y métricas por semilla; no comparar directamente estas cifras con rondas previas que usaron otra receta o subconjunto. Se ejecutaron 151 pruebas locales: 150 correctas y una omitida por dependencias GPU.

Registro histórico antes de la ampliación de presupuesto: la segunda tanda terminó con 2,334 videos completos, uno parcial y 8,945 sin iniciar; 194,510 comentarios capturados dentro de ventana, incluidas 47,537 respuestas. Frente al histórico específico del estudio, 46,548 comentarios son nuevos y 46,077 de ellos son respuestas. La unión parcial de auditoría tiene 807,387 comentarios, pero no se congeló ni sustituyó el corpus canónico. El siguiente día UTC ya no determina la renovación del presupuesto local: ahora se utiliza medianoche del Pacífico (03:00 de Lima durante noviembre). Los informes de `collection_runs/` y los estados de captura dan el avance posterior. No hay reanudación automática tras una pausa; congelación, muestras y referencia nueva siguen pendientes mientras no termine la captura.

Una vez importados los checkpoints y preparadas todas las muestras que se compararán:

```bash
.venv/bin/sa-polarization targeted publication predict
.venv/bin/sa-polarization targeted publication remote --task predict --operation submit
.venv/bin/sa-polarization targeted publication remote --task predict --operation status
.venv/bin/sa-polarization targeted publication remote --task predict --operation start
.venv/bin/sa-polarization targeted publication remote --task predict --operation fetch
.venv/bin/sa-polarization targeted publication benchmark --stage provisional
# Tras la anotación humana independiente:
.venv/bin/sa-polarization targeted publication benchmark --stage final
```

Predicción recibe candidatos/textos y checkpoints, nunca etiquetas nuevas. El benchmark separa rendimiento integral (incluye objetivos omitidos) y clasificación condicional con contexto completo común. Informa macro-F1, cobertura, precisiones aceptadas, confusiones, IC95% por video y seis contrastes macro-F1 con Holm. La comparación con sentimiento general histórico usa exactamente el mismo subconjunto con baseline disponible. La comparación AP/gap por usuario es diagnóstico de medición en historias que pueden compartir desarrollo; no se presenta como exactitud predictiva independiente. No se imputan abstenciones a comentarios fuera del trabajo de predicción.

## Resultados y cierre

```bash
# Comprobación de solo lectura, independiente de la comparación automática:
.venv/bin/sa-polarization targeted publication measurement-preflight
.venv/bin/sa-polarization targeted publication analyze --stage provisional
# Continuar revisiones/lotes si las correcciones reducen comparables:
.venv/bin/sa-polarization targeted publication next --stage final
.venv/bin/sa-polarization targeted publication analyze --stage final
```

Afinidad en A: mayoría positiva única, >=2 positivos en >=2 videos y cuota dominante >=2/3. Evaluación en B: ambos bloques, >=3 eventos y >=2 videos. Se colapsa por comentario/bloque; la fuente neutral no es un tercer bloque objetivo. Los neutrales evaluables cuentan en denominadores; mezclas y ausencias no se transforman en neutralidad.

Se conservan AP_In, AP_Out, AP y spread; contraste principal `gap=(Pos_in-Neg_in)/N_in-(Pos_out-Neg_out)/N_out`. Igual contribución por usuario. IC95% con 2,000 remuestreos cruzados de usuarios/canales estratificados por fuente, recalculando afinidad/elegibilidad; >=80% de réplicas válidas o insuficiencia explícita. Holm solo en los contrastes secundarios. Sensibilidades: A/B invertido, equilibrio por video, exclusión de los tres actores más frecuentes uno a uno e histórico sin ampliación, sobre los mismos usuarios primarios.

`gap>0` mide favoritismo relativo; no prueba por sí solo valoración externa negativa, intensidad psicológica, segregación ni causalidad. Los resultados se interpretan con sus intervalos y sensibilidades. Un nulo o una estimación imprecisa no se convierte en evidencia afirmativa cambiando los criterios.

Salidas locales bajo `outputs/targeted/<study_id>/`; datos bajo `data/targeted/<study_id>/`, ignorados por Git. Cada análisis crea artefactos y manifiesto; los anteriores no se sobrescriben. Solo el cierre final actualiza su propia subsección generada en AGENTS. El manuscrito histórico permanece protegido mientras falte el cierre humano y estadístico; la integración editorial utilizará los artefactos finales y las correcciones interpretativas pendientes. Ningún comando de este flujo abre la prueba histórica ni habilita producción automática del corpus.
