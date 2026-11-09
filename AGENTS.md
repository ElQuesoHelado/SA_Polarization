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
- Todo comando que produzca resultados de análisis de producción (`analyze`, `infer-results`, `full-pipeline`) debe regenerar también el bloque delimitado `GENERATED RESULTS COMPARISON` en este archivo, con el resumen de tablas, métricas y comparación con el paper de referencia. La actualización ocurre solo después de generar correctamente los artefactos; si faltan o se duplican los marcadores, detenerse con un error claro. `smoke-test` nunca actualiza este contexto de producción.

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

## Evaluación de calidad y mejoras recomendadas

- **Juicio general**: los resultados actuales son reproducibles y describen un corpus grande (552,456 comentarios); la última salida de Kaggle y los artefactos locales fueron verificados byte por byte el 2026-11-07. Esto respalda la integridad del procesamiento, no la validez sustantiva de AP. Como descripción exploratoria del sentimiento predicho en comentarios recolectados de canales etiquetados, los resultados son útiles. No alcanzan para afirmar que una audiencia partidaria siente afecto o rechazo hacia el grupo del canal, ni para concluir qué grupo tiene más polarización.
- **Validez del constructo (riesgo principal)**: `pyupeu/robertuito-peruvian-sentiment` clasifica la valencia general del texto; el código usa esa etiqueta como interacción positiva/negativa dirigida al grupo asociado al canal del video. Un comentario sobre una noticia, un tercero, sarcasmo o una crítica al propio canal no necesariamente expresa actitud hacia la izquierda/derecha. La literatura distingue análisis de sentimiento general de opinión/stance dirigida a un objetivo; ver [Sentiment Is Not Stance](https://www.cambridge.org/core/journals/political-analysis/article/sentiment-is-not-stance-targetaware-opinion-classification-for-political-text-analysis/743A9DD62DF3F2F448E199BDD1C37C8D). Por eso la inversión entre el AP_In de derecha (+0.493) e izquierda (−0.839) no debe interpretarse aún como que la primera apoya a su endogrupo y la segunda lo rechaza: también puede reflejar los temas y textos de los videos o errores de valencia.
- **Comparación numérica, no ranking de calidad**: AP medio local (derecha 1.484; izquierda −0.259) queda por debajo de los valores derivados de Tabla 4 del paper (9.885; 7.972), pero AP conserva conteos y la muestra, unidades y grupos difieren; la diferencia no significa menor polarización. AP_Out es negativo en ambos estudios, pero local agrega `neutral` a los grupos externos y el paper suma tres partidos externos. Spread local (1.098; 1.133) frente a Tabla 6 (1.874; 1.748), y porcentaje alto local (7.12%; 10.21%) frente a Tabla 5 (15.89%; 13.35%), tampoco son comparables: el pipeline calcula el denominador usando solo comentarios positive/negative y define alto con su propio corte global 1.940; el paper usa total de interacciones y corte 2.68. No comparar porcentajes de nivel sin armonizar métrica, población y corte.
- **Usuarios indeterminados**: la corrida local reporta 100,870/135,259 (74.58%) frente a 55% en el paper. La diferencia no estima una mejora o empeoramiento de clasificación: `analysis.py` construye el universo de usuarios después de filtrar sentimientos `positive`/`negative`, por lo que excluye a usuarios con comentarios exclusivamente neutrales; además, YouTube/canales y Twitter/interacciones generan oportunidades de clasificación distintas. La etiqueta `ingroup` es una afinidad operacional inferida por comentarios positivos, no ideología declarada.
- **Qué muestran las tablas y figuras del paper**: Tablas 1–2 muestran más interacciones positivas hacia el endogrupo, pero también críticas internas y desviaciones estándar muy grandes; la Figura 2 es una distribución de usuarios detectados, no una estimación de la población ideológica. Figuras 3–5 muestran colas largas y valores extremos en AP/AP_In/AP_Out; el propio texto dice que las diferencias AP entre partidos son modestas. Figura 6 y Tablas 5–6 presentan spread en un rango más compacto, con un valor extremo y mayor porcentaje alto para la derecha. El paper informa ANOVA y Bonferroni, pero no da F ni valores p en el texto; sus conclusiones estadísticas no constituyen un patrón para copiar sin validación. El paper también tiene límites y no debe tratarse como verdad de referencia.
- **Ruta priorizada para mejorar**:
  1. Sin etiquetado manual, mantener explícito que Robertuito predice valencia general y que `party` asigna el grupo de origen del video; no equiparar automáticamente esas variables con postura del comentario hacia un grupo político. Presentar AP como indicador exploratorio del corpus, no como medición validada de actitudes ciudadanas.
  2. Auditar sensibilidad de `ingroup`: reportar usuarios con evidencia positiva, empates, usuarios exclusivamente neutrales y cambios al aplicar umbrales de actividad. Mantener `Undetermined` explícito y no presentar la afinidad operacional como ideología declarada.
  3. Separar `neutral` (pool de fuentes) de los grupos políticos en métricas de dos bloques; presentar aparte análisis que incluyan fuentes neutrales. Examinar el tope de 2,000 comentarios/video y el desequilibrio entre canales, periodos y volumen de usuario.
  4. Evaluar robustez con contribución equilibrada por video/canal y remuestreo agrupado; comparar sensibilidad a volumen, neutralidad, umbrales y periodos. Mantener las definiciones oficiales y etiquetar cualquier variante como análisis de sensibilidad.
  5. Triangular la interpretación con estudios peruanos, encuestas y resultados electorales, respetando diferencias de periodo, unidad, plataforma y población. No comparar directamente magnitudes de Twitter/encuestas con YouTube ni inventar categorías de izquierda/derecha radical para replicar cuatro grupos españoles.
- **Criterio para una conclusión más fuerte**: mostrar que los patrones descriptivos sobreviven a análisis de sensibilidad y son coherentes —o explicar por qué divergen— con la evidencia peruana pertinente. Sin medir la postura dirigida al objetivo, limitar las conclusiones a sentimiento predicho bajo fuentes clasificadas y no generalizar a votantes o a toda la población peruana.

## Evidencia externa: polarización política usando YouTube

La literatura confirma que YouTube se usa para estudiar fenómenos relacionados con polarización política, aunque “polarización” abarca constructos distintos. Un estudio de sentimiento genérico no equivale a postura hacia un actor político; toxicidad, interacción entre grupos, homofilia y polarización narrativa tampoco son intercambiables con polarización afectiva (AP). Elegir y nombrar el constructo antes de interpretar resultados.

**Contexto peruano:** sí existen estudios de polarización afectiva en Perú, aunque en la revisión del 2026-11-08 no se identificó uno que mida AP con comentarios peruanos de YouTube. Ponte Torrel (2022) analiza 1.2 millones de tuits de la segunda vuelta de 2021 y reporta sentimientos extremos hacia candidaturas y variación temporal; Mejía Navarrete (2024) analiza dimensiones de polarización peruana entre 2000 y 2023; una síntesis comparativa con encuestas/CSES sitúa a Perú con promedio alto entre seis países latinoamericanos y describe una trayectoria en U entre 2001 y 2017. Estos trabajos aportan contexto nacional, pero no son benchmarks numéricos directos para la corrida de YouTube. La revisión completa, sus fuentes y límites están en [docs/literatura_polarizacion_peru_youtube.md](docs/literatura_polarizacion_peru_youtube.md).

| Estudio | Fuente y constructo | Método / resultado relevante | Aplicabilidad y límite para este pipeline |
|---|---|---|---|
| Miehling, Dakota y Kübler (RANLP 2025), [*Investigating Polarization in YouTube Comments via Aspect-Based Sentiment Analysis*](https://aclanthology.org/2025.ranlp-1.83/) | Más de 3 millones de comentarios y respuestas de cuatro canales de noticias durante el conflicto Israel–Hamas; sentimiento hacia aspectos/entidades concretos. | Anota cerca de 5,000 comentarios y evalúa clasificación de sentimiento basada en aspectos; reporta F1 global de 77.9, con variación por aspecto y errores en sarcasmo, objetivos múltiples, lenguaje implícito y mezcla de idiomas. | Es el precedente más cercano por plataforma y sentimiento hacia objetivos. Su resultado no valida Robertuito ni se transfiere automáticamente a español peruano o a elecciones; sirve para distinguir el alcance de sentimiento general frente a postura dirigida. |
| Wu y Resnick (ICWSM 2021), [*Cross-Partisan Discussions on YouTube*](https://doi.org/10.1609/icwsm.v15i1.18105) | 134 millones de comentarios de 274,241 videos de 973 canales políticos estadounidenses; interacción entre audiencias de medios partidistas. | Estudia participación entre grupos, toxicidad de respuestas y visibilidad de comentarios; encuentra cruces entre grupos, con asimetrías y menor visibilidad de comentarios interpartidistas. | Inspira medidas conductuales calculables con `user_id`, canal y video. Comentar en un canal no prueba apoyar su línea editorial; el estudio no mide AP directamente. |
| Tran et al. (2022), [*Understanding Political Polarization Based on User Activity*](https://journals.sagepub.com/doi/10.1177/21582440221094587) | Canales políticos de YouTube en Corea; más de 600,000 usuarios y 11 millones de comentarios. | Usa canales semilla definidos con expertos y actividad/solapamiento de usuarios para inferir afinidad y sesgo de canal; informa bajo solapamiento entre campos. | Precedente para medir concentración y cruce de audiencias, no para validar ideología individual. La inferencia depende de la selección de canales semilla y de asumir afinidad a partir de comentar allí. |
| Mall et al. (2024), [*Politics on YouTube: Detecting Online Group Polarization Based on News Videos’ Comments*](https://journals.sagepub.com/doi/10.1177/21582440241256438) | Cerca de 180,000 comentarios de unos 3,700 videos de noticias; polarización operacionalizada mediante toxicidad. | Propone una puntuación de polarización de toxicidad a partir de la distribución de comentarios tóxicos/no tóxicos. | Sirve como alternativa si la pregunta es hostilidad/tóxico, no afecto partidario. No usar toxicidad como sustituto de AP. |
| Elfes, Bastos y Aiello (PNAS Nexus 2026), [*Measuring narrative polarization in online discourse*](https://academic.oup.com/pnasnexus/article/5/8/pgag270/8758080) | 90,029 comentarios de 212 videos sobre el conflicto Israel–Palestina; polarización narrativa. | Extrae roles y relaciones narrativas y los contrasta con codificación humana; encuentra narrativas de video más polarizadas que las conversaciones sobre sus narrativas centrales. | Muestra que la polarización puede estar en marcos narrativos y no solo en valencia. Exige otro diseño/constructo; su conflicto y muestreo no representan la política peruana. |
| Shevtsov et al. (PLOS ONE 2023), [*What Tweets and YouTube comments have in common?*](https://doi.org/10.1371/journal.pone.0270542) | Comentarios de videos de YouTube enlazados con publicaciones de Twitter sobre elecciones de EE. UU. 2020. | Combina sentimiento hacia candidatos/eventos y análisis de grafos/comunidades entre plataformas. | Precedente para combinar entidades objetivo con estructura de interacción; el diseño no es YouTube exclusivamente ni una validación directa de AP. |

### Consecuencias metodológicas para este corpus

- El corpus actual sí permite estudiar **sentimiento predicho en comentarios publicados bajo videos de fuentes clasificadas**. Hasta validar objetivo y postura, no describirlo como apoyo/rechazo al grupo ni como medición validada de polarización afectiva.
- No se ha acordado realizar etiquetado manual. No transferir al modelo local los F1 reportados por estudios en otros idiomas/dominios; limitar las afirmaciones según las variables operacionales disponibles.
- Como resultado complementario viable con campos actuales (`user_id`, canal/video, `party`), calcular distribución de actividad entre fuentes izquierda/derecha/neutrales, tasa de participación en ambos campos y solapamiento de usuarios/canales. Aplicar umbrales de actividad como análisis de sensibilidad y llamarlo **participación/exposición entre fuentes**, no ideología ni apoyo: comentar en un canal no revela por sí solo la preferencia del usuario. `neutral` es un pool de medios, no un tercer bloque ideológico.
- La recolección actual usa comentarios de nivel superior; guarda `reply_count`, pero no el texto completo de todas las respuestas. Las respuestas permitirían estudiar interacción directa y toxicidad conversacional, como en parte de la literatura; exigirían una etapa de captura propia y documentación de cobertura. La API indica que `commentThreads.list` no siempre incluye todas las respuestas; para recuperarlas se requiere `comments.list` ([documentación de YouTube](https://developers.google.com/youtube/v3/docs/commentThreads)).
- El tope de 2,000 comentarios por video y la cobertura desigual por canal pueden sesgar el corpus. La API ofrece orden `time` (predeterminado) o `relevance`; registrar y declarar el orden, el tope y la fecha de extracción, y comparar resultados bajo muestras/umbrales alternativos cuando sea posible ([`commentThreads.list`](https://developers.google.com/youtube/v3/docs/commentThreads/list)). No asumir que el conjunto recolectado es una muestra aleatoria de la audiencia.
- `stage` actualmente se deriva de la fecha de publicación del **video**, no de la fecha del comentario. Para afirmar evolución temporal de opinión, usar y validar la fecha de publicación del comentario como eje temporal; de lo contrario, describir `stage` como etapa de publicación del video.
- Informar incertidumbre y robustez con remuestreo agrupado por video o canal, porque comentarios del mismo espacio no son observaciones independientes. Las conclusiones se limitan a las fuentes, videos y periodo observados; no generalizar a votantes peruanos sin un diseño representativo.
- Mantener AP/spread actuales como resultados oficiales de esta corrida. Cualquier variante que armonice el denominador, unidad, grupos o umbral con un paper debe ser una sensibilidad etiquetada y documentada; no reemplaza las métricas oficiales sin una decisión metodológica explícita.

Para recomendaciones y prioridades específicas de interpretación peruana sin etiquetado manual, consultar [la revisión de literatura y plan analítico](docs/literatura_polarizacion_peru_youtube.md).

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
- **Salidas** (`outputs/`, local, ignorado por Git): `datos_clasificados.csv` (~218 MB), `ap_individual.csv` (~9.1 MB), `favorabilidad_por_partido.csv`, `favorabilidad_ponderada_por_partido.csv`, `polarizacion_por_grupo.csv`, 11 PNG y `sa-polarization-inference.log`. La inferencia/log corresponden a Kaggle del 2026-11-03; las tablas y figuras se regeneraron localmente el 2026-11-07 a las 12:08 (America/Lima), como registra el bloque comparativo.
- **Verificación remota de resultados (2026-11-07)**: `comentarios_consolidado.csv` de la versión Kaggle 5 coincide byte por byte (SHA-256) con `data/processed/comentarios_consolidado.csv`; `datos_clasificados.csv` y el log de la última salida del kernel coinciden byte por byte con sus copias en `outputs/`. La última corrida y los artefactos locales tienen el mismo total de 552,456 filas. Regeneré en una carpeta temporal las 4 tablas CSV y los 11 PNG usando ese CSV clasificado: los 15 archivos coinciden byte por byte con los de `outputs/`. Por tanto, las tablas y figuras locales corresponden a la última salida disponible en Kaggle; no se encontró una corrida posterior.

### Resultados de la corrida

<!-- BEGIN GENERATED RESULTS COMPARISON -->
**Actualizado:** 2026-11-07T12:08-05:00 (America/Lima).
**Entrada analizada:** `datos_clasificados.csv`, 552,456 filas; SHA-256 `8acce58a23275e349767c50793c0dccb7b3834777ff914ec349e58ee568e24bf`.

#### Sentimiento y favorabilidad por grupo

| party | comentarios | % negativo | % neutro | % positivo | favorabilidad neta | favorabilidad ponderada normalizada |
|---|---:|---:|---:|---:|---:|---:|
| derecha | 116,111 | 49.34% | 35.10% | 15.56% | -0.338 | -0.281 |
| izquierda | 264,520 | 51.74% | 30.13% | 18.13% | -0.336 | -0.282 |
| neutral | 171,825 | 61.43% | 28.13% | 10.44% | -0.510 | -0.422 |

#### Polarización por endogrupo asignado

Usuarios en `ap_individual.csv`: 135,259; `Undetermined`: 100,870 (74.58%). AP global: 0.325 (DE 6.323); spread global: 1.121 (DE 0.819; nivel alto > 1.940).

| ingroup | usuarios determinados | AP_In medio | AP_Out medio | AP medio | spread medio | spread alto |
|---|---:|---:|---:|---:|---:|---:|
| derecha | 11,524 | 0.493 | -0.991 | 1.484 | 1.098 | 7.12% |
| izquierda | 22,865 | -0.839 | -0.580 | -0.259 | 1.133 | 10.21% |

#### Comparación descriptiva con el paper

Valores por par `paper / pipeline`. Derecha/Right e izquierda/Left son correspondencias aproximadas, no grupos equivalentes; AP_Out y AP del paper se derivan de las medias de la tabla 4. Los denominadores, plataformas e interacciones difieren, así que estas cifras no son una réplica ni una prueba de diferencias.

| grupo aproximado | AP_In | AP_Out | AP | spread | spread alto |
|---|---:|---:|---:|---:|---:|
| Right (PP) ↔ derecha | 8.662 / 0.493 | -1.223 / -0.991 | 9.885 / 1.484 | 1.874 / 1.098 | 15.89% / 7.12% |
| Left (PSOE) ↔ izquierda | 6.813 / -0.839 | -1.160 / -0.580 | 7.972 / -0.259 | 1.748 / 1.133 | 13.35% / 10.21% |
<!-- END GENERATED RESULTS COMPARISON -->

### Advertencias y límites de esta corrida

- **Carrera de publicación (crítica)**: `kaggle datasets version` retorna antes de crear la versión y el `kernels push` inmediato puede montar la versión anterior. En la primera corrida el kernel procesó 325,050 filas viejas; se resolvió re-ejecutando `infer` (sin republicar) cuando la versión ya estaba lista. **El parche automático (validación de conteo + reintento) no está implementado** y el usuario pidió no hacerlo por ahora. Si se republica, compara las filas de `outputs/datos_clasificados.csv` con `data/processed/comentarios_consolidado.csv` (552,456) antes de aceptar las métricas.
- **Métrica AP sensible al volumen**: AP y spread son diferencias de conteos de comentarios positivos/negativos, no tasas; no están acotadas y tienen colas largas (AP hasta ±220; spread hasta 14). Los usuarios con ≥5 comentarios concentran 62.3 % de los comentarios de izquierda, 37.4 % de derecha y 39.8 % de neutral; los promedios de AP pueden estar dominados por supercomentaristas. No cambies la definición sin una solicitud metodológica explícita.
- **Asignación de endogrupo**: `ingroup` se infiere como el `party` con más comentarios positivos del usuario; empates o ausencia de positivos → `Undetermined` (100,870 usuarios). No es ideología declarada.
- El `DtypeWarning` de `search_query` en `analysis.py` es cosmético.
- Canales sin datos útiles: `@prensaperulibre1465` no aportó videos en la ventana (solo 2 videos de 2021, fuera del periodo) y `@JuntosTVoficial` aportó 3 videos con 0 comentarios.
- El paquete `kaggle` 2.2.5 requiere `six` instalado aparte en `.venv` (dependencia no declarada).
- `@tvperu` es el handle correcto de TV Perú; no usar `@rtp` (RTP Portugal) ni `@Radiotelevisionperuana`/`@rtpnoticias648` (muertos).
