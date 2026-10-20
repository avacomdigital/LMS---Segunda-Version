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
| Fallas de reloj y límites | **Tres defectos confirmados y ya corregidos: H-13, H-14 y H-15** (§2) |
| Módulo de licencia del backend (250 pruebas) sobre el árbol commiteado | **250 de 250** (6 omitidas por diseño) en ≈ 147 s; la suite completa de la otra sesión (2195, 14 omitidas) se toma como línea base del backend y se repite una vez, cuando los arreglos de §2 estén dentro |
| Pruebas de .NET sobre el árbol commiteado (12:07) | **Core 2122 · OPS 453 · Student 102**, todas correctas (líneas base antes de empezar: 1221 · 399 · 102; la diferencia incluye lo de otros módulos que se commiteó a la vez) |
| **Regresión en vivo de las 316 rutas** con la licencia en cada estado (evaluación, activa, en gracia, degradada) contra un nodo aislado por HTTP real: 1244 peticiones | **0 desvíos**: toda ruta licenciable con su módulo apagado responde exactamente `402 no_disponible_por_licencia` con su capacidad y con el módulo encendido no lo responde; **ninguna de las 109 intocables ni de las 178 de núcleo** responde nunca ese 402, y todas responden lo mismo en los cuatro estados que con la licencia activa |
| 5xx de ese barrido | 25 rutas, **iguales en los cuatro estados** (no vienen de la licencia): 21 son 503 («AVACOM Biblioteca no está encendida en este equipo»: el nodo de prueba no tiene la biblioteca conectada) y 2 son 501 («llega en una versión posterior») —ambos por diseño— y **1 par es un defecto real de otro módulo, ya corregido**: `DELETE …/padron/grupos/<id>/estudiantes/` y `POST …/estudiantes/<id>/` daban `TypeError` sin atrapar (500) porque `PadronMatriculaView` atiende dos rutas con firmas distintas; ahora 405 (`Bugfix:` e3784980, 4 pruebas nuevas) |
| **Recorrido por UI Automation de la pantalla Licencia de OPS** (nodo aislado en un puerto propio, memoria USB simulada con una unidad virtual, **sin teclado**, con la regla de tercios en cada captura; OPS compilado por la otra sesión a las 12:29) | **58 de 58 comprobaciones cumplidas**: evaluación con su aviso desde el primer día · activar en los tres pasos con una licencia firmada a partir de la solicitud que OPS guardó (una sola confirmación) · el botón final dice «Instalar la licencia» sin licencia y «Renovar la licencia» con una licencia **activa** y la administración, y «Instalar la licencia» en gracia o en pausa · copia de custodia (los tres archivos, la hoja sin documentos ni nombres) · renovar (serie 2) · «Vencida · en gracia» sin módulos en pausa · «Funciones en pausa» con los cuatro módulos «En pausa» y el aviso en el menú principal · **el soporte técnico ve la licencia y NO renueva** («Renovar es de la administración», y no cambia nada) · la administración renueva y los módulos se encienden · liberar (el `.avrel` queda en la memoria y el equipo vuelve a «En evaluación») y volver a activar el mismo archivo · **el profesor no ve botón ni aviso de licencia** · con la licencia en pausa, **Reportes** y **Buscar** lo dicen en pantalla con el texto común y **Evaluaciones, Calificaciones y Clase de hoy** (núcleo) abren sin ningún aviso |
| Student con el cupo de equipos agotado, contenido del instalador reconstruido | **Pendiente** (§4) |

## 2 · Defectos encontrados

| # | Qué | Estado |
|---|---|---|
| **BUG-1** | `Instalar` aceptaba una licencia con `desde` a menos de un día pero `estado.calcular` no aplicaba esa tolerancia: con la evaluación vencida el colegio quedaba **degradado** justo después de activar | **Corregido** por el nodo (D-8: una sola tolerancia) |
| **BUG-2** | Un secreto propio del nodo ilegible devolvía un valor en memoria y no guardaba nada: una identidad distinta en cada arranque (F-08, sin salida) | **Corregido** (D-9: se aparta, se guarda uno nuevo, se asienta una vez) |
| **DECISIÓN-A** | El técnico recibía 403 al trasladar la licencia al equipo que restauró la base del viejo | **Adoptada** (D-10: otra huella = traslado, `license.activate`) |
| **MENOR** | `HEAD` se saltaba el 402 | **Corregido** (D-11) |
| **H-13** | **Atrasar la fecha del equipo alarga la licencia** lo que se atrasó: el instante confiable es `max(reloj, marca alta)` y, con el reloj por debajo de la marca, ese máximo es un valor fijo: el tiempo de la licencia se congela hasta que la hora de pared alcanza la marca. Con 30 días de vigencia y 30 de gracia, atrasar la fecha 100 días degrada a los **151 días reales** en vez de a los ~51; con 300 días, a los 70 días reales sigue «activa» con `ahora_confiable` clavado en el día 10. Una pila de BIOS agotada (el reloj vuelve a 2010 en cada arranque) la vuelve inmortal y la evaluación no termina nunca. Contradice P-06 | **Corregido** en `f0d44008` (piso monótono, LIC-B-25): aceptado por la otra sesión y aplicado por esta; 9 pruebas nuevas |
| **H-14** | El tope de **72 h** del aplazamiento por un salto sospechoso hacia adelante se mide en esa misma línea congelada: **adelantar la fecha y devolverla** aplaza la degradación lo que duró el salto (+365 días → degrada a los **368** días reales en vez de a los 3) y un nodo ya `degradada` recupera sus cuatro módulos (pasa a `en_gracia`). Cuesta dos cambios de fecha | **Corregido** en `f0d44008` (el mismo piso) |
| **H-15** | El nodo acepta una licencia **firmada** con un límite en **0** (equipos, usuarios, concurrentes normales o en pico). Un 0 no limita: **detiene**. Con concurrencia 0 el aula responde `409 aula_llena` («alcanzó su capacidad (0 dispositivos)») al **primer** alumno; con equipos o usuarios en 0 no se registra ninguna tableta ni persona nueva. El emisor oficial no emite ceros (lo valida y lo prueba), pero ningún archivo, venga de donde venga, puede detener una clase (R-01) | **Corregido** en `64d0c9b5`: `desde_campos` rechaza un límite < 1; 3 pruebas nuevas y la del formato usa el mínimo 1 en lugar de 0 |

**Estado del arreglo de H-13, H-14 y H-15:** aplicado en el repositorio en dos commits `Bugfix:` (`f0d44008` el reloj, `64d0c9b5` los límites) con el visto bueno del dueño del código. Sobre el repositorio con los dos commits: **las 250 pruebas del módulo más las 12 nuevas (262) en verde, las 100 del emisor en verde**. Falta la suite completa del backend, que corre la otra sesión **una sola vez** (dos corridas completas a la vez tardan el doble), y volver a pasar el recorrido de interfaz contra la compilación final de OPS.

**Cómo repetir H-13 y H-14** (hoy son `backend/licenciamiento/tests/test_reloj_robustez.py`; antes del arreglo fallaban). El esquema:

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

## 3b · Observaciones de interfaz (del recorrido; no son fallas de licencia)

Se juzgaron con las capturas y la cuadrícula de tercios. La pantalla **Licencia** cumple la composición: tres tarjetas entre 1/6 y 5/6 del alto, cada una en su tercio, y las hojas en el tercio central.

| # | Qué se vio | Estado |
|---|---|---|
| U-1 | En la primera compilación que se probó (12:07) la **hoja** era translúcida y dejaba ver el texto de la tarjeta de estado de abajo | **Corregido** por la otra sesión (blanco opaco): comprobado en la compilación de las 12:29 |
| U-2 | El **aviso de licencia del menú principal tapa la parte alta de la tesela «Reportes»** (el panal empieza a 90 px del borde y la franja ocupa de 96 a 157 px, con un ancho que cruza los dos tercios). Como el aviso de evaluación existe desde el primer día, se verá durante 30 días | Reportado a la otra sesión |
| U-3 | **Buscar** con el módulo en pausa muestra el recuadro genérico «No se pudo cargar todo · No se pudo buscar. …» con el texto común; **Reportes**, en cambio, tiene su tarjeta propia «No disponible con la licencia de este equipo» con «Ver la licencia». Una licencia en pausa no es un fallo de carga | Reportado |
| U-4 | Con «Funciones en pausa» la tarjeta de la izquierda deja de caber y su última nota queda fuera de la vista (es un `ScrollView`, se desplaza con el dedo) | Menor |

## 4 · Pendiente (se completa en este documento)

1. Student con el cupo de equipos agotado: la tableta nueva debe ver «Esta tableta todavía no puede entrar al aula. Pídele ayuda a tu profesor» y las ya registradas no deben notar nada.
2. Una segunda corrida completa del backend, **una sola vez**, cuando estén dentro los arreglos de §2 (H-13, H-14, H-15), y las 100 pruebas del emisor contra el dominio ya corregido.
3. El contenido del instalador reconstruido: sin emisor, sin llave de desarrollo, sin llaves privadas, con la pública de producción cuando exista (hoy `produccion.json` está vacío); y reconstruir el paquete portátil del emisor con el dominio final.
4. Repetir el recorrido de la pantalla Licencia contra la compilación final de OPS (con los arreglos de interfaz de U-2 y U-3).

## 5 · Lo que esta verificación no puede comprobar

El TPM y el SMBIOS del panel real, una instalación real con administrador, DPAPI desde la cuenta SYSTEM, el ancla del registro de Windows con permisos reales, una tableta Android 14 física, un antivirus, la firma de código y la ceremonia real de llaves. Todo lo que se verificó usa relojes y hardware falsos sobre un nodo real, y llaves creadas por las propias pruebas.
