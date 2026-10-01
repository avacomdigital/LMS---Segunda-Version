Bloqueo de examen en Android y Windows: cómo replicarlo
Guía para reproducir en otro software el bloqueo que usa este prototipo: que el estudiante no pueda salir del examen ni consultar otra pantalla. Describe lo que hace el código de src/Avacom.Exam.Student, por qué, y qué exige el sistema operativo para que funcione. Los fragmentos son los del prototipo; las rutas indican dónde verlos completos.

Estado de la evidencia. El bloqueo de Android (Device Owner + Lock Task) se probó sobre una tableta física con Android 14. El gancho de teclado de Windows se probó en un banco aislado. Assigned Access y Shell Launcher en Windows no se ejercitaron al escribir este documento: están descritos a partir de los scripts del repositorio, no de una prueba en equipo. Valida esa parte antes de apoyarte en ella.

1. El principio que lo organiza todo
Una aplicación no puede encerrarse a sí misma. El botón Inicio y los Recientes de Android, y Alt+Tab y Ctrl+Alt+Supr en Windows, los gobierna el sistema operativo. Por eso el bloqueo tiene siempre dos capas:

Capa	Quién la aplica	Qué consigue	Qué no consigue
Aplicación	el propio proceso	pantalla completa, ignorar Atrás, rechazar el cierre, descartar teclas	impedir que el sistema operativo ofrezca una salida
Sistema operativo	una política de dispositivo o de cuenta, aprovisionada aparte	cerrar la salida de verdad	nada, pero exige preparar el equipo antes
Toda la lógica del prototipo sale de ahí. La capa de aplicación funciona en cualquier equipo y se activa sola; la del sistema exige aprovisionar, y por eso la app mide e informa cuál de las dos está activa (§5.1).

Sin aprovisionar	Aprovisionado
Android	inmersivo, Atrás ignorado; se puede salir	Device Owner + Lock Task: Inicio, Recientes, notificaciones y menú de apagado bloqueados
Windows	pantalla completa, cierre rechazado, teclas descartadas; Ctrl+Alt+Supr sigue libre	Assigned Access o Shell Launcher: cierra también esa vía
2. Arquitectura que conviene copiar
El prototipo aísla todo el bloqueo detrás de una interfaz de cinco miembros (PlatformServices/IKioskService.cs). La lógica del examen no sabe qué plataforma hay debajo:

public interface IKioskService
{
    bool IsTrueDeviceLockAvailable { get; }   // ¿está aprovisionada la capa del SO?
    Task EnterFullScreenAsync(...);           // desde el arranque, sin examen aún
    Task StartExamLockAsync(...);             // al empezar el examen
    Task StopExamLockAsync(...);              // al terminar
    string LockdownSummary { get; }           // qué restricciones hay activas AHORA
}
Hay una implementación por plataforma, registrada con compilación condicional (MauiProgram.cs): AndroidKioskService y WindowsKioskService. Al portar a otro stack, reproduce esta separación aunque cambie el lenguaje.

Ciclo de vida
sequenceDiagram
    participant P as Profesor (OPS)
    participant A as API
    participant T as Cliente del estudiante
    participant K as KioskService
    T->>K: EnterFullScreen (al abrir la app)
    P->>A: iniciar examen
    A-->>T: WebSocket exam_started
    T->>K: StartExamLock
    Note over K: marca "examen en curso", aplica la capa del SO y la de app
    T->>T: el estudiante responde
    T->>A: finalizar entrega
    A-->>T: OK
    T->>K: StopExamLock
Tres decisiones del ciclo que importan al replicar:

Pantalla completa desde el arranque, no solo al empezar el examen: el estudiante no debe ver el escritorio ni la barra de tareas en ningún momento.
El bloqueo se libera solo después de que la entrega se confirme. Si el servidor no responde, el estudiante no queda fuera con el examen a medias: se reintenta (ExamViewModel.FinishAsync).
Una bandera compartida (ExamSession.IsExamInProgress) la consultan las plataformas para negarse a cerrar. Se activa antes de aplicar el bloqueo: el rechazo al cierre debe valer incluso en un equipo sin aprovisionar.
3. Android
Tecnología: Device Owner + Lock Task Mode de DevicePolicyManager, más la capa de aplicación en la Activity. Nada de esto es específico de .NET MAUI: son APIs nativas, y en Kotlin o Java se llaman igual.

3.1 Requisitos y rango de versiones
La app debe ser Device Owner. Activar «administrador del dispositivo» desde Ajustes no basta: es un permiso distinto y mucho más débil, y startLockTask() solo fija pantalla, sin bloquear nada.
Android concede Device Owner una sola vez y solo a un equipo sin cuentas configuradas, con un único usuario y sin propietario previo.
El prototipo apunta a Android 14. setLockTaskFeatures existe desde API 28; si necesitas Android 8–9, protege esa llamada con una comprobación de versión. El SupportedOSPlatformVersion del proyecto es 26 y esa llamada no está protegida.
3.2 Declarar el receptor de administración
ExamDeviceAdminReceiver.cs es una clase casi vacía, pero el sistema la exige:

[BroadcastReceiver(Name = "com.avacom.exam.student.ExamDeviceAdminReceiver",
    Permission = "android.permission.BIND_DEVICE_ADMIN", Exported = true)]
[IntentFilter(["android.app.action.DEVICE_ADMIN_ENABLED",
               "android.app.action.PROFILE_PROVISIONING_COMPLETE"])]
[MetaData("android.app.device_admin", Resource = "@xml/device_admin_receiver")]
public sealed class ExamDeviceAdminReceiver : DeviceAdminReceiver { }
Y la política que declara, en Platforms/Android/Resources/xml/device_admin_receiver.xml:

<device-admin xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-policies>
        <force-lock />
        <disable-camera />
    </uses-policies>
</device-admin>
El nombre del componente (paquete/clase) es lo que se pasa luego a dpm set-device-owner. Si el nombre de la clase y el del manifiesto difieren, el comando falla; por eso el prototipo fija Name = "com.avacom...." en lugar de dejar que se genere un nombre automático.

3.3 Aplicar el bloqueo
AndroidKioskService.StartExamLockAsync, en este orden exacto:

PolicyManager.SetLockTaskPackages(AdminComponent, [Activity.PackageName!]); // 1. autorizar
if (!PolicyManager.IsLockTaskPermitted(Activity.PackageName))               // 2. comprobar
    throw new InvalidOperationException("El paquete no quedó autorizado.");
PolicyManager.SetLockTaskFeatures(AdminComponent, LockTaskFeatures.None);   // 3. quitar TODO
PolicyManager.AddUserRestriction(AdminComponent,
    UserManager.DisallowCreateWindows);                                     // 4. sin ventanas flotantes
Activity.StartLockTask();                                                   // 5. fijar
Activity.HideSystemUi();                                                    // 6. inmersivo
LockTaskFeatures.None desactiva Inicio, Recientes, notificaciones, información del sistema, pantalla de bloqueo y el menú de apagado. Si algo debe seguir disponible, se habilita por bandera.
Al terminar: StopLockTask() y ClearUserRestriction(...). StopLockTask lanza InvalidOperationException si no estaba activo, así que se captura.
Todo corre en el hilo de interfaz, y se devuelve el resultado al llamador. El prototipo lo resuelve con RunOnUiThreadAsync, un puente con TaskCompletionSource. Sin él, una excepción dentro de RunOnUiThread (por ejemplo, un equipo que no es Device Owner) sube por el hilo de interfaz y cierra la app en pleno examen, sin pasar por el try/catch del código que la llamó.
3.4 La capa de aplicación (MainActivity)
Sirve en equipos sin aprovisionar, y sigue haciendo falta con Device Owner:

[Activity(MainLauncher = true, LaunchMode = LaunchMode.SingleTask,
          ScreenOrientation = ScreenOrientation.SensorLandscape, ...)]

OnCreate:            Window.AddFlags(WindowManagerFlags.KeepScreenOn); HideSystemUi();
OnWindowFocusChanged(hasFocus): if (hasFocus) HideSystemUi();   // las barras vuelven al deslizar
OnBackPressed():     if (examen en curso) { HideSystemUi(); return; }  base.OnBackPressed();
Lock Task no intercepta el botón Atrás. Desactiva Inicio, Recientes y notificaciones; Atrás sigue llegando a tu Activity, y si esa Activity termina, termina la tarea y con ella el bloqueo. Ignóralo tú mientras haya examen. (El comentario de MainActivity dice que Lock Task ya lo bloquea; es impreciso.)
HideSystemUi usa WindowInsetsController desde API 30 (Hide(StatusBars | NavigationBars) con ShowTransientBarsBySwipe) y las banderas SystemUiFlags heredadas por debajo. Se reaplica en cada ganancia de foco, porque deslizar desde el borde muestra las barras.
SingleTask evita que otra instancia de la Activity se apile.
Al subir targetSdk, comprueba que OnBackPressed siga invocándose: Android ha ido moviendo el comportamiento hacia el retroceso predictivo.
3.5 Aprovisionar el equipo
Es la parte que más tiempo cuesta, y se hace antes de entregar la tableta.

Una tableta, por ADB (la app ya instalada):

adb shell dumpsys account        # "Accounts: 0" es obligatorio
adb shell dpm list-owners        # "no owners"
adb shell pm list users          # un solo UserInfo
adb shell dpm set-device-owner com.avacom.exam.student/com.avacom.exam.student.ExamDeviceAdminReceiver
adb shell dpm list-owners        # debe nombrar el paquete: un "Success" no basta
set-device-owner no se deshace sin restablecimiento de fábrica. Con ADB inalámbrico hay que emparejar antes (adb pair <ip:puerto-de-emparejamiento> <código>), y el puerto de emparejamiento es distinto del de conexión.

Muchas tabletas, por QR (sin cable ni PC por equipo): en la primera pantalla del asistente de un equipo recién restablecido, toca seis veces y escanea un QR cuyo JSON lleva el componente, la URL de descarga del APK, su checksum SHA-256 en Base64 URL-safe y sin relleno, y PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED=false para reducir lo que se puede abrir si el bloqueo fallara. Ver scripts/android/New-DeviceOwnerQr.py y device-owner-qr.template.json. Para flotas grandes y permanentes, el camino es Android Management API o Zero-touch.

3.6 Verificar
adb shell dpm list-owners
adb shell dumpsys activity activities | findstr /i LockTaskModeState   # nombre exacto varía por versión
Y a mano, con la tableta en examen: Inicio, Recientes, deslizar desde arriba, Atrás y mantener pulsado el botón de encendido. El apagado forzado por hardware (mantener el botón varios segundos) no lo puede impedir ningún software.

4. Windows
Aquí no hay un equivalente a Lock Task dentro de la app. Hay cinco piezas: cuatro en el proceso y una en el sistema.

4.1 Pantalla completa real
AppWindowPresenterKind.FullScreen, no maximizar: maximizar deja visibles la barra de título y la de tareas. Se aplica en el arranque (window.Created), porque antes no existe la ventana nativa.

4.2 Rechazar el cierre
appWindow.Closing += (_, args) => { if (session.IsExamInProgress) args.Cancel = true; };
Cubre Alt+F4 y cualquier cierre programático. Se engancha una sola vez.

4.3 Gancho de teclado de bajo nivel
ExamKeyboardGuard.cs: SetWindowsHookEx(WH_KEYBOARD_LL), la misma técnica de los navegadores de examen comerciales. No necesita administrador. Descarta: tecla Windows (izquierda y derecha), Alt+Tab, Esc (y con él Alt+Esc, Ctrl+Esc y Ctrl+Shift+Esc), Alt+F4 y F11.

Cuatro detalles que costó descubrir y que se pierden al reescribirlo:

Descarta también KEYUP, no solo KEYDOWN. El menú Inicio se abre al soltar la tecla Windows; bloquear solo la pulsación deja pasar el evento que de verdad lo dispara.
El delegado se guarda en un campo estático. Si solo viviera como argumento, el recolector de basura lo liberaría y Windows llamaría a memoria inválida.
Se instala desde el hilo de interfaz, que tiene bucle de mensajes: un gancho global sin él no recibe nada.
Devolver 1 consume la tecla; en cualquier otro caso se debe terminar en CallNextHookEx.
El estado del gancho se expone (IsActive) para que la app pueda informar si falló.

4.4 Cubrir los monitores adicionales
SecondaryScreenBlocker.cs abre una ventana opaca a pantalla completa en cada DisplayArea distinto al del examen, con el texto «Esta pantalla queda bloqueada». Solo actúa en modo extendido: en modo duplicado Windows expone un único display y ambos ya muestran lo mismo. La ventana nativa no existe hasta Created, así que se mueve al monitor de destino en ese evento.

4.5 La capa del sistema: Assigned Access o Shell Launcher
El gancho cubre casi todo, pero no Ctrl+Alt+Supr: Windows lo procesa en un escritorio seguro al que ningún gancho llega, por diseño. Desde ahí se abre el Administrador de tareas o se cambia de usuario. Cerrar esa vía exige una política de la cuenta, no del proceso:

Assigned Access	Shell Launcher
Ediciones	Pro, Enterprise, Education, IoT	Enterprise, Education, IoT (no Pro)
Reemplaza	la sesión por una sola app	el shell (explorer.exe) por tu ejecutable
Script	scripts/windows/Install-Kiosk.ps1	scripts/windows/Install-ShellLauncher.ps1
Pensado para	apps empaquetadas (MSIX)	ejecutables de escritorio estables
Pasos de Assigned Access (Install-Kiosk.ps1, como administrador):

Crea un usuario local estándar (AvacomExam). Mantén una cuenta administradora distinta: es la recuperación.
Inicia sesión una vez como ese usuario e instala el MSIX para él. El script lo advierte porque una app empaquetada se instala por usuario.
Averigua el AUMID: Get-StartApps | Where-Object Name -like "*AVACOM*". El script lo exige como parámetro obligatorio (-AppUserModelId).
Set-AssignedAccess -UserName AvacomExam -AppUserModelId <AUMID>.
Reinicia y entra como ese usuario.
Revertir: scripts/windows/Remove-Kiosk.ps1 (con -DisableShellLauncher si se usó Shell Launcher). Conserva el usuario y sus datos.

Si tu software es un ejecutable de escritorio y no un MSIX, el esquema de configuración de Assigned Access también admite aplicaciones clásicas por ruta. Verifícalo contra la documentación vigente de Microsoft para tu versión de Windows; este prototipo no lo usa.

4.6 El interruptor de desarrollo
WindowsKioskService lee AVACOM_EXAM_NO_LOCKDOWN=1: mantiene la pantalla completa pero no instala el gancho, no cubre monitores y permite cerrar la ventana. Es indispensable: el gancho es global, y probando panel y examen en el mismo equipo no quedaría forma de volver al panel con Alt+Tab. En los equipos de la sede la variable no se define.

5. Lo transversal: tres reglas de diseño
5.1 Informar el estado real, no el deseado
IsTrueDeviceLockAvailable y LockdownSummary existen para que la pantalla del examen diga qué hay activo:

Android: IsDeviceOwnerApp(packageName). Es una consulta real al sistema.
Windows: existencia de %ProgramData%\AVACOM\kiosk-provisioned.marker, un archivo que escribe el script de aprovisionamiento. Es un indicio, no una comprobación: si alguien borra la política pero deja el archivo, la app lo dará por aprovisionado. Si portas esto, consulta el estado real (por ejemplo la configuración de Assigned Access).
Sin ese informe, en una sede es imposible distinguir «el bloqueo se aplicó» de «el bloqueo falló y el estudiante puede salir».

5.2 Un bloqueo parcial se informa, no se oculta
StartExamLockAsync lanza una excepción cuando el bloqueo queda incompleto, y el ViewModel la captura, muestra LockdownSummary y la conserva aunque cambie el estado de la conexión (_lockdownWarning). Funciona, pero usar una excepción como canal de estado es un olor: al portar, devuelve un resultado tipado (Aplicado, Parcial(motivo), Fallido(motivo)). Y un aviso de seguridad no debe pisarse con mensajes de red.

Cuidado inverso: la propiedad que construye el resumen no debe lanzar. En Android lee Platform.CurrentActivity, que puede ser nulo; si lanza dentro del catch que reporta un fallo, se pierde el mensaje útil.

5.3 Una salida administrativa que no dependa de nadie
Hace falta una vía para sacar a un estudiante de un examen colgado. En el prototipo: siete toques en dos segundos sobre el título y un PIN local, sin depender del servidor ni de Internet. En Android detiene Lock Task pero no quita Device Owner.

No copies el almacenamiento del PIN. El prototipo guarda SHA-256 sin sal sobre seis dígitos (un millón de combinaciones, que se recorren en menos de un segundo), con un PIN por omisión escrito en el código y en el README. Usa PBKDF2 con sal por dispositivo y genera un PIN distinto por equipo durante el aprovisionamiento.

Lista de comprobación para portar
Android

sin completar
Receptor declarado con permiso BIND_DEVICE_ADMIN y nombre explícito
sin completar
Equipo restablecido, sin cuentas; dpm set-device-owner y dpm list-owners verificado
sin completar
setLockTaskPackages → comprobar isLockTaskPermitted → setLockTaskFeatures → startLockTask
sin completar
Llamadas en el hilo de interfaz, con el error devuelto al llamador
sin completar
Atrás ignorado en examen; barras ocultas y reaplicadas al ganar foco
sin completar
stopLockTask al terminar y salida administrativa probada
Windows

sin completar
Pantalla completa desde el arranque
sin completar
Cierre rechazado mientras IsExamInProgress
sin completar
Gancho instalado en el hilo de interfaz, KEYUP incluido, delegado en campo estático
sin completar
Ventana opaca por cada monitor adicional
sin completar
Usuario estándar, MSIX instalado para ese usuario, Assigned Access aplicado y reiniciado
sin completar
Interruptor de desarrollo para no bloquear tu propio equipo
sin completar
Cuenta administradora aparte y Remove-Kiosk.ps1 probado
Ambas

sin completar
El bloqueo se libera solo tras confirmar la entrega
sin completar
La pantalla informa el estado real del bloqueo
sin completar
Un fallo parcial se muestra y no se pisa
sin completar
PIN con PBKDF2, sal por equipo y valor distinto por dispositivo
7. Límites conocidos
Ctrl+Alt+Supr no se puede interceptar desde ninguna aplicación; solo la política de cuenta lo cierra.
Apagado forzado por hardware en Android: no hay software que lo impida.
El marcador de aprovisionamiento de Windows es un indicio, no una comprobación (§5.1).
Una sola pantalla de Android: no hay equivalente al bloqueador de monitores.
El código de plataforma no tiene pruebas automatizadas. Las 102 pruebas del prototipo cubren Avacom.Exam.Core; los servicios de kiosco y los ViewModels se validaron a mano. Al portar, aísla la lógica detrás de la interfaz de §2 para poder probarla con un doble.
No contempla capturas de pantalla, grabación, portapapeles ni dispositivos USB. Android bloquea la captura con FLAG_SECURE, que este prototipo no activa.