; Valores compartidos por el instalador de Student (AvacomStudent.iss) y por su arnes de
; diagnostico (build\PruebaAsistente.iss). Se definen una sola vez para que el arnes no pueda
; comprobar algo distinto de lo que se instala de verdad.

#define NombreProducto      "AVACOM Student"
#define NombreCorto         "Student"
#define Fabricante          "AVACOM"
; La version del producto sale de installer\version.json (Build-StudentInstaller.ps1 la inyecta con
; /DVersionProducto). Este valor solo sirve si alguien compila el .iss a mano.
#ifndef VersionProducto
  #define VersionProducto   "2.3.0"
#endif
#define UrlProducto         "https://github.com/avacomdigital/lms-prototype-v04"
#define EjecutableApp       "Avacom.Lms.Student.exe"
#define EjecutableLanzador  "Avacom.Student.Lanzador.exe"

; El identificador de instalacion de Student. NO CAMBIA entre versiones (asi una version nueva se
; reconoce como actualizacion) y NO es el de OPS Master ni el de AVACOM Contenido.
#define IdInstalacion       "{4C2DB723-841F-4620-BBE3-8F5CC7E57D1D}"

; Carpeta preparada por Build-StudentInstaller.ps1. Se puede sobrescribir con ISCC /DCarpetaContenido=...
#ifndef CarpetaContenido
  #define CarpetaContenido  "..\..\..\dist\student-windows\staging"
#endif
#ifndef CarpetaSalida
  #define CarpetaSalida     "..\latest"
#endif
#ifndef Revision
  #define Revision          "sin-revision"
#endif
