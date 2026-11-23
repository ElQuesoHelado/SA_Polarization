# Figuras del manuscrito

El pipeline del enfoque dirigido se edita en `pipeline_actual.tikz`. El artículo
lo incorpora directamente; `pipeline_actual.tex` permite exportarlo por separado:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=/tmp/sa-pipeline docs/figures/pipeline_actual.tex
pdftoppm -singlefile -r 180 -png /tmp/sa-pipeline/pipeline_actual.pdf \
  docs/figures/pipeline_3
```

Ejecutar desde la raíz. `../pipeline_actual.mmd` conserva el mismo flujo semántico.
El entrenamiento usa desarrollo separado, no las etiquetas de las nuevas muestras.
La medición por historiales no depende de las predicciones de los clasificadores.

El icono de YouTube procede del símbolo `video-youtube-red` del mapa SVG servido
por https://brand.youtube/ (consulta: 2026-11-22 UTC). Se conservan sus paths,
colores y viewBox; únicamente se envuelve el símbolo en un SVG autónomo.
`youtube_icon.pdf` es su conversión vectorial mediante `rsvg-convert`.
Guía oficial: https://developers.google.com/youtube/terms/branding-guidelines.
Los demás pictogramas proceden del paquete TeX `fontawesome5` (Font Awesome Free;
iconos CC BY 4.0). Los nombres de las etapas identifican el uso de cada icono.

## Edición en inglés y tamaño de publicación

Los elementos visuales activos se exportan en inglés. El título, el abstract y
el estado del arte del artículo conservan español por instrucción del usuario.
`observational_gap_distribution` y `observational_event_support` son figuras
independientes a ancho de columna, con texto de al menos ocho puntos efectivos.
El antiguo compuesto `observational_gap_support` queda en los informes sellados
y respaldos, fuera de las figuras activas. No recortar ni sobrescribir el informe
sellado para cambiar su idioma.

El renderer `targeted/publication/observational_figures.py` lee los CSV del informe
y genera las figuras en una carpeta de presentación distinta.
`scripts/build_observational_supplement.py` lo utiliza para publicar las figuras
activas y construir el suplemento en inglés. Las ecuaciones, datos de barras,
intervalos y denominadores se conservan. Exportar las figuras principales al
ancho de una columna; la sensibilidad horizontal es para dos columnas/suplemento.
