# 15 · Licenciamiento (MOD-018) · Verificación independiente

| Campo | Valor |
|---|---|
| Estado | **En curso** (2026-10-20). Se completa cuando la otra sesión cierre las Fases 2 y 3 |
| Quién | La sesión que mantiene `tools/licencias/` (emisor) y la documentación de requerimientos, guías y funciones que se podrían perder. **No escribió** el nodo ni los clientes: los lee, los prueba **desde fuera** y reporta |
| Para qué | El encargo pide «probar cada funcionalidad», «probar todo lo desarrollado después del licenciamiento» y «arreglar los defectos». Quien construye no es la mejor persona para encontrar sus propios defectos: esta verificación los busca con otra mirada |
| Método | (1) Leer el código con la pregunta «¿cómo se rompe esto, o cómo lo rompe alguien con la fecha, el disco o la red?». (2) **Reproducir** cada sospecha con una prueba contra el **nodo real** (el arnés de `backend/licenciamiento/tests/base.py`: base, bitácora, anclas y permisos de verdad; sólo el reloj y el hardware son falsos), **fuera del repositorio**, sin tocar la base ni los logs del repositorio. (3) Un hallazgo sólo se reporta si una prueba lo demuestra. (4) Lo corrige quien es dueño del código, o esta sesión como `Bugfix:` si el dueño lo autoriza |
| Relacionados | [impacto-funciones.md](impacto-funciones.md) (hallazgos `H-nn`) · [01-diseno.md](01-diseno.md) · [03-pruebas.md](03-pruebas.md) · [05-emision.md](05-emision.md) |

## 1 · Resultado hasta ahora

| Qué | Resultado |
|---|---|
| Emisor (`tools/licencias/tests`) contra el nodo vigente | **100 de 100**. Una prueba describía el margen anterior (38 h) y se corrigió: con la tolerancia de un día que ahora tiene el nodo, la licencia activa **siempre** con 48 h de atraso a cualquier hora de emisión y hasta 63 h con la hora del caso (`Bugfix:` 2b4e737a) |
| Interoperabilidad emisor ↔ nodo (`backend/licenciamiento/tests/test_emisor_real.py`) | **13 de 13** en ≈ 13 s: el emisor real firma, el nodo real activa, renueva y traslada por su API. Se salta sola sin la herramienta; sólo usa llaves que crea en una carpeta temporal. Comprueba la tolerancia de `desde` con relojes de −30, −45 y −72 horas, el traslado del técnico y que el técnico no renueva |
| Clasificación de rutas frente a la licencia | **316 rutas: 109 intocables · 178 núcleo · 29 licenciables**, igual que en la segunda foto. Ninguna ruta de una clase, un examen, el modo estudio, el inicio de sesión ni la lectura de calificaciones se puede apagar (inventario recorriendo el resolvedor real de Django) |
| Fallas de reloj y límites | **Tres defectos confirmados y abiertos: H-13, H-14 y H-15** (§2) |
| Backend completo, Core, OPS, Student, UIA de la pantalla Licencia, regresión de módulos | **Pendiente**: se corren cuando la otra sesión termine su propia corrida (dos corridas completas a la vez se estorban) |

## 2 · Defectos encontrados

| # | Qué | Estado |
|---|---|---|
| **BUG-1** | `Instalar` aceptaba una licencia con `desde` a menos de un día pero `estado.calcular` no aplicaba esa tolerancia: con la evaluación vencida el colegio quedaba **degradado** justo después de activar | **Corregido** por el nodo (D-8: una sola tolerancia) |
| **BUG-2** | Un secreto propio del nodo ilegible devolvía un valor en memoria y no guardaba nada: una identidad distinta en cada arranque (F-08, sin salida) | **Corregido** (D-9: se aparta, se guarda uno nuevo, se asienta una vez) |
| **DECISIÓN-A** | El técnico recibía 403 al trasladar la licencia al equipo que restauró la base del viejo | **Adoptada** (D-10: otra huella = traslado, `license.activate`) |
| **MENOR** | `HEAD` se saltaba el 402 | **Corregido** (D-11) |
| **H-13** | **Atrasar la fecha del equipo alarga la licencia** lo que se atrasó: el instante confiable es `max(reloj, marca alta)` y, con el reloj por debajo de la marca, ese máximo es un valor fijo: el tiempo de la licencia se congela hasta que la hora de pared alcanza la marca. Con 30 días de vigencia y 30 de gracia, atrasar la fecha 100 días degrada a los **151 días reales** en vez de a los ~51; con 300 días, a los 70 días reales sigue «activa» con `ahora_confiable` clavado en el día 10. Una pila de BIOS agotada (el reloj vuelve a 2010 en cada arranque) la vuelve inmortal y la evaluación no termina nunca. Contradice P-06 | **Abierto** · reportado a la otra sesión con la prueba y el arreglo (piso monótono, LIC-B-25) |
| **H-14** | El tope de **72 h** del aplazamiento por un salto sospechoso hacia adelante se mide en esa misma línea congelada: **adelantar la fecha y devolverla** aplaza la degradación lo que duró el salto (+365 días → degrada a los **368** días reales en vez de a los 3) y un nodo ya `degradada` recupera sus cuatro módulos (pasa a `en_gracia`). Cuesta dos cambios de fecha | **Abierto** · mismo arreglo |
| **H-15** | El nodo acepta una licencia **firmada** con un límite en **0** (equipos, usuarios, concurrentes normales o en pico). Un 0 no limita: **detiene**. Con concurrencia 0 el aula responde `409 aula_llena` («alcanzó su capacidad (0 dispositivos)») al **primer** alumno; con equipos o usuarios en 0 no se registra ninguna tableta ni persona nueva. El emisor oficial no emite ceros (lo valida y lo prueba), pero ningún archivo, venga de donde venga, puede detener una clase (R-01) | **Abierto** · el arreglo es una línea en `desde_campos` (rechazar un límite < 1) más una prueba del formato que usaba 0 como valor de ida y vuelta |

**Estado del arreglo de H-13, H-14 y H-15:** hay un parche validado, **sin aplicar al repositorio** hasta que el dueño del código lo acepte (reparto propuesto: lo aplica esta sesión como un `Bugfix:` propio de cinco archivos más dos de pruebas, o lo aplica el dueño). Sobre una copia del backend: las 250 pruebas del módulo siguen en verde, las 100 del emisor también, las 9 pruebas de reloj nuevas pasan (7 fallan sin el parche) y las 3 de límites también.

**Cómo repetir H-13 y H-14** (cinco pruebas, ≈ 40 s; fallan hasta que se arregle): están en la carpeta de trabajo de esta sesión y usan el arnés del nodo. El esquema, para quien las reescriba en su propio estilo:

```text
BaseLicencia · activar_ok(vence=t0 + 30 días)   → 30 días de vigencia y 30 de gracia; degrada a partir del día 61
H-13   10 días de uso → reloj.saltar(−300 días) → tick → 70 días reales (ticks de 12 h con reloj.avanzar)
       esperado: «degradada»  ·  actual: «activa», dias_restantes = 20, ahora_confiable clavado en el día 10
H-14   59 días → tick (en_gracia) → reloj.saltar(+10 días) → tick (en_gracia: bien) → reloj.saltar(−10 días) → 5 días reales
       esperado: «degradada» a las 72 h  ·  actual: «en_gracia» con los cuatro módulos
```

**Arreglo propuesto** (no decide H-09): un **piso monótono**. Mientras el reloj de pared esté por debajo de la marca, el instante confiable avanza con el reloj monótono del proceso (`max(marca, confiable_previo + Δmonótono)`) y la marca sube con él; con el reloj en orden sigue siendo `max(reloj, marca)`. Tras un reinicio sólo se pierde el tiempo apagado, que nadie puede aprovechar. Con el confiable avanzando uno a uno con el tiempo real, las 72 h del tope vuelven a ser 72 h de verdad. **Efecto colateral que hay que saber**: un salto accidental al futuro (H-09) hoy «se salva» por este defecto (el nodo se queda en gracia lo que dure el salto); con el arreglo degrada a las 72 h. Por eso la decisión del CTO sobre H-09 (Q-L13) pesa más.

**Menores de documentación** (de la otra sesión, reportados): `01-diseno.md` §5 dice que «hoy la salida es una licencia de recuperación emitida por AVACOM», pero esa bandera no existe ni hay ruta para bajar la marca (lo dice su propio `02-api.md` §3); D-9 nombra el archivo apartado `<nombre>.ilegible-<n>-<fecha>` y el código lo escribe `<nombre>.ilegible-<fecha UTC>` (con `-<n>` sólo si choca).

## 3 · Cómo repetir lo que ya está verificado

```bash
# 100 pruebas del emisor (≈ 28 s), desde la raíz del repositorio
backend/.venv/Scripts/python.exe -m unittest discover -s tools/licencias/tests -t tools/licencias

# 13 pruebas de interoperabilidad emisor ↔ nodo (≈ 13 s)
cd backend && .venv/Scripts/python.exe manage.py test licenciamiento.tests.test_emisor_real
```

## 4 · Pendiente (se completa en este documento)

1. Corrida completa del backend (`manage.py test`, línea base 1945 y 8 omitidas en 870 s), `makemigrations --check`, y `dotnet test` de Core (1221), OPS (399) y Student (102) con las pruebas nuevas.
2. Recorrido por UI Automation de la pantalla **Licencia** de OPS en un nodo aislado (puerto 8010, unidad virtual para la memoria USB, **sin teclado**): activar, renovar, liberar, copia, banner por rol, y verificación con la regla de tercios.
3. Regresión de los módulos desarrollados después del licenciamiento con la licencia en cada estado (activa, en gracia, degradada, cupo lleno): Reportes, Búsqueda, Importación, Escalas de calificación; el aula, el examen y el modo estudio **no** deben notar nada; Student con el cupo de equipos agotado.
4. El contenido del instalador reconstruido: sin emisor, sin llave de desarrollo, sin llaves privadas, con la pública de producción cuando exista (hoy `produccion.json` está vacío).

## 5 · Lo que esta verificación no puede comprobar

El TPM y el SMBIOS del panel real, una instalación real con administrador, DPAPI desde la cuenta SYSTEM, el ancla del registro de Windows con permisos reales, una tableta Android 14 física, un antivirus, la firma de código y la ceremonia real de llaves. Todo lo que se verificó usa relojes y hardware falsos sobre un nodo real, y llaves creadas por las propias pruebas.
