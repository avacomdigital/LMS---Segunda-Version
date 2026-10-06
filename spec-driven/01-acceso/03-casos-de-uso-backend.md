# 03 · Módulo de acceso · Casos de uso del backend

| Campo | Valor |
|---|---|
| Para qué sirve | Entender el código ya escrito en `backend/acceso/`: qué hace cada operación, por dónde viaja la información y qué pantalla del frontend la va a usar |
| Para quién | Programadores que van a tocar el módulo **y** personas no técnicas que necesitan saber qué hace el sistema |
| Alcance | 39 casos de uso · 32 rutas HTTP · 24 serializers · 18 tablas · 4 migraciones · 2 comandos de consola |
| Alineación | MOD-001 · Identity & Access del Documento Maestro. El cruce función a función está en [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md) |
| Documentos hermanos | [01 · Modelado de datos](01-modelado-datos.md) · [02 · Endpoints](02-Endpoints.md) · [Pantallas MAUI](../../specs/presentaciones/acceso-sugerencias.html) |
| Estado del código | Implementado y probado: 118 pruebas en verde (86 de este módulo) |

> **Cómo leer este documento.** Las secciones 1 a 3 explican el mecanismo general con una sola analogía y un ejemplo completo. La sección 4 recorre los 39 casos de uso uno por uno. Si sólo va a leer una cosa, lea la sección 3: el viaje de una petición. Si no programa, puede saltarse los bloques de código; el texto se entiende sin ellos.

---

## 1 · La idea en una página

### 1.1 · Qué es un «caso de uso»

Un caso de uso es **una cosa completa que alguien quiere hacer**: «crear un estudiante», «entrar al sistema», «importar el padrón», «restablecer un PIN», «autorizar una tableta para el examen». No es un botón ni una pantalla ni una tabla: es la operación entera, con todas sus reglas y todas sus consecuencias.

En este módulo cada caso de uso es una clase de Python con un único método `ejecutar(...)`. **Para saber todo lo que pasa cuando el profesor restablece un PIN, sólo hay que leer una clase.** El Documento Maestro las llama *funciones* (FUN-001 a FUN-011); aquí cada función tiene su caso de uso, y en la cabecera de `casos_uso.py` está la correspondencia.

### 1.2 · La analogía de la oficina

| En la oficina de secretaría académica | En el código | Dónde vive |
|---|---|---|
| La **ventanilla** donde el público entrega formularios y recibe respuestas | La capa HTTP: vistas (APIViews) y serializers | `acceso/interfaces/` |
| El **formulario en papel**, que se revisa antes de aceptarlo: ¿está firmado? ¿tiene todos los campos? | Los serializers | `acceso/interfaces/serializers.py` |
| El **funcionario** que tramita la gestión completa de principio a fin | El caso de uso | `acceso/aplicacion/casos_uso.py` |
| El **reglamento** de la institución que el funcionario debe respetar | El dominio: políticas, entidades y valores | `acceso/dominio/` |
| El **archivo** donde se guardan y se buscan los expedientes | Los repositorios | `acceso/infraestructura/repositorios.py` |
| La **carpeta** de una gestión, que se entrega completa o no se entrega | La Unidad de Trabajo | `acceso/infraestructura/unidad_trabajo.py` |
| La **caja fuerte** y el sello: lo que cifra, lo que firma | Argon2id, AES-GCM, HMAC, JWT | `acceso/infraestructura/seguridad.py` |
| Los **muebles y estanterías** del archivo | Las tablas de la base de datos | `acceso/models.py` |
| El día que se **montó la oficina** y las **reformas** posteriores | Las migraciones | `acceso/migrations/` |
| La **puerta de servicio** para el personal técnico, sin pasar por ventanilla | Los comandos de consola | `acceso/management/commands/` |

La regla que sostiene todo el diseño: **el funcionario no sabe cómo es el archivo por dentro**. Pide «tráeme el expediente de Juan» y alguien se lo trae. Hoy el archivo es SQLite con Django; mañana puede ser PostgreSQL con SQLAlchemy y el funcionario trabaja igual.

### 1.3 · Las seis carpetas del módulo

```
backend/acceso/
├── dominio/              EL REGLAMENTO. No sabe que existe internet ni bases de datos.
│   ├── valores.py          Tipos con reglas propias: alcances, menús, niveles educativos, tipos de credencial, motivos de cierre
│   ├── entidades.py        Las cosas del negocio: Usuario, Persona, Identificador, Credencial, UsuarioRol, Sesión...
│   ├── politicas.py        Las tres decisiones difíciles: ¿puede? ¿es buena la clave? ¿está bloqueado?
│   ├── plantillas.py       Los cinco roles, los 28 permisos identity.* y las políticas de fábrica
│   └── errores.py          Los "no" posibles, cada uno con su motivo
│
├── aplicacion/           LOS FUNCIONARIOS.
│   ├── casos_uso.py        Las 39 operaciones. Este es el corazón del módulo
│   └── puertos.py          Lo que los funcionarios necesitan pedir (sin decir a quién)
│
├── infraestructura/      QUIEN HACE EL TRABAJO SUCIO.
│   ├── repositorios.py     Leer y escribir en la base, cifrando al pasar
│   ├── unidad_trabajo.py   La transacción: todo o nada
│   ├── seguridad.py        Argon2id, AES-256-GCM, HMAC-SHA-256, JWT
│   └── contenedor.py       El armador: junta cada pieza con la que le toca
│
├── interfaces/           LA VENTANILLA (Django REST Framework).
│   ├── views.py            Las APIViews: reciben HTTP, llaman al caso de uso, devuelven JSON
│   ├── serializers.py      Revisan la forma del formulario
│   ├── autenticacion.py    Lee el pase de entrada (JWT) en cada petición
│   ├── permisos.py         ¿Esta ruta exige sesión?
│   └── urls.py             El directorio: qué dirección lleva a qué ventanilla (32 rutas)
│
├── management/commands/  LA PUERTA DE SERVICIO.
│   ├── acceso_instalar.py  Instalar el equipo desde la consola
│   └── acceso_importar.py  Cargar el padrón desde un archivo (FUN-003)
│
├── migrations/           EL MONTAJE Y LAS REFORMAS.
│   ├── 0001_initial.py            Crea las tablas originales
│   ├── 0002_plantillas.py         Siembra permisos y roles de fábrica
│   ├── 0003_alineacion_mod001.py  Reforma: asignaciones de rol, niveles, avatar, inactividad, emisor...
│   └── 0004_datos_mod001.py       Renombra permisos a identity.*, siembra Reportes y Técnico, migra los datos
│
├── models.py             LAS ESTANTERÍAS: la forma de las 18 tablas m01_*
└── tests/                LAS PRUEBAS: 86 comprobaciones automáticas
```

### 1.4 · La regla de oro del diseño

**El reglamento no puede depender de la tecnología.** Ni `dominio/` ni `aplicacion/` mencionan Django, DRF, FastAPI, SQLAlchemy ni Pydantic. Hay una prueba automática que recorre esos archivos y **falla** si alguien escribe uno de esos nombres. Por qué importa: la regla «una persona tiene una sola sesión abierta» es de AVACOM, no de Django. Si el backend cambia de tecnología, esa regla y su prueba sobreviven intactas.

---

## 2 · Los cuatro conceptos que aparecen en todos los casos de uso

### 2.1 · `Principal`: quién está actuando, y con qué rol

Cuando alguien inicia sesión recibe un **pase de entrada** (un JWT). En cada petición posterior lo presenta, y el backend lo convierte en un objeto llamado `Principal`.

```python
Principal(
    usuario_id="a1b2…",        # quién es
    organizacion_id="c3d4…",   # de qué colegio
    rol_codigo="TEACHER",      # con qué rol ESTÁ TRABAJANDO en esta sesión (BR-021)
    menu="teacher",            # qué menú le toca en la app
    nivel=2,                   # 1 alumno · 2 personal · 3 administración
    sesion_id="e5f6…",         # cuál de sus sesiones es esta
    clase_sesion=NORMAL,       # NORMAL o TEMPORAL (pase de examen)
    debe_cambiar_credencial=False,
    dispositivo_id="…",        # desde qué tableta
    evaluacion_ref=None,       # si el pase es sólo para un examen
)
```

Un detalle nuevo tras la alineación: una persona puede tener **varios roles** (la profesora que además es coordinadora), pero en cada sesión trabaja con **uno solo**, el que eligió al entrar. El `Principal` lleva ese rol efectivo, no la lista.

### 2.2 · Permiso y alcance: «qué» y «sobre quién»

Un permiso solo no dice nada útil. `identity.password.reset` (restablecer la clave de alguien) significa cosas distintas según quién lo tenga:

| Alcance | Maestro | Significa | Ejemplo |
|---|---|---|---|
| `SELF` | propio | Sólo sobre sí mismo | Juan cambia **su** clave |
| `ASSIGNED_GROUPS` | grupo | Sobre los estudiantes de sus grupos | La profesora restablece el PIN de **su** curso |
| `LEVEL` | nivel | Sobre todos los grupos de un nivel educativo | La coordinadora de secundaria, sobre **toda secundaria** |
| `ORGANIZATION` | instalación | Sobre todo el colegio | El rector, sobre **cualquiera** |

La pregunta «¿es Juan mi estudiante?» **no se guarda en ninguna tabla de permisos**: se calcula. Existe un grupo donde yo soy docente vigente (o que me abre la asignación de mi rol) y Juan es miembro vigente, luego Juan es mi estudiante.

**La asignación acota al rol.** Si a alguien se le asigna el rol Administrador con alcance «nivel secundaria», sus permisos de organización valen sólo dentro de secundaria. Es la mitad de la regla BR-021 del Maestro que más trabajo ahorra: no hace falta crear un rol distinto por cada coordinación.

**Fuera de alcance se responde «acceso denegado» (403), nunca «no existe» (404).** Es una regla explícita del Maestro. El 404 queda para lo que de verdad no existe.

### 2.3 · La Unidad de Trabajo: todo o nada

Casi todos los casos de uso empiezan igual:

```python
with self.s.uow() as uow:
    ...
```

Esa línea abre una **carpeta de gestión**. Todo lo que se escriba dentro se guarda de golpe al final, o no se guarda nada si algo falla. Crear un estudiante son ocho escrituras (cuenta, datos cifrados, identificadores, asignación de rol, inscripción al grupo, credencial, auditoría y aviso de sincronización); si la sexta falla, no queda medio estudiante.

Hay **una excepción deliberada**: `AutenticarUsuario`, `CanjearAccesoTemporal` y `ResolverPrincipal` usan `ejecutar_registrando(...)`, que confirma la transacción **aunque la operación termine en error**. Si alguien falla la clave cinco veces, esos fallos tienen que quedar escritos, porque son lo que dispara el bloqueo. Y si una sesión se cierra por inactividad, ese cierre debe quedar registrado aunque la respuesta sea «vuelva a entrar».

### 2.4 · Sesión única: una persona, una sesión

La regla más restrictiva de MOD-001. Cuando alguien abre sesión, `abrir_sesion()` hace dos cosas antes de crear la nueva:

1. Cierra **cualquier otra sesión de esa persona** con motivo `otro_dispositivo`, y devuelve en la respuesta de dónde se cerró (`sesion_anterior`), para que la app muestre «Tenías tu sesión abierta en tableta-03. Se cerró allí y todo tu trabajo está a salvo».
2. Cierra la sesión **de otra persona en esa misma tableta** con motivo `dispositivo_compartido`, porque un dispositivo compartido tiene cero o una sesión (INV-011).

El dispositivo abandonado, en su siguiente petición, recibe `401 sesion_cerrada_otro_dispositivo` y la app vuelve al acceso con el aviso correspondiente.

---

## 3 · El viaje completo de una petición

Seguimos un caso real de principio a fin: **Juan, estudiante de octavo, entra a su tableta.**

### 3.1 · Lo que ocurre en la pantalla

Juan toca su tableta. Aparece un teclado numérico grande. Escribe su código, `122499`, y su PIN, `691302`. Toca el botón verde. Un segundo después ve su menú con sus asignaturas. Si hubiera dejado su sesión abierta en otra tableta, vería además un aviso de que allí se cerró.

### 3.2 · Lo que ocurre por dentro

```
   TABLETA (.NET MAUI)
        │  POST http://192.168.1.10:8000/api/acceso/sesiones/
        │  { "identificador": "122499", "secreto": "691302", "dispositivo": "a8f3…", "rol": "" }
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 1. urls.py            "sesiones/" → SesionesView                      │
├───────────────────────────────────────────────────────────────────────┤
│ 2. views.py           SesionesView.post()                             │
│                       Es VistaPublica: no exige sesión previa         │
├───────────────────────────────────────────────────────────────────────┤
│ 3. serializers.py     LoginEntrada revisa la FORMA del formulario:    │
│                       ¿vienen identificador y secreto? ¿son texto?    │
│                       NO revisa si la clave es correcta: eso es       │
│                       negocio, no forma                               │
├───────────────────────────────────────────────────────────────────────┤
│ 4. contenedor.py      Entrega las herramientas: archivo, caja fuerte, │
│                       sellador de pases, reloj y generador de azar    │
├───────────────────────────────────────────────────────────────────────┤
│ 5. casos_uso.py       AutenticarUsuario.ejecutar(…)  ← EL FUNCIONARIO │
│                       Abre la carpeta con ejecutar_registrando: lo    │
│                       que se escriba queda, aunque el resultado sea   │
│                       un error                                         │
└───────────────────────────────────────────────────────────────────────┘
        │
        ├─ a) dominio/valores.py · DocumentNumber.normalizar_entrada()
        │     "122499" → "122499".  Si fuera "1.042.888-795" → "1042888795"
        │
        ├─ b) infraestructura/seguridad.py · cifrador.indice()
        │     Convierte el código en una huella HMAC. Los identificadores
        │     están CIFRADOS en la base: se busca por huella, no por texto
        │
        ├─ c) infraestructura/repositorios.py · usuarios.por_identificador(huella)
        │     Encuentra a Juan (sólo entre identificadores vigentes, no retirados).
        │     Si no lo encontrara, verifica igual contra un hash señuelo, para que
        │     "no existe" tarde lo mismo que "clave incorrecta"
        │
        ├─ d) casos_uso.py · asignaciones_vigentes() + elección del rol
        │     Juan tiene un solo rol vigente (STUDENT). Si tuviera varios y no
        │     hubiera pedido uno, entraría con el principal (BR-021)
        │
        ├─ e) casos_uso.py · politica_de(usuario, rol)
        │     ¿Qué reglamento le aplica? Su grupo (si tiene uno propio) → su nivel
        │     educativo (preescolar con avatar, BR-024) → su perfil. Octavo A no
        │     tiene excepción: manda la política de estudiantes: código + PIN
        │
        ├─ f) dominio/entidades.py · politica.admite_identificador(CODIGO)
        │     ¿Este colegio deja entrar con código estudiantil? Sí
        │
        ├─ g) dominio/politicas.py · PoliticaBloqueo.evaluar(intentos, politica)
        │     ¿Juan viene de fallar cinco veces? No. Puede seguir
        │
        ├─ h) infraestructura/seguridad.py · hasher.verificar(hash, "691302")
        │     Argon2id compara. La base NUNCA guardó el PIN, sólo su huella
        │
        ├─ i) repositorios · intentos.registrar(EXITO)
        │
        ├─ j) casos_uso.py · abrir_sesion()               ← SESIÓN ÚNICA
        │     · cierra otras sesiones de Juan (otro_dispositivo) y anota cuál era
        │     · cierra la sesión de otra persona en esta tableta (dispositivo_compartido)
        │     · crea la fila de sesión con el ROL EFECTIVO
        │     · pide a seguridad.py un JWT firmado de cuatro horas
        │
        └─ k) auditoría + outbox
              identidad.sesion.abierta.v1 en la cola de salida, en la misma transacción
        │
        ▼  Se cierra la carpeta: TODO lo anterior se confirma de golpe
┌───────────────────────────────────────────────────────────────────────┐
│ 6. views.py           Devuelve el diccionario tal cual, como JSON      │
│                       { token, expira_en, inactividad_min,             │
│                         sesion_anterior, roles_disponibles, usuario }   │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
   TABLETA guarda el pase en el almacén seguro del dispositivo
        │  GET /api/acceso/yo/   con el pase en la cabecera
        ▼
   autenticacion.py → ResolverPrincipal: ¿sesión vigente? ¿no cerrada? ¿no inactiva?
   Recibe menú "student", rol efectivo, permisos y grupos → pinta el menú del estudiante
```

### 3.3 · Las cuatro cosas que este viaje enseña

1. **La vista es muy corta a propósito.** Tres líneas: validar la forma, llamar al caso de uso, devolver. Toda la inteligencia está en el caso de uso, y por eso se prueba sin levantar un servidor.
2. **El dominio decide, la infraestructura obedece.** Quién puede entrar lo decide `politicas.py`, que no sabe qué es una base de datos. Cómo se guarda lo resuelve `repositorios.py`, que no decide nada.
3. **Los datos sensibles cambian de forma al cruzar la frontera.** El código de Juan entra en texto, se guarda cifrado y se busca por huella. Su PIN nunca se guarda: sólo su huella Argon2id.
4. **El reglamento se resuelve por el objeto, no por la persona.** Que Juan entre con PIN o con avatar lo dice el nivel de su grupo, no una casilla en su ficha. Es la regla del Maestro «el alcance se resuelve por el objeto» aplicada a las credenciales.

---

## 4 · Los 39 casos de uso, uno por uno

Cada ficha tiene la misma estructura: **qué hace**, **ruta y ejemplo**, **recorrido** por capas, **pantalla** que lo consume y, cuando aplica, la **función del Maestro** que cumple.

---

### Familia A · Arranque y dispositivos

#### A.1 · `InstalarNodo` (JRN-001, PAN-204)

**Qué hace.** El día cero del equipo. Resuelve el huevo y la gallina: para crear usuarios hace falta un administrador, y para crear al administrador hacen falta permisos que nadie tiene. De una vez crea el colegio, las **cinco** políticas de acceso (una por perfil) y a la primera persona, administradora.

**Ruta.** `POST /api/acceso/instalacion/` · pública · una única vez.

```bash
curl -X POST http://127.0.0.1:8000/api/acceso/instalacion/ -H "Content-Type: application/json" -d '{
  "organizacion": {"codigo":"IE-SANJOSE","nombre":"IE San José","pais":"CO","idioma":"es","locale":"es-CO"},
  "administrador": {"alias":"Rectoría","nombres":"Ana","apellidos":"Pérez","dni":"1042888795"}
}'
```

**Recorrido.** `InstalacionEntrada` (forma) → caso de uso: ¿ya hay colegio? 409 → `asegurar_plantillas()` (permisos y los cinco roles) → `CountryCode`/`LanguageCode`/`LocaleCode` validan ISO → `POLITICAS_POR_DEFECTO` → `CrearUsuario._crear()` para la administradora, que recibe además su **primera asignación de rol** con alcance de organización → auditoría y evento `identidad.organizacion.instalada.v1`.

**Detalle.** `password_inicial` se devuelve una sola vez: es la «hoja de acceso del administrador, de un solo uso» del Maestro.

**Pantalla.** Instalador de Windows; A2 como respaldo si el equipo llega sin instalar.

---

#### A.2 · `ConsultarConfiguracion` (PAN-101, BR-024)

**Qué hace.** Le dice a la app cómo pintar la pantalla de acceso, sin revelar ningún dato personal. Por perfil, y **por nivel educativo** cuando el colegio configuró excepciones: preescolar con avatar, primaria con clave corta, secundaria con contraseña, todo en la misma instalación.

**Ruta.** `GET /api/acceso/configuracion/` · pública.

**Cómo lo usa el frontend.** Si el nivel del grupo dice `AVATAR`, la app muestra una cuadrícula de dibujos; si dice `PIN`, teclado numérico; si dice `PASSWORD`, teclado completo. También trae `inactividad_min`, para que la app avise antes de que la sesión se cierre sola.

**Pantalla.** S1, S2, O1.

---

#### A.3 · `RegistrarDispositivo` · A.4 · `ListarDispositivos` · A.5 · `ActualizarDispositivo`

**Qué hacen.** La tableta se presenta al aula («soy esta», idempotente); el profesor las ve para elegir cuál autorizar; administración las renombra o da de baja. Dar de baja **cierra las sesiones abiertas en ella** con motivo `dispositivo_baja`.

**Rutas.** Desde el 2026-09-28 estos tres casos de uso viven en **MOD-009 · Device Manager** (`backend/device_manager/`, `POST` / `GET /api/dispositivos/`, `PATCH /api/dispositivos/{id}/`, más `bloquear/`, `desbloquear/` y `latido/`; ver [03-device-manager](../03-device-manager/00-modelo-y-api.md)). Este módulo conserva su puerto `RepositorioDispositivos` para leerlos en el login y para cerrar las sesiones de una tableta dada de baja.

**Nota del Maestro.** El dispositivo es **contexto, nunca identidad**: la sesión es de la persona; la tableta sólo dice desde dónde.

**Pantallas.** S1 (invisible), O3, A1.

---

### Familia B · Entrar, estar y salir

#### B.1 · `AutenticarUsuario` (FUN-004, FUN-005, FUN-007, BR-021)

**Qué hace.** Comprobar quién es alguien y entregarle un pase válido por cuatro horas, imponiendo la sesión única. Recorrido completo en la sección 3.

**Ruta.** `POST /api/acceso/sesiones/` · pública.

**Elegir el rol.** Si la persona tiene varios roles vigentes, puede enviar `"rol": "REPORTS"` y trabajará esa sesión como Reportes: verá el menú de Reportes y sólo los permisos de Reportes. Si no envía nada, entra con su rol principal. La respuesta trae `roles_disponibles` para que la app ofrezca el cambio.

**Las cuatro defensas.**

| Defensa | Qué evita |
|---|---|
| Mismo error y mismo tiempo para «no existe», «tipo no permitido», «rol no asignado» y «clave incorrecta» | Que alguien descubra quién está matriculado |
| El tipo de identificador debe estar permitido por el reglamento aplicable | Entrar con el documento cuando el colegio dijo «aquí se entra con la matrícula» |
| Bloqueo tras cinco fallos en quince minutos (FUN-007), con evento `identidad.cuenta.bloqueada.v1` | Probar PIN uno por uno |
| Argon2id, deliberadamente lento | Que robar la base sirva para adivinar claves |

**Respuestas.** `200` (con `sesion_anterior` si cerró otra) · `401 credenciales_invalidas` con `intentos_restantes` · `423 usuario_bloqueado` con `reintentar_en_seg`.

**Pantallas.** S2, O1, S6/PAN-103 para el aviso de sesión anterior.

---

#### B.2 · `ResolverPrincipal` (FUN-009, FUN-011)

**Qué hace.** Es el **portero invisible**. Sin ruta propia: se ejecuta en *cada* petición que traiga un pase, antes de que la vista vea nada.

**Recorrido.** `autenticacion.py` lee `Authorization: Bearer …` → este caso de uso comprueba contra la base, en orden:

1. La firma del pase es válida y no caducó.
2. La sesión existe y no fue cerrada. Si fue cerrada, dice **por qué**: `sesion_cerrada_otro_dispositivo`, `sesion_inactiva` o `sesion_revocada`, para que la app muestre el mensaje correcto.
3. **Inactividad (FUN-009):** si desde el último uso pasaron más minutos que `inactividad_min` del reglamento aplicable, la sesión se cierra aquí mismo con motivo `inactividad` y se rechaza. No hay temporizador en segundo plano: el reloj del nodo decide al primer contacto.
4. La cuenta sigue activa y el rol efectivo de la sesión existe.

**Por qué contra la base y no fiándose del pase.** Porque en cuatro horas pasan cosas: el profesor cierra la sesión del estudiante, alguien entra desde otra tableta, el rector suspende una cuenta. Al mirar la base en cada petición, esas decisiones surten efecto al instante.

**Reinicio del nodo (FUN-011).** La sesión vive en `m01_sesion`, no en la memoria del proceso. Si el equipo del aula se reinicia, el mismo pase sigue valiendo y la primera petición «restaura» la sesión sin que el profesor vuelva a escribir su clave. Hay una prueba que lo simula.

---

#### B.3 · `ConsultarIdentidad`

**Qué hace.** Responde «¿quién soy y qué puedo hacer aquí?». Decide qué menú ve cada persona.

**Ruta.** `GET /api/acceso/yo/`.

**Qué devuelve de nuevo tras la alineación.** `rol_efectivo` (con el alcance de su asignación: organización, nivel o grupo), `roles_disponibles` (para cambiar de rol volviendo a entrar), los permisos ya **acotados** por la asignación, e `identificadores` con emisor y principal.

**Advertencia que conviene repetir.** Esto sirve para dibujar la pantalla, no para proteger nada. Cada botón vuelve a comprobarse en el servidor al pulsarlo.

**Pantallas.** S6, O2, A1, A2.

---

#### B.4 · `CambiarCredencialPropia`

**Ruta.** `PUT /api/acceso/yo/credencial/` · `{ "secreto_actual", "secreto_nuevo" }`.

Cuatro reglas: la actual debe ser correcta; la nueva cumple el reglamento aplicable (PIN, contraseña o avatar); no repite las tres últimas; **cierra las demás sesiones** con motivo `credencial_cambiada`.

**Pantalla.** S4.

---

#### B.5 · `RevocarSesion` · B.6 · `RevocarSesionesDeUsuario` (FUN-010) · B.7 · `ListarSesiones`

**Rutas.** `DELETE /sesiones/actual/` (propia, motivo `persona`) · `DELETE /sesiones/{id}/` (ajena, motivo `profesor` o `administrador`) · `DELETE /usuarios/{id}/sesiones/` (**todas** las de una persona, FUN-010) · `GET /sesiones/`.

Cada sesión listada trae su **rol efectivo**, su dispositivo y su `motivo_cierre`, así el administrador entiende de un vistazo por qué se cerró cada una.

**Pantallas.** S6, O2, A2.

---

### Familia C · Personas

#### C.1 · `CrearUsuario` (FUN-001, DEC-049, MSG-023)

**Qué hace.** Matricular a alguien: cuenta, datos personales cifrados, identificadores externos, **primera asignación de rol**, inscripción al grupo y primera clave. Todo en una carpeta.

**Ruta.** `POST /api/acceso/usuarios/`

```bash
curl -X POST .../api/acceso/usuarios/ -H "Authorization: Bearer $TOKEN" -d '{
  "rol": "STUDENT", "alias": "Juan P.",
  "persona": {"nombres":"Juan","apellidos":"Pérez","fecha_nacimiento":"2012-04-09"},
  "identificadores": [{"tipo":"CODIGO_ESTUDIANTIL","valor":"122499","es_login":true,"principal":true},
                      {"tipo":"DNI","valor":"1.020.334.556","es_login":false}],
  "grupo_id": "…"
}'
```

**Recorrido detallado.**

| Paso | Capa | Qué pasa |
|---|---|---|
| 1 | `serializers.py` · `UsuarioEntrada` | Forma: rol, alias; identificadores opcionales; `provisional` |
| 2 | `casos_uso.py` | Alcance sobre `identity.user.create`: el profesor sólo crea estudiantes y **debe** indicar un grupo suyo; administración crea cualquier nivel igual o inferior |
| 3 | `dominio/valores.py` · `DocumentNumber` | Normaliza cada identificador |
| 4 | `repositorios.py` · `existe_identificador()` | ¿Ya es de otra persona (vigente)? → 400 `identificador_duplicado` |
| 5 | `casos_uso.py` | **DEC-049**: si no hay ningún identificador de acceso, el nodo emite una `CLAVE_INSTALACION` («IE-SANJOSE-583920»). **DEC-048**: exactamente un `principal`; `emisor` = código del colegio |
| 6 | `repositorios.py` · `guardar_persona()` | Cifra nombres, apellidos, nacimiento y teléfono |
| 7 | `repositorios.py` · `guardar_asignacion()` | Primera fila en `m01_usuario_rol`: rol principal, alcance de organización |
| 8 | `repositorios.py` · `guardar_miembro()` | **Inscripción antes de la clave**: el grupo o su nivel pueden cambiar el reglamento (avatar en preescolar) |
| 9 | `politica_de()` + `PoliticaFortaleza` + Argon2id | Valida o genera la clave según el reglamento aplicable |
| 10 | auditoría + outbox | `identidad.usuario.creado.v1` |

**Admisión nominal (JRN-007, MSG-023).** «Tu profesor puede dejarte entrar por tu nombre y vincularlo después.» El profesor envía `{ "rol": "STUDENT", "alias": "Lucía", "provisional": true, "grupo_id": "…" }`, sin identificadores ni clave. Se crea una cuenta **provisional** con clave de instalación; el profesor le da el pase de examen a la tableta y Lucía trabaja. Cuando llegue el padrón, se vincula (C.3).

**Pantallas.** O5 · Nuevo estudiante; O2 · «Admitir por nombre».

---

#### C.2 · `ImportarUsuarios` (FUN-003, CAP-003, JRN-003, PAN-220, MSG-065)

**Qué hace.** Dar de alta alumnos y profesores por carga masiva desde un archivo delimitado, sin red.

**Ruta.** `POST /api/acceso/usuarios/importar/` · permiso `identity.user.import` (administración). También `manage.py acceso_importar padron.csv --actor-dni 1042888795`.

```
rol,alias,nombres,apellidos,tipo_identificador,identificador,grupo,secreto
STUDENT,,Carlos,Torres,CODIGO_ESTUDIANTIL,150001,8A,
STUDENT,Sofi L.,Sofía,López,CODIGO_ESTUDIANTIL,150002,9B,
TEACHER,Prof. Díaz,Ana,Díaz,DNI,90111222,,Docente.2026!
```

**Recorrido.**

| Paso | Capa | Qué pasa |
|---|---|---|
| 1 | `ImportacionEntrada` | Llega `contenido` (el texto del archivo) o `filas` ya parseadas |
| 2 | `casos_uso.py` · `_parsear()` | `csv.DictReader`. **Precondición del Maestro**: si las columnas no son las esperadas → 400 con `columnas_esperadas` |
| 3 | Por cada fila | Busca el identificador por huella. Si **ya existe**, «fusiona»: no duplica, lo reporta en `existentes`. Si no, `CrearUsuario._crear()` con el grupo de la columna |
| 4 | Errores por fila | Se capturan y van a `rechazadas` con `fila`, `motivo` y `codigo`; **no abortan el lote** (MSG-065: «Importamos n de m. Las k filas con problemas están listas para descargar y corregir») |
| 5 | Al final | Un solo asiento de auditoría con los conteos y `identidad.usuarios.importados.v1` |

**Respuesta.** `{ resumen, creados (con secreto_inicial), existentes, rechazadas }`. El alias se propone «Nombre A.» si no viene.

**Pantalla.** A1 · Importar padrón, con vista previa y descarga de rechazadas.

---

#### C.3 · `VincularUsuarioProvisional` (JRN-007)

**Qué hace.** Cierra la admisión nominal. La cuenta provisional que creó el profesor se vincula con la persona definitiva que llegó por el padrón.

**Ruta.** `POST /api/acceso/usuarios/{provisional}/vincular/` · `{ "usuario_definitivo_id": "…" }` · permiso `identity.user.update` sobre ambas.

**Qué pasa.** La provisional pasa a `RETIRADO` con `vinculado_a` apuntando a la definitiva; sus sesiones se cierran; se publica `identidad.usuario.vinculado.v1` para que el expediente reasigne lo que hizo. **Nada se borra** (BR-025): el rastro de que Lucía trabajó como provisional queda.

**Pantalla.** O2 · en la fila del alumno provisional, «Vincular con…».

---

#### C.4 · `ListarUsuarios` · C.5 · `VerUsuario` · C.6 · `ActualizarUsuario`

**Rutas.** `GET /usuarios/`, `GET` / `PATCH /usuarios/{id}/`.

**La lista se recorta sola** según el alcance del rol efectivo: el estudiante se ve a sí mismo; el profesor a sus estudiantes; una coordinadora de nivel a todo su nivel; administración a todo el colegio.

**Reglas de `ActualizarUsuario`.** Dejar de estar activo cierra sesiones (`estado_cuenta`). **BR-025**: una cuenta `RETIRADO` no se reactiva (409) y sus identificadores siguen reservados. Cambiar identificadores **retira** los anteriores en vez de borrarlos (CV-05).

**Pantallas.** O2, A2.

---

#### C.7 · `AsignarRol` (FUN-002, CAP-005, CAP-006, BR-021) · C.8 · `RevocarRolAsignado`

**Qué hace.** Asignar un rol **con alcance concreto y vigencia**. Es la tabla `m01_persona_rol` del Maestro.

**Ruta.** `POST /api/acceso/usuarios/{id}/roles/`

```json
{ "rol": "ADMIN", "alcance_tipo": "LEVEL", "alcance_id": "secundaria", "vigente_hasta": null, "principal": false }
```

Tres ejemplos que resuelven casos reales del colegio:

| Caso | Cuerpo |
|---|---|
| La profesora Gómez también es coordinadora de secundaria | `rol: ADMIN`, `alcance_tipo: LEVEL`, `alcance_id: secundaria` |
| Un profesor suplente cubre 8A hasta fin de mes (CAP-006) | `rol: TEACHER`, `alcance_tipo: ASSIGNED_GROUPS`, `alcance_id: <8A>`, `vigente_hasta: <fin de mes>` |
| La secretaria pasa a Reportes como rol por defecto | `rol: REPORTS`, `principal: true` |

**Reglas.** Nadie asigna un nivel superior al suyo ni un alcance mayor que el de su propia asignación. Repetir la misma asignación la sustituye (idempotente). `principal: true` cambia el menú por defecto y cierra las sesiones (`rol_cambiado`).

**Revocar.** `DELETE /usuarios/{id}/roles/{asignacion_id}/`. Nunca deja a la persona sin rol (409): asigne otro antes o retire la cuenta.

**Pantalla.** A2 · ficha de usuario, sección Roles.

---

#### C.9 · `OtorgarEscalada` (BR-101, PAN-241) · C.10 · `RevocarEscalada`

**Qué hace.** Un permiso puntual, temporal, con motivo. Es la tabla `m01_escalada` del Maestro.

**Ruta.** `POST /api/acceso/usuarios/{id}/escaladas/`

```json
{ "permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "Coordinadora académica 2026", "vigente_hasta": 1789014400000 }
```

**Tres reglas que no se negocian.**

1. **Caducidad obligatoria** (`vigente_hasta`), máximo 24 horas. Sin ella, 400. Caduca sola; renovar es un asiento nuevo.
2. **Motivo obligatorio**: es lo que se lee en la auditoría meses después.
3. **Sin autoconcesión**: quien concede y quien recibe deben ser identidades distintas, aunque ambos sean administradores (403).

Además, el alcance no supera el techo del permiso ni el que tiene quien concede.

**Pantalla.** A2 · Escalada temporal (MSG-052 «Tienes acceso a {alcance} hasta el {fecha}» y MSG-053 al vencer).

---

#### C.11 · `RestablecerCredencial` (FUN-006, CAP-004)

**Qué hace.** La recuperación real: el profesor establece una clave provisional desde el aula, sin soporte externo. Se genera según el reglamento aplicable (PIN, contraseña o avatar).

**Ruta.** `POST /api/acceso/usuarios/{id}/credencial/restablecer/`. → `{ "secreto_provisional": "204915", "debe_cambiar": true, "sesiones_revocadas": 2 }`. Una sola vez.

**Pantalla.** O2 → O4.

---

#### C.12 · `DesbloquearUsuario` (FUN-008)

**Ruta.** `POST /api/acceso/usuarios/{id}/desbloquear/`. Inserta una fila `DESBLOQUEO`; como el conteo sólo mira los fallos posteriores al último éxito o desbloqueo, esa fila borra el pasado sin borrar la evidencia. Publica `identidad.cuenta.desbloqueada.v1`.

**Pantalla.** O2.

---

### Familia D · La emergencia del examen (CAP-002, CAP-004)

El examen empieza a las 10:00. Son las 09:57. Juan dice que olvidó su clave. El sistema no adivina si es verdad: el profesor decide y todo queda registrado.

#### D.1 · `OtorgarAccesoTemporal` · D.2 · `CanjearAccesoTemporal` · D.3 · `ListarAutorizaciones` · D.4 · `RevocarAccesoTemporal`

**Rutas.** `POST` / `GET /autorizaciones-temporales/`, `POST …/canjear/` (pública), `DELETE …/{id}/`.

**Opción A · autorizar la tableta.** El profesor elige «tableta-07»; el nodo genera `grant_id` + token de 256 bits (guarda SHA-256) y se lo entrega a esa tableta; la tableta canjea y entra con una sesión `TEMPORAL`. Juan no recuerda nada.

**Opción B · código para dictar.** `834 195`, cinco minutos, un uso, guardado con Argon2id.

**La sesión temporal** sólo permite rendir la evaluación, ver el propio progreso y cerrar sesión. **No permite cambiar la credencial**: para eso está restablecer. Como toda sesión, es única por persona y única por tableta.

**Pantallas.** O3 (profesor), S3 (tableta).

---

### Familia E · Configuración del colegio

#### E.1 · `ListarRoles` · E.2 · `ListarPermisos` · E.3 · `CrearRol` (PAN-222, TST-066)

**Rutas.** `GET /roles/` (los cinco de sistema + los del colegio), `GET /permisos/` (28, con `alcance_maximo` y `sensible`), `POST /roles/` (clona una plantilla y ajusta alcances sin superar el techo de cada permiso).

**Pantalla.** A1 · Roles y permisos.

#### E.4 · `ListarPoliticas` · E.5 · `ConfigurarPolitica` (BR-023, BR-024)

**Rutas.** `GET /politicas/`, `PUT /politicas/{perfil}/` y, para excepciones por nivel, `PUT /politicas/student/?nivel=preescolar`.

```bash
curl -X PUT ".../api/acceso/politicas/student/?nivel=preescolar" -H "Authorization: Bearer $TOKEN" \
  -d '{"tipo_secreto":"AVATAR","longitud_minima":4}'
```

A partir de ahí, `GET /configuracion/` muestra `perfiles.student.niveles.preescolar.tipo_secreto = "AVATAR"` y las tabletas de los grupos de preescolar pintan la cuadrícula de dibujos. Los de octavo siguen con PIN. **Sin reinstalar nada.**

El dominio impide reglamentos absurdos (`PoliticaCredencial.validar()`): PIN fuera de 4..8, avatar para docentes, inactividad mayor que la sesión…

**Pantalla.** A1 · «Cómo entran», con una tarjeta por perfil y pestañas por nivel.

---

### Familia F · Grupos (contexto de MOD-002)

#### F.1 · `ListarGrupos` · F.2 · `VerGrupo` · F.3 · `CrearGrupo` · F.4 · `ActualizarGrupo` · F.5 · `AgregarMiembro` · F.6 · `RetirarMiembro`

Los grupos son el contexto que da sentido a «mis estudiantes» y ahora también llevan `nivel_clave`, que decide qué reglamento de acceso aplica a sus alumnos y qué grupos abre una asignación de rol con alcance `LEVEL`. Un profesor sólo añade o retira estudiantes de sus grupos. Retirar sella fecha, no borra.

**Pantallas.** O2 (selector), A1 · Grupos, O5.

---

### Familia G · PIN maestro y profesores (revisión 2026-10-06 · `aplicacion/pin_maestro.py`)

El PIN maestro es de la **institución**, no de una persona: seis dígitos con versiones, vigencia anual y bloqueo contra la adivinación. Quien lo conoce hace dos cosas y sólo dos: crear su propia cuenta de profesor y restablecer su propia contraseña de profesor. No abre cuentas de administración, de reportes ni de técnico.

| Caso de uso | Qué hace | Permiso / quién autoriza |
|---|---|---|
| `VerificadorPinMaestro` (en `casos_uso.py`) | Verifica el PIN **dentro** de la operación que autoriza: rechaza tabletas de alumno (RN-11), bloquea por equipo y global (RN-10), rechaza el vencido (RN-09) y paga el mismo coste con o sin versión activa (RB-34). Los fallos y bloqueos se confirman aunque la respuesta sea un error (`ejecutar_registrando`) | — |
| `crear_version_pin_maestro` (RB-10) | Nace una versión: sustituye la anterior, reinicia el reloj, evento y asiento. La llama `InstalarNodo` (primer arranque, sin creador) y `CambiarPinMaestro` | — |
| `ConsultarEstadoPinMaestro` (RB-12) | `{configurado, creado_en, vence_en, dias_restantes, vencido, aviso, bloqueado_hasta}`, nunca el PIN | `identity.master_pin.manage` |
| `CambiarPinMaestro` (RB-11) | Reemplaza el PIN sin saber el actual: seis dígitos, no trivial, distinto de los tres últimos | `identity.master_pin.manage` |
| `RegistrarDocente` (RB-13) | Dos transacciones: verifica el PIN (se confirma aunque falle) y luego crea la cuenta `TEACHER` activa, con origen `PIN_MAESTRO`, contraseña definitiva y docente de los grupos elegidos | **PIN maestro** |
| `RestablecerContrasenaDocente` (RB-14) | Verifica el PIN **antes** de mirar el documento (RN-25), sólo restablece profesores (RN-12), cierra sus sesiones y levanta su bloqueo | **PIN maestro** |
| `ListarDocentesPorPinMaestro` (RB-15) | Las cuentas con origen `PIN_MAESTRO`, con el equipo desde el que se registraron | `identity.user.read` (organización) |

`AutenticarUsuario` cambia (RB-22): acepta `usuario_id` (alumno que toca su nombre) y `pin_maestro` (administración). `InstalarNodo` exige `pin_maestro`. `ConsultarConfiguracion` añade el estado público del PIN y las puertas de entrada (RB-24). `RestablecerCredencial` deja a los alumnos en PIN pendiente (RB-23). `CrearGrupo` admite al profesor sobre sus propios grupos (RB-28). `ConfigurarPolitica` admite `autoregistro`, `bloqueo_alcance` y `visitante` (RB-27). `ImportarUsuarios` y el padrón dejan al alumno sin PIN en PIN pendiente (RB-26).

### Familia H · El alumno y el visitante en la tableta (`aplicacion/estudiantes.py`)

| Caso de uso | Qué hace | Quién autoriza |
|---|---|---|
| `ListarGruposDelAula` (RB-16) | Grupos que la tableta ofrece, con el tipo de clave de cada uno | Tableta registrada (BR-056) |
| `ListarEstudiantesDelGrupo` (RB-16) | `[{id, alias, pin_pendiente}]`, nada más (D-A8) | Tableta registrada |
| `RegistrarEstudiante` (RB-17) | Alta propia: alias único por grupo (RN-34) con sugerencia, PIN validado por el reglamento del grupo, tope de 5 por tableta y hora, apagable con `autoregistro` | Tableta registrada |
| `EstablecerPinAlumno` (RB-18) | Elegir el PIN de una cuenta **sin credencial** | Tableta registrada |
| `AbrirSesionVisitante` (RB-19) | Cuenta efímera + sesión `VISITANTE`; barre las visitas de más de 24 h; respeta INV-011 | Tableta registrada · política `visitante` |
| `ConfirmarEstudiante` (RB-20) | Marca `confirmado_en`; idempotente | `identity.user.update` |
| `ListarVisitantes` (RN-46) | Visitas abiertas y su tableta | `identity.session.read` (profesor o administración) |

Dominio nuevo (sin Django): `PoliticaPinMaestro` (formato, trivialidad, vigencia, aviso, bloqueo por equipo y global), `PoliticaBloqueo.evaluar_dispositivo` (RN-33), `ClaseSesion.VISITANTE` con `PERMISOS_SESION_VISITANTE`, y `alias_clave` / `sugerir_alias`. `PoliticaAutorizacion.transversal` devuelve `sesion_visitante_limitada` y limita el alcance a `SELF`; los adaptadores de autorización de modo estudio y evaluación lo dicen con su causa exacta.

### Familia I · La consola del técnico (`aplicacion/consola.py`)

| Caso de uso | Comando | Qué hace |
|---|---|---|
| `EstadoPinMaestroDeConsola` | `acceso_pin_maestro` | Estado sin mostrar el PIN |
| `CambiarPinMaestroDeConsola` | `acceso_pin_maestro --cambiar` | Reemplaza el PIN (entrada estándar o `AVACOM_LMS_PIN_MAESTRO_NUEVO`); asiento con `actor = sistema`, `motivo = consola` |
| `RestablecerAdministradorDeConsola` | `acceso_restablecer_admin --dni …` | Único camino para recuperar al administrador (RN-12, PA-07): contraseña provisional, sesiones cerradas, asiento con `actor = sistema` |

**Los 16 casos de uso y piezas de esta revisión se suman a los 39 de las familias A–F.**

## 5 · Las piezas que no son casos de uso

### 5.1 · Migraciones

| Archivo | Qué hace |
|---|---|
| `0001_initial.py` | Crea las tablas originales del módulo |
| `0002_plantillas.py` | Siembra el catálogo de permisos y los roles de fábrica |
| `0003_alineacion_mod001.py` | **Reforma**: crea `m01_usuario_rol`; añade `nivel_clave` e `inactividad_min` a las políticas, `emisor`/`principal`/`retirado_en` a los identificadores, `provisional`/`vinculado_a` a los usuarios, `rol` a las sesiones y `nivel_clave` a los grupos; cambia las restricciones únicas a parciales |
| `0004_datos_mod001.py` | **Datos**: renombra los permisos a `identity.*` conservando roles y escaladas; siembra Reportes y Técnico; crea las políticas de los perfiles nuevos en las organizaciones existentes; convierte el rol de cada usuario en su primera asignación; marca el identificador principal y su emisor |

```bash
.venv\Scripts\python manage.py migrate
```

Las cuatro son idempotentes y se probaron sobre una base con datos.

### 5.2 · Comandos de consola

| Comando | Caso de uso | Para qué |
|---|---|---|
| `manage.py acceso_instalar --codigo … --nombre … --admin-dni … --admin-nombres …` | `InstalarNodo` | Primer arranque desde el instalador de Windows |
| `manage.py acceso_importar padron.csv --actor-dni … [--delimitador ";"] [--grupo 8A]` | `ImportarUsuarios` | Cargar el padrón sin pasar por la interfaz (CAP-003, sin red) |

Ninguno reimplementa nada: dos puertas, un solo funcionario.

### 5.3 · `/health/`

`"acceso": { "instalado": true, "claves_derivadas": false }`. Si `instalado` es falso, la app ofrece el asistente; si `claves_derivadas` es verdadero, el instalador debe generar las tres claves propias.

### 5.4 · Las pruebas

| Suite | Qué comprueba |
|---|---|
| `test_arquitectura` | Que el reglamento no dependa de la tecnología |
| `test_politicas` | Cuatro alcances, el tope por asignación, los cinco roles, la regla 403, avatar, inactividad, bloqueo |
| `test_seguridad` | Cifrado, huellas, Argon2id, JWT |
| `test_api_sesiones` | Instalación, login, bloqueo, **sesión única**, **tableta compartida**, **inactividad**, **reinicio del nodo**, revocación total |
| `test_api_usuarios` | Creación por alcance, **importación**, **admisión nominal y vinculación**, credenciales, **roles con alcance y vigencia**, **escaladas**, grupos, políticas por nivel, baja irreversible |
| `test_api_temporal` | Las dos opciones del pase de examen |
| `test_outbox` | Outbox transaccional y nomenclatura `identidad.*.v1` |

```bash
.venv\Scripts\python manage.py test acceso
```

---

## 6 · Tabla maestra: caso de uso ↔ endpoint ↔ pantalla ↔ Maestro

| # | Caso de uso | Endpoint | Sesión | Pantalla | Maestro |
|---|---|---|---|---|---|
| 1 | `InstalarNodo` | `POST /instalacion/` | no | Instalador · A2 | JRN-001, PAN-204 |
| 2 | `ConsultarConfiguracion` | `GET /configuracion/` | no | S1 · S2 · O1 | PAN-101, BR-024 |
| 3 | `RegistrarDispositivo` | `POST /dispositivos/` | no | S1 | MOD-009 |
| 4 | `AutenticarUsuario` | `POST /sesiones/` | no | **S2** · **O1** | FUN-004/005/007, BR-021 |
| 5 | `ResolverPrincipal` | (todas, automático) | — | — | FUN-009, FUN-011 |
| 6 | `ConsultarIdentidad` | `GET /yo/` | sí | S6 · O2 · A1 · A2 | PAN-020 |
| 7 | `CambiarCredencialPropia` | `PUT /yo/credencial/` | sí | **S4** | — |
| 8 | `RevocarSesion` | `DELETE /sesiones/actual/` · `/{id}/` | sí | S6 · O2 · A2 | — |
| 9 | `RevocarSesionesDeUsuario` | `DELETE /usuarios/{id}/sesiones/` | sí | A2 | **FUN-010** |
| 10 | `ListarSesiones` | `GET /sesiones/` | sí | O2 · A2 | — |
| 11 | `CrearUsuario` | `POST /usuarios/` | sí | **O5** · O2 (nominal) | **FUN-001**, DEC-049, MSG-023 |
| 12 | `ImportarUsuarios` | `POST /usuarios/importar/` · comando | sí | **A1 · Importar padrón** | **FUN-003**, CAP-003, PAN-220 |
| 13 | `VincularUsuarioProvisional` | `POST /usuarios/{id}/vincular/` | sí | O2 | JRN-007 |
| 14 | `ListarUsuarios` | `GET /usuarios/` | sí | **O2** · A2 | PAN-221 |
| 15 | `VerUsuario` | `GET /usuarios/{id}/` | sí | A2 | — |
| 16 | `ActualizarUsuario` | `PATCH /usuarios/{id}/` | sí | A2 | BR-025 |
| 17 | `AsignarRol` | `POST /usuarios/{id}/roles/` · `PUT …/rol/` | sí | **A2** | **FUN-002**, CAP-005/006, BR-021 |
| 18 | `RevocarRolAsignado` | `DELETE /usuarios/{id}/roles/{a}/` | sí | A2 | — |
| 19 | `OtorgarEscalada` | `POST /usuarios/{id}/escaladas/` | sí | **A2 · PAN-241** | BR-101 |
| 20 | `RevocarEscalada` | `DELETE /usuarios/{id}/escaladas/{p}/` | sí | A2 | — |
| 21 | `RestablecerCredencial` | `POST /usuarios/{id}/credencial/restablecer/` | sí | **O4** | **FUN-006**, CAP-004 |
| 22 | `DesbloquearUsuario` | `POST /usuarios/{id}/desbloquear/` | sí | **O2** | **FUN-008** |
| 23 | `OtorgarAccesoTemporal` | `POST /autorizaciones-temporales/` | sí | **O3** | CAP-002/004 |
| 24 | `CanjearAccesoTemporal` | `POST /autorizaciones-temporales/canjear/` | no | **S3** | CAP-002, TST-074 |
| 25 | `ListarAutorizaciones` | `GET /autorizaciones-temporales/` | sí | O3 | — |
| 26 | `RevocarAccesoTemporal` | `DELETE /autorizaciones-temporales/{id}/` | sí | O3 | — |
| 27 | `ListarRoles` | `GET /roles/` | sí | A1 | PAN-222 |
| 28 | `ListarPermisos` | `GET /permisos/` | sí | A1 | PAN-222 |
| 29 | `CrearRol` | `POST /roles/` | sí | A1 | TST-066 |
| 30 | `ListarPoliticas` | `GET /politicas/` | sí | A1 | BR-023 |
| 31 | `ConfigurarPolitica` | `PUT /politicas/{perfil}/[?nivel=]` | sí | **A1** | BR-023, **BR-024** |
| 32 | `ListarGrupos` | `GET /grupos/` | sí | O2 · A1 | MOD-002 |
| 33 | `VerGrupo` | `GET /grupos/{id}/` | sí | A1 | — |
| 34 | `CrearGrupo` | `POST /grupos/` | sí | A1 | — |
| 35 | `ActualizarGrupo` | `PATCH /grupos/{id}/` | sí | A1 | — |
| 36 | `AgregarMiembro` | `POST /grupos/{id}/miembros/` | sí | A1 · O5 | — |
| 37 | `RetirarMiembro` | `DELETE /grupos/{id}/miembros/{u}/` | sí | A1 | — |
| 38 | `ListarDispositivos` | `GET /dispositivos/` | sí | O3 · A1 | MOD-009 |
| 39 | `ActualizarDispositivo` | `PATCH /dispositivos/{id}/` | sí | A1 | MOD-009 |

En negrita, la pantalla dueña de cada operación.

---

## 7 · Las pantallas del frontend, vistas desde el backend

El detalle visual está en [acceso-sugerencias.html](../../specs/presentaciones/acceso-sugerencias.html). Aquí, lo que el backend exige de cada una tras la alineación.

| Código | Pantalla | Casos de uso | Obligación que impone el backend |
|---|---|---|---|
| **S1** | Conectar al aula | 2, 3 | Generar un identificador de dispositivo una vez y guardarlo en el almacén seguro |
| **S2** | Acceso del estudiante (PAN-101) | 2, 4 | Pintar según el reglamento del nivel: cuadrícula de avatares, pad numérico o teclado completo. Si hay `sesion_anterior`, mostrar PAN-103 / MSG-020 |
| **S3** | Código del profesor | 24 | En la opción A no hay formulario: aviso y botón |
| **S4** | Elegir clave nueva | 7 | Interceptar `403 debe_cambiar_credencial` desde cualquier pantalla |
| **S5** | Bloqueado | (423) | Cuenta regresiva con `reintentar_en_seg` |
| **S6** | Menú del estudiante | 6, 8 | Hexágonos según `permisos[]`; banda amarilla si la sesión es temporal; aviso antes de `inactividad_min` |
| **O1** | Acceso del docente | 2, 4 | Teclado completo en pantalla (el nodo no tiene teclado). Si `roles_disponibles` tiene más de uno, ofrecer el cambio de rol |
| **O2** | Estudiantes del grupo | 6, 10, 11, 13, 14, 22, 32 | Estado de acceso por fila; acciones «Nuevo PIN», «Desbloquear», «Autorizar acceso», «Admitir por nombre», «Vincular con…» |
| **O3** | Autorizar acceso a examen | 23, 25, 26, 38 | Dos toques como máximo |
| **O4** | Clave provisional | 21 | Mostrar una sola vez |
| **O5** | Nuevo estudiante | 11, 36 | Identificadores opcionales (el nodo emite clave si faltan); inscripción obligatoria para el profesor |
| **A1** | Acceso y seguridad del colegio | 12, 27–39 | Pestañas: Cómo entran (por perfil y por nivel), Roles y permisos, Grupos (con nivel), Tabletas, **Importar padrón** |
| **A2** | Personas y sesiones | 1, 6, 9, 15–20 | Ficha con **roles asignados** (alcance y vigencia), **escaladas** (motivo y caducidad), sesiones con motivo de cierre, auditoría |

### 7.1 · Comportamientos que no son una pantalla

| El backend responde | La app hace |
|---|---|
| 401 `sesion_cerrada_otro_dispositivo` | «Tenías tu sesión abierta en otro dispositivo. Se cerró aquí y todo tu trabajo está a salvo.» Vuelve al acceso |
| 401 `sesion_inactiva` | «Cerramos tu sesión por inactividad y guardamos todo.» Vuelve al acceso |
| 401 `sesion_expirada` · `sesion_revocada` · `sesion_invalida` | Borra el pase y vuelve al acceso con un aviso corto |
| 403 `debe_cambiar_credencial` | Navega a la pantalla de cambio de clave |
| 403 `sesion_temporal_limitada` | Banda amarilla; «Este acceso es sólo para la evaluación» |
| 403 `sin_permiso` | «No te corresponde.» Nunca «no existe» |
| 423 `usuario_bloqueado` | Pantalla de espera con cuenta regresiva |

---

## 8 · Preguntas frecuentes

**¿Por qué una persona ya no tiene «un rol» sino «asignaciones de rol»?**
Porque el Maestro (BR-021) contempla a la profesora que además coordina un nivel. En vez de inventar un rol «profesora-coordinadora», se le asignan dos roles, cada uno con su alcance, y elige con cuál trabaja al entrar. `Usuario.rol_id` sigue existiendo como el rol por defecto.

**¿Qué diferencia hay entre una asignación de rol y una escalada?**
La asignación es estable (puede tener vigencia, pero es «su papel»). La escalada es un permiso puntual, con motivo, que caduca en horas y que otra persona tuvo que concederle. La primera se ve en la ficha como rol; la segunda, en la auditoría como excepción.

**¿Por qué fuera de alcance responde 403 y no 404?**
Porque el Maestro lo exige: «acceso denegado, nunca objeto inexistente». Fingir que algo no existe confunde al usuario legítimo y no protege nada que la auditoría no proteja mejor.

**¿Por qué el bloqueo no es una casilla?**
Porque desbloquear borraría la evidencia. Con el registro de intentos se puede ver que María falló cinco veces el martes y que la profesora la desbloqueó.

**¿Por qué la inactividad no la maneja un temporizador?**
Porque no hace falta un proceso en segundo plano: a la primera petición después del plazo, el nodo cierra la sesión y lo registra. Para quien está usando la sesión el efecto es el mismo, y el sistema es más simple.

**¿Qué pasa si el equipo del aula se reinicia a mitad de clase?**
Las sesiones están en la base, no en memoria. El pase del profesor sigue valiendo y la primera petición lo comprueba. Nadie vuelve a escribir su clave (FUN-011).

**¿Se puede recuperar una clave olvidada?**
No, y es intencional. Se **pone una nueva** desde el aula, o se da un pase de examen, o se admite al alumno por su nombre y se vincula después.

**¿Esto ya está en uso?**
El backend está implementado y probado. Las rutas del expediente siguen funcionando igual que antes: sin pase, el visitante es anónimo. Exigir sesión en todo el sistema es la decisión Q-34.

---

## 9 · Glosario mínimo

| Palabra | En lenguaje llano |
|---|---|
| **Caso de uso** | Una operación completa que alguien quiere hacer, con todas sus reglas |
| **Función (FUN)** | Lo mismo, en el vocabulario del Documento Maestro |
| **Endpoint / ruta** | Una dirección a la que la app envía una petición |
| **APIView** | El trozo de código que atiende esa dirección |
| **Serializer** | El revisor de formularios: comprueba que el mensaje tenga la forma esperada |
| **Dominio** | Las reglas de AVACOM, escritas sin depender de ninguna tecnología |
| **Repositorio** | El archivo: sabe guardar y encontrar, no decide nada |
| **Unidad de Trabajo** | La carpeta de una gestión: o se guarda entera o no se guarda |
| **Migración** | La instrucción que monta o reforma las tablas |
| **JWT** | El pase de entrada sellado que se presenta en cada petición |
| **Rol efectivo** | El rol con el que se trabaja en esta sesión, elegido al entrar |
| **Asignación de rol** | Un rol dado a una persona con un alcance (organización, nivel o grupo) y una vigencia |
| **Escalada** | Un permiso puntual y temporal, con motivo, concedido por otra persona |
| **Alcance** | Hasta dónde llega un permiso: uno mismo, sus grupos, su nivel o todo el colegio |
| **Provisional** | Una cuenta creada por el profesor «por el nombre», pendiente de vincular con la definitiva |
| **Identificador externo** | Matrícula, documento, correo o clave emitida por el nodo; lo que vincula a la misma persona entre nodos |
| **Argon2id** | La forma de guardar claves de modo que nadie pueda leerlas |
| **AES-256-GCM** | El cifrado de los datos personales, que sí se pueden volver a leer |
| **HMAC** | Una huella fija de un dato cifrado, que permite buscarlo sin descifrarlo |
| **Outbox** | La bandeja de salida: avisos `identidad.*.v1` guardados por si hay que sincronizar |
| **Idempotente** | Que repetirlo no cambia el resultado ni duplica nada |
