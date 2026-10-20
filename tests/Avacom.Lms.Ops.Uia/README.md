# Recorrido de interfaz del acceso de OPS (RF-31)

Prueba de punta a punta de las pantallas de acceso de AVACOM OPS Master contra un nodo **aislado**, manejando la ventana por UI Automation
(sin ratón ni teclado) y capturándola con `PrintWindow`.

| Archivo | Para qué |
|---|---|
| `recorrido_acceso.py` | El recorrido completo: levanta el nodo, abre OPS, recorre las pantallas, comprueba y captura |
| `ui-ops.ps1` | Lista controles, invoca botones por nombre, escribe en campos, marca un PIN en el teclado propio, espera un texto, captura el área de contenido |
| `tercios.ps1` | Dibuja la cuadrícula de tercios sobre una captura (así se juzga la composición de las pantallas de tarjeta) |
| `recorrido_licencia.py` | La pantalla **Licencia** (MOD-018) de punta a punta: ver más abajo |
| `licencia_en_vivo.py` | Las rutas del backend con la licencia en cada estado y el cupo, por HTTP, sin ventanas: ver más abajo |
| `licencia_paquete.py` | El backend empaquetado del instalador y el emisor portátil trabajando juntos, como producción: ver más abajo |

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

## Licencia (MOD-018)

Tres guiones que comprueban la licencia **desde fuera**, contra un nodo aislado (puerto propio, base y carpeta de estado temporales, sesión obligatoria): los dos primeros con `AVACOM_LICENCIA_MODO=firmada`; el tercero con el
backend **empaquetado** del instalador, que se clasifica solo como producción. Sólo corren en un árbol de desarrollo: las licencias se firman con las llaves de desarrollo de `backend/licenciamiento/tests/emisor.py`, como lo
haría AVACOM con la solicitud que OPS guarda (el tercero las usa únicamente para comprobar que el paquete **no** las acepta).

| Guion | Qué comprueba | Cuánto tarda |
|---|---|---|
| `recorrido_licencia.py --ops <exe> --salida <carpeta>` | **La pantalla Licencia por UIA, sin teclado y con la regla de tercios en cada captura**: evaluación y su aviso desde el primer día · activar en los tres pasos con una licencia firmada a partir de la solicitud (una memoria USB simulada con `subst`) · copia de custodia (tres archivos, hoja sin documentos ni nombres) · renovar · «Vencida · en gracia» · «Funciones en pausa» y el aviso del menú · el soporte técnico **no renueva** · la administración renueva · liberar y volver a activar · el profesor no ve botón ni aviso · con la licencia en pausa, Reportes y Buscar lo dicen y Evaluaciones, Calificaciones y Clase de hoy abren sin aviso | ≈ 12 min |
| `licencia_en_vivo.py rutas` | **Todas las rutas del backend** (el inventario sale del resolvedor de Django en el momento) con la licencia en evaluación, activa, en gracia y degradada: la licenciable apagada responde 402 `no_disponible_por_licencia`, ninguna intocable ni de núcleo lo responde y todas responden lo mismo que con la licencia activa. Imprime los 5xx para clasificarlos a mano | ≈ 5 min |
| `licencia_en_vivo.py cupo` | Con 2 equipos y 6 usuarios: la tercera tableta recibe 402 `cupo_agotado`, las registradas y el equipo maestro siguen, la clase y el visitante entran siempre, el séptimo usuario recibe 402 y el estado avisa del cupo al ciclo siguiente del programador | ≈ 1 min |
| `licencia_paquete.py` | **Lo que se entrega**: copia el backend empaquetado (`dist\staging`, con su Python embebido y Daphne) y el emisor portátil (`tools\licencias\dist`) a una carpeta temporal con `%ProgramData%` redirigido. Como se entrega (`produccion.json` vacío): modo «firmada», entorno «produccion», «sin licencia» con 30 días, solicitud con la huella de este equipo, y una licencia firmada con la llave de desarrollo **se rechaza** (`kid_desconocido`), igual que una de una llave que el nodo no conoce. Tras la «ceremonia» (la pública del emisor en el `produccion.json` de la copia): la de desarrollo sigue rechazada, la del emisor portátil se activa y queda «activa» con sus cuatro módulos, y tras reiniciar el proceso del nodo sigue activa | ≈ 1 min |

```powershell
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_licencia.py --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\capturas-licencia [--puerto 8013] [--sin-modulos]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_en_vivo.py todo [--puerto 8014]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_paquete.py [--puerto 8016] [--staging <dist\staging>] [--emisor <carpeta del emisor portátil>]
```

`licencia_paquete.py` necesita el instalador preparado (`installer\build\Build-Installer.ps1` deja `dist\staging`) y el emisor compilado (`tools\licencias\Build-Emisor.ps1`); si falta alguno lo dice y sale con 2. Corre al compilar cada versión: es la prueba de que el
instalador que se entrega, el emisor y la llave pública que se incruste después de la ceremonia **funcionan juntos**.

Cuidados: los mismos de arriba (nodo aislado, perfil de OPS de pruebas, candado de pantalla). Dos más: la sesión del personal es **única**, así que el guion mira el estado por la API con una cuenta lectora aparte (entrar con
la de la administración cerraría la de OPS); y los controles se tocan por `AutomationId` con la acción `tecla` de `ui-ops.ps1` porque la página y la hoja tienen botones que se llaman igual («Liberar este equipo»).
