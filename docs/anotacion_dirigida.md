# Anotación humana de valoraciones dirigidas

El protocolo vigente, autorizado por el usuario el 2026-11-14, usa propuestas de IA para **2,000 comentarios únicos** y revisión de cada uno por **un humano**. Incluye los 500 de prueba. No equivale a dos revisores humanos ni a una referencia humana independiente de las propuestas. El protocolo original de dos revisores se conserva como alternativa, pero no se usa en esta ejecución.

## Cómo continuar: revisión asistida v2

La revisión original terminó: **2,000 comentarios, 1,953 propuestas aceptadas y 47 corregidas**. Se conserva intacta en `targeted_20261114`. Al comprobar el extractor se detectó cobertura insuficiente. El usuario autorizó ampliarlo y revisar casos adicionales; la ejecución activa es **`targeted_20261115_v2`** con configuración independiente.

La nueva muestra conserva 2,000 comentarios y las cuotas 1,200/300/500 y 1,600 principales/400 respuestas. **La revisión y la importación están completas:** 1,349 revisiones heredadas verificadas y 651 nuevas (641 aceptadas y 10 corregidas). Las nuevas abarcan 502 comentarios nuevos y 149 anteriores que necesitaban comprobar identidad, contexto u objetivos omitidos. No hay revisiones pendientes. [Estado y diseño completos](estado_targeted_20261115_v2.md).

Desde la raíz del proyecto:

```bash
.venv/bin/sa-polarization targeted assisted-review --config config/targeted_v2.toml --run-id targeted_20261115_v2
```

El formulario muestra únicamente pendientes, con texto, contexto y propuesta. Revisa también los objetivos que puedan faltar. Las propuestas `[]` requieren revisión. Se guarda cada confirmación y se reanuda con el mismo comando.

- `a`: conservar propuesta; después confirmar con `s` que revisaste todo el comentario.
- `e`: reemplazar la propuesta por tu anotación completa, añadiendo todos los objetivos correctos. Copia la mención exacta y elige una de las cinco etiquetas; Enter termina la lista y `s` confirma.
- `s`: dejar el comentario pendiente.
- `q`: salir.

Las decisiones nuevas se guardan en `human_review.csv`. Las herencias viven aparte en `inherited_reviews.csv`: se comprueban contra las decisiones humanas originales, sus propuestas, textos, contexto y hashes. No se rellenó `review_complete` para simular una confirmación nueva. Propuestas IA, herencias y decisiones humanas se conservan separadas.

**Criterio principal:** menciones explícitas. Un nombre o apodo puede ser válido aunque el extractor no lo encuentre; conservar el objetivo correcto y dejar que la evaluación contabilice esa omisión. Una referencia resuelta únicamente desde título/padre se separa para sensibilidad. No trasladar una crítica del interlocutor al político que supuestamente apoya, ni sustituir una persona por su movimiento. El registro no se amplía al leer los nuevos casos de prueba; usar `unregistered:nombre` para objetivos fuera de él.

Comprobar el estado sin escribir ni abrir la prueba:

```bash
.venv/bin/sa-polarization targeted assisted-import --config config/targeted_v2.toml --run-id targeted_20261115_v2 --check-only
```

El piloto v2 y la referencia completa ya se importaron tras auditar las correcciones. El usuario confirmó como apodos explícitos las cuatro referencias nuevas mediante «sombrero/sombrerito» y «chancho»: permanecen en el principal sin ampliar alias, y las omisiones del extractor siguen contando como errores. La proporción de propuestas aceptadas no estima exactitud ni acuerdo entre humanos. La nueva prueba de 500 también es asistida, por elección del usuario, y solo se evaluará una vez tras fijar el modelo y sus umbrales.

La rectificación de tres casos contextuales del piloto original y sus versiones sigue en `targeted_20261114/annotations/pilot_user_correction.json`; no se alteró. El registro original permanece semilla, mientras que el registro v2 independiente fue auditado. No cambiar definiciones ni alias de la muestra v2: otra modificación requiere otra ejecución y prueba independiente, conservando todo el trabajo previo.

## Preparación del modo original de dos revisores (alternativa)

1. Consultar `config/political_targets.json` y la cola de actores del estudio. Revisar identidad, alias, bloque, fuentes y vigencia. `unknown` es válido: no forzar un bloque. Tras revisar las definiciones, cambiar únicamente `status` a `reviewed`. Si cambian actores o alias después de muestrear, regenerar la muestra antes de etiquetar.
2. Ejecutar `targeted annotation-export`. Los CSV de cada revisor omiten canal, etiqueta editorial, partición del modelo y predicciones. El manifiesto privado de muestreo sí conserva procedencia y probabilidades.
3. Cada persona completa su propio archivo, comenzando con los 200 registros `pilot=True`. Mantener identificadores y texto originales. No intercambiar etiquetas durante la revisión independiente.

Si se cambian actores/alias antes de que nadie empiece, `targeted annotation-export --run-id ... --refresh-unreviewed` regenera la muestra usando el corpus/panel ya capturados y conserva una copia de los formularios anteriores. Se niega a hacerlo si existe cualquier anotación humana, adjudicación o modelo. Si ya se empezó a revisar, conservar esa ejecución y preparar otra; no borrar datos para resolver el conflicto.

Para evitar escribir JSON u offsets manualmente, existe un formulario local en terminal:

```bash
sa-polarization targeted annotate --run-id targeted_20261114 --reviewer 1 --pilot-only
sa-polarization targeted annotate --run-id targeted_20261114 --reviewer 2 --pilot-only
sa-polarization targeted annotation-import --run-id targeted_20261114 --pilot-only
```

Cada persona ejecuta únicamente su formulario. El programa pide las decisiones humanas, calcula offsets al copiar la mención, guarda cada registro confirmado y reanuda los pendientes. `:q` sale. Para completar el resto, omitir `--pilot-only`. También se pueden editar los CSV directamente.

## Unidad y objetivo

La unidad es comentario–actor/grupo político mencionado explícitamente. Anotar todos los objetivos políticos identificables del texto, incluso cuando no expresen una valoración. No usar la línea editorial del canal como evidencia. El título y el comentario padre ayudan a comprender el caso, pero el análisis principal exige una mención localizable en el comentario.

Si el actor no está en el registro, usar `unregistered:nombre`. Esto permite contar los objetivos omitidos por el generador al evaluar recall. No añadir apodos o asignaciones nuevas al registro durante la prueba final.

Un periodista, un medio o un interlocutor no se convierte en actor partidario por publicar en un canal etiquetado. La crítica de una política pública no se traslada automáticamente a un juicio afectivo de quien la propone.

## Etiquetas

| Etiqueta | Criterio |
|---|---|
| `positive` | Valoración favorable expresada hacia el actor o grupo: aprecio, confianza, aprobación personal o apoyo manifiesto. |
| `negative` | Valoración desfavorable hacia ese actor/grupo: rechazo, desprecio, desconfianza o descalificación. No implica necesariamente toxicidad. |
| `neutral` | El actor está identificado, pero se lo menciona de forma informativa sin una evaluación favorable/desfavorable. |
| `mixed` | Coexisten valoraciones favorables y desfavorables del mismo objetivo y no corresponde reducirlas a un signo. |
| `not_evaluable` | El objetivo aparece pero no puede determinarse su valoración con evidencia suficiente; por ejemplo ironía irresoluble o texto ininteligible. |

La ausencia de objetivo político se marca con una lista vacía `[]`. Un alias que no refiere al actor político tampoco se anota como objetivo. No deducir simpatía por A a partir de una crítica a B, ni ideología del autor por mencionar un nombre.

## Formato

La columna `annotation_json` contiene una lista JSON; `review_complete` debe decir `true` cuando el registro esté revisado.

Ejemplo ficticio, texto `Apoyo a Actor A; rechazo a Actor B`:

```json
[
  {"target_id":"actor_a","valence":"positive","mention_start":8,"mention_end":15},
  {"target_id":"actor_b","valence":"negative","mention_start":27,"mention_end":34}
]
```

Los offsets son posiciones de caracteres Python: inicio incluido y fin excluido. El programa comprueba límites, aunque el revisor debe comprobar que el tramo identifica realmente al objetivo. Los IDs del ejemplo no pertenecen al registro real.

Para un comentario sin objetivo: `annotation_json=[]`, `review_complete=true`. Una celda vacía no significa revisión terminada.

## Acuerdo y adjudicación del modo original; prueba final

Solo en el modo original, ejecutar `targeted annotation-import` después de ambas revisiones. Se calcula acuerdo sobre la unión de objetivos detectados por los humanos, sin inflarlo con miles de entidades ausentes. Si κ < 0.70 o no es calculable, revisar el protocolo y repetir el piloto. Los desacuerdos se exportan a `adjudication.csv`; completar `annotation_json` y `review_complete` por consenso y reimportar. Estos comandos se niegan a importar una ejecución configurada como asistida.

Los 500 comentarios de prueba no se usarán para seleccionar ejemplos, hiperparámetros o umbrales. La prueba se abre una sola vez mediante `targeted evaluate`. Un fallo requiere una evaluación independiente para un método revisado; no se puede declarar superada reutilizando sus etiquetas después de ajustar.

Las anotaciones y comentarios se conservan bajo `data/`, ignorado por Git. Ejecutar dos modelos no equivale a dos revisores humanos. En el modo vigente hay un humano y propuestas IA declaradas explícitamente.
