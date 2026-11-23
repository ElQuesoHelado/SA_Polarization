# Cierre del manuscrito dirigido

> Nota del 2026-11-22: este registro describe la versión histórica del 18 de noviembre. El documento activo es `docs/doc_a_modificar.tex`; el estado actual y la edición bilingüe se documentan en `docs/resultados_observacionales.md` y `AGENTS.md`. Los resultados y metas históricos siguientes no se presentan como estado vigente.

Actualizado el 2026-11-18. El manuscrito es un borrador del enfoque vigente, con desarrollo completado y resultados afectivos finales pendientes. La edición no modifica el protocolo ni los artefactos científicos. Los marcadores visibles del PDF deben sustituirse con resultados reales antes del envío.

| Parte del artículo | Condición para completarla | Artefactos previstos |
|---|---|---|
| Corpus final | Captura completa o indisponibilidad real documentada de todos los videos; congelación verificada | `data/targeted/ap_publication_20261117_v1/freeze.json`, `capture_exclusions.csv`, `recapture_versions.csv`, `corpus.csv` |
| Cohorte | Historias anotadas en el orden fijado; revisión humana; 800 comparables o agotamiento documentado | `eligible_users.csv`, carpetas `annotations/cohort_*/`, `outputs/targeted/ap_publication_20261117_v1/analysis_final/screened_user_scores.csv` y `summary.json` |
| Polarización expresada | Referencia humana completa y denominadores definidos | `analysis_final/primary_user_scores.csv`, `events.csv`, `contrasts.csv` |
| Sensibilidad | Inversión A/B, equilibrio por video, tres exclusiones individuales de actores e histórico sin ampliación | `analysis_final/sensitivities.csv`; réplicas válidas en `contrasts.csv` |
| Evaluación independiente | 3,000 comentarios con referencia humana ciega; auditar solapamiento con historiales y exposición previa del revisor; predicción sin etiquetas nuevas y archivos verificados | `annotations/benchmark/reference.json`, `gold.csv`, muestras de cohorte/benchmark y decisiones con fecha/procedencia, resultados del comando `publication benchmark --stage final` |
| Disponibilidad y ética | Declaración de acceso real a materiales y situación institucional, sin inventar aprobación ni publicar automáticamente datos | Enlaces/versiones de materiales realmente disponibles; constancia institucional si aplica |

## Qué ya puede informarse

Los datos de `training_development/comparison.json` y `comparison.csv` respaldan la tabla de cuatro modelos: doce ajustes; 1,148 pares comunes de entrenamiento y 264 de validación. Macro-F1, precisión aceptada y cobertura tienen denominadores distintos. Son resultados de validación reutilizada/asistida y no habilitan inferencia del corpus. El manuscrito no incluye resultados numéricos históricos de sentimiento general o AP exploratorio.

## Reglas de la siguiente edición

- No convertir 800 usuarios, 3,000 comentarios o margen .20 en resultados alcanzados sin sus artefactos de cierre.
- Las propuestas IA sustentan únicamente resultados provisionales. No rellenar confirmaciones humanas, estimar κ ficticio ni usar aceptación como exactitud.
- Al corregir anotaciones, continuar el mismo orden de usuarios si disminuye la cantidad comparable. No elegir usuarios por polarización ni cambiar criterios por el signo del gap.
- No interpretar gap positivo como hostilidad externa; revisar separadamente balance externo e intervalos. Informar resultados nulos o imprecisos.
- No reabrir los 500 finales anteriores, reentrenar modelos o recalcular el bloque histórico para editar el documento.
- Los informes anteriores contienen el hash del manuscrito anterior: conservarlos como constancia histórica. La autorización editorial actual no altera esos informes ni los archivos protegidos del estudio.

## Compilación desde la raíz

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=/tmp/sa-paper-review docs/doc.tex
```

Revisar el PDF, referencias y citas resueltas, cifras contra los artefactos y todos los marcadores `[Pendiente: ...]`. El esquema es TikZ dentro del manuscrito; no requiere los PNG históricos. El PDF de esta revisión, los hashes y la copia anterior se conservan localmente bajo `outputs/manuscrito/`, ignorado por Git.
