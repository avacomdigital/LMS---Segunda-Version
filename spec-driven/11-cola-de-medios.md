# 11 · Cola de medios (caché y reparto de recursos en la LAN)

> Estado: construida el 2026-10-08 · app `backend/cola_medios` · tablas `cm_*` · rutas `/api/medios/cola/` · instaladores 2.5.0.
> Atiende a MOD-007 (aula), MOD-008 (modo estudio) y MOD-010 (evaluación). Ninguno cambia lo que responde: sólo de dónde salen los bytes.

## 1. El problema

Los videos, audios, imágenes, PDF y páginas html de un curso los sirve **AVACOM Contenido** (la biblioteca), por loopback, al nodo. Hasta ahora el nodo los
pasaba **en paso a través**: cada petición de una tableta abría una conexión a Contenido y reenviaba el flujo. Con 35 tabletas pidiendo el mismo video:

- Contenido servía el mismo archivo 35 veces (y una sesión de medios por trozo `Range`, ver `contenido_v2._sesion_de_medio`).
- Nadie regulaba cuántas transferencias iban a la vez ni a qué ritmo.
- Preparar un paquete de estudio leía **entero** cada medio para medirlo y calcular su SHA-256, **por alumno**: 35 alumnos, 35 lecturas.
- Bajo Daphne, Django consume un generador **síncrono** entero en memoria antes de enviar el primer byte (`StreamingHttpResponse.__aiter__`): un video de 300 MB
  pedido con `Range: bytes=0-` se cargaba completo en RAM por cada tableta.

## 2. Qué se hizo

```
 tableta ──GET/HEAD+Range──►  vista del módulo (aula · estudio · evaluación)         ← la autorización sigue siendo de cada módulo
                                       │
                                       ▼
                             cola_medios.servicio.abrir_medio(..., directo=<paso a través de siempre>)
                                       │
            ┌──────────────────────────┼───────────────────────────────┐
            ▼                          ▼                               ▼
     ¿está en la caché?        ¿lo están bajando?               no está: se pone en la COLA
     sirve de disco/memoria    SIGUE esa descarga               (prioridad de quien lo pide)
            └──────────────┬───────────┴──────────────┬────────────────┘
                           ▼                          ▼
                   RespuestaLocal (Range)     si no llega a tiempo, o la cola falla → `directo()`
                           │                          (nunca empeora lo que había)
                           ▼
              cuerpo ASÍNCRONO por trozos · cupo de transferencia · tope de ancho de banda
```

### 2.1 Piezas (hexagonal, como el resto del repo)

| Capa | Archivo | Qué hace |
|---|---|---|
| dominio | `dominio/catalogos.py` | estados (`pendiente · descargando · disponible · fallido · cancelado`), prioridades, módulos, motivos de fallo |
| | `dominio/clave.py` | `ClaveMedio(fuente, curso_ref, media_ref, ruta)` → huella SHA-256 de la clave |
| | `dominio/rangos.py` | `Range` de HTTP: `a-b`, `a-`, `-n`, 416; lo ilegible se ignora |
| | `dominio/ritmo.py` | cubo de fichas (ancho de banda) y cupos (transferencias a la vez) |
| | `dominio/politica.py` | a quién expulsar (el menos usado; no lo que se lee ni lo reciente) |
| | `dominio/referencias.py` | qué `media_ref` usa un objeto de la vista de aula |
| aplicación | `aplicacion/servidor.py` | `abrir`, `preparar`, `medir`, `cancelar`, `reintentar`, `mantenimiento`, `estado` |
| | `aplicacion/planificador.py` | la **cola ligera en memoria**: prioridad + orden de llegada; un hilo reservado a lo urgente |
| | `aplicacion/descargador.py` | baja un recurso: `Range` para reanudar, SHA-256 al vuelo, hace sitio, reintenta |
| | `aplicacion/respuesta.py` | `RespuestaLocal`: se parece a una respuesta `urllib` y sabe **seguir una descarga en curso** |
| | `aplicacion/almacen.py` | el disco: `objetos/<aa>/<id>.bin` y el conteo de lectores |
| infraestructura | `registro.py` · `memoria.py` · `origen.py` · `difusion.py` · `http.py` · `programador.py` · `contenedor.py` | ORM, **LocMemCache**, fuente (casos de uso del aula), aviso WebSocket, respuesta HTTP, hilos, composition root |
| interfaces | `interfaces/views.py` · `urls.py` | `/api/medios/cola/…` |
| puerta | `servicio.py` | lo único que importan los tres módulos |

### 2.2 Dónde se guarda qué

| Dato | Dónde | Por qué |
|---|---|---|
| Estado de cada recurso (`pendiente…cancelado`), progreso, SHA-256, error, quién lo pidió | **base de datos** (`cm_recurso`, `cm_solicitud`) | sobrevive a un reinicio: lo que quedó a medias se **reanuda** |
| Los bytes | **disco** (`AVACOM_COLA_DIR`) | un video no cabe en RAM |
| Índice caliente, medios ≤ 256 KB (subtítulos, js, css, iconos), versión vigente de cada curso | **`LocMemCache`** (alias `medios`) | evita ir a la base o al disco en cada trozo de cada tableta |
| Tareas vivas, cupos, cubos de ancho de banda | memoria del proceso | el nodo es un solo proceso |

La caché es **regenerable**, no expediente: expulsar un recurso borra su fila y la próxima petición lo vuelve a traer. No hay ninguna tabla ni columna de
curso, pregunta ni clave de respuesta (artículo 14); `tests/test_arquitectura.py` lo comprueba.

## 3. Reglas de diseño (y por qué)

1. **La cola nunca le cuesta un medio a nadie.** Cualquier cosa que no pueda hacer a tiempo —o que falle— se resuelve sirviendo en paso a través, como antes.
   Los clientes tienen poca paciencia (el audio se rinde a los 10–12 s sin datos, la imagen a los 10 s; la descarga de paquetes trata un 503 como fallo), así que
   la cola **no responde 503 por carga**: espera `AVACOM_COLA_ESPERA_INICIO_SEG` (6 s) a que el recurso empiece a llegar y, si no, `directo()`.
2. **Una sola descarga por recurso.** 35 tabletas que piden el mismo video comparten una tarea; todas leen el mismo archivo mientras crece (`RespuestaLocal`
   espera a que lleguen los bytes que le faltan). Un salto a más de 32 MB de lo ya descargado se sirve directo (la descarga sigue).
3. **El curso y la autorización siguen siendo de AVACOM Biblioteca.** Antes de servir una copia se le pregunta (cada 60 s, `LocMemCache`) si el curso
   se sigue ofreciendo y en qué versión: curso retirado o apagado por política → 404 como siempre; biblioteca cerrada → 503 como siempre (salvo
   `AVACOM_COLA_SERVIR_SIN_BIBLIOTECA=1`); versión nueva → se descarta la copia vieja y se vuelve a traer. Quien decide si ESTE alumno puede leer ESTE medio
   sigue siendo la vista de cada módulo (asignación, intento, sesión); la cola sólo reparte bytes y la caché **no se sirve nunca como archivo estático**.
4. **Los eventos y los bytes van por canales distintos.** El WebSocket sólo avisa (`cambio` con `que = "medios"`, conteos de listos/preparando/fallidos, como
   mucho uno cada 2 s por clase); los bytes siguen por HTTP.
5. **Prioridades** (menor = antes): `proyeccion` 0 (lo que el profesor proyecta) · `evaluacion` 1 · `clase` 2 · `estudio` 3 · `paquete` 4 · `precarga` 5.
   Un hilo de descarga está reservado a ≤ `clase`. Una proyección que el profesor reemplaza baja a `clase`; una proyección vencida (30 min) deja de contar.
6. **Reanudable.** Se escribe en `objetos/<aa>/<id>.bin` mientras baja; tras un corte (o un reinicio del nodo) se pide `Range: bytes=N-` desde donde quedó y se
   re-suma lo que ya había. Si la fuente ignora `Range`, se empieza de cero. Se verifica el tamaño antes de marcar `disponible`.
7. **Espacio.** Tope de caché (`AVACOM_COLA_MAX_MB`, 4096) y espacio libre mínimo en el disco (`AVACOM_COLA_LIBRE_MIN_MB`, 1024). Si no cabe, expulsa lo menos usado
   (no lo que alguien está leyendo ni lo usado hace < 5 min); si aun así no cabe, `fallido · sin_espacio` y se sirve directo (se reintenta a los 10 min).

## 4. Cómo encaja con cada módulo

| Módulo | Qué cambia | Dónde |
|---|---|---|
| **classroom_engine** | `MedioView` pide el medio a la cola (prioridad `clase`). **Proyectar** (`IniciarSesion`, `DeclararSelector`) y **lanzar** (`Distribuir`) ponen en cola los medios del objeto con prioridad `proyeccion` al confirmarse la transacción, ligados a la sesión (`cm_solicitud.contexto_ref = sesion_id`). Puerto opcional `Servicios.preparar_medios`. | `interfaces/views.py`, `aplicacion/casos_uso.py`, `infraestructura/contenedor.py` |
| **modo_estudio** | `abrir_medio` por la cola (`estudio`). **`medir`** (preparar un paquete) trae el medio **una vez** a la caché y todos los alumnos reutilizan tamaño + SHA-256: con 35 tabletas, una lectura en vez de 35 (`paquete`, ligado a la asignación). El registro de autorización (paquete por alumno y aparato) y el contenido físico compartido quedan separados. | `infraestructura/contenido.py` |
| **evaluacion** | `abrir_medio` por la cola (`evaluacion`) **después** de que `MedioDelIntento` comprobó que el medio es de ESE examen y de ESE alumno. Al entregar las preguntas de un intento se preparan **sólo los medios de esas preguntas** (no el banco ni el material que la política no revela), ligados al intento. | `infraestructura/contenido.py` |

## 5. Configuración (`AVACOM_COLA_*`, en `backend.env` del nodo)

| Variable | Defecto | Qué es |
|---|---|---|
| `AVACOM_COLA_ACTIVA` | 1 | 0 = todo en paso a través, como antes de la cola |
| `AVACOM_COLA_DIR` | `backend/cache_medios` · instalado: `%ProgramData%\AVACOM\OPS Master\CacheMedios` | dónde viven los bytes |
| `AVACOM_COLA_MAX_MB` · `AVACOM_COLA_LIBRE_MIN_MB` | 4096 · 1024 | tope de la caché y espacio que debe quedar libre en el disco |
| `AVACOM_COLA_DESCARGAS` | 3 | descargas simultáneas desde Contenido (hilos; 0 = en la propia petición, así corren las pruebas) |
| `AVACOM_COLA_TRANSFERENCIAS` | 24 | transferencias simultáneas hacia tabletas |
| `AVACOM_COLA_ANCHO_ENTRADA_KBPS` · `…_SALIDA_KBPS` | 0 · 0 | tope global (KB/s) fuente→nodo y nodo→tabletas; 0 = sin tope |
| `AVACOM_COLA_REVALIDAR_SEG` | 60 | cada cuánto se confirma la versión del curso con la biblioteca |
| `AVACOM_COLA_ESPERA_INICIO_SEG` · `…_ESPERA_PAQUETE_SEG` · `…_ESPERA_CUPO_SEG` | 6 · 120 · 20 | esperas (ver reglas 1 y 3) |
| `AVACOM_COLA_SERVIR_SIN_BIBLIOTECA` | 0 | 1 = con Contenido cerrado se sirve lo que ya está en la caché |

Los topes de ancho de banda y de transferencias se ajustan según la Wi-Fi del aula y el número de tabletas; el estado actual está en `GET /api/medios/cola/`.

## 6. API (`/api/medios/cola/`)

| Ruta | Verbo | Quién | Qué |
|---|---|---|---|
| `/` | GET | cualquier sesión | cola, caché (bytes y espacio), cupos, límites y contadores |
| `/recursos/?contexto=&estado=&modulo=&limite=` | GET | cualquier sesión | los recursos con su avance; `contexto` = sesión / asignación / intento |
| `/recursos/{id}/` | GET | cualquier sesión | uno |
| `/recursos/{id}/cancelar/` · `/reintentar/` | POST | personal (no tableta de alumno) | cancela una preparación · reintenta una fallida |
| `/limpiar/` | POST | personal | vacía lo que nadie lee |

OPS: pestaña **Medios** de la Bitácora (administrador y técnico): cifras, recursos recientes con su avance, cancelar/reintentar y «Vaciar la caché».

## 7. Lo medido (2026-10-08)

Nodo aislado bajo Daphne de verdad (`manage.py runserver`, ASGI), con la API de Contenido v2 de pruebas y **8 tabletas pidiendo a la vez el mismo video de 100 MB** con
`Range: bytes=0-` (como lo hace un `<video>`):

| | cola apagada (como antes) | cola encendida |
|---|---|---|
| Descargas a AVACOM Contenido, 1.ª ronda | 8 | **1** |
| Descargas a Contenido, 2.ª ronda | 8 | **0** (salen del disco) |
| Primer byte (2.ª ronda) | 1,1–1,5 s | **0,05 s** |
| Memoria pico del nodo | **1 691 MB** (cada respuesta se cargaba entera) | **104 MB** |

El «antes» no es una suposición: Django consume un generador síncrono entero antes de enviar el primer byte bajo ASGI (`StreamingHttpResponse.__aiter__`), así que el
paso a través de la biblioteca cargaba cada video completo en RAM por tableta. El cuerpo asíncrono de la cola sale por trozos de 256 KB.

Pruebas: 125 de `cola_medios` (reglas puras, servidor con hilos reales y fuente falsa lenta, cuerpo HTTP síncrono y asíncrono, rutas, integración con las tres rutas de medios sobre la
API de Contenido de pruebas, preparación de la proyección y del examen, arquitectura), 7 del cliente .NET, y toda la suite del backend (1270) sigue pasando.

## 8. Lo que NO cambia

Ninguna ruta, ningún código de error, ninguna cabecera visible para MAUI: `Content-Type`, `Content-Length`, `Content-Range`, `Accept-Ranges`, `Cache-Control: no-store`,
las `X-Avacom-*` de la fuente, el pase de medios (`/api/m/<pase>/…`), CORS, `ETag` de los paquetes. `biblioteca/`, `contenido_v2.py`, `FuenteDeCursos` y sus adaptadores y
`classroom_engine/dominio/curso.py` **no se tocaron** (la cola lee por los casos de uso del aula, como cada módulo).

## 9. Decisiones y pendientes

- **La caché nunca tumba el nodo.** El ensayo del instalador encontró un backend que no arrancaba porque la carpeta de la caché no era accesible. Ahora, si no se puede crear, la cola se apaga sola con el motivo (`motivo_apagada` en `/api/medios/cola/` y en la pestaña Medios) y los medios van en paso a través; un fallo al construirla tampoco impide arrancar.

- **No hay deduplicación por contenido.** El archivo se nombra por el id del recurso, no por su SHA-256: en Windows un archivo abierto no se puede renombrar y las
  peticiones lo siguen mientras baja. El SHA-256 se calcula, se guarda y es el `ETag`/la medida del paquete, pero dos medios idénticos de cursos distintos ocupan dos veces.
- **La caché no se cifra.** Está en una carpeta de ProgramData con los mismos permisos que el resto del estado del nodo; el expediente (mucho más sensible) vive al lado.
- **`POST /paquetes/` sigue siendo síncrono**: el primer alumno espera a que se traiga cada medio nuevo (el cliente tiene 15 s de espera de cabeceras); los siguientes, no.
- **Un medio que no existe (404) no deja fila** en la cola ni sale en el panel: que la biblioteca diga «no existe» no es una falla del nodo; la siguiente petición lo vuelve a preguntar, como el paso a través de siempre.
  Sí se recuerda (un minuto, o diez si no cabe en la caché) lo que falla por causa del nodo o de la biblioteca cerrada, para no insistir en cada petición.
- **Lo que una fuente entrega ya hecho en memoria** (el manifiesto de ejemplo, sólo pruebas y desarrollo) se responde en una pieza con su cuerpo, como antes; la biblioteca de verdad, siempre por flujo.
- **Sin cifras de campo.** Lo medido está en las pruebas con una fuente falsa y con la API de Contenido de pruebas; no se probó con 35 tabletas ni con la Contenido real (no está en este equipo).
