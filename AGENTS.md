# Instrucciones para agentes

## Objetivo del repositorio

Mantener un pipeline reproducible de análisis de sentimiento para comentarios públicos de YouTube. La recolección y el preprocesamiento se ejecutan localmente; la inferencia usa GPU en Kaggle; las métricas, tablas y gráficas se generan localmente.

## Flujo establecido

- Las etapas principales son `prepare-data` (recolectar y preprocesar) e `infer-results` (publicar los datos preparados, inferir y analizar). `full-pipeline` ejecuta ambas; los comandos individuales siguen disponibles. Consulta `README.md` antes de operar servicios externos.
- La extracción oficial usa canales y periodos de `config/pipeline.toml`. No cambies canales, periodos ni etiquetas sin indicación explícita.
- Kaggle Datasets es la fuente canónica y conserva los JSON y CSV en la raíz. `data/raw/` y `data/processed/` son las carpetas locales que la CLI crea al descargar o recolectar.
- El kernel usa `pyupeu/robertuito-peruvian-sentiment` y conserva etiquetas `negative`, `neutral`, `positive`.
- El kernel necesita descargar el modelo desde Hugging Face. Antes de inferir, comprueba que Internet esté habilitado en los ajustes de sesión de Kaggle; `enable_internet=true` en `kernel-metadata.json` por sí solo no garantiza conectividad efectiva.
- Los resultados de inferencia se descargan a `outputs/`; las métricas AP, AP_In, AP_Out, spread y sus gráficas se generan allí.

## Secretos y datos

- Nunca leas, muestres, registres ni agregues a Git el contenido de `.env`, los tokens de Kaggle o las claves de API.
- `.env.example` solo contiene nombres de variables y valores vacíos.
- No agregues datos, salidas ni credenciales al repo. Las rutas locales de datos y resultados están ignoradas por Git.
- `data-pull` separa por extensión (JSON a raw, CSV a processed) y no sobrescribe carpetas locales existentes. No borres datos locales para resolver conflictos; informa qué carpeta debe respaldarse o retirarse.
- `smoke-test` usa una muestra determinista de los JSON compatibles en `raw_data/`, publica solo en IDs Kaggle privados de prueba y guarda cada ejecución bajo `data/smoke-test/`. No redirijas ese comando a los IDs productivos.

## Operaciones remotas

- `data-create`, `data-publish`, `infer`, `infer-results`, `full-pipeline` y `smoke-test` crean recursos, versiones o ejecuciones en Kaggle. Ejecútalos solo cuando la solicitud del usuario incluya esa operación.
- Mantén privados el dataset y el kernel salvo instrucción explícita.
- No publiques resultados ni envíes mensajes a servicios externos distintos de las operaciones Kaggle del pipeline.

## Cambios de código

- Mantén módulos importables en `src/polarization_pipeline`; no incorpores magics de Colab ni pushes de Git desde notebooks.
- Si cambia el formato de datos, actualiza conjuntamente el preprocesador y el kernel de Kaggle.
- Conserva la definición existente de métricas durante este refactor; los cambios metodológicos requieren una solicitud específica.
