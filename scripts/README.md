# Scripts de aprovisionamiento del bloqueo de examen

Scripts para dejar un equipo (Windows) o una tableta (Android) listo para el examen de AVACOM LMS: la **capa del sistema operativo** del bloqueo descrita en `spec-driven/06-evaluation-delivery/kiosk.md` (§3.5, §4.5, §4.6, §5.1, §5.3 y §7). La capa de aplicación (pantalla completa, gancho de teclado, rechazo del cierre) vive en la propia Student y no se instala desde aquí.

> **Lee primero la sección «NO PROBADO EN HARDWARE».** Nada de lo que hay aquí se ha ejecutado de verdad sobre Assigned Access, Shell Launcher ni una tableta.

## Qué hay

| Archivo | Para qué sirve |
|---|---|
| `windows/Install-Kiosk.ps1` | Assigned Access **multiaplicación** con una aplicación de escritorio permitida (`DesktopAppPath`). Camino principal en Windows Pro, Enterprise, Education e IoT. |
| `windows/Install-ShellLauncher.ps1` | Alternativa con **Shell Launcher v2** (solo Enterprise, Education, IoT; **no** Pro). |
| `windows/Remove-Kiosk.ps1` | Revierte Assigned Access y, con `-DisableShellLauncher`, Shell Launcher. Conserva la cuenta y sus datos. |
| `windows/Kiosk.Common.ps1` | Funciones compartidas. Lo cargan los tres anteriores: **copia siempre los cuatro archivos juntos**. |
| `android/Provision-DeviceOwner.ps1` | Convierte la app en Device Owner de **una** tableta por ADB, con todas las comprobaciones previas. |
| `android/New-DeviceOwnerQr.py` | Genera el JSON (y el PNG si hay `qrcode`) del QR de aprovisionamiento para **muchas** tabletas. |
| `android/device-owner-qr.template.json` | Plantilla del JSON del QR (sin claves de ningún tipo). |

Datos de la Student que usan los scripts:

- Android: `applicationId` `com.avacom.lms.student`; receptor `com.avacom.lms.student/com.avacom.lms.student.ExamDeviceAdminReceiver`.
- Windows: la Student es un **ejecutable de escritorio sin empaquetar** (`WindowsPackageType None`): no es MSIX y no tiene AUMID. Por eso Assigned Access se aplica en su forma multiaplicación con `DesktopAppPath`; la forma de una sola app `Set-AssignedAccess -AppUserModelId` **no** sirve. La ruta del ejecutable instalado se desconoce de antemano y es un parámetro obligatorio (`-ExecutablePath`). Ejemplo de ayuda: `C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe`.

## Reglas que cumplen todos los scripts

- **`-DryRun`**: muestra lo que haría y **no modifica nada**. En Windows funciona sin administrador y escribe solo en consola (ni usuarios, ni registro, ni WMI, ni archivos). En Android imprime los comandos `adb` y **no llama a adb en absoluto**.
- **`-Verify`** (`Install-*`, `Provision-DeviceOwner`): solo lectura; consulta el **estado real** del sistema, no el marcador.
- El modo real de Windows **se niega a ejecutarse sin consola elevada**, comprueba la edición de Windows y exige una **cuenta administradora de recuperación distinta** de la del kiosco (aborta si el usuario del kiosco es administrador o es el único administrador).
- Las contraseñas **nunca** se escriben, imprimen ni registran. Una cuenta nueva pide la contraseña con `Read-Host -AsSecureString` (o llega por `-Password` como `SecureString`).
- Registro (solo en modo real): `%ProgramData%\AVACOM\logs\kiosk-install.log` (instalación) y `kiosk-remove.log` (reversión).
- **Códigos de salida**: `0` correcto / aprovisionado; `1` error, bloqueo o **no** aprovisionado; `2` (solo `-Verify` en Windows) no se pudo comprobar el estado real sin privilegios de administrador.

## Orden exacto en un aula

### Android (una tableta por ADB)

1. **Restablecer de fábrica** la tableta. Durante el asistente **no inicies sesión en ninguna cuenta**: Android solo concede Device Owner a un equipo con `Accounts: 0`, un único usuario y sin propietario previo.
2. Activar *Opciones de desarrollador* y *Depuración por USB*; conectar por cable y aceptar la clave RSA. Con ADB inalámbrico hay que emparejar antes (`adb pair <ip:puerto-de-emparejamiento> <código>`; el puerto de emparejamiento no es el de conexión).
3. **Instalar el APK**: `adb install -r Student.apk`. El receptor debe llamarse exactamente `com.avacom.lms.student.ExamDeviceAdminReceiver` o `set-device-owner` falla.
4. Simular y revisar: `.\android\Provision-DeviceOwner.ps1 -DryRun`.
5. Aprovisionar (**irreversible**; pide teclear el número de serie): `.\android\Provision-DeviceOwner.ps1 -Serial <serie>`. Con varias tabletas conectadas `-Serial` es obligatorio.
6. Verificar: `.\android\Provision-DeviceOwner.ps1 -Serial <serie> -Verify`. Debe terminar con código `0` y nombrar el paquete. Después, a mano y con la tableta en examen: Inicio, Recientes, deslizar desde arriba, Atrás y mantener el botón de encendido.

El script solo ejecuta `dpm set-device-owner` si **todas** las comprobaciones previas pasan (app instalada, `Accounts: 0`, `no owners`, un solo `UserInfo`) y después exige que `dpm list-owners` **nombre el paquete**: un «Success» suelto no basta.

### Android (muchas tabletas, por QR, sin cable)

```powershell
python .\android\New-DeviceOwnerQr.py --apk C:\ruta\Student.apk --url https://servidor/Student.apk --out C:\ruta\salida
```

Calcula el SHA-256 del APK en Base64 URL-safe **sin relleno**, rellena la plantilla (componente, URL de descarga, checksum y `PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED=false`) y valida su salida. Escribe `device-owner-qr.json` y, si `qrcode` está instalado (`python -m pip install "qrcode[pil]"`), `device-owner-qr.png`; si no, imprime el JSON para pegarlo en cualquier generador de QR. No usa la red. En la primera pantalla del asistente de una tableta recién restablecida: tocar seis veces y escanear.

- Wi-Fi opcional: `--wifi-ssid RED --wifi-password -` (el `-` pide la clave por teclado sin mostrarla). **La clave queda en claro en el JSON y en el QR**: trata la carpeta de salida como secreta y no la subas al repositorio. La plantilla no lleva ninguna clave.
- Para flotas grandes y permanentes el camino es Android Management API o Zero-touch, no este QR.

### Windows (Assigned Access, camino principal)

Todo desde una consola de PowerShell **como administrador** en la carpeta `scripts`. Si copiaste los archivos desde un ZIP o una descarga: `Get-ChildItem .\windows | Unblock-File`; y, solo para esa consola, `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

1. **Usuario estándar**: no hace falta crearlo a mano, `Install-Kiosk.ps1` lo crea si falta (pide la contraseña). Si prefieres crearlo tú, que sea **estándar** (nunca administrador). Confirma que existe **otra** cuenta administradora habilitada: es tu recuperación.
2. Instalar la Student de Windows en su ruta definitiva y anotar la ruta del `.exe` (debe ser legible por el usuario del kiosco; `C:\Program Files\...` lo es).
3. **Simular**: `.\windows\Install-Kiosk.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -DryRun`. Revisa el XML impreso y que no haya líneas `[ERROR]`.
4. **Ejecución real**: el mismo comando **sin** `-DryRun`. Pide teclear `APLICAR` (o usa `-Force`).
5. **Reiniciar** e iniciar sesión como el usuario del kiosco: la Student se abre sola (`AutoLaunch`).
6. **Verificar** (como administrador, otra sesión): `.\windows\Install-Kiosk.ps1 -ExecutablePath '<ruta>' -Verify`. Código `0` = aprovisionado; `1` = no aprovisionado; `2` = no se pudo comprobar sin privilegios.

Si la sede es Enterprise/Education/IoT y prefieres Shell Launcher: `.\windows\Install-ShellLauncher.ps1 -ExecutablePath '<ruta>' -DryRun`; si la característica `Client-EmbeddedShellLauncher` está desactivada el script **no la activa en silencio**: muestra el comando exacto (`Enable-WindowsOptionalFeature -Online -FeatureName Client-EmbeddedShellLauncher -All -NoRestart`) o la activa con `-EnableFeature` (puede pedir reinicio; reinicia y vuelve a ejecutarlo).

## Cómo deshacer

- **Windows**: `.\windows\Remove-Kiosk.ps1 -DryRun` y luego `.\windows\Remove-Kiosk.ps1`. Con Shell Launcher: `-DisableShellLauncher` (y `-DisableFeature` para apagar también la característica; requiere reinicio). **Conserva siempre la cuenta y sus datos.** Cierra sesión o reinicia; después `Install-Kiosk.ps1 ... -Verify` debe decir «NO APROVISIONADO».
  - Assigned Access tiene **una sola configuración por equipo** (`MDM_AssignedAccess`): borrarla la quita para todas las cuentas, por eso se detiene si incluye a otras cuentas salvo `-Force`. Aplicar una nueva también la reemplaza.
  - Si no puedes iniciar sesión como el kiosco ni se aplica nada: entra con la cuenta administradora de recuperación y ejecuta `Remove-Kiosk.ps1`.
- **Android**: Device Owner **solo se deshace con un restablecimiento de fábrica** (con pérdida de datos). La salida administrativa de la Student (siete toques en dos segundos sobre el título y un PIN local) detiene Lock Task pero **no** quita Device Owner.

## Interruptor de desarrollo `AVACOM_EXAM_NO_LOCKDOWN=1`

Variable de entorno que lee `WindowsKioskService` de la Student (kiosk.md §4.6): mantiene la **pantalla completa**, pero **no instala el gancho de teclado de bajo nivel, no cubre los monitores adicionales y permite cerrar la ventana**. Es indispensable en un equipo de desarrollo porque el gancho es global y, probando panel y examen en la misma máquina, no habría forma de volver al panel con Alt+Tab.

```powershell
$env:AVACOM_EXAM_NO_LOCKDOWN = '1'      # solo para esta consola; luego lanza la Student desde ella
```

En los equipos de la sede la variable **no se define** (no la pongas con `setx` ni en el perfil del usuario del kiosco). No sustituye a Assigned Access ni a Shell Launcher: no afecta a la capa del sistema.

## Decisiones de diseño que conviene conocer

- **El marcador es solo un indicio** (kiosk.md §5.1). `%ProgramData%\AVACOM\kiosk-provisioned.marker` (JSON con `mode`, `user`, `executablePath`, `appliedAtUtc`, `configSha256`) lo escribe el instalador **después** de aplicar, y es lo que la Student comprueba. Si alguien borra la política y deja el archivo, la Student se creerá aprovisionada. Por eso existe `-Verify`, que consulta el sistema: primero `MDM_AssignedAccess.Configuration` (necesita administrador) y, si no se puede leer, el almacén del sistema en `HKLM\SOFTWARE\Microsoft\Windows\AssignedAccessConfiguration` (legible sin privilegios; búsqueda de texto, **heurística**). Para Shell Launcher consulta `WESL_UserSetting`.
- **Escritura por el puente MDM**: `root\cimv2\mdm\dmmap`, clase `MDM_AssignedAccess`, propiedad `Configuration` (cadena con el XML escapado). Ese puente suele exigir la cuenta SYSTEM: el script lo intenta como administrador y, si falla, reintenta como SYSTEM con una **tarea programada de un solo uso** (carpeta de trabajo con ACL solo SYSTEM + Administradores, que se borra al terminar junto con la tarea).
- **Lista de aplicaciones permitidas**: solo la Student (`rs5:AutoLaunch`). Si Windows bloquea procesos auxiliares (por ejemplo el de WebView2), añádelos con `-AdditionalAllowedPaths` (rutas absolutas).
- **Idioma**: las consultas de cuentas usan SID (`S-1-5-32-544`), no nombres de grupo, y no dependen del idioma de Windows.

## NO PROBADO EN HARDWARE

**Todo lo siguiente se escribió a partir de la documentación y NO se ha ejecutado en un equipo ni en una tableta reales.** No des por válido ninguno de estos puntos hasta probarlo en un equipo de pruebas con una cuenta de recuperación y con acceso físico.

- **Assigned Access con `DesktopAppPath`**: el XML (espacios de nombres 2017 y `rs5`, `AutoLaunch`, `Taskbar ShowTaskbar="false"`, **sin** `StartLayout`/`StartPins`), su aceptación por Windows 11, que la Student arranque sola, que el resto del escritorio quede bloqueado y si hacen falta ejecutables adicionales (WebView2). Si Windows rechaza la configuración por falta de `StartLayout`/`StartPins`, habrá que añadirlos.
- **La escalada a SYSTEM** con tarea programada y el borrado con cadena vacía en `Remove-Kiosk.ps1` (más el refuerzo `Clear-AssignedAccess`).
- **Lectura del estado real**: en el equipo de desarrollo (Windows 11 Pro) se comprobó que `MDM_AssignedAccess` responde «Acceso denegado» sin elevación y que el almacén del registro existe y está vacío sin configuración. **No** se ha visto cómo queda el registro en un equipo con Assigned Access aplicado; por eso esa vía es heurística.
- **Shell Launcher v2**: las llamadas WMI (`SetCustomShell`, `SetDefaultShell`, `SetEnabled`, `RemoveCustomShell`), la activación de `Client-EmbeddedShellLauncher` y el comportamiento al cerrarse el shell. Shell Launcher no está disponible en Pro; y según la documentación de Microsoft **no oculta por sí solo las opciones de Ctrl+Alt+Supr** (Administrador de tareas), que estos scripts no restringen: el texto de kiosk.md §4.5 que dice que cierra también esa vía debe validarse.
- **Android**: el formato real de la salida de `dpm list-owners`, `dumpsys account`, `pm list users` y `dumpsys activity activities` en tu versión de Android; el script y los analizadores se probaron con **adb simulado**, no con una tableta. El `set-device-owner` por ADB sí se probó a mano en una tableta Android 14 según kiosk.md, pero **este script no**.
- **Flujo de QR**: ni el escaneo ni la descarga/validación del APK por el asistente de Android se han ejercitado. La generación del PNG solo se probó con un módulo `qrcode` simulado (la biblioteca no estaba instalada).
- **El receptor `ExamDeviceAdminReceiver` aún no existe en `src/Avacom.Lms.Student`** en el momento de escribir esto: sin esa clase, con ese nombre exacto, `dpm set-device-owner` fallará.

### Límites que ningún script puede resolver

- **Ctrl+Alt+Supr no se puede interceptar desde ninguna aplicación**; solo una política de cuenta lo cierra (Assigned Access lo restringe; con Shell Launcher hay que validarlo).
- **El apagado forzado por hardware** (mantener el botón de encendido) no lo impide ningún software, en Android ni en Windows.
- El **marcador de aprovisionamiento es un indicio**, no una comprobación (ver arriba).
- Android es de una sola pantalla: no hay equivalente al bloqueador de monitores. No se contemplan capturas de pantalla, grabación, portapapeles ni USB.

## Qué sí se verificó al escribir los scripts

En el equipo de desarrollo (Windows 11 Pro, Windows PowerShell 5.1, sin elevación, sin modificar nada):

- Los cinco `.ps1` se analizan con `[System.Management.Automation.Language.Parser]::ParseFile` con 0 errores; se guardan en UTF-8 **con BOM** (PowerShell 5.1 lee el UTF-8 sin BOM como ANSI) y el texto acentuado de la ayuda se lee intacto.
- Cada script se ejecutó **solo con `-DryRun`** (y `Install-*` además con `-Verify`): sin archivos nuevos en `%ProgramData%\AVACOM` ni usuarios nuevos.
- La lógica del modo real (confirmaciones, bloqueos, orden de operaciones, qué se escribe y cuándo) se ejercitó con **simulacros** de las funciones que modifican el sistema y de `adb`, nunca contra el sistema real.
- `New-DeviceOwnerQr.py`: el checksum coincide con un SHA-256 Base64 URL-safe sin relleno calculado de forma independiente con .NET; el JSON se valida a sí mismo.
