# Abstención, calibración y criterios heurísticos

## Geifman y El-Yaniv (2017)

*Selective Classification for Deep Neural Networks*. Advances in Neural Information Processing Systems 30. Clave: `Geifman2017Selective`.
Fuente primaria: https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html
PDF local: `pdfs/contexto/geifman-selective-2017.pdf`.

Sustenta el marco de clasificación selectiva: aceptar una parte de las predicciones permite estudiar el intercambio entre error y cobertura. El artículo desarrolla un procedimiento con control probabilístico del riesgo; el pipeline local no implementa ese control ni hereda sus garantías. Se cita el marco general, no una reproducción de su algoritmo.

## Guo et al. (2017)

*On Calibration of Modern Neural Networks*. Proceedings of the 34th International Conference on Machine Learning, PMLR 70:1321–1330. Clave: `Guo2017Calibration`.
Fuente primaria: https://proceedings.mlr.press/v70/guo17a.html
PDF local: `pdfs/contexto/guo-calibration-2017.pdf`.

Sustenta la calibración de probabilidades mediante temperatura. En el pipeline se seleccionó la temperatura dentro de una rejilla fijada utilizando validación. No se afirma que se reprodujera exactamente todo el procedimiento experimental de la publicación ni que calibrar garantizara precisión fuera de muestra.

## Alcance de la justificación numérica

La precisión ponderada mínima 0.85 y el mínimo de diez pares aceptados por clase fueron decisiones heurísticas y discrecionales del estudio, conservadas en sus comparaciones. Sus motivos prácticos fueron priorizar precisión y evitar habilitar clases con muy pocos casos. Ninguna de estas referencias prescribió esos valores. No hubo una derivación de tamaño muestral, una optimización de costes ni un análisis que demostrara que fueran óptimos. Diez contó pares brutos; no equivalió a diez observaciones independientes ni a un tamaño efectivo ajustado por pesos o videos. Cumplir la precisión puntual en validación no constituyó una garantía estadística de alcanzar 85% en datos nuevos.

Estos criterios regularon aceptación y cobertura; el macro-F1 principal se calculó antes de abstención y la medición observacional provino de historiales anotados. No deben justificarse retroactivamente usando la sensibilidad adversa de B, que tuvo otro denominador y otras condiciones.

Procedencia, versiones, fecha de descarga y SHA-256: `threshold-rationale-downloads.json`.
