# 17 · Update Manager (MOD-017) · Operación en el aula

| Campo | Valor |
|---|---|
| Para quién | La administración del colegio y el técnico de AVACOM. Sin teclado: todo se hace tocando la pantalla de OPS (**Actualizaciones**, sólo administración y técnico). |
| Qué es | Cómo se actualiza un módulo del nodo con un paquete `.avupd`, qué pasa solo si algo sale mal y qué hace una persona cuando no se pudo resolver solo. |
| Referencias | Diseño [01-diseno.md](01-diseno.md) · contrato con el Host [02-api.md](02-api.md) §3 · instalador `installer/README.md` («Paquetes de módulo»). |

> **Principio.** Nunca se detiene una clase. Si hay una clase abierta, la actualización espera. Y si algo falla, el aula vuelve sola a la versión anterior con sus datos.

## 1 · Actualizar (el camino normal)

1. **Fuera de clase**, la persona de administración (o el técnico) conecta la memoria USB con el paquete. OPS → **Actualizaciones**.
2. Aparece el paquete en «Paquetes encontrados». Se toca **Importar**: el nodo comprueba la firma y que todo encaje con los módulos instalados. Si no, la pantalla dice por qué (firma, versión, espacio) y **no se guarda nada**.
3. Se ve el detalle: qué módulos cambian, cuánto pesa, el espacio libre y si es compatible.
4. **Aplicar ahora** (una confirmación) o **Programar** una ventana (el nodo la abre solo si no hay clase y aplaza si aparece una).
5. Al aceptarse la orden, **iniciar una clase nueva responde «El aula se está actualizando; vuelve a intentarlo en unos minutos»**. Unirse, responder, exámenes y estudio siguen igual. Tarda 3 a 5 minutos como máximo (3 si cambia `evaluacion`).
6. La pantalla avisa sola cuando termina: **aplicado** (queda revertible 14 días) o **revertido**.

## 2 · Lo que el sistema hace solo

| Situación | Resultado |
|---|---|
| Hay una clase abierta al aplicar | 409 `sesion_activa` en OPS. Con la ventana programada, el nodo espera. El Host, si la ve al empezar, **aplaza** sin parar nada. |
| Falla copiar, migrar o verificar | **Reversión automática**: vuelven el código (desde la instantánea) y, si la migración empezó, la base y `backend.env` (desde la copia). Se arranca el backend anterior y se comprueba. Resultado `revertido`. Medido: 15 a 43 s en los ensayos. |
| El Host se apaga o la máquina se corta a mitad | Al volver el servicio, **antes** de levantar el backend, retoma (si aún no se cambió nada) o deshace (si el código o la base quedaron a medias). |
| Paquete alterado, sin firma, o con rutas fuera del módulo | Se rechaza **sin escribir nada** y queda anotado en el historial. |
| Ni la reversión automática funciona | `reversion_fallida`: **no se borra nada**, el aula conserva la copia de la base y se avisa en pantalla. Ver §4. |

## 3 · Revertir a mano (14 días)

Dentro de los 14 días posteriores a un `aplicado`, la administración toca **Revertir**, elige el motivo de una lista (queda como la nota que exige el nodo) y confirma una vez. El Host migra hacia atrás con el reverso de cada migración y devuelve el código desde la instantánea. Con una clase abierta se bloquea igual que aplicar. Pasados los 14 días la instantánea se retira sola y el paquete queda `archivado`: ya no se puede revertir por aquí.

**El técnico** puede importar y leer, pero **aplicar, revertir y programar requieren la administración** (o una escalada temporal ESC-01 que esta pantalla todavía no concede: ver Q-U12 en [01-diseno.md](01-diseno.md)).

## 4 · Cuando la reversión también falló (`reversion_fallida`)

Esto no debería ocurrir, y es el hueco que el Maestro marca («falta el procedimiento de reversión sin técnico en sitio», Q-U4). Lo que hace falta y lo que no:

1. **No apagar ni desinstalar nada.** La copia de la base está en `%ProgramData%\AVACOM\OPS Master\Respaldos\<versión>-<fecha>\` y la instantánea del código en `Actualizaciones\versiones\<paquete>\anterior\`. Nadie las borra mientras el estado sea `reversion_fallida`.
2. Si el aula **abre y funciona** (el backend responde), seguir con las clases; llamar a AVACOM con el id del paquete que muestra la pantalla.
3. Si **no abre**, hace falta un técnico en sitio: abre una consola con administrador y corre `Avacom.Ops.Host.exe aplicar-actualizacion` con el servicio parado (reintenta lo que el checkpoint dejó a medias), o reinstala la versión anterior con el instalador completo (la política de datos es **protegidos**: conserva la base y toma copia previa).
4. **Qué no se puede hacer sin técnico:** no existe todavía una reversión sin nadie en sitio cuando la propia reversión automática falla. Está declarado como pregunta abierta al CTO (Q-U4).

Códigos de salida de `aplicar-actualizacion`: 0 aplicado o revertido · 30 aplazada · 31 rechazada · 32 reversión fallida.

## 5 · Dónde mirar

| Qué | Dónde |
|---|---|
| Estado, paquetes, historial | OPS → Actualizaciones |
| Qué hizo el Host paso a paso | `%ProgramData%\AVACOM\OPS Master\Logs\` (el registro del servicio) y `Actualizaciones\resultado.json` / `resultados\<orden>.json` |
| Hasta dónde llegó un corte | `Actualizaciones\checkpoint.json` |
| Hechos de auditoría | Bitácora → módulo `actualizacion` (cadena de huellas) |
| El estado desde fuera | `GET /health/` → campo `actualizacion` |

## 6 · Lo que no se debe hacer

- No editar archivos de `Program Files\AVACOM\OPS Master\Backend` a mano: se detecta (la huella del paquete no coincide) y el Host no garantiza volver atrás.
- No copiar un paquete de otra versión del producto sobre una instalación nueva: el Host **no vuelve** a código de otra versión que la de la instantánea.
- No borrar `Actualizaciones\` a mano: allí viven la orden, el resultado y las instantáneas de 14 días.
