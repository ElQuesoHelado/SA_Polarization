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
