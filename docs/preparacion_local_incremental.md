# Preparación local incremental

Mientras `targeted publication collect --daily-api-budget 9000` captura los videos, ejecutar en otra terminal:

```bash
.venv/bin/sa-polarization targeted publication prepare-local --watch
```

Sin `--watch` realiza una sola pasada. No usa servicios externos ni consume cuota. El modo continuo consulta cambios cada 60 segundos, no genera otro informe si las entradas son iguales y termina cuando existe el snapshot congelado. Un bloqueo separado impide dos preparadores, pero permite continuar la captura.

Lee el histórico protegido y los videos completos en el orden de `videos.csv`; excluye capturas incompletas, indisponibles o no iniciadas del aporte nuevo y las cuenta por separado. Mantiene la primera versión histórica de cada comentario, registra recapturas y rechaza conflictos de identidad. Conserva filtros de fecha, texto padre y extracción explícita del registro congelado, sin predecir valencia.

La caché vive en `data/targeted/ap_publication_20261117_v1/local_preparation_cache/`. Cada fragmento contiene filas normalizadas, candidatos y exclusiones con un manifiesto de hashes. La clave depende de la fuente, periodos, registro y código. Los fragmentos e informes se publican mediante renombrado atómico; una fuente que cambia durante el procesamiento se pospone. Una caché alterada provoca un error y no se usa silenciosamente.

Los informes versionados quedan en `outputs/targeted/ap_publication_20261117_v1/local_preparation/`, con resumen JSON, distribución por fuente/mes/canal/tipo y oportunidad estructural por usuario. `local_preparation_cache/latest.json` señala la última pasada publicada. Los conteos son parciales: la oportunidad estructural no confirma comparabilidad afectiva ni polarización.

Esta preparación no crea `corpus.csv`, muestras, propuestas, decisiones humanas, benchmark ni AP final. Una vez cerrada la captura, el comando existente `freeze` reutiliza los fragmentos válidos y calcula lo que falte. Conserva formato, orden y muestreo del cierre sin caché. El cierre toma el bloqueo del recolector para impedir cambios concurrentes; no se debe intentar durante una captura activa. La referencia histórica de prueba, modelos, registro y manuscrito permanecen protegidos.

Verificación: `tests/test_local_preparation.py` compara byte a byte corpus, recapturas, exclusiones, usuarios elegibles y benchmark con/sin caché; comprueba reutilización sin repetir extracción, transición incompleto/completo, invalidación, corrupción, fuentes cambiantes y salida del modo continuo.

## Continuación hasta las muestras

Para encadenar la captura autorizada y su cierre:

```bash
.venv/bin/sa-polarization targeted publication advance --watch --daily-api-budget 9000
```

`advance` espera al recolector existente sin duplicarlo. Si quedan videos pendientes, usa el presupuesto compartido del Pacífico y reanuda la captura al renovarse. Una respuesta de cuota oficial suspende también las llamadas hasta el siguiente periodo, aunque el contador local conserve saldo. Un error de transporte/API/captura requiere revisión y detiene la continuación; no se reintenta indefinidamente. No cambia canales, periodos ni el presupuesto protegido de configuración.

Cuando todos los videos están completos o tienen indisponibilidad registrada, ejecuta `freeze`, inicializa el benchmark ciego y el primer lote de usuarios por el orden congelado. Si ya existen, verifica sus manifiestos y conserva sus archivos. Guarda los dos preflight y el estado operativo en `outputs/targeted/ap_publication_20261117_v1/advancement/`. No sobrescribe muestras ni confirmaciones humanas. El estado `waiting_annotations` marca el fin de esta continuación; no genera propuestas, predicciones, entrenamiento ni AP final.

Después se preparan las propuestas completas de cohorte por lectura, conservando su procedencia, y el humano anota primero el benchmark a ciegas antes de revisar propuestas de cohorte. Los lotes posteriores siguen los comandos y reglas de [estudio publicable](estudio_publicable.md). La inferencia diagnóstica recibe las muestras definitivas cuando estén preparadas; el análisis final exige las confirmaciones correspondientes.

Sin `--watch`, `advance` realiza una pasada: puede ejecutar una tanda de captura, cerrar y preparar muestras, o devolver el motivo de espera. El proceso continuo consulta cada 60 segundos y utiliza un bloqueo propio para impedir controladores duplicados. Se puede reanudar con el mismo comando. Si el equipo se apaga o el proceso termina, no hay un servicio del sistema que lo reinicie por sí solo.

## Servicios independientes de la conversación

```bash
.venv/bin/sa-polarization targeted publication start-services --daily-api-budget 9000
.venv/bin/sa-polarization targeted publication runtime-status
```

`start-services` crea dos servicios transitorios de usuario de systemd: continuación y preparación local. Reutiliza servicios activos y rechaza duplicar procesos externos. Los registros quedan en `outputs/targeted/<estudio>/runtime_logs/`. No pasa claves en argumentos ni modifica credenciales. Los servicios sobreviven al cierre de la terminal o de esta conversación mientras siga funcionando el administrador de servicios del usuario; no se instalan para arrancar tras reiniciar el equipo. No reinician automáticamente errores de captura. El comando informa los nombres de unidad para consultar `systemctl --user status <unidad>` o detenerlos con `systemctl --user stop <unidad>`.

`runtime-status` consulta bloqueos reales y muestra por separado el último estado registrado y el pulso del controlador. Un `waiting_quota` guardado no implica que exista un proceso activo. El controlador renueva su pulso cada 30 segundos incluso durante una captura larga. La consulta no crea archivos ni consume API.

## Auditoría del aporte y del trabajo de anotación

```bash
.venv/bin/sa-polarization targeted publication audit-capture
```

Compara el histórico protegido con su unión con capturas completas, verifica fuentes y guarda un informe sellado bajo `capture_audits/`. Incluye composición por fuente/canal/mes/tipo, comentarios y respuestas realmente nuevos, recapturas, exclusiones, padres ausentes o pertenecientes a otro video y aumento de candidatos estructurales. Estima comentarios de los primeros 100, 500, 800 y 1,000 candidatos por el orden fijado. Estos prefijos no son muestras definitivas antes del cierre ni usuarios afectivamente confirmados. Un padre ausente puede deberse a eliminación o falta de observación; `parent_id` no identifica necesariamente al interlocutor. La auditoría no calcula AP ni clasifica valencia.

Las [instrucciones de anotación](guia_anotacion_publicacion.md) describen exportación y revisión por tandas de 50, independencia del benchmark y ejemplos ficticios.
