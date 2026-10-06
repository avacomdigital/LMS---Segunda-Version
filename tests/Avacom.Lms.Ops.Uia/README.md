# Recorrido de interfaz del acceso de OPS (RF-31)

Prueba de punta a punta de las pantallas de acceso de AVACOM OPS Master contra un nodo **aislado**, manejando la ventana por UI Automation
(sin ratón ni teclado) y capturándola con `PrintWindow`.

| Archivo | Para qué |
|---|---|
| `recorrido_acceso.py` | El recorrido completo: levanta el nodo, abre OPS, recorre las pantallas, comprueba y captura |
| `ui-ops.ps1` | Lista controles, invoca botones por nombre, escribe en campos, marca un PIN en el teclado propio, espera un texto, captura el área de contenido |
| `tercios.ps1` | Dibuja la cuadrícula de tercios sobre una captura (así se juzga la composición de las pantallas de tarjeta) |

## Cómo se corre

```powershell
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -p:OutDir=C:\temp\ops-uia\
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_acceso.py --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe [--puerto 8011] [--salida <carpeta>]
```

Tarda unos 6 minutos. Sale con 0 si todo se cumplió y lista lo que falló si no. Las capturas (`NN-nombre.png` y `NN-nombre-tercios.png`) quedan en
`salida/` (ignorada por git) o en la carpeta indicada.

## Qué recorre

1. **Primer arranque** con el nodo sin instalar: se abre solo; país, aula (el código sale del nombre), administrador; PIN `123456` rechazado por trivial
   (AC-A02); PIN marcado dos veces; **hoja de acceso** con la contraseña inicial y el PIN; «Ya la entregué» (AC-A01).
2. **Administración**: documento + contraseña de la hoja → el nodo pide el **PIN maestro** → «Elige tu contraseña» → tablero.
3. **Seguridad del aula**: estado real del PIN y **cambio del PIN maestro** (dos veces en el teclado).
4. Por la API, como lo haría la administración: un grupo, un alumno de padrón (PIN pendiente), una tableta, un alumno que se registró solo y un visitante.
5. **Crear mi usuario** con un PIN equivocado antes («Te quedan 4 intentos») y luego el bueno: entra directo (AC-A08).
6. **Grupos**: «sin confirmar» y «PIN pendiente»; Confirmar y Nuevo PIN (sin ningún número a la vista).
7. **Olvidé mi contraseña** → «Cerramos tus sesiones abiertas…» → entra con la nueva (AC-A09).
8. **Vencimiento**: a 12 días la banda del tablero lo dice con los días (AC-A05); vencido, «Crear mi usuario» explica qué pasó (AC-A04), la
   administración entra sin PIN y los profesores siguen entrando (RN-09). El paso del tiempo se simula moviendo `vence_en` en la base temporal.
9. **Segundo arranque**: la hoja confirmada ya no aparece (AC-A03); el **monitor** lista al visitante y lo vincula a un alumno (RN-44).

## Cuidados (el equipo lo comparte quien trabaja en él)

- **El nodo es aislado**: base temporal propia, `127.0.0.1:8010` (o `--puerto`), sesión obligatoria. Nunca el nodo del aula (`:8000`).
- **OPS corre con un perfil de pruebas** (`AVACOM_OPS_PERFIL=uia-<hora>`, `AVACOM_OPS_SERVIDOR`): sus preferencias y su almacén cifrado van en un
  contenedor aparte y la dirección del servidor sale de la variable, así que la OPS de quien trabaja en el equipo no cambia. `AVACOM_OPS_RUTA` (sólo con
  el perfil) lleva una vez el tablero a otra pantalla, porque las teselas hexagonales no se pueden tocar por UI Automation.
- **Contraseñas**: el campo enmascarado de MAUI en Windows no acepta el `ValuePattern` de UI Automation (el texto se ve, pero la contraseña queda
  vacía). Con el perfil, `AVACOM_OPS_CLAVES_VISIBLES=1` deja esos campos sin máscara; el enmascarado en sí no lo prueba este recorrido.
- **Candado de pantalla**: antes de abrir ventanas toma `%LOCALAPPDATA%\Temp\avacom-gui.lock` (lo usan también las pruebas de Student) y lo suelta al
  terminar. La ventana de prueba toma el foco mientras dura.
- Si una OPS del usuario está abierta, compila con `-p:OutDir=` a otra carpeta (la suya bloquea `bin\`); el guion sólo cierra las instancias que abre.
- UI Automation no ve lo que queda debajo de una WebView; en estas pantallas no hay ninguna.
