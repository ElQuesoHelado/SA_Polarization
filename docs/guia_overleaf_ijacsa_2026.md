# Actualizar el proyecto de Overleaf a IJACSA 2026

La migración usa el contenido actualizado de `docs/doc_correcciones.tex`, la clase suministrada por el usuario y la bibliografía vigente. El archivo de correcciones y la plantilla original se conservaron intactos. La entrega contiene archivos individuales, sin ZIP.

## Archivos que debes subir o reemplazar

La carpeta local `outputs/manuscrito/abstract_closing_20261123/overleaf_files/` contiene exactamente los archivos que debes subir. Conserva sus carpetas: la raíz de esa carpeta equivale a la raíz de tu proyecto de Overleaf.

| Ruta en Overleaf | Qué hacer |
|---|---|
| `latexmkrc` | Subir a la raíz. Si ya tienes uno, conservar un respaldo e integrar su configuración; la migración debe dar prioridad a la clase local. |
| `IEEEtran.bst` | Subir o reemplazar en la raíz: estilo bibliográfico IEEEtran usado en la validación. |
| `IEEEabrv.bib` | Subir o reemplazar en la raíz: abreviaturas bibliográficas estándar. |
| `SAI_Paper_Format_Latex/IEEEtran.cls` | Crear esta carpeta y subir la clase suministrada, sin editarla. |
| `Paper_format.tex` | Subir o reemplazar en la raíz con el artículo migrado. Será el documento principal. |
| `References.bib` | Subir o reemplazar la bibliografía vigente en la raíz, respetando la mayúscula inicial. |
| `figures/pipeline_actual.tikz` | Subir el diagrama del método. |
| `figures/youtube_icon.pdf` | Subir el icono utilizado por ese diagrama. |
| `figures/observational_gap_distribution.pdf` | Subir la distribución de la brecha. |
| `figures/observational_event_support.pdf` | Subir la figura de soporte por usuario. |
| `figures/observational_balance_matrix.pdf` | Subir la matriz de balances. |

Las demás gráficas del artículo están definidas dentro del TeX y no necesitan archivos adicionales. El PDF complementario actualizado se conserva junto al PDF principal de la entrega local; no es una dependencia de compilación del artículo.

## Configuración en Overleaf

1. Selecciona **`Paper_format.tex` de la raíz como Main document/documento principal**. Reemplaza su contenido anterior con el archivo de esta entrega.
2. Selecciona **pdfLaTeX** como compilador.
3. Usa **Recompile from scratch / Recompilar desde cero** después de subir todos los archivos.
4. Comprueba que el PDF muestre la cabecera IJACSA con año 2026, el título sin «An Observational Study» y los tres autores con su afiliación compartida.

El `latexmkrc` debe estar en la raíz, no dentro de `docs`. El log debe cargar `SAI_Paper_Format_Latex/IEEEtran.cls`. La clase suministrada declara internamente la versión 2012/11/21 V1.8c: ese identificador corresponde a la clase incluida en la plantilla 2026. Si el log carga la clase de la distribución TeX (por ejemplo, V1.8b de 2015) se está usando una configuración diferente.

## Referencias y archivos anteriores

El artículo ahora usa `\bibliography{IEEEabrv,References}` y carga `xurl` y `hyperref`. Mantén las URLs completas en el `.bib`, incluidos sus guiones bajos; no añadas espacios, signos matemáticos ni cortes manuales.

No necesitas borrar tu documento anterior para probar esta migración: puede quedar como respaldo, pero no debe ser el Main document. El nuevo artículo no lee `referencies.bib`, el antiguo `figures/pipeline.tikz` ni la bibliografía de ejemplo de la plantilla.

No subas ni reutilices los `.aux`, `.bbl`, `.blg`, `.log` o `.dvi` de la plantilla. Overleaf debe regenerarlos. Tampoco pegues el contenido de un `.bbl` antiguo dentro del artículo ni redefinas `\url` en otro archivo.

Si todavía ves URLs sin guiones bajos o letras en estilo matemático, comprueba primero el Main document, la presencia del nuevo preámbulo con `xurl` y la recompilación desde cero. La validación local usa únicamente los archivos enumerados arriba.

## Iteraciones futuras

Después de editar en Overleaf, copia el documento principal completo actualizado a `docs/doc_correcciones.tex`. Ese archivo seguirá siendo la entrada revisada para la siguiente actualización del documento activo. Mantén las rutas de esta estructura para poder repetir la compilación local y la de Overleaf con los mismos archivos.

El nombre del documento principal en Overleaf es `Paper_format.tex`. El archivo local de edición sigue siendo `docs/doc_a_modificar.tex`; la entrega conserva su contenido y adapta la ruta bibliográfica a `References.bib` y las imágenes a `figures/` en la raíz. En Overleaf no se necesita ninguna carpeta `docs/`.
