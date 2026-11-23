# Ampliación de modelos: 2026-11-22

La comparación activa conserva RoBERTuito, BETO y XLM-RoBERTa-base e incorpora
MrBERT-es y mDeBERTa-v3-base. BERTIN queda archivado: no se borran sus resultados
ni se reescribe la comparación inicial de cuatro bases.

El experimento `encoder_extension_20261122_v1` usa la configuración adicional
`config/targeted_publication_models_v2.toml`, protocolo
`targeted-publication-model-extension-v1`. Los artefactos están en
`data/targeted/ap_publication_20261117_v1/model_experiments/encoder_extension_20261122_v1/`;
los informes usan la misma jerarquía bajo `outputs/targeted/`.

## Datos y receta

Solo se ajustan las dos bases nuevas con semillas 42/43/44: **seis ajustes**.
Se conservan los mismos 1,148 pares de entrenamiento y 264 de validación comunes
originales, en el mismo orden y con iguales etiquetas y pesos. La preparación
verifica contexto completo para ambos tokenizadores; cualquier exclusión adicional
detiene el trabajo. No entran etiquetas del benchmark ni de las nuevas cohortes.

La receta conserva AdamW, tasa 2e-5, decaimiento .01, clipping 1, lote efectivo
16 y físico 4, máximo ocho épocas, paciencia dos y ponderación inversa de la raíz
de la frecuencia de clase. La validación nueva usa lotes físicos de cuatro para
limitar memoria. Se promedian probabilidades de semillas; temperatura y umbrales
se ajustan solo con validación, manteniendo precisión .85 y mínimo diez predicciones
por clase. No cambian las cinco etiquetas ni las definiciones de métricas.

MrBERT-es usa tokenizador rápido, clasificación ModernBERT con SDPA y compilación
automática desactivada. El límite experimental es 512 tokens, aunque el recurso
admita 8,192. mDeBERTa usa su tokenizador SentencePiece y 512 tokens. Las revisiones
inmutables y las dependencias efectivas quedan en los manifiestos.

## Preparación y operación privada

```bash
.venv/bin/sa-polarization targeted publication train --experiment-id encoder_extension_20261122_v1 --training-config config/targeted_publication_models_v2.toml
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task train --operation submit --create-dataset
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task train --operation status
# Esperar la versión exacta del dataset ready antes de start.
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task train --operation start
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task train --operation fetch
.venv/bin/sa-polarization targeted publication training-report --experiment-id encoder_extension_20261122_v1
```

No reenviar un trabajo publicado/iniciado. Consultar su manifiesto y versión
exacta; los checkpoints y descargas parciales se conservan. Los recursos privados
son distintos de los del estudio anterior.

## Predicción y comparación

```bash
.venv/bin/sa-polarization targeted publication predict --experiment-id encoder_extension_20261122_v1 --scope benchmark
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task predict --scope benchmark --operation submit
# Esperar la nueva versión exacta ready.
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task predict --scope benchmark --operation start
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task predict --scope benchmark --operation status
.venv/bin/sa-polarization targeted publication remote --experiment-id encoder_extension_20261122_v1 --task predict --scope benchmark --operation fetch
.venv/bin/sa-polarization targeted publication benchmark --experiment-id encoder_extension_20261122_v1 --scope benchmark --stage provisional
```

El payload de predicción contiene candidatos/textos del benchmark y checkpoints
nuevos, nunca etiquetas de evaluación ni formularios humanos. La comparación
local verifica y reutiliza los tres CSV originales de referencia. Recalcula el
panel común a cinco modelos; no arrastra los 3,222 pares del panel anterior.
Los intervalos remuestrean videos 2,000 veces; los diez contrastes macro-F1 usan Holm.

El benchmark ya fue examinado y la selección de candidatos es posterior a sus
resultados: esta ampliación no es evaluación final independiente. Propuestas IA
y revisiones humanas pendientes conservan su procedencia. No abre los 500
reservados, promueve modelos, infiere el corpus ni modifica el gap de los usuarios.

## Documento

`docs/doc_a_modificar.tex` sigue activo y se edita incrementalmente desde la última
versión del usuario; `docs/references.bib` sigue como bibliografía compartida.
Solo se incorporan cifras desde informes verificados. Mientras estén en curso,
las filas nuevas muestran evaluación ausente, no ceros. Las tres referencias
conservan sus cifras y el contexto común inicial se identifica como tal.

## Seguimiento de la ejecución iniciada

El entrenamiento privado exacto es
`josealvacornejo/sa-polarization-pub-encoders-train/2`, con el mismo dataset privado v1 ready.
La versión 1 fue cancelada por el usuario sin llegar a ejecutar; su manifiesto y
la evidencia del reintento autorizado quedan bajo `kaggle/train/attempts/0001/`.
No reenviarlo. El servicio transitorio de usuario
`sa-polarization-encoder-extension-20261122.service` sigue ese trabajo, importa los
resultados, prepara la predicción privada y genera la comparación. No arranca tras
reiniciar el equipo ni reintenta errores. Su controlador y registros están bajo
`outputs/targeted/ap_publication_20261117_v1/model_experiments/encoder_extension_20261122_v1/`.

`runtime_status.json` es un registro, no una prueba de liveness: consultar también
el servicio y el bloqueo `continuation.lock`. La actualización posterior del
artículo exige fuentes sin cambios respecto de `observational_manuscript_guard.json`; si el
usuario editó el documento, conserva sus cambios y deja aviso pendiente. Las cifras
se toman exclusivamente del informe sellado de cinco modelos.

El reintento se ejecutó una vez tras confirmar cancelación, registros vacíos y
cuota GPU disponible. `remote --operation retry --task train --experiment-id
encoder_extension_20261122_v1` conserva versiones previas y rechaza trabajos
activos, parcialmente ejecutados o envíos inciertos. No es un bucle automático.
La predicción siguiente utiliza el paquete de código congelado del entrenamiento,
verificado contra el manifiesto del archivo publicado, aunque cambie el código
local de análisis. La integración posterior del manuscrito solo sustituye el
bloque de modelos y preserva los diagnósticos observacionales.

## Continuación verificada del 22 de noviembre

El entrenamiento `/2` terminó y se importó tras verificar los **seis ajustes**,
las tres semillas por modelo y **56 archivos**. El archivo descargado tiene
SHA-256 `308abb30f38dd5e380bc94d66453685d9be8c2aa6fb4392ab0f8a57cd82b2dc6`.
El informe local `training_development/` reproduce las métricas guardadas:

| Modelo | Macro-F1 ponderado | Cobertura de pares candidatos |
|---|---:|---:|
| MrBERT-es | 0.5322 | 25.75% |
| mDeBERTa-v3-base | 0.4451 | 14.88% |

Son diagnósticos de validación reutilizada/asistida sobre 264 pares comunes,
no resultados del benchmark ni cobertura integral de extracción. MrBERT-es
habilita positivos y negativos; mDeBERTa solo positivos. Ninguno habilita
neutrales con la calibración fijada. No se selecciona ni promueve un modelo.

El controlador se reanudó después de importar el entrenamiento, bajo la
invocación `3bf97a6f6ea04a9eb636fd8517695abc`. Las consultas de estado de
datasets y kernels admiten hasta tres intentos, separados por 30 segundos,
ante errores de transporte. Esta regla no repite publicaciones, envíos,
descargas ni ejecuciones fallidas. La suite local ejecutó 260 pruebas:
257 correctas y tres omitidas por dependencias de entrenamiento locales.

## Comparación terminada y presentación del artículo

La predicción privada exacta
`josealvacornejo/sa-polarization-pub-encoders-predict/1` terminó usando el dataset
v2 ready. Se importaron los dos CSV con verificación de muestra, entrenamiento y
hashes; no repetir la ejecución. El informe sellado `benchmark_provisional/`
compara cinco modelos sobre 3,000 comentarios, 5,165 pares integrales y 3,222
candidatos comunes con contexto completo.

RoBERTuito conserva el mayor macro-F1 integral (.3836), seguido por BETO (.3237),
MrBERT-es (.3225), mDeBERTa (.3086) y XLM-R (.2832). Los contrastes por video con
Holm favorecen RoBERTuito frente a las cuatro alternativas; BETO y MrBERT-es no
presentan diferencia clara, sin demostrar equivalencia. Esta comparación sigue
siendo acuerdo con propuestas IA pendientes de revisión humana, sobre una muestra
ya examinada, no evaluación final independiente.

La tabla principal muestra macro-F1 e IC95% en ambos ámbitos. La cobertura se
resume una vez en el texto y se detalla en el suplemento con la precisión aceptada.
Los intervalos comunes se derivan en `manuscript_statistics/`, fuera del informe
original, mediante 2,000 remuestreos por video con semilla 57 y los mismos pesos y
orden de videos. El generador rechaza intervalos incompatibles o alterados.
El suplemento admite `--model-report PATH`; mantiene los diagnósticos históricos
de tres referencias con su alcance explícito, sin atribuirlos a cinco modelos.

PDF principal y suplemento: `outputs/manuscrito/model_presentation_20261122/`.
La suite pasó 264 pruebas, con 261 correctas y tres omitidas. No se promueve un
modelo ni se modifica la medición anotada de polarización.
