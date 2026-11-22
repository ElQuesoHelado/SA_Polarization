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
`josealvacornejo/sa-polarization-pub-encoders-train/1`, con dataset nuevo v1 ready.
No reenviarlo. El servicio transitorio de usuario
`sa-polarization-encoder-extension-20261122.service` sigue ese trabajo, importa los
resultados, prepara la predicción privada y genera la comparación. No arranca tras
reiniciar el equipo ni reintenta errores. Su controlador y registros están bajo
`outputs/targeted/ap_publication_20261117_v1/model_experiments/encoder_extension_20261122_v1/`.

`runtime_status.json` es un registro, no una prueba de liveness: consultar también
el servicio y el bloqueo `continuation.lock`. La actualización posterior del
artículo exige fuentes sin cambios respecto de `manuscript_guard.json`; si el
usuario editó el documento, conserva sus cambios y deja aviso pendiente. Las cifras
se toman exclusivamente del informe sellado de cinco modelos.
