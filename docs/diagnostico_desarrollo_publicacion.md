# Diagnóstico local del desarrollo de publicación

Implementado y ejecutado el 18 de noviembre de 2026 para `ap_publication_20261117_v1`. Examina las predicciones ya guardadas de los doce ajustes; no entrena, selecciona modelos, modifica umbrales, consulta APIs ni evalúa los 500 comentarios reservados. La validación reutilizada/asistida sigue siendo desarrollo, no evaluación independiente.

```bash
.venv/bin/sa-polarization targeted publication diagnose-development
.venv/bin/sa-polarization targeted publication evaluation-preflight
```

El primer comando genera una carpeta sellada `outputs/targeted/ap_publication_20261117_v1/development_diagnostics/` y rechaza sobrescribirla. Ya existe: consultar `report.md`, sin volver a ejecutarlo. Incluye confusiones ponderadas y sin ponderar, soporte por clase, resultados por semilla, estratos por actor/bloque/fuente/tipo, curvas descriptivas con calibración fija e inventario local de errores. Este inventario contiene texto y etiquetas; no se publica automáticamente. Una primera versión se conserva en `development_diagnostics_before_scope_wording_clarification/`; la versión canónica precisa el alcance del panel común, sin nuevos ajustes.

## Hallazgos medidos

Hay 1,148 pares de entrenamiento y 264 de validación en el panel de contexto común. La referencia humana de validación contiene 298 objetivos: el extractor omite 23. De los 278 candidatos extraídos, 14 quedan fuera del panel común. Estos últimos no necesariamente exceden el contexto de cada modelo: la comparación guardada solo puntúa el panel compartido.

| Modelo | Macro-F1 ponderado | Macro-F1 sin ponderar | F1 neutral | Predicciones neutrales antes de abstener |
|---|---:|---:|---:|---:|
| RoBERTuito | 0.6439 | 0.7185 | 0.5472 | 28 |
| BETO | 0.4768 | 0.5661 | 0.0982 | 8 |
| BERTIN | 0.4553 | 0.5232 | 0.1208 | 9 |
| XLM-RoBERTa | 0.4278 | 0.4917 | 0.0032 | 1 |

Ningún modelo habilita neutral bajo la regla vigente de precisión ≥0.85 y al menos diez predicciones. En los umbrales descriptivos examinados que conservan ese mínimo, RoBERTuito alcanza como máximo aproximadamente 0.7086 de precisión neutral ponderada. Los otros modelos no alcanzan diez neutrales con confianza ≥0.50 tras la calibración guardada. No se seleccionan nuevos umbrales a partir de estas curvas.

Los diez pares con mayor peso concentran el 20.14% del peso de validación. El tamaño efectivo debido solo a pesos es 87.19; no incorpora dependencia por usuario, video ni canal. La discrepancia entre métricas ponderadas y sin ponderar y la variación entre semillas se documentan, sin atribuirles causas lingüísticas o prometer mejoras con otro entrenamiento.

`coverage_breakdown.csv` distingue omisiones, candidatos fuera del panel común, abstenciones por confianza, clases auxiliares aceptadas y valencias aceptadas. Su denominador son los 291 objetivos humanos evaluables, pero solo hay puntuaciones en el panel común. No representa la cobertura de una inferencia completa propia de cada modelo ni la de los ~800,000 comentarios históricos. Las curvas emplean candidatos del panel común y tienen otro denominador explícito.

## Preparación de la evaluación

`evaluation-preflight` es de solo lectura: devuelve JSON y no crea muestras, propuestas, anotaciones, predicciones ni recursos remotos. Comprueba captura/snapshot, sellos, muestras, revisión y cierre de referencia, alcance de predicciones y ausencia de etiquetas en sus entradas. Tras congelar el snapshot, también registra coincidencias de ID/texto entre cohorte y benchmark y la exposición documentada por identidad del revisor/fecha. La falta de evidencia registrada no demuestra ausencia de lectura previa.

En esta ejecución devuelve `waiting_snapshot`: 1,176 videos completos, uno parcial y 10,103 sin iniciar. Entrenamiento importado; benchmark, cohorte, predicciones y referencia nueva todavía pendientes. El siguiente comando operativo sigue siendo `targeted publication collect`, cuando el presupuesto diario permita continuar. No se ejecutó durante este diagnóstico.

Una vez completada la captura, congelar el snapshot y preparar las muestras según [el protocolo](estudio_publicable.md). La comprobación informa requisitos; no los completa automáticamente. La evaluación provisional necesita propuestas completas, y la final necesita decisiones humanas completas para benchmark y cohorte incluida, además de predicciones íntegras. No habilita producción ni abre la prueba histórica.
