# 18 · Backup & Recovery (MOD-016) · Pruebas

## 1 · Cifras (2026-10-26)

| Qué | Resultado |
|---|---|
| Pruebas propias (`manage.py test respaldo`) | **135 en verde**, ≈ 40 s |
| Suites vecinas que el módulo toca (`acceso audit nodo actualizacion expediente licenciamiento`) | **1131 pruebas, 10 omitidas, 0 fallos** tras un ajuste: `nodo.tests.test_arquitectura.test_sin_dependencias_nuevas` falló porque el adaptador de la purga importa `respaldo` (la dependencia es a propósito y está declarada en esa lista) |
| Resto del backend (`classroom_engine evaluacion modo_estudio device_manager search reporting gradebook cola_medios logs biblioteca cache_medios expediente`) | **1626 pruebas, 8 omitidas, 1 error AJENO** (§1.1) |
| Comprobación **en vivo** (SQLite de archivo y la conexión REAL de Django, no un `TestCase`) | respaldo en caliente con un hilo escribiendo parejas de filas · 121 filas = 1 + 60 parejas completas · restauración real: la conexión de Django ve la base restaurada, el modo WAL se restituye, el archivo vuelve a su versión |

Por archivo: `test_formato` 20 · `test_dominio` 31 · `test_infraestructura` 14 · `test_motor` 36 (11 de ellas, `Endurecimiento`, son los hallazgos de la revisión independiente) · `test_acceso` 11 · `test_vigilante` 13 · `test_arquitectura` 10.

### 1.1 · Resto del backend

El único error es `reporting.tests.test_arquitectura.test_el_escritor_de_archivos_usa_solo_la_biblioteca_estandar`: lee `backend/requirements.txt` como UTF-8 y el archivo quedó en **UTF-16** con el commit `d1ac03e1` («Actualización de los requirements»). No lo causa este módulo y **no se tocó** (es del dueño de ese commit): conviene guardar `requirements.txt` en UTF-8.

## 2 · Qué se probó, contra el Maestro

| Escenario del Maestro | Prueba |
|---|---|
| **TST-058** · respaldo válido: verificado y restaurable, con tamaño y conteo coincidentes | `Respaldar.test_un_respaldo_completo_queda_cifrado_verificado…` · `test_la_base_respaldada_es_una_copia_consistente…` · `Verificar.*` |
| **TST-059** · archivo truncado: restauración abortada **antes de tocar los datos vivos** | `Restaurar.test_TST_059…`: la base viva sigue vacía, no se toma punto de retorno, el pase **no** se gasta, queda `restauracion_abortada` |
| **TST-060** · restaurar en un equipo nuevo (hardware distinto) | `Restaurar.test_BR_102…`: otra clave y otra identidad del equipo → `custodia_requerida`; con el código se restaura, `nueva_huella`, y el equipo nuevo vuelve a anclar la custodia. *Sin* hardware distinto real ni los 30 min medidos |
| **TST-063** · reproceso de la cola tras restaurar | La restauración llama a `nodo.arrancar()` (INV-002); el reproceso de los consumidores lo prueban `reporting_reconstruir`/`gradebook_reconstruir`. Aquí se comprueba el orden y que un paso que falla no detiene a los demás (`TrasRestaurar.*`) |
| **BR-102** · cifrado con la clave del nodo, no restaurable en otro equipo sin la custodia | `Claves.*` (clave del nodo, custodia, otra clave, código de otra institución, respaldo anterior a emitir la custodia) |
| **INV-021** · ninguna evidencia legible en claro | `test_ningun_contenido_se_lee_en_claro` · `test_el_manifiesto…no_trae_nombres_de_archivos` · la constancia no trae DNI, códigos ni nombres de las personas de la prueba |
| **INV-002** · la secuencia nunca se reutiliza tras restaurar | Se delega en `nodo.arrancar()` (probado en MOD-015 con anclas); aquí sólo que se **invoca** tras aplicar |
| **BR-017 / INV-009** · la purga sólo con un respaldo verificado | `respaldo.servicios.verificado_hasta()` lo da el último restaurable que existe; `RespaldoVerificado` en `nodo` |
| **BR-003** · un solo escritor por grupo de datos | `Escrituras`: durante respaldar, verificar y **restaurar** sólo `m16_*`, `m15_*` y `m19_*` reciben escrituras (más el «último uso» de la sesión, que anota MOD-001 en cada petición) |
| **FUN-177** · reanudar un respaldo interrumpido | `Arranque.*` |
| **FUN-169/170/171** · programar, completo, incremental | `Calendario.*` (hora, días, zona, puesta al día, aplazar con una clase, reintento a la hora) |
| **CAP-103** · prueba periódica de restaurabilidad | `Verificacion.test_la_prueba_periodica…` |

## 3 · Lo propio de este módulo

- **Quién opera (D-1, D-2, D-3).** `MatrizDeRoles`: la **administración** lee todo y recibe **403** en las siete operaciones; profesor, alumno y reportes, 403 también en las lecturas; **sin sesión** y con un **actor declarado** en el cuerpo, 403; un rol que no es `TECHNICIAN` no pasa aunque tuviera el permiso; y la administración **no puede conceder por escalada** un `backup.*` que no tiene.
- **Pase de soporte.** Vencido · aún no vigente (con tolerancia de reloj) · vigencia de más de un día · otra operación · otro equipo · el comodín `*` · firma ajena · `kid` desconocido · **cada byte** cambiado de un pase · `kid` cambiado con la misma firma · **firma universal con puntos de orden pequeño** · un pase no puede autorizar `backup.read` ni permisos de otros módulos · **un solo uso** · el pase no viaja en la respuesta ni en la bitácora · un nodo de producción no carga la llave de desarrollo.
- **El archivo.** Ida y vuelta con varios trozos y un archivo vacío · truncado en 6 puntos · bytes de más · **300 cambios de un bit al azar, 0 aceptados** · trozos reordenados y repetidos · manifiesto alterado · versión desconocida · rutas que escapan (`../`, unidad, `\`, nombres reservados) · entradas duplicadas · un archivo que crece mientras se copia.
- **Instantánea.** Consistente con un escritor concurrente (parejas de filas, 5 copias) · cota de espera cuando la base está ocupada por su propia conexión (en vez de reintentar para siempre).
- **Restaurar.** Devuelve la base **y los archivos**, no borra lo que sobra, toma punto de retorno verificado, deja el informe y gasta el pase · con una clase abierta no se restaura y el pase no se gasta · un incremental aplica su cadena · desde una unidad externa sin el archivo en el equipo.
- **Catálogo.** Un `.avbak` que la base no conoce se cataloga desde la carpeta; uno que ya no está se marca caducado.
- **Retención.** Conserva los N más recientes y **nunca** deja sin base a un incremental ni sin el último restaurable.
- **Informes.** Castellano, sin DNI ni rutas, CSV con BOM y decimal con coma.

## 3 bis · La revisión independiente (2026-10-26)

Un revisor que **no escribió** el módulo lo leyó buscando defectos reales. Diez hallazgos; cada uno se verificó contra el código antes de aceptarlo:

| # | Hallazgo | Estado |
|---|---|---|
| 1 | La administración puede crear/asignarse `TECHNICIAN` y con él respaldar, programar, verificar y **reemplazar la custodia** (devolviendo el código en claro) | **Custodia corregida** (exige pase). **Abierto:** que la administración asigne `TECHNICIAN` es de MOD-001 (Q-B8) |
| 2 | Si fallaban los archivos tras aplicar la base, el equipo quedaba a medias (sin sesiones revocadas, sin salto de secuencia INV-002, sin licencia ni índices) | **Corregido** y probado (`parcial`) |
| 3 | Los pases gastados después del respaldo «revivían» al reemplazar la base | **Corregido** y probado (se copian todos y se vuelven a anotar) |
| 4 | Un respaldo sin verificar servía de base de incrementales y de «completo de la semana» | **Corregido** y probado |
| 5 | DPAPI en modo máquina: quien lea `estado\nodo.key` la abre | **Abierto** (Q-B12): hay que fijar la ACL; no se tocó sin saber con qué cuenta corre el servicio |
| 6 | El catálogo confiaba en el manifiesto en claro de cualquier `.avbak` | **Corregido** y probado (UUID, fecha, entradas; un archivo malo no rompe el resto) |
| 7 | Parámetros de scrypt tomados del manifiesto sin tope (CPU) y `TypeError` sin capturar | **Corregido** y probado |
| 8 | Archivos restaurados con fecha vieja: el siguiente incremental los omitía | **Corregido** y probado |
| 9 | Restaurar desde una unidad copiaba todos sus respaldos al disco del nodo | **Corregido** y probado (sólo la cadena, con espacio comprobado) |
| 10 | La nota libre del técnico la leía quien tuviera `backup.read` | **Corregido** y probado (va a la bitácora) |

Lo que el revisor **confirmó sin defecto:** ninguna ruta sin permiso ni anónima; el orden del pase (firma antes de interpretar, puntos de orden pequeño, unicidad por clave primaria); nonces, AAD, truncado y reordenado del `.avbak`; path traversal al extraer y al aplicar; que hasta el paso 5 no se toca nada vivo. Y señaló, con razón, que `aplicar_base` contra la conexión viva de Django no tenía prueba de extremo a extremo: **se comprobó en vivo** (§1).

## 4 · Cómo repetirlo

```bash
cd backend
.venv\Scripts\python manage.py test respaldo
```

Las pruebas de integración usan `TestCase` con un nodo real instalado por HTTP. La API de respaldo de SQLite **no copia desde una conexión en medio de una escritura** (la envoltura de un `TestCase`): la instantánea de esas pruebas sale de `iterdump`, y la API real se prueba aparte (`InstantaneaDeLaBase`) y en vivo. La «base viva» de la restauración es un archivo SQLite aparte, no la conexión de la prueba.

## 5 · Lo que NO se pudo comprobar

| Qué | Por qué |
|---|---|
| **Memoria USB física** (exportar y restaurar desde una unidad extraíble real, FAT32/exFAT, retirada en caliente) | Las unidades de las pruebas son carpetas. `GetDriveType` real sólo se ejercita en Windows con una unidad conectada. |
| **Un equipo nuevo de verdad** (TST-060 en 30 min) y **NFR-052** (60 min, 100 % de datos críticos) | No hay segundo equipo. Se probó otra clave y otra identidad en el mismo equipo. |
| **Volumen real:** NFR-030 (completo de 200 GB en 20 min, incremental en 5) y la restauración de 200 GB en 90 min de JRN-019 | Lo medido: ≈ 1,9 MB en 0,23 s. El Maestro mismo lo marca «parcial: falta medir con el volumen de un ciclo». |
| **CAP-101 · volver a dar clase en menos de 3 minutos** | Restaurar en caliente no reinicia el servicio; el reinicio recomendado no se midió. |
| **DPAPI con la cuenta real del servicio** (SYSTEM/LocalService), con la clave copiada a otro equipo y la **ACL efectiva** de `Respaldos\\estado` | Se probó con el usuario del desarrollador. `LOCAL_MACHINE` debería funcionar para el servicio; no está visto (Q-B12). |
| **Antivirus** sobre `Respaldos\` y `trabajo\` | No hay un equipo con el antivirus del colegio. |
| **FUN-172** (punto de recuperación de 5 s) · **FUN-175** (restauración selectiva) | No construidos (D-14; la compuerta de FUN-175 sí se prueba). |
| **TST-054 / NFR-014** (corte eléctrico: 50 cortes, 30 s) | Es de MOD-015 y del almacén, no de este módulo; no se repitió. |
| **El Host y el instalador** | No se tocaron (cambios de otra sesión sin commitear): `Build-Installer.ps1` aún no excluye `respaldo\tests`. |
| **Pantallas de OPS** | No hay: ninguna prueba de interfaz. |
| **Concurrencia entre procesos** (dos procesos ASGI) | El candado de «un solo respaldo a la vez» es del proceso; el nodo corre un proceso. |
