# MrBERT y MrBERT-es

**Cita:** Daniel Tamayo, Iñaki Lacunza, Paula Rivera-Hidalgo, Severino Da Dalt,
Javier Aula-Blasco, Aitor Gonzalez-Agirre y Marta Villegas (2026), *MrBERT:
Modern Multilingual Encoders via Vocabulary, Domain, and Dimensional Adaptation*,
[arXiv:2602.21379v2](https://arxiv.org/abs/2602.21379v2), 7 de marzo de 2026.
**Claves:** `MrBERT2026`, `MrBERTesResource`.
**PDF:** `pdfs/contexto/mrbert-2026.pdf`. Procedencia/hash en
`encoder-extension-downloads.json`. Consulta: 2026-11-22.

## Hallazgos citables y recurso

El resumen del artículo presenta una familia de encoders ModernBERT y adaptaciones
de vocabulario, dominio y dimensión; no es un estudio de polarización.
La [ficha oficial de MrBERT-es](https://huggingface.co/BSC-LT/MrBERT-es), sección
Technical Description, identifica la variante español/inglés de 150 M de
parámetros y contexto máximo de 8,192 tokens. Su evaluación EvalES comprende
tareas generales de español; no valida sentimiento dirigido en YouTube peruano.

## Uso y límites locales

Se incorpora como candidato lingüístico/arquitectónico. La ejecución fija
`BSC-LT/MrBERT-es` en `34a7cc86e0d0a2b77e802d07a189db1c0ef2e7d4` y usa **512**
tokens para esta comparación, no los 8,192 de capacidad máxima. El tokenizador
rápido se carga desde los archivos del recurso; el modelo de clasificación es
ModernBERT, aunque el tokenizador pertenezca a la familia Llama.
La elección no demuestra mejora local ni permite atribuir diferencias únicamente
al idioma de preentrenamiento. Requiere ajuste dirigido con las cinco etiquetas.
