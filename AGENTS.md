# Instrucciones para agentes

## Objetivo del repositorio

Mantener un pipeline reproducible de análisis de sentimiento para comentarios públicos de YouTube. La recolección y el preprocesamiento se ejecutan localmente; la inferencia usa GPU en Kaggle; las métricas, tablas y gráficas se generan localmente.

## Flujo establecido

- Las etapas principales son `prepare-data` (sincronizar el grupo neutral desde Kaggle, recolectar y preprocesar) e `infer-results` (publicar los datos preparados, inferir y analizar). `full-pipeline` ejecuta ambas; los comandos individuales siguen disponibles. Consulta `README.md` antes de operar servicios externos.
- La extracción oficial usa canales y periodos de `config/pipeline.toml`. No cambies canales, periodos ni etiquetas sin indicación explícita.
- Kaggle Datasets es la fuente canónica y conserva los JSON y CSV en la raíz. `data/raw/` y `data/processed/` son las carpetas locales que la CLI crea al descargar o recolectar.
- El kernel usa `pyupeu/robertuito-peruvian-sentiment` y conserva etiquetas `negative`, `neutral`, `positive`.
- `party` identifica el grupo de origen (izquierda, derecha o neutral); `sentimiento` contiene la predicción del modelo. No los confundas ni elimines filas neutrales antes de inferir.
- El kernel necesita descargar el modelo desde Hugging Face. Antes de inferir, comprueba que Internet esté habilitado en los ajustes de sesión de Kaggle; `enable_internet=true` en `kernel-metadata.json` por sí solo no garantiza conectividad efectiva.
- Los resultados de inferencia se descargan a `outputs/`; las métricas AP, AP_In, AP_Out, spread y sus gráficas se generan allí.

## Fuentes (canales) y criterio de clasificación

- Un canal solo entra a `[youtube.channels]` de `config/pipeline.toml` si su línea editorial tiene **fuente citable** (es.wikipedia, Media Ownership Monitor, afiliación partidaria comprobable). La clasificación es decisión de investigación y queda documentada aquí; sin evidencia, el canal queda como pendiente y no se recolecta.
- Grupos actuales y su evidencia:
  - `izquierda`: Pavel Yachay, León Moya, Marco Sifuentes (`@canalYAAAAA`), Curwen, UNANCHA TV (lista original) + `@hildebrandtensustreceOficial` (Hildebrandt, "izquierdista… antiimperialista, anticapitalista", es.wikipedia *Mafia caviar*), `@prensaperulibre1465` (Perú Libre, "izquierda a extrema izquierda"), `@JuntosTVoficial` (Juntos por el Perú, "partido de izquierdas"), `@PartidoComunistaPeruano`, `@veronikamendoza_peru` (JP/Frente Amplio).
  - `derecha`: La Roro, Todo Good, Paolo Benza, Mi rinconcito favorito, Libertando Perú (lista original) + `@willaxtv` (Willax, "tendencia conservadora", es.wikipedia), `@DiarioExpreso_Perú` y `@diariolarazon_peru` (es.wikipedia *Conservadurismo en el Perú*: "medios de corte mayormente conservador, como los diarios La Razón y Expreso, y el canal Willax"), `@DiarioPeru21` ("postura neoliberal", es.wikipedia *Perú 21*), `@FuerzaPopularPeru` ("derecha a extrema derecha", es.wikipedia).
  - `neutral_local`: medios establecidos sin partido propio (`@cronicatv`, `@panoramaptv`, `@atvnoticias`, `@latinanoticias`, `@exitosape`, `@24horasperu`, `@tvperunoticias`, `@Panamericana-Noticias`, `@tvperu` [TV Perú, canal estatal 7; es la continuación de RTP, hoy "Radio Televisión Peruana" redirige a TV Perú en es.wikipedia], `@radionacionaldelperu`). Cuidado: `@rtp` es RTP **Portugal** y `@Radiotelevisionperuana`/`@rtpnoticias648` son canales muertos (sin videos desde 2016/2018).
- **Pendientes de clasificar** (no agregar hasta documentar aquí la evidencia): `@IdeeleradioNHD` (Ideeleradio pertenece al IDL, no a un partido), `@SoloFonseca`, `@nosoymermelero`, `@wayka` (DDHH/culturales, sin línea partidista comprobable), `@antaurohumalaoficial` (etnocacerismo/etnonacionalismo, no encaja en izq/der), `@IDLReporterosperu`, `@convocape`, `@OjoPúblicoPE` (periodismo de investigación independiente), `@laizquierdadiariocom` (línea clara pero canal internacional, validar contenido peruano), `@pbo`, `@francogaleano8826`, `@TUESTASINFILTRO`, `@jaimebayly1`, `@elrinconpolitico` (sin fuente de línea editorial), `@LaRepublica` (Media Ownership Monitor: centro-izquierda) y `@DiarioElComercio` (Grupo El Comercio citado como conservador), `@nmas`, `@singuionlr`, `@ipe_peru`, `@Capital21_Tv`, `@EpicentroTV`, `@altoalcrimen`.
- `neutral_local` es un pool local que `preprocess.file_party` traduce a `party=neutral` y que se fusiona con el `neutral.json` canónico de Kaggle; `collect` se niega a escribir sobre ese archivo canónico. El preprocesador deduplica por `comment_id` por si ambos comparten videos.
- La recolección guarda `data/raw/<pool>.json` tras cada canal y corta con aviso ante `quotaExceeded`; al reejecutar `collect` solo se repiten los canales no listados en `canales_procesados`.

## Secretos y datos

- Nunca leas, muestres, registres ni agregues a Git el contenido de `.env`, los tokens de Kaggle o las claves de API.
- `.env.example` solo contiene nombres de variables y valores vacíos.
- No agregues datos, salidas ni credenciales al repo. Las rutas locales de datos y resultados están ignoradas por Git.
- `data-pull` separa por extensión (JSON a raw, CSV a processed) y no sobrescribe carpetas locales existentes. No borres datos locales para resolver conflictos; informa qué carpeta debe respaldarse o retirarse.
- `smoke-test` usa una muestra determinista de los JSON compatibles en `raw_data/`, publica solo en IDs Kaggle privados de prueba y guarda cada ejecución bajo `data/smoke-test/`. No redirijas ese comando a los IDs productivos.

## Operaciones remotas

- `prepare-data` consulta Kaggle para sincronizar `neutral.json` y YouTube para recolectar; `data-create`, `data-publish`, `infer`, `infer-results`, `full-pipeline` y `smoke-test` crean recursos, versiones o ejecuciones en Kaggle. Ejecútalos solo cuando la solicitud del usuario incluya esas operaciones.
- Mantén privados el dataset y el kernel salvo instrucción explícita.
- No publiques resultados ni envíes mensajes a servicios externos distintos de las operaciones Kaggle del pipeline.

## Cambios de código

- Mantén módulos importables en `src/polarization_pipeline`; no incorpores magics de Colab ni pushes de Git desde notebooks.
- Si cambia el formato de datos, actualiza conjuntamente el preprocesador y el kernel de Kaggle.
- Conserva la definición existente de métricas durante este refactor; los cambios metodológicos requieren una solicitud específica.
