# Keystore / KeyMint del emulador Android (Fase 0 · MOD-018)

Medido el 2026-10-20 en el equipo de desarrollo (Windows 11 Pro). Sólo lecturas: no se tocó el repositorio, no se instaló ni se empujó nada al emulador y no se usó root. Todo lo generado está en esta carpeta.

## 1. Conclusión

El KeyMint del emulador es **de software**, aunque Android lo presenta como nivel **TEE**. StrongBox no existe.

| Pregunta | Respuesta | Evidencia principal |
|---|---|---|
| ¿Es hardware seguro real (TEE)? | **No** | Implementación `FakeKeyMintDevice` (autor Google), el HAL de referencia de AOSP; proceso normal del invitado (uid `nobody`); librerías de software puro presentes en `/vendor/lib64` (`libkeymaster_portable`, `libpuresoftkeymasterdevice`); sin nodos de TEE en `/dev`; gatekeeper «nonsecure»; `ro.kernel.qemu=1` |
| ¿Cómo lo ve el framework? | Como `TRUSTED_ENVIRONMENT` | `dumpsys android.security.maintenance`: «Device info for r#TRUSTED_ENVIRONMENT»; las métricas de keystore2 que leí dicen `sec=TEE`; logcat: «KeyMint device is current version (Some(400)) for security level: r#TRUSTED_ENVIRONMENT» |
| ¿StrongBox? | **No** | Sin la característica `android.hardware.strongbox_keystore`; sólo existe la instancia `IKeyMintDevice/default` (no `/strongbox`); keystore2: «No StrongBox Keymint available» |
| ¿Arranque verificado green/locked u orange/unlocked? | **Ninguno: no se reporta** | `ro.boot.verifiedbootstate`, `ro.boot.flash.locked` y `ro.boot.vbmeta.device_state` están vacías (ver sección 5); en un emulador no hay bootloader real, así que no es de confianza |

Implicación para MOD-018 (inferencia, no medida): un cliente que pregunte `KeyInfo.getSecurityLevel()` o `isInsideSecureHardware()` muy probablemente vea «TEE» en este emulador, porque keystore2 clasifica así a ese KeyMint. Esas llamadas, por sí solas, no distinguen un emulador de un equipo real. Lo que sí lo distinguiría (cadena de atestación y su raíz, estado del Root of Trust) no se pudo medir sin una app (sección 6).

## 2. Entorno y arranque

- Emulador 36.6.11.0; AVD `Pixel_10`; imagen `android-37.2-beta3` `google_apis_playstore_ps16k` x86_64 (Android 17, SDK 37.1, build `user`, claves `dev-keys`, parche 2026-07-05).
- Aceleración: `emulator -accel-check` dice «WHPX(10.0.26200) is installed and usable» y el log confirma «Windows Hypervisor Platform accelerator is operational».
- RAM: el AVD declara 2048 MB y el emulador la subió a 4096 MB («Increasing RAM size to 4096MB»). GPU del anfitrión Intel, pero se usó SwiftShader (software) por `-gpu swiftshader_indirect`.
- Estado inicial: no había proceso `adb`, `emulator` ni `qemu` (el `crashpad_handler` de Spotify es ajeno). El servidor adb **no** estaba corriendo; lo arrancó mi primer `adb devices`.
- Comando (PowerShell, `Start-Process` oculto, salida a archivos `emulator.out.log` y `emulator.err.log`):

```
emulator.exe -avd Pixel_10 -no-window -no-audio -no-snapshot-save -no-snapshot-load -no-boot-anim -gpu swiftshader_indirect -netdelay none -netspeed full
```

  Única desviación respecto a lo pedido: añadí `-no-snapshot-load` para forzar un arranque en frío (el AVD tiene un snapshot `default_boot` del 15/10; restaurarlo habría dado un «tiempo de arranque» sin sentido y habría reanudado el estado del usuario). Tampoco usé `adb wait-for-device`: sondeé `adb devices` y luego `getprop sys.boot_completed` cada ~3 s con tope de 8 min (equivalente, con tiempo límite controlable).
- Procesos que arrancó mi lanzamiento: `emulator.exe` (PID 4312), `qemu-system-x86_64-headless.exe` (12016; el binario se llama así, no `qemu-system-x86_64.exe`), `netsimd.exe` (34072) y el `crashpad_handler.exe` del emulador (20692).
- **Tiempo de arranque en frío: ≈ 95,7 s** desde el lanzamiento hasta `sys.boot_completed=1` (resolución ≈ 3 s). Línea de tiempo del sondeo: dispositivo `offline` a 45,7 s (primer sondeo), `device` a 51,2 s, `boot_completed=1` a 95,7 s. `/proc/uptime` del invitado en ese instante: 84,66 s, es decir el kernel arrancó ≈ 11 s después del lanzamiento.

## 3. Lecturas (comandos y salidas recortadas)

Todas con `adb -s emulator-5554 shell ...`.

### 3.1 Propiedades (`getprop <nombre>`)

```
ro.build.version.release     = 17            (sdk 37, sdk_full 37.1)
ro.product.cpu.abilist       = x86_64,arm64-v8a
ro.boot.verifiedbootstate    = (vacío)
ro.boot.flash.locked         = (vacío)
ro.boot.veritymode           = enforcing
ro.boot.vbmeta.device_state  = (vacío)
ro.hardware                  = ranchu
ro.hardware.keystore         = (vacío)
ro.hardware.keymaster        = (vacío)
ro.kernel.qemu               = 1             (ro.boot.qemu = 1)
ro.product.model             = sdk_gphone16k_x86_64
ro.debuggable                = 0
ro.secure                    = 1
ro.build.type / tags         = user / dev-keys
ro.product.first_api_level   = 37
ro.build.characteristics     = emulator
```

Otras propiedades relacionadas (`getprop | grep -i -E 'verified|vbmeta|flash|veritymode|bootloader|keymint|keymaster|keystore|strongbox|gatekeeper|weaver|rkp|remote_prov|boot.hardware'`):

```
[ro.boot.vbmeta.digest]/[hash_alg]/[size] = presentes (sha256, 6720 bytes)
[ro.bootloader] = [unknown]
[partition.system.verified] = [2]          (dm-verity en system)
[remote_provisioning.tee.rkp_only] = [1]   [remote_provisioning.strongbox.rkp_only] = [1]
[init.svc.keystore2] = [running]           [init.svc.gatekeeperd] = [running]
```

### 3.2 Características (`pm list features | grep -i -E "keystore|strongbox|keymint|attestation|device_id_attestation"`)

```
feature:android.hardware.hardware_keystore=400
feature:android.hardware.keystore.app_attest_key
```

KeyMint 4.0 (valor 400). **No** aparece `android.hardware.strongbox_keystore`, ni `android.software.device_id_attestation`, ni `android.hardware.device_unique_attestation`.

### 3.3 Servicios (`service list | grep -i -E "keymint|keymaster|keystore|strongbox|security"`, sólo lo relevante)

```
52  android.hardware.security.keymint.IKeyMintDevice/default
53  android.hardware.security.keymint.IRemotelyProvisionedComponent/default
54  android.hardware.security.secureclock.ISecureClock/default
55  android.hardware.security.sharedsecret.ISharedSecret/default
56  android.hardware.security.sharedsecret.ISharedSecret/gatekeeper
67..73  android.security.apc / authorization / compat / identity / legacykeystore / maintenance / metrics
75  android.system.keystore2.IKeystoreService/default
240 remote_provisioning
```

Sólo la instancia `default` de KeyMint; no hay `.../strongbox`. `dumpsys -l | grep -i -E "keystore|keymint|security"` lista `android.security.maintenance`, `android.security.metrics`, `android.system.keystore2.IKeystoreService/default` y el resto de la familia (sin novedad).

### 3.4 `dumpsys android.security.maintenance` (105 líneas; primeras 40 recortadas, se omite la línea hexadecimal DER de módulos atestiguados)

```
keystore2 running
Device info for r#TRUSTED_ENVIRONMENT with Uuid([0, ..., 0, 1])
  HAL version:              400
  Implementation name:      FakeKeyMintDevice
  Implementation author:    Google
  Timestamp token required: false
Attested module information (DER-encoded):
  (hexadecimal omitido)
Top-10 per-uid key counts (where > 5 keys):
Database size information (in bytes): ...
Metrics information:
  KEYGEN_GENERAL : [
    EC  crv=P-256 GENERATED rc=1 attest? Y => count=7      (en una segunda lectura: 13)
    EC  crv=P-256 GENERATED rc=4 attest? Y => count=2
    AES IMPORTED  rc=1 attest? N => count=1
  ]
  KEYGEN_AUTH    : [ auth=NOAUTH log(time)= -1 sec=TEE => count=10 ]
```

Filtrando el volcado (`| grep -n -i -E 'sec=|SOFTWARE|TEE|STRONGBOX|attest'`, 51 líneas coincidentes; sólo guardé y revisé las 40 primeras) todas las líneas de generación, importación y operaciones (`GENKEY`, `IMPKEY`, `BEGIN`) llevan `sec=TEE`; en lo revisado no aparece ningún `sec=SOFTWARE` ni `sec=STRONGBOX` (las 11 líneas restantes no se pudieron releer porque el emulador ya estaba apagado). Los contadores crecieron entre dos lecturas (generaciones EC con atestación 7 → 13): las provocan procesos del propio invitado (uids de sistema y de apps), no mi sondeo, que sólo leyó. No interpreté `rc=1` / `rc=4`.

### 3.5 Otras lecturas de apoyo (todas de sólo lectura)

- `ps -A -o PID,USER,ARGS | grep ...`: `keystore2` (uid `keystore`, PID 336), `android.hardware.security.keymint-service` (uid `nobody`, PID 337, proceso ordinario del invitado), `android.hardware.gatekeeper-service.nonsecure` (uid `system`) y `gatekeeperd`.
- `/vendor/etc/vintf/manifest/android.hardware.security.keymint-service.xml` (el comentario de cabecera dice `Input: hardware/interfaces/security/keymint/aidl/default/...`, es decir, el HAL por defecto de AOSP): declara `android.hardware.security.keymint` `IKeyMintDevice/default` (versión AIDL 5) e `IRemotelyProvisionedComponent/default` (versión 3). Los fragmentos de `secureclock` y `sharedsecret` sólo declaran `default`. No hay instancia `strongbox` declarada.
- `ls /vendor/lib64 | grep -i -E 'keymaster|keymint|kmr|cppbor|rkp'`: `libkeymaster_portable.so`, `libpuresoftkeymasterdevice.so`, `libkeymaster_messages.so`, `libkeymint.so`, `lib_android_keymaster_keymint_utils.so`, `libcppbor.so`, `libcppcose_rkp.so`, `android.hardware.security.keymint-V1/V4-ndk.so`, `android.hardware.security.rkp-V3-ndk.so`, `android.hardware.keymaster-V4-ndk.so`.
- `ls /dev | grep -i -E 'tee|trusty|qsee|optee|tz|teei'`: sin resultados (no hay nodos de TEE).
- `logcat -d -b all | grep ...` (keystore2 al arrancar):

```
keymint-service: adding keymint service instance: ...IKeyMintDevice/default (y SecureClock, SharedSecret, RemotelyProvisionedComponent)
keystore2: KeyMint device is current version (Some(400)) for security level: r#TRUSTED_ENVIRONMENT
keystore2: createMintDevice(STRONGBOX) -> failed to create compat KeyMint device for STRONGBOX
keystore2: No StrongBox Keymint available, so no RoT transfer
keystore2: Call to earlyBootEnded succeeded for security level TRUSTED_ENVIRONMENT / failed for StrongBox as it is not available
keystore2: Call to setAdditionalAttestationInfo succeeded for security level TRUSTED_ENVIRONMENT / failed for StrongBox
keystore2: get_level_zero_key: security_level=r#SOFTWARE, deny_later_strategy=EarlyBootOnly
```

La última línea es una **pista no concluyente**: para su clave de nivel de arranque keystore2 usó el nivel SOFTWARE, lo que encaja con que el HAL se declare de software por dentro aunque ocupe el hueco TEE. No pude leer `getHardwareInfo().securityLevel` directamente (ver 3.6).

### 3.6 Lecturas que fallaron (no se rodearon)

- `dumpsys android.system.keystore2` y `dumpsys android.security.keystore`: «Can't find service» (esos nombres no existen; para el primero el logcat registra un `avc: denied { find }` con `tcontext=default_android_service`, que es el contexto de un nombre desconocido). El nombre real `android.system.keystore2.IKeystoreService/default` se volcó vacío.
- `service call android.hardware.security.keymint.IKeyMintDevice/default 1` (transacción getter `getHardwareInfo`; lectura adicional que no estaba en la lista): «Service ... does not exist» (salida 10). El logcat registra 3 denegaciones `avc: denied { find } ... scontext=u:r:shell:s0 tcontext=u:object_r:hal_keymint_service:s0 tclass=service_manager`. La política SELinux oculta el HAL al usuario `shell`; sin root no hay forma de leerlo y no se intentó.
- `cat /proc/bootconfig`: Permission denied. `ls -l /vendor/bin/hw/android.hardware.security.keymint-service`: Permission denied.

## 4. Por qué «software» y no «TEE»

1. Es la implementación `FakeKeyMintDevice` del HAL por defecto de AOSP (nombre y autor que informa keystore2, ruta de origen del manifiesto VINTF y presencia de las librerías de software puro `*_portable` / `puresoft*`; no pude leer el binario del HAL para ver qué enlaza).
2. Corre como proceso corriente en el espacio de usuario del invitado (uid `nobody`), sin aislamiento de TEE; no hay nodos de TEE; el gatekeeper es «nonsecure»; el dispositivo es un emulador QEMU (`ro.kernel.qemu=1`, `ro.build.characteristics=emulator`).
3. `ro.hardware.keystore` y `ro.hardware.keymaster` vacías: no hay HAL de proveedor.
4. Aun así keystore2 lo monta en el hueco `TRUSTED_ENVIRONMENT` (sección 3.4 y 3.5), por eso las métricas dicen `sec=TEE`. Lo que reporta Android es «TEE»; lo que hay detrás es software.

StrongBox queda descartado por tres vías independientes: característica ausente, instancia `/strongbox` ausente y mensajes de keystore2.

## 5. Arranque verificado

- `ro.boot.verifiedbootstate`, `ro.boot.flash.locked`, `ro.boot.vbmeta.device_state`: **vacías**. No es «green/locked» ni «orange/unlocked»: simplemente no se informa.
- Sí hay `ro.boot.veritymode=enforcing`, `ro.boot.vbmeta.digest/hash_alg/size` y `partition.system.verified=2` (dm-verity activo en `system`), `ro.bootloader=unknown`.
- El log de arranque del emulador lista los parámetros `androidboot.*` que inyecta: `veritymode=enforcing` y los tres de vbmeta; **no** inyecta `verifiedbootstate`. El emulador arranca el kernel directamente, sin bootloader: cualquier afirmación de arranque verificado no es de confianza ni equivale a la de un equipo real.

## 6. Qué NO se puede saber sin una app (no se construyó ni instaló ninguna)

- El valor real de `KeyInfo.getSecurityLevel()` / `isInsideSecureHardware()` para una clave generada por una app (lo esperable es TEE, no medido).
- El `securityLevel` que declara el propio HAL en `getHardwareInfo()` (SELinux lo bloquea al usuario `shell`).
- La cadena de atestación (`KeyGenParameterSpec.setAttestationChallenge`): `attestationSecurityLevel`, `keymasterSecurityLevel`, Root of Trust (`verifiedBootState`, `deviceLocked`, clave de arranque), de qué raíz cuelga, y si el aprovisionamiento remoto (RKP, propiedades `rkp_only=1`) funciona en el emulador; las dos generaciones con atestación que keystore2 cuenta con `rc=4` no se interpretaron.
- El comportamiento de `setIsStrongBoxBacked(true)` (lo esperable es `StrongBoxUnavailableException`), de la atestación de ID de dispositivo y de la clave única de dispositivo (características ausentes, no probado).
- La persistencia de claves entre reinicios y restablecimientos, autenticación de usuario ligada a claves, etc.
- Cómo se comporta una tableta real con Android 14: esta medición es de un emulador de Android 17 y no la sustituye.

## 7. Cierre y estado final

- `adb -s emulator-5554 emu kill` → «OK: killing emulator, bye bye». `emulator.exe` salió con código 0 a los 3,5 s; los cuatro procesos que arrancó mi lanzamiento (4312, 12016, 34072, 20692) ya no existen. Duración total del emulador ≈ 9,5 min.
- Servidor adb: no corría al empezar; lo arrancó mi primer `adb devices` (PID 3048, 10:11:36). Al terminar `adb devices` estaba vacío y sin clientes activos (sólo conexiones TimeWait en el puerto 5037), así que ejecuté `adb kill-server`; comprobado que no queda proceso `adb` ni escucha en 5037.
- Incidencia: apareció un `emulator.exe` transitorio (PID 29988) a las 10:20:20, el mismo segundo del `emu kill`, y ya no existía en la siguiente consulta (CIM sin datos de padre ni línea de comandos). No lo toqué. Coincide con la escritura de archivos del AVD en el apagado, así que probablemente es parte del cierre, pero no está comprobado (otra sesión es posible).
- Efectos en el AVD `Pixel_10` (no se usó `-read-only`, así que arrancar lo escribe): con fecha de hoy `userdata-qemu.img.qcow2` (3220,1 → 3860,1 MB), `sdcard.img.qcow2`, `encryptionkey.img.qcow2`, `quickbootChoice.ini` (contiene `saveOnExit = true`; no sé qué valía antes), `emulator-user.ini`, `bootcompleted.ini`, `hardware-qemu.ini`, `initrd`, `emu-launch-params.txt`, `multiinstance.lock`, `read-snapshot.txt` y la carpeta `tmpAdbCmds`. `config.ini`, `AVD.conf` y `cache.img.qcow2` conservan su fecha anterior.
- El snapshot `default_boot` del usuario sigue intacto: sus archivos conservan fechas del 21/08 y 15/10 y `qemu-img snapshot -l` lo lista en `userdata-qemu.img.qcow2` y en `cache.img.qcow2` (2026-08-21 16:45:34). Al apagar, el log dijo «Not saving state: RAM not mapped as shared» y luego «Saving snapshot 'default_boot' using 7 ms» pese a `-no-snapshot-save`; no hay rastro de que se haya escrito nada.
- Repositorio: no se escribió nada (sólo un `git status` de lectura).
- Archivos de esta carpeta: `emulator.out.log` / `emulator.err.log` (logs crudos del emulador; el `.out.log` contiene la clave pública adb del usuario, no copiarlo a sitios públicos), `raw_*.txt` (salidas crudas de cada lectura), `poll.log`, `t0.*`, `bootdone.ms.txt`, `serial.txt`, `emulator.pid`, `emulator.exit.txt`.
