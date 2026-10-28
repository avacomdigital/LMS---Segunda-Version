# QA · Grupo 5 · Guía corta de pruebas

Licenciamiento · Node Platform · Backups · Update Manager

> Cómo leerla: cada prueba tiene **Haz** (lo que tocas) y **Debe pasar** (lo que ves). Si lo que ves no coincide, es un posible bug: anota el número de la prueba, una captura y la hora.
> Los detalles técnicos están en `spec-driven/15-licenciamiento`, `16-node-platform`, `17-update-manager` y `18-backup-recovery`.

## Antes de empezar

| Necesitas | Para qué |
|---|---|
| Un **instalador de pruebas firmado**, compilado con una **llave de sello de prueba** (`-ExigirPuertaDeDispositivo`: worktree + llaves de prueba, sin tocar `installer/latest`). El que está publicado en `installer/latest` (2.16.1) es **anterior a la segunda protección**: no trae puerta de dispositivo ni código cifrado, y la prueba 1.1 fallaría contra él | Licenciamiento y Update Manager |
| Una **PC normal** (no AVACOM) y, si existe, una **OPS AVACOM real** | Prueba 1.1 |
| Un **equipo de pruebas** con OPS Master instalada y el backend en marcha | Todo lo demás |
| Una memoria USB | Licencia, backup y paquete de actualización |
| El **equipo de emisión** (sin internet) con la herramienta `tools/licencias` y la llave de **prueba** | Prueba 1.2 |

> **Dos formas de correrla.** *En el aula de pruebas* (instalador, OPS y USB reales) o *por API contra un nodo aislado* (`manage.py runserver` con base y carpetas temporales, llaves de desarrollo, sesión de técnico y pases de prueba de `respaldo/tests/emisor.py`). Lo hecho por API está en [grupo5-resultados-qa.md](../grupo5-resultados-qa.md), con lo que sólo se puede ver en pantalla marcado como pendiente.

> **Ojo con las llaves:** la ceremonia de la llave de sello (`sello-2026-1`) y la de Update Manager siguen pendientes. Un instalador de producción compilado hoy **sale sin puerta de dispositivo** y un nodo de producción **no acepta paquetes `.avupd`**. Por eso estas pruebas se hacen con instalador y llaves **de prueba**, nunca con las de producción.

---

## 1 · Licenciamiento

### 1.1 No se puede instalar en un equipo que no es AVACOM

**A. PC normal (sin identidad AVACOM)**

1. **Haz:** copia el instalador de pruebas a una PC corriente y ábrelo como administrador.
2. **Debe pasar:** el instalador **se detiene antes de copiar nada** y muestra el mensaje: *«El LMS solo puede correr en dispositivos AVACOM. En caso de tratarse de un error, contacte con su distribuidor o canales de soporte autorizados.»* con un código tipo `AVC-UEFI-01`.
3. **Comprueba:** no existe la carpeta `C:\Program Files\AVACOM\OPS Master` ni el servicio `AVACOMOPSBackend`.

**B. Copiar una instalación ya funcionando**

1. **Haz:** copia la carpeta de instalación y la de datos de un equipo AVACOM a la PC normal e intenta iniciar OPS.
2. **Debe pasar:** el backend **no arranca** (el código viaja cifrado y la llave solo la libera el equipo sellado). No se ve ninguna clase ni datos.
3. **Comprueba:** dentro de `Backend\` no hay archivos `.py`.

**C. Equipo AVACOM real (si lo tienes)**

1. **Haz:** instala en la OPS AVACOM con su sello cargado.
2. **Debe pasar:** instala sin quejarse y OPS abre. Como administrador, `Avacom.Ops.Host.exe verificar-identidad` dice **«Autorizado»**.

### 1.2 Generar una licencia completa (llaves y sellos)

Hay tres piezas y se hacen en este orden: **sello del equipo → solicitud → licencia**.

**Paso 1 · El sello del dispositivo (lo que hace de un equipo "AVACOM")**

1. **Haz:** en el equipo a licenciar, ejecuta `Avacom.Ops.Host.exe solicitar-sello`. Deja el archivo `equipo.avsol` en la memoria USB.
2. **Haz:** en el equipo de emisión, usa `avacom-licencias sello emitir` con ese `.avsol` y la llave de sello de prueba. Se crea el `.avsello`.
3. **Haz:** vuelve al equipo y ejecuta `Avacom.Ops.Host.exe instalar-sello` con la USB.
4. **Debe pasar:** el equipo queda en estado **Autorizado**.
5. **Prueba negativa:** intenta emitir un sello para una serie que **no** está en el inventario, o para una solicitud con un byte cambiado. **La estación se niega a firmar.**

**Paso 2 · La solicitud de licencia**

1. **Haz:** en OPS ve a **Licencia** y elige generar la **solicitud**. Guarda el `.avreq` en la USB.
2. **Debe pasar:** se crea el archivo. No contiene datos de alumnos.

**Paso 3 · Emitir la licencia (equipo de emisión, sin internet)**

1. **Haz:** doble clic en `Emitir-Licencia.bat`. Elige **ver solicitud** y arrastra el `.avreq`.
2. **Debe pasar:** dice «La firma del equipo es válida» y muestra el nivel de huella.
3. **Haz:** elige **emitir**: aula, plan `anual-aula`, fecha de vencimiento, llave de prueba y su frase de paso.
4. **Debe pasar:** aparece un **resumen** (aula, vigencia, 60 equipos y 1200 usuarios, gracia 30 días). Léelo.
5. **Haz:** escribe `EMITIR` y Enter.
6. **Debe pasar:** se crean un `.avlic` y una hoja de entrega `.txt`. El mensaje dice «Licencia emitida y verificada».
7. **Prueba negativa:** escribe otra cosa en vez de `EMITIR` → **no se crea ningún archivo**. Pide 61 equipos → **la herramienta se niega**.

**Paso 4 · Activarla en el aula**

1. **Haz:** en OPS, **Licencia** → carga el `.avlic` desde la USB (o con «Buscar en el Explorador…»).
2. **Debe pasar:** confirma una vez y la pantalla dice **Licencia activa**, con la fecha y los límites que emitiste.
3. **Pruebas negativas:**
   - Cambia un solo carácter del `.avlic` y cárgalo → **lo rechaza**.
   - Carga la licencia de otro equipo → «Esta licencia es de otro equipo».
   - Adelanta la fecha de Windows **más de 7 días** (con menos no hay aviso: es el umbral de la regla) → en un par de minutos aparece el aviso **«Fecha adelantada»**; las clases siguen y ningún módulo se apaga. Al devolver la fecha el aviso se quita solo (o la administración toca «Confirmar la fecha de hoy»).
   - Después de adelantar y devolver la fecha, **Estado del equipo** puede quedar en **Restringido** (reloj retrocedido) hasta que la fecha real alcance lo adelantado: ver el hallazgo H-1 de los resultados. No apagues nada por eso: hoy el modo restringido sólo avisa.

---

## 2 · Node Platform

Pantalla: **Bitácora → Estado del equipo**.

| # | Haz | Debe pasar |
|---|---|---|
| 2.1 | Abre **Estado del equipo** con el equipo recién arrancado | Chip **Operativo**; sin motivos de alerta |
| 2.2 | Inicia una clase y entra un alumno desde Student | La clase y el alumno funcionan; el estado **no se pone en rojo** y **no sale ningún banner** en el menú durante la clase |
| 2.3 | Mientras hay clase, mira la pantalla | En esta versión **la lista de consumidores está vacía** (ningún módulo se registra todavía como consumidor: es la Fase 4 de MOD-015). Lo que sí se ve: los **6 módulos ya cortados** a la cola única y que el contador de **eventos sube** al operar la clase. Cuando haya consumidores aparecerán **Al día** (o **Rezagado** unos segundos) |
| 2.4 | Termina a la fuerza el **proceso del servicio** del backend (Administrador de tareas → `AVACOMOPSBackend` / su `python.exe`) y espera a que el servicio vuelva. Cerrar sólo la ventana de OPS **no** prueba esto: el backend es otro proceso | Al arrancar dice **«El anterior no se cerró limpio»**. No se perdió nada; vuelve a **Operativo**. (Una parada normal del servicio también puede decirlo mientras el gancho de cierre no corra: es informativo, D-18) |
| 2.5 | Con la clase cerrada, mira **Eventos apartados** | Vacío. Si hay alguno: cada línea dice qué evento y qué error, **sin datos de ningún alumno** |
| 2.6 | Sólo si hay un evento apartado, toca **Reprocesar** como administración | Se vuelve a aplicar una vez y queda anotado en la bitácora. (Un evento apartado exige un consumidor registrado en el proceso: hoy sólo se provoca con la suite de pruebas; sin él, `consumidor_sin_aplicador`) |
| 2.7 | Entra como **técnico** y repite 2.6 | Lo rechaza: necesita una escalada temporal de la administración |
| 2.8 | Atrasa la fecha de Windows más de un día y recarga | Aparece **Restringido** con el motivo de la fecha. Corrígela y vuelve a **Operativo** |

---

## 3 · Backups

> El respaldo lo opera **solo personal AVACOM** y no tiene pantalla en OPS: se usa por la API del nodo (`/api/respaldo/…`) con sesión de técnico y un **pase** firmado. Para las pruebas usa el nodo de pruebas y la llave de pase de prueba (`tools/respaldo/emitir_pase.py`).

### 3.1 Generar un backup

1. **Prepara:** con una clase de prueba, crea o deja **3 estudiantes con datos reconocibles** (nombre, un grupo, una nota o una respuesta). Anótalos.
2. **Haz:** pide primero la **hoja de custodia** (`POST custodia/emitir/` con pase `backup.schedule`). *Va antes del respaldo que vas a exportar: un respaldo hecho antes de emitir la custodia sale con `con_custodia: false` y no se puede restaurar en un equipo nuevo (prueba 3.3).*
3. **Debe pasar:** se muestra un código **una sola vez**. Guárdalo; lo necesitas en la prueba 3.3. Sin pase responde `pase_requerido`; pedirla otra vez sin `reemplazar` responde `custodia_ya_emitida` y no vuelve a mostrar el código.
4. **Haz:** pide un respaldo **completo ahora** (`POST respaldos/ahora/`). Hazlo con la **clase cerrada** (ver 3.2).
5. **Debe pasar:** queda **«Terminado y verificado»** (`completo_verificado`, `restaurable`, `con_custodia: true`). Se genera una **constancia** (`constancia-….txt`) en `Informes\` (`GET respaldos/<id>/constancia/` la devuelve).
6. **Haz:** pide el estado (`GET estado/`).
7. **Debe pasar:** `aviso_sin_respaldo` es `false`, y el estado no trae el código de custodia.
8. **Haz:** exporta el respaldo a la USB (`POST respaldos/<id>/exportar/` con `{unidad, pase}`; pase `backup.export`).
9. **Debe pasar:** aparece un archivo `.avbak` en `AVACOM\Respaldos\` de la USB. No se puede leer con el Bloc de notas. Sin pase, o con un pase ya usado, se niega (`pase_requerido` / `pase_invalido`).

### 3.2 Borrar datos y comprobar que el backup guardó a los estudiantes

1. **Haz:** con el respaldo ya verificado, **borra datos**: retira a los 3 estudiantes (`PATCH acceso/usuarios/<id>/` con `{"estado": "RETIRADO"}`, o desde OPS), o borra el contenido de la base de pruebas.
2. **Comprueba:** en OPS ya no aparecen (o la base está vacía).
3. **Haz:** con la **clase cerrada**, restaura ese respaldo (`POST restaurar/` con `{respaldo_id, motivo, pase}`; pase `backup.restore`). El `motivo` es obligatorio y es uno de `equipo_danado`, `equipo_nuevo`, `datos_danados`, `error_humano`, `prueba_de_recuperacion`, `otro`.
4. **Debe pasar:**
   - La respuesta dice qué se perdió (horas/eventos desde el respaldo) y no trae fallos.
   - Se genera el **informe de restauración**.
   - Hay que **volver a iniciar sesión** (se cerraron todas las sesiones).
5. **Comprueba:** los **3 estudiantes están de vuelta**, con su grupo, sus notas y sus respuestas, iguales a lo que anotaste en 3.1. Si el respaldo se hizo **con una clase abierta**, esa clase reaparece **abierta** (la base vuelve tal como estaba), la respuesta trae en `post.fallos` que el índice de búsqueda y los reportes no se reconstruyeron («Hay una clase en curso») y conviene reiniciar el servicio (`reinicio_recomendado`); por eso se respalda con la clase cerrada.
6. **Pruebas negativas:**
   - Intenta restaurar **con una clase abierta** → **se niega** y no gasta el pase.
   - Cambia un byte del `.avbak` y restaura → **aborta antes de tocar nada**.
   - Usa un pase vencido o ya usado → `pase_invalido`.

### 3.3 (Opcional) Equipo nuevo

1. **Haz:** en otro equipo con OPS instalada, restaura desde la USB **sin** el código de custodia.
2. **Debe pasar:** se niega con `409 restauracion_abortada` y `motivo: clave_no_disponible` («hace falta el código de custodia de la institución»); no toca nada. Con un código equivocado también se rechaza (`datos_invalidos`).
3. **Haz:** repite con la hoja de custodia (`custodia` en el cuerpo). El respaldo debe ser **posterior** a la emisión de la custodia (3.1, paso 2).
4. **Debe pasar:** restaura (`nueva_huella: true`: es otro equipo) y los estudiantes aparecen.

---

## 4 · Update Manager · hacer una actualización

> Prepara antes (en el equipo de emisión, sin internet): un paquete de prueba con `avacom-actualizacion plantilla`, `emitir` y `verificar` (ejemplo en `tools/actualizacion/ejemplo/paquete.json`), firmado con la llave de **prueba**. Cópialo a la USB, en la raíz o en `AVACOM\`. La serie del módulo debe ser **mayor** que la instalada.

| # | Haz | Debe pasar |
|---|---|---|
| 4.1 | **Sin clase abierta**, conecta la USB. OPS → **Actualizaciones** (como administración) | El paquete aparece en «Paquetes encontrados» |
| 4.2 | Toca **Importar** | Se ve el detalle: qué módulos cambian, peso, espacio libre y «compatible». Todavía no se cambió nada |
| 4.3 | Toca **Aplicar ahora** y confirma | El aula dice que se está actualizando. Tarda **3 a 5 minutos como máximo** |
| 4.4 | Mientras actualiza, intenta **iniciar una clase** | Responde «El aula se está actualizando; vuelve a intentarlo en unos minutos» |
| 4.5 | Espera el aviso | Estado **aplicado**. OPS vuelve a abrir y los datos (estudiantes, notas) siguen ahí. (Esto lo hace el **Host** real con el servicio parado: sin un equipo instalado, el nodo sólo deja la orden y el Host se simula escribiendo `resultado.json`) |
| 4.6 | Mira el historial de Actualizaciones y la Bitácora | Quedó anotado el paquete, la versión nueva y quién lo aplicó |
| 4.7 | Toca **Revertir**, elige un motivo y confirma | Estado **revertido**; vuelve la versión anterior con los mismos datos |

**Pruebas negativas (cada una con su propio paquete):**

| # | Haz | Debe pasar |
|---|---|---|
| 4.8 | Importa un paquete **con un byte cambiado** | Lo rechaza (firma) y **no guarda nada** |
| 4.9 | Importa un paquete con **serie menor o igual** a la instalada | Se importa pero queda **«incompatible»** (compatibilidad `ya_aplicado`) y **Aplicar** responde `409 ya_aplicado` sin escribir ninguna orden |
| 4.10 | Intenta **aplicar con una clase abierta** | No se aplica; avisa que hay una clase. No se corta la clase |
| 4.11 | Entra como **técnico** e intenta aplicar | Puede importar y ver, pero **no aplicar, programar ni revertir** (sólo administración): `403 sin_permiso` |

---

## Cierre

Marca al final:

- [ ] 1.1 A, B (y C si hubo OPS real) · 1.2 pasos 1 a 4
- [ ] 2.1 a 2.8
- [ ] 3.1 · 3.2 (los 3 estudiantes volvieron) · 3.3 opcional
- [ ] 4.1 a 4.11

**Reporta cada bug con:** número de prueba, qué hiciste, qué esperabas, qué pasó, captura y hora.

**Lo que esta guía no cubre** (sigue sin poder probarse sin hardware real): el asistente del instalador en una PC real elevada, la lectura del firmware de una OPS AVACOM en fábrica, Windows 10, y la copia exportada en memorias FAT32/exFAT reales.
