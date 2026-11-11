# nuestro-paper — `docs/doc.tex` (documento en preparación)

**Documento:** `docs/doc.tex`
**Título:** *Análisis de sentimientos y favorabilidad política en comentarios de Youtube durante las elecciones presidenciales peruanas de 2026*.
**Autor:** Jose Alva Cornejo (Universidad Nacional de San Agustín de Arequipa). Plantilla IJACSA/IEEEtran.
**Rol:** `paper-propio` — contexto del trabajo que consume el pipeline.
**Verificado:** 2026-11-10 contra `docs/doc.tex`.

## Estado y fuente de datos canónica

- **Vigente:** Documento completamente unificado sobre el corpus de **YouTube: 827,287 comentarios** de 11,786 videos de 40 canales consolidados (30 monitoreados agrupados en izquierda, derecha y neutral local, más el pool neutral canónico), elecciones peruanas de 2026. Todas las secciones (§Resumen, §Introducción, §Método, §Resultados y §Conclusiones) están alineadas con esta corrida.
- **TikTok descartado:** Ya no forma parte del trabajo ni de ninguna sección del documento; la única fuente es YouTube.

## Corpus y método

- **Datos:** `data/processed/comentarios_consolidado.csv` → inferencia Kaggle → `outputs/datos_clasificados.csv` (827,287 filas).
- **Modelo:** `pyupeu/robertuito-peruvian-sentiment`; salida `(S_i, P_i)` con `S_i ∈ {negative, neutral, positive}` y confianza `P_i ∈ [0,1]`.
- **Favorabilidad neta (NSS):** `F_neta = (N_pos − N_neg) / N ∈ [−1, 1]`.
- **Favorabilidad ponderada:** `F_pond = (1/N) Σ s_i P_i`, con `s_i ∈ {1, 0, −1}`.
- **Ingroup:** `argmax_j Pos_i,j` sobre grupos partidarios (izquierda/derecha); sin positivos o empate → `Undetermined`.
- **AP_In:** `Pos_i,j − Neg_i,j` con `j = ingroup`.
- **AP_Out:** `Σ_{j'≠j} (Pos_i,j' − Neg_i,j')` (incluye tanto al partido opuesto como al pool neutral).
- **AP:** `AP_In − AP_Out`.
- **spread:** `sqrt( Σ_j (Pos_i,j − Neg_i,j)² / n_i )`, **adaptado de Wagner (2021)**. En el código local `n_i` cuenta comentarios con valencia determinada (positive/negative); el paper de referencia usa el total de interacciones.
- **Niveles:** bajo/medio/alto por media ± DE de cada indicador, con el criterio de Martínez-España. Umbral de spread alto en la corrida actual: **2.052**.

## Resultados exactos (corrida documentada en `AGENTS.md`)

**Tabla 1 — sentimiento y favorabilidad por grupo:**

| party | comentarios | % neg | % neu | % pos | favorabilidad neta | ponderada norm. |
|---|---:|---:|---:|---:|---:|---:|
| derecha | 210,278 | 45.46 | 37.33 | 17.21 | −0.282 | −0.238 |
| izquierda | 293,109 | 52.70 | 29.90 | 17.39 | −0.353 | −0.296 |
| neutral | 323,900 | 62.24 | 28.23 | 9.54 | −0.527 | −0.436 |

**Tabla 2 — métricas individuales:**

| métrica | derecha | izquierda |
|---|---:|---:|
| usuarios | 19,861 | 23,489 |
| AP_In medio | 0.377 | −1.065 |
| AP_Out medio | −1.200 | −0.956 |
| AP medio | 1.577 | −0.109 |
| spread medio | 1.150 | 1.189 |
| spread alto (%) | 8.21 | 10.53 |

- Usuarios en el análisis: **179,355**; `Undetermined`: **136,005 (75.83%)**; determinados: **43,350**.
- Globales: AP medio **0.664** (DE 6.976); spread medio **1.171** (DE 0.882).
- Comparación con Martínez-España (Tabla 4 y Tablas 5–6): AP_In paper 8.662/6.813; AP_Out −1.223/−1.160; AP 9.885/7.972; spread 1.874/1.748; spread alto 15.89%/13.35%. **No son comparables** por plataforma, grupos, denominadores y umbrales.

## Figuras

- `docs/figures/pipeline_3.png` — esquema del pipeline.
- `docs/figures/plot_ap_in.png`, `plot_ap_out.png`, `plot_ap_final.png`, `plot_spread.png` — distribuciones individuales.

## Limitaciones declaradas en el paper

- El modelo estima valencia general, no postura hacia un objetivo político.
- AP y spread son conteos sensibles al volumen de actividad.
- El denominador local de spread excluye neutrales y el universo de usuarios excluye a quienes solo comentaron neutral.
- No se puede inferir ideología, apoyo al grupo ni polarización de la población peruana.

## Bibliografía

`doc.tex` usa `\bibliographystyle{IEEEtran}` y `\bibliography{IEEEabrv, referencias}`, pero **no existe `referencias.bib` ni `IEEEabrv.bib`** en el repo: la bibliografía no compila. El registro `docs/referencias/referencias.md` es la fuente desde la cual derivar el `.bib` cuando se decida crearlo. Claves citadas y su estado: ver la tabla «Citadas en `doc.tex` sin PDF local» del índice.
