# martinez-espana-2024 — fuente principal

**Cita completa:** Martínez-España, R.; Fernández-Pedauye, J.; Giner-Pérez de Lucía, J.; Rojo-Martínez, J. M.; Bakdid-Albane, K.; García-Escribano, J. J. (2024). *Methodology for Measuring Individual Affective Polarization Using Sentiment Analysis in Social Networks*. IEEE Access 12. DOI [10.1109/ACCESS.2024.3431999](https://doi.org/10.1109/ACCESS.2024.3431999).

**PDF:** `pdfs/01.martinez-espana-2024.pdf`
**Rol:** `principal` — base metodológica de AP, AP_In, AP_Out y spread.
**Clave en `doc.tex`:** `polariz`.
**Verificado:** 2026-11-09 (contra el PDF local).

## Qué aporta

Estudio de Twitter durante las elecciones regionales de Murcia (2023). Combina una muestra por palabras clave (más de 29 mil tuits; 50 mil incluyendo hilos) con otra por perfiles políticos (más de 21 mil; alrededor de un millón incluyendo hilos). Etiqueta manualmente 78 entidades y clasifica a los usuarios en cuatro grupos: derecha, izquierda, derecha radical e izquierda radical. A partir del sentimiento de las interacciones define una medida individual de polarización afectiva y una alternativa normalizada (`spread`).

## Definiciones y operacionalización

- **Ingroup:** grupo con más interacciones positivas del usuario (`argmax Pos_i,j`); sin positivos o con empate → `Undetermined`. Reporta 147,534 indeterminados (55 % de la muestra).
- **AP_In = Pos_in − Neg_in.**
- **AP_Out = Σ_{j≠ingroup} (Pos_j − Neg_j).**
- **AP = AP_In − AP_Out.** Conserva conteos; es sensible al volumen de actividad.
- **`spread` = sqrt(Σ_p (Pos_ip − Neg_ip)² / n_i)**, donde `n_i` cuenta las interacciones del usuario (el paper la presenta como alternativa normalizada frente a hiperactividad).

## Hallazgos citables

- **Tablas 1–2 (interacciones promedio por usuario y grupo destino):** la diagonal positiva (ingroup) es la mayor en cada fila: derecha 9.725, izquierda 7.819, derecha radical 6.422, izquierda radical 6.411; desviaciones estándar grandes (hasta 50.953 en derecha). En negativas, el valor intragrupo es el mayor en derecha (1.063), izquierda (1.006) e izquierda radical (2.187); en derecha radical el máximo va hacia izquierda radical (0.893 frente a 0.270 intragrupo). El paper interpreta favoritismo intragrupo con crítica interna.
- **Figura 2:** distribución decreciente de usuarios detectados desde izquierda radical hasta derecha radical; los autores advierten que puede reflejar actividad/detección, no cantidad de simpatizantes.
- **Tabla 3 (AP, niveles bajo/medio/alto):** derecha radical 0.04/93.61/6.35; derecha 0.54/92.92/6.55; izquierda 0.22/94.14/5.64; izquierda radical 1.07/94.09/4.84. Cortes globales aproximados −26 y +26 (media 3.16, DE 23.75).
- **Tabla 4 (medias AP_In):** derecha 8.662, izquierda 6.813, derecha radical 6.151, izquierda radical 4.224. Las medias AP hacia grupos externos son mayormente negativas.
- **Tabla 5 (`spread`, niveles):** bajo = 0; medio > 0 y ≤ 2.68; alto > 2.68 (media global 1.16 + DE 1.52). Derecha radical 1.33/85.62/13.05; derecha 2.69/81.43/15.89; izquierda 1.95/84.70/13.35; izquierda radical 3.62/80.82/15.57.
- **Tabla 6 (`spread`, media y DE):** derecha 1.874 (2.299); izquierda radical 1.763 (1.729); izquierda 1.748 (1.997); derecha radical 1.732 (1.670).
- **Figuras 3–5:** AP/AP_In/AP_Out con colas largas y valores extremos; AP_Out mayormente negativo, con casos positivos.
- **Figura 6:** `spread` no negativo, rango más compacto, con un valor extremo de izquierda.
- **Estadística:** ANOVA significativo y post hoc Bonferroni; derecha difiere de los otros grupos, los otros tres no difieren entre sí. **El texto no reporta F ni valores p.**

## Límites para nuestro trabajo

- **Constructo:** mide interacción dirigida a grupos/partidos en Twitter mediante sentimiento; nuestro corpus son comentarios de YouTube asignados al grupo del canal, no postura dirigida a un objetivo.
- **Grupos:** cuatro familias partidarias españolas; Perú no tiene equivalentes directos de "derecha radical"/"izquierda radical".
- **Denominador de `spread`:** el paper usa el total de interacciones (incluye neutrales); el pipeline local usa solo comentarios positive/negative.
- **`neutral`:** en el pipeline se incluye como grupo externo para AP_Out y `spread`; en el paper los grupos externos son los otros tres partidos.
- **Muestra y plataforma:** Twitter, Murcia 2023, etiquetado manual de 78 entidades; YouTube, Perú 2026, etiquetas automáticas.
- **Comparaciones:** sus cifras no son un benchmark para Perú; usar solo como referencia conceptual y metodológica.

## Uso en el proyecto

- `AGENTS.md` conserva el resumen operativo (fórmulas, tablas, cautelas) para comandos de análisis; esta nota amplía el detalle para `docs/doc.tex` (§Método, §Resultados) y para responder consultas metodológicas.
- El bloque `GENERATED RESULTS COMPARISON` compara contra este paper con las salvedades anteriores.
