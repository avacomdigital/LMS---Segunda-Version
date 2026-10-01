## ¿Qué es una OPS?

Una OPS es un sistema windows 10 con una pantalla grande táctil, que permite realizar las interacciones pero no cuenta con la posibilidad de colocar un teclado, mouses. Por lo que lo mejor es que todo el AVACOM OPS se maneje en un install wizard, el instalador debe hacer un icono de acceso directo en el OPS. 

Añadido: en la práctica la OPS es el nodo principal del aula. Además de la aplicación del profesor (AVACOM OPS Master), en ese mismo equipo corre el backend del LMS (Django), que atiende por la red local a las tabletas y computadores de los estudiantes en el puerto 8000, y guarda el expediente en una base de datos SQLite. Nadie va a abrir una consola en ese equipo: si algo no lo hace el instalador con toques, no se hace. Windows 10 ofrece su teclado táctil, y el login de OPS ya lo usa para escribir documento y clave, pero el instalador no debe depender de él.

Otros detalles a tener en cuenta:

1. Cada instalador debe generar un desinstalador (uninstaller) para que podamos colocar nuevas versiones sobre el mismo sistema
2. Es probable que para instalar nuevas versiones se deban borrar algunas dependencias o crear unas nuevas.
3. La base de datos por ahora se puede borrar, pero cuando lleguemos a crear el módulo de progreso y calificaciones, ahí ya no se puede borrar. 
4. El backend debe ejecutarse de manera automática
5. En los instaladores se debe compromar los paquetes necesarios, cómo python, .NET necesarios para ejecutarse, en caso que no existan, el wizard de manera automática debe ejecutar comandos de winget para instalarlo.
6. La idea es que el wizard permita instalar el programa sin el uso de comandos, teclas, solo clicks (puede ejecutar en segundo plano archivos .BAT pero el WIZARD lo administra no el usuario para evitar hacer uso del teclado).
7. El backend siempre debe correr en el 0.0.0.0:8000 

## Reglas fundamentales

1. Siempre que se genere un instalador debes verificar que es la versión actual y no versiones anteriores. 
2. El instalador debe asegurar que el programa resultante tenga los temas de auditoria, permisos de escritura y lectura, también permisos para borrar y hacer todas las modificaciones y acciones que requiere el LMS para ejecutarse.
3. El instalador de la OPS AVACOM debe asegurarse siempre de que el sistema de pueda guardar la información de auditoría y logs.
4. Evitar que los problemas de configuración externa rompa la información del sistema o lo inhabilite por completo. 

## Dos instaladores, no uno

AVACOM OPS Master y AVACOM Student tienen instaladores separados. No comparten identificador de instalación, carpeta, versión, desinstalador ni ciclo de publicación, y ninguno exige que el otro esté instalado en el mismo equipo. Lo único que los une es el contrato de red: Student habla con el backend que instala OPS. Este documento describe los dos porque el contexto es común, pero cada uno se construye, se prueba y se entrega por su cuenta.

Un tercer producto, AVACOM Contenido (la biblioteca de cursos), tiene su propio instalador y queda fuera de los dos. Ni OPS ni Student lo instalan, lo actualizan o lo modifican.

Cada vez que se inicie la aplicación de AVACOM OPS debe iniciarse de manera automática también el backend hecho en Django Rest Framework.

## Cómo leer los tres detalles anteriores

Sobre el desinstalador y las nuevas versiones sobre el mismo sistema. Cada instalador se registra en Aplicaciones instaladas de Windows con un identificador propio y estable, de modo que una versión nueva se reconozca como actualización de la anterior y no como otro producto. Actualizar es: detectar lo instalado, detener lo que corre (sólo lo propio), respaldar lo que no se puede regenerar, retirar lo que la versión nueva ya no usa, copiar lo nuevo, preparar y validar. El desinstalador debe dejar el equipo como estaba, sin tocar lo que pertenece a otros productos de AVACOM.

Sobre borrar y crear dependencias. En la OPS, las dependencias son el runtime de Python embebido y sus paquetes, la carpeta del backend y el servicio de Windows. Cada versión trae su runtime completo, así que al actualizar hay que borrar el anterior antes de copiar el nuevo, no mezclar. Hay un motivo concreto: Django carga todos los archivos de migraciones que encuentra en la carpeta, y una migración que la versión nueva ya no trae pero que quedó de la anterior rompe el comando de migración. Lo mismo pasa con paquetes que dejan de usarse o cambian de nombre, y con carpetas de caché compiladas. La instalación nunca ejecuta pip ni descarga nada: todo viaja dentro del instalador, porque el aula puede no tener internet.

Sobre la base de datos. Hoy se puede borrar; cuando exista el módulo de progreso y calificaciones, no. Ver la sección Política de datos más abajo.

## AVACOM LMS OPS

Este instalador debe ser para el contexto de la OPS

Todo lo que sigue en esta sección es el contexto verificado en el repositorio a 2026-09-29, más propuestas marcadas como tales.

## OPS · qué se instala

AVACOM OPS Master es una aplicación .NET MAUI de escritorio (Avacom.Lms.Ops.exe, destino net10.0-windows10.0.19041.0, sin empaquetar como MSIX). El proyecto declara Windows 10 versión 1809 (10.0.17763) como mínimo. La ventana arranca maximizada por sí sola. Se publica autocontenida, con el runtime de .NET y el Windows App SDK dentro, para no exigir prerrequisitos.

El backend es Django y Django REST Framework, en la carpeta backend, sirviendo la API del aula en 0.0.0.0:8000 (las tabletas llegan por la IP del equipo). Se ejecuta como servicio de Windows, no como runserver, para que la API exista aunque nadie tenga abierta la interfaz. El expediente y el resto de datos viven en SQLite.

## OPS · lo que ya existe

No se parte de cero. Ya hay un instalador construido con Inno Setup 6, versión 2.0.0, en la carpeta installer, documentado en spec-driven/08-instalador.md e installer/README.md. Tiene ocho pantallas pensadas para toque (ventana al 150 %, botones de 150 por 46 px, casillas de 34 px, ruta de instalación de sólo lectura con botón para usar la carpeta recomendada), nueve comprobaciones del equipo, un servicio AVACOMOPSBackend con inicio automático, un ejecutable auxiliar (Avacom.Ops.Host.exe) que hace de servicio, lanzador y preparación, un Python 3.12.10 embebido, la configuración del nodo en %ProgramData%\AVACOM\OPS Master (Config, Data y Logs, fuera de Program Files), una regla de firewall para el puerto 8000, un AppId propio y un desinstalador que pregunta al final si borrar el expediente (por defecto, no). Se construye con installer\build\Build-Installer.ps1, que pasa antes las pruebas del backend y verifica el asistente. Esta tarea es actualizar ese instalador al estado actual del producto, no escribir otro.

## OPS · lo que quedó desactualizado

Estas diferencias están comprobadas contra el código de hoy.

El servidor. El instalador arranca el backend con Waitress, un servidor WSGI. Desde el 2026-09-29 el aula tiene un canal en tiempo real por WebSocket (Django Channels) que se sirve en el mismo puerto 8000, y el programador del nodo (presencia por latido, cierre de clases tras 120 minutos de inactividad, archivado y detección de caída al arrancar) se inicia solo desde avacom_lms/asgi.py. Waitress no atiende WebSocket ni inicia ese programador. El arranque tiene que pasar a Daphne sirviendo avacom_lms.asgi:application, conservando la escucha en 0.0.0.0:8000. Ese cambio se hace en el archivo de arranque del instalador (avacom_ops_backend.py) y no en backend, y toca varios puntos: el requirements-runtime.txt, la verificación de importaciones de Get-PythonRuntime.ps1 y de Preparar.cs (hoy importan waitress), el manifiesto (servidor_wsgi), la descripción del servicio, la parada del proceso (ProcesoBackend supone la forma de cerrar de Waitress y hay que asegurar que Daphne deje SQLite consistente al detenerse) y las secciones del diagnóstico que hablan de hilos de Waitress. El puerto sigue siendo uno solo, así que la regla de firewall no cambia por esto.

Las dependencias. El requirements-runtime.txt distribuido no trae channels 4.3.2 ni daphne 4.2.3 ni sus transitivas. En el entorno de desarrollo actual eso son Twisted, autobahn, txaio, attrs, Automat, constantly, hyperlink, Incremental, zope.interface, pyOpenSSL, service-identity, idna, cbor2, msgpack, ujson, packaging y typing_extensions, además de lo que ya viaja (Django 5.2.3, djangorestframework 3.16.1, asgiref, sqlparse, tzdata, argon2-cffi, cryptography, PyJWT y sus transitivas). Waitress deja de usarse. La lista definitiva sale de resolver backend/requirements.txt en el equipo de compilación con ruedas precompiladas para Windows, Python 3.12 y 64 bits: nada se compila en el equipo destino.

Las claves del módulo de acceso. El backend espera tres claves de 32 bytes en base64 en backend.env: AVACOM_LMS_CLAVE_DATOS (cifra los datos personales con AES-GCM), AVACOM_LMS_CLAVE_INDICE (índice ciego HMAC para buscar por documento, código o correo) y AVACOM_LMS_CLAVE_TOKENS (firma de las sesiones). La configuración que genera el instalador de hoy sólo crea AVACOM_LMS_SECRET, así que el backend deriva las tres de esa clave y /health/ responde claves_derivadas en verdadero. El instalador debe generarlas una sola vez. Regla derivada: backend.env tiene el mismo estatus que la base de datos. Si se conserva la base y cambian esas claves, las personas ya guardadas dejan de poder descifrarse y buscarse. Se conservan o se reemplazan juntos, nunca uno sin el otro, y nunca se agregan claves nuevas en silencio a una base que ya tiene datos de acceso.

La biblioteca. El aula lee ahora la API de Contenido v2 de AVACOM Contenido, que se instala en C:\Program Files\AVACOM\Contenido y publica su nota de enlace en %ProgramData%\AVACOM\content\link.json (puertos, token). El instalador de hoy, su comprobación de presencia de la biblioteca y el diagnóstico Probar-Comunicacion miran la nota del contrato anterior, %ProgramData%\AVACOM\contenido\enlace.json (nótese contenido contra content). Deben mirar link.json. La comprobación sigue siendo informativa: sin biblioteca el producto instala y arranca, pero el aula no tendrá cursos. Como antes, el instalador no toca la biblioteca; sólo el backend lee la nota, en tiempo de ejecución.

La base de datos. El backend abre SQLite en modo WAL, de modo que junto al archivo de la base aparecen dos archivos más, terminados en -wal y -shm. Copiar, respaldar, restaurar o borrar la base es tratar los tres, con el servicio detenido. Además las migraciones siguen cambiando en el desarrollo (apps acceso, device_manager, biblioteca, expediente, classroom_engine y modo_estudio, con migraciones nuevas sin publicar), por lo que una base de una versión antigua puede no migrar limpia.

La organización. Tras migrar, el nodo no tiene organización ni administrador, y sin ellos el login responde 409 no_instalado. Se crean una sola vez con POST /api/acceso/instalacion/ o con el comando manage.py acceso_instalar (código, nombre y país de la organización; documento, nombres y apellidos del primer administrador; si no se da contraseña se genera una y se muestra una sola vez). La documentación del backend prevé que ese primer arranque lo haga el instalador de Windows, pero hoy ni el instalador ni OPS tienen una pantalla para hacerlo, y son datos de texto libre en un equipo sin teclado. Es una decisión pendiente (ver más abajo).

La dirección para las tabletas. Student pide escribir la dirección del aula (algo como http://192.168.0.55:8000). El documento 07 planteó que el backend anunciara sus direcciones y que OPS las mostrara, pero no está implementado. Propuesta: la pantalla final del instalador puede leer las direcciones IPv4 del equipo (sin loopback ni adaptadores virtuales) y mostrarlas en letra grande con la frase de qué escribir en las tabletas, sin tocar el backend.

## OPS · requisitos de la instalación

El asistente se maneja sólo con toques y ningún campo de texto es obligatorio. Se conserva lo ya resuelto: ruta de sólo lectura, botones y casillas grandes, avisos que se cierran con un toque y ningún diálogo que pida confirmar dos veces.

El acceso directo en el escritorio es un requisito pedido, no una opción. Hoy es una casilla de tareas marcada por defecto; en una pantalla táctil basta un toque accidental para dejar la OPS sin icono, así que debe crearse siempre. Abre el lanzador (Avacom.Ops.Host.exe con el verbo iniciar), que asegura el backend, valida /health/ y después abre la interfaz, con el icono de AVACOM. También se crea el acceso del menú Inicio.

El servicio del backend queda en inicio automático, con reinicio ante fallos, y el usuario que da la clase puede arrancarlo y detenerlo sin credenciales de administrador. El instalador pide permisos de administrador una sola vez, al principio. La aplicación se lanza con los permisos de quien da la clase, no con el token elevado del instalador.

Sin internet y sin prerrequisitos: ni Python ni .NET ni pip ni winget en el equipo destino.

El puerto 8000. Libre: se continúa. Ocupado por el backend de AVACOM (se reconoce preguntando a /health/, que responde el componente avacom-lms-backend): es una actualización, se avisa y se detiene el servicio propio. Ocupado por otro programa: se detiene la instalación con un mensaje claro y no se cierra nada ajeno. Los WebSocket usan el mismo puerto, sin reglas nuevas.

Firewall. La regla actual abre TCP 8000 de entrada sólo en los perfiles privado y de dominio, y sólo para el python.exe del runtime instalado. Es deliberado: la API no exige sesión por defecto y el aula es una red privada. El riesgo, visto en la prueba del documento 07, es que Windows clasifique la red del aula como pública y las tabletas no lleguen (ver Decisiones por confirmar).

La marca es la de AVACOM y sale de un solo archivo, assets/avacom-symbol.svg. La compilación falla si reaparece el logotipo de la plantilla de MAUI.

## OPS · actualizar sobre una versión anterior

Orden esperado. Uno: detectar la instalación previa por su identificador y leer su versión. Dos: detener el servicio y cerrar la aplicación propia. Tres: si los datos se conservan, hacer una copia de seguridad de la carpeta Data (base más -wal y -shm) y de backend.env en una carpeta de respaldos, con la versión y la fecha en el nombre, conservando sólo las últimas. Cuatro: borrar lo que la versión nueva reemplaza (Backend, Runtime\Python y sus paquetes, cachés compiladas) con una instrucción de borrado previa a la copia, no sólo al desinstalar como ocurre hoy. Cinco: copiar lo nuevo. Seis: preparar (revisión de configuración, migraciones, archivos estáticos sólo si el backend declara STATIC_ROOT). Siete: volver a registrar el servicio y la regla de firewall, porque el comando que ejecutan cambia (Daphne en lugar de Waitress). Ocho: arrancar y validar que /health/ responde y que el canal en tiempo real acepta conexiones. Nueve: si algo falla en los pasos seis a ocho, no dejar la instalación a medias: restaurar la copia y volver a arrancar lo anterior, o detenerse con un mensaje que diga qué pasó.

Los datos de estado (Config, Data, Logs) viven fuera de la carpeta del programa y se crean con la marca de no desinstalar. La carpeta padre %ProgramData%\AVACOM la comparte AVACOM Contenido y nunca se borra.

## OPS · política de datos

Hoy la base de datos se puede borrar. Aclaración de alcance: no es sólo el expediente. Esa base contiene también la organización, el administrador, las personas importadas, los dispositivos registrados, las clases y las asignaciones de estudio. Borrarla obliga a repetir la instalación de la organización, volver a importar el padrón y volver a registrar las tabletas.

Cuando exista el módulo de progreso y calificaciones, no se podrá borrar. Desde ese momento las reglas son otras: se conserva siempre; la copia de seguridad previa a migrar es obligatoria; una migración que falla restaura la copia y no destruye nada; y la base sólo se elimina si quien desinstala lo pide expresamente, con la respuesta por defecto en no.

Propuesta: que la política sea un dato de cada versión, escrito en el manifiesto del instalador (por ejemplo, datos reemplazables o datos protegidos), y no lógica cableada. Así el paso al modo protegido, cuando llegue el módulo de calificaciones, es cambiar un valor y no reescribir el instalador. Mientras rija reemplazables, conservar la base cuando las migraciones se aplican sin error y reemplazarla sólo si fallan, dejando antes la copia; y, si se quiere una base limpia a propósito, ofrecer en la pantalla Listo para instalar dos botones grandes, Conservar los datos y Empezar de cero, que desaparezcan cuando la política sea protegida.

## OPS · desinstalar

Desde Aplicaciones instaladas y desde el menú Inicio. Detiene el servicio, lo elimina, retira la regla de firewall, borra los archivos del programa y los accesos directos. Al final pregunta si eliminar también los datos; la respuesta por defecto es conservarlos, y la respuesta vale para la base y para backend.env juntos. No borra %ProgramData%\AVACOM ni nada de AVACOM Contenido.

## OPS · convivencia con AVACOM Contenido

Comparten el equipo y nada más. OPS usa el identificador de instalación propio, la carpeta Program Files\AVACOM\OPS Master, los datos en %ProgramData%\AVACOM\OPS Master, el servicio AVACOMOPSBackend, el puerto TCP 8000 y la regla de firewall AVACOM OPS Master Backend. Contenido tiene lo suyo, con puertos al azar en loopback. El único punto de contacto es la nota link.json, que se lee y no se escribe. La variable AVACOM_CONTENIDO_ENLACE se deja sin definir para que el backend busque la nota donde la biblioteca la publica.

## OPS · límites

El instalador no es ocasión para arreglar el producto. No cambia el comportamiento funcional ni la arquitectura, no edita archivos de backend ni de src (la configuración se entrega por variables de entorno que el backend ya lee, y las propiedades de publicación se inyectan desde installer\build\Distribucion.props sin tocar los proyectos), no añade rutas y no pide comandos al usuario. Cambiar Waitress por Daphne es cambiar cómo el instalador arranca el backend, no el backend. Los cambios de código que hagan falta se piden aparte.

## AVACOM STUDENT

Este puede correr en computadores normales windows 10, windows 11, también corre en tablets con versiones de android alrededor de android 13 y android 14.

## Student · una app, dos entregas

Es un solo proyecto .NET MAUI (Avacom.Lms.Student, identificador com.avacom.lms.student) con dos destinos, y cada destino se entrega distinto. En ambos, Student sólo hace conexiones salientes hacia el backend de la OPS: no instala servicio, no abre puertos y no necesita regla de firewall.

Windows 10 y 11. Se publica como aplicación de escritorio autocontenida (no está empaquetada como MSIX, así que no tiene instalación propia de Windows) y necesita su propio instalador con asistente, acceso directo en el escritorio y desinstalador, y su propio identificador de instalación, distinto del de OPS. El proyecto declara Windows 10 versión 1809 como mínimo. No comparte carpeta con OPS Master ni con Contenido.

Android 13 y 14 (API 33 y 34). Se entrega como un APK firmado. Como el aula puede no tener internet, no se cuenta con una tienda de aplicaciones: la instalación es manual (sideload) y cada tableta debe permitir instalar apps de origen desconocido. Tres requisitos de las actualizaciones: mismo identificador de aplicación, la misma llave de firma en todas las versiones y un número de versión interno (ApplicationVersion) que aumente en cada compilación; hoy es 1 fijo, igual que la versión visible 1.0, así que la numeración de versiones no está conectada. Perder la llave de firma obliga a desinstalar en cada tableta. La versión mínima declarada hoy es Android 5 (API 21), mucho más laxa que el objetivo de pruebas; el manifiesto permite tráfico HTTP en texto claro (la LAN del aula no usa HTTPS) y pide los permisos de internet y estado de red.

Datos en el aparato. Student guarda en el equipo la dirección del aula y el nombre, una cola de respuestas aún no entregadas (cola-respuestas.json, para cuando la red se cae) y, según el diseño del Modo Estudio, los paquetes de lección descargados y cifrados. El espacio libre y la batería que la tableta reporta con cada latido se leen del sistema y no requieren nada del instalador. Actualizar encima conserva todo eso; desinstalar en Android lo borra siempre. En Windows, el desinstalador no debe borrar la carpeta de datos del usuario por defecto, por la misma razón por la que el de OPS conserva el expediente: hay respuestas del estudiante que quizá todavía no llegaron al backend.

Versiones mezcladas. El 2026-09-28 una OPS más vieja que su backend llamó a una ruta que ya no existía y el aula respondió con errores 404. El mismo riesgo aplica entre Student y el backend de la OPS. Los dos instaladores deben registrar la versión del producto y la revisión de git en su manifiesto, y conviene que ambos salgan de una sola fuente de versión aunque se publiquen por separado.

## Decisiones por confirmar

Estas cosas no las decide el documento; tienen una recomendación, pero pide respuesta.

1. Política de datos al actualizar: conservar cuando migra bien y reemplazar sólo si falla (recomendado), o reemplazar siempre mientras la base sea desechable. Y si se ofrecen los dos botones táctiles.
2. Quién crea la organización y el primer administrador. Recomendación: que el instalador deje el nodo listo (migrado, con claves) y avise en la pantalla final si no hay organización, y que la creación sea una pantalla de primer arranque de OPS, que sí puede usar el teclado táctil de Windows. Eso es una tarea de la aplicación, no del instalador. Alternativa: que el instalador ejecute acceso_instalar con datos que alguien haya definido antes, lo que reintroduce texto libre en el asistente.
3. Firewall en red pública. Si la OPS clasifica la red del aula como pública, la regla actual bloquea a las tabletas. Opciones: incluir el perfil público, avisarlo en la comprobación del equipo, o cambiar el perfil de la red. Ninguna se ha elegido.
4. Si la aplicación OPS debe abrirse sola al iniciar sesión en Windows, como un quiosco. Hoy sólo el servicio arranca con Windows.
5. Versión mínima de Android de Student: dejar API 21 o subir a 33.
6. Cómo llega el APK a las tabletas (cable, tarjeta, descarga desde otro equipo) y quién custodia la llave de firma.
7. Student en Windows: instalación por usuario o para todo el equipo, y si el instalador puede dejar sembrada la dirección del aula para que nadie la teclee.
8. Firma de código de los instaladores. Sin ella, SmartScreen de Windows 10 advierte de un editor desconocido y hace falta pasar por Más información y Ejecutar de todos modos, incómodo en una pantalla táctil.
9. Versión única del producto y de dónde sale (hoy los proyectos dicen 1.0 y el instalador de OPS dice 2.0.0).

## Cómo se comprobará

En un Windows 10 limpio, sin internet y sin Python ni .NET, la instalación de OPS termina sin que nadie escriba nada: el servicio queda en inicio automático, /health/ responde, el canal en tiempo real acepta una conexión, el icono está en el escritorio y una tableta de la misma red llega al backend por la IP del equipo.

Actualizar sobre la versión 2.0.0 (la de Waitress) y sobre la misma versión no deja restos: no queda waitress ni migraciones viejas, el servicio corre con Daphne, y la base y backend.env terminan conforme a la política de datos. Una migración que falla deja el equipo con la versión anterior funcionando, no a medias.

Desinstalar quita servicio, firewall, archivos y accesos, pregunta por los datos con la respuesta por defecto en conservar y no toca AVACOM Contenido. Reinstalar después, conservando los datos, deja el aula como estaba, con las personas todavía descifrables.

Los dos instaladores se prueban por separado, y una instalación de Student (Windows o Android) nunca requiere ni modifica la de OPS. El instalador de OPS ya se verifica a sí mismo en cada compilación: sus comprobaciones se pueden ejecutar de verdad con el modo de volcado (/VOLCADO), el script Verificar-Asistente.ps1 y las pruebas del backend que Build-Installer.ps1 corre antes de empaquetar; el de Student debería tener un equivalente.
