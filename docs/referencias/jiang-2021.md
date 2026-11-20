# Jiang et al. (2021): NEEDLE

**Cita:** Jiang, H.; Zhang, D.; Cao, T.; Yin, B.; Zhao, T. *Named Entity Recognition with Small Strongly Labeled and Large Weakly Labeled Data*. ACL-IJCNLP 2021, 1775–1789. DOI [10.18653/v1/2021.acl-long.140](https://doi.org/10.18653/v1/2021.acl-long.140).

**PDF local:** `pdfs/contexto/jiang-2021.pdf`. Fuente primaria: [ACL Anthology](https://aclanthology.org/2021.acl-long.140/). **Rol:** antecedente técnico de refinamiento final con etiquetas humanas; no benchmark de polarización.

## Hallazgos citables

- Resumen e introducción: en sus tareas NER, combinar datos de supervisión débil y fuerte, incluso ponderándolos, no garantiza mejora y puede deteriorar el resultado.
- §3, Fig. 1: NEEDLE combina adaptación de dominio, aprendizaje con supervisión débil/fuerte y pérdida resistente al ruido, y ajuste final con etiquetas fuertes.
- §3.3: tras el aprendizaje resistente al ruido, vuelven a ajustar el modelo con etiquetas fuertes para recuperar su adaptación a ellas.
- §4: evalúan NER de consultas de comercio electrónico y biomédico. Sus resultados pertenecen a esas tareas y esquemas de etiquetado.

## Transferencia al proyecto

La ronda humana retoma únicamente la idea de un ajuste final con referencia humana después de aprender con etiquetas auxiliares. No implementa NEEDLE completo, su adaptación MLM, CRF, completado de etiquetas ni pérdida específica. Nuestra referencia es asistida por IA y confirmada por un humano; no equivale a su conjunto fuerte en independencia.

Dos épocas fijas, tasa 2e-6 y tres semillas son decisiones locales congeladas, no parámetros transferidos de sus resultados. El artículo no estudia sentimiento dirigido peruano ni valida AP, las etiquetas auxiliares locales o los mínimos de calidad. Una mejora debe medirse sobre el desarrollo del proyecto y posteriormente comprobarse de forma independiente.
