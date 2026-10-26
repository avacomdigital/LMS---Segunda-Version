# 18 · Backup & Recovery (MOD-016) · Operación (para el personal técnico de AVACOM)

> Respaldar y restaurar son **sólo** del personal de AVACOM WORLD. Esta guía es para ustedes. La que lee la institución es [05-guia-administrativa.md](05-guia-administrativa.md).

## 1 · Antes de instalar en un colegio

1. **Código de custodia (una vez, al instalar).** Con sesión de técnico y un **pase** con la operación `backup.schedule` (§5): `POST /api/respaldo/custodia/emitir/` `{"pase": "…"}`. La respuesta trae el **código** y la **hoja de custodia**. **Se muestra una sola vez y el equipo no lo guarda.** Imprímela, entrégala al representante de la institución (anota quién y cuándo) y **haz un respaldo completo nuevo**: sólo los respaldos hechos desde ahora se abren en otro equipo.
2. **Programación.** Por defecto: diario a las 02:00, un completo cada 7 días e incrementales entre medias, 14 respaldos conservados, local. Cámbiala con `POST programacion/`. El calendario **no** saca datos del equipo: para tener una copia fuera, exporta a mano (§3).
3. **Archivos de la institución.** Si el colegio guarda archivos que no están en la base, decláralos en `backend.env`: `AVACOM_RESPALDO_CARPETAS=evidencias=D:\Evidencias;medios:reinstalable=D:\Medios`. Lo marcado `:reinstalable` no entra salvo que se pida.
4. Comprueba `GET estado/`: `aviso_sin_respaldo` debe pasar a `false` tras el primer respaldo verificado.

## 2 · Respaldar y verificar

- **Ahora:** `POST respaldos/ahora/` (`{"tipo": "completo"}`). Sale **verificado** si todo va bien; si no, queda `completo_no_verificado` y se **reintenta cada 6 h**. Un respaldo que falla la verificación **no se descarta**: míralo con `GET respaldos/<id>/` (`historial`, `motivo`).
- **Espacio:** hacen falta ≈ `2 × la base + los archivos + 64 MB`. Si no hay, responde `espacio_insuficiente` antes de empezar.
- **Con una clase abierta** el respaldo del calendario se **aplaza** (`estado → aplazado_por_clase`); uno manual **no** se frena (el respaldo en caliente no detiene a nadie).
- **Un respaldo a medias** (el equipo se apagó) se marca `interrumpido` y se **rehace solo** al arrancar si tiene menos de un día.

## 3 · Exportar a una memoria USB

1. Conecta la memoria; `GET destinos/` → `unidades[].id`.
2. Pide un **pase** a quien tenga la llave de AVACOM (§5): operación `backup.export`.
3. `POST respaldos/<id>/exportar/` `{"unidad": "<id>", "pase": "<base64>"}`. Copia el `.avbak` (y su cadena si es incremental) y la constancia a `AVACOM\Respaldos\`, verifica el tamaño y queda `exportado`.

## 4 · Restaurar

**Antes:** sin clase abierta. Qué hace y en qué orden está en [01-diseno.md](01-diseno.md) §7: **hasta el paso 5 no se toca nada vivo**.

**En el mismo equipo** (disco dañado, error humano):
1. Elige el respaldo (`GET respaldos/`: busca el último `completo_verificado`).
2. Pide un pase con `backup.restore`.
3. `POST restaurar/` `{"respaldo_id": "…", "motivo": "datos_danados", "pase": "…"}`.
4. Lee `perdidas` (horas y eventos que se pierden) y `post.fallos`. **Reinicia el servicio** si `reinicio_recomendado`. Entrega el **informe** (`informe`, también en `Informes\`) a la administración.
5. Los profesores y alumnos **vuelven a entrar** (se cerraron todas las sesiones).

**En un equipo nuevo o reemplazado:**
1. Instala AVACOM OPS Master en el equipo nuevo.
2. Conecta la memoria con el respaldo; `GET destinos/` → `candidatos[].id`. (Si es un incremental, la memoria debe traer también su base: `exportar` ya copia la cadena.)
3. Pide al representante de la institución su **hoja de custodia**. Pide un pase con `backup.restore` (sin `--nodo`: un equipo nuevo no tiene aún su identificador).
4. `POST restaurar/` `{"candidato": "<id>", "custodia": "<código>", "motivo": "equipo_nuevo", "pase": "…"}`. Sin el código, `custodia_requerida`.
5. El equipo nuevo **guarda desde ya** la custodia: sus respaldos siguen abriendo con el mismo código.

**Si algo sale mal:** un respaldo alterado o truncado **aborta antes de tocar nada** (`restauracion_abortada`, con su `motivo`; el pase no se gasta). `aplicacion_base` = la base no se pudo reemplazar y **no cambió**. Si la respuesta trae `ok: false, parcial: true`, la base **sí** se restauró y lo derivado se rehizo, pero no se devolvieron los archivos de `fallos_archivos`: corrige la causa (archivo bloqueado, permisos, disco) y restaura de nuevo con un pase nuevo; el respaldo de seguridad previo (`punto_de_retorno`) sigue intacto.

## 5 · Emitir un pase (quien tiene la llave de AVACOM)

```bash
backend\.venv\Scripts\python tools\respaldo\emitir_pase.py emitir --privada F:\claves\sop-2026-1.pem --kid sop-2026-1 --tecnico "Ana Pérez (AVACOM)" --acciones backup.restore --horas 4 --base64
```

Operaciones que un pase puede autorizar: `backup.restore`, `backup.export`, `backup.restore.module` y `backup.schedule` (éste **sólo** para emitir la custodia).

Un pase: nombra a la persona, vale **una** operación, **≤ 24 h** y (con `--nodo`) para un solo equipo. `emitir_pase.py ver` lo inspecciona y `llave` genera el par (la privada **nunca** al repositorio; la pública va a `backend/respaldo/claves/produccion.json`: **ceremonia pendiente, Q-B1**). Mientras ese archivo esté vacío, un nodo de producción **no acepta ningún pase**.

## 6 · Qué mirar cuando algo falla

| Síntoma | Causa y salida |
|---|---|
| `pase_invalido` | el `motivo` lo dice: `vencido`, `otro_equipo`, `ya_usado` (pide otro), `kid_desconocido` (la llave de producción aún no está en `produccion.json`), `accion_no_incluida` |
| `no_verificado` con `huella_distinta` | el archivo cambió en disco (disco dañado o editado): haz un respaldo nuevo; el dañado no se borra |
| `cadena_incompleta` | falta el completo de un incremental: exporta siempre la cadena entera |
| `custodia_requerida` en el mismo equipo | se perdió `estado\nodo.key` (reinstalación): con el código de custodia sí se abre |
| `aviso_sin_respaldo` | pasaron 7 días: ¿clase abierta cada noche?, ¿sin espacio?, ¿calendario apagado? |
| `post.fallos` en una restauración | repite a mano lo que dice: `manage.py migrate`, `search_reconstruir`, `reporting_reconstruir`, `gradebook_reconstruir --reproducir` |
| La carpeta `Respaldos\trabajo\` crece | quedó trabajo de un proceso que murió: se puede borrar con el servicio parado |
