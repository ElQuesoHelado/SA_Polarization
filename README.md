# SA Polarization

Pipeline reproducible para extraer comentarios públicos de YouTube, preprocesarlos localmente, clasificarlos en Kaggle con GPU y generar resultados y gráficas en local.

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

`prepare-data` primero sincroniza `neutral.json` desde Kaggle, luego usa canales y periodos de `config/pipeline.toml` y preprocesa izquierda, derecha y neutral. Requiere credenciales de YouTube y Kaggle. El grupo de origen `party=neutral` es distinto de la predicción `sentimiento=neutral`. `infer-results` crea una versión del dataset Kaggle con los datos locales, ejecuta el kernel GPU y genera resultados en `outputs/`.

Para ejecutar ambas etapas de corrido existe `sa-polarization full-pipeline`. También puedes ejecutar tareas individuales: `collect`, `preprocess`, `data-publish`, `infer` y `analyze`. `data-pull` descarga los JSON/CSV de Kaggle a `data/raw/` y `data/processed/` cuando se quiere trabajar desde una copia local.

## Prueba de humo

Para validar el flujo con una muestra determinista del 25 % de los comentarios JSON de YouTube, ejecuta `sa-polarization smoke-test --create-dataset` la primera vez. En ejecuciones posteriores omite `--create-dataset`; se publicará una nueva versión en los recursos Kaggle privados de prueba. La prueba guarda manifiesto y resultados bajo `data/smoke-test/`, no llama a YouTube y no modifica resultados anteriores.

## Datos, resultados y configuración

Kaggle Datasets es la fuente canónica de JSON y CSV y mantiene sus archivos en la raíz. El repo de GitHub contiene código y documentación; los datos y resultados locales están excluidos de Git. Los datos de versiones anteriores de Git pueden seguir en el historial.

El pipeline usa `pyupeu/robertuito-peruvian-sentiment`, etiquetas `negative`, `neutral`, `positive`, y conserva las métricas AP, AP_In, AP_Out y spread del análisis previo. Revisa `config/pipeline.toml` antes de recolectar: canales y periodos son decisiones de investigación.
