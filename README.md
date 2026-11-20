# SA Polarization

Pipeline reproducible para extraer comentarios públicos de YouTube, preprocesarlos localmente, clasificarlos en Kaggle con GPU y generar resultados y gráficas en local.

## Estudio ampliado autorizado el 2026-11-17

La [medición anotada puede cerrarse aunque fallen los clasificadores](docs/contingencia_medicion_anotada.md). `targeted publication measurement-preflight` comprueba historiales completos y revisiones humanas sin exigir modelos; el análisis final informa cobertura y precisión observada por separado del desempeño automático.

Disponible el [diagnóstico local de desarrollo y preparación de evaluación](docs/diagnostico_desarrollo_publicacion.md): `targeted publication diagnose-development` genera un informe sellado sin reentrenar; `targeted publication evaluation-preflight` comprueba requisitos en modo de solo lectura. El diagnóstico ya está guardado y la evaluación espera el snapshot de captura.

La ruta nueva es [`targeted publication`](docs/estudio_publicable.md), con configuración independiente `config/targeted_publication.toml`. Busca 800 usuarios realmente comparables mediante historiales completos anotados, una referencia independiente de 3,000 comentarios y una comparación cerrada de cuatro modelos/tres semillas. Conserva la prueba final anterior, los modelos y los resultados históricos. Las propuestas IA permiten resultados provisionales; no sustituyen el cierre humano.

El estudio `ap_publication_20261117_v1` ya está preparado con 11,280 videos elegibles para captura. Para consultar o reanudar:

```bash
.venv/bin/sa-polarization targeted publication status
.venv/bin/sa-polarization targeted publication collect
```

La captura contabiliza el presupuesto compartido por día del Pacífico (`America/Los_Angeles`), como YouTube. La configuración conserva 2,500 solicitudes; con la cuota de 10,000 confirmada para este proyecto se autorizó ejecutar `targeted publication collect --daily-api-budget 9000`, reservando 1,000 unidades. La opción solo afecta a la ejecución y no modifica el estudio protegido. No repetir `prepare` ni sobrescribir la ejecución. La [guía completa](docs/estudio_publicable.md) documenta captura, migración del contador, congelación, anotación y cierre.

El entrenamiento ampliado terminó y sus 12 ajustes están importados y verificados. `targeted publication training-report` reproduce la comparación local desde logits y calibración guardados: mayor macro-F1 de desarrollo, RoBERTuito 0.6439; mayor cobertura condicional de candidatos, BETO 37.16%. No habilita producción ni sustituye la evaluación independiente pendiente. No reenviar ese entrenamiento; el informe existente está sellado y no se sobrescribe.

Para mantener el trabajo independiente de la conversación, usar `targeted publication start-services --daily-api-budget 9000` y consultar `targeted publication runtime-status`. Los servicios de usuario conservan registros y se detienen ante errores; no arrancan tras reiniciar el equipo. `targeted publication audit-capture` genera el informe local del aporte de las capturas y la carga provisional de anotación. La [guía de anotación](docs/guia_anotacion_publicacion.md) explica las tandas de 50 comentarios y el benchmark ciego.

## Requisitos

- Python 3.11 o superior.
- Git y acceso SSH al repositorio.
- Una API key de YouTube Data API.
- Cuenta de Kaggle con API habilitada y acceso a aceleradores GPU.

## Instalación y credenciales

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[kaggle]'
cp -n .env.example .env
```

Completa `.env` con `YOUTUBE_API_KEY` y `KAGGLE_API_TOKEN`, o con `KAGGLE_USERNAME` y `KAGGLE_KEY`. No agregues credenciales reales al repo. El kernel de inferencia no necesita la API de YouTube.

El dataset es `josealvacornejo/sa-polarization-dat` y el kernel es `josealvacornejo/sa-polarization-inference`. El kernel usa GPU e Internet; comprueba que el acceso a Internet esté habilitado en los ajustes de sesión de Kaggle para descargar el modelo desde Hugging Face.

## Flujo principal

El trabajo habitual se divide en dos comandos:

```bash
# 1. Obtener comentarios de YouTube y generar el CSV consolidado local
sa-polarization prepare-data

# 2. Publicar ese CSV en Kaggle, inferir y producir tablas/gráficas
sa-polarization infer-results --message "Nueva inferencia"
```

`prepare-data` primero sincroniza `neutral.json` desde Kaggle, luego usa canales y periodos de `config/pipeline.toml` y preprocesa izquierda, derecha y neutral. El pool local `neutral_local` (medios neutrales recolectados en YouTube) se une al `neutral.json` canónico y se traduce a `party=neutral` en el preprocesamiento, que además deduplica por `comment_id`. Revisa `AGENTS.md` para el criterio de clasificación de canales: solo entran fuentes con evidencia documentada. Requiere credenciales de YouTube y Kaggle. El grupo de origen `party=neutral` es distinto de la predicción `sentimiento=neutral`. `infer-results` crea una versión del dataset Kaggle con los datos locales, ejecuta el kernel GPU y genera resultados en `outputs/`.

La recolección conserva la caché de comentarios por video y, al reanudar, solo consulta comentarios para videos nuevos o incompletos. `target_total_comments` fija la meta total y `target_group_shares` distribuye esa meta según la composición actual; `max_videos_per_channel` limita cuántos videos recientes de cada canal se revisan dentro del periodo configurado. La meta se evalúa al terminar cada video y puede superarse ligeramente.

Para ejecutar ambas etapas de corrido existe `sa-polarization full-pipeline`. También puedes ejecutar tareas individuales: `collect`, `preprocess`, `data-publish`, `infer` y `analyze`. `data-pull` descarga los JSON/CSV de Kaggle a `data/raw/` y `data/processed/` cuando se quiere trabajar desde una copia local.

## Estudio de polarización dirigida

El comando `sa-polarization targeted --help` ofrece un flujo separado de auditoría, captura contextual, anotación, entrenamiento y contraste de valoraciones hacia actores políticos. Conserva los resultados históricos. El protocolo vigente usa propuestas IA para 2,000 comentarios y confirmación individual por un humano, incluida la prueba final; declara su menor independencia. El modo original de dos revisores sigue disponible en otras ejecuciones.

Consulta [el método y la ejecución](docs/metodo_polarizacion_dirigida.md) y [el protocolo de anotación](docs/anotacion_dirigida.md). Configuración: `config/targeted.toml`; objetivos: `config/political_targets.json`. El registro inicial debe auditarse antes de entrenar. Las nuevas salidas van a `outputs/targeted/<run_id>/` y los datos de trabajo a `data/targeted/<run_id>/`.

La [ejecución v2 activa](docs/estado_targeted_20261115_v2.md) tiene **2,000 comentarios revisados y referencia cerrada**: 1,349 revisiones heredadas y 651 nuevas (641 propuestas aceptadas, 10 corregidas). El entrenamiento inicial y las rondas de comparación terminaron y sus checkpoints están verificados. **Ningún candidato cumple todos los criterios de desarrollo; evaluación e inferencia quedan bloqueadas.** Los 500 comentarios finales siguen sin evaluar y sus etiquetas no se publicaron en Kaggle. Usar siempre `--config config/targeted_v2.toml --run-id targeted_20261115_v2`; mantener el registro congelado. Para comprobar la revisión sin escribir: `targeted assisted-import` con `--check-only`. La prueba GPU privada previa terminó y no debe repetirse.

Para validar el código sin servicios externos: `.venv/bin/python -m unittest discover -s tests -v`. El extra `targeted-training` instala dependencias GPU. `targeted kaggle-prepare --task smoke` prepara una prueba GPU privada aislada sin resultados científicos; no sustituye la validación humana.

La [ronda de entrenamiento y validación](docs/entrenamiento_validacion_dirigida.md) añade `targeted validate` para diagnosticar los pesos existentes y `targeted tune` para comparar RoBERTuito/BETO en un máximo de 12 ajustes. Ambos tienen tareas Kaggle homónimas y requieren `--experiment-id`; el experimento `development_20261115_v1` conserva el modelo anterior y excluye las etiquetas finales de todos sus paquetes. Su configuración independiente es `config/targeted_training.toml`. Un candidato seleccionado por validación todavía requiere la prueba final antes de inferencia.

La ronda terminó y se importaron sus checkpoints: 12 ajustes, macro-F1 ponderado de desarrollo 0.5289 para RoBERTuito y 0.6724 para BETO. Ninguno cumple todos los mínimos: BETO falla macro-F1 ≥0.75 y cobertura ≥60% (19.47%). `selection.json` conserva `selected=null`; los 500 finales siguen reservados y la inferencia de producción permanece bloqueada. Resumen local: `data/targeted/targeted_20261115_v2/experiments/development_20261115_v1/report/comparison.md`. Verificación local: 77 pruebas correctas.

La ronda de representación del objetivo terminó en `development_targetaware_20261115_v1`, con `config/targeted_targetaware.toml`: seis ajustes de dos variantes BETO que señalan la mención automática. Macro-F1/cobertura: CLS marcado 0.5996/21.44%; máximo de mención 0.6051/31.29%. La cobertura aumenta, pero el macro-F1 empeora respecto de BETO anterior (0.6724); **ninguna variante cumple todos los mínimos**. Checkpoints verificados y 87 pruebas locales correctas. Los 500 finales y los modelos anteriores permanecen intactos; no se habilita inferencia de producción. No repetir estos trabajos. Resultados y comandos para otra ejecución independiente en el protocolo anterior.

La [auditoría de suficiencia y sesgos](docs/diagnostico_datos_dirigido.md) añade `targeted diagnose-data --diagnostic-id <id>` para examinar localmente composición, oportunidad de comparación por usuario, soporte humano y errores de validación existentes. No requiere GPU ni servicios externos, conserva la prueba final y escribe en `outputs/targeted/<run_id>/diagnostics/<id>/`. Termina con un informe de decisión; no inicia nuevas anotaciones, entrenamientos ni análisis AP.

La [ampliación auxiliar IA autorizada](docs/ampliacion_ia_dirigida.md) incorpora 2,000 comentarios adicionales anotados por el agente, sin confirmación humana, exclusivamente al entrenamiento. `ai-augment-export` e `ai-augment-import` mantienen procedencia y separación de la referencia humana. Experimento `development_ai_augmentation_v1`, configuración `config/targeted_ai_augmentation.toml`: una receta BETO, tres semillas y peso IA 0.25 relativo al humano de igual clase. La evaluación usa los mismos 300 comentarios humanos de validación; los 500 finales siguen reservados.

Esta ronda terminó en Kaggle privado v5 COMPLETE y sus resultados/checkpoints están importados: cobertura **19.47% → 49.99%** (izquierda **4.60% → 57.03%**), macro-F1 ponderado **0.6724 → 0.6636**. Las precisiones positiva/negativa aceptadas son 85.42%/85.02%. Falla los mínimos F1/cobertura y la regla de mejora parcial; `selected=null`. La ronda queda cerrada sin abrir prueba ni producción. El informe y su verificación están en `experiments/development_ai_augmentation_v1/report/` y `execution_report.json`; no repetir v5.

El siguiente paso es [preparar una comprobación por usuario](docs/cohorte_validacion_usuario.md): `targeted design-user-validation --config config/targeted_v2.toml --run-id targeted_20261115_v2 --cohort-id <id>`. Recalcula la elegibilidad tras excluir muestras anteriores, selecciona por defecto 100 usuarios y conserva todos sus comentarios elegibles, incluidos los no detectados como políticos. Informa el coste de escenarios de 25/50/100/200 usuarios. Es preparación local sin etiquetas nuevas, entrenamiento, AP ni apertura de prueba; `--seed` solo modifica selección, conservando A/B del método.

Preparación completada: `user_validation_20261116_v1`, **100 usuarios/1,887 comentarios** dentro de un marco de 304 usuarios potenciales después de exclusiones. Se avanzó con un **piloto de 25 usuarios completos/505 comentarios**, con propuestas IA por lectura del agente, sin confirmaciones humanas ni AP calculada. Los otros 75 usuarios/1,382 comentarios siguen pendientes. Para revisar: `targeted cohort-review --config config/targeted_v2.toml --run-id targeted_20261115_v2 --cohort-id user_validation_20261116_v1`; guarda cada confirmación y permite reanudar. [Protocolo y comandos](docs/cohorte_validacion_usuario.md). Informes de diseño y propuestas en `outputs/targeted/targeted_20261115_v2/cohorts/user_validation_20261116_v1/`. 122 pruebas locales ejecutadas, una omitida.

El usuario **aplazó esas revisiones** y autorizó seguir mejorando modelos. Se completó la [combinación local de los BETO](docs/combinacion_modelos_dirigida.md), `development_blend_20261116_v1`: tres mezclas fijas, sin nuevos entrenamientos ni usar propuestas pendientes. La mezcla 50/50 alcanza macro-F1 ponderado **0.7037** y cobertura de desarrollo **40.17%**, frente a 0.6724/19.47% del anterior y 0.6636/49.99% del ampliado. Con calibración separada por video, cobertura 36.16% y precisiones positiva/negativa 80.25%/83.26%; sigue sin cumplir mínimos y `selected=null`. No repetir esta ronda ni abrir prueba/inferir producción. 128 pruebas locales ejecutadas, una omitida; referencia, cohorte pendiente y modelos conservados.

Terminó el [refinamiento humano final](docs/entrenamiento_validacion_dirigida.md#resultado-del-refinamiento-humano-final), `development_human_refinement_20261116_v1`: dataset/kernel privados v6 ready/COMPLETE, tres semillas y dos épocas fijas desde checkpoints ampliados, con 1,270 pares humanos en la fase final. F1 ponderado **0.6806** y cobertura completa **39.85%**, frente a 0.7037/40.17% de 50/50; cobertura con calibración separada **42.37%**, pero precisiones positiva/negativa **78.69%/82.55%**. No cumple mejora parcial ni mínimos: `selected=null`. Se verificaron 53 archivos exportados, 19 archivos de checkpoints y 384 originales conservados. Las revisiones siguen pendientes, los 500 finales reservados; 134 pruebas locales, una omitida. Ronda cerrada: no repetir ni promover el modelo.

La [preparación local incremental](docs/preparacion_local_incremental.md) puede avanzar durante la captura: `.venv/bin/sa-polarization targeted publication prepare-local --watch`. Guarda caché verificada e informes parciales sin consumir API ni crear muestras finales; `freeze` reutiliza esa caché cuando la captura esté cerrada. Para reanudar por cuota y encadenar el cierre y las primeras muestras: `targeted publication advance --watch --daily-api-budget 9000`; termina en espera de anotaciones.

## Prueba de humo histórica

Para validar el flujo con una muestra determinista del 25 % de los comentarios JSON de YouTube, ejecuta `sa-polarization smoke-test --create-dataset` la primera vez. En ejecuciones posteriores omite `--create-dataset`; se publicará una nueva versión en los recursos Kaggle privados de prueba. La prueba guarda manifiesto y resultados bajo `data/smoke-test/`, no llama a YouTube y no modifica resultados anteriores.

## Datos, resultados y configuración

Kaggle Datasets es la fuente canónica de JSON y CSV y mantiene sus archivos en la raíz. El repo de GitHub contiene código y documentación; los datos y resultados locales están excluidos de Git. Los datos de versiones anteriores de Git pueden seguir en el historial.

El pipeline usa `pyupeu/robertuito-peruvian-sentiment`, etiquetas `negative`, `neutral`, `positive`, y conserva las métricas AP, AP_In, AP_Out y spread del análisis previo. Revisa `config/pipeline.toml` antes de recolectar: canales y periodos son decisiones de investigación.
