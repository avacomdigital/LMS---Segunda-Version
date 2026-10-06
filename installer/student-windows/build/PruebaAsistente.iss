; ============================================================================
;  Arnés de prueba del código del asistente de AVACOM Student.
;
;  Compila EXACTAMENTE la misma lógica que el instalador de verdad
;  (installer\student-windows\src\codigo.iss), pero sin nada que instalar y sin pedir permisos de
;  administrador. Ejecutado con:
;
;      PruebaAsistente.exe /VERYSILENT /VOLCADO=<archivo>
;
;  corre las ocho comprobaciones del equipo en un Windows real, escribe el resultado en <archivo> y
;  aborta sin tocar nada.
;
;  Sirve para lo que un compilador no puede comprobar: que Pascal Script no falle en tiempo de
;  ejecución al consultar el registro, al listar procesos o al crear los controles de la página.
;
;  Lo lanza Build-StudentInstaller.ps1. No forma parte del paquete distribuido.
; ============================================================================

#include "..\src\definiciones.iss"

[Setup]
AppId={{E1A2C3D4-0000-4000-8000-ESTUDIANTEPR}
AppName=Prueba del asistente de AVACOM Student
AppVersion={#VersionProducto}
DefaultDirName={localappdata}\AVACOM\prueba-asistente-student
DefaultGroupName=Prueba AVACOM Student
; Sin administrador: el arnés no instala nada y así se puede ejecutar en cualquier sesión.
PrivilegesRequired=lowest
Uninstallable=no
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=PruebaAsistenteStudent
Compression=none
WizardStyle=modern
WizardSizePercent=150
ShowLanguageDialog=no
AllowNoIcons=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

; ============================================================================
[Code]
#include "..\src\codigo.iss"
