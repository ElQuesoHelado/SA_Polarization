# shevtsov-2023 — Comparación y enlace entre Twitter y comentarios de YouTube

**Cita completa:** Shevtsov, S.; O’Connor, A.; O’Hagan, M.; Carley, K. M. (2023). *What Tweets and YouTube comments have in common? An analysis of social media dynamics during the 2020 US Presidential Election*. *PLOS ONE* 18(4), e0270542. DOI [10.1371/journal.pone.0270542](https://doi.org/10.1371/journal.pone.0270542).

**PDF:** `pdfs/contexto/shevtsov-2023.pdf`  
**Rol:** `youtube-sa-polarizacion` — estudio multiplataforma que enlaza comentarios de YouTube con discursos en Twitter.  
**Clave en `doc.tex`:** `Shevtsov2023`  
**Verificado:** 2026-11-09 (contra el PDF en `pdfs/contexto/shevtsov-2023.pdf`).

## Qué aporta

Analiza conjuntamente publicaciones de Twitter y comentarios de videos de YouTube enlazados durante las elecciones presidenciales de EE. UU. 2020. Combina análisis de sentimiento hacia entidades/candidatos, análisis de redes sociales (SNA) y modelado de comunidades para entender cómo viaja la polarización entre ambas plataformas.

## Hallazgos citables

- **Convergencia y divergencia de sentimiento:** Las reacciones a los mismos eventos y videos varían significativamente según la plataforma: los comentarios de YouTube tienden a mostrar mayor negatividad y persistencia de temas contenciosos en comparación con Twitter.
- **Topología de red:** Muestra que los enlaces de videos de YouTube compartidos en Twitter actúan como puentes de polarización, concentrando la interacción de comunidades con posturas ideológicas homogéneas.

## Límites para nuestro trabajo

- Enfocado en elecciones de EE. UU. 2020 con arquitectura de grafos bipartitos y propagación de enlaces.
- No utiliza la formulación de AP individual ni modelos en español.
- Su aporte es conceptual sobre diferencias entre Twitter y YouTube, no un benchmark numérico.

## Uso en el proyecto

- `doc.tex` §Estado del Arte: Fundamenta teóricamente por qué los resultados obtenidos en Twitter (como Martínez-España 2024 o Ayma 2024) no pueden compararse numéricamente de forma directa con los comentarios recolectados en YouTube.
