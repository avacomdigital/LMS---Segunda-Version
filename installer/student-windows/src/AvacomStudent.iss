; ============================================================================
;  Instalador de AVACOM Student para Windows 10 y 11.
;
;  Se compila con installer\student-windows\build\Build-StudentInstaller.ps1, que antes deja el
;  contenido a instalar en dist\student-windows\staging. No compiles este archivo a mano: el script
;  de compilacion es el que garantiza que lo que se empaqueta es la version actual del producto y
;  no una copia vieja.
;
;  Es OTRO producto que AVACOM OPS Master: otro AppId, otra carpeta, otra version publicada, otro
;  desinstalador. No exige que OPS este en este equipo y no lo toca.
;
;  Student solo hace conexiones SALIENTES hacia la OPS. Por eso este instalador NO registra ningun
;  servicio, NO abre puertos y NO toca el firewall.
; ============================================================================

#include "definiciones.iss"

[Setup]
; Este AppId identifica a AVACOM Student y a nada mas, y NO CAMBIA entre versiones: asi una version
; nueva se reconoce como actualizacion de la anterior y no como otro producto.
AppId={{4C2DB723-841F-4620-BBE3-8F5CC7E57D1D}
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

; Carpeta propia bajo AVACOM. OPS Master usa AVACOM\OPS Master y Contenido AVACOM\Contenido.
DefaultDirName={autopf}\AVACOM\{#NombreCorto}
DefaultGroupName={#NombreProducto}
DisableProgramGroupPage=yes
UninstallDisplayName={#NombreProducto}
UninstallDisplayIcon={app}\App\{#EjecutableApp}

; Instalacion para TODO el equipo (decision 7 del contexto: es lo normal en un aula, donde varios
; estudiantes usan el mismo equipo): Program Files y el icono comun del escritorio piden permisos de
; administrador, una sola vez al principio. Los datos de cada persona viven en SU perfil.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=

ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
; La aplicacion lleva el Windows App SDK autocontenido, que pide Windows 10 version 1809
; (compilacion 17763).
MinVersion=10.0.17763

OutputDir={#CarpetaSalida}
OutputBaseFilename=AVACOM-Student-Setup-{#VersionProducto}
SetupIconFile={#CarpetaContenido}\Asistente\instalador.ico

InfoBeforeFile=informacion.txt

; Marca del asistente (las genera New-ImagenesAsistente.ps1 desde el simbolo de la aplicacion).
WizardImageFile={#CarpetaContenido}\Asistente\banner.png,{#CarpetaContenido}\Asistente\banner-2x.png
WizardSmallImageFile={#CarpetaContenido}\Asistente\simbolo.png,{#CarpetaContenido}\Asistente\simbolo-2x.png
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

; --- Asistente pensado para tocar: puede correr en una tableta con Windows, sin teclado ---
WizardStyle=modern
WizardSizePercent=150
ShowLanguageDialog=no
AllowNoIcons=no
DisableWelcomePage=no
DisableReadyMemo=no
RestartIfNeededByRun=no
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
SetupLogging=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
es.WelcomeLabel1=Bienvenido a la instalación de [name]
es.WelcomeLabel2=Este asistente instalará [name/ver] en este equipo.
es.ClickNext=Toca Siguiente para continuar, o Cancelar para salir de la instalación.
es.ReadyLabel2a=Toca Instalar para continuar, o Atrás si quieres revisar o cambiar algo.
es.WizardInfoBefore=Información de AVACOM Student
es.InfoBeforeLabel=Lee esta información antes de continuar.
es.InfoBeforeClickLabel=Cuando estés listo, toca Siguiente.
es.WizardSelectDir=Carpeta de instalación
es.SelectDirDesc=¿Dónde se debe instalar [name]?
es.SelectDirLabel3=La instalación colocará [name] en la carpeta siguiente. AVACOM OPS Master y AVACOM Contenido, si están en este equipo, usan carpetas distintas y no se modifican.
es.SelectDirBrowseLabel=Para continuar, toca Siguiente. Para elegir otra carpeta, toca Examinar.
es.FinishedHeadingLabel=Instalación completada
es.FinishedLabelNoIcons={#NombreProducto} quedó instalado en este equipo.
es.FinishedLabel={#NombreProducto} quedó instalado en este equipo.
es.ExitSetupTitle=Salir de la instalación
es.ExitSetupMessage=La instalación no se ha terminado. Si sales ahora, {#NombreProducto} no quedará instalado.%n%n¿Salir de la instalación?

[CustomMessages]
es.EjecutarAhora=Abrir {#NombreProducto} ahora

; Sin [Tasks] a proposito: el icono del escritorio NO es una opcion. Un toque accidental sobre una
; casilla no puede dejar al equipo sin icono.

[Dirs]
; --------------------------------------------------------------------------
; WebView2 (audio, video, PDF y laboratorios de las lecciones) guarda su perfil por defecto JUNTO AL
; EJECUTABLE: <App>\Avacom.Lms.Student.exe.WebView2. La aplicacion vive en Program Files, donde el
; estudiante no puede escribir, y al abrir una leccion WebView2 no puede crear su perfil: la
; aplicacion se cierra. El lanzador ya le da una carpeta propia en el perfil de Windows de cada
; persona (WEBVIEW2_USER_DATA_FOLDER), pero la aplicacion tambien se puede abrir sin pasar por el
; lanzador (por ejemplo, como shell de un equipo en modo kiosco). Esta carpeta, y solo esta, queda
; escribible para los usuarios: el resto de App sigue siendo de solo lectura y los binarios no se
; pueden cambiar.
; --------------------------------------------------------------------------
Name: "{app}\App\{#EjecutableApp}.WebView2"; Permissions: users-modify

[Files]
; Interfaz .NET MAUI, con el runtime de .NET y el Windows App SDK dentro: el equipo no instala
; prerrequisitos ni necesita internet.
Source: "{#CarpetaContenido}\App\*"; DestDir: "{app}\App"; Flags: ignoreversion recursesubdirs createallsubdirs

; Lanzador: perfil de WebView2 por persona y comprobacion de lo instalado.
Source: "{#CarpetaContenido}\Lanzador\*"; DestDir: "{app}\Lanzador"; Flags: ignoreversion recursesubdirs createallsubdirs

; Que se empaqueto y desde que revision.
Source: "{#CarpetaContenido}\manifiesto.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#CarpetaContenido}\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; El icono abre el lanzador, no la aplicacion: primero se le da a WebView2 su perfil escribible.
Name: "{group}\{#NombreProducto}"; Filename: "{app}\Lanzador\{#EjecutableLanzador}"; Parameters: "iniciar"; WorkingDir: "{app}"; IconFilename: "{app}\App\{#EjecutableApp}"; IconIndex: 0; Comment: "Abre {#NombreProducto}"
Name: "{group}\Desinstalar {#NombreProducto}"; Filename: "{uninstallexe}"
; Siempre se crea: es un requisito, no una opcion. Con instalacion para todo el equipo, es el
; escritorio comun: lo ven todas las cuentas.
Name: "{autodesktop}\{#NombreProducto}"; Filename: "{app}\Lanzador\{#EjecutableLanzador}"; Parameters: "iniciar"; WorkingDir: "{app}"; IconFilename: "{app}\App\{#EjecutableApp}"; IconIndex: 0; Comment: "Abre {#NombreProducto}"

[Run]
; Casilla en la ultima pantalla: un toque y se abre. runasoriginaluser importa: sin esa marca la
; aplicacion heredaria el token de administrador del instalador y se ejecutaria elevada.
Filename: "{app}\Lanzador\{#EjecutableLanzador}"; Parameters: "iniciar"; Description: "{cm:EjecutarAhora}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[InstallDelete]
; Red de seguridad: el asistente ya aparta App y Lanzador a {app}\Anterior antes de copiar, asi que
; normalmente no queda nada que borrar. Si quedara algo (un intento anterior cortado), se retira
; aqui para que la version nueva nunca se mezcle con archivos de la anterior.
Type: filesandordirs; Name: "{app}\App"
Type: filesandordirs; Name: "{app}\Lanzador"

[UninstallDelete]
; Lo que crea la ejecucion y no el instalador (el perfil de WebView2 que la aplicacion deja dentro
; de su carpeta, restos de una actualizacion cortada).
Type: filesandordirs; Name: "{app}\App"
Type: filesandordirs; Name: "{app}\Lanzador"
Type: filesandordirs; Name: "{app}\Anterior"
Type: dirifempty; Name: "{app}"

; ============================================================================
[Code]
#include "codigo.iss"
