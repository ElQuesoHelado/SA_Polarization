# Revisión v2 del estudio dirigido — 2026-11-15

La ejecución activa es **`targeted_20261115_v2`**, con `--config config/targeted_v2.toml`. **Referencia cerrada y rondas de comparación completadas en GPU. Ningún candidato cumple todos los criterios de desarrollo.** BETO anterior conserva el mayor macro-F1 (0.6724); las variantes con marcadores aumentan cobertura, pero reducen macro-F1. Todos fallan los mínimos conjuntos 0.75/60%. Los 500 comentarios finales siguen reservados, sin evaluación ni publicación de sus etiquetas. La inferencia de producción permanece bloqueada.

**Comparación completada:** RoBERTuito/BETO en `development_20261115_v1`, con [protocolo de entrenamiento y validación](entrenamiento_validacion_dirigida.md), 12 ajustes y criterios conservados. Diagnóstico y búsqueda privados terminaron en las versiones 2 y 3 del kernel; sus informes y checkpoints se descargaron, verificaron e importaron bajo `experiments/development_20261115_v1/`. Estado remoto por tarea en `kaggle/development_20261115_v1/`. El modelo anterior permanece intacto.

## Anotaciones originales y diagnóstico

La revisión original terminó: **2,000 comentarios, 1,953 propuestas aceptadas y 47 corregidas**. No equivale a exactitud ni acuerdo entre humanos. La ejecución `targeted_20261114` conserva sus archivos sin cambios; no importar con el registro v2 ni reemplazar sus definiciones. Su referencia final no se generó, pues el registro inicial permanecía como semilla.

SHA-256 del formulario humano original: `6d3bd678b8ce16a68cf6594c0e72e735a34a4dabc2807b62f4c8bb5c62807b89`. Propuestas originales: `498a50b77a5671e5e295896fb630819e520405cbe7c68729f0249d9b58dc53e4`.

El extractor inicial recuperaba el 33.2% de los objetivos ponderados de entrenamiento y el 38.8% de validación. El nuevo registro se auditó exclusivamente con esos 1,500 comentarios; sus 500 originales de prueba se retiraron sin evaluación y solo después del congelamiento pueden aportar revisiones a desarrollo. El registro v2 tiene 124 referencias, incluidas identidades literales `unknown`; no significa que todos sus actores estén clasificados políticamente. Fuentes y criterios: [registro de actores](referencias/registro-actores-v2.md).

| Desarrollo original | Precisión de extracción | Recall de extracción |
|---|---:|---:|
| Entrenamiento | 96.63% | 84.94% |
| Validación | 95.53% | 88.47% |

Son diagnósticos usados para desarrollar el extractor, no una evaluación independiente ni métricas del clasificador afectivo. No se bajaron los mínimos 0.90/0.80.

## Muestra derivada y revisión completada

La nueva muestra tiene **2,000 comentarios: 1,200 entrenamiento, 300 validación, 500 prueba; 1,600 principales y 400 respuestas**. Reutiliza copias verificadas de los corpus principal y panel, sin nueva recolección.

- **1,349 decisiones humanas compatibles heredadas**; su forma original, propuesta, contexto y transformación de identificador se verifican contra una copia íntegra del origen.
- **651 revisiones nuevas completadas: 641 propuestas aceptadas y 10 corregidas**. Incluyen 502 comentarios nuevos y 149 anteriormente revisados: 121 necesitaban comprobar identidad explícita y 28 tenían candidatos adicionales. Aceptación no equivale a exactitud ni acuerdo entre humanos.
- El agente leyó los 651 textos en siete lotes. Los scripts únicamente compilan sus decisiones explícitas, localizan menciones y validan/importan; no clasifican por reglas de sentimiento ni llaman servicios adicionales.
- `human_review.csv` contiene exclusivamente las 651 confirmaciones nuevas. Las 1,349 herencias están en `inherited_reviews.csv`, con fuentes y hashes en `inheritance_manifest.json`. Nunca se rellenó `review_complete` para representar una herencia.
- Piloto v2: 200 del entrenamiento; los compatibles ya heredados no necesitan repetirse. La revisión completa incluye los pendientes del piloto.

**Decisión de implementación para aprovechar trabajo:** desarrollo se selecciona prioritariamente dentro del marco ya revisado, con partición 80/20 por video y semilla 43; se completan sus cuotas con casos nuevos cuando falta disponibilidad. Sus pesos registran probabilidad original por selección condicional. La prueba usa la partición nueva por video con semilla 43 y excluye todos los videos y textos normalizados de los 2,000 anteriores. Se preservan las probabilidades dentro de sus estratos elegibles; la evaluación describe ese marco, no toda la población de YouTube.

Con la partición anterior solo quedaban 51 respuestas elegibles para prueba. La semilla 43 dejó 123 y permitió seleccionar 100 respuestas y 400 comentarios principales. No se eligió usando etiquetas. Ningún video cruza particiones; las semillas de entrenamiento y de los análisis afectivos conservan sus definiciones.

Artefactos locales ignorados: `data/targeted/targeted_20261115_v2/revision_report.json`, `annotations/pending_review.csv`, `pending_snapshot_manifest.json`, siete archivos de decisiones y siete lotes de propuestas. Las copias de los corpus coinciden con el origen por SHA-256.

Verificación local actual: **77 pruebas correctas**, incluidas protección de la prueba cuando una clase requerida no admite predicciones, integridad de calibración, aislamiento de desarrollo, paquetes sin etiquetas finales y rechazo de importaciones alteradas. Se verificaron los 2,000 comentarios, la procedencia completa y la separación por video. `annotations/proposals_completed_report.json` conserva el estado histórico anterior a la revisión; el cierre está en `annotations/closure_report.json`. El formulario original y las propuestas permanecen intactos; el bloque productivo generado de AGENTS no cambió.

## Cierre de referencia

- Piloto importado: 200 comentarios, 184 heredados y 16 confirmaciones nuevas aceptadas.
- Conjunto completo importado: 2,000 comentarios y **2,148 unidades objetivo**, con política explícita y cero unidades contextuales separadas.
- El usuario aclaró que las cuatro nuevas menciones de «sombrero/sombrerito» y «chancho» son apodos explícitos. Se conservan sus decisiones en el principal, sin ampliar el registro; sus omisiones siguen siendo errores del extractor. Constancia: `annotations/explicit_alias_confirmation.json`.
- Respaldo previo al cierre: `annotations/backups/review_completed_20261115T172137Z/`.
- SHA-256 humano completado: `a7f3bba53a10abc611b2d32064f4056c5d101d39c6fd51b2a6e6e8ec34aeff6b`.
- SHA-256 propuestas: `cd953d78e0c887ccb87aa4ac3be502d9dcaadf0ce566edaa1f073fa89724bd6a`.
- SHA-256 gold: `b95552b630142e64d7b7353069b5d269677d0059c0da182ed92af98c76833191`.
- SHA-256 registro congelado: `e8f4bc6765be730a65541ab6d1ca05a702e9c0b6ecaabb5537aa9a4eb0abe4ff`.

| Desarrollo v2 completo | Precisión de extracción | Recall de extracción |
|---|---:|---:|
| Entrenamiento | 97.50% | 83.49% |
| Validación | 99.71% | 87.93% |

Estos diagnósticos ponderados superan los mínimos 0.90/0.80; no evalúan valencia afectiva ni sustituyen la prueba final.

## Entrenamiento privado completado

El paquete de `kaggle/train/` contiene 1,500 comentarios de referencia y 1,569 pares (1,291 entrenamiento y 278 validación), con integridad comprobada y **sin etiquetas de los 500 de prueba**, formularios humanos ni instantánea de herencia. Se publicó como versión **1, ready**, del dataset privado `josealvacornejo/sa-polarization-targeted-dat`. El kernel privado `josealvacornejo/sa-polarization-targeted-training`, versión 1, terminó **COMPLETE**. El log confirma GPU **Tesla T4**, descarga efectiva del modelo y finalización de las tres semillas.

- Modelo base: `pysentimiento/robertuito-base-uncased`, revisión `20cb399e4b93f270c0cd6b6f533bcb0ada3cb658`, contexto máximo 128 tokens.
- Semillas 42/43/44; épocas seleccionadas por pérdida de validación: 2/4/2. Calibración exclusivamente en validación, temperatura 1.0.
- Checkpoints descargados y 16 archivos verificados por SHA-256. Evidencia: `kaggle/train/training_verified.json` y log descargado.
- SHA-256 del manifiesto de entrenamiento: `bb6823df54799cd9ed4bb3668988160b709f80c555375f2ec958c51cf1bb22fd`.
- La descarga inicial incluía el árbol de trabajo completo de Kaggle; se interrumpió únicamente la transferencia local y se conservó en `kaggle/train/download_interrupted_20261115T192348Z/`. `kaggle-fetch` ahora selecciona solo `targeted_result.tar.gz`; el log se conserva mediante la CLI. No se repitió el entrenamiento ni se borraron datos.

## Bloqueo del modelo anterior previo a la prueba final

| Clase | Umbral de calibración | Estado |
|---|---:|---|
| positiva | 0.65 | habilitada por validación |
| negativa | 1.01 | abstención total |
| neutral, mixta y no evaluable | 1.01 | abstención total |

Un umbral superior a 1 impide toda predicción aceptada de esa clase. Por ello, la configuración anterior no puede cumplir la precisión negativa aceptada ≥0.85 exigida en la evaluación. Esta es una comprobación lógica de la calibración de desarrollo, **no un resultado medido sobre prueba**; no se inventan F1, precisión o cobertura finales.

Se añadió una comprobación antes de preparar el trabajo remoto y antes de abrir la prueba local. Verifica el hash y el criterio de calibración; si positiva o negativa están deshabilitadas, detiene la etapa sin GPU de evaluación, payload final ni marcador de apertura. La ejecución real quedó bloqueada antes de crear `kaggle/evaluate/`; `model/pretest_readiness.json` conserva motivo, umbrales y hashes. **No existe `model/test_opened.json`; los 500 permanecen disponibles para la evaluación independiente futura.**

## Comparación de desarrollo completada

Se diagnosticó el modelo anterior sin reentrenarlo y se completaron los 12 ajustes autorizados de RoBERTuito/BETO, con semillas 42/43/44 para ambos finalistas. La configuración independiente es `config/targeted_training.toml`; datos y plan permanecen congelados. Ambos paquetes remotos excluyeron las etiquetas finales.

| Modelo | Macro-F1 ponderado | Precisión positiva aceptada | Precisión negativa aceptada | Cobertura extremo a extremo |
|---|---:|---:|---:|---:|
| Anterior | 0.5267 | 85.82% | deshabilitada | 12.65% |
| RoBERTuito ajustado | 0.5289 | 85.82% | deshabilitada | 12.65% |
| BETO | 0.6724 | 99.76% | 85.61% | 19.47% |
| Mínimos | 0.7500 | 85% | 85% | 60% |

BETO obtuvo el mayor macro-F1 de esta ronda, pero ningún finalista cumple todos los mínimos. `selection.json` conserva `selected=null`, `fits_completed=12` y `final_test_evaluated=false`. Las precisiones aceptadas corresponden a subconjuntos; estos resultados proceden de validación reutilizada y asistida, no de evaluación independiente. Diagnósticos, curvas, matrices, ejemplos de error y resumen están bajo `experiments/development_20261115_v1/`; `execution_report.json` registra la integridad final.

Siguiente trabajo: analizar los errores y mejorar el aprendizaje usando exclusivamente entrenamiento/validación, conservando los modelos y las revisiones. No modificar alias ni bajar criterios para hacer pasar esta ejecución. Una vez fijado otro modelo que cumpla todos los criterios de desarrollo, podrá usarse la prueba todavía reservada; no hace falta reemplazarla por un fallo que ocurrió antes de evaluarla. Solo superar todos los criterios finales habilita inferencia y análisis. Un fallo después de abrir prueba sí exige otra evaluación independiente para un método revisado.

## Ronda de representación del objetivo

El usuario eligió primero aprovechar las anotaciones actuales. Experimento `development_targetaware_20261115_v1`, configuración `config/targeted_targetaware.toml`: BETO marcado CLS y BETO con máximo de estados de tokens de la mención, seis ajustes como máximo. Procedencia, revisión de BETO e informes anteriores se congelaron por hashes. Se verificaron localmente las 1,569 menciones automáticas: 1,270 pares de entrenamiento caben completos y los 278 de validación también. Ningún span humano se usa como entrada adicional.

Verificación local: 87 pruebas correctas, incluidas pruebas reales torch de guardado/recarga, máscaras, gradientes y predicción individual/por lotes. El payload privado contiene solo 1,500 comentarios de desarrollo, sin etiquetas finales ni pesos anteriores. Dataset versión 4 ready verificada; kernel privado `josealvacornejo/sa-polarization-targeted-training/4` **COMPLETE**. Se descargaron e importaron los resultados y checkpoints; estado y preflight en `kaggle/development_targetaware_20261115_v1/tune/`.

| Conjunto | Macro-F1 ponderado | Cobertura |
|---|---:|---:|
| BETO anterior | **0.6724** | 19.47% |
| BETO marcado CLS | 0.5996 | 21.44% |
| BETO centrado en la mención | 0.6051 | **31.29%** |

El aumento de cobertura viene acompañado de menor macro-F1; **ninguno cumple 0.75/60%**. Ambos nuevos finalistas cumplen las precisiones positiva/negativa aceptadas, pero deshabilitan predicciones neutrales en calibración. Los mismos 278 pares caben completos y la comparación compartida reproduce los resultados. Estas variantes no sustituyen a BETO anterior y no habilitan prueba ni producción.

`experiments/development_targetaware_20261115_v1/selection.json` conserva `selected=null`, seis ajustes y prueba no evaluada. `execution_report.json` verifica 71 archivos exportados, checkpoints, los 110 archivos del experimento padre y conservación de revisiones/registro/manuscrito/bloque generado. `report/comparison.md` y `report/diagnostic_comparison.md` reúnen resultados y diagnóstico. Los 500 finales permanecen reservados; no hubo inferencia de los 805,039 comentarios. Esta ronda concluye sin candidato elegible; no repetir sus entrenamientos ni ampliar automáticamente las anotaciones.

No repetir la prueba GPU privada completada ni operaciones históricas. No reemplazar tablas AP del manuscrito con diagnósticos de extracción o valores sin validar.

## Auditoría de suficiencia de datos completada

El comando local `targeted diagnose-data` terminó con el diagnóstico `data_sufficiency_20261115_v3`. [Protocolo, resultados y límites](diagnostico_datos_dirigido.md). Salida: `outputs/targeted/targeted_20261115_v2/diagnostics/data_sufficiency_20261115_v3/report.md`.

El marco explícito del corpus principal permite como máximo **3,714 usuarios potencialmente comparables (1.69% de los identificados)** con la partición y mínimos actuales, antes de exigir etiquetas fiables. Dentro del desarrollo humano principal hay **cero usuarios que satisfagan ese recuento estructural** con sus comentarios revisados. BETO previo cubre el 22.66% de objetivos evaluables de derecha y 4.60% de izquierda en validación ponderada; las diferencias de soporte y pesos limitan la interpretación.

La siguiente intervención priorizada es dimensionar una comprobación humana por usuario, abordando esa cobertura desigual antes de otro entrenamiento. No se amplió automáticamente ninguna muestra. La auditoría verificó 15 artefactos y 280 archivos protegidos; 99 pruebas locales, una omitida. Los 500 finales siguen reservados, no hubo inferencia ni AP nuevo, y el registro, manuscrito y bloque de resultados productivos permanecen intactos.

## Ampliación auxiliar IA autorizada

El usuario aplazó otra revisión humana y delegó al agente una ampliación de entrenamiento. [Protocolo y comandos](ampliacion_ia_dirigida.md). Experimento `development_ai_augmentation_v1`, configuración `config/targeted_ai_augmentation.toml`. Se anotaron por lectura del agente 2,000 comentarios nuevos: 3,456 pares auxiliares (923 positivos, 1,967 negativos, 499 neutrales, 23 mixtos, 44 no evaluables) y diez pares inciertos excluidos. Ninguna decisión nueva se representa como confirmación humana.

Los 1,200/300/500 humanos permanecen intactos. Se excluyeron de la muestra IA los usuarios, videos y textos previamente muestreados; el paquete privado contiene únicamente entrenamiento y validación. Una receta BETO, tres semillas, peso IA 0.25 relativo a un ejemplo humano de igual clase; frecuencias de clase calculadas solo con humanos. Se conservan los mínimos originales y el registro congelado.

Dataset dirigido privado versión **5 ready** verificada; kernel `josealvacornejo/sa-polarization-targeted-training/5` **COMPLETE**, en Tesla T4. Se descargaron e importaron los resultados y los checkpoints de las tres semillas. Se ajustaron 4,597 pares con contexto completo: 1,270 humanos y 3,327 IA; se excluyeron 150 por longitud (21 humanos y 129 IA). Épocas seleccionadas: 2/2/3. La calibración habilita positivo/negativo/neutral con umbrales 0.70/0.70/0.50; temperatura 1.0.

| Métrica de validación | BETO anterior | BETO ampliado IA |
|---|---:|---:|
| Macro-F1 ponderado | 0.6724 | 0.6636 |
| Macro-F1 sin ponderar | 0.6879 | 0.7316 |
| Precisión positiva aceptada | 99.76% | 85.42% |
| Precisión negativa aceptada | 85.61% | 85.02% |
| Cobertura global | 19.47% | 49.99% |
| Cobertura de objetivos izquierda | 4.60% | 57.03% |
| Cobertura de objetivos derecha | 22.66% | 42.91% |

La ampliación aumenta la cobertura, especialmente de izquierda, pero **no cumple la mejora parcial acordada** porque el macro-F1 ponderado puntual desciende. Su diferencia es −0.0088, IC95% pareado por video [−0.0818, 0.0629]: no demuestra un deterioro concluyente ni una mejora de F1. La diferencia de cobertura global es +30.51 puntos porcentuales, IC95% [18.96, 42.56]; izquierda +52.43 puntos, IC95% [26.61, 75.28]; derecha +20.25 puntos, IC95% [−0.14, 41.23]. Son IC condicionales a modelos/calibración fijos sobre validación reutilizada/asistida, no prueba independiente.

Las precisiones positiva/negativa aceptadas alcanzan el mínimo puntual 0.85, pero el modelo falla macro-F1 ≥0.75 y cobertura ≥60%. `selection.json` conserva `selected=null`, tres ajustes y `final_test_evaluated=false`. No se sustituyó BETO anterior, no se abrió prueba ni se infirió el corpus. Los 500 finales siguen reservados. El aumento de cobertura no valida AP individual ni resuelve la escasez estructural de usuarios comparables.

Informe: `experiments/development_ai_augmentation_v1/report/comparison.md`; diferencias y bootstrap en `report/augmentation_comparison.json`. El importador preserva los informes remotos sellados para evitar que versiones locales de NumPy/matplotlib cambien sus bytes; se restauraron desde el archivo verificado las dos salidas que la primera importación había regenerado. No se repitió ningún ajuste. Integridad y cierre en `execution_report.json`. Pruebas locales: 109 ejecutadas, una omitida. Se conservaron 261 archivos protegidos. Esta ronda queda cerrada; no repetirla ni ampliar automáticamente anotaciones, criterios o trabajos GPU.

## Cohorte por usuario preparada el 2026-11-16

El usuario eligió conservar AP individual como objetivo principal y autorizó continuar con la preparación de la comprobación por usuario. [Diseño, alcance y comandos](cohorte_validacion_usuario.md). Nuevo comando local `targeted design-user-validation`; cohorte `user_validation_20261116_v1`.

Se reproduce el techo estructural sin exclusiones de 3,714 usuarios. Excluir usuarios/videos/textos de los muestreos humanos original/v2 y auxiliar IA reduce el marco separado a **304 usuarios potenciales**. No son 304 usuarios con afinidad o AP confirmadas. La muestra uniforme reproducible de 100 usuarios conserva **1,887 comentarios completos**, incluidos 1,073 sin candidatos políticos explícitos. A: 959 comentarios; B: 928, con videos separados y semilla 42. Selección de usuarios: semilla 57, sin utilizar sentimientos ni resultado afectivo.

Costes anidados: 25 usuarios/505 textos; 50/905; 100/1,887; 200/4,712. Los 100 usuarios son un tamaño operativo para dimensionar, no un cálculo de potencia ni una obligación de revisar. Datos bajo `data/targeted/targeted_20261115_v2/cohorts/user_validation_20261116_v1/`; informe y hashes bajo `outputs/targeted/targeted_20261115_v2/cohorts/user_validation_20261116_v1/`.

Preparación completa, nueve artefactos sellados y 350 archivos protegidos intactos. 116 pruebas ejecutadas, una omitida. No se anotó esta cohorte, no se entrenó, no hubo API remota ni AP productivo. Los 500 finales permanecen reservados. El paso posterior exige fijar protocolo de referencia y separación de desarrollo/comprobación antes de producir etiquetas; las propuestas IA nunca cuentan como confirmación humana. No presentar la elegibilidad estructural como evidencia de polarización.

## Piloto por usuario con propuestas IA preparado

Continuación autorizada el 2026-11-16: protocolo `targeted-user-cohort-assisted-pilot-v1`, sobre los primeros 25 usuarios del orden ya fijado, **505 comentarios completos**. Se leyeron todos los textos y se importaron propuestas IA en cinco lotes, incluidos objetivos omitidos y coincidencias rechazadas. No se alteraron alias ni bloques. Los otros 75 usuarios/1,382 comentarios siguen pendientes; comparten 138 videos con el piloto y no son una prueba independiente automáticamente.

**Cero confirmaciones humanas**: `human_review.csv` conserva sus campos de decisión vacíos. CLI nueva: `cohort-annotation-init`, `cohort-proposals`, `cohort-review`, `cohort-reference-import`. [Protocolo, alcance y comandos](cohorte_validacion_usuario.md). El formulario guarda y reanuda decisiones reales; la importación rechaza cerrar una referencia incompleta. La probabilidad del piloto es 25/304, distinta del 100/304 heredado en la columna de la cohorte completa; no usar esa columna para ponderar un futuro análisis del piloto.

`pilot_proposals.md/json` documentan procedencia, recuentos de propuestas y hashes. Esos recuentos no son resultados de calidad ni polarización. Los nueve artefactos de diseño siguen intactos. De 350 archivos anteriores auditados, 349 permanecen iguales y se registra el cambio autorizado de la CLI. Referencias originales, registro, checkpoints, manuscrito y bloque productivo se conservaron. **122 pruebas locales ejecutadas, una omitida**. No hubo entrenamiento, operaciones remotas, comparación validada del modelo ni AP nueva. Los 500 finales siguen reservados. La comparación por usuario requiere primero cerrar una referencia confirmada y fijar el contraste; las propuestas IA solas no cumplen ese paso.

## Revisiones aplazadas y combinación de modelos completada

El usuario indicó explícitamente aplazar las revisiones y continuar mejorando los resultados. Se conservaron las 505 propuestas con cero decisiones humanas y los otros 75 usuarios sin anotar. [Protocolo y resultados](combinacion_modelos_dirigida.md). Experimento `development_blend_20261116_v1`, configuración `config/targeted_ensemble.toml`, comando local `targeted blend-development`. **Ya terminó: no repetirlo.**

Tres mezclas de probabilidades del BETO anterior y ampliado IA (pesos ampliado 0.25/0.50/0.75), con extremos de control; cero nuevos ajustes de modelos. Mismo coeficiente para todos los actores/bloques, sin características editoriales. Los 278 pares de validación se alinean exactamente y se conservan criterios, registro y denominadores. Además de calibración completa se separó la calibración en cinco folds por video; no constituye prueba independiente porque la validación ya se usó para entrenar/seleccionar los componentes.

La mejor mezcla descriptiva, **50/50**, alcanza macro-F1 ponderado **0.7037** (anterior 0.6724, ampliado 0.6636), F1 sin pesos 0.7320 y cobertura de desarrollo **40.17%** (anterior 19.47%, ampliado 49.99%). Mejora F1 frente a ambos, pero pierde cobertura frente al ampliado. Precisión positiva/negativa calibrando en todo desarrollo: 85.94%/90.39%. Con calibración separada por video: **80.25%/83.26%** y cobertura **36.16%**. No cumple los mínimos; `selected=null`, `best_development_candidate=blend_0.50`, producción deshabilitada. El intervalo pareado de diferencia F1 frente al anterior es [0.0052, 0.0668], condicionado a modelos/calibraciones/selección/folds fijos; no se presenta como mejora independiente.

Informes, calibraciones, especificación de mezcla y procedencia bajo el experimento. Se verificaron 11 entradas y 40 archivos protegidos, incluida la cohorte pendiente; **128 pruebas locales ejecutadas, una omitida**. Modelos canónicos, referencia original, registro, manuscrito y bloque productivo conservados. No hubo API remota ni AP nueva; los 500 finales siguen reservados. Esta ronda deja una mejora de clasificación de desarrollo y un diagnóstico de inestabilidad de calibración; no convierte las propuestas IA pendientes en referencia ni valida AP individual.

## Refinamiento humano final completado

El usuario autorizó implementar el plan y eligió **una receta, tres semillas**. Experimento `development_human_refinement_20261116_v1`, configuración `config/targeted_human_refinement.toml`, protocolo `targeted-human-refinement-v1`. [Receta, comprobaciones y comandos](entrenamiento_validacion_dirigida.md#refinamiento-humano-final-autorizado-el-2026-11-16).

Se continuó desde cada checkpoint ampliado IA correspondiente, sin reiniciar clasificador; fase final exclusivamente humana con dos épocas fijas, tasa 2e-6 y pérdida equilibrada por clase humana. Dataset privado **v6 ready verificado**, kernel privado `josealvacornejo/sa-polarization-targeted-training/6` **COMPLETE**. Se importaron los tres checkpoints y sus informes con hashes; cada semilla entrenó 1,270 pares humanos y excluyó 21 por longitud. Sus historiales registran dos épocas fijas sin pérdida de validación para seleccionar época.

| Indicador | Mezcla 50/50 | Refinado humano |
|---|---:|---:|
| Macro-F1 ponderado | 0.7037 | 0.6806 |
| Macro-F1 sin ponderar | 0.7320 | 0.7102 |
| Cobertura, calibración completa | 40.17% | 39.85% |
| Precisión positiva/negativa, completa | 85.94% / 90.39% | 94.89% / 85.94% |
| Cobertura, calibración separada | 36.16% | 42.37% |
| Precisión positiva/negativa, separada | 80.25% / 83.26% | 78.69% / 82.55% |

No cumple mejora parcial ni mínimos completos; `selected=null`. El refinamiento mejora F1 frente a su padre ampliado (0.6636), pero no frente a la mejor mezcla de desarrollo. La diferencia F1 frente a 50/50 es −0.0231, IC95% [−0.1321, 0.0915]; cobertura separada +6.21 puntos, IC95% [−3.45, 16.56]. Ambos intervalos son condicionales a modelos/calibración/folds fijos y no demuestran una diferencia poblacional concluyente. No usar estos valores como validación independiente ni AP.

`comparison.md`, `selection.json`, `paired_bootstrap.json`, desgloses por grupo y `local_error_comparison.csv` conservan el diagnóstico. Se recuperan 14 errores de 50/50 y aparecen 17 nuevos; 53 pares son errores en los cuatro modelos. `execution_report.json` verifica 53 archivos exportados, 19 archivos de checkpoints y **384 originales sin cambios**, incluida la cohorte pendiente. Pruebas locales: **134 ejecutadas, una omitida**; el kernel completó la comprobación sintética real de recarga y épocas fijas antes de los tres ajustes. Ronda cerrada: no repetir, ampliar búsquedas ni promover estos pesos automáticamente.

Las 505 propuestas siguen con cero confirmaciones y no se usaron; los otros 75 usuarios siguen pendientes y los 500 finales reservados. No se cambió el registro, modelo canónico, manuscrito ni bloque productivo, ni se infirió el corpus o calculó AP. La mejor mezcla descriptiva continúa siendo 50/50, todavía sin cumplir los mínimos.
