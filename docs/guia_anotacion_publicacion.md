# Anotación del benchmark y de los historiales

La anotación identifica todos los actores políticos explícitos de cada comentario y la valoración expresada hacia cada uno. La línea editorial del canal y las preferencias supuestas del autor no determinan las etiquetas. Las muestras definitivas se preparan después de congelar la captura.

## Orden de trabajo

El usuario autorizó obtener resultados provisionales y revisar después las propuestas tanto del benchmark como de los historiales. En el estudio activo el benchmark pasó a revisión asistida mediante una política adicional sellada; su manifiesto original y exportaciones ciegas permanecen conservados. Otras ejecuciones mantienen su modo ciego original. Las tandas de 50 comentarios organizan una muestra ya fijada: no eliminan textos ni cambian el orden de usuarios o los criterios de comparabilidad.

```bash
# Consultar el avance y la parada por comparabilidad.
.venv/bin/sa-polarization targeted publication annotation-progress
# Exportar una tanda según la política efectiva de revisión.
.venv/bin/sa-polarization targeted publication annotation-batch --sample benchmark --batch-number 1
# Abre la primera tanda con pendientes; guarda cada confirmación y permite reanudar.
.venv/bin/sa-polarization targeted publication review --sample benchmark
# También se puede elegir una tanda concreta.
.venv/bin/sa-polarization targeted publication review --sample benchmark --batch-number 2
```

Para la cohorte, sustituye `benchmark` por `cohort_0001`. La exportación incluye las pistas del extractor y una plantilla de propuestas con `annotations: null`; ese valor significa pendiente, no ausencia de objetivos. Completar la plantilla por lectura íntegra y conservar el hash de muestra, el origen real y una nota por comentario. Importar con `publication proposals --sample cohort_0001 --batch archivo.json`. La importación no escribe confirmaciones humanas. La revisión admite aceptar, editar, dejar pendiente o salir, y exige confirmar la lectura completa. Una omisión o lista vacía requiere la misma atención que una propuesta con actores.

## Criterios comunes

Todos los ejemplos siguientes son ficticios. «Actor A» y «Actor B» no representan identidades reales del registro.

| Texto | Anotación |
|---|---|
| «Confío en Actor A» | Actor A: `positive` |
| «Actor A es un corrupto» | Actor A: `negative`; se anota la valoración del autor, sin dar por cierta su acusación |
| «Actor A participó en la reunión» | Actor A: `neutral` |
| «Actor A hizo algo bueno, pero también lo rechazo por sus abusos» | Actor A: `mixed`, si ambas valoraciones recaen sobre él |
| «Qué maravilla lo de Actor A…» | `not_evaluable` si la ironía no puede resolverse con el texto |
| «Apoyo a Actor A y rechazo a Actor B» | Dos objetivos: A positivo y B negativo |
| «No estoy de acuerdo contigo» | `[]`, si no hay otro objetivo político explícito |
| «Ese hombre nos salvará» | `[]` si solo el título o el padre permiten identificarlo |

Un apodo explícito que identifique al actor puede anotarse aunque el extractor lo omita; esas omisiones permanecen como errores del extractor. Si la identidad no figura en el registro, usar `unregistered:nombre`, sin ampliar alias ni asignar bloques durante la anotación. Copiar la mención exacta para obtener sus posiciones. Cada actor se etiqueta una sola vez por comentario, considerando todas sus menciones.

`neutral` exige un objetivo identificado sin valoración favorable o desfavorable. `not_evaluable` exige un objetivo identificado cuya valoración es incierta. La ausencia de objetivo es `[]`; una celda vacía sigue pendiente. No deducir apoyo a A de una crítica a B, ni trasladar una crítica al interlocutor hacia el político que supuestamente apoya.

## Cierre

Tras completar todas las tandas, cerrar la referencia con `publication reference-close --sample benchmark` o el lote correspondiente. Las propuestas, las confirmaciones y el cierre son archivos distintos. Los resultados provisionales no sustituyen la referencia humana; la aceptación de propuestas no estima acuerdo entre humanos ni exactitud independiente. Las correcciones pueden exigir revisar más usuarios en el mismo orden hasta alcanzar la meta o agotar el marco.

## Estado de la primera cohorte

`ap_publication_20261117_v1` tiene propuestas completas para los 4,701 comentarios de `cohort_0001` (100 usuarios, 95 tandas) y para los 3,000 comentarios del benchmark (60 tandas). Las fuentes de lectura y las correcciones posteriores se conservan separadas; ninguna propuesta constituye una confirmación humana. La ampliación conserva historiales completos por orden congelado y ahora cierra únicamente los tres lotes ya seleccionados (300 usuarios examinados, todos sus comparables); la lectura ahora aplica el screening exacto descrito abajo. `annotation-progress` registra el estado reanudable y no usa AP/gap para decidir la parada.

Cuando comience la revisión humana, usa `review --sample benchmark` y repite el comando para reanudar las tandas pendientes. Tras confirmar o corregir las 3,000 propuestas, ejecuta `reference-close --sample benchmark`. Revisa del mismo modo cada `cohort_NNNN` y cierra sus referencias solo después de sus confirmaciones reales. Todos estos subcomandos llevan el prefijo `.venv/bin/sa-polarization targeted publication`. Estas revisiones están aplazadas y no bloquean el avance provisional autorizado.

El informe local de preparación e integridad queda en `outputs/targeted/ap_publication_20261117_v1/cohort_proposals_0001/completion.json`. Sus conteos describen propuestas pendientes; no estiman exactitud, acuerdo entre revisores ni polarización final.


## Lectura acelerada por afinidad

Desde la enmienda del 21 de noviembre, `screening-batch --sample cohort_NNNN` exporta los comentarios necesarios para resolver primero la afinidad en A. Tras importar cada tanda, repetirlo: la cola cambia al incorporar evidencia. Los participantes que califican deben tener A y B completamente anotados. Una exclusión solo puede omitir lectura si una cota conservadora demuestra que ningún bloque alcanzaría la afinidad exigida aunque todos los textos pendientes fueran favorables. No se excluye por una predicción ni por ausencia de pistas del extractor.

`screening-status --sample cohort_NNNN` muestra los IDs pendientes y las exclusiones. `screening-status --sample cohort_NNNN --stage final` recalcula todo usando exclusivamente decisiones humanas reales. `review` prioriza esa evidencia; `reference-close` exige que no falten lecturas necesarias. Una corrección puede reabrir textos de A o B. Un comentario sin leer conserva anotación nula y motivo `skipped_affinity`; no equivale a una lista vacía revisada. El benchmark sigue requiriendo la revisión individual de sus 3,000 comentarios.

La inferencia y comparación del benchmark pueden avanzar mediante `predict`, `remote` y `benchmark` con `--scope benchmark`, sin esperar la ampliación de usuarios. Los resultados de esta rama se guardan separados y siguen siendo provisionales hasta la revisión.


## Techo vigente de revisión

La política `fixed_user_scope/` sustituye la meta anterior de 800 comparables por **300 usuarios examinados**. Revisar las propuestas de `cohort_0001`, `cohort_0002` y `cohort_0003`, además del benchmark de 3,000 comentarios. No crear una cuarta cohorte. El screening se recalcula con cada corrección humana y puede requerir leer comentarios antes omitidos de esos mismos usuarios. Los resultados actuales son provisionales; los formularios humanos continúan separados y pendientes.
