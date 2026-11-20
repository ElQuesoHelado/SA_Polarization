# Anotación del benchmark y de los historiales

La anotación identifica todos los actores políticos explícitos de cada comentario y la valoración expresada hacia cada uno. La línea editorial del canal y las preferencias supuestas del autor no determinan las etiquetas. Las muestras definitivas se preparan después de congelar la captura.

## Orden de trabajo

Primero anota el benchmark a ciegas; después revisa las propuestas de los historiales. Las tandas de 50 comentarios organizan la lectura de una muestra ya fijada: no eliminan textos ni cambian el orden de usuarios o los criterios de comparabilidad.

```bash
# Exportar una tanda del benchmark: únicamente ID y texto, sin propuestas ni pistas.
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
