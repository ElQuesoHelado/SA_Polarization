# Biblioteca de PDFs

Los archivos se numeran según la importancia del trabajo en `docs/doc.tex`: núcleo metodológico, contexto peruano, antecedentes de polarización/análisis de sentimiento y, finalmente, surveys y contexto general. El número no corresponde al orden de cita ni al orden alfabético.

El índice canónico, con la clave `.bib`, el número IEEE y el estado de cada trabajo, está en [`docs/referencias/referencias.md`](../docs/referencias/referencias.md).

- `01`–`07`, `09`–`13`, `15`–`18`: copias locales disponibles.
- `08` (Carrera et al., 2026) y `14` (Pandey et al., 2025): números reservados; no hay copia local por acceso cerrado. No reutilizar esos números.
- `19` y `20`: referencias web (Statista y ADEN); no tienen PDF.
- `contexto/`: PDFs de literatura relacionada no citada en el paper.
- `contexto/lakens-2022.pdf`: preprint del autor sobre justificación del tamaño muestral, incorporado para el estudio ampliado; no es un benchmark ni una copia editorial. Fuente y SHA en su nota bibliográfica.
- `Irrelevantes/`: PDFs descartados, conservados para trazabilidad.

La extensión dirigida de 2026-11-14 incorpora `contexto/chae-2024.pdf`, `contexto/bessi-2016.pdf` y `contexto/lee-kim-2026.pdf` sin renumerar la colección histórica. Sus citas, roles, hashes y disponibilidad están en el registro canónico y `docs/referencias/targeted-downloads.json`. El PDF de Tran (2022) sigue pendiente: el editor rechazó ambas rutas de descarga con HTTP 403.

La ronda de representación del objetivo de 2026-11-15 incorpora `contexto/mutlu-ozgur-2022.pdf` como antecedente técnico de marcadores y lectura de tokens del objetivo. Su nota e integridad están en el mismo registro; no es un benchmark de polarización ni modifica la numeración histórica.

La ampliación auxiliar IA incorpora `contexto/bansal-sharma-2023.pdf` (arXiv:2306.15766v1) como contexto técnico de anotaciones LLM para entrenamiento. No estudia polarización ni valida estas anotaciones; véase su nota en el índice canónico.

El refinamiento humano final incorpora `contexto/jiang-2021.pdf` (NEEDLE, ACL-IJCNLP 2021) como antecedente técnico. Su §3.3 trata el ajuste final con etiquetas fuertes después del aprendizaje con supervisión débil; no es un benchmark de polarización ni una validación de la referencia asistida local.
