# 06 · Evaluation & Delivery Engine (MOD-010) · Frontend: Student, OPS, kiosco y scripts

| Campo | Valor |
|---|---|
| Módulo | `evaluacion` (backend) y sus clientes: **Student** (la tableta del alumno: Windows y Android), **OPS** (la pantalla del profesor: Windows, táctil y sin teclado) y la capa de **bloqueo** de la tableta |
| Contrato HTTP | [backend.md](backend.md) §4 · modelo de datos [modelado-datos.md](modelado-datos.md) · cómo se bloquea una tableta [kiosk.md](kiosk.md) |
| Dónde está el código | `src/Avacom.Lms.Core/Evaluacion/` (cliente, reglas, cola cifrada y sesión del examen: sin MAUI y con pruebas) · `src/Avacom.Lms.Ui/Controls/ExamenView.cs` (el control del examen) · `src/Avacom.Lms.Student/Examen/` y `Platforms/` (pantallas y kiosco por plataforma) · `src/Avacom.Lms.Ops/Pages/Examen*.cs` · `scripts/` (aprovisionamiento) |
| Pruebas | `tests/Avacom.Lms.Core.Tests` (xUnit, sin hardware). Lo que sólo se comprueba en una tableta real está en §10 |

---

## 1 · Qué hace cada pieza (y qué NO hace)

El examen es el momento en que el producto tiene que ser creíble sin ser policial. En el cliente eso se traduce en cinco reglas que **ningún** archivo de esta carpeta rompe:

1. **Lo que el alumno responde se guarda primero en su tableta** (cola cifrada, AES-256-GCM) y sólo después se intenta enviar. Un corte de red, el cierre de la app o un reinicio no pierden nada; la pantalla dice «Guardado» o «Guardado en tu tableta», nunca «error de red».
2. **El reloj es del nodo.** La tableta pinta el cronómetro con lo que el nodo le dijo y manda su cuenta monotónica en cada latido, pero nunca decide cuándo se acaba el tiempo (INV-017). El contador **no cambia de color ni suena**, tampoco en el último minuto (Guion, paso 5).
3. **El nodo decide el bloqueo; la tableta lo aplica y cuenta lo que logró.** El `plan_de_bloqueo` viaja con el intento; la tableta devuelve `aplicado`, `parcial` o `fallido` con su motivo. Un bloqueo incompleto **se muestra** al alumno y al profesor; no se esconde ni anula el intento (BR-077).
4. **Se sale del examen sólo por la entrega confirmada.** El bloqueo se suelta DESPUÉS de que el nodo confirma la entrega (o de que se ve que el nodo ya entregó). Si el nodo no responde, la entrega queda guardada en la tableta, el bloqueo sigue y se reenvía sola.
5. **Anular es del profesor, con nombre y motivo, y sólo desde el expediente.** Ninguna pantalla del alumno ni del panel lo ofrece.

Lo que **no** se construyó en el cliente, a propósito: crear evaluaciones y reactivos (de la biblioteca, art. 14), la nota publicada y los ajustes (MOD-011), el arrastrar y soltar y la matemática con equivalencias (la biblioteca no los publica, Q-79) y el recorrido de un examen sin red desde cero (el examen se pide al nodo al abrir; ver §4.4).

---

## 2 · El recorrido completo

```
 Profesor (OPS)                                              Alumno (Student)
 ──────────────                                              ────────────────
 Clase de hoy → toca el examen del curso
 «Aplicar examen»: nivel (nunca preseleccionado),
   tiempo, fecha límite, intentos, resultados
 Elegibilidad de tabletas (MSG-036) ──────────────────────►  (las tabletas declaran su capacidad al registrarse y en cada latido)
 Aplicar ─────────────────────────────────────────────────►  Menú → «Exámenes» (o la tarjeta dentro de la clase) → «¿Quién eres?» si no hay sesión
                                                             Antesala (PAN-120): preguntas, duración, condiciones, qué se registra → «Comenzar»
 Panel del examen (PAN-005/121) ◄── latidos, incidentes ───  Examen (PAN-121): bloqueo según el plan, una pregunta a la vez, guardado primero
   · suspendido → «Reactivar» / «Reactivar a todos (N)»      Suspendido (PAN-122): «Tu examen está en pausa», el bloqueo sigue
   · tableta que no alcanza → Admitir / Rechazar
   · envío tardío → Aceptar / Descartar
 Cerrar examen / Prórroga / Endurecer / Bajar el nivel ───►  (el plan cambia en el siguiente latido; el nodo entrega al vencer)
 Revisar y puntuar las abiertas → Publicar                   Entrega (PAN-123): «Tu examen quedó entregado» + qué sigue (nunca «calificado» con algo por revisar)
 Liberar resultados (DEC-032) ────────────────────────────►  «Ver mi resultado»
 Expediente de un intento (PAN-062, sólo lectura)
   └ único lugar donde se anula: persona + motivo
```

---

## 3 · Student

### 3.1 · Rutas del Shell y archivos

| Ruta | Pantalla | Archivo | Se llega desde |
|---|---|---|---|
| `evaluaciones` | **Mis evaluaciones** + «¿Quién eres?» | `Examen/EvaluacionesPage.cs` | Dock del menú, botón «Exámenes»; la tarjeta de la clase sin identidad |
| `examen-antesala?asignacion=ID[&reanudar=1]` | **Antesala** (PAN-120) | `Examen/ExamenAntesalaPage.cs` | Mis evaluaciones; la tarjeta «Examen» de la clase |
| `examen` | **El examen** (PAN-121) y **esperando al profesor** (PAN-122) | `Examen/ExamenPage.cs` + `Ui/Controls/ExamenView.cs` | La antesala (sustituye a la antesala en la pila) |
| `examen-entrega[?intento=ID]` | **Entrega** (PAN-123) y **resultado** | `Examen/ExamenEntregaPage.cs` | El examen al entregar (sustituye al examen); Mis evaluaciones → «Ver resultado» |

Las pantallas se construyen en código con el kit (`Ds.*`), no en XAML, como `PracticaEstudioView` y `ActividadResponderView`; los identificadores de automatización (`AutomationId`) llevan el prefijo `evals-`, `antesala-`, `exa-` y `entrega-` para el arnés de UI Automation.

### 3.2 · Quién presenta («¿Quién eres?», D-19, D-25)

Con sesión de usuario el pase del nodo ya dice quién es y la app no manda `alumno_id`. **Sin sesión** (Q-34 abierta, el modo del prototipo) la tableta no puede saberlo: «Mis evaluaciones» pregunta `GET /api/evaluacion/estudiantes/` y muestra los grupos con una evaluación abierta y sus alumnos; la persona toca su nombre, sin código ni contraseña, y la elección queda en `Preferences` (`student_eval_alumno`, `student_eval_rotulo`). «¿No eres tú? Toca aquí» la borra. Es la misma filosofía que Modo Estudio: el LMS es offline y no hay verificación central.

### 3.3 · Mis evaluaciones

Una tarjeta por evaluación con su título, curso, número de preguntas, fecha límite, el **nivel en palabras** («Examen supervisado»), el estado («Abierto», «Abierto · fuera de plazo», «Aún no abre») y **una frase** de lo que puede hacer:

| Situación | Botón | Frase |
|---|---|---|
| Puede comenzar | **Comenzar** | «Lee las condiciones antes de empezar» |
| Intento vivo (en curso o suspendido) | **Continuar** | «Tienes un examen en curso» / «Tu examen está en pausa: avisa a tu profesor» |
| Su tableta espera a que el profesor decida | Ver | «Esperando que tu profesor decida sobre esta tableta» |
| Rechazada la tableta | — | «Tu profesor no admitió esta tableta: pídele que te indique cómo continuar» |
| Entregado | — | «Entregado · tu profesor publicará los resultados» |
| Resultado liberado | **Ver resultado** | «Ya puedes ver tu resultado» |
| Programada / cerrada / sin intentos | — | «Abre hoy 10:30» / «Este examen ya cerró» / «Ya presentaste este examen» |

Se sondea cada 5 s mientras la pantalla está a la vista y **no se repinta si nada cambió** (repintar parpadea y deja a la accesibilidad sin el botón entre una lectura y otra).

### 3.4 · Antesala (PAN-120)

Lo que el alumno debe ver **antes** de empezar. Iniciar sin que lo haya visto es lo que el sistema nunca hace: el examen se abre sólo al tocar «Comenzar».

* Título, curso y tres datos: **N preguntas · duración (o «Sin límite de tiempo») · intento único / «Intento 2 de 3»**; la fecha límite si la hay.
* **Las condiciones del nivel**, con el texto obligatorio del nodo (`CONDICIONES`): «Durante este examen tu tableta solo muestra el examen. Si sales, tu profesor lo verá, y tus respuestas se guardan igual.» y la lista **«Qué se registra»**.
* En `controlado`, el **estado real del bloqueo de esta tableta** (`IKioskService.LockdownSummary`): ni más ni menos de lo que la tableta puede garantizar.
* Si la tableta no alcanza el nivel (`dispositivo.alcanza = false`): «Tu tableta no cumple lo que pide este examen. Puedes tocar «Comenzar» de todos modos: tu profesor decidirá cómo continúas. No pierdes nada.» (BR-075: el alumno nunca queda excluido por su aparato.) Al comenzar queda **esperando**; la pantalla sondea cada 3 s y el examen abre solo cuando el profesor admite la tableta. Si la rechaza, una frase tranquila y sin culpables.
* Composición: en una ventana ancha (≥ 1500 px, escritorio 1920 × 1080) la tarjeta se ancla a la **cuadrícula de tercios** del encuadre completo (Grid `*,*,*` / `*,4*,*`, tarjeta en la celda central con `Fill`, sin márgenes). En una tableta el tercio central sería demasiado estrecho para leer, y la tarjeta toma casi todo el ancho con la misma proporción vertical.

### 3.5 · El examen (PAN-121) — `ExamenView`

Una pregunta a la vez con **los mismos editores** que la actividad del aula y la práctica de estudio (opción múltiple, verdadero o falso, completar, relacionar, ordenar y abierta; cualquier otro tipo dice «Esta pregunta se responde con tu profesor.» y no bloquea la entrega).

* **Cabecera**: título, **estado de guardado** («✓ Guardado» / «● Guardado en tu tableta»; jamás «error»), el **cronómetro del nodo** (`mm:ss` o `h:mm:ss`; «Sin límite de tiempo»; «tiempo detenido» si está suspendido), «Pregunta 3 de 12», barra de progreso y «8 de 12 contestadas».
* **Avisos que no se pisan**: el del **bloqueo** (ámbar, con texto: «Bloqueo parcial: …») vive mientras dure el bloqueo incompleto; el de **conexión** (azul suave: «Sin conexión con el aula. Tus respuestas se guardan en esta tableta y se enviarán solas.») sólo mientras no hay red. Nunca rojo y nunca sólo color (UXR-011).
* **Navegación**: «Anterior» / «Siguiente», tira de números tocables con ✓ de contestada y ★ de «Marcar para revisar» (ayuda del alumno: no cambia lo que se guarda). Si el profesor apagó el retroceso (`allowBackNavigation`) las anteriores se ven atenuadas y no se tocan.
* **Guardar**: al confirmar una respuesta se escribe en la cola cifrada **antes** de cualquier envío; luego se intenta enviar sin esperar. Si el disco no deja escribir, se lo dice en voz baja y la pregunta **no** cuenta como respondida.
* **Entregar** (PAN-123, primera parte): «Entregar» pide una sola confirmación: «Ya respondiste todas las preguntas» o «Te faltan 3 preguntas. Puedes entregar igual.» con los números sin responder. Un solo botón principal por pantalla (Siguiente mientras queden preguntas; Entregar en la última).
* **Sin salida**: el botón Atrás, el gesto de volver y cualquier navegación del Shell se descartan mientras el examen está en curso, suspendido o entregándose (`OnBackButtonPressed` + `Shell.Navigating`). Los incidentes `cierre_bloqueado` salen de las plataformas.
* **Estados como tarjeta**: la pausa, la confirmación de entrega, el «Entregando…» y las salidas («continúa en otra tableta», «se liberó») son una tarjeta. En una ventana ancha (≥ 1500 px) se ancla a los **tercios del encuadre completo** (capa de estado de `ExamenView`: Grid `*,*,*` / `*,4*,*`, tarjeta en la celda central con `Fill`; el margen de la pantalla lo pone el propio control, no la página) y la cabecera con el reloj queda visible encima. La pregunta en sí es una superficie de trabajo y no se ancla.
* **Latido** cada `plan.latido_seg` (5 s; 10 s en nivel abierto): da señal, aprende el reloj del nodo (`RelojNodo.Aprender`), sigue el plan, detecta la suspensión y la entrega hecha por el nodo, y vacía la cola. Una tableta que no recibe el examen al abrir (la biblioteca no estaba) **lo reintenta sola** en cada latido: no se deja al alumno afuera con el bloqueo puesto.

### 3.6 · Esperando al profesor (PAN-122)

Cuando el nodo suspende el intento (más de `AVACOM_EVAL_LATIDO_VENCIDO_MS` sin latido —30 s por omisión—, un reinicio del equipo del aula), la tableta muestra una **tarjeta serena**: «Tu examen está en pausa — Todo lo que respondiste está guardado y el tiempo está detenido. Tu examen queda en pausa. Avisa a tu profesor para continuar.» (MSG-033) y «No necesitas hacer nada más: cuando tu profesor te reactive, sigues justo donde ibas.». No hay cuenta atrás en rojo, ni sonido. **El bloqueo no se suelta** y lo ya capturado sigue guardándose (BR-071). La reactivación es del profesor; el siguiente latido trae el estado `en_curso` y la pantalla vuelve sola (tarda, como mucho, un latido: 5 o 10 s).

### 3.7 · Entrega (PAN-123) y resultado

* «Tu examen quedó entregado» y **qué sigue** con el texto del nodo (sin repetir la primera frase, que ya es el título): «Tu profesor publicará los resultados.» / «Algunas respuestas las revisa tu profesor.» **Nunca «calificado»** mientras quede algo por revisar (Guion, paso 13).
* Si el examen se entregó solo, se dice con una frase: «Se acabó el tiempo y tu examen se entregó solo…», «Venció el plazo…», «Tu profesor cerró el examen…».
* Sin red al entregar: «Tu entrega quedó guardada en este dispositivo y se enviará en cuanto haya conexión. No cierres el examen.» (el bloqueo sigue; sale sola con el siguiente latido).
* **Resultado** sólo si el profesor lo liberó (DEC-032): porcentaje, «Aprobado» (verde) o «Todavía no llegas al 60 % que pide el examen» (**ámbar, nunca rojo**), puntos y **pregunta por pregunta** con ✓/✗, la retroalimentación y el comentario del profesor. Antes de liberarse no hay botón: el nodo responde 403 y la pantalla dice «Tu profesor aún no publica los resultados».

### 3.8 · En la clase

`ClaseSiguiendoPage` sondea cada ~3 s `mias/` (si se sabe quién presenta) y ofrece una **tarjeta** «Tu profesor abrió un examen para la clase — Ver el examen / Continuar» por cada evaluación de ESTA clase (`sesion_id`). Un examen no se responde dentro de la clase: tiene su antesala, su bloqueo y su reloj. Sin identidad y con algo abierto en algún grupo, la tarjeta lleva a «Mis evaluaciones», donde se elige quién eres.

### 3.9 · Salida administrativa (kiosk.md §5.3)

**Siete toques en dos segundos** sobre el título del examen abren un cuadro de PIN. El PIN es **local de cada tableta**: PBKDF2-HMAC-SHA256 con 210 000 iteraciones y **sal propia**, nunca el PIN en claro (a diferencia del prototipo de referencia, que guardaba SHA-256 sin sal). Cinco fallos seguidos frenan un minuto y cada freno duplica la espera hasta una hora. Con el PIN correcto la tableta suelta el bloqueo y **el nodo registra `bloqueo_liberado`** (severidad alta) porque se soltó con el examen en marcha; el intento sigue en el nodo.

**Sin PIN fijado no hay salida local**: la vía es el *cierre forzado* del profesor desde su panel, y la tableta se suelta sola al ver el intento entregado. Quién genera el PIN por equipo y cómo se entrega durante el aprovisionamiento es la pregunta abierta **Q-83**.

---

## 4 · El corazón sin pantalla: `SesionDeExamen`

`src/Avacom.Lms.Core/Evaluacion/SesionDeExamen.cs` es toda la lógica de una tableta frente a un examen, sin una línea de interfaz, y se prueba con dobles de la API y del kiosco (53 pruebas). La pantalla (`ExamenView`) sólo la pinta.

### 4.1 · Fases

`SinExamen → Abriendo → (EsperandoAdmision) → EnCurso ⇄ Suspendido → Entregando → Terminado`, más `EnOtraTableta` (otra tableta tomó el examen: ésta se libera y deja de dar señal por un intento que no es suyo, TST-027) y `Liberada` (salida administrativa).

### 4.2 · Qué hace en cada momento

| Momento | Regla |
|---|---|
| **Abrir** | Idempotente. Declara su capacidad real (`IKioskService.Capacidad`) y sus datos. Con la tableta por debajo del nivel el examen **no empieza** y no se aplica ningún bloqueo. Activa `ExamenEnCurso` **antes** del bloqueo, aplica el plan y **cuenta lo que logró**. La secuencia arranca desde lo que el nodo ya aceptó (`secuencia_maxima`), de modo que nunca retrocede. |
| **Responder** | `ColaExamen.Guardar` (persistida y con secuencia ANTES de devolver) → recuerda la respuesta en la sesión → intenta vaciar. «Te faltan N» sale de lo que el alumno tiene respondido, venga del nodo o de este dispositivo (defecto corregido: antes se olvidaba lo ya enviado). |
| **Vaciar** | Por intento y en orden: incidentes → respuestas (`origen: cola` si esperaron más de 5 s) → informe de bloqueo → entrega guardada. Sólo con el acuse se borra lo enviado. Un 400/403/404/409 descarta SU parte; un 5xx, la red o una sesión perdida **conservan** y reintentan. |
| **Latir** | Aprende el reloj del nodo; sigue el plan (si el profesor degradó el nivel se suelta lo que ya no se exige y se informa); detecta suspensión (el bloqueo **sigue**); si el nodo entregó, **primero** envía lo capturado antes del corte y **después** suelta el bloqueo; si `sesion_activa = false`, se libera. Seguir sin red no repinta ni alarma. |
| **Entregar** | Con preguntas sin responder pide confirmar («Te faltan N») y **no llama al nodo**. Envía lo pendiente antes de la entrega. Sin red: `GuardadaSinRed`, bloqueo puesto. El bloqueo se suelta tras el acuse de la entrega, nunca antes. Suspendido: no llama al nodo. |
| **Incidentes** | Los `HechoDeKiosco` se encolan con un `ref_cliente` propio (emisor + contador persistente): reenviar la cola no duplica nada (INV-005). La tableta sólo informa los tipos que le tocan (`TiposDeIncidente.DeLaTableta`). |
| **Bloqueo parcial o fallido** | `AvisoDeSeguridad` queda hasta que un bloqueo completo lo reemplace; ningún mensaje de red lo pisa. Una excepción del kiosco se convierte en un informe `fallido` con motivo, nunca en un cierre de la app. |

### 4.3 · La cola cifrada (`ColaExamen`)

Un solo archivo AES-256-GCM de escritura atómica (`FileSystem.AppDataDirectory/examen/cola.avc`) con su **propia clave** (`examen-clave`: DPAPI en Windows, `SecureStorage` en Android): destruir la clave del modo de estudio no toca un examen en curso, y destruir la del examen deja la cola ilegible (BR-053). Si el archivo no se puede descifrar se aparta como `.dañado` y se arranca con un **emisor nuevo** para que ninguna referencia vieja choque con las nuevas. Guarda respuestas (una por pregunta; la secuencia mayor gana), incidentes, el último informe de bloqueo y la entrega pedida.

---

## 5 · El bloqueo de la tableta (kiosco)

El contrato entre el examen y el sistema operativo es `IKioskService` (Core): `StartExamLockAsync(plan)` devuelve un **`InformeDeBloqueo`** (`aplicado` · `parcial` · `fallido`, con las capas que de verdad quedaron y el motivo), `StopExamLockAsync`, `Capacidad` (lo que esta tableta puede garantizar), `LockdownSummary` (la verdad de ahora, nunca lo que se aplicó hace un rato) y los eventos `Hecho` que la sesión convierte en incidentes. La política pura (`PoliticaDeKiosco`, `FiltroDeTeclas`, `AgregadorDeTeclas`) vive en Core y tiene pruebas; lo que toca el sistema vive en `src/Avacom.Lms.Student/Platforms/` y sólo se obtiene con `KioscoReal.Crear()` (un singleton; si el servicio de la plataforma no se puede crear cae a un kiosco nulo que **dice** que no bloquea).

### 5.1 · Dos capas, y la tableta dice cuál tiene

| Capa | Qué es | Quién la da |
|---|---|---|
| **Sistema** | La tableta es un dispositivo dedicado: no hay forma de salir sin credencial de administración | Android: Device Owner + Lock Task. Windows: Assigned Access (multiaplicación) o Shell Launcher. Se provisiona con `scripts/` (§7); la app **no** puede darse esta capa a sí misma |
| **Aplicación** | Pantalla completa, teclas de salida tragadas, cierre rechazado, capturas bloqueadas, monitores extra cubiertos | La propia app, en ejecución |

`Capacidad` = `controlado` (ambas capas), `supervisado` (sólo la de aplicación) o `abierto` (ninguna). El nodo la compara con el nivel que exige el examen (BR-075); si no alcanza, **el examen no empieza solo**: el profesor decide si admite esa tableta por debajo del nivel (FUN-116).

### 5.2 · Windows

`Platforms/Windows/`: `WindowsKioskService`, `ExamKeyboardGuard`, `SecondaryScreenBlocker`, `AprovisionamientoWindows`.

- **Gancho de teclado** (`WH_KEYBOARD_LL`, instalado desde el hilo de interfaz, delegado en un campo estático para que el recolector no lo suelte): traga las teclas de Windows, Alt+Tab (y variantes con Ctrl/Mayús), Esc con cualquier modificador, Alt+F4 y F11, **incluido el KEYUP** (si no, soltar Alt después deja la tecla «pegada» en otra ventana). No cuenta repeticiones y siempre llama a `CallNextHookEx` salvo cuando traga. Se retira **primero** en `Stop`, `Dispose`, `ProcessExit`, `UnhandledException`, `Window.Closed` y en cualquier excepción de `Start`: un gancho huérfano deja al usuario sin teclado.
- **Pantalla completa real** (`AppWindowPresenterKind.FullScreen`, guarda y restaura el presentador anterior, también el de una ventana maximizada), `AppWindow.Closing` cancelado, bloqueo de capturas (`WDA_EXCLUDEFROMCAPTURE`, con `WDA_MONITOR` de respaldo).
- **Monitores extra**: una ventana nativa por monitor, fuera de Alt+Tab, que devuelve el foco al examen si lo recibe; reescanea cada 5 s y avisa `pantalla_adicional` si aparece un monitor nuevo. Sin `Path` ni `Ellipse` (Win2D).
- **Capa del sistema = consulta real, nunca un marcador.** `AprovisionamientoWindows.Consultar()` mira el almacén de Assigned Access (HKLM, sin privilegios), interpreta el XML por WMI (`MDM_AssignedAccess`, con enlace tardío por COM: no hay paquete nuevo) y, si Windows niega el acceso —lo normal en la cuenta estándar del kiosco—, decide por búsqueda de texto en el almacén (cuenta **y** ruta del ejecutable) y lo declara en `Via`. Para Shell Launcher exige la cuenta actual, este ejecutable, `IsEnabled()` y que **no corra `explorer.exe`** en la sesión. Falla siempre a «no aprovisionado» con su motivo y nunca lanza; guarda 5 s de caché.
- **Incidentes**: `salida_de_app`/`regreso_a_app` (con 300 ms de espera y comprobando que el foco no lo tiene otra ventana de la misma app, como una cubierta), `cierre_bloqueado`, `tecla_bloqueada` **agregada por minuto** (no un incidente por tecla), `pantalla_adicional`. Se entregan a la sesión en orden y en el hilo del grupo, nunca desde dentro del callback del gancho.
- **Pantalla completa desde el arranque** sólo con `AVACOM_STUDENT_KIOSCO=1` (`KioscoReal.PantallaCompletaDeArranque`, enganchada en `App.CreateWindow`); sin la variable no cambia nada.

### 5.3 · Android

`Platforms/Android/`: `AndroidKioskService`, `ExamDeviceAdminReceiver` (+ `Resources/xml/device_admin_receiver.xml`), `MainActivity`.

- Orden **exacto** de kiosk.md §3.3: `SetLockTaskPackages` → `IsLockTaskPermitted` → `SetLockTaskFeatures(None)` (sólo API ≥ 28) → `AddUserRestriction(DisallowCreateWindows)` → `StartLockTask` → ocultar barras. Antes comprueba `IsDeviceOwnerApp`: si no lo es, no lo intenta y lo dice. Todo corre por el hilo de interfaz; una excepción vuelve como informe `parcial`/`fallido`, jamás llega a la pantalla.
- Tras `StartLockTask` espera 500 ms y **pregunta** a `ActivityManager.LockTaskModeState`: sólo `Locked` cuenta como capa del sistema; `Pinned` (fijar pantalla) no, y se informa.
- Sin Device Owner queda la capa de aplicación: modo inmersivo reaplicado en cada cambio de foco, `FLAG_SECURE`, pantalla encendida, Atrás tragado (`OnBackPressedCallback` propio, que si no hay examen se desactiva y deja a MAUI hacer lo de siempre).
- `LaunchMode.SingleTask`; `OnPause`/`OnResume` emiten `salida_de_app`/`regreso_a_app` mientras hay examen.
- El receptor se llama `com.avacom.lms.student.ExamDeviceAdminReceiver` (el mismo componente que usa `scripts/android/Provision-DeviceOwner.ps1`); verificado en el manifiesto fusionado: `BIND_DEVICE_ADMIN`, `exported`, `DEVICE_ADMIN_ENABLED`, `PROFILE_PROVISIONING_COMPLETE` y el XML de políticas (`force-lock`, `disable-camera`).
- Una pantalla externa no se puede cubrir: se avisa `pantalla_adicional` y esa capa **no** se marca como lograda.

### 5.4 · Decisiones que conviene revisar

1. **Rechazo del cierre / de Atrás**: sólo mientras `ExamenEnCurso` **y** (el plan aún no se resolvió **o** pide la capa de aplicación) **y** el interruptor no está activo. Antes de saber el plan se rechaza por prudencia (kiosk.md §2); en abierto y supervisado se permite.
2. **Las salidas de la app sólo se informan si el plan las pide** (`registrar_salidas`: supervisado y controlado). El servicio de plataforma no recibe el plan cuando éste no exige bloqueo, así que emite siempre; la sesión descarta `salida_de_app`/`regreso_a_app` si `Plan.RegistrarSalidas` no es verdadero (probado).
3. **`AVACOM_EXAM_NO_LOCKDOWN=1` baja la capacidad declarada** a «abierto» (no hay capa de aplicación): un examen supervisado o controlado pasará por la admisión del profesor. Es la lectura honesta.
4. **El almacén de Assigned Access leído como texto cuenta como «aprovisionado»** cuando WMI no es legible. Alternativa más conservadora: tratarlo como no aprovisionado. Queda anotado para el CTO.
5. **Alt+F4 tragado por el gancho se cuenta como `tecla_bloqueada`**, no como `cierre_bloqueado` (ése sólo sale cuando `Closing` llega a cancelarse). Esc se traga en toda la app, también en diálogos. Alt+Espacio (menú de sistema) **no** está en kiosk.md §4.3 y no se traga.

---

## 6 · OPS: el profesor

Pantallas del profesor en `src/Avacom.Lms.Ops/Pages/Examen*.cs`, con el vocabulario y los motivos prehechos en `src/Avacom.Lms.Ops/Examen/` (`ExamenTexto`, `ExamenUi`, `HojaDeOpciones`, `CalculoDeElegibilidad`, `RespuestaLegible`, `ExamenExtra`). Todo es táctil y **sin teclado** (el nodo principal no tiene): lo que se elige se elige de una lista o de una hoja de opciones, y los motivos de anular, rechazar o cambiar un puntaje son frases prehechas. Nada es rojo salvo el botón principal del kit, y no hay sonido.

| Ruta | Pantalla | Qué hace |
|---|---|---|
| `examen-aplicar` (`curso`, `objeto`, `fuente`, `sesion`, `grupo`, `titulo`, `curso_titulo`) | **Aplicar un examen** | Nivel de control **obligatorio y sin valor inicial** (el botón queda apagado hasta elegirlo), intentos, tiempo, plazo, qué ve el alumno y cuándo, quién reactiva. Al elegir `controlado` baja sola hasta MSG-036 con las tabletas que no alcanzan. Aplicar crea la asignación y **reemplaza** la pantalla por el panel (Atrás vuelve adonde estaba, no a Aplicar). La tarjeta está en el tercio central |
| `examen-panel?asignacion=` | **Panel** | Ordenado por el nodo (quién necesita al profesor primero). Por alumno: estado, respondidas, pregunta actual, reloj, tableta y capacidad, incidentes con su severidad. Reactivar / cerrar su examen; **«Reactivar a todos (N)»** lee el conteo y dice «Vas a reactivar a N alumnos» con una sola confirmación; admitir o rechazar tabletas; bajar el nivel (dos hojas); endurecer; cerrar y liberar; aceptar o descartar un envío tardío. Sondeo de 3 s y canal de tiempo real |
| `examen-expediente?intento=` | **Expediente** | Sólo lectura mientras el alumno presenta. Línea de tiempo con hh:mm:ss, avisos (neutro/ámbar), informe de bloqueo, revisión (puntaje en pasos de 0/25/50/75/100 %; cambiar uno ya puesto pide motivo), publicar y **anular**: sólo en un intento ya entregado, botón discreto, con motivo de lista → «Anulado por *nombre* · motivo» |
| `examen-resultados?asignacion=` | **Resultados** | Con menos de 3 entregas no se calcula un promedio |

En la **clase** (`ClaseSesionPage`) el examen es tocable: «Aplicar examen» o «Ver panel del examen»; `ClaseCursoPage` ya no lo atenúa y una lección que sólo trae examen se puede elegir. En **Dispositivos** cada tableta muestra su capacidad («controlado», «supervisado», «abierto» o «no declarada»; sin declarar cuenta como abierto).

### 6.1 · Desvíos que conviene saber

1. **Con la biblioteca real el examen no aparece en la secuencia de la clase**: `classroom_engine/infraestructura/fuente_biblioteca.py` pide el curso con `mode=class` y el examen es de modo `exam`. «Aplicar examen» desde la clase sólo se ve con la fuente «ejemplo». Hace falta que la vista del docente incluya los objetos `exam` (backend, fuera de este módulo).
2. **`ElegibilidadAsync` exige una asignación ya creada**: antes de aplicar, MSG-036 se calcula en el cliente con la misma regla del nodo (inventario con `capacidad_control`, tableta de la clase y tableta asignada). Ya aplicado, el panel sí pregunta al nodo.
3. **`SesionDeClase` no trae `grupo_id`** y OPS inicia clases sin grupo: Aplicar toma el del profesor y, si tiene varios, muestra fichas para elegir.
4. **`Examen/ExamenExtra.cs`** añade lo que los registros del Core todavía no traen (`objeto_ref`, `curso_ref`, `grupo_id`, `creada_en` de la asignación; `bloqueo`, `dispositivo_id`, `calificacion_pendiente` del expediente). Es una lectura extra por pantalla; cuando Core lo incorpore se borra el archivo.
5. **`anulado_por` es un id**: se resuelve a nombre para el profesor de este equipo y para los `docente-*`; cualquier otro sale como «otra persona del profesorado o de la administración». Conviene que el nodo mande `anulado_por_rotulo`.
6. **El menú principal no tiene entrada «Evaluaciones»**: el menú hexagonal no tiene un hueco natural y el panel se alcanza desde la clase.

---

## 7 · Scripts de aprovisionamiento

`scripts/` deja un equipo o una tableta listo para el bloqueo **del sistema operativo** (la capa de aplicación vive en Student y no se instala desde aquí). Detalle, orden exacto en un aula y cómo deshacer: [`scripts/README.md`](../../scripts/README.md).

| Script | Para qué |
|---|---|
| `windows/Install-Kiosk.ps1` | Assigned Access **multiaplicación** con `DesktopAppPath` (la Student de Windows es un ejecutable sin empaquetar: no es MSIX y no tiene AUMID, así que `Set-AssignedAccess -AppUserModelId` **no** sirve). Pide una cuenta administradora de recuperación distinta y escribe `APLICAR` para continuar. |
| `windows/Install-ShellLauncher.ps1` | Alternativa con Shell Launcher v2 (Enterprise, Education, IoT; **no** Pro). |
| `windows/Remove-Kiosk.ps1` | Revierte; conserva la cuenta y sus datos. |
| `android/Provision-DeviceOwner.ps1` | `dpm set-device-owner` por ADB, con todas las comprobaciones previas (`Accounts: 0`, sin propietario, un solo usuario) y exige que `dpm list-owners` **nombre el paquete**. |
| `android/New-DeviceOwnerQr.py` | El JSON (y el PNG) del QR de aprovisionamiento para muchas tabletas, con el checksum SHA-256 en Base64 URL-safe sin relleno. |

Todos tienen **`-DryRun`** (no modifica nada; en Windows funciona sin administrador y en Android no llama a `adb`) y **`-Verify`** (consulta el **estado real**, no un marcador). El modo real de Windows exige consola elevada.

---

## 8 · Interruptores de desarrollo

| Variable | Efecto |
|---|---|
| `AVACOM_EXAM_NO_LOCKDOWN=1` | Student en Windows: la capa de aplicación **no** se aplica (sin gancho de teclado, sin cubrir monitores, el cierre se permite). Indispensable para probar OPS y Student en el mismo equipo: el gancho es global y no habría forma de volver al panel con Alt+Tab. El informe de bloqueo lo dice (`parcial`/`fallido` con «AVACOM_EXAM_NO_LOCKDOWN activo»). En los equipos de la sede **no** se define. |
| `AVACOM_STUDENT_KIOSCO=1` | Student en Windows: pantalla completa desde el arranque (cuentas dedicadas al examen). Sin ella la app se abre como siempre y sólo entra en pantalla completa al empezar un examen con bloqueo. |
| `AVACOM_EVAL_LATIDO_VENCIDO_MS` | **Nodo** (backend): cuánto silencio de una tableta basta para suspender su intento (30 000 por omisión). Para probar la pausa a mano se baja, pero **siempre por encima del latido del plan** (10 s en abierto): con 9 000 la tableta se pausa sola aunque esté bien. |

---

## 9 · Pruebas

`dotnet test tests\Avacom.Lms.Core.Tests` (siempre con `-p:OutDir=<carpeta aparte>` si OPS o Student están abiertos: bloquean las DLL).

| Archivo | Qué prueba |
|---|---|
| `ContratoEvaluacionTests` | Los DTOs contra **respuestas reales del backend** capturadas en `Fixtures/evaluacion/*.json` por `backend/evaluacion/tests/test_capturar_contrato.py` (el examen sin ninguna clave, el 202 de la admisión, el estado suspendido…). Un campo mal escrito se descubre aquí y no en una tableta. |
| `EvaluacionApiTests` | Método, URL y cuerpo de cada ruta; lo nulo no viaja; «sin tope de intentos» se dice con un nulo explícito; errores con código y extras. |
| `KioscoYPinTests` | La política del bloqueo (aplicado/parcial/fallido según lo pedido y lo logrado) y el PIN (PBKDF2, sal, freno). |
| `ColaExamenTests` | Secuencia monotónica aunque se vacíe o se reinicie, cifrado en disco, clave destruida, reconocer sin perder lo nuevo, entrega guardada. |
| `SesionDeExamenTests` | El examen de punta a punta con dobles: bandera antes del bloqueo, bloqueo parcial que no se esconde, guardar antes de enviar, suspensión que no suelta, entrega que suelta sólo tras el acuse, salida administrativa, y que las salidas de la app sólo se informan si el plan las pide. |
| `FiltroDeTeclasTests` | Qué teclas se tragan (Windows, Alt+Tab, Esc con modificador, Alt+F4, F11: un barrido de las 256 teclas × 8 combinaciones prueba que sólo esas 6 teclas base se descartan) y el resumen por minuto de `tecla_bloqueada`. |
| `DispositivoCapacidadTests` | La capacidad que declara cada tableta en el inventario de OPS («sin declarar» cuenta como abierto). |

El recorrido real de Student —del «¿Quién eres?» al resultado— lo hace `tests/Avacom.Lms.Student.Uia/escenario_examen.py` (UI Automation, sin ratón ni teclado ni foco; `congelar.ps1` provoca la pausa y `tercios.ps1` dibuja la cuadrícula sobre las capturas). Necesita un nodo aparte sembrado con `backend/tools/sembrar_evaluacion.py` y Student lanzado con `AVACOM_EXAM_NO_LOCKDOWN=1`. Las preguntas de elegir una opción son filas con gesto táctil que el árbol de accesibilidad no expone como botón, así que el guion sólo responde las abiertas y las de ordenar.

Regenerar los contratos: `set AVACOM_CAPTURAR_CONTRATO=<carpeta Fixtures\evaluacion>` y `manage.py test evaluacion.tests.test_capturar_contrato`.

---

## 10 · Estado de construcción y límites

### 10.1 · Lo que está probado

| Capa | Cómo se probó |
|---|---|
| Backend (`backend/evaluacion/`) | 302 pruebas propias y la suite completa del backend. Los contratos que consume el cliente se capturan de respuestas reales. |
| Cliente sin pantalla (`Core/Evaluacion/`) | 475 pruebas de `Avacom.Lms.Core.Tests` en verde: contrato, API, PIN y política de bloqueo, cola cifrada, sesión, filtro de teclas y capacidad de dispositivos. |
| Pantallas de Student | Compilan para Windows y Android (0 errores). El guion `escenario_examen.py` pasó **27 de 27 comprobaciones** contra un nodo real aparte: «¿Quién eres?», Mis evaluaciones, antesala, espera y decisión de admisión, examen (escribir una respuesta abierta, ordenar, «Siguiente», contador y guardado), «Te faltan N preguntas», pausa por falta de latido y reactivación desde el panel, entrega, tarjeta de calificación pendiente y los datos que ve el panel del profesor. |
| Composición | Antesala, espera, pausa, confirmación y entrega se verificaron por captura a 1920 × 1040 con la cuadrícula de tercios: tarjeta en el tercio central en X y de 1/6 a 5/6 en Y del área de la aplicación. |
| OPS | Compila sin errores ni advertencias; el agente que lo construyó lo recorrió en vivo contra un nodo aparte con un host de pruebas de la API de Contenido v2 que califica de verdad (aplicar, panel, expediente, revisión, resultados, dispositivos). |

### 10.1.1 · Lo que la prueba en vivo encontró

* **La tarjeta de entrega repetía** «Tu examen quedó entregado» como título y como primera frase del mensaje del nodo: ahora sólo repite lo que sigue.
* **Los estados del examen (pausa, confirmación) eran una banda a todo lo ancho** en una ventana de 1920 px: ahora son una tarjeta anclada a los tercios.
* **La espera de admisión perdía su segunda frase** («No cierres esta pantalla: el examen empieza solo») cuando el nodo mandaba su propio texto: ahora la lleva siempre.
* No era un defecto, pero cuesta descubrirlo: con el nivel abierto la tableta late cada 10 s, así que un nodo con vencimiento de latido de 9 s pausa un examen sano.

### 10.2 · Lo que NO se pudo probar (no hay el hardware)

Se declara sin rodeos para que nadie lo dé por verificado:

- **Lock Task / Device Owner en una tableta Android real.** El orden de las llamadas y los permisos está escrito como indica la documentación de Android, pero no corrió contra un dispositivo. El `InformeDeBloqueo` existe justamente para que la primera tableta real diga qué logró.
- **El gancho de teclado global y la cobertura de monitores en Windows**, fuera del propio equipo de desarrollo (el gancho es global; probarlo aquí inutilizaría el escritorio).
- **Assigned Access y Shell Launcher**: los scripts se ejercitaron sólo con `-DryRun` y `-Verify`; el XML de Assigned Access con `DesktopAppPath` no se aceptó en un equipo real.
- **El flujo del QR de aprovisionamiento** de Android.
- **La latencia con 50 tabletas** latiendo a la vez contra un nodo.

### 10.3 · Límites conocidos y decisiones abiertas

- **Ctrl+Alt+Supr no se puede interceptar** desde ninguna aplicación. `kiosk.md` lo da por bloqueado con Shell Launcher; lo que se puede hacer es quitarle al usuario del examen las opciones de esa pantalla por política (cuenta estándar, sin «Cambiar de usuario»). Esa discrepancia queda anotada para el CTO.
- **Q-83 · PIN de salida por equipo.** El PIN es local y no tiene valor por defecto: sin PIN fijado no hay salida local y la vía es el cierre forzado del profesor. Quién lo genera y cómo viaja durante el aprovisionamiento está sin decidir.
- **Q-82 · Capturas de pantalla.** No se capturan imágenes del examen; la pregunta es si se debe registrar sólo el intento de captura.
- **Hasta que un bloqueo completo lo reemplace**, `AvisoDeSeguridad` queda visible: un bloqueo parcial no se esconde.
- Hay una prueba del backend anterior a este módulo (`AuditoriaTests`) que falla de forma intermitente por el vaciado de la bitácora; se dejó fuera de este alcance y quedó señalada como tarea aparte.
