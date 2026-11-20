# Mutlu y Özgür (2022): representación del objetivo en BERT

**Cita:** Mutlu, M. M.; Özgür, A. (2022). *A Dataset and BERT-based Models for Targeted Sentiment Analysis on Turkish Texts*. ACL Student Research Workshop, 467–472. DOI [10.18653/v1/2022.acl-srw.39](https://doi.org/10.18653/v1/2022.acl-srw.39).

**PDF:** `pdfs/contexto/mutlu-ozgur-2022.pdf`. **Rol:** antecedente técnico de clasificación dirigida; no benchmark de polarización. Verificado contra el PDF el 2026-11-15.

## Hallazgos citables

- Secciones 4–4.1 y figura 1: compara entradas sin modificar con marcadores especiales alrededor del objetivo, usando representación global CLS, primer marcador o máximo de estados de tokens del objetivo. Añade el marcador al vocabulario y redimensiona embeddings.
- Tabla 3: F1 macro 0.610 para T-BERT y 0.669 para T-BERT marcado con max pooling, sobre su conjunto turco de prueba. No transferir estas cifras al español peruano ni a nuestro corpus.
- Tabla 4 y sección 5: examina por separado textos con sentimiento general distinto del dirigido; sus resultados muestran por qué acertar el tono global no basta para valorar un objetivo.

## Transferencia y límites

Son tuits turcos sobre seis marcas/empresas, no comentarios políticos peruanos ni una medida AP. Nuestro experimento conserva la entrada de par nombre–comentario, dos marcadores distintos y la primera mención automática; su max pooling excluye marcadores. Es una adaptación con ablación local, no una réplica exacta. No demuestra de antemano que mejore BETO ni que alcance los criterios congelados.

## Uso en el proyecto

Fundamento técnico del experimento `development_targetaware_20261115_v1`, descrito en [entrenamiento y validación](../entrenamiento_validacion_dirigida.md). Registrar siempre que la selección usa validación reutilizada/asistida y que los 500 finales permanecen reservados.
