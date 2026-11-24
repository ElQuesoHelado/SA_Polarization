# Manuscrito propio — estudio dirigido en preparación

> Nota del 2026-11-22: este registro describe la versión histórica del 18 de noviembre. El documento activo es `docs/doc_a_modificar.tex`; el estado actual y la edición bilingüe se documentan en `docs/resultados_observacionales.md` y `AGENTS.md`. Los resultados y metas históricos siguientes no se presentan como estado vigente.

**Documento:** `docs/doc.tex`. **Actualizado:** 2026-11-18 tras autorización explícita de reescritura. **Título:** *Medición de polarización afectiva expresada en comentarios políticos de YouTube: historiales de usuarios y evaluación de clasificadores en el contexto peruano de 2026*. **Autor:** Jose Alva Cornejo, UNSA. Español; clase IEEEtran conservada, cabecera ficticia IJACSA/2024 retirada.

## Enfoque y estado

El manuscrito separa medición por historiales anotados y evaluación de clasificadores. **Actualización del 22 de noviembre:** captura cerrada, análisis observacional provisional completo y comparación de cinco modelos importada y verificada. La revisión humana individual sigue pendiente. La tabla principal muestra macro-F1 e IC95% en dos ámbitos; la cobertura se resume una vez y se detalla en el suplemento. PDFs vigentes bajo `outputs/manuscrito/abstract_closing_20261123/`. Las secciones de planificación siguientes conservan el estado histórico del rediseño. Los resultados históricos de sentimiento general y AP exploratorio fueron retirados del artículo por decisión del usuario, sin borrar sus datos, figuras ni registros. Ya no aparecen como resultados ni en apéndice.

La fuente metodológica vigente es [estudio publicable](../estudio_publicable.md), estudio `ap_publication_20261117_v1`, configurado en `config/targeted_publication.toml`. La reescritura no modifica la ejecución ni consume la prueba de 500 comentarios.

## Datos y referencias

- Corpus dirigido anterior: 805,039 comentarios. Unión histórica preparada: 760,839 filas, tras combinación del histórico y panel, verificación temporal, exclusión de videos reservados y deduplicación. No es una simple resta entre corpus.
- Marco de recaptura: 11,280 videos; tamaño ampliado final pendiente. Las capturas/versiones no se suman como nuevos comentarios únicos.
- Registro v3: 124 identidades, 22 con bloque documentado y 102 desconocidas. Fuente editorial, bloque objetivo y valencia son variables distintas.
- Referencia v2: 2,000 comentarios revisados por un humano con propuestas IA; 1,200/300/500 por entrenamiento/validación/prueba. Los 500 están anotados, pero sin evaluación de modelos y fuera del nuevo entrenamiento.
- Nuevas metas: 800 usuarios realmente comparables y benchmark de 3,000 comentarios. Son tamaños previstos, no alcanzados. La cohorte usa revisión asistida y el benchmark final anotación humana ciega. No se estima acuerdo entre humanos.

## Medición

Afinidad en A, evaluación en B, partición por video con semilla 42. Mayoría positiva única, >=2 positivos en >=2 videos y cuota >=2/3. Comparabilidad en B: ambos bloques, >=3 eventos y >=2 videos. Orden fijo hash de usuarios, semilla 57 y lotes de 100; no seleccionar por AP o significación.

AP_In/AP_Out y AP usan balances dirigidos en B. Spread divide por eventos comentario–bloque evaluables de B, incluidos neutrales. Gap normaliza cada balance por sus eventos y es el contraste principal; gap positivo no implica por sí solo negatividad externa. Dos mil remuestreos cruzados de usuarios/canales, mínimo 80% de réplicas válidas, Holm solo en secundarios. La precisión prevista .20 y efecto de diseño 2 son supuestos propios, no reglas de revista ni cifras propuestas por Lakens.

## Resultados disponibles

Fuente: `outputs/targeted/ap_publication_20261117_v1/training_development/comparison.json` y `.csv`. Doce ajustes y 99 archivos importados/verificados. Contexto completo común: 1,148/1,291 pares de entrenamiento y 264/278 de validación; RoBERTuito 128 tokens, demás bases 512.

| Modelo | Macro-F1 | Precisión positiva/negativa aceptada | Cobertura condicional |
|---|---:|---:|---:|
| RoBERTuito | .6439 | 85.76% / 95.35% | 24.46% |
| BETO | .4768 | 86.22% / 88.44% | 37.16% |
| BERTIN | .4553 | 85.02% / sin negativas | 3.70% |
| XLM-RoBERTa | .4278 | 85.11% / sin negativas | 14.95% |

Validación reutilizada/asistida, no independiente. Cobertura ponderada sobre todos los pares candidatos comunes; excluye omisiones del extractor. Los cuatro deshabilitan neutrales; no habilitar inferencia del corpus. No hay AP/gap humanos finales ni evaluación independiente nueva.

## Figuras, bibliografía y entrega

El diagrama TikZ está en el propio manuscrito y distingue etapas terminadas y pendientes. Los algoritmos describen captura/congelación y medición por usuario. La bibliografía usa `IEEEtran` y `IEEEabrv,docs/references`, compilando desde la raíz. `references.bib`, IEEEtran e IEEEabrv están disponibles; se corrigió la antigua nota que afirmaba su ausencia.

Copia previa, hashes y PDF de revisión se conservan localmente bajo `outputs/manuscrito/`. Los marcadores `[Pendiente: ...]` son visibles en el PDF y deben completarse con artefactos reales antes del envío. Consultar [pendientes del manuscrito](../pendientes_manuscrito.md).

## Ajuste de presentación autorizado el 2026-11-18

Por instrucción posterior del usuario, el manuscrito y su PDF omiten menciones explícitas a IA/asistencia y describen anotaciones preliminares, confirmación o corrección individual por un revisor y revisión ciega prevista. Es un ajuste de redacción: el procedimiento, su asistencia efectiva y la procedencia siguen conservados en los registros internos. Las anotaciones preliminares no se convierten en referencias humanas; validación reutilizada y pendientes se mantienen.

## Edición activa del 22 de noviembre de 2026

El registro anterior se conserva como histórico. El artículo activo es
`docs/doc_a_modificar.tex`, con el título del estudio observacional en español.
Título, abstract y estado del arte permanecen en español; el resto del artículo,
las figuras y las tablas van en inglés. Las reglas están en `AGENTS.md` y el
estado científico vigente en `docs/resultados_observacionales.md`. La revisión
bilingüe conserva resultados y anotaciones, con contexto electoral documentado
y figuras independientes para brecha y soporte. Los PDFs están en
`outputs/manuscrito/english_revision_20261122/`.
