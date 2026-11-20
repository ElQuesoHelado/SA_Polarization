# BETO — recurso técnico del modelo

**Recurso:** DCC, Universidad de Chile, `dccuchile/bert-base-spanish-wwm-uncased`.
**Clave del manuscrito:** `BETOResource`.
**Rol:** modelo candidato para clasificación dirigida; no benchmark de polarización.
**Consulta:** 2026-11-15. **PDF local:** no aplica a esta ficha del recurso; no se afirma haber descargado el artículo asociado.

Fuentes primarias: [ficha del modelo](https://huggingface.co/dccuchile/bert-base-spanish-wwm-uncased), [configuración](https://huggingface.co/dccuchile/bert-base-spanish-wwm-uncased/blob/main/config.json), [repositorio de sus autores](https://github.com/dccuchile/beto).

La ficha describe un BERT de español, tamaño base, preentrenado con whole-word masking. La configuración declara `model_type=bert`, 12 capas y `max_position_embeddings=512`. La revisión congelada para el experimento es `d1c9c4565c9d6731e57ed7f027b802697bad861e`; las ejecuciones deben registrar el SHA y verificar sus pesos.

Estos datos sustentan su elección como comparación de arquitectura y contexto frente a RoBERTuito. No demuestran precisión afectiva en comentarios peruanos ni que BETO supere al modelo actual. Esa comparación se realiza sobre el desarrollo local; la prueba final permanece separada. No se transfieren los benchmarks generales de la ficha a este estudio.
