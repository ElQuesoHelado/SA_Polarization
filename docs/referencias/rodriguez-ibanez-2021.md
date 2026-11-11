# rodriguez-ibanez-2021 — dinámica temporal del sentimiento (España 2019)

**Cita completa:** Rodríguez-Ibáñez, M.; Gimeno-Blanes, F.-J.; Cuenca-Jiménez, P. M.; Soguero-Ruiz, C.; Rojo-Álvarez, J. L. (2021). *Sentiment Analysis of Political Tweets From the 2019 Spanish Elections*. IEEE Access 9, 101847–101862. DOI [10.1109/ACCESS.2021.3097492](https://doi.org/10.1109/ACCESS.2021.3097492).

**PDF:** `pdfs/11.rodriguez-ibanez-2021.pdf`
**Rol:** `polarizacion-sa` — caracterización estadística y temporal del sentimiento electoral en España.
**Clave en `doc.tex`:** `rodriguez2021sentiment`.
**Verificado:** 2026-11-09 (resumen e introducción).

## Qué aporta

Recopila miles de tuits que mencionan partidos y líderes antes y después de las elecciones generales españolas de 2019. Propone un análisis en dos etapas:

1. **Caracterización estadística** con entropía, información mutua y el *Compounded Aggregated Positivity Index* (CAPI).
2. **Extracción de características no lineales** con autoencoders y embeddings estocásticos (manifold learning).

## Hallazgos citables

- Los índices y las características de manifold describen de forma informativa la dinámica del sentimiento durante el periodo electoral.
- Se observan variaciones medibles de polaridad entre partidos y líderes.
- La dinámica difiere según la posición en el espectro, la presencia regional/nacional y las aspiraciones nacionalistas/globalistas.
- Enfoque metodológico, no una medida de AP individual.

## Límites para nuestro trabajo

- Twitter y elecciones españolas de 2019; no YouTube ni Perú.
- Unidad de análisis agregada por partido/líder, no por usuario.
- El CAPI y las métricas de entropía no son equivalentes a AP/spread.
- Requiere series temporales densas; el corpus de YouTube puede no tener la misma granularidad.

## Uso en el proyecto

- `doc.tex` §Estado del Arte: antecedente de análisis temporal del sentimiento en elecciones y de métricas estadísticas.
- Referencia para discutir dinámica temporal, no para comparar magnitudes con AP.
