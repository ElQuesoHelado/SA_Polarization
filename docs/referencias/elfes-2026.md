# elfes-2026 — Medición de polarización narrativa en discursos en línea

**Cita completa:** Elfes, T.; Bastos, M.; Aiello, L. M. (2026). *Measuring narrative polarization in online discourse*. *PNAS Nexus* 5(8), pgag270. DOI [10.1093/pnasnexus/pgag270](https://doi.org/10.1093/pnasnexus/pgag270). Preprint en arXiv:2601.07398.

**PDF:** `pdfs/contexto/elfes-2026.pdf`  
**Rol:** `youtube-sa-polarizacion` — metodología avanzada para evaluar polarización más allá de la valencia simple en YouTube.  
**Clave en `doc.tex`:** `Elfes2026`  
**Verificado:** 2026-11-09 (contra el documento en `pdfs/contexto/elfes-2026.pdf`).

## Qué aporta

Analiza 90,029 comentarios de 212 videos de YouTube relacionados con el conflicto Israel–Palestina, proponiendo un marco para medir **polarización narrativa**. Extrae roles de personajes (héroes, villanos, víctimas) y relaciones narrativas mediante modelos de lenguaje, contrastando la estructura de los comentarios con la codificación de los videos.

## Hallazgos citables

- **Disociación entre valencia y polarización de marcos:** Demuestra que la polarización en redes no se manifiesta únicamente en el tono positivo/negativo de las palabras, sino en la asignación divergente de roles narrativos y causales.
- **Narrativas del video vs. conversación en comentarios:** Encuentra que los videos presentan encuadres narrativos significativamente más polarizados y cerrados que los comentarios de los usuarios, los cuales a menudo introducen controversia sobre las narrativas centrales.

## Límites para nuestro trabajo

- Requiere extracción de grafos de conocimiento y marcos narrativos de alta complejidad, superando el alcance de los modelos de polaridad tri-clase (positivo/negativo/neutral).
- Enfocado en política internacional en inglés.

## Uso en el proyecto

- `doc.tex` §Discusión y Trabajo Futuro: Proporciona el marco teórico que respalda por qué un análisis basado únicamente en polaridad de sentimiento (positivo/negativo) ofrece una aproximación inicial que debe complementarse en el futuro con análisis de marcos discursivos.
