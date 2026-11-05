# QA · Grupo 5 · Resultados

Licenciamiento · Node Platform · Backups · Update Manager

> Corrida del **2026-10-28**, rama `feature_encapsulacion`, versión del producto **2.17.0**. La guía es [qa/grupo5-qa-test.md](qa/grupo5-qa-test.md) (se corrigió con lo que esta corrida encontró: ver §5).
> Cómo leerlo: **Pasó** = se hizo y dio lo esperado · **Pasó, la guía estaba mal** = el producto hace lo correcto y se arregló la guía · **Hallazgo** = diferencia real, con número H-n · **Pendiente** = no se pudo ver en esta corrida y por qué.

## 1 · Resumen

| | |
|---|---|
| Pruebas de la guía con resultado | 28 de 29 (la 1.1 C necesita una OPS AVACOM de fábrica); en varias, lo que pide la guía de pantalla o del Host real queda pendiente (§6) |
| Defectos del **producto** | **0 que haya que corregir ya.** 5 hallazgos (H-1 a H-5) para decisión del CTO, ninguno bloquea las pruebas |
| Defectos de la **guía** | **11**, todos corregidos en `qa/grupo5-qa-test.md` |
| Suite automática de los cuatro módulos | **837 pruebas en verde** (10 omitidas por diseño), 276 s |
| Resto de la línea base | Host 89 · emisor de licencias 129 · emisor de actualizaciones 13 · ensayo de la puerta de dispositivo 27/27 · ensayo de la clave del paquete cifrado 27/27 |
| Código del producto tocado | **Ninguno** (los commits son de documentación) |

## 2 · Cómo se corrió

Ningún paso tocó la fecha de Windows, el registro, `%ProgramData%` ni el servicio instalado.

- **Nodos de pruebas aislados** (`manage.py runserver --noreload`, entorno de desarrollo, base, cola, respaldos, actualizaciones y licencia en carpetas temporales, logs fuera del repositorio): `:8010` (respaldos, nodo y actualizaciones), `:8011` (licencia y reloj; con un `sitecustomize` que mueve el reloj **sólo para el nodo y la licencia**, como el recorrido de fecha de MOD-018) y `:8013` (el «equipo nuevo» de la 3.3, otra clave del nodo).
- **Sesiones reales por HTTP**: administración (con PIN maestro), técnico, docente y alumno; la organización se instaló por `POST /api/acceso/instalacion/`.
- **Llaves de desarrollo**: los pases de soporte y los paquetes se firmaron con las llaves de pruebas del repositorio (sólo las acepta un nodo de desarrollo). Para la licencia se creó un `.avkey` con `dev-1` y se usó la **herramienta de emisión real** (`tools/licencias`), no un firmador de pruebas.
- **El Host se simuló** donde la guía lo exige (4.5 y 4.7): el nodo deja `orden.json` y la prueba escribe el `resultado.json` que dejaría el Host.
- Lo que sólo es de instalador/firmware se probó con los **ensayos del repositorio** (`Ensayar-Dispositivo.ps1`, `Ensayar-ClaveDelPaquete.ps1`), que corren en carpeta temporal, con claves de usuario de ensayo y sin elevarse.

## 3 · Resultados por prueba

### Licenciamiento (guía §1)

| # | Resultado | Evidencia |
|---|---|---|
| 1.1 A · PC normal | **Pasó (ensayo)**, pantalla pendiente | Sin la variable UEFI `puerta-instalacion` sale con 47 y **no deja solicitud para llevar a AVACOM**; identificador mal formado también 47; el código para una variable ausente es `AVC-UEFI-01` (`IdentidadUefi.cs:95`) y el mensaje obligatorio está literal en `codigo.iss:1241`. El asistente real no se corrió (pide administrador) |
| 1.1 B · copiar una instalación | **Pasó (ensayo)** | `Ensayar-ClaveDelPaquete`: el `Backend` cifrado no trae ningún `.py` ni `__pycache__`, sólo `codigo.avpkg`; sin sello **no arranca**; copiado a otro equipo se niega (42) y sin claves de AVACOM se niega (44); con la clave de otro equipo no libera; revocado (43); la llave del paquete no aparece en ningún archivo |
| 1.1 C · OPS AVACOM real | **Pendiente** | No hay una OPS AVACOM de fábrica en este equipo (lectura del firmware con privilegio) |
| 1.2 Paso 1 · sello | **Pasó (ensayo)** | La estación firma con inventario que trae la serie; **se niega** con una serie ajena y con un identificador UEFI distinto; un sello alterado → 41; el de otro equipo → 42; lista de revocados → 43; la MAC no entra en la decisión |
| 1.2 Paso 2 · solicitud | **Pasó** | `POST /api/licencia/solicitud/` → `.avreq` de 290 bytes, nivel `hardware`, 2 de 2 piezas; no contiene nombres, DNI ni contraseña |
| 1.2 Paso 3 · emitir | **Pasó** | «ver solicitud»: *firma válida*. Resumen con aula, vigencia, **60 equipos · 1200 usuarios · gracia 30 días**. Sin `EMITIR` → «Cancelado: no se creó ningún archivo»; **61 equipos → se niega** (decisión Q-L1); con `EMITIR` → `.avlic` + hoja + «Licencia emitida y verificada». Se probaron los comandos, **no el menú del `.bat`** |
| 1.2 Paso 4 · activar | **Pasó** | `activa`, 60/1200/gracia 30, 366 días restantes. Carácter cambiado → `licencia_invalida/firma_invalida`; licencia de otra huella → `409 huella_no_coincide` («emitida para otro equipo») |
| 1.2 Paso 4 · fecha adelantada | **Pasó, la guía estaba mal** (G-5) | +3 días: sin aviso (el umbral es **7 días**). +40 días: bandera `reloj_adelantado`, `restringe: false`, el aula responde 200. Al devolverla el aviso se quita (ver H-1) |

### Node Platform (guía §2)

| # | Resultado | Evidencia |
|---|---|---|
| 2.1 | **Pasó** (API) | `operativo`, sin motivos, base íntegra; el anónimo recibe 401; el docente 403 |
| 2.2 | **Pasó** (API); banner pendiente | Clase iniciada y alumno unido: sigue `operativo`, `restringido: false`. Que no salga banner en el menú es de pantalla |
| 2.3 | **Hallazgo H-2 · la guía estaba mal** | La lista de consumidores está **vacía** también durante la clase; nada la llena todavía |
| 2.4 | **Pasó, la guía estaba mal** (G-3) | Con el proceso del nodo matado a la fuerza, el arranque siguiente trae `apagado_sucio_previo: true`, `operativo`, y la cola conserva sus eventos |
| 2.5 | **Pasó** | `problemas.total = 0` |
| 2.6 | **Pendiente** (parcial) | Sin un consumidor registrado no hay eventos apartados que reprocesar: la ruta responde `404 no_encontrado` a un id inexistente. Lo cubre `test_problemas_sin_carga_y_reproceso_por_rol` de la suite |
| 2.7 | **Pasó** | Técnico: `403 sin_permiso` (`node.queue.replay`, «lo recibe por una escalada temporal»); docente 403; la administración llega al 404 |
| 2.8 | **Pasó** | Reloj 2 días atrás → `restringido` con `reloj_retrocedido`; 30 min atrás no restringe; al corregir → `operativo`. Con el nodo restringido el aula sigue atendiendo (el modo restringido aún no se aplica) |

### Backups (guía §3)

| # | Resultado | Evidencia |
|---|---|---|
| 3.1 respaldo completo | **Pasó** | 201, `completo_verificado`, `restaurable`, 1,9 MB, constancia en `Informes\`, `aviso_sin_respaldo: false`; el estado no trae el código de custodia |
| 3.1 custodia | **Pasó, la guía estaba mal** (G-6) | Sin pase → `pase_requerido`; con pase → código en pantalla **una vez**; pedirla otra vez → `409 custodia_ya_emitida`. Un respaldo hecho **antes** de la custodia sale `con_custodia: false` |
| 3.1 exportar | **Pasó** | Sin pase → `pase_requerido`; con pase → `.avbak` en `AVACOM\Respaldos\` de la «USB»; el mismo pase otra vez → `pase_invalido`; el archivo empieza por `AVBK`, sin texto legible |
| 3.1 informes | **Pasó** | La administración lee constancias y el CSV; sin DNI, sin códigos, sin rutas |
| 3.2 restaurar | **Pasó** | Con una clase abierta → `409 sesion_activa` y **el pase no se gasta** (se reutilizó). Cerrada la clase: restaura, informa lo perdido (0,0 horas y 11 eventos), cierra las sesiones (401 con el token viejo), los 3 estudiantes vuelven `ACTIVO` e idénticos |
| 3.2 negativas | **Pasó** | Un bit cambiado → no verifica, `restaurable: false`, restaurar → `409 restauracion_abortada/integridad_alterada` y los datos quedan como estaban; pase vencido y pase de otra operación → `pase_invalido` |
| 3.2 roles | **Pasó** | Administración lee (200) y no respalda (403); docente 403 |
| 3.3 equipo nuevo | **Pasó, la guía estaba mal** (G-9) | Otro nodo con otra clave: el respaldo de la USB aparece como candidato; **sin custodia** → `409 restauracion_abortada/clave_no_disponible`; código equivocado → `datos_invalidos`; con la hoja → restaura (`nueva_huella: true`) y están los 3 estudiantes |

### Update Manager (guía §4)

| # | Resultado | Evidencia |
|---|---|---|
| 4.1 | **Pasó** | El paquete aparece en la raíz **y** en `AVACOM\` de la unidad; el docente recibe 403 |
| 4.2 | **Pasó** | `201`, estado `verificado`, con manifiesto; no se aplicó nada |
| 4.3 | **Pasó** | `202`, `aplicando`, `orden.json` escrita, `limite_minutos: 5`; una segunda orden → `409 estado_invalido` |
| 4.4 | **Pasó** | Iniciar clase durante la orden → `503 actualizacion_en_curso`, «El aula se está actualizando; vuelve a intentarlo en unos minutos», `reintentar_en_s: 60` |
| 4.5 | **Pasó (Host simulado)** | Con el `resultado.json` → `aplicado` y la clase vuelve a poder iniciarse. Lo que hace el Host real (3 a 5 min, servicio parado) no se vio |
| 4.6 | **Pasó** | Historial (recibido, verificado, bloqueada, aplicando con quién, aplicado) y asientos del módulo en la Bitácora; la cadena verifica (`POST /api/auditoria/verificar/` → `verificada`, 65 asientos) |
| 4.7 | **Pasó (Host simulado)** | Sin nota → 400; con nota → `202` orden `revertir`; con el resultado → `revertido` |
| 4.8 | **Pasó** | Un byte cambiado → `422 paquete_invalido/estructura`; en `paquetes\` sólo queda el bueno |
| 4.9 | **Pasó, la guía estaba mal** (G-10) | Serie igual a la instalada: se importa **«incompatible»** y **Aplicar** responde `409 ya_aplicado` sin escribir orden |
| 4.10 | **Pasó** | Con una clase abierta → `409 sesion_activa`; no hay `orden.json`; la clase sigue |
| 4.11 | **Pasó** | Técnico: importa y ve (201/200); aplicar, programar y revertir → `403 sin_permiso` |

## 4 · Hallazgos del producto

| # | Qué | Severidad | Decisión |
|---|---|---|---|
| **H-1** | **Adelantar la fecha y devolverla deja el NODO «Restringido» (reloj retrocedido) hasta que la fecha real alcance lo adelantado.** La licencia hace lo que decidió el CTO (Q-L13: no guarda la fecha adelantada, sólo avisa), pero la marca alta de MOD-015 sí sube con el salto (`anclas.marca_siguiente = max`). En la corrida: +40 días y vuelta → `retroceso_ms = 3 455 969 137` y `reloj_retrocedido`; la licencia quedó `activa` con `reloj_sospechoso` | Media. Hoy sin efecto (el modo restringido sólo avisa), pero con la Fase 5 un reloj mal puesto una vez dejaría el aula en 503 durante días | Del CTO / Fase 6 de MOD-015, donde ya está prevista la unificación de los dos relojes. **No se tocó el código** |
| **H-2** | **La pantalla «Estado del equipo» no puede mostrar «Al día»:** ningún módulo llama a `registrar_consumidor`, así que `consumidores` está vacío. Los seis módulos cortados sí aparecen en `cortes` | Baja | Fase 4 de MOD-015. La guía se corrigió |
| **H-3** | **Un respaldo hecho con una clase abierta la hace reaparecer abierta al restaurar** y deja sin reconstruir el índice de búsqueda y los reportes (`post.fallos: sesion_activa`). El resultado es `ok: true` y recomienda reiniciar | Baja/media | Diseño: ¿cerrar o suspender las clases «fantasma» al restaurar? Hoy se resuelve respaldando con la clase cerrada. **No se tocó el código** |
| **H-4** | **Q-B8 sigue abierto y se reprodujo:** con la sesión de administración se creó un usuario `TECHNICIAN` (201) y con él se respaldó, se verificó y se pidió la custodia. Lo que realmente exige el pase de AVACOM es exportar, restaurar y emitir la custodia | Media (seguridad), **ya conocida** | Del CTO (MOD-001). Tampoco se tocó |
| **H-5** | Tras **cualquier restauración** el estado trae `apagado_sucio_previo: true` (se vio en el nodo `:8010`). Causa probable, sin comprobar en el código: el respaldo se toma con el nodo vivo y la última fila de arranque queda abierta en la copia | Baja, informativa | Ninguna por ahora |

**Incidente de la propia corrida, sin consecuencias:** durante ≈ 60 s el nodo `:8013` arrancó con una variable apuntando a las carpetas del `:8010`. Se detuvo de inmediato; no escribió respaldos (la carpeta quedó igual), y el `:8010` siguió `operativo` con sus datos.

## 5 · Lo que se corrigió

**La guía** (`qa/grupo5-qa-test.md`), 11 puntos:

| # | Antes | Ahora |
|---|---|---|
| G-1 | Cualquier «instalador de pruebas firmado» | Debe compilarse con llave de sello de prueba; `installer/latest` (2.16.1, con 732 `.py` en `dist\staging`) es anterior a la segunda protección |
| G-2 | 2.3 «consumidores Al día» | Lista vacía en esta versión (H-2) |
| G-3 | 2.4 «cierra OPS a la fuerza» | Se termina el proceso del **servicio**; la ventana de OPS no lo prueba |
| G-4 | 2.6 «toca Reprocesar» | Sólo si hay un evento apartado, que hoy sólo provoca la suite |
| G-5 | 1.2 «adelanta la fecha varios días» | Más de 7 días; y el efecto sobre el nodo (H-1) |
| G-6 | 3.1 custodia después del respaldo | Va **antes**; si no, `con_custodia: false` y la 3.3 no puede pasar |
| G-7 | 3.2 «restaura» | Falta el `motivo` (lista cerrada) y que el respaldo se hace con la clase cerrada |
| G-8 | 3.2 «borra datos» | Cómo: `PATCH estado RETIRADO` o desde OPS |
| G-9 | 3.3 `custodia_requerida` | Es `409 restauracion_abortada/clave_no_disponible` |
| G-10 | 4.9 «lo rechaza (`ya_aplicado`)» | Se importa «incompatible» y Aplicar da 409 |
| G-11 | 4.5 sin aclarar quién aplica; 4.11 sólo «no aplicar» | El Host real aplica; el técnico tampoco programa ni revierte |

**El producto:** nada. Los hallazgos H-1, H-3 y H-4 cambian comportamiento acordado con el CTO o tocan otros módulos; se dejan por escrito para que se decida.

## 6 · Lo que no se pudo comprobar

- **El asistente del instalador en una PC real elevada** y **la OPS AVACOM de fábrica** (1.1 A en pantalla y 1.1 C): sólo los ensayos del Host y de la clave del paquete.
- **Las pantallas de OPS** (chip y motivos de Estado del equipo, que no haya banner con clase, «Licencia activa», pantalla Actualizaciones, la confirmación única): se probó el contrato que las alimenta, no la ventana. Los recorridos por UI Automation del repositorio (`tests/Avacom.Lms.Ops.Uia`) no se corrieron.
- **El Host real aplicando y revirtiendo** (4.3 a 4.7): sólo la orden y un resultado simulado. El tope de 3 a 5 minutos no se midió.
- **La fecha de Windows**: no se cambió (sería tocar la configuración del equipo); el salto se hizo dentro del proceso del nodo.
- **El menú guiado de `Emitir-Licencia.bat`**: se probaron sus comandos.
- **Una licencia de otro equipo con otro hardware real**: se usó una licencia firmada para otra huella.
- **Windows 10, memorias FAT32/exFAT reales y TPM discreto**: igual que antes (§ final de la guía).

## 7 · Línea base automática

| Qué | Resultado |
|---|---|
| `manage.py test licenciamiento nodo respaldo actualizacion` | **837 en verde**, 10 omitidas, 276 s (con el árbol de trabajo de la segunda protección, sin commitear) |
| `dotnet test tests/Avacom.Ops.Host.Tests` | **89 en verde** |
| `tools/licencias` (unittest) | **129 en verde** |
| `tools/actualizacion` (unittest) | **13 en verde** |
| `Ensayar-Dispositivo.ps1` | **27 correctas, 0 con falla** |
| `Ensayar-ClaveDelPaquete.ps1` | **27 correctas, 0 con falla** (el backend cifrado arranca en 5,7 s; el mismo backend plano, en 7,6 s) |

## Cierre

- [x] 1.1 A y B por ensayo · 1.2 pasos 1 a 4
- [x] 2.1 a 2.8 (2.3 y 2.6 con la salvedad de H-2)
- [x] 3.1 · 3.2 (los 3 estudiantes volvieron) · 3.3
- [x] 4.1 a 4.11 (4.5 y 4.7 con el Host simulado)
- [ ] Pendiente en el aula de pruebas: 1.1 C, pantallas de OPS, Host real
