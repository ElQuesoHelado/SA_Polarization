# miehling-2025 — Aspect-Based Sentiment Analysis en YouTube

**Cita completa:** Miehling, E.; Dakota, D.; Kübler, S. (2025). *Investigating Polarization in YouTube Comments via Aspect-Based Sentiment Analysis*. In *Proceedings of the 15th International Conference on Recent Advances in Natural Language Processing (RANLP 2025)*, pp. 784–794. [ACL Anthology](https://aclanthology.org/2025.ranlp-1.83/).

**PDF:** `pdfs/09.miehling-2025.pdf`  
**Rol:** `youtube-sa-polarizacion` — antecedente metodológico directo de análisis de sentimiento y polarización en comentarios de YouTube.  
**Clave en `doc.tex`:** `Miehling2025`  
**Verificado:** 2026-11-09 (contra el PDF en `pdfs/09.miehling-2025.pdf`).

## Qué aporta

Analiza más de 3 millones de comentarios y respuestas de videos informativos de cuatro canales de noticias internacionales durante el conflicto Israel–Hamas. Introduce una anotación manual de cerca de 5,000 comentarios para evaluar Aspect-Based Sentiment Analysis (ABSA) frente a análisis de sentimiento global, aislando el sentimiento hacia entidades y aspectos específicos (Israel, Palestina, gobiernos, civiles, cobertura mediática).

## Hallazgos citables

- **Rendimiento ABSA:** Reporta un F1 macro global de 77.9% en la clasificación de polaridad orientada a aspectos.
- **Desafíos lingüísticos en YouTube:** Documenta que los principales errores surgen de sarcasmo, objetivos múltiples en un mismo comentario, lenguaje implícito y mezclas de idiomas/slang.
- **Distinción entre sentimiento general y postura hacia objetivos:** Muestra empíricamente que un comentario de valencia negativa con frecuencia expresa apoyo al actor defendido al criticar a su contraparte o a los medios, evidenciando los sesgos de atribuir valencia general como actitud hacia el canal.

## Límites para nuestro trabajo

- El dominio es un conflicto armado internacional (Israel-Hamas), no un proceso electoral peruano.
- No evalúa la fórmula matemática de AP individual de Martínez-España, sino la distribución de polaridad hacia aspectos.
- Su F1 (77.9%) no se transfiere automáticamente a modelos de valencia general como RoBERTuito en español peruano.

## Uso en el proyecto

- `doc.tex` §Estado del Arte y §Discusión / Limitaciones: Justifica teóricamente la diferencia entre sentimiento global y postura dirigida a un objetivo (*Sentiment is not stance*).
