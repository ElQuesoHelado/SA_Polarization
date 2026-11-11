# singh-2026 — survey de SA con deep learning

**Cita completa:** Singh, M.; Panwar, S.; Choudhary, S. (2026). *Exploring advanced sentiment analysis techniques using deep learning architectures: a comprehensive survey*. Knowledge and Information Systems 68, 94. DOI [10.1007/s10115-026-02704-6](https://doi.org/10.1007/s10115-026-02704-6).

**PDF:** `pdfs/15.singh-2026.pdf`
**Rol:** `survey-sa` — revisión sistemática de arquitecturas de deep learning para SA.
**Clave en `doc.tex`:** `Singh2026`.
**Verificado:** 2026-11-09 (resumen e introducción).

## Qué aporta

Revisión sistemática y comparativa de técnicas de SA basadas en deep learning publicadas entre 2020 y 2025. Cubre CNN, RNN, modelos con atención, Transformers, híbridos y modelos basados en grafos; describe diseños, datasets, métricas y limitaciones. Propone una taxonomía unificada y enumera retos abiertos (desbalance, adaptación de dominio, multilingüismo, interpretabilidad).

## Hallazgos citables

- Los Transformers y los modelos híbridos dominan el estado del arte en SA.
- Persisten problemas de desbalance de clases, adaptación entre dominios y multilingüismo.
- La interpretabilidad es un reto transversal.
- Útil para justificar la elección de arquitecturas Transformer frente a enfoques clásicos.

## Límites para nuestro trabajo

- Survey general; no evalúa el corpus peruano ni YouTube.
- No mide AP ni polarización.
- Las comparaciones de rendimiento entre arquitecturas provienen de datasets distintos; no son un benchmark único.

## Uso en el proyecto

- `doc.tex` §Estado del Arte: respaldo general del uso de Transformers/BERT en SA.
- Contexto para discutir limitaciones y trabajo futuro.
