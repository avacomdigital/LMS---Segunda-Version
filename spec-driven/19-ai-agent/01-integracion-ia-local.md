# 19 · AI Agent · etapa 2: conversación con AVACOM Local AI (Qwen + voz)

| Campo | Valor |
|---|---|
| Estado | **Construido y probado el 2026-10-29, sin Qwen** (este equipo no puede correr Ollama). Todo lo demás se probó contra la API de IA **real** con su voz Piper **real** (ver §7). Sin commit. |
| Contrato de origen | `avacom-local-ai/docs/contrato-api-ai-lms.md` (API 0.1.0). Topología **A**: el backend del LMS corre en la misma OPS Master que la IA (`http://127.0.0.1:12000`). |
| Regla estructural | **La app no habla con la IA.** OPS habla sólo con el nodo (`/api/agente-ia/`); el nodo es el único cliente de AVACOM Local AI (`agente_ia/infraestructura/cliente.py`). |
| Piezas | Backend `backend/agente_ia/` · Core `src/Avacom.Lms.Core/AgenteIa/` · OPS `Pages/AiAgentPage.Chat.cs` + `AgenteIa/ReproductorWindows.cs` · sonda `backend/tools/probar_agente_ia.py` |
| Rutas | `POST /api/agente-ia/preguntar/` · `POST /api/agente-ia/hablar/` · `GET /api/agente-ia/estado/` |
| Pruebas | Backend 89 (agente) y 2889 en total, en verde · Core 2328 · OPS 533 · ensayo de punta a punta (§7) |
| Antecedente | [README.md](README.md): etapa 1, el personaje 3D (sólo visual). |

## 0 · Lo que se promete

1. **Nada de lo que pase con la IA rompe la aplicación.** Servicio apagado, Ollama caído, modelo sin instalar, tiempo agotado, respuesta absurda, audio dañado, reproductor roto, un defecto nuestro, la bitácora caída: cada caso termina en un texto para la persona y un código, nunca en una excepción que llegue a la pantalla ni en un 500 sin explicación.
2. **Cada fallo deja constancia en la bitácora y en un archivo de logs** (§4), sin el texto de la pregunta ni el de la respuesta.
3. **El texto no depende de la voz**: son dos peticiones. Si el modelo respondió y la voz falla, la respuesta escrita ya está en pantalla.

Lo que **no** se promete: calidad de las respuestas de Qwen, que la voz guste (nadie la ha escuchado con criterio), tiempos de Qwen en una OPS real (§7.2).

## 1 · Arquitectura

```
OPS (MAUI)  ──HTTP :8000──►  Nodo (Django/Daphne)  ──loopback :12000──►  AVACOM Local AI  ──►  Ollama + Qwen3
 AiAgentPage                  agente_ia                                    (FastAPI)           └► Piper (voz)
 ConversacionConAgente        ├─ preguntar  → /llm/query
 AgenteIaApi                  ├─ hablar     → /audio/gen-voice  (por trozos de ≤450, uno solo de salida)
 ReproductorWindows           └─ estado     → /health/dependencies
```

- **Pasos del contrato → piezas.** 1–2 (pregunta y texto): `preguntar/`. 3–4 (voz): `hablar/` trocea el texto por frases (`dominio/troceo.py`), sintetiza trozo a trozo, une los WAV (`dominio/wav.py`) y devuelve **un** WAV. 5 (reproducir): `ReproductorWindows` (WinRT `MediaPlayer`, en memoria, con corte inmediato).
- **Capas del backend** (como el resto del repo): `dominio/` (errores, troceo, WAV, id de conversación; sin framework) · `aplicacion/agente.py` (casos de uso; no conoce Django) · `infraestructura/` (cliente HTTP, configuración, registro en bitácora y log, contenedor) · `interfaces/` (vistas DRF).
- **Sin tablas ni migraciones.** La memoria de la conversación vive en el servicio de IA (30 min de inactividad, 6 intercambios; se pierde si se reinicia `AVACOMLocalAI`).

## 2 · API del nodo

Todas exigen sesión (con `AVACOM_LMS_EXIGIR_SESION=1`, como instala el instalador) y **personal**: una sesión de alumno recibe 403 `sin_permiso`.

| Ruta | Cuerpo | Respuesta 200 |
|---|---|---|
| `POST preguntar/` | `{pregunta, conversacion?}` (≤ 2000 car.) | `{conversacion, texto, modelo, contexto_usado, ms}` |
| `POST hablar/` | `{texto, velocidad?}` (≤ 3000 car.; velocidad 0,5–2,0) | `audio/wav` (mono, 16 bits, 22 050 Hz) + `X-Audio-Duration-Ms`, `X-Audio-Chunks` |
| `GET estado/` | — | `{habilitada, servicio_activo, disponible, voz_disponible, codigo, motivo, motivo_voz, sugerencia?, modelo}`. **Siempre 200**: «no disponible» es una respuesta. |

- `conversacion` es un id **opaco** de la pantalla; el nodo arma `lms-<huella de quien pregunta>-<id>` (patrón `^[A-Za-z0-9_.:-]{1,64}$`): ningún dato personal llega a la IA y una persona no puede continuar la conversación de otra aunque adivine el id. Sin id no hay memoria.
- `hablar/` ignora el `Accept` (la negociación estándar de DRF contestaría 406 a `Accept: audio/wav`).
- La voz de un texto largo (959 car. medidos en el contrato) se parte en trozos de ≤ 450; un trozo sin letras ni números se descarta; `tts_busy` se reintenta 3 veces (0,5/1/1,5 s); una síntesis a la vez por equipo (candado) y **tope total de 120 s** por texto.

## 3 · Errores

Formato de degradación del nodo: `{detail, codigo, reintentable, sugerencia?}`. `detail` está en español para la persona; lo técnico (puerto, excepción) **nunca** viaja a la pantalla: va a la bitácora y al log.

| Código | HTTP | ¿Reintentar? | Cuándo |
|---|---|---|---|
| `ai_unreachable` | 503 | sí | Nadie escucha en el puerto de la IA (se comprueba el socket **antes** de esperar: ≈2 s en Windows, no 160 s) |
| `ai_timeout` | 504 | sí | El nodo se cansó de esperar (160 s modelo · 75 s por trozo de voz) |
| `llm_unavailable` · `llm_timeout` · `llm_error` | 503 · 504 · 502 | sí | Ollama apagado · Qwen no respondió en 120 s · respuesta inválida |
| `llm_model_missing` · `context_unavailable` | 503 | **no** | Modelo sin instalar · `avacom-context.txt` roto: reintentar no cambia nada |
| `busy` · `tts_busy` | 429 | sí | Otra consulta ocupa el modelo / la voz |
| `tts_unavailable` · `tts_timeout` | 503 · 504 | sí | La voz no carga / tardó |
| `ai_invalid_response` | 502 | sí | La IA contestó algo que no es JSON/WAV (se valida: un «audio» que no es WAV no llega a la app) |
| `ai_disabled` | 503 | no | `AVACOM_IA_HABILITADA=0` |
| `question_required/too_long` · `text_required/too_long` · `empty_text` | 400 · 422 | no | Petición inválida (no se audita: no es un fallo de la IA) |
| `ai_internal` | 502 | sí | Un defecto nuestro: se registra con traza, la app recibe un código |

**En OPS** (`ConversacionConAgente` + `AiAgentPage.Chat.cs`): el aviso aparece en una franja del chat con «Reintentar» (si sirve) o «Escuchar de nuevo»; el personaje pasa a «error» 3 s y vuelve solo al reposo; el texto ya mostrado se conserva. Sin nodo: «No hay conexión con el aula».

## 4 · Auditoría y logs

**Bitácora** (`m19_bitacora`, módulo `agente_ia`, acciones en `audit/dominio/catalogos.py`): `agente_ia.consulta_realizada` (ok), `agente_ia.consulta_fallida` y `agente_ia.voz_fallida` (resultado `fallido`, con `codigo`, `estado_http`, `estado_servicio`, `reintentable`, `ms`, `detalle_tecnico`). El actor es el usuario real de la sesión; el objeto, una huella corta de la conversación. **Nunca** el texto. Un fallo al asentar no rompe la respuesta (se registra `agente_ia.bitacora_no_disponible`).

**Logs del nodo** (`backend-app.log`, y `backend-errores.log` desde WARNING; JSON Lines, logger `avacom.agente_ia`): estados normales de la IA (apagada, ocupada, tiempo) = WARNING, `ruta: sad`, canal `comunicacion`; defectos (respuesta inválida, voz sin instalar, error interno) = ERROR, `ruta: bad`. Cada línea lleva `corr` (el mismo de la petición y del asiento).

**Logs de OPS** (`ops-app.log`/`ops-errores.log`, eventos `aiagent.*`: `consulta_fallida`, `voz_fallida`, `reproduccion_fallida`, `no_disponible`, `defecto`…): sólo longitudes, tiempos y códigos. Los WARNING+ los entrega `EntregadorDeLogs` al nodo (`backend-clientes.log`); se comprobó en vivo.

Con el **nodo apagado** no hay a quién asentar: queda sólo el log local de OPS (el WARNING `red.sin_conexion` + `aiagent.*`).

## 5 · Configuración (`backend.env`, todo opcional)

| Variable | Defecto | Para qué |
|---|---|---|
| `AVACOM_IA_HABILITADA` | `1` | `0` apaga el asistente (la pantalla lo dice) |
| `AVACOM_IA_URL` | — | Fija la dirección. Si falta, se lee `AVACOM_HOST/PORT` de `%ProgramData%\AVACOM\LocalAI\config\.env` **en cada petición** (si el técnico cambia el puerto no hace falta reiniciar) y, si tampoco, `http://127.0.0.1:12000` |
| `AVACOM_IA_TIEMPO_LLM_S` · `_VOZ_S` · `_VOZ_TOTAL_S` · `_SALUD_S` | 160 · 75 · 120 · 5 | Topes (contrato: ≥ 160 s backend, ≥ 170 s app; OPS espera 185 s) |
| `AVACOM_IA_TROZO_MAX` · `_PREGUNTA_MAX` · `_VOZ_TEXTO_MAX` · `_MAX_TOKENS` · `_VOZ_TURNO_S` | 450 · 2000 · 3000 · 256 · 45 | Límites |

Sin proxy: el cliente ignora el proxy del sistema (la IA está en el bucle local). La ruta no es «licenciable» (`licenciamiento/dominio/rutas.py`): ninguna licencia vencida la apaga.

## 6 · La pantalla (OPS)

- **Chat** a la derecha (tercio derecho: el personaje queda en el central): burbujas, sugerencias tocables (sin teclado: el equipo puede no tenerlo), campo con el teclado táctil del sistema, «Enviar/Detener», «Escuchar» en cada respuesta, «Nueva» (otra conversación), interruptor de voz (se recuerda). Funciona aunque el visor 3D no arranque.
- **Personaje**: pensando → `thinking` · hablando → `talking` (simulado: la voz no trae visemas) · error → `tender` · reposo → idle. El subtítulo bajo el personaje muestra el principio de la respuesta (≤ 4 renglones).
- Las órdenes al visor esperan en cola hasta su `ready` (un mensaje a un `HybridWebView` que aún no carga se pierde).
- Ganchos del **perfil de pruebas** (`Ajustes`, sin efecto en uso normal): `AVACOM_OPS_AI_PREGUNTA` (envía una pregunta sola) y `AVACOM_OPS_AI_VOLUMEN` (0 = recorre el audio sin hacer ruido).

## 7 · Verificación

### 7.1 Lo que se probó (2026-10-29)

| Qué | Cómo | Resultado |
|---|---|---|
| Backend | 89 pruebas con un servicio de IA simulado por HTTP de verdad (sin servicio, tiempo agotado, respuestas basura, cuerpos cortados, bitácora y log caídos, concurrencia de voz, alumno/personal, sesión) | verde · suite completa 2889 en verde |
| Cliente C# | 26 pruebas contra **respuestas reales del nodo** capturadas (`Fixtures/agente_ia/`, `backend/agente_ia/tests/test_capturar_contrato.py`) + 25 del orquestador (nunca lanza, estados, cancelación, reproductor roto) | Core 2328 en verde |
| **Cadena real sin Qwen** | Backend (Daphne, sesión obligatoria) → **API real de IA con Piper real** → Ollama simulado con el protocolo real de `/api/chat`: memoria entre turnos, respuesta de 1490 car. (4 trozos → un WAV de 92,6 s en 10,8 s), Markdown/emojis, 3 voces a la vez, Ollama 500, modelo no instalado, Ollama **apagado**, IA **apagada**, recuperación sin reiniciar, `llm_timeout` real, espera real de **75 s** sin cortes | todo conforme |
| Audio | `MediaPlayer` con el WAV real de Piper a volumen 0; corte con `Detener`/cancelación; bytes que no son audio (→ `SourceNotSupported`, sin colgarse) | conforme |
| Pantalla real | OPS compilada, sesión real, capturas con `PrintWindow`: chat, texto largo, subtítulo, «Detener», IA apagada | conforme |
| Registro | Bitácora, `backend-errores.log`, `ops-app.log` y su entrega a `backend-clientes.log` | conforme |

### 7.2 Lo que NO se pudo probar

- **Qwen real**: calidad, español latino, ausencia de Markdown, uso del contexto, memoria semántica, latencia y tokens/s. Ninguna respuesta del ensayo la generó un modelo.
- **Tiempos en una OPS real** (CPU lenta): el modelo y la síntesis. Los topes están puestos con el peor caso del contrato.
- **Escuchar la voz** y la pronunciación (se probó el audio volumen 0 y se guardó un WAV; nadie lo evaluó).
- **Teclado táctil** al escribir en el campo (sólo se probó con la pregunta de prueba y las sugerencias).
- **Instalación real**: servicios Windows, reinicio de la OPS, el autodescubrimiento del puerto en `%ProgramData%` (probado con archivos temporales, no en el equipo), antivirus.
- **Android/Student**: el agente es sólo de OPS.

### 7.3 Defectos que el ensayo de punta a punta encontró (y están arreglados)

1. **Los alumnos pasaban**: `Menu` es `str`+`Enum` y `str(Menu.STUDENT)` es `"Menu.STUDENT"`; la comprobación copiada de la cola de medios nunca bloqueaba. Mis primeras pruebas lo escondían (simulaban `menu="student"`); ahora usan un `Principal` real.
2. **Las órdenes al visor antes de su `ready` se perdían** (el subtítulo no aparecía): cola de espera.
3. **El `HttpClient` de OPS se rinde a los 15 s**: ninguna pregunta habría llegado a responder → `Sesion.AgenteIa` tiene el suyo (210 s) y la espera la corta `AgenteIaApi` con su mensaje.
4. **El campo de texto** mostraba el borde nativo de Windows → `NeumoChrome`.
5. (Arnés) `PostAsJsonAsync` manda el cuerpo troceado y Daphne no lo lee: `ClienteJson` ya usa `StringContent`; no usar `PostAsJsonAsync` con el nodo.

> **Hallazgo ajeno, sin tocar:** `backend/cola_medios/interfaces/views.py` (`VistaCola._personal`) usa la misma comparación `str(menu) != "student"` y, por la misma razón, **deja pasar a un alumno** a cancelar, reintentar o vaciar la cola de medios. Su prueba usa `SimpleNamespace(menu="student")` y no lo ve. Se deja para que lo decida su dueño.

## 8 · Verificación en el equipo real (checklist)

Con el instalador ya puesto y Qwen instalado, **en la OPS** (PowerShell):

```powershell
Get-Service AVACOMLocalAI, AVACOMOllama          # ambos Running, inicio Automatic
backend\.venv\Scripts\python backend\tools\probar_agente_ia.py --documento <profesor> --clave <clave> --preguntas --guardar C:\Temp\voz.wav
```

La sonda dice, eslabón por eslabón (IA directa → nodo → pregunta → voz), qué falla y qué mirar; con `--preguntas` imprime 5 respuestas para **leerlas** y comprueba la memoria. Después, a mano:

1. **Leer** las respuestas: español latino, breves (< 400 car.), sin Markdown, usan el contexto de AVACOM (preguntar algo que sólo esté en `avacom-context.txt`), no inventan (un curso inexistente).
2. **Escuchar** `C:\Temp\voz.wav`: claridad, pronunciación, tono; probar siglas («AVACOM», «LMS») y cifras.
3. **Medir** y anotar: primera respuesta (carga el modelo), siguientes, factor de tiempo real de la voz (`X-Audio-Duration-Ms` frente a lo que tarda) y segundos hasta oír el primer sonido. Si Qwen tarda más de ≈100 s, bajar a `qwen3:4b`/`qwen3:1.7b`.
4. **Abrir AI Agent en OPS**: «Asistente listo» en verde; tocar una sugerencia; ver al personaje pensar y hablar; escribir con el teclado táctil; «Detener» a media voz; «Nueva».
5. **Apagar** `AVACOMOllama`, luego `AVACOMLocalAI`: la pantalla debe decirlo, dejar «Reintentar» y seguir usable. Volver a encender: se recupera sin reiniciar nada.
6. **Reiniciar Windows** sin iniciar sesión y repetir la sonda.
7. **Mirar los registros** (carpeta de logs del nodo, `%ProgramData%\AVACOM\OPS Master\Logs\`): `backend-errores.log` (eventos `agente_ia.*`), y la bitácora (asientos del módulo `agente_ia`).

## 9 · Decisiones (a confirmar con el CTO)

| # | Decisión | Por qué |
|---|---|---|
| D-1 | Sólo **personal** (no alumnos) usa el asistente | AI Agent está en el menú de OPS; las tabletas no alcanzan `127.0.0.1` del nodo (contrato §2, topología A) |
| D-2 | Se asienta **cada consulta** (sólo cifras) y cada fallo | «Quién usó la IA y cuándo» sin guardar contenido; si el volumen molesta, dejar sólo los fallos |
| D-3 | `estado/` responde 200 con `disponible:false` | Es la pregunta «¿está?», no un error; los demás 503 sí son errores del trabajo pedido |
| D-4 | Una sola ruta `hablar/` que une los trozos (no un `hablar` por trozo) | Menos viajes; riesgo: la espera al primer sonido es la suma de todos los trozos (las respuestas de 256 tokens suelen caber en 1–2). Alternativa documentada: `/audio/gen-voice/stream` |
| D-5 | La IA **no** es una capacidad licenciable | Evita que una licencia vencida apague una función de apoyo sin que nadie lo haya decidido (Q-L12 sigue abierta para lo demás) |
| D-6 | El texto del chat no se persiste | Privacidad; al salir de la pantalla la conversación se pierde (y la memoria del servicio caduca a los 30 min) |
