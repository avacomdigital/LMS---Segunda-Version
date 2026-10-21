# 16 · Node Platform (MOD-015) · Operación: qué significa cada estado y qué hacer

Una página para el técnico y la administración. Todo esto se ve en **Bitácora › Estado del equipo** (pestaña del técnico; la administración la abre desde la bitácora) y, si algo no está bien, en el banner del menú principal, que nunca aparece con una clase abierta.

## El estado del nodo

| Chip | Qué significa | Qué hacer |
|---|---|---|
| **Operativo** | El nodo atiende con normalidad. | Nada. |
| **Restringido** | Alguna condición del equipo no está bien (abajo). **La clase, las evaluaciones y el estudio siguen**; lo que puede esperar (altas, importaciones, exportaciones, reprocesos) esperará cuando la Fase 5 lo aplique. | Leer el motivo y resolverlo. El chip vuelve a «Operativo» solo cuando la condición se despeja con holgura. |
| **Recuperándose** | El nodo se está poniendo al día tras un corte (Fase 5). | Esperar; la clase puede seguir. |
| **Arrancando** / **Detenido** | El nodo está levantando o cerrando sus servicios. | Esperar unos segundos y tocar [Reintentar]. |

| Motivo | Qué pasa | Qué hacer |
|---|---|---|
| La base no está en modo de escritor único | El orden de los eventos no está garantizado. | Avisar a soporte técnico (es un cambio de configuración del nodo). |
| Queda poco espacio en el disco | Menos de 2 GB o del 5 % libres. | Liberar espacio (medios en caché, exportaciones viejas) o avisar a soporte. |
| La comprobación de la base no pasó | `quick_check` encontró un problema. | No usar el equipo para exámenes hasta que soporte lo revise y restaure si hace falta. |
| El diario de la base creció demasiado | Más de 512 MB sin volcar. | Reiniciar el nodo cuando no haya clase. |
| Un consumidor principal quedó suspendido | Tiene más de 10 000 eventos sin aplicar. | Revisar la cola, reprocesar lo apartado y, si no se mueve, reproducirlo desde cero. |
| La fecha del equipo retrocedió | Más de un día por debajo de lo que el aula ya vio. | Corregir la fecha del equipo o confirmarla desde Licencia. |

## La cola de salida por consumidor

Cada módulo que lee la cola (hoy ninguno: se irán conectando por fases) aparece con su estado:

| Estado | Qué significa | Qué hacer |
|---|---|---|
| Al día | Aplicó todo lo publicado. | Nada. |
| Rezagado | Tiene eventos pendientes; lo que muestra puede ir unos minutos por detrás. | Normal durante una clase. Si crece sin parar, mirar si hay eventos apartados. |
| Reconstruyéndose | Volvió a empezar desde cero (tras [Reproducir] o una restauración). | Esperar. |
| Suspendido | Superó su límite de rezago. | Reprocesar lo apartado; si sigue, [Reproducir] y avisar a soporte. |

Cuando un consumidor no puede aplicar un evento, lo reintenta solo (1 s, 2 s, 4 s… hasta 1 minuto) y tras cinco fallos lo **aparta** para no frenar a los demás. Nada se pierde: el evento sigue en la cola y queda en la lista de abajo.

## Eventos apartados

Cada línea dice **qué evento** (su número y su tipo), **para qué consumidor** y **el último error** (sin datos de ningún alumno). Nunca se ve el contenido del evento.

- **[Reprocesar]**: vuelve a aplicar ese evento una sola vez, cuando la causa del fallo ya está corregida. Lo puede hacer la administración; el técnico necesita una **escalada temporal** que le concede la administración (Bitácora › Escalada temporal, permiso `node.queue.replay`). Queda asentado en la bitácora.
- Si vuelve a fallar, sigue apartado con un intento más: revisar el error y avisar a soporte si se repite.
- **[Reproducir]** (por consumidor): su marca vuelve a cero y vuelve a leer toda la cola. Es seguro (aplicar dos veces el mismo evento no cambia nada) pero puede tardar; mientras tanto ese módulo muestra datos viejos. La clase no se detiene.
- **[Reintentar]**: vuelve a leer el estado.

## Último arranque y punto de recuperación

- «El anterior no se cerró limpio (apagado sucio)»: el nodo no se apagó de forma ordenada (corte de luz, cierre forzado). Sólo informa; el siguiente arranque reproduce lo que haga falta.
- «Restauración detectada»: alguien devolvió una copia vieja de la base. El nodo **saltó la numeración** para no repetir ningún evento ya emitido; lo que la copia no traía hay que recuperarlo del respaldo.
- «Último punto de recuperación: no disponible»: el módulo de respaldo (MOD-016) aún no existe. Hasta entonces la cola **no se purga** y crece (≈ 0,6 GB al año estimados).

## Lo que nunca pasa

- Ningún aviso de plataforma interrumpe una clase: el banner no se muestra con una clase abierta en este equipo.
- El técnico nunca ve el contenido de un evento ni datos de un alumno: ni en la pantalla, ni en los errores, ni en la bitácora.
- Nada de esta pantalla exige teclado.
