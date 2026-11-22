# DeBERTaV3 y mDeBERTa-v3-base

**Cita:** Pengcheng He, Jianfeng Gao y Weizhu Chen (2023), *DeBERTaV3: Improving
DeBERTa using ELECTRA-Style Pre-Training with Gradient-Disentangled Embedding
Sharing*, ICLR 2023. Registro consultado:
[arXiv:2111.09543v4](https://arxiv.org/abs/2111.09543v4), 24 de marzo de 2023.
**Claves:** `DeBERTaV32023`, `mDeBERTaResource`.
**PDF:** `pdfs/contexto/debertav3-2023.pdf`. Procedencia/hash en
`encoder-extension-downloads.json`. Consulta: 2026-11-22.

## Hallazgos citables

El resumen del artículo explica el objetivo de detección de tokens reemplazados
y el mecanismo de compartición de embeddings con gradientes desacoplados.
Incluye una variante multilingüe; los resultados XNLI no son puntuaciones
esperables para sentimiento político dirigido.
La [ficha oficial](https://huggingface.co/microsoft/mdeberta-v3-base) identifica
12 capas, 86 M de parámetros del backbone y aproximadamente 190 M adicionales
de embeddings. No describirlo como un modelo de solo 86 M de parámetros totales.

## Uso y límites locales

Se incorpora `microsoft/mdeberta-v3-base`, revisión
`a0484667b22365f84929a935b5e50a51f71f159d`, contexto máximo de 512 tokens.
Sirve como arquitectura multilingüe complementaria a XLM-R, no como una prueba
aislada del efecto del multilingüismo. El antecedente de uso en sentimiento
dirigido español se documenta aparte en [SINAI/FinancES](sinai-finances-2023.md);
no equivale a validación en comentarios peruanos ni prueba que este checkpoint
sin ajustar ya resuelva las cinco clases locales.
