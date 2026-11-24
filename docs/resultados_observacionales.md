# Estudio observacional: resultados y reproducción

El enfoque vigente mide **polarización afectiva expresada hacia actores políticos** entre usuarios con evidencia suficiente en ambos bloques. La afinidad se identifica en videos A y la valoración se mide en B. Los clasificadores constituyen una rama separada: su desempeño no determina el resultado de los historiales anotados ni autoriza extrapolarlo al conjunto de comentarios completo.

## Ejecución local cerrada

```bash
.venv/bin/sa-polarization targeted publication diagnose-measurement \
  --analysis-id observational_strengthening_20261122_v1 --stage provisional
```

Configuración adicional: `config/targeted_observational.toml`. Informe inmutable:
`outputs/targeted/ap_publication_20261117_v1/observational/observational_strengthening_20261122_v1/`.
El comando verifica entradas protegidas, reproduce exactamente la medición principal y las seis sensibilidades anteriores y sella los diagnósticos. Reejecutarlo verifica y devuelve el informe; no repite el remuestreo ni sobrescribe resultados. Un cambio de decisiones exige una nueva identidad de análisis y una edición metodológicamente explícita, nunca reemplazar silenciosamente el informe. Esta implementación admite únicamente la etapa provisional; no habilita producción ni cierre humano.

La familia complementaria se definió después de conocer el resultado principal. Conserva 2,000 remuestreos cruzados de usuarios y canales, semilla 42 y mínimo 80% de réplicas válidas. Las variantes condicionadas a los comparables utilizan los 122 originales; la rejilla de umbrales utiliza los 300 examinados para permitir incorporaciones al relajar B. No se imputan etiquetas de comentarios omitidos. Las 200 divisiones de videos B usan semilla 57 y no constituyen intervalos de confianza poblacionales.

## Lectura de los resultados

| Evidencia | Resultado | Interpretación y límite |
|---|---|---|
| Selección | 4,443 candidatos → 300 examinados → 126 con afinidad → 122 comparables | Los excluidos no se clasifican como personas sin polarización. Los comparables son más activos en variables observables. |
| Brecha media | 1.4424, IC95% [1.2733, 1.6827] | Valoración diferencial consistente dentro del marco; escala normalizada de −2 a 2, sin niveles universales. |
| Brecha positiva | 120/122, 98.36%, IC95% [91.67%, 100%] | Favoritismo relativo entre comparables; no proporción del electorado polarizado. |
| Apoyo interno y rechazo externo simultáneos | 93/122, 76.23%, IC95% [66.67%, 93.75%] | Distingue el signo de ambos componentes del mero contraste positivo. |
| Mediana / media recortada | 1.6000 / 1.5111 | El promedio positivo no depende de una sola cola o caso extremo. |
| Rejilla fija de umbrales | 12 variantes, 66–123 usuarios, brecha 1.4306–1.5176 | Todos los IC conservan signo positivo; cambia la población retenida. |
| Soporte ≥5 eventos por bloque | 30 usuarios, 1.3954 [1.0908, 1.6829] | Persiste el patrón con mayor soporte individual y menor amplitud de observación. |
| Diferencia derecha−izquierda | −.0526 [−.4624, .3868] | Inconclusa; no demuestra igualdad ni superioridad de un bloque. |
| A frente a B | Cambio .1658 [−.0494, .3290], mismos 113 usuarios | No demuestra inflación estadísticamente clara por reutilizar A. |
| Estabilidad entre mitades de B | Pearson mediana .3667; mediana 63 usuarios por partición | Limita la precisión individual aun cuando el promedio agregado resista sensibilidades. |
| Error adverso en B | Con 160 cambios: brecha mínima .1801; 193 cambios llevan a ≤0 | Cota con afinidad, extracción, usuarios y denominadores fijos; no tasa real de error ni garantía del proceso completo. |
| Referencia mayoritaria | Macro-F1 integral .1524 | Las tres referencias la superan, sin alcanzar cobertura suficiente para automatizar todo el conjunto. |
| Pérdidas de extracción | 55.93% del peso evaluable omitido antes de clasificar | No se resuelven bajando únicamente el umbral de aceptación. |

`report.md` explica cada archivo; las tablas CSV conservan precisión completa. Las figuras no incluyen identificadores. `user_scores.csv`, `user_observables.csv` e `influence.csv` son artefactos locales sensibles: no publicarlos sin una decisión específica de anonimización.

## Revisión editorial bilingüe del 22 de noviembre

El título, el abstract y el estado del arte permanecen en español. El resto del
artículo y el cuerpo del suplemento están en inglés, al igual que todas las tablas,
figuras, captions y algoritmos. El abstract conserva solo la estimación principal
con su intervalo y el tamaño comparable; la interpretación electoral se desarrolla
con evidencia propia y contexto externo claramente separados.

La figura compuesta se sustituyó por distribución de brecha y soporte de eventos
independientes, a tamaño de columna. La tabla robusta explica “10% trimmed mean”
en una nota, sin R10. Los PDFs de esta edición y su respaldo están bajo
`outputs/manuscrito/english_revision_20261122/`. Los informes numéricos sellados
no se regeneraron ni alteraron. Las reglas persistentes están en `AGENTS.md`.

## Documento y figuras

- Fuente activa: `docs/doc_a_modificar.tex`. `docs/doc.tex` permanece histórico.
- Tablas completas, comparación de cinco modelos y diagnósticos adicionales de las tres referencias originales: `docs/observational_supplement.tex`.
- Bibliografía: `docs/references.bib`; nuevas fuentes y PDFs registrados en `docs/referencias/referencias.md`.
- Figuras científicas: `docs/figures/observational_*`; flujo: `pipeline_actual.tikz`, `pipeline_actual.tex` y `docs/pipeline_actual.mmd`.
- PDF principal y complementario vigentes: `outputs/manuscrito/abstract_closing_20261123/`. Las ediciones anteriores se conservan.

El exportador corresponde explícitamente a esta edición narrativa; rechaza otros estudios para no reutilizar explicaciones numéricas desactualizadas:

```bash
MPLCONFIGDIR=/tmp/sa-observational-mpl .venv/bin/python scripts/build_observational_supplement.py \
  --report outputs/targeted/ap_publication_20261117_v1/observational/observational_strengthening_20261122_v1
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=outputs/manuscrito/observacional_20261122/build docs/doc_a_modificar.tex
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=outputs/manuscrito/observacional_20261122/supplement_build docs/observational_supplement.tex
```

## Kaggle y continuación

**Cierre verificado:** entrenamiento `/2` y predicción
`josealvacornejo/sa-polarization-pub-encoders-predict/1` COMPLETE, comparación de
cinco modelos importada y sellada. El controlador terminó; no hay que esperar
otro entrenamiento ni reenviar estos trabajos. RoBERTuito conserva el mayor
macro-F1 integral (.3836); los nuevos modelos no mejoran esa referencia.
La tabla principal presenta macro-F1 e IC95% y el detalle de cobertura se conserva
en el suplemento. Para regenerar esta edición del suplemento, añadir
`--model-report outputs/targeted/ap_publication_20261117_v1/model_experiments/encoder_extension_20261122_v1/benchmark_provisional`
al comando anterior. Los intervalos comunes están sellados separadamente en
`manuscript_statistics/`; no se sobrescribió el informe observacional ni el de
evaluación. Los párrafos operativos siguientes conservan la historia del envío.

El usuario canceló la primera versión en cola. Se confirmó `CANCEL_ACKNOWLEDGED`, ausencia de registros y cuota GPU disponible; el reintento explícito conserva el trabajo anterior bajo `kaggle/train/attempts/0001/`. Versión exacta activa: `josealvacornejo/sa-polarization-pub-encoders-train/2`. No reenviar una versión activa ni publicar otro dataset.

El servicio transitorio `sa-polarization-encoder-extension-20261122.service` espera la versión exacta, importa y verifica checkpoints, prepara predicción diagnóstica privada sin etiquetas de evaluación y compara cinco modelos. La predicción utiliza el código congelado del entrenamiento, verificado contra el manifiesto dentro del archivo publicado; las mejoras locales del análisis no cambian ese código. El servicio no arranca después de reiniciar el equipo ni reintenta errores.

La integración del artículo usa `observational_manuscript_guard.json` y los marcadores `BEGIN/END OBSERVATIONAL MODEL RESULTS`. Verifica hashes de fuentes antes de editar y conserva respaldo. Si el usuario ha editado el documento, deja aviso pendiente; no reemplaza sus cambios. Las tablas complementarias de las tres referencias conservan su alcance aunque después aparezcan resultados de cinco modelos.

## Estado de validación

La revisión editorial posterior unificó tercera persona y pasado en artículo y
suplemento. Se añadieron llamadas a las ocho ecuaciones y etiquetas/referencias
explicativas a las trece tablas del suplemento; las cinco tablas principales
conservaron sus llamadas. Los generadores mantienen estas convenciones. Los
cuerpos numéricos de las 18 tablas, las fórmulas y las coordenadas de los
histogramas quedaron iguales. Los pendientes se describieron con referencia al
momento de preparar la versión; la edición no realizó revisiones humanas.

La base de esta ejecución son propuestas de anotación pendientes de confirmación humana individual. No se simularon confirmaciones ni se abrieron los 500 reservados. Los intervalos describen variación dentro del marco, sin incorporar error de anotación. Las limitaciones y este estado se explican al final del artículo y del material complementario. El informe histórico y el bloque de resultados de producción de `AGENTS.md` permanecen intactos.

## Traducción final y correcciones de revisores

La versión activa quedó completamente en inglés, incluidos título, abstract y
Related Work. Se integraron aclaraciones útiles de `doc_correcciones.tex` sin
modificar ese archivo ni reintroducir elementos metodológicos desactualizados.
Se preservaron resultados, Limitaciones, cifras, fórmulas y citas. El título del
suplemento también se actualizó en su generador. El registro de decisiones,
respaldo y verificación quedaron junto a los PDF vigentes.

## Revisión externa del 23 de noviembre

La versión recibida en `doc_correcciones.tex` se conservó íntegra. Se corrigieron
autoría y afiliación; se compactó A/B manteniendo las ecuaciones; se normalizaron
`Eq.`/`Eqs.` y decimales; y las conclusiones destacaron aportes y evidencia.
Los detalles operativos de lectura y la receta de entrenamiento quedaron en el
suplemento. Se añadió Holm (1979), diferenciando valores p ajustados de IC
percentiles. La bibliografía se compiló con manejo correcto de URLs.

El PDF completo incluyó figuras y referencias. Una copia de comprobación
excluyó únicamente figuras/captions y bibliografía, manteniendo tablas,
algoritmos y ecuaciones, para verificar el máximo de diez páginas. Conteo y
fuentes reproducibles quedaron junto a los PDF. No se recalcularon resultados.

## Migración a IJACSA 2026

La fuente revisada fue `doc_correcciones.tex`; se conservaron su contenido y
sus cambios, con ajustes mínimos de puntuación y pasado. La nueva clase local,
la configuración de compilación y las URLs se validaron con archivos
individuales en una carpeta aislada. La entrega no contiene ZIP.
La [guía de Overleaf](guia_overleaf_ijacsa_2026.md) enumera qué reemplazar/subir.
La advertencia de compatibilidad de `caption` procede de la clase de la plantilla;
los estilos se configuraron explícitamente. No hubo desbordes de columnas ni
referencias indefinidas en la compilación completa.
