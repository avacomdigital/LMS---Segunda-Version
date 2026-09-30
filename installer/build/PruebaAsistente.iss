; ============================================================================
;  Arnés de prueba del código del asistente.
;
;  Compila EXACTAMENTE la misma lógica que el instalador de verdad
;  (installer\src\codigo.iss), pero sin nada que instalar y sin pedir permisos
;  de administrador. Ejecutado con:
;
;      PruebaAsistente.exe /VERYSILENT /VOLCADO=<archivo>
;
;  corre las diez comprobaciones del equipo en un Windows real, escribe el
;  resultado en <archivo> y aborta sin tocar nada.
;
;  Sirve para lo que un compilador no puede comprobar: que Pascal Script no
;  falle en tiempo de ejecución al partir la salida de netstat, al preguntar a
;  /health/ por COM, al leer el registro o al crear los controles de la página
;  táctil.
;
;  Lo lanza Verificar-Asistente.ps1. No forma parte del paquete distribuido.
; ============================================================================

#include "..\src\definiciones.iss"

[Setup]
AppId={{E1A2C3D4-0000-4000-8000-PRUEBAASIST}
AppName=Prueba del asistente de AVACOM OPS Master
AppVersion={#VersionProducto}
DefaultDirName={localappdata}\AVACOM\prueba-asistente
DefaultGroupName=Prueba AVACOM
; Sin administrador: el arnés no instala nada y así se puede ejecutar en
; cualquier sesión.
PrivilegesRequired=lowest
Uninstallable=no
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=PruebaAsistente
Compression=none
WizardStyle=modern
WizardSizePercent=150
ShowLanguageDialog=no
AllowNoIcons=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
; La lógica compartida toca WizardForm.TasksList: tiene que existir una tarea.
Name: "iconoescritorio"; Description: "Sin efecto en la prueba"

; ============================================================================
[Code]
#include "..\src\codigo.iss"
