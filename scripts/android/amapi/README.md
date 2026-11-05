# Kiosco masivo en Android 14 · Android Management API (AMAPI)

Vía oficial de Google para dejar 50 tabletas por aula como **dispositivos dedicados**: Android Device Policy es el Device Owner, la Student se instala desde Google Play administrado y se fija como kiosco **por política**. Sustituye al `adb set-device-owner` y al QR propio de `../New-DeviceOwnerQr.py`, que quedan solo para desarrollo.

`kiosk_fleet.py` cubre el trabajo repetible; hay pasos que son de una sola vez y manuales (más abajo).

## Orden de trabajo

| # | Quién | Qué |
|---|---|---|
| 0 | AVACOM | Proyecto de Google Cloud con la API **Android Management** habilitada y una cuenta de servicio (JSON). |
| 1 | AVACOM | `python kiosk_fleet.py signup-url --project P --callback https://…` |
| 2 | Administrador del cliente | Abre esa URL con su cuenta de Google y acepta; Google devuelve `enterpriseToken` en la callback. |
| 3 | AVACOM | `python kiosk_fleet.py create-enterprise --project P --signup-url-name … --enterprise-token … --name "Colegio X"` |
| 4 | AVACOM | **Publicar la Student como app privada** en Google Play administrado (manual, ver abajo). |
| 5 | AVACOM | `python kiosk_fleet.py apply-policy --enterprise LC0xxxx` |
| 6 | Técnico | `python kiosk_fleet.py enrollment-token --enterprise LC0xxxx --etiqueta "Aula 3B" --wifi-ssid RED` |
| 7 | Técnico | Cada tableta, restablecida de fábrica: tocar 6 veces la pantalla de bienvenida y escanear el QR; **o** zero-touch (sin tocar nada). |
| 8 | Técnico | `python kiosk_fleet.py devices --enterprise LC0xxxx` hasta que diga 0 «NO listas». |

Todos los comandos aceptan `--dry-run` (antes del subcomando): muestran la petición y no llaman a Google. Empieza siempre por ahí.

```powershell
pip install google-auth requests "qrcode[pil]"
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\ruta\cuenta-servicio.json'
$env:AVACOM_WIFI_PASSWORD = '…'       # solo si el QR debe llevar la clave del Wi-Fi
python kiosk_fleet.py --dry-run apply-policy --enterprise LC0xxxx
python -m unittest test_kiosk_fleet   # 28 pruebas de la lógica, sin red
```

## Las cuatro vías

1. **AMAPI + QR**: pasos 6 y 7. El QR sirve para todas las tabletas de un aula mientras el token no venza (`--duration`, 7 días por defecto; **no** uses `--one-time` para 50).
2. **Zero-touch**: `enrollment-token` también escribe `zero-touch-dpc-extras.json`. Se pega en «DPC extras» de la configuración del portal de zero-touch, con el DPC **Android Device Policy**. Las tabletas deben comprarse a un revendedor autorizado, que las registra en el portal. Usa un token de vigencia larga (`--duration 365d`) y renuévalo antes de que venza.
3. **MDM comercial** (Intune, Workspace ONE, SOTI, Hexnode, Knox Manage): este script no los maneja. Sirve de **especificación**: reproduce en su consola los valores de `construir_politica()` (rol KIOSK, navegación, barra de estado, ajustes y botón de encendido bloqueados, etc.).
4. **Samsung Knox Mobile Enrollment**: se carga el lote de tabletas por número de serie o IMEI en el portal de Knox y se apunta al mismo token o al MDM elegido. Tampoco lo maneja este script.

## Lo que el script NO hace (pasos manuales)

- **Publicar la app.** La Student debe existir como **app privada** de la empresa en Google Play administrado (Play Console → app privada, o el iframe de Play administrado). Hay que subir el APK/AAB firmado con la clave de producción. Hasta entonces la política no tiene qué instalar. El `applicationId` debe coincidir con `--package` (`com.avacom.lms.student`).
- **Crear la cuenta de servicio y el proyecto de Google Cloud.**
- **Comprar las tabletas para zero-touch** y registrarlas en el portal.

## Cambio necesario en la Student (no hecho)

Hoy `AndroidKioskService` espera ser el Device Owner: llama a `SetLockTaskPackages`, `SetLockTaskFeatures` y `AddUserRestriction` con **su propio** receptor. Con AMAPI el Device Owner es Android Device Policy, así que esas llamadas **fallarán**. Hay que:

1. Detectar quién es el propietario (`IsDeviceOwnerApp` será `false`) y, si la app es el kiosco por política (`DevicePolicyManager.getLockTaskPackages` / `isLockTaskPermitted`), **solo llamar a `StartLockTask`** y reportar la capa del sistema como aplicada.
2. Quitar de la app lo que ahora lo decide la política (`SetLockTaskFeatures`, `DisallowCreateWindows`).
3. Mantener lo de `MainActivity` (Atrás, pantalla inmersiva).
4. Ajustar `AprovisionamientoWindows`/la capacidad que se declara al nodo: una tableta bajo AMAPI debe declarar `controlado`.

Mientras eso no se haga, una tableta inscrita con este script queda bloqueada **por la política** pero la Student declarará `abierto` o `supervisado` al nodo.

## Verificar en una tableta real (Android 14), antes de las 50

1. Restablecer de fábrica y escanear el QR: debe descargar la Student y arrancar sola.
2. Probar con el examen en curso: Inicio, Recientes, deslizar desde arriba, Atrás, Ajustes, botón de encendido (menú), captura de pantalla.
3. `devices` debe listarla como lista y con `versionName` de la app.
4. Publicar una versión nueva y ver que llega sola.
5. Empujar un cambio de política y ver que se aplica.

## Wi-Fi y recuperación de una tableta sin red

La política bloquea Ajustes: una tableta que pierde la red **no se puede reconectar a mano**. Hay dos salidas, y conviene tener la primera puesta desde el principio.

1. **Red por política (recomendada).** Crea un archivo `wifi.json` (secreto; en `.gitignore`, no lo subas) en formato ONC y empújalo; las tabletas ya inscritas lo reciben solas y se unen a la red aunque la anterior haya desaparecido:
   ```json
   {"Type": "UnencryptedConfiguration", "NetworkConfigurations": [
     {"GUID": "aula", "Name": "Aula", "Type": "WiFi",
      "WiFi": {"SSID": "RED", "Security": "WPA-PSK", "Passphrase": "…", "AutoConnect": true}}]}
   ```
   `python kiosk_fleet.py --dry-run apply-policy --enterprise LC0xxxx --wifi-json wifi.json` (la clave sale como `***`), y luego sin `--dry-run`. El script valida GUID, Name, `Type = WiFi`, SSID, `Security` (`None`, `WEP-PSK`, `WPA-PSK`, `WPA-EAP`) y que haya clave si la red la exige. Una política con red que cambia de clave se vuelve a aplicar con el mismo comando.
2. **Reinscripción.** Si la tableta nunca recibió la red (o la política no llega porque no tiene red), se restablece de fábrica (desde el cargador de arranque / recuperación, porque el restablecimiento desde Ajustes está bloqueado) y se vuelve a inscribir con un QR nuevo que lleve la red (`enrollment-token --wifi-ssid RED`, con la clave en `AVACOM_WIFI_PASSWORD`) o por zero-touch.

La red por política **no se probó contra Google**: el formato ONC y que `openNetworkConfiguration` acepte este contenido en el campo de la política salen de la referencia consultada, sin ejecución real. La política no puede alcanzar una tableta que no tiene ninguna red: la primera conexión siempre es por el QR (o por una red que ya traiga la tableta).

## Qué hace la Student según quién sea el propietario (Android)

`AndroidKioskService` consulta a `DevicePolicyManager` y distingue: **propietario propio** (`IsDeviceOwnerApp`, instalación por ADB): autoriza Lock Task, quita las funciones, restringe ventanas y fija; **propietario ajeno** (Android Device Policy, la app en la lista de Lock Task de la política: `IsLockTaskPermitted`): solo `StartLockTask`/`StopLockTask`; **ninguno**: nivel `supervisado`/`abierto` como siempre. Declara `controlado` solo si el sistema lo permite y, tras fijar, comprueba que quedó `LOCKED`. El caso de propietario ajeno solo se probó por simulación o no se probó (ver el informe de la sesión).

## Prueba en emulador Android 14 (2026-11-04)

Tableta virtual `kiosk14-tab` (imagen Google Play, Android 14, 2560x1600), la Student 2.12.0 como Device Owner por ADB y un examen de nivel `controlado` en un nodo aislado. **Esto prueba el comportamiento de Android al aplicar Lock Task con la app actual, no el script ni a Google.** AMAPI no se puede probar en un emulador: exige una empresa real y una cuenta de Google.

| Comprobación | Resultado |
|---|---|
| La app es Device Owner | `dpm list-owners` lo confirma (en el emulador hay que marcar la configuración como incompleta un instante para que Android lo permita) |
| Al pulsar Comenzar | `mLockTaskModeState=LOCKED` |
| Inicio, Recientes, Atrás | el foco no sale de la Student y sigue LOCKED |
| Barra de notificaciones, ajustes rápidos y deslizar desde arriba | el foco no sale de la Student |
| Pulsación larga de encendido | no aparece el menú de apagado |
| Abrir Ajustes u otra app | rechazado con el error 101 (violación de Lock Task) |
| Captura de pantalla | `screencap` devuelve 0 bytes |
| Entregar el examen | `mLockTaskModeState` pasa a `NONE`, la Student muestra «Tu examen quedó entregado» y Ajustes se abre (2.ª pasada, 2026-11-04) |
| Siete toques sobre el título, sin PIN fijado | sale el cuadro «Salida del examen»; con un PIN cualquiera responde «Esta tableta no tiene PIN de salida…» y sigue `LOCKED` |
| Cierre forzado o anulación desde el profesor con el intento `en_curso` | el nodo responde 409 (solo se cierra a la fuerza un intento suspendido; un `en_curso` no se anula): la tableta sigue `LOCKED` |
| Nodo | tras el primer examen la antesala deja de decir que la tableta no cumple |

**No probado:** la salida con un PIN correcto (la app de Release no deja fijar `salida.json` y no hay `run-as`; haría falta el APK Debug), la liberación remota con un intento suspendido, el apagado forzado por hardware, ni nada de AMAPI (política, QR, zero-touch, `devices`).
**Trampas:** el emulador pierde caracteres al teclear si la carga es alta (esperar a que baje a menos de 2); Git Bash convierte `/` en rutas (usar `MSYS_NO_PATHCONV=1`); en Lock Task `uiautomator dump` falla con «could not get idle state» o devuelve la pantalla anterior (repetir hasta que diga «dumped» y comprobar el título); `screencap` da 0 bytes con el examen en curso (es el bloqueo funcionando); un «System UI isn't responding» aparece al arrancar (tocar «Wait»); si el emulador pierde la red (`Network is unreachable`) basta `svc wifi disable` y `enable`; el aviso «Viewing full screen» de Android toma el foco y falsea las pruebas de teclas hasta pulsar «Got it»; una suspensión del equipo deja el emulador inservible (reiniciarlo).

## No probado

Las llamadas HTTP no se ejecutaron contra una empresa real; solo la lógica pura y los `--dry-run`. Antes de depender de ellas hay que confirmar contra la referencia vigente de AMAPI:
- `installType: REQUIRED_FOR_SETUP` junto con el rol `KIOSK` en una sola app, y el valor de `allowPersonalUsage` (`PERSONAL_USAGE_DISALLOWED`) en el token.
- La clave `com.google.android.apps.work.clouddpc.EXTRA_ENROLLMENT_TOKEN` del bundle de zero-touch: salió de una fuente de terceros, no de la documentación de Google.
- Que los extras de Wi-Fi del QR los acepte el asistente de Android 14 de las tabletas del cliente.
