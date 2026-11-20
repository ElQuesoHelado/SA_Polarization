# Entrenamiento y validación de desarrollo

Estudio: `targeted_20261115_v2`, configuración `config/targeted_v2.toml`. Experimento autorizado: `development_20261115_v1`, configuración independiente `config/targeted_training.toml`. Reutiliza los 1,200 comentarios de entrenamiento y 300 de validación; **los 500 finales quedan reservados**. La referencia asistida por IA y confirmada por un humano tiene las limitaciones documentadas en el protocolo de anotación.

El modelo anterior permanece en `model/`. El experimento escribe bajo `experiments/<experiment_id>/`, con procedencia, plan congelado, hashes, diagnóstico de referencia, ensayos y dos finalistas. El estado de preparación/publicación/ejecución está separado en `kaggle/<experiment_id>/<task>/job_manifest.json`. Cada nuevo trabajo fija también la versión del kernel para descargar su propia salida.

## Diagnóstico sin reentrenar el modelo anterior

`targeted validate` ejecuta en GPU los checkpoints ya existentes sobre los pares de validación. Genera predicciones, probabilidades por clase y semilla, longitudes tokenizadas, motivos de abstención, matriz de confusión ponderada/sin ponderar y curvas de precisión/cobertura de pares. Los diagnósticos distinguen soporte insuficiente de precisión insuficiente para los umbrales predefinidos. La cobertura extremo a extremo del informe incluye objetivos omitidos y contexto incompleto; la cobertura de pares de las curvas es condicional al extractor.

## Búsqueda congelada

- RoBERTuito: revisión `20cb399e4b93f270c0cd6b6f533bcb0ada3cb658`, máximo 128 tokens.
- BETO uncased: revisión `d1c9c4565c9d6731e57ed7f027b802697bad861e`, máximo 512 tokens. Fuente: [ficha técnica y límites](referencias/beto-modelo.md).
- Cuadrícula por modelo: tasas `1e-5`/`2e-5` y pérdidas `class_balanced`/`sampling_weighted`; ocho ensayos iniciales con semilla 42.
- Se elige una configuración por modelo y se completan semillas 43/44: **12 ajustes como máximo**. El checkpoint de semilla 42 elegido se reutiliza; no se repite el entrenamiento anterior.
- AdamW, regularización 0.01, recorte de gradiente 1, hasta ocho épocas, parada tras dos sin mejorar pérdida ponderada de validación. Lote efectivo 16: físico 16 para RoBERTuito y 4 con acumulación para BETO. La acumulación tiene una comprobación numérica en el entorno torch antes de entrenar.
- Pesos de pérdida normalizados por su media sobre los ejemplos entrenables. La variante por clase usa frecuencias de esos ejemplos; la variante por muestreo usa únicamente sus probabilidades de inclusión. Los pesos originales de evaluación se conservan.

La entrada sigue siendo objetivo–comentario. Se mantienen las cinco etiquetas y la abstención por contexto incompleto, sin modificar registro, alias, grupos, decisiones humanas ni particiones. La longitud admisible se obtiene de la arquitectura: el desplazamiento de posiciones de RoBERTa no se aplica a BERT.

## Selección y límites

La ordenación prioriza cumplir todos los criterios de desarrollo; después, mayor macro-F1 ponderado, mayor cobertura, menor pérdida ponderada y el identificador estable. Los criterios mantienen sus mínimos originales: extracción 0.90/0.80, macro-F1 0.75, precisiones positiva/negativa aceptadas 0.85 y cobertura extremo a extremo 0.60. La calibración conserva temperaturas, umbrales y mínimo de diez casos. Los dos conjuntos finales promedian probabilidades de tres semillas y vuelven a calibrarse con validación.

`selection.json` registra un candidato `ready_for_reserved_test` únicamente si cumple todos los criterios; esto **no es una evaluación final superada**. Si ninguno cumple, se conserva el bloqueo. `common_complete_context.json` compara ambos modelos sobre exactamente los pares con contexto completo compartidos. Los informes son de desarrollo y selección sobre validación reutilizada, no estimaciones independientes de generalización.

Esta ronda termina con el diagnóstico y la comparación. No abre prueba ni ejecuta inferencia de producción, análisis AP o actualización del bloque de resultados productivos.

## Diagnóstico recuperado del modelo anterior

La tarea `validate` terminó en el kernel privado, versión 2, usando dataset versión 2 ready. Los resultados importados abarcan los 300 comentarios de validación y 278 pares extraídos. No se reentrenaron esos pesos.

| Indicador de desarrollo ponderado | Modelo anterior | Mínimo |
|---|---:|---:|
| Macro-F1 positiva/negativa/neutral | 0.5267 | 0.75 |
| Cobertura extremo a extremo | 12.65% | 60% |
| Precisión de extracción | 99.71% | 90% |
| Recall de extracción | 87.93% | 80% |

El diagnóstico marca precisión insuficiente para negativos entre los umbrales con soporte mínimo. Con confianza ≥0.85 hay ocho pares negativos y precisión ponderada 97.01%, pero no alcanzan los diez requeridos; los umbrales con al menos diez no alcanzan precisión 0.85. Hay 14 pares con contexto incompleto. Estos datos son de desarrollo reutilizado/asistido y no determinan por sí solos la causa del fallo ni el rendimiento de BETO.

## Resultado de la comparación

La comparación `tune` terminó en el kernel privado versión 3, con dataset versión 3 ready. Se completaron **12 ajustes**; el log confirma Tesla T4 y la comprobación numérica de acumulación. Los informes y checkpoints se descargaron, verificaron e importaron; corresponden al mismo plan y fuente congelados. La suite local terminó con **77 pruebas correctas**.

| Modelo / conjunto de tres semillas | Macro-F1 ponderado | Precisión positiva aceptada | Precisión negativa aceptada | Cobertura extremo a extremo |
|---|---:|---:|---:|---:|
| Anterior | 0.5267 | 85.82% | deshabilitada | 12.65% |
| RoBERTuito ajustado | 0.5289 | 85.82% | deshabilitada | 12.65% |
| BETO | 0.6724 | 99.76% | 85.61% | 19.47% |
| Mínimos establecidos | 0.7500 | 85% | 85% | 60% |

**Ningún finalista queda preparado para la prueba reservada.** BETO obtuvo el mayor macro-F1 de desarrollo y admite negativos con la precisión exigida, pero no cumple macro-F1 ni cobertura. Su precisión positiva alta corresponde únicamente al subconjunto aceptado; no representa exactitud global. No se modificaron criterios, etiquetas ni registro para hacer pasar un modelo.

Configuraciones elegidas por modelo: RoBERTuito `2e-5/class_balanced` y BETO `1e-5/class_balanced`. Ambas combinan semillas 42/43/44. BETO utiliza umbrales positivo 0.90, negativo 0.80 y neutral 0.55; mixtos y no evaluables quedan deshabilitados. Hay 14 pares de validación con contexto incompleto en RoBERTuito y cero en BETO. El resultado no atribuye causalmente toda diferencia al contexto o a la arquitectura; se conserva una sensibilidad sobre pares compartidos con contexto completo.

Los F1 de BETO por clase son 0.6597 positivo, 0.7532 negativo y 0.6043 neutral. Esto identifica componentes pendientes de clasificación, además de la abstención, sin puntuar los 500 finales. Sobre los 264 pares compartidos con contexto completo, el macro-F1 es 0.5463 para RoBERTuito y 0.6738 para BETO; esta sensibilidad tampoco es evaluación independiente.

Los informes detallados de los ocho ensayos, ambos finalistas, curvas, matrices y pesos se conservan bajo el experimento; el resumen local está en `report/comparison.md`, `comparison.csv` y `comparison.png`. Los archivos `report/*_error_examples.csv` reúnen errores de validación ordenados por peso para su inspección; no modifican las decisiones humanas. `selection.json` mantiene `selected=null` y `final_test_evaluated=false`. `execution_report.json` deja constancia de importación, hashes, separación y conservación de la prueba, revisiones y resultados productivos.

El siguiente trabajo debe partir del análisis de errores de desarrollo y mantener los criterios y la prueba final reservada. Esta comparación no habilita inferencia de los 805,039 comentarios ni resultados de polarización afectiva.

## Ronda de representación del objetivo

Experimento autorizado `development_targetaware_20261115_v1`, configuración `config/targeted_targetaware.toml`, protocolo `targeted-target-aware-v1`. Usa las anotaciones actuales; no solicita nuevas revisiones ni modifica alias. Prepara `tune` directamente, reutilizando informes de `development_20261115_v1` vinculados por hashes. No vuelve a entrenar ni validar los modelos anteriores. El paquete conserva solo los 1,500 comentarios de desarrollo y los informes de referencia.

Ambas variantes mantienen el nombre canónico como primera secuencia y el comentario como segunda. Se insertan IDs especiales `[TGT]` y `[/TGT]` alrededor de la primera mención encontrada por el extractor congelado, usando sus offsets automáticos. La máscara selecciona únicamente los tokens de esa mención, no el nombre de la primera secuencia, ni posiciones humanas, ni otros actores. El texto original se conserva. Marcadores literales dentro del comentario no pueden cambiar la máscara.

- `beto_marked_cls`: clasificación global CLS habitual, con la mención marcada.
- `beto_target_max`: máximo por dimensión de los estados finales de los tokens de la mención, sin marcadores; dropout 0.1 y capa lineal de cinco etiquetas.

Fuente y diferencias respecto del artículo: [Mutlu y Özgür (2022)](referencias/mutlu-ozgur-2022.md). La adaptación no garantiza una mejora. BETO conserva su SHA anterior; se añaden dos tokens al vocabulario, con inicialización aleatoria controlada por semilla. Tokenizador, configuración y manifiesto guardan la representación para recargar el clasificador correcto, sin ejecutar código remoto de terceros.

Dos variantes × semillas 42/43/44 = **seis ajustes como máximo**. Tasa 1e-5 y pérdida por clase inversa a la raíz de su frecuencia entrenable, normalizada por su media. Se conservan AdamW, regularización 0.01, clip 1, batch efectivo 16/físico 4, hasta ocho épocas y paciencia 2 por pérdida ponderada de validación. Cada semilla parte del mismo modelo base; no usa pesos ajustados anteriores. Los marcadores cuentan en el máximo 512 y la comprobación de contexto completo sigue siendo obligatoria.

Antes de entrenar, el entorno torch comprueba acumulación, guardado/recarga, máscaras, predicciones individuales/por lotes y gradientes con un BERT pequeño sintético sin descargas. Se rechaza repetir una ronda iniciada. El kernel trabaja en `/tmp` y exporta únicamente el archivo de resultados a la carpeta de salidas de Kaggle, evitando publicar copias redundantes del árbol de trabajo.

La comparación incluye BETO anterior, matrices/curvas, métricas por clase/bloque, comentarios con uno/varios objetivos, neutralidad, contexto completo compartido y descomposición de cobertura. Criterios y calibración permanecen iguales. Los resultados son de desarrollo reutilizado/asistido; la ronda termina con informes/checkpoints verificados. No abre prueba ni produce inferencia del corpus, aunque algún candidato cumpla los mínimos.

```bash
.venv/bin/sa-polarization targeted kaggle-prepare --config config/targeted_v2.toml --run-id targeted_20261115_v2 --task tune --experiment-id development_targetaware_20261115_v1 --training-config config/targeted_targetaware.toml
```

Después, `kaggle-submit`, `kaggle-start`, `kaggle-status` y `kaggle-fetch` con los mismos estudio, configuración, tarea y experimento. Esperar la versión exacta ready antes de iniciar; mantener dataset/kernel privados. No repetir los trabajos completados de la comparación anterior.

## Resultado de la ronda de representación del objetivo

El kernel privado versión **4 terminó COMPLETE**, montando la versión 4 ready del dataset. Se completaron los **seis ajustes**, con Tesla T4, acumulación y comprobaciones de modelos marcados verificadas. El archivo de resultados y los checkpoints se descargaron e importaron con hashes; `execution_report.json` registra la integridad del cierre y las 87 pruebas locales correctas.

| Conjunto de tres semillas | Macro-F1 ponderado | Precisión positiva aceptada | Precisión negativa aceptada | Cobertura extremo a extremo |
|---|---:|---:|---:|---:|
| BETO anterior | **0.6724** | 99.76% | 85.61% | 19.47% |
| BETO marcado CLS | 0.5996 | 85.74% | 87.38% | 21.44% |
| BETO centrado en la mención | 0.6051 | 93.43% | 87.36% | **31.29%** |
| Mínimos | 0.7500 | 85% | 85% | 60% |

**Ningún candidato cumple todos los criterios.** La variante centrada en la mención aumenta cobertura 11.82 puntos porcentuales, pero reduce macro-F1 en 0.0673 respecto de BETO anterior. La variante CLS marcada también reduce macro-F1. Estos resultados no justifican reemplazar el BETO anterior bajo este régimen; tampoco demuestran que toda arquitectura dirigida sea ineficaz. La hipótesis de que estos cambios bastarían con la muestra actual no queda respaldada como mejora global.

Ambas variantes entrenaron con los mismos 1,270 pares completos y las mismas frecuencias por clase que BETO anterior. Los 278 pares de validación caben completos en los tres modelos, y la sensibilidad sobre contexto compartido reproduce las mismas puntuaciones: la diferencia no procede de evaluar subconjuntos distintos. Las épocas elegidas fueron 3/2/3 en ambas variantes.

La neutralidad sigue siendo problemática: BETO anterior acierta 20 de 40 pares neutrales; CLS marcado, 16; máximo de mención, 17. Sus F1 neutrales ponderados son 0.6043, 0.3991 y 0.4644 respectivamente. Las dos variantes nuevas deshabilitan predicciones de clase neutral por calibración; eso no equivale a reconocer y excluir automáticamente todos los casos verdaderamente neutrales. El máximo de mención usa temperatura 0.75, umbrales positivo 0.90 y negativo 0.70; CLS marcado usa temperatura 0.75 y umbrales 0.85/0.80. Mixtos y no evaluables permanecen deshabilitados.

En el máximo de mención, la cobertura se descompone en 12.15% de objetivos omitidos, 56.56% de abstención por confianza y 31.29% aceptados, sin pérdida por longitud. Son porcentajes ponderados de objetivos evaluables, no exactitud ni porcentajes de todos los comentarios del corpus. `report/diagnostic_comparison.md` y `.json` conservan la descomposición y los cortes por uno/varios objetivos; las matrices, curvas y predicciones de validación siguen disponibles por variante.

`selection.json` conserva `selected=null`, `fits_completed=6` y `final_test_evaluated=false`. El cierre verificó los 110 archivos del experimento padre, las anotaciones, registro, checkpoints canónicos y manuscrito, además del bloque productivo generado. Los **500 finales siguen reservados** y no hubo inferencia del corpus ni análisis AP. Cualquier ampliación de datos o siguiente búsqueda constituye otra ronda; no repetir automáticamente estos seis ajustes ni bajar los mínimos.

## Operación

Preparar el diagnóstico localmente; la publicación y ejecución son comandos separados:

```bash
.venv/bin/sa-polarization targeted kaggle-prepare --config config/targeted_v2.toml --run-id targeted_20261115_v2 --task validate --experiment-id development_20261115_v1
.venv/bin/sa-polarization targeted kaggle-submit --config config/targeted_v2.toml --run-id targeted_20261115_v2 --task validate --experiment-id development_20261115_v1
```

Esperar la versión exacta disponible; luego `kaggle-start`, `kaggle-status` y `kaggle-fetch` con los mismos argumentos. Tras importar el diagnóstico, repetir la secuencia usando `--task tune`. Mantener recursos privados, verificar GPU/Internet efectivos y descargar únicamente el archivo de resultados. Las carpetas existentes no se sobrescriben; los checkpoints del estudio anterior permanecen intactos. El archivo de resultados exporta registros/predicciones de todos los ensayos y pesos completos de los finalistas, sin duplicar los pesos intermedios de los ocho ensayos.

## Refinamiento humano final autorizado el 2026-11-16

El usuario eligió una receta con tres semillas, manteniendo aplazadas las revisiones. Experimento `development_human_refinement_20261116_v1`, configuración `config/targeted_human_refinement.toml`, protocolo `targeted-human-refinement-v1`. Se inicia desde los checkpoints 42/43/44 de `development_ai_augmentation_v1`, conservando encoder y clasificador aprendidos. Solo la fase final usa exclusivamente anotaciones humanas; su historia de entrenamiento sigue incluyendo las etiquetas auxiliares anteriores.

La hipótesis es recuperar ajuste a la referencia confirmada tras aprender con datos auxiliares. [Jiang et al. (2021), §3.3](referencias/jiang-2021.md) es un antecedente de esa idea, no de los parámetros elegidos ni de resultados en sentimiento dirigido. No se implementa NEEDLE completo. La referencia local conserva su limitación de asistencia IA y un único humano.

- Datos: 1,200 comentarios humanos de entrenamiento y 300 de validación ya cerrados; 1,291 pares de entrenamiento antes de excluir longitudes y 278 de validación. Cinco etiquetas y representación comentario–objetivo originales. Las propuestas del piloto y las etiquetas auxiliares no entran en esta fase ni en su evaluación.
- Una receta: tres semillas, dos épocas fijas, tasa 2e-6, AdamW nuevo, regularización 0.01, clip 1, lote efectivo 16/físico 4. Todos los parámetros se actualizan. La pérdida usa inversa de raíz de frecuencia de clase solo de humanos con contexto completo, normalizada a media uno.
- No se consulta validación entre épocas ni se aplica parada temprana: se conserva la segunda época. Las predicciones de validación se calculan después de cerrar el entrenamiento de cada semilla. Se promedian las tres distribuciones.
- Se conservan 512 tokens, exclusión de contexto incompleto y calibración existente. Se añade la misma comprobación de calibración separada en cinco folds por video, semilla 57, que en la ronda de mezcla. Esto no revierte la selección previa de los checkpoints padres sobre esa validación.
- Controles: resultados congelados del BETO anterior, ampliado y mezcla 50/50, sin volver a entrenarlos o buscar mezclas nuevas. Alineación de los 278 pares y cobertura extremo a extremo, incluidas omisiones; reportes por bloque, valencia y motivo de abstención.
- Mejora parcial: F1 ponderado estrictamente mayor al valor exacto de 50/50, ambas coberturas no inferiores y precisiones positiva/negativa con calibración separada ≥85%. Elegibilidad requiere todos los criterios originales tanto en calibración completa como separada. Si no se cumplen, `selected=null`; no ampliar la ronda automáticamente.

El entorno GPU ejecuta antes una prueba sintética pequeña sin descargas: recarga exacta del clasificador, dos épocas y una sola predicción de validación al final, conservación del checkpoint de entrada. Esa comprobación no cuenta como uno de los tres ajustes científicos. Se mantienen la comprobación de acumulación y semillas deterministas.

Preparación/importación verifican referencia, registro, checkpoints iniciales, controles y criterios por hashes. El payload contiene únicamente desarrollo y los pesos iniciales necesarios; no publica los 500 finales, el corpus ni las propuestas pendientes. Los pesos iniciales no se vuelven a descargar en el archivo de resultados. Los informes remotos sellados se importan sin regenerarlos con otras versiones locales de bibliotecas.

```bash
.venv/bin/sa-polarization targeted kaggle-prepare \
  --config config/targeted_v2.toml --run-id targeted_20261115_v2 \
  --task tune --experiment-id development_human_refinement_20261116_v1 \
  --training-config config/targeted_human_refinement.toml
```

Después se usa la secuencia privada `kaggle-submit`, `kaggle-start`, `kaggle-status`, `kaggle-fetch` con esa misma tarea/experimento. La preparación ya se ejecutó: no sobrescribirla ni repetir trabajos iniciados. El seguimiento de versión y resultados está en el estado del estudio. La ronda termina en desarrollo incluso si un candidato resulta elegible: no abre prueba ni infiere el corpus ni calcula AP. Los intervalos pareados por video conservan 2,000 remuestreos y son condicionales a modelos, calibración y folds fijos; no incluyen selección ni error de etiquetas.

## Resultado del refinamiento humano final

La ronda concluyó: dataset dirigido privado v6 ready confirmado y kernel privado v6 **COMPLETE**. Se completaron exactamente las semillas 42/43/44, cada una desde su checkpoint ampliado correspondiente, con dos épocas fijas. La fase final utilizó **1,270 pares humanos** con contexto completo; se excluyeron 21 por longitud. No se añadieron etiquetas ni se usaron propuestas pendientes. La comprobación sintética en GPU se ejecutó antes de los ajustes y verificó recarga del clasificador, conservación de entrada y una única predicción de validación al finalizar las dos épocas.

| Modelo | F1 ponderado | Cobertura completa | Cobertura separada | P+ separada | P− separada |
|---|---:|---:|---:|---:|---:|
| BETO anterior | 0.6724 | 19.47% | 23.58% | 81.02% | 73.04% |
| BETO ampliado IA | 0.6636 | 49.99% | 45.30% | 78.86% | 80.84% |
| Mezcla 50/50 | 0.7037 | 40.17% | 36.16% | 80.25% | 83.26% |
| Refinado humano | 0.6806 | 39.85% | 42.37% | 78.69% | 82.55% |

El nuevo F1 sin ponderar es 0.7102. Con calibración completa admite positivos/negativos con precisiones 94.89%/85.94%, pero no alcanza F1 0.75 ni cobertura 60%; la calibración separada tampoco mantiene precisión 85%. **No cumple la mejora parcial fijada ni resulta elegible.** El descenso puntual de F1 frente a 50/50 tiene diferencia −0.0231 e IC95% [−0.1321, 0.0915]; no permite afirmar deterioro poblacional concluyente. La ganancia puntual de cobertura separada es +6.21 puntos, IC95% [−3.45, 16.56]. Ambos IC omiten selección, recalibración por remuestreo e incertidumbre de etiquetas.

Los informes remotos permanecen intactos. `local_error_comparison.csv`, añadido tras importarlos, identifica **14 errores recuperados** de 50/50, **17 nuevos** y **53 errores persistentes en los cuatro modelos**. No cambia sus etiquetas ni prueba que una causa concreta explique esas discrepancias.

La auditoría local se ejecuta una sola vez después de importar:

```bash
.venv/bin/python scripts/audit_human_refinement.py
```

**Ya se ejecutó; no repetirla.** `execution_report.json` cierra el experimento con versión exacta, hashes y conservación de 384 originales, 53 archivos exportados y 19 archivos de checkpoints. Pruebas locales: 134 ejecutadas, una omitida por dependencias GPU locales; la comprobación sintética real se completó en Kaggle. Los modelos anteriores, referencia, registro, manuscrito y resultados productivos se conservaron. La ronda termina con `selected=null`, sin abrir los 500 finales ni producir inferencia del corpus o AP. Las revisiones aplazadas siguen pendientes.
