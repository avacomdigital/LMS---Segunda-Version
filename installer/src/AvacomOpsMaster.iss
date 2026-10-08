; ============================================================================
;  Instalador de AVACOM OPS Master (aplicacion + backend Django REST Framework)
;
;  Se compila con installer\build\Build-Installer.ps1, que antes deja el
;  contenido a instalar en dist\staging. No compiles este archivo a mano: el
;  script de compilacion es el que garantiza que lo que se empaqueta es la
;  version actual del producto y no una copia vieja.
;
;  Tres cosas que este instalador NO hace, a proposito:
;
;    * No cambia el comportamiento del producto. Configura lo que el backend
;      ya sabe leer (variables de entorno) y no toca su codigo.
;    * No toca AVACOM Contenido (la biblioteca de cursos). Otro AppId, otra
;      carpeta, otro servicio, otra base de datos, otros logs, otro grupo del
;      menu inicio. De el solo se LEE la nota de enlace (link.json), y eso lo
;      hace el backend en tiempo de ejecucion.
;    * No pide escribir nada. El equipo principal del aula es tactil y no
;      tiene teclado: todo el asistente se maneja con toques.
; ============================================================================

#include "definiciones.iss"

[Setup]
; Este AppId identifica a AVACOM OPS Master y a nada mas, y NO CAMBIA entre
; versiones: asi una version nueva se reconoce como actualizacion de la anterior
; y no como otro producto. AVACOM Contenido y AVACOM Student tienen el suyo: son
; productos independientes en "Aplicaciones instaladas".
AppId={{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}
AppName={#NombreProducto}
AppVersion={#VersionProducto}
AppVerName={#NombreProducto} {#VersionProducto}
AppPublisher={#Fabricante}
AppPublisherURL={#UrlProducto}
AppSupportURL={#UrlProducto}
AppUpdatesURL={#UrlProducto}
VersionInfoVersion={#VersionProducto}
VersionInfoDescription=Instalador de {#NombreProducto}
VersionInfoCompany={#Fabricante}
VersionInfoTextVersion={#VersionProducto} ({#Revision})

; Carpeta propia bajo AVACOM. Contenido usa AVACOM\Contenido.
DefaultDirName={autopf}\AVACOM\{#NombreCorto}
; Grupo propio en el menu inicio: no se comparte ni se sobrescribe ningun
; acceso directo de la biblioteca.
DefaultGroupName={#NombreProducto}
DisableProgramGroupPage=yes
UninstallDisplayName={#NombreProducto}
UninstallDisplayIcon={app}\App\{#EjecutableApp}

; El servicio, la regla de firewall y la carpeta de Program Files necesitan
; permisos de administrador. Es un unico consentimiento al principio.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=

ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
; La aplicacion lleva el Windows App SDK autocontenido, que pide Windows 10
; version 1809 (compilacion 17763). Con una version mas vieja el asistente se
; abriria y la aplicacion no.
MinVersion=10.0.17763

OutputDir={#CarpetaSalida}
OutputBaseFilename=AVACOM-OPS-Master-Setup-{#VersionProducto}
; Icono del propio archivo del instalador. Se usa el que compone
; New-ImagenesAsistente.ps1 y no el appicon.ico de MAUI, porque ese trae un
; solo tamano de 64 px y Windows lo escalaria borroso justo en el archivo
; que el usuario toca para instalar.
SetupIconFile={#CarpetaContenido}\Asistente\instalador.ico

; Pantalla 2 del asistente: la informacion de AVACOM LMS 2.0.
InfoBeforeFile=informacion.txt

; Marca del asistente. Sin estas dos directivas, Inno Setup pone sus propias
; ilustraciones: la grande en Bienvenido y en Instalacion completada, y la
; pequena arriba a la derecha en TODAS las demas pantallas. Es decir, un logo
; ajeno repetido pantalla a pantalla.
;
; Las genera New-ImagenesAsistente.ps1 desde el mismo simbolo que usa la
; aplicacion (assets/avacom-symbol.svg). Dos tamanos por imagen: Inno escoge
; segun el DPI, que en una pantalla tactil de aula no suele ser 96.
WizardImageFile={#CarpetaContenido}\Asistente\banner.png,{#CarpetaContenido}\Asistente\banner-2x.png
WizardSmallImageFile={#CarpetaContenido}\Asistente\simbolo.png,{#CarpetaContenido}\Asistente\simbolo-2x.png
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

; --- Asistente pensado para una pantalla tactil sin teclado ---
WizardStyle=modern
; Ventana grande: los objetivos de toque necesitan sitio.
WizardSizePercent=150
ShowLanguageDialog=no
AllowNoIcons=no
DisableWelcomePage=no
DisableReadyMemo=no
; Si algun archivo esta en uso, se avisa en lugar de reiniciar sin permiso.
RestartIfNeededByRun=no
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
SetupLogging=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
es.WelcomeLabel1=Bienvenido a la instalación de [name]
es.WelcomeLabel2=Este asistente instalará [name/ver] en este equipo.
; Textos para tocar, no para hacer clic. Sin esto salen los de fabrica («Haga clic en...»), y la pantalla de bienvenida
; repetia dos veces la instruccion de continuar.
es.ClickNext=Toca Siguiente para continuar, o Cancelar para salir de la instalación.
es.ReadyLabel2a=Toca Instalar para continuar, o Atrás si quieres revisar o cambiar algo.
es.WizardInfoBefore=Información de AVACOM LMS 2.0
es.InfoBeforeLabel=Lee esta información antes de continuar.
es.InfoBeforeClickLabel=Cuando estés listo, toca Siguiente.
es.WizardSelectDir=Carpeta de instalación
es.SelectDirDesc=¿Dónde se debe instalar [name]?
es.SelectDirLabel3=La instalación colocará [name] en la carpeta siguiente. AVACOM Contenido, si está en este equipo, usa una carpeta distinta y no se modifica.
es.SelectDirBrowseLabel=Para continuar, toca Siguiente. Para elegir otra carpeta, toca Examinar.
es.FinishedHeadingLabel=Instalación completada
es.FinishedLabelNoIcons={#NombreProducto} quedó instalado en este equipo.
es.FinishedLabel={#NombreProducto} quedó instalado en este equipo. El servicio de la API local arranca solo con Windows.
es.ExitSetupTitle=Salir de la instalación
es.ExitSetupMessage=La instalación no se ha terminado. Si sales ahora, {#NombreProducto} no quedará instalado.%n%n¿Salir de la instalación?

[CustomMessages]
es.EjecutarAhora=Abrir {#NombreProducto} ahora

; Sin [Tasks] a proposito: el icono del escritorio NO es una opcion. En una
; pantalla tactil basta un toque accidental sobre una casilla para dejar la OPS
; sin icono, y sin teclado no hay otra forma de abrirla.

[Dirs]
; --------------------------------------------------------------------------
; Estado del nodo. Vive FUERA de Program Files por dos razones:
;   1. Program Files es de solo lectura para el usuario que da la clase.
;   2. El expediente del estudiante es el unico dato que no se puede volver a
;      generar, asi que no puede depender de la carpeta del programa.
;
; La carpeta padre %ProgramData%\AVACOM la comparten los dos productos (la
; biblioteca guarda ahi su nota de enlace), por eso ni ella ni las nuestras se
; borran al desinstalar: solo se borra lo que este instalador creo, y el
; expediente se borra unicamente si se pide expresamente.
; --------------------------------------------------------------------------
;
; Permisos. El servicio corre como SYSTEM y es quien escribe la base de datos y
; los registros; el instalador y el mantenimiento los hace un administrador. Se
; les concede control total de forma EXPLICITA en cada carpeta de estado, en
; lugar de fiarse de lo que herede de ProgramData: si una carpeta ya existia con
; una lista de permisos rara (un intento anterior, una copia de otro equipo),
; sin esto el servicio no podria escribir y el nodo funcionaria sin guardar nada.
; Los demas usuarios conservan lo que hereden (leer), salvo en Logs.
; --------------------------------------------------------------------------
Name: "{commonappdata}\AVACOM"; Flags: uninsneveruninstall
Name: "{commonappdata}\AVACOM\{#NombreCorto}"; Permissions: system-full admins-full; Flags: uninsneveruninstall
Name: "{commonappdata}\AVACOM\{#NombreCorto}\Config"; Permissions: system-full admins-full; Flags: uninsneveruninstall
Name: "{commonappdata}\AVACOM\{#NombreCorto}\Data"; Permissions: system-full admins-full; Flags: uninsneveruninstall
; Copias de seguridad previas a cada actualizacion (las ultimas cinco).
Name: "{commonappdata}\AVACOM\{#NombreCorto}\Respaldos"; Permissions: system-full admins-full; Flags: uninsneveruninstall
; Registros del nodo (JSON Lines del backend, auditoria en archivo, y los del
; instalador y el lanzador). El lanzador escribe su diagnostico como el usuario
; del aula, no como administrador: necesita poder escribir aqui.
Name: "{commonappdata}\AVACOM\{#NombreCorto}\Logs"; Permissions: users-modify system-full admins-full; Flags: uninsneveruninstall
; La bitacora rota y exportada va aqui (la crea el backend; existir desde ya
; evita que la primera exportacion dependa de un permiso de creacion).
Name: "{commonappdata}\AVACOM\{#NombreCorto}\Logs\auditoria"; Permissions: system-full admins-full; Flags: uninsneveruninstall
; Cache de medios del nodo (cola de medios): los videos, audios, imagenes, PDF y paginas html que el nodo trae de AVACOM Contenido una vez y reparte a las
; tabletas. Es regenerable, asi que SE BORRA al desinstalar (ver [UninstallDelete]) y no entra en las copias de seguridad. Solo SYSTEM y los administradores
; la leen: el host le quita los permisos heredados de ProgramData al preparar el nodo.
Name: "{commonappdata}\AVACOM\{#NombreCorto}\CacheMedios"; Permissions: system-full admins-full

; --------------------------------------------------------------------------
; WebView2 (audio, video, PDF y laboratorios de las lecciones) guarda su perfil
; por defecto JUNTO AL EJECUTABLE: <App>\Avacom.Lms.Ops.exe.WebView2. La
; aplicacion vive en Program Files, donde quien da la clase no puede escribir, y
; al abrir una leccion WebView2 no puede crear su perfil: la aplicacion se cierra.
; El lanzador ya le da una carpeta propia en el perfil de Windows de la persona
; (WEBVIEW2_USER_DATA_FOLDER), pero la aplicacion tambien se puede abrir sin pasar
; por el lanzador. Esta carpeta, y solo esta, queda escribible para los usuarios:
; el resto de App sigue siendo de solo lectura y los binarios no se pueden cambiar.
; --------------------------------------------------------------------------
Name: "{app}\App\Avacom.Lms.Ops.exe.WebView2"; Permissions: users-modify

[Files]
; Interfaz .NET MAUI, con el runtime de .NET y el Windows App SDK dentro: el
; equipo del aula no instala prerrequisitos ni necesita internet.
Source: "{#CarpetaContenido}\App\*"; DestDir: "{app}\App"; Flags: ignoreversion recursesubdirs createallsubdirs

; Backend Django REST Framework, tal cual esta en el repositorio.
Source: "{#CarpetaContenido}\Backend\*"; DestDir: "{app}\Backend"; Flags: ignoreversion recursesubdirs createallsubdirs

; Runtime: Python embebido con Django, DRF, Channels y Daphne ya instalados, el
; arranque de Daphne y el host del servicio. Cada version trae su runtime
; completo: al actualizar, el asistente aparta el anterior antes de copiar este
; (nunca se mezclan runtimes, migraciones ni paquetes de versiones distintas).
Source: "{#CarpetaContenido}\Runtime\*"; DestDir: "{app}\Runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

; Que se empaqueto y desde que revision.
Source: "{#CarpetaContenido}\manifiesto.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#CarpetaContenido}\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; El icono abre el lanzador, no la aplicacion: primero se asegura el backend,
; se valida y despues se abre la interfaz.
Name: "{group}\{#NombreProducto}"; Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "iniciar"; WorkingDir: "{app}"; IconFilename: "{app}\App\{#EjecutableApp}"; IconIndex: 0; Comment: "Abre {#NombreProducto} y su API local"
Name: "{group}\Desinstalar {#NombreProducto}"; Filename: "{uninstallexe}"
; Siempre se crea: es un requisito, no una opcion.
Name: "{autodesktop}\{#NombreProducto}"; Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "iniciar"; WorkingDir: "{app}"; IconFilename: "{app}\App\{#EjecutableApp}"; IconIndex: 0; Comment: "Abre {#NombreProducto} y su API local"

[Run]
; --------------------------------------------------------------------------
; Teclado tactil de Windows. El primer arranque de OPS pide texto (nombre del aula,
; documento, nombres y apellidos del administrador) y el equipo del aula no tiene
; teclado: si Windows no muestra solo su teclado tactil al tocar un campo, el
; primer arranque (y con el, el PIN maestro) no se puede hacer. Windows 10 trae esa
; opcion apagada cuando no esta en modo tableta («Mostrar el teclado tactil cuando
; no hay un teclado conectado»). Aqui se enciende, y se muestra tambien el boton del
; teclado en la barra de tareas como segunda via. Son dos valores del usuario
; (HKCU\Software\Microsoft\TabletTip\1.7): sin servicios, sin administracion y
; reversibles desde Configuracion > Dispositivos > Escritura.
;
; runasoriginaluser: HKCU tiene que ser el de QUIEN DA LA CLASE, no el del token de
; administrador del instalador (sin la marca, con otra cuenta de administrador, se
; escribiria en el perfil equivocado). Si falla, no rompe nada: el verificador lo avisa.
; --------------------------------------------------------------------------
Filename: "{sys}\reg.exe"; Parameters: "add ""HKCU\Software\Microsoft\TabletTip\1.7"" /v EnableDesktopModeAutoInvoke /t REG_DWORD /d 1 /f"; StatusMsg: "Activando el teclado táctil de Windows..."; Flags: runhidden waituntilterminated runasoriginaluser
Filename: "{sys}\reg.exe"; Parameters: "add ""HKCU\Software\Microsoft\TabletTip\1.7"" /v TipbandDesiredVisibility /t REG_DWORD /d 1 /f"; Flags: runhidden waituntilterminated runasoriginaluser

; Casilla en la ultima pantalla: un toque y se abre.
;
; runasoriginaluser importa: sin esa marca la aplicacion heredaria el token de
; administrador del instalador, se ejecutaria elevada el resto de la sesion y
; lo que escribiera quedaria a nombre del administrador. Debe correr como quien
; da la clase, que es justo el permiso que se le concedio sobre el servicio.
Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "iniciar"; Description: "{cm:EjecutarAhora}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
; Antes de borrar archivos: parar el servicio (que usa el propio host), quitarlo
; del sistema y retirar la regla de firewall. Solo lo nuestro.
Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "detener-servicio"; Flags: runhidden waituntilterminated; RunOnceId: "DetenerServicioOps"
Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "quitar-servicio"; Flags: runhidden waituntilterminated; RunOnceId: "QuitarServicioOps"
Filename: "{app}\Runtime\{#EjecutableHost}"; Parameters: "cerrar-firewall"; Flags: runhidden waituntilterminated; RunOnceId: "CerrarFirewallOps"

[InstallDelete]
; Red de seguridad: el asistente ya aparta App, Backend y Runtime a
; {app}\Anterior antes de copiar, asi que normalmente no queda nada que borrar.
; Si quedara algo (un intento anterior cortado), se retira aqui para que la
; version nueva nunca se mezcle con restos: Django carga TODAS las migraciones
; que encuentra en la carpeta, y una que la version nueva ya no trae rompe el
; comando de migracion.
Type: filesandordirs; Name: "{app}\Backend"
Type: filesandordirs; Name: "{app}\Runtime\Python"
Type: filesandordirs; Name: "{app}\Runtime\*.py"

[UninstallDelete]
; Lo que crea la ejecucion y no el instalador (cachés de Python, el perfil de
; WebView2 que la aplicacion deja dentro de su carpeta, restos de una
; actualizacion cortada).
Type: filesandordirs; Name: "{app}\Backend"
Type: filesandordirs; Name: "{app}\Runtime\Python"
Type: filesandordirs; Name: "{app}\App"
Type: filesandordirs; Name: "{app}\Anterior"
Type: dirifempty; Name: "{app}"
; La cache de medios no es expediente: se vuelve a llenar sola (pueden ser varios GB).
Type: filesandordirs; Name: "{commonappdata}\AVACOM\{#NombreCorto}\CacheMedios"

; ============================================================================
[Code]
#include "codigo.iss"
