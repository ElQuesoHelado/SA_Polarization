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
- `kaggle datasets version` es asíncrono: retorna antes de crear la versión y un `kernels push` inmediato puede montar la versión anterior. Antes de inferir, confirma que la versión nueva ya esté disponible (ver *Última ejecución registrada*).
- Mantén privados el dataset y el kernel salvo instrucción explícita.
- No publiques resultados ni envíes mensajes a servicios externos distintos de las operaciones Kaggle del pipeline.

## Cambios de código

- Mantén módulos importables en `src/polarization_pipeline`; no incorpores magics de Colab ni pushes de Git desde notebooks.
- Si cambia el formato de datos, actualiza conjuntamente el preprocesador y el kernel de Kaggle.
- Conserva la definición existente de métricas durante este refactor; los cambios metodológicos requieren una solicitud específica.

## Paper de referencia para polarización afectiva

- Referencia local: Martínez-España et al. (2024), *Methodology for Measuring Individual Affective Polarization Using Sentiment Analysis in Social Networks*, IEEE Access 12, DOI [10.1109/ACCESS.2024.3431999](https://doi.org/10.1109/ACCESS.2024.3431999), PDF en `pdfs/`. El estudio analiza Twitter durante las elecciones regionales de Murcia de 2023; combina una muestra por palabras clave (más de 29 mil tuits; 50 mil incluyendo hilos) con otra por perfiles políticos (más de 21 mil; alrededor de un millón incluyendo hilos) y etiqueta manualmente 78 entidades. No es directamente comparable con comentarios de YouTube clasificados por canal.
- **Clasificación de usuario**: asigna como `ingroup` el grupo con más interacciones positivas (`argmax Pos_i,j`); sin positivos o con empate, `Undetermined`. Considera cuatro grupos (derecha, izquierda, derecha radical, izquierda radical). Reporta 147,534 indeterminados, 55 % de la muestra. La figura 2 muestra una distribución decreciente de usuarios detectados desde izquierda radical hasta derecha radical; los autores advierten que eso puede reflejar diferencias de actividad/detección, no la cantidad de simpatizantes en la población.
- **Tablas 1–2, interacciones promedio por usuario y grupo destino**: la diagonal de interacciones positivas (ingroup) es la mayor en cada fila: derecha 9.725, izquierda 7.819, derecha radical 6.422 e izquierda radical 6.411; las desviaciones estándar son grandes (hasta 50.953 para derecha). Para interacciones negativas, el valor intragrupo es el mayor en derecha (1.063), izquierda (1.006) e izquierda radical (2.187); en derecha radical, el máximo es hacia izquierda radical (0.893 frente a 0.270 intragrupo). El artículo interpreta que prevalece el favoritismo intragrupo, aunque también hay crítica interna; destaca mayor apego positivo de la derecha y división interna de la izquierda radical.
- **Definiciones**: `AP_In = Pos_in − Neg_in`; `AP_Out = Σ_{j≠ingroup}(Pos_j − Neg_j)`; `AP = AP_In − AP_Out`. AP conserva conteos y es sensible al volumen de actividad. La medida que el paper llama `spread` es `sqrt(Σ_p (Pos_ip − Neg_ip)^2 / n_i)`, donde `n_i` cuenta las interacciones del usuario; los autores la presentan como alternativa normalizada frente a hiperactividad.
- **Tablas 3–4 y figuras 3–5, AP sin normalizar**: el paper usa media ± desviación estándar global (media 3.16, DE 23.75; cortes aproximados −26 y +26) para niveles bajo/medio/alto. Tabla 3: porcentajes bajo/medio/alto: derecha radical 0.04/93.61/6.35; derecha 0.54/92.92/6.55; izquierda 0.22/94.14/5.64; izquierda radical 1.07/94.09/4.84. Tabla 4, medias AP_In (diagonal): derecha 8.662, izquierda 6.813, derecha radical 6.151, izquierda radical 4.224. Las medias AP hacia grupos externos son mayormente negativas. Figuras 3–5 muestran distribuciones con colas largas y valores extremos; AP_Out es en su mayoría negativo, aunque hay usuarios con valores positivos. El artículo observa AP mayores con más frecuencia en derecha y derecha radical, pero describe diferencias generales modestas.
- **Tablas 5–6 y figura 6, `spread`**: niveles con bajo = 0, medio > 0 y ≤ 2.68, alto > 2.68 (media global 1.16 + DE 1.52). Porcentajes bajo/medio/alto: derecha radical 1.33/85.62/13.05; derecha 2.69/81.43/15.89; izquierda 1.95/84.70/13.35; izquierda radical 3.62/80.82/15.57. Medias (DE): derecha 1.874 (2.299), izquierda radical 1.763 (1.729), izquierda 1.748 (1.997), derecha radical 1.732 (1.670). La figura 6 muestra valores no negativos y rango más compacto que AP, con un valor extremo de izquierda. El grupo de derecha tiene la mayor proporción de nivel alto.
- **Conclusiones y cautelas estadísticas**: el artículo informa ANOVA significativo y post hoc Bonferroni: derecha difiere de los otros grupos; los otros tres no difieren entre sí. En el texto de resultados no reporta estadístico F ni valores p. Atribuye tentativamente el resultado a la victoria electoral/movilización de la derecha y limita la generalización a usuarios de redes en una elección regional; recomienda mejorar la clasificación por la alta proporción indeterminada. La figura 1 es un esquema metodológico, no un resultado empírico.
- **Comparación con el código actual (`analysis.py`)**: las fórmulas de AP y la forma de `spread` tienen estructura equivalente, pero no son métricas comparables sin ajustes/decisión metodológica. Aquí el `ingroup` se elige entre izquierda/derecha por comentarios positivos; `neutral` se incluye entre los grupos de interacción para AP_Out y `spread`. Además, el denominador local de `spread` cuenta solo comentarios con sentimiento positivo o negativo, mientras el paper describe `n_i` como total de interacciones, incluyendo neutrales. Plataforma, tipo de interacción, grupos y selección de muestra también difieren. No cambiar las métricas del pipeline solo por esta referencia; documentarla como base para evaluar opciones de estandarización.

## Última ejecución registrada (2026-11-03)

> Corrida realizada el 2026-11-03; estado remoto comprobado en modo de solo lectura el 2026-11-07. Si se vuelve a ejecutar el pipeline, actualiza esta sección.

- **Estado**: pipeline completo y verificado; no hay ejecuciones en curso ni pendientes según la consulta a Kaggle del 2026-11-07.
- **Código**: commits `3ecc187` (fuentes ampliadas + pool `neutral_local` + recolección incremental) y `55dc7eb` (`@tvperu`); árbol de trabajo limpio al guardar esta nota.
- **Datos de entrada** (`data/raw/`): 30 canales configurados (10 izquierda / 10 derecha / 10 `neutral_local`). Los JSON contienen 8,608 videos recorridos (incluidos 100 del `neutral.json` canónico) y 552,486 comentarios crudos; `preprocess` eliminó 30 duplicados por `comment_id` (16 izquierda, 12 derecha, 2 neutral) y dejó **552,456 comentarios** en `data/processed/comentarios_consolidado.csv`:

  | party | comentarios | videos con comentarios |
  |---|---:|---:|
  | izquierda | 264,520 | 1,570 |
  | derecha | 116,111 | 2,231 |
  | neutral | 171,825 | 3,020 |
  | **total** | **552,456** | **6,821** |

  El CSV final muestra 40 nombres de canal porque `neutral` fusiona `neutral_local` con el `neutral.json` canónico de Kaggle (18 canales adicionales); el archivo canónico permaneció intacto. El tope de recolección fue 2,000 comentarios por video.
- **Inferencia**: Kaggle reporta el dataset `josealvacornejo/sa-polarization-dat` en **versión 5, `ready`**. La última ejecución de `josealvacornejo/sa-polarization-inference` figura `COMPLETE`, con `lastRunTime=2026-11-03 19:19:12 UTC` (14:19 en Lima). Los archivos de la versión actual se publicaron a las 17:04 UTC, antes de esa ejecución; el log de esa última corrida confirma `Clasificados 552456 comentarios` y la descarga de Robertuito desde Hugging Face (Internet OK).
- **Salidas** (`outputs/`, local, ignorado por Git; escritas el 2026-11-03 entre 15:15 y 15:16): `datos_clasificados.csv` (~218 MB), `ap_individual.csv` (~9.1 MB), `favorabilidad_por_partido.csv`, `favorabilidad_ponderada_por_partido.csv`, `polarizacion_por_grupo.csv`, 11 PNG y `sa-polarization-inference.log`.
- **Verificación remota de resultados (2026-11-07)**: `comentarios_consolidado.csv` de la versión Kaggle 5 coincide byte por byte (SHA-256) con `data/processed/comentarios_consolidado.csv`; `datos_clasificados.csv` y el log de la última salida del kernel coinciden byte por byte con sus copias en `outputs/`. La última corrida y los artefactos locales tienen el mismo total de 552,456 filas. Regeneré en una carpeta temporal las 4 tablas CSV y los 11 PNG usando ese CSV clasificado: los 15 archivos coinciden byte por byte con los de `outputs/`. Por tanto, las tablas y figuras locales corresponden a la última salida disponible en Kaggle; no se encontró una corrida posterior.

### Resultados de la corrida

| party | total | % negativo | % neutro | % positivo | favorabilidad_neta | favorabilidad_ponderada_norm |
|---|---:|---:|---:|---:|---:|---:|
| izquierda | 264,520 | 51.74 | 30.13 | 18.13 | −0.336 | −0.282 |
| derecha | 116,111 | 49.34 | 35.10 | 15.56 | −0.338 | −0.281 |
| neutral | 171,825 | 61.43 | 28.13 | 10.44 | −0.510 | −0.422 |

- **Global**: 54.2 % negativo / 30.6 % neutro / 15.2 % positivo; confianza media 0.794 / 0.581 / 0.690. Por etapa: antes 110,697; durante 95,808; después 333,490.
- **AP** (`ap_individual.csv`; solo usuarios con `ingroup` determinado, 34,389 de 135,259):
  - derecha: AP medio **1.484** (spread 1.098; n=11,524); AP_In 0.493; AP_Out −0.991.
  - izquierda: AP medio **−0.259** (spread 1.133; n=22,865); AP_In −0.839; AP_Out −0.580.
  - AP global (todos los determinados): media 0.325, desv. 6.323; `nivel_AP` usa esos valores: Alto > 6.65, Bajo < −6.00.
  - `nivel_AP`: Alto 1,002 / Medio 31,567 / Bajo 1,820 / Undetermined 100,870.
- **Lectura**: la favorabilidad neta de izquierda y derecha es casi idéntica (−0.336 vs −0.338); el grupo neutral es más negativo (−0.510). La diferencia fuerte está en AP: los usuarios asignados a derecha muestran polarización afectiva positiva (favorables a su endogrupo y negativos hacia el exogrupo), mientras que los de izquierda son negativos hacia ambos, con AP cercano a cero/negativo.

### Advertencias y límites de esta corrida

- **Carrera de publicación (crítica)**: `kaggle datasets version` retorna antes de crear la versión y el `kernels push` inmediato puede montar la versión anterior. En la primera corrida el kernel procesó 325,050 filas viejas; se resolvió re-ejecutando `infer` (sin republicar) cuando la versión ya estaba lista. **El parche automático (validación de conteo + reintento) no está implementado** y el usuario pidió no hacerlo por ahora. Si se republica, compara las filas de `outputs/datos_clasificados.csv` con `data/processed/comentarios_consolidado.csv` (552,456) antes de aceptar las métricas.
- **Métrica AP sensible al volumen**: AP y spread son diferencias de conteos de comentarios positivos/negativos, no tasas; no están acotadas y tienen colas largas (AP hasta ±220; spread hasta 14). Los usuarios con ≥5 comentarios concentran 62.3 % de los comentarios de izquierda, 37.4 % de derecha y 39.8 % de neutral; los promedios de AP pueden estar dominados por supercomentaristas. No cambies la definición sin una solicitud metodológica explícita.
- **Asignación de endogrupo**: `ingroup` se infiere como el `party` con más comentarios positivos del usuario; empates o ausencia de positivos → `Undetermined` (100,870 usuarios). No es ideología declarada.
- El `DtypeWarning` de `search_query` en `analysis.py` es cosmético.
- Canales sin datos útiles: `@prensaperulibre1465` no aportó videos en la ventana (solo 2 videos de 2021, fuera del periodo) y `@JuntosTVoficial` aportó 3 videos con 0 comentarios.
- El paquete `kaggle` 2.2.5 requiere `six` instalado aparte en `.venv` (dependencia no declarada).
- `@tvperu` es el handle correcto de TV Perú; no usar `@rtp` (RTP Portugal) ni `@Radiotelevisionperuana`/`@rtpnoticias648` (muertos).
