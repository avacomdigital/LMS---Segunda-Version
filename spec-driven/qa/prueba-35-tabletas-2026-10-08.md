# Prueba de consumo con 35 tabletas · «Guerra Fría y América Latina» · 2026-10-08

Qué se hizo: 35 tabletas simuladas (inicio de sesión con PIN, unirse, WebSocket, latido, y por cada objeto proyectado: estado + objeto + todos los medios con pase,
video/audio con `Range: bytes=0-`) contra un nodo aislado (127.0.0.1:8010, sesión obligatoria, cola de medios encendida) y la **AVACOM Contenido 2.2.0 real** (curso
1.17.4, 8 lecciones, 70 medios, 30 MB). Todo por loopback: mide el **nodo**, no el router. El arnés no está en el repo (scratchpad de la sesión).

## Hallazgos del nodo 2.5.0 y arreglos (2.5.1)

| # | Hallazgo (medido) | Causa | Arreglo |
|---|---|---|---|
| 1 | Con 35 tabletas, 3–6 peticiones de medios por ronda daban **HTTP 500** «database is locked» | Cada petición con sesión y cada medio con pase abría una transacción de escritura (`BEGIN IMMEDIATE`) sólo para *leer* la sesión; 35 tabletas hacían fila hasta agotar los 20 s | La validación de sesión es de sólo lectura (`uow_lectura`); sólo escribe el «último uso» una vez por minuto |
| 2 | Aviso de cambio de lámina: p95 de 8 a 47 s; el propio nodo medía p95 = 23,6 s (objetivo 3 s) | La mitad del tiempo del nodo (py-spy) se iba en comprobar la sesión del pase (8 consultas + conexión SQLite nueva) en cada imagen | Caché de 15 s de la persona de un pase (`acceso/aplicacion/cache_pases.py`), vaciada **al instante** al cerrar sesión, cambiar clave, mover/desactivar a la persona o cambiar política, rol o grupo |
| 3 | 35 inicios de sesión a la vez: mediana 4–6 s, máx 12 s | Argon2id (0,2 s, 64 MiB) se calculaba dentro de la transacción de escritura: se hacía fila | Se verifica antes del turno de escritura (`AutenticarUsuario._verificar_antes`); mediana 1,5 s, máx 2,7 s |
| 4 | Las 35 tabletas se veían como UNA | `Sesion.Dispositivo = "student-" + nombre del aparato` (mismo nombre de fábrica) | La huella lleva un código propio de la instalación (`Identidad.HuellaDeTableta`) |
| 5 | Student olvidaba la dirección del aula al cerrarse | `ConnectionPage` no releía `student_server` | La recuerda |
| 6 | Entregar una actividad con 35 tabletas: p95 de 5,7 s por respuesta | La calificación (HTTP a Contenido) corría dentro de la transacción | Se pregunta antes de abrirla (`EnviarRespuestas._calificar_antes`). **El p95 no bajó en la medición**: queda otra causa sin perfilar (pendiente) |

Sesión: de fábrica **480 min (8 h)** para todos los perfiles (migración `acceso 0013`, sólo mueve lo que estaba en 240); `test_sesion_minima.py` comprueba que administración,
docente, alumno y visitante duran **≥ 1 h** (caducidad e inactividad). La clase del aula sigue viva mientras haya tabletas latiendo.

## Antes / después (35 tabletas, mismas rondas)

| Medida | 2.5.0 | 2.5.1 |
|---|---|---|
| Medios con HTTP 500 | 3–6 por ronda | **0** |
| Ronda de la cátedra (35 × 37 MB) | 99–101 s | **34–36 s** |
| Aviso de cambio de lámina a las tabletas | p95 8–47 s | **0,35–0,58 s** |
| Entrega de avisos medida por el nodo | p95 23,6 s | **p95 82 ms** |
| 35 inicios de sesión | mediana 5,7 s · máx 12,1 s | mediana 1,5 s · máx 2,7 s |
| Salida media del nodo | 95 Mbps | 247 Mbps (CPU pico 144 %, 182 MB) |

El techo del servidor sin autenticación (punto `/api/diagnostico/velocidad/descarga/`) es de ≈ 8 Gbps por loopback: Daphne no es el límite.

## Medidor de red

`AVACOM-Medir-Red.bat` (`installer/tools/Medir-Red.ps1`; puntos de medición `/api/diagnostico/velocidad/`): latencia, jitter y pérdida al router y al nodo (en reposo y **bajo carga**),
bajada y subida con 1/4/8 conexiones, Internet opcional y la estimación para 35 tabletas. Correrlo desde una laptop por Wi-Fi con OPS encendido; desde el equipo del nodo mide el techo
del servidor. Primera lectura desde este equipo: Wi-Fi 6E «Makers» 802.11ax, señal 93 %, router 192.168.0.1 con p95 de 18 ms y **5 % de pings perdidos** → si el nodo va por Wi-Fi, ponerlo por cable.

## Pendiente / no probado

- Router y Wi-Fi reales con 35 tabletas físicas (aquí todo es loopback); Android real.
- Entrega simultánea de actividades (hallazgo 6) y fin de examen con 35 alumnos (la calificación del examen puede tener el mismo patrón).
- El `POST /paquetes/` del modo estudio sigue síncrono.
