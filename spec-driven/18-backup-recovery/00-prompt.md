# 18 · Backup & Recovery (MOD-016) · Prompt de trabajo

> Prompt con el que se auditó, se completó y se construyó MOD-016. Se deja aquí con su resultado (§6) para que la próxima sesión no repita la auditoría. Lo construido está en [01-diseno.md](01-diseno.md); lo que falta, en §5 y en [03-pruebas.md](03-pruebas.md) §5.

## 1 · Rol y encargo

Eres un ingeniero senior de plataforma y un experto en ingeniería de prompts. Tu encargo tiene tres partes, en este orden:

1. **Revisar los avances** de Backup & Recovery (MOD-016) contra el Documento Maestro (`AVACOM_LMS_Documento_Maestro_Consolidado_v1.0`, ficha MOD-016, JRN-018/019, CAP-104, NFR-014/030/052, TST-035/036/054/058/059/060/063, BR-003/015/017/102, INV-002/021) y contra el repositorio: ¿qué está desarrollado y qué falta?
2. **Ejecutar los cambios pendientes** que esa revisión encuentre.
3. **Ejecutar los cambios que este prompt sugiere** (§4).

**Regla del usuario, por encima de todo lo demás:** *respaldar y restaurar sólo lo puede hacer el personal de AVACOM WORLD, las personas que tienen el software.* La institución (su administración, sus profesores, sus alumnos) **no** respalda ni restaura. Además, el módulo debe **generar archivos de información para el personal administrativo** de la institución.

## 2 · Lo que ya existía antes de empezar (auditoría del 2026-10-26)

| Pieza | Estado antes |
|---|---|
| App `respaldo` (`m16_*`, `/api/respaldo/`) | **No existía.** Ninguna línea de MOD-016. |
| Puerto de MOD-015 hacia el respaldo | `nodo/infraestructura/respaldo.py`: sólo `RespaldoAusente` (`cubre()` siempre `False`): la purga de la cola única **nunca** era elegible (Q-N3: «sin MOD-016 la cola crece»). |
| MOD-017 Update Manager | Su puerto `Respaldo` era provisional: el `Host` copia la base con `Datos.Respaldar`; sin el punto de recuperación de 5 s. |
| MOD-001 | Existía `MotivoCierre.RESTAURACION` (sesiones cerradas por una restauración) **sin usar**. Ningún permiso `backup.*`. La administración recibe por defecto **todo** permiso nuevo (`_TODOS_ORG`): habría recibido los de respaldo. |
| MOD-021 / MOD-013 / MOD-011 | Ya traían `search_reconstruir`, `reporting_reconstruir`, `gradebook_reconstruir` («lo que se hace tras restaurar un respaldo»). Nadie los llamaba tras una restauración. |
| Nodo (MOD-015) | Detecta una restauración al arrancar (ancla de secuencia fuera de la base) y salta el contador: INV-002 ya tiene la mitad del trabajo. |
| Instalador | Crea `%ProgramData%\AVACOM\OPS Master\Respaldos` con `uninsneveruninstall`. Nada escribe ahí. |
| Clientes (Core/OPS/Student) | Ninguna pantalla PAN-231 «Respaldos» ni PAN-232 «Restaurar». |

**Conclusión de la auditoría: MOD-016 estaba sin desarrollar; sólo existían los puertos y los hechos que lo esperaban.**

## 3 · Restricciones (no negociables)

- **R-03 / BR-003:** MOD-016 es dueño de `m16_*` y de nada más. Lo ajeno entra por el `servicios.py` de cada dueño (`nodo`, `audit`, `acceso`, `classroom_engine`, `licenciamiento`). Dominio y aplicación sin Django.
- **INV-021:** ningún respaldo, informe, evento ni asiento de bitácora deja leer datos de alumnos, ni siquiera nombres de archivos. El técnico no los lee.
- **BR-102:** los respaldos van cifrados con la clave del nodo y **no** abren en otro equipo sin la copia de custodia de la institución.
- **INV-002:** la secuencia global nunca retrocede, tampoco tras restaurar.
- **R-01:** un respaldo nunca frena una clase; una restauración **nunca** con una clase abierta.
- **R-04:** ningún fallo interno de respaldo llega a quien pregunta (la purga, `/health/`): se responde lo prudente.
- El nodo principal **no tiene teclado**: nada que exija escribir (motivos de una lista cerrada, ids opacos, el pase por archivo).
- No tocar trabajo ajeno sin commitear (otra sesión): `git add` sólo con rutas explícitas.

## 4 · Cambios que este prompt sugiere (y se ejecutaron)

1. **Quién opera (D-1, D-2, D-3).** Permisos `backup.*` sembrados en MOD-001: la administración sólo `backup.read`; el técnico los siete. Exportar y restaurar exigen **además** un **pase de soporte** firmado por AVACOM (Ed25519, un uso, ≤ 24 h). Sin rama «anónima». El rol efectivo debe ser `TECHNICIAN` aunque se componga un rol con `backup.*`.
2. **El archivo `.avbak`.** Cifrado AES-256-GCM por trozos, clave por respaldo envuelta con la del nodo **y** con la de custodia; nombres de archivos dentro de lo cifrado; cualquier byte alterado se rechaza.
3. **Respaldar (FUN-170/171).** Instantánea consistente de la base en caliente + carpetas de la institución; completo e incremental; escritura como `.parcial` y renombrado.
4. **Verificar (FUN-173).** Descifrar todo, huellas, integridad de la base y cadena; un respaldo que falla **no se descarta**: se marca. Prueba periódica de recuperación.
5. **Programar (FUN-169).** Calendario con puesta al día; se aplaza con una clase; retención sin romper cadenas ni el último restaurable.
6. **Exportar (FUN-176)** a unidad extraíble, con su constancia.
7. **Restaurar (FUN-174).** Todo en un lugar de trabajo **antes** de tocar nada vivo (TST-059); punto de retorno; aplicar; rehacer lo derivado (esquema, nodo, sesiones, licencia, índices); informe de qué se recupera y qué se pierde. En otro equipo, con el código de custodia (TST-060).
8. **Reanudar (FUN-177)** lo interrumpido; **catálogo reconstruible** desde la carpeta.
9. **Activar la purga de MOD-015:** `RespaldoVerificado` en lugar de `RespaldoAusente` (BR-017, INV-009).
10. **Archivos para el personal administrativo (nuevo):** constancia por respaldo, resumen CSV, hoja de custodia (se muestra una vez, no se guarda) e informe de restauración, en español y sin datos de personas; la administración los **lee** y no puede operar. Más una guía para ese personal ([05-guia-administrativa.md](05-guia-administrativa.md)).
11. **Documentar** el diseño, la API, las pruebas con lo que **no** se probó, la operación del técnico y las preguntas para el CTO.

## 5 · Fuera de este tramo (queda dicho)

Pantallas de OPS (PAN-231/232) y cliente Core · alertas de MOD-020 (MSG-066: hoy `aviso_sin_respaldo` en la API y en `/health/`) · FUN-172 punto de recuperación de 5 s · FUN-175/CAP-102 restauración selectiva (la compuerta existe, ningún módulo la declara) · exclusión de `respaldo\tests` en `Build-Installer.ps1` (el archivo tiene cambios de otra sesión sin commitear) · Update Manager usando MOD-016 como respaldo previo · la ceremonia de la llave de soporte · mediciones de NFR-030/NFR-052/CAP-101 con volumen real y pruebas con memoria USB física.

## 6 · Criterios de aceptación y resultado

| Criterio | Resultado |
|---|---|
| La administración no respalda, programa, verifica, exporta ni restaura (ni concediendo escaladas) | **Cumplido** y probado (matriz de roles, rol personalizado, anónimo, actor declarado). |
| Exportar/restaurar exigen el pase; un pase malo/vencido/ajeno/usado se rechaza y queda en la bitácora | **Cumplido** y probado (vigencia, operación, equipo, firma, `kid`, un uso). |
| TST-058 respaldo válido y verificado · TST-059 corrupto aborta antes de tocar | **Cumplido** y probado (también 300 cambios de un bit, truncado, trozos reordenados). |
| TST-060 restaurar en un equipo nuevo con el código de custodia | **Cumplido** a nivel de módulo (otra clave e identidad); **sin** hardware distinto ni medir los 30 min. |
| INV-002, BR-017, INV-021, BR-102 | Cumplidos y probados (ver [03-pruebas.md](03-pruebas.md)). |
| Respaldo en caliente consistente con un escritor concurrente; restauración real sobre la conexión de Django | **Comprobado en vivo** (archivo SQLite real, no `TestCase`). |
| Archivos para el personal administrativo | **Cumplido**: ver [ejemplos/](ejemplos/) y la guía. |

Cifras: 135 pruebas propias; suites vecinas (1131 + 1626) y la revisión independiente, con lo que corrigió y lo que dejó abierto, en [03-pruebas.md](03-pruebas.md) §1 y §6.
