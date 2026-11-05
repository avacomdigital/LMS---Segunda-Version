# QA 01 · Instalación del kiosco de AVACOM Student por cable USB (ADB)

| Campo | Valor |
|---|---|
| Código | QA-INST-KIOSK-01 |
| Tipo | Prueba de instalación / diagnóstico de entorno |
| Fecha del informe | 2026-11-05 |
| Equipo de pruebas | Computador Windows AVACOM (Windows 11 Pro) |
| Tableta de pruebas | Android 14, SoC Rockchip (`VID_2207&PID_0017`) |
| Resultado global | **BLOQUEADO** — `adb devices -l` no lista el dispositivo |
| Estado | Abierto. Causa raíz no confirmada; hipótesis principal en la sección 8 |

---

## 1. Objetivo

Verificar que un computador AVACOM puede instalar el kiosco de AVACOM Student en una tableta Android mediante ADB sobre cable USB, como paso previo a una instalación masiva realizada por personal interno, técnico y terceros oficiales.

## 2. Alcance

**Incluye:** detección de la tableta por ADB en Windows; diagnóstico del controlador USB; alternativas de instalación sin cable.
**No incluye:** la instalación del APK, el modo kiosco ni el aprovisionamiento Device Owner. Todo ello depende de que ADB vea la tableta y no pudo ejecutarse.

## 3. Precondiciones y configuración

### 3.1 Computador Windows

| Elemento | Estado | Evidencia |
|---|---|---|
| Google USB Driver 13 (Android Studio SDK Manager) | Instalado; el instalador reporta éxito | Verificado también por PowerShell |
| `adb.exe` en el `PATH` | OK | `Get-Command adb` → `C:\Users\AVACOM\AppData\Local\Android\Sdk\platform-tools\adb.exe` |
| Servidor ADB | Arranca (`daemon started successfully`) | `adb start-server` |

### 3.2 Tableta

| Elemento | Estado |
|---|---|
| Modo desarrollador | Activo |
| Depuración USB | Activa |
| Modo USB | Transferencia de archivos (MTP) |
| Conexión con el computador | Comprobada; la transferencia de archivos funciona |

## 4. Procedimiento ejecutado y resultado

| # | Paso | Comando | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|---|
| 1 | Ubicar `adb.exe` | `Get-Command adb` | Ruta de `platform-tools` | Ruta correcta (ver 3.1) | OK |
| 2 | Listar dispositivos | `adb devices -l` | Una fila con estado `device` | `List of devices attached` **vacío** | **FALLA** |
| 3 | Reiniciar el servidor ADB | `adb kill-server` · `adb start-server` · `adb devices -l` | Dispositivo listado | Lista vacía | **FALLA** |
| 4 | Ver si Windows enumera la tableta | `Get-PnpDevice -PresentOnly` (filtro Android/ADB/MTP/USB) | Dispositivo y/o interfaz ADB | Aparece la tableta y su interfaz ADB (ver 5) | OK |
| 5 | Buscar dispositivos con error | `Get-PnpDevice -PresentOnly` con `Status -ne OK` | Sin errores relacionados con la tableta | Sólo `RM520N-GL` (módem, otro hardware) y dos dispositivos de audio; **ninguno es la tableta** | OK |
| 6 | Identificar el controlador de la interfaz ADB | `Get-CimInstance Win32_PnPSignedDriver` filtrado por `VID_2207&PID_0017&MI_01` | Controlador de ADB | `WinUSB Device` · Microsoft · 10.0.26100.9549 · `winusb.inf` | Informativo |

Nota: el intento `adb.exe list` (paso fuera de la secuencia) devolvió `unknown command list`. Es un error de uso (no existe ese subcomando), no un fallo del entorno.

## 5. Hallazgos

### H-01 · La tableta y su interfaz ADB están presentes en Windows

```
OK  USBDevice  ADB Interface            USB\VID_2207&PID_0017&MI_01\8&77DAD17&0&0001
OK  USB        Dispositivo compuesto USB USB\VID_2207&PID_0017\AVT015202515603
```

| Propiedad | Valor |
|---|---|
| Fabricante USB | Rockchip (`VID_2207`) |
| Product ID | `0017` |
| Interfaz ADB | `MI_01`, estado `OK` |
| Transferencia de archivos | Funciona |

Conclusión: el problema **no** es cable, puerto ni alimentación; la capa física y la enumeración USB funcionan.

### H-02 · El controlador asociado a la interfaz ADB es el genérico de Microsoft

Windows enlazó la interfaz con `winusb.inf` y **no** con el Google USB Driver 13 instalado. Eso es esperable: el Google USB Driver está pensado para dispositivos de Google y sólo coincide con los `VID/PID` de su `.inf`. Un dispositivo Rockchip genérico queda con WinUSB (instalación automática del sistema).

WinUSB no es por sí mismo incorrecto: ADB puede operar sobre WinUSB. Pero que Windows muestre la interfaz como `OK` no demuestra que ADB pueda abrirla y negociar con ella.

### H-03 · ADB no obtiene respuesta del dispositivo

El servidor ADB arranca bien y aun así la lista permanece vacía, incluso tras `kill-server`. No aparece ni `unauthorized` ni `offline`: el dispositivo ni siquiera llega a listarse, por lo que el diálogo «¿Permitir depuración USB?» no se produce.

### H-04 · Dispositivos con error ajenos al caso

`RM520N-GL` (módem USB), `BT LE Sideband device` e `Intel High Definition Audio` están en estado `Error`. No corresponden a la tableta y no se consideran causa del defecto. Se registran para no confundirlos en futuras revisiones.

## 6. Pruebas pendientes de diagnóstico (en orden recomendado)

No se debe cambiar ni desinstalar el controlador WinUSB hasta agotar las pruebas no intrusivas.

| # | Prueba | Comandos | Qué se descarta o confirma |
|---|---|---|---|
| D-1 | Versión de ADB instalada | `adb version` | Punto de partida; permite compararla con la más reciente |
| D-2 | Platform-Tools actual en carpeta aislada (sin reemplazar la instalación existente) | Descargar `https://dl.google.com/android/repository/platform-tools-latest-windows.zip` a `$env:TEMP\adb-test`, extraer y ejecutar `adb kill-server; adb version; adb devices -l` con ese `adb.exe` | Incompatibilidad entre ADB antiguo y el backend USB de Windows. Hay reportes de que Platform-Tools 37.0.1 incorporó un backend USB nuevo (`libadbusb`) y un síntoma idéntico se resolvió actualizando |
| D-3 | Backend USB heredado | `$env:ADB_USB_LEGACY = "1"`; `adb kill-server; adb start-server; adb devices -l`. Revertir con `Remove-Item Env:\ADB_USB_LEGACY` | Si el fallo es del backend nuevo, el heredado lo evita (sólo aplica a ADB ≥ 37.0.1) |
| D-4 | La interfaz USB anuncia el protocolo ADB | `Get-PnpDeviceProperty -InstanceId <MI_01> -KeyName DEVPKEY_Device_CompatibleIds` | Se espera `USB\Class_FF&SubClass_42&Prot_01`. Si falta, el firmware no expone una interfaz ADB estándar |
| D-5 | Reautorizar la depuración | En la tableta: desactivar Depuración USB → «Revocar autorizaciones de depuración USB» → reactivar → reconectar con la pantalla desbloqueada → `adb kill-server; adb devices -l` | Descarta una autorización corrupta (poco probable dado H-03) |
| D-6 | Otro cable y otro puerto USB, y otro computador AVACOM | — | Descarta el equipo concreto |
| D-7 | Depuración inalámbrica (Android 11+) | Tableta: Opciones de desarrollador → Depuración inalámbrica → Vincular con código. PC: `adb pair IP:PUERTO_VINCULACION` · `adb connect IP:PUERTO` · `adb devices -l` | Verifica que ADB funciona sin depender del controlador USB. Ver 7 |

Criterio de salida de D-1…D-6: `adb devices -l` devuelve la tableta con estado `device` y `adb shell getprop ro.product.model` responde.

## 7. Alternativas a la instalación por cable USB

Restricciones de uso, definidas por AVACOM:

- Los computadores del equipo interno, técnicos y terceros oficiales normalmente **sí tienen acceso a Internet**.
- El personal **no es de programación**: cualquier herramienta debe ser un **script autoejecutable** (doble clic) con su propia lógica, sin pasos manuales de desarrollo.

Alternativas ya presentes en el repositorio (`scripts/android/`):

| Alternativa | Ubicación | Depende del USB | Notas |
|---|---|---|---|
| ADB inalámbrico | `1-adb-inalambrico/` | No | Requiere vincular una vez por tableta |
| APK servido por la LAN | `2-apk-por-lan/` | No | La tableta descarga e instala el APK desde la red local |
| ADB en lote | `3-adb-lote/` | No (por IP) | Instalación sobre una lista de tabletas |
| Aprovisionamiento Device Owner por QR | `Provision-DeviceOwner.ps1`, `New-DeviceOwnerQr.py` | No | Para dejar la tableta administrada desde el arranque |
| Flota AMAPI | `amapi/` | No | Administración masiva vía Android Management API |
| Instalador unitario | `Instalar-StudentEnTableta.ps1` | Depende del modo | Ejecutable por personal no técnico |

Todas evitan que el flujo dependa del controlador USB del equipo; son las candidatas para el despliegue masivo.

## 8. Conclusión y sospecha

La instalación por cable USB **no pudo completarse**: el computador AVACOM no ve la tableta por ADB aunque Windows la enumera correctamente, la transferencia de archivos funciona y ADB corre sin errores.

**Se sospecha que los computadores AVACOM no cuentan con los drivers y firmwares adecuados para realizar esta instalación masiva por medio de cable USB.** En concreto:

1. La interfaz ADB de la tableta Rockchip usa el controlador genérico `winusb.inf`, y el Google USB Driver 13 no se asocia a ella (H-02); no hay un controlador del fabricante de la tableta instalado en estos equipos.
2. La versión de ADB (`platform-tools`) instalada podría no ser compatible con el backend USB de Windows para este firmware (D-1…D-3).
3. El firmware de la tableta podría no anunciar la interfaz ADB de forma estándar (D-4).
4. Se sugiere revisar opciones de instalación que no use USB para realizar la instalación del Kiosk

La instalación masiva por USB exigiría estandarizar driver, `platform-tools` y firmware en cada computador AVACOM, lo cual es costoso y poco viable para personal no técnico. 