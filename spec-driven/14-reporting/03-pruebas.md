# 14 · Reporting (MOD-013) · Pruebas

| Campo | Valor |
|---|---|
| Estado | Verificado el **2026-10-15** sobre el código final, sin commit; el **Boletín Académico Individual** (2026-10-19) está en el [§5, punto 10](#5--lo-que-no-se-probó) y en [04-boletin-academico.md](04-boletin-academico.md). Lo que **no** se pudo comprobar está en el [§5](#5--lo-que-no-se-probó): léelo antes de dar el módulo por cerrado. |
| Qué dice cada documento | Diseño y decisiones: [01-diseno.md](01-diseno.md) · contrato de la API: [02-api.md](02-api.md) · capturas: [capturas/](capturas/). |

## 1 · En una mirada

| Qué | Resultado |
|---|---|
| Backend · **toda** la suite (`manage.py test`, todas las apps) | **1864 pruebas, OK** (7 omitidas: las de siempre, no son de este módulo; es la compuerta de `Build-Installer.ps1`, que la corre completa antes de empaquetar) |
| Backend · app `reporting` | **164 pruebas, OK** (1 omitida: la captura de contrato, que sólo corre con `AVACOM_CAPTURAR_CONTRATO`) |
| Core (`dotnet test`) | **1190 OK** (380 son de MOD-013) |
| OPS (`dotnet test`) | **389 OK** (257 son de MOD-013) |
| Student (`dotnet test`) | **102 OK** (sin cambios: MOD-013 no tiene pantallas de alumno) |
| Compilación de OPS y de Student para Windows | **0 errores, 0 advertencias** |
| Instalador **2.8.0** (`installer/latest`) | **Construido y ensayado de punta a punta** (`Ensayar-Paquete.ps1`: instalación nueva, primer arranque, actualización con datos desde la 2.7.0 y migración que falla). Dentro van `Backend\reporting` (49 archivos idénticos a los del repositorio), `acceso 0017` y el OPS con la exportación; en el nodo empaquetado `/api/reportes/clases/` responde 401 (sesión obligatoria). **No** se instaló en un equipo de aula (§5, punto 9) |
| Verificación en vivo con UI Automation, capturas y «memorias» simuladas | **Hecha** (§4): lectura, roles, privacidad, política, exportación completa y todos sus fallos |
| Contra una memoria USB **física**, FAT32/exFAT, carpeta de red real, antivirus real, Android | **No** (§5) |

## 2 · Qué cubre cada suite

**Backend** (`backend/reporting/tests/`, 164 pruebas):

| Archivo | Pruebas | Qué comprueba |
|---|---|---|
| `test_arquitectura.py` | 21 | Reporting nunca lee ni escribe las tablas de otro módulo (BR-085) y sus fuentes sólo leen; **toda** tabla `m13_*` es derivada o propia, nunca las dos; ninguna columna guarda títulos ni nombres (art. 14) ni sale una clave foránea del módulo; `dominio/` y `aplicacion/` no importan Django ni conocen a otros módulos y las dependencias apuntan hacia adentro; **nada habla con internet** (BR-084) y la capa de biblioteca no se toca (sólo `arbol.py` habla con ella); los ocho permisos, el reparto por rol, las acciones de bitácora y los eventos son los del catálogo. |
| `test_dominio.py` | 39 | Porcentajes con `Decimal` y por puntos, «sin dato = null, nunca cero»; criterios de «necesita atención»; estado de integración y caducidad de sus señales; umbral de privacidad; nombres de archivo seguros; el documento exportable. |
| `test_proyeccion.py` | 21 | El consumidor: idempotencia, marca de lectura, `rezagada` derivada, **reconstruir borra todo lo derivado y vuelve a dejarlo idéntico** (BR-007) sin tocar lo propio, no se reconstruye con una clase abierta (409) y una reconstrucción que falla no queda a medias. |
| `test_clase.py` | 14 | El reporte de la clase (TST-008): participación y aciertos por alumno, promedio, tableta al cerrar, «Incompleto», clase en curso (409), alumno que no fue. |
| `test_grupo_alumno_uso.py` | 30 | Grupo (atención primero, modo simple/calificaciones), informe del alumno (nota ya resuelta por el libro), uso de equipos sin personas, filtros por nodo con la biblioteca viva o cerrada, **permisos por rol y alcance** (otro profesor, técnico: 403 con asiento), umbral de privacidad, recientes. |
| `test_exportacion.py` | 38 | Alcance declarado (sin efectos), política de destinos y razón, **dos tiempos** (autorizar → confirmar), huella releída, `fallido` que no cierra, caducidad, XLSX bien formado (zip, XML de cada parte, números como números, filtros), CSV (BOM, `;`, coma decimal, neutraliza fórmulas), reporte de 3000 filas sin cargarlo entero, **nada de rutas, nombres de archivo ni contenido en la auditoría**, y de dónde sale la «Versión del nodo» del archivo (el manifiesto del instalador, `installer/version.json` o «desarrollo»). |
| `test_capturar_contrato.py` | 1 | Captura las respuestas **reales** del backend a `tests/Avacom.Lms.Core.Tests/Fixtures/reportes/` (37 archivos) para que Core pruebe contra ellas. Sólo escribe con `AVACOM_CAPTURAR_CONTRATO=1`. |

**Core** (`tests/Avacom.Lms.Core.Tests/`): `ContratoReportesTests` (33, lee las respuestas reales capturadas), `ReportesApiTests` (26: descarga **en streaming** a un temporal con SHA-256 incremental, cancelación que no deja temporales, errores como `UltimoError`), `ReportesTextoTests` (87: cifras, fechas, estados vacíos, mensajes), `MotivosDeEscrituraTests` (103: de cada excepción de E/S de Windows al motivo y al texto accionable) y `NombreDeArchivoTests` (131: FAT32/exFAT, nombres reservados, rutas de red).

**OPS** (`tests/Avacom.Lms.Ops.Tests/`, sin MAUI: compila los mismos archivos del equipo del aula): `DestinosTests` (82: unidades, atajos, política, clasificación extraíble/red, vigilante), `EscrituraSeguraTests` (86, con un sistema de archivos falso que **retira la unidad, llena el disco, protege contra escritura, se cae a mitad, bloquea por antivirus** y comprueba que nunca queda un archivo a medias ni se sobrescribe), `FlujoDeExportacionTests` (36: el archivo bajado se reutiliza al cambiar de destino, caduca, se re-autoriza si cambia el formato, confirma con la huella releída, reintenta la confirmación) y `ReportesLogicaTests` (53: quién entra, fichas de periodo, rutas, listas, árbol de nodos, textos de la confirmación y **qué botones ofrece cada fallo**).

## 2b · Reglas y casos del Maestro

El Maestro le da a MOD-013 un solo escenario (TST-008); las reglas son las que manda el prompt. Cada una, con la prueba que la sostiene y dónde se vio en vivo:

| Regla o caso | Prueba | En vivo |
|---|---|---|
| **TST-008** clase cerrada hace 5 minutos → 25 filas y promedio | `test_clase.py::test_tst_008_clase_cerrada_hace_cinco_minutos_da_25_filas_y_el_promedio` | §4 filas 4 y 5 (6 estudiantes, promedio abajo) |
| **BR-007** borrar todo lo derivado y reconstruir devuelve los mismos reportes | `test_proyeccion.py::test_br007_…` (por la ruta y borrando las tablas), `test_borrar_lo_derivado_no_toca_lo_propio`, `test_si_la_reconstruccion_falla_no_queda_a_medias` | «Reconstruir» sólo a la administración y 409 con una clase en curso (`test_no_se_reconstruye_con_una_clase_abierta`) |
| **BR-083** todo reporte y todo archivo declara su corte y su integración | `test_dominio.py::test_la_cabecera_lleva_lo_que_exige_br_083…`, `test_clase.py::test_el_reporte_declara_su_corte_y_el_estado_de_integracion`, `test_exportacion.py::ArchivoTests` (el xlsx y el csv traen la cabecera dentro) | §4 filas 4, 5, 14 (Excel real) |
| **BR-084** nada habla con internet | `test_arquitectura.py::test_br_084_nada_del_modulo_habla_con_internet` y `test_el_escritor_de_archivos_usa_solo_la_biblioteca_estandar` | — (el nodo de pruebas ni tiene salida) |
| **BR-085** Reporting no escribe datos académicos | `test_arquitectura.py::test_br_085_…` (tablas ajenas, fuentes de sólo lectura) y `test_las_escrituras_del_modulo_son_solo_de_sus_tablas` | — |
| **BR-085 / TST-069** el técnico no lee datos académicos: 403 y asiento | `test_clase.py::test_tst_069_el_tecnico_no_lee_datos_academicos_y_queda_asiento`, `test_grupo_alumno_uso.py` (alcance y roles), `test_proyeccion.py::test_solo_administracion_y_tecnico_reconstruyen` | §4 fila 13: 403 en clase, grupo y alcance, con 4 asientos |
| **BR-086** menos de 5 alumnos con el umbral activo → sólo el agregado, también en el archivo | `test_grupo_alumno_uso.py::UmbralDePrivacidadTests`, `test_exportacion.py::test_el_umbral_de_privacidad_aplicado_va_dentro_del_archivo` | §4 fila 8 |
| **Art. 14** ni títulos ni nombres guardados | `test_arquitectura.py::test_articulo_14_…` y `test_el_detalle_y_las_filas_no_traen_titulos_ni_nombres`; `test_clase.py::test_los_rotulos_del_aula_se_piden_al_mostrar_y_no_se_guardan` | — |
| Exportar en dos tiempos, caducidad, política y razón; sólo quien la pidió la confirma | `test_exportacion.py::DosTiemposTests` (incluye `test_solo_quien_la_pidio_la_confirma_ni_siquiera_se_sabe_que_existe`), `PoliticaDelAdministradorTests`, `QuienPuedeExportarTests` | §4 filas 14 a 19 |
| Nombre de archivo seguro (FAT32/exFAT) y sin personas | `test_dominio.py` (nombres), `test_exportacion.py::test_el_nombre_del_archivo_nunca_lleva_el_nombre_de_una_persona`, `NombreDeArchivoTests` (Core) | §4 fila 14 |
| Asientos de auditoría sin ruta, nombre ni contenido | `test_exportacion.py::test_ni_la_ruta_ni_el_nombre_ni_el_contenido_llegan_a_la_bitacora_ni_a_las_tablas` | §4 fila 22 |
| La «Versión del nodo» del archivo es la del instalador | `test_exportacion.py::VersionDelNodoTests` (manifiesto del instalador → `installer/version.json` → «desarrollo») | — |

## 3 · La escena de datos

Se siembra con lo que está en el repo, por la API, igual que lo harían OPS y Student (las credenciales de prueba están en esos scripts; no se repiten aquí):

```bash
# nodo aislado (nunca el del aula): base temporal, host de contenido de pruebas, puerto 8010
AVACOM_LMS_DB=%TEMP%\rp.sqlite3 AVACOM_AULA_PERMITIR_EJEMPLO=1 AVACOM_LMS_EXIGIR_SESION=0 python manage.py migrate
python -m tools.host_contenido_v2_con_examenes %TEMP%\link-pruebas.json          # y AVACOM_CONTENIDO_ENLACE_V2=%TEMP%\link-pruebas.json
python manage.py runserver 127.0.0.1:8010 --noreload
python tools/sembrar_gradebook.py --base http://127.0.0.1:8010 > semilla-gradebook.json
python -m tools.sembrar_reportes   --base http://127.0.0.1:8010 --semilla semilla-gradebook.json
python -m tools.sembrar_reportes   --base http://127.0.0.1:8010 --semilla semilla-gradebook.json --solo-roles   # otro profesor (9B), técnico y Reportes
# después se reinicia el nodo con AVACOM_LMS_EXIGIR_SESION=1 y la misma base para probar con sesiones de verdad
```

Queda: **8A** (7 estudiantes, modo calificaciones, escala Colombia 1–5), **P1** (2 estudiantes, modo simple), **9B** (del otro profesor); dos clases cerradas de 8A —una **completa** (6 estudiantes: 5/5, 4/5, 1/5, 5/5, 3/5, 5/5; Eva no fue) y una **incompleta** (una tableta que perdió la conexión al cerrar)—; una tarea de estudio y una evaluación por grupo.

## 4 · Verificación en vivo

**Cómo.** Nodo aislado en `127.0.0.1:8010` con **sesión obligatoria** (JWT de verdad por rol); OPS compilada del código final y lanzada con el **perfil de pruebas** (`AVACOM_OPS_PERFIL`: no toca las preferencias ni la clase guardada de quien usa el equipo); `tests/Avacom.Lms.Ops.Uia/ui-ops.ps1` (lista controles, toca botones por su `AutomationId`, marca el PIN con el teclado propio, captura sólo el área de la página con `PrintWindow`) y `tercios.ps1` (cuadrícula de tercios sobre la captura). Sin memoria USB física: dos «memorias» con letra de unidad (`subst X:` escribible y `subst Y:` con un permiso de denegar escritura) que la hoja ve como **extraíbles** por un gancho que sólo existe con el perfil de pruebas (`AVACOM_OPS_UNIDADES_PRUEBA`), y otro que **enlentece la escritura** (`AVACOM_OPS_ESCRITURA_LENTA_MS`) para poder ver el avance, cancelar a mitad y «retirar» la memoria (`subst X: /D`) mientras se guarda. Para el filtro por materia, el nodo leyó (sólo lectura) la **AVACOM Contenido real** instalada en el equipo.

| # | Escenario | Resultado | Captura |
|---|---|---|---|
| 1 | El menú del profesorado trae la tesela «Reportes» | Sí. **Su toque no se pudo automatizar** (la tesela es un grupo sin patrón de invocación para UI Automation): se probó la ruta `reportes` y se leyó el `case "Reportes"` del código | [00](capturas/00-menu-principal-con-reportes.png) |
| 2 | Inicio: tres tarjetas y «Recientes» | Cada tarjeta en su tercio de X y de 1/6 a 5/6 de Y; los recientes se distinguen entre sí | [01](capturas/01-inicio-tercios.png) · [01b](capturas/01b-inicio-con-recientes-tercios.png) |
| 3 | Elegir clase | Más reciente primero, con grupo y filtro de materia | [02](capturas/02-elegir-clase.png) |
| 4 | Reporte de una clase **completa** | 6 estudiantes, barras desde cero, promedio, «Integración completa», «Dominio por objetivo: Aún no disponible» | [03](capturas/03-clase-completa.png) |
| 5 | Reporte de una clase **incompleta** | «Incompleto» en ámbar con su motivo, «Sin conexión al cerrar» y **«—»** (no 0) donde no hay aciertos | [04](capturas/04-clase-incompleta.png) |
| 6 | Grupo | **Primero quién necesita atención**, con su motivo; luego todos | [05](capturas/05-elegir-grupo.png) · [06](capturas/06-grupo-8A.png) |
| 7 | Estudiante | Evaluación con la nota que ya resolvió el libro (3,8 · Básico), estudio y clases | [07](capturas/07-elegir-estudiante.png) · [08](capturas/08-informe-de-estudiante.png) |
| 8 | **Privacidad (BR-086)** con el umbral activo y un grupo de 2 | Sólo totales, sin lista de personas, y lo dice; en el CSV exportado no hay nombres y «necesitan atención» queda vacío | [09](capturas/09-privacidad-grupo-chico.png) · [32](capturas/32-exportar-confirmar-privacidad-csv.png) |
| 9 | Uso de equipos | Sin datos de personas; periodo por fichas | [10](capturas/10-uso-de-equipos.png) |
| 10 | Estado y ajustes (administración) | Las cuatro fuentes al día; los tres ajustes **se cambian tocando y el nodo los recibe** (versión 2 → 7 en la prueba) | [11](capturas/11-estado-y-ajustes.png) · [12](capturas/12-ajustes-de-administracion.png) |
| 11 | El nodo se cae con un reporte abierto | Se queda lo último leído y avisa «Sin conexión con el aula…» | [13](capturas/13-sin-conexion.png) |
| 12 | **Filtro por materia con la biblioteca real** | El árbol real (Colombia, Estados Unidos…) baja hasta Ciencias naturales › Sexto; deja **1 de las 3 clases** (la que está sobre el curso real); Estados Unidos deja ninguna y lo explica. Por la API: grupo sin filtro 3 clases · con filtro 1 · EE. UU. 0, sin avisos | [14](capturas/14-filtro-materia-biblioteca-real.png) · [15](capturas/15-filtro-sin-clases-de-esa-materia.png) |
| 13 | **Roles** | Reportes ve «Uso de equipos»; el **técnico** ve «Este rol no accede a los reportes» y por la API recibe **403 `sin_permiso`** en clase, grupo y alcance de exportación (y **200** en uso, que no lleva personas) con **4 asientos** `reporte.acceso_denegado` (TST-069); otro profesor ve **sólo su 9B** y por la API recibe **403 `fuera_de_alcance`** en todo lo del 8A (clase, grupo, lista de estudiantes, informe de un estudiante, alcance y generación de exportaciones), **403 `sin_permiso`** en uso, configuración y reconstruir, y **404** si intenta leer o confirmar una exportación ajena; sus recientes quedan vacíos | [16](capturas/16-inicio-rol-reportes-tercios.png) · [17](capturas/17-tecnico-sin-acceso-tercios.png) · [18](capturas/18-otro-profesor-solo-su-grupo.png) |
| 14 | **Exportar, camino feliz** | Formato → destino (unidades con etiqueta, letra y espacio libre; atajos; «Elegir otra carpeta…») → confirmación con el alcance declarado y la advertencia de nombres → guardando → «Guardado en X:\…xlsx · 6,5 KB». **El SHA-256 del archivo en la unidad = la huella del nodo = la huella que OPS releyó.** El zip es válido y **Excel real** lo abre: hojas Resumen, Alumnos, Clases y Evaluaciones, con filtros y la cabecera de BR-083 | [20](capturas/20-exportar-elegir-tercios.png) · [21](capturas/21-exportar-confirmar-tercios.png) · [22](capturas/22-exportar-guardando.png) · [23](capturas/23-exportar-guardado-tercios.png) |
| 15 | Cancelar a mitad | «Cancelaste el guardado. No se guardó nada.»; **ningún `.parte` ni archivo a medias** en la unidad; el nodo anota `fallido · cancelado` y la exportación sigue abierta | [24](capturas/24-exportar-cancelado.png) |
| 16 | Memoria protegida (permiso negado) | «No tienes permiso para guardar en esa carpeta…» con «Elegir otro destino» (no hay «Guardar otra vez»: repetir no lo arregla) | [25](capturas/25-exportar-fallo-sin-permiso.png) |
| 17 | **Memoria retirada a mitad de la escritura** | «Se retiró la memoria mientras se guardaba. Vuelve a conectarla y toca Guardar otra vez, o elige otro destino.» con **esos dos botones**; al reconectarla y tocar «Guardar otra vez» queda guardado. En el nodo, **una sola autorización con tres intentos** (`fallido·sin_permiso`, `fallido·medio_retirado`, `guardado`) y la misma huella: el archivo **no se generó de nuevo** | [26](capturas/26-exportar-memoria-retirada.png) · [27](capturas/27-exportar-guardar-otra-vez-listo.png) |
| 18 | **La política cambia con la hoja abierta** | El administrador apaga las memorias USB; al guardar, el aula rechaza (`destino_no_permitido`); «Elegir otro destino» **vuelve a leer la política** y ya no ofrece las memorias, con su aviso | [28](capturas/28-exportar-politica-cambio-rechazo.png) · [29](capturas/29-exportar-politica-elegir-de-nuevo.png) |
| 19 | **Razón exigida** | Las razones son fichas (nadie escribe); «Continuar» espera a que se elija; la confirmación dice el motivo y el nodo lo guarda (`razon_codigo`). Sin razón, por la API: **400 `razon_requerida`** | [30](capturas/30-exportar-pide-razon.png) · [31](capturas/31-exportar-confirmar-con-motivo.png) |
| 20 | **Cambiar de clase de destino** (D-29) | Una memoria que falla por permiso y luego un disco local: el nodo recibe una **segunda autorización** («carpeta_local»), el archivo se guarda y su SHA-256 coincide con la huella del nodo | — |
| 21 | **El técnico en `/filtros/`** (D-30) | Recibe los tres grupos con `alumnos` y `en_atencion` en `null`; el profesor recibe 7 y 4 en el 8A. Un código de materia inválido (`A`×65, con espacio, con `/`) da **400 `datos_invalidos`** | — |
| 22 | Auditoría | Quedan `reporte.generado`, `reporte.exportacion_autorizada`, `reporte.exportado`, `reporte.configuracion_cambiada` y `reporte.acceso_denegado`; la prueba automática comprueba que **no** llevan ruta, nombre de archivo ni contenido | — |

## 5 · Lo que NO se probó

1. **Una memoria USB física.** Los códigos de error que devuelve cada dispositivo real al retirarse o llenarse se clasifican con una tabla (`MotivosDeEscritura`); si aparece uno que no está, sale «No se pudo guardar el archivo» y el registro local anota el código completo (sin rutas) para ampliarla. Lo probado en vivo es una carpeta con letra de unidad que se «retira» con `subst X: /D`.
2. **FAT32, exFAT y red.** La verificación relee del destino **sin caché** (`FILE_FLAG_NO_BUFFERING`); no se comprobó que esa lectura llegue al dispositivo en esos sistemas. Tampoco se probó una **carpeta de red real** (sólo su clasificación, en las pruebas).
3. **Un antivirus real** que ponga en cuarentena el archivo (el caso está en las pruebas con un sistema de archivos falso).
4. **«Abrir carpeta»** tras guardar y **«Elegir otra carpeta…»** (el selector de carpetas nativo de Windows): no se pulsaron. Abren una ventana del sistema sobre el escritorio de quien usa el equipo y UI Automation no las maneja; lo que sí se probó son las piezas de después: cómo se clasifica una ruta (extraíble, red o local) en `DestinosTests` y la escritura segura en `EscrituraSeguraTests`.
5. **El toque sobre la tesela «Reportes»** del menú (§4, fila 1).
6. **Un cierre brusco** (matar OPS a mitad): el temporal `.parte` se borra al siguiente arranque si tiene más de 20 minutos; no se mató el proceso a propósito.
7. **Exportar ≥ 1000 filas en la pantalla.** Lo cubren las pruebas automáticas (3000 filas escritas por bloques en el backend; archivo grande por bloques con avance en OPS); en vivo los grupos de prueba tienen ≤ 10 filas.
8. **Android.** MOD-013 no tiene pantallas en Student; sólo se compiló Windows (OPS y Student).
9. **La instalación real.** OPS se probó compilada en una carpeta de pruebas con el perfil de UI Automation, no desde el instalador. El instalador 2.8.0 está en `installer/latest` (15 de octubre de 2026, SHA-256 `98672194C1CD9EE84B1ED0DE7FDEF34FA4765F23628E17FFBB8B198246A189E5`): salió de la misma compilación que MOD-011 (política de datos `protegidos`), con la suite completa del backend en verde y un ensayo del paquete que comprueba que `/api/reportes/clases/` exista y pida sesión. Pero **nadie ha instalado ese `.exe` en un equipo de aula** ni ha exportado un reporte desde esa instalación: la exportación a archivo sólo se vio con OPS compilado en la carpeta de pruebas.
10. **El Boletín Académico Individual (2026-10-19, D-32 a D-37).** Backend: `reporting/tests/test_boletin.py` (22 pruebas: elección de plantilla por país, nivel y configuración —México Secundaria en disciplinas, preescolar sin cifras—, desempeño nacional, modelo común con las cuatro preguntas, boletín de un estudiante y del grupo con permisos y alcance, exportación por estudiante en xlsx/csv y del grupo como **zip con un archivo por estudiante**, configuración con plantilla, periodos y leyenda validados) más la arquitectura con el evento `reporte.boletin_generado.v1`; la pasada completa de `gradebook reporting audit`: 510 OK (3 omitidas). C#: contrato con las respuestas reales (`boletin`, `boletines`, `*_alcance`, `configuracion_boletin`, `recientes_boletin`), `ReportesApiTests` (el grupo se pide sin alumno y llega como zip) y las rutas de recientes; Core 1221, OPS 399. **No** se probó: ninguna pantalla en ventana (la tarjeta «Boletín académico», la lista de grupos, las dos páginas del boletín, la hoja de exportar con el zip ni los ajustes de plantilla y periodos), la escritura real del zip en una memoria, el boletín con AVACOM Contenido real (los nombres de materia salen del árbol de la biblioteca), ni ninguna de las plantillas contra las tres del XLSX del CTO, que no llegó.

## 6 · Revisión independiente

Un revisor sin el contexto de quien escribió el código (un agente aparte, **sólo lectura**, con las reglas del módulo y la lista de lo ya probado) leyó la exportación completa —backend, cliente y escritura segura— y buscó saltos de autorización, fugas con la privacidad activa, escrituras fuera de la carpeta, temporales que se quedan y datos personales en mensajes. **No encontró** saltos de autorización con sesión, ni fuga de nombres con el umbral aplicado, ni escritura fuera de la carpeta o sobrescritura. Sí encontró lo siguiente; se corrigió todo salvo lo marcado:

| # | Hallazgo | Qué se hizo |
|---|---|---|
| 1 | BR-085: el técnico leía `en_atencion` (y `alumnos`) por grupo en `GET /filtros/` | Recibe los grupos para filtrar el uso y **ninguna cifra** (`null`). Prueba y comprobado en vivo (D-30) |
| 2 | Con la hoja cerrándose a mitad de la escritura, el borrado del temporal fallaba en silencio y quedaba un `.parte` con nombres de alumnos hasta el próximo arranque | El temporal se abre con `FileShare.Delete`, el borrado se reintenta y se termina al acabar la escritura. **La prueba falla con el código anterior** (se comprobó quitando el arreglo) (D-31) |
| 3 | El detalle técnico de un fallo de escritura no se anotaba en ningún lado, aunque el diseño lo prometía | Se anota en el registro local —que lo entrega al nodo— **sin rutas ni el nombre de usuario de Windows** (D-31) |
| 4 | OPS reutilizaba el archivo autorizado para otra clase de destino: con las memorias cerradas por el administrador, una carpeta del equipo que fallaba y luego una memoria USB saltaban la política | Cambiar de clase de destino vuelve a pasar por el nodo. En vivo: **dos autorizaciones** (la de la memoria, que falló, y la del disco local, entregada) (D-29) |
| 5 | Los códigos del árbol académico se guardaban sin validar, también en recientes y en el asiento encadenado de la bitácora | Se validan (código de hasta 64 caracteres o `400 datos_invalidos`) (D-30) |
| 6 | El identificador de la exportación daba nombre al temporal sin validarse (`..\..\x` desde una cabecera manipulada) | Tiene que ser un código, nunca una ruta (D-31) |
| 7a | Ponerse al día antes de exportar podía volverse un 500 por «database is locked» en plena clase | Igual que en cada reporte: se sigue con lo que hay |
| 7b | Una unidad de red **mapeada** (`Z:`) que se caía salía como «se retiró la memoria» | El sistema dice que es de red: «no se pudo llegar a esa carpeta de red» |
| 7d | El asiento de una denegación sin sesión (sólo desarrollo) salía sin quién | Sale del cuerpo de la petición |
| 7c | Sin tope de intentos fallidos por exportación | **No se cambió:** cada intento es una petición autenticada del mismo profesor durante 15 minutos, como cualquier otra ruta auditada |
| 7e · 7f | Un `.parte` huérfano en el destino si el proceso muere; un `FileResponse` síncrono bajo ASGI | **Aceptados:** el primero está documentado (§5, punto 6) y el segundo sólo afecta a archivos de unos KB o pocos MB |

**Revisado y correcto**, sin hallazgos: el alcance y la autorización de alcance, autorizar, confirmar, ver y listar (lo ajeno responde 404 igual que lo inexistente); BR-086 en el cuerpo, el nombre del archivo, las cabeceras y la auditoría; los escritores XLSX y CSV con emoji, caracteres de control, `&<>"'`, `]]>`, textos de 40 000 caracteres y cadenas que empiezan por `=`, `+`, `-`, `@` (las 8 partes del xlsx son XML bien formado; los textos van como cadenas en línea y nunca son fórmula; el CSV antepone `'`); `NombreDeArchivo.Sanear` con 33 nombres hostiles (`..\..\x`, `C:\x`, `a:b`, `CON`, `COM¹`, puntos y espacios finales, más de 300 caracteres…); `EscrituraSegura` con la lógica real (un archivo existente se conserva y el nuevo sale como `(2)`, tamaños 0, 1, 4095/4096/4097 y 5 MiB verifican bien con lectura sin caché en NTFS, tras un hash malo o una cancelación no queda `.parte`); y en OPS que cada botón pasa por `ReportesUi.Seguro`, que los ganchos de prueba dependen sólo de `AVACOM_OPS_PERFIL` y que la cancelación de la bajada limpia el temporal.

## 7 · Lo que encontró la pasada final en vivo (y ya está corregido)

| Qué se vio | Qué se hizo |
|---|---|
| Las frases de fallo decían «toca Guardar otra vez» y la hoja no tenía ese botón | D-25: los botones son los que nombra la frase; la decisión es una función pura con pruebas |
| «No hay clases en este periodo · Elige otro periodo» con un filtro de materia puesto | D-28: la lista vacía dice por qué |
| El archivo de un grupo con privacidad decía «0 necesitan atención» mientras la pantalla ponía «—» | D-26: la celda queda vacía |
| Tres «Grupo 8A» en Recientes que no se podían distinguir | D-27: el título dice «con filtro de materia» o «desde <fecha>» |
| La tabla de clases del estudiante terminaba a mitad de ancho | Su primera columna ocupa el resto, como las otras dos tablas |
| El «Incompleto» de una clase se apagó solo a los 15 minutos | Es el diseño de D-5 (criterio propio), pero **queda como pregunta para el CTO** (§9 de 01-diseno.md, punto 10) |

## 8 · Cómo repetirlo

```bash
cd backend && python manage.py test                      # todo el backend
cd backend && python manage.py test reporting            # sólo este módulo
dotnet test tests/Avacom.Lms.Core.Tests                  # Core
dotnet test tests/Avacom.Lms.Ops.Tests                   # OPS
dotnet test tests/Avacom.Lms.Student.Tests               # Student
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -p:OutDir=<carpeta>/   # OPS para Windows, fuera del árbol de bin/
# volver a capturar las respuestas reales para Core (sólo si cambió el contrato):
AVACOM_CAPTURAR_CONTRATO=1 python manage.py test reporting.tests.test_capturar_contrato
```

En vivo: la escena de §3, OPS con `AVACOM_OPS_PERFIL=<nombre>`, `AVACOM_OPS_SERVIDOR=http://127.0.0.1:8010`, `AVACOM_OPS_RUTA=reportes` (o `reporte-grupo?grupo=<id>`), `AVACOM_OPS_UNIDADES_PRUEBA='X:\|MEMORIA|extraible|15032385536|16106127360;Y:\|SOLO LECTURA|extraible|1000000000|2000000000'` y `AVACOM_OPS_ESCRITURA_LENTA_MS=8000`; y `tests/Avacom.Lms.Ops.Uia/ui-ops.ps1` para tocar y capturar.
