# 05 · Acceso del alumno en AVACOM Student (RF-20…RF-28, RF-30, RF-32)

| Campo | Valor |
|---|---|
| Fecha | 2026-10-06 |
| Fuente normativa | [requisitos.md](requisitos.md) · PARTE D (D.4), §5, §8 (AC-A11…A21), RN-30…RN-37 y RN-40…RN-47 |
| Alcance | Sólo la tableta (`src/Avacom.Lms.Student`). OPS y el backend no cambian aquí, salvo la corrección del teclado compartido (§4) |

## 1 · Qué ve el alumno

El acceso sigue en `ConnectionPage`, con la misma composición (tarjeta de vidrio, lápiz 3D, panal, `AjustarComposicion`) y sin el saludo BIENVENIDO. Los pasos se
pintan dentro de la misma tarjeta: arriba, título, instrucción y **aviso** (qué pasó y qué sigue, §5); abajo, lo que se toca; fijas al pie, **«No estoy en la
lista · soy nuevo»** y **«Entrar como visitante»**.

| Paso | Qué hace | Notas |
|---|---|---|
| 0 · Conexión | Dirección del aula, «Comprobar conexión», «Entrar al aula» | Sin sesión obligatoria (prototipo) se escribe el nombre como siempre |
| 1 · Grupo | Tarjetas grandes con los grupos (`/api/acceso/aula/grupos/`) | Antes, la tableta se presenta con su latido (MOD-009); sin registro el nodo no da nombres |
| 2 · Nombre | La lista del grupo: sólo alias | «Entrar con mi código» queda como salida de siempre |
| 3 · PIN | `TecladoPinView` (teclas de 68 × 52, de `LongitudPin` a 6 dígitos) | Preescolar (`UsaAvatar`): `AvatarPickerView`, 12 dibujos de 56 |
| Elegir mi PIN | «Todavía no tienes PIN. Elige uno de 4 números que recuerdes.» — dos veces | Si la lista no lo sabía, el nodo contesta `pin_pendiente` y se pasa aquí |
| Soy nuevo | Nombre y apellido (teclado del sistema: lo único que se escribe), grupo, PIN dos veces | `alias_duplicado` → «Usar «Juan Pé.»» con un toque, sin volver a marcar |
| Visitante | Un botón y «Sí, entrar como visitante» | Banda amarilla en todas las pantallas mientras dure |
| Tableta en pausa | `dispositivo_en_pausa`: cuenta atrás, teclado apagado, visitante a la vista | No nombra a nadie |
| Grupo con contraseña | Pasa directo a «Entrar con mi código» | El nodo no deja entrar por nombre con `PASSWORD` |

Ni el PIN ni la clave quedan escritos: el teclado se vacía al repintar y, al volver al acceso, no queda grupo, nombre ni datos de alta (BR-053). Sin nodo, el aviso
lo dice y «Reintentar» repite lo último **sin volver a marcar** (el PIN vive sólo en memoria hasta entonces); nunca se simula un acceso.

**Tamaños (corrección de diseño del 2026-10-06):** lo que se toca es del mismo orden que «Entrar al aula» (52 de alto): teclas 68 × 52, grupos de 64, nombres y
acciones de 52. Prevalece sobre las «72 pt» de RF-00a, que hacían que el teclado dominara la tarjeta.

## 2 · Fuera del acceso

| ID | Dónde | Qué cambió |
|---|---|---|
| RF-23 | `BandaDeVisitante` + `AppShell.OnNavigated` | Banda amarilla `MensajesDeAcceso.BandaVisitante` arriba de cada pantalla. Se inserta una fila en la rejilla raíz sin re-colgar vistas (una WebView en clase no se recarga) |
| RF-24 | `StudyModeViewModel`, `EstudioCompose` | Con sesión, el modo estudio usa a quien entró y ya no pregunta «¿Quién eres?» (sin «Cambiar»). Visita: no llama al aula y ofrece «Ir a la clase en vivo» y «Leer mis asignaturas». Sin sesión (prototipo): igual que antes |
| RF-25 | `StudentMenuPage` | Visita: Perfil y Progreso atenuados y sin respuesta, «Exámenes» fuera del dock, rótulo «Visitante» |
| RN-43 | `EvaluacionesPage` | Si una visita llega a «Mis evaluaciones», se le explica que no aplica |
| RF-27 | `App.AlRechazarLaSesion` | Avisos de otra tableta, inactividad y expirada. Una visita que termina vuelve al acceso limpio (sin readmitirse en la clase) con su propio aviso; el nodo ya retiró la cuenta efímera |

**Visitante en clase:** no existe en el nodo una ruta para encontrar «la clase en curso del grupo» sin código, así que la visita entra al menú limitado y desde
«Clase en vivo» se une con el código del profesor, como todos. El backend no da a la visita permisos `study.*`: por eso el modo estudio de una visita no
muestra prácticas propias sino adónde ir a practicar (pendiente de confirmar, §5).

## 3 · Lógica probada sin interfaz

`src/Avacom.Lms.Student/Acceso/FlujoDeAcceso.cs` (pasos, reintento, pausa, alta con sugerencia, visitante, código), `DobleMarcado.cs` y `Avatares.cs` se compilan
en `tests/Avacom.Lms.Student.Tests` (`AccesoAlumnoTests`, con un nodo de mentira `Ayudas/FalsoAccesoApi.cs`).

```
dotnet test tests/Avacom.Lms.Student.Tests
dotnet test tests/Avacom.Lms.Core.Tests
```

## 4 · Corrección en el control compartido

`src/Avacom.Lms.Ui/Controls/TecladoPinView.cs`: las teclas 1–9 capturaban la variable del `for`, así que **todas marcaban «10»** (dos dígitos por toque: «1234»
llegaba como «101010» y fallaba). Se descubrió en la prueba de interfaz. Cada tecla guarda ahora su dígito. Además «Listo» se atenúa mientras no se puede
tocar (en Windows el botón rojo deshabilitado se veía activo). Afecta también a OPS (PIN maestro); main recibió el mismo arreglo (d877aaf7) junto con el
descarte de un segundo `Clicked` en 180 ms (f59a54df). El recorrido de interfaz lo comprueba: un toque en «5» deja «1 de 6 números marcados».

## 5 · Cómo correr el recorrido de interfaz (RF-30)

Arnés: `tests/Avacom.Lms.Student.Uia/` (`sembrar_acceso.py`, `escenario_acceso.py`, `lanzar-student.ps1 -SinFoco`, `ui-student.ps1`, `tercios.ps1`).

1. **Nodo aislado** (nunca el del aula ni el de desarrollo en 8000), desde `backend/`:
   `AVACOM_LMS_DB=<archivo nuevo fuera del repo>` · `AVACOM_LMS_EXIGIR_SESION=1` · `manage.py migrate` ·
   `AVACOM_LMS_PIN_MAESTRO=482915 manage.py acceso_instalar --codigo IE-PRUEBA --nombre "Aula de prueba" --admin-dni 900001 --admin-nombres Ana --admin-password "Rectoria.2026!"` ·
   `manage.py runserver 127.0.0.1:8010 --noreload`.
2. **Sembrar**: `AVACOM_LMS_PIN_MAESTRO=482915 python sembrar_acceso.py` (grupos Quinto B y Preescolar A con AVATAR, un profesor, Juan P./Ana R./Sofía R. en PIN
   pendiente/Lía M. con «gato», y la tableta de esta máquina).
3. **Student** compilado a una carpeta aparte (`dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0 -p:OutDir=<carpeta>`)
   y lanzado con `lanzar-student.ps1 -Exe <carpeta>\Avacom.Lms.Student.exe -SinFoco` (devuelve el foco: lo que se teclee en otra ventana no cae en la tableta).
4. `python escenario_acceso.py` (variables `AVACOM_AULA_URL`, `AVACOM_TAMANO=1280x800`, `AVACOM_VERTICAL=800x1280`). Deja capturas con tercios y el texto de cada
   pantalla en `salida/capturas-acceso/` y el veredicto en `salida/informe-acceso.json`.

Un nodo sembrado sirve para **una** corrida: el alta de «Juan Pé.» no se repite y la pausa de la tableta dura 2 minutos. Student comparte `Preferences` con la
instancia del usuario: copiar antes `%LOCALAPPDATA%\User Name\com.avacom.lms.student\Settings\preferences.dat` y devolverlo al terminar.

## 6 · Preguntas abiertas

| # | Pregunta | Qué hice mientras tanto |
|---|---|---|
| PS-01 | ¿La visita debe poder hacer **prácticas** del modo estudio (RN-42 «leer lecciones y practicar»)? El nodo no le da permisos `study.*` | Modo estudio de visita = aviso + clase en vivo + asignaturas |
| PS-02 | «Entra a la clase en curso del grupo» (RF-23) necesita una ruta que diga qué clase está abierta para un grupo sin el código | La visita va al menú limitado y se une con el código |
| PS-03 | ¿Se esconde «Entrar como visitante» cuando la institución lo apaga (RN-47), o se muestra y explica? | Se esconde, igual que «Soy nuevo» con el autoregistro apagado (AC-A20) |
