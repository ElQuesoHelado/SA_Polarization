# calizaya-2026 — contexto peruano (RoBERTuito y jerga peruana)

**Cita completa:** Calizaya-Milla, S. E.; Santos, J.; Huanca Torres, F. A. (2026). *Fine-Tuning Monolingual Pre-Trained BERT Models for Sentiment Analysis in Peruvian Slang Contexts*. Applied Artificial Intelligence 40(1), e2641381. DOI [10.1080/08839514.2026.2641381](https://doi.org/10.1080/08839514.2026.2641381).

**PDF:** `pdfs/05.calizaya-2026.pdf`
**Rol:** `contexto-peru` — justifica el uso de RoBERTuito en español peruano informal.
**Clave en `doc.tex`:** `CalizayaMilla2026`.
**Verificado:** 2026-11-09 (resumen y primeras páginas).

## Qué aporta

Construye un corpus de **11,276 comentarios de redes sociales anotados manualmente**, con preprocesamiento que preserva rasgos de la jerga peruana y expansión de vocabulario con un diccionario de slang. Ajusta modelos monolíticos en español y compara su desempeño.

## Hallazgos citables

- **RoBERTuito: F1 = 0.750**, el mejor del estudio.
- BETO 0.661; BERTuit 0.700; RoBERTa-BNE 0.696.
- Argumenta que la jerga, abreviaturas y ambigüedad limitan el SA en español peruano y que los modelos generales no representan bien esos rasgos.
- Señala que, al momento del estudio, no identificó trabajos peruanos comparables con modelos Transformer monolingües para lenguaje coloquial.

## Límites para nuestro trabajo

- El corpus es de comentarios de redes sociales en general, no de comentarios políticos de YouTube.
- El F1 de 0.750 es de su tarea y anotación; **no transfiere** al pipeline (que usa Robertuito sin fine-tuning específico y etiquetas automáticas).
- No mide polarización ni AP; es evidencia sobre calidad de clasificación en español peruano.

## Uso en el proyecto

- `doc.tex` §Estado del Arte y §Método: respalda la elección de `pyupeu/robertuito-peruvian-sentiment` y la necesidad de considerar jerga peruana.
- Citar el F1 solo como resultado del estudio, no como estimación del desempeño local.
