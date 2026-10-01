"""
Fachada de la bitácora para los demás módulos (§4.3): conserva la firma del puerto `registrar(actor, accion, tabla,
objeto_id, anterior, nuevo)` que ya usan acceso, aula, dispositivos, estudio y el expediente, y la amplía con
parámetros opcionales (`motivo`, `resultado`, `dispositivo_id`, `evento_id`). Quién actúa de verdad, desde dónde y
con qué correlación se toma del CONTEXTO de la operación (`audit.contexto`, fijado por el middleware, el socket o el
programador), de modo que un módulo no pueda olvidarlos.

Es el único punto por el que otro módulo escribe en m19_bitacora (BR-003, un solo escritor).
"""
from __future__ import annotations

from django.conf import settings

from . import contexto
from .aplicacion import anexar as app
from .dominio import asiento as dom
from .dominio import catalogos


def _estricta() -> bool:
    return bool(getattr(settings, "AVACOM_LMS_AUDITORIA_ESTRICTA", False))


def _actor(actor: str | None, ctx: contexto.Contexto) -> tuple[str, str | None]:
    """(actor_tipo, usuario_id). Con sesión, el usuario del contexto manda; sin ella, el declarado por el módulo."""
    declarado = str(actor or "").strip()
    if ctx.origen == contexto.ORIGEN_INSTALADOR or declarado == "instalador":
        return dom.ACTOR_INSTALADOR, None
    if declarado in ("", "sistema"):
        return dom.ACTOR_SISTEMA, None
    if declarado == "cliente":
        return dom.ACTOR_DECLARADO, None
    if ctx.usuario_id and declarado == ctx.usuario_id:
        return dom.ACTOR_USUARIO, declarado[:64]
    if ctx.usuario_id:
        # El caso de uso nombró a otra persona (por ejemplo, un cierre en nombre del alumno): se conserva a quien nombró.
        return dom.ACTOR_USUARIO, declarado[:64]
    return dom.ACTOR_DECLARADO, declarado[:64]


def anexar(actor: str | None, accion: str, tabla: str = "", objeto_id: str = "", anterior=None, nuevo=None, *,
           motivo: str | None = None, resultado: str = dom.RESULTADO_OK, dispositivo_id: str | None = None,
           evento_id: str | None = None, roles_activos: list[str] | None = None, origen: str | None = None,
           ocurrido_en: int | None = None):
    """Registra un hecho auditable. Lanza `BitacoraNoDisponible` si no se pudo escribir: el caso de uso revierte."""
    ctx = contexto.actual()
    clave, definicion, extra = dom.preparar(accion, estricta=_estricta(), motivo=motivo)
    valor_nuevo = nuevo
    if extra is not None:
        valor_nuevo = {**extra, "valor_nuevo": nuevo} if not isinstance(nuevo, dict) else {**extra, **nuevo}
    actor_tipo, usuario_id = _actor(actor, ctx)
    return app.anexar(
        clave, actor_tipo=actor_tipo, usuario_id=usuario_id, modulo=definicion.modulo, resultado=resultado,
        objeto_tabla=dom.recortar_objeto(tabla), objeto_id=dom.recortar_objeto(objeto_id), valor_anterior=anterior,
        valor_nuevo=valor_nuevo, motivo=(motivo or None) and str(motivo).strip()[:dom.MAX_MOTIVO],
        dispositivo_id=dispositivo_id or ctx.dispositivo_id, evento_id=evento_id,
        roles_activos=roles_activos if roles_activos is not None else (ctx.roles_activos() or None),
        origen=origen, correlacion_id=ctx.corr, ocurrido_en=ocurrido_en,
    )


# Alias con el nombre del puerto de los módulos.
registrar = anexar


def registrar_denegacion(codigo: str, permiso: str | None, metodo: str, ruta: str, objeto=None) -> None:
    """019-08 / VER-01: toda denegación (403) con la lista completa de roles activos, el permiso solicitado y la ruta."""
    ctx = contexto.actual()
    accion = "aula.denegado" if ruta.startswith("/api/aula/") else "acceso.denegado"
    anexar(ctx.usuario_id, accion, resultado=dom.RESULTADO_DENEGADO,
           nuevo={"codigo": codigo, "permiso_solicitado": permiso, "metodo": metodo, "ruta": ruta, "objeto": objeto,
                  "roles_activos": ctx.roles_activos()})


def alteracion_intentada(operacion: str, objeto_tabla: str, objeto_id: str | None) -> None:
    """AC-081: el intento de editar o borrar la bitácora deja un asiento nuevo (resultado denegado)."""
    ctx = contexto.actual()
    anexar(ctx.usuario_id, "auditoria.alteracion_intentada", objeto_tabla, objeto_id or "", resultado=dom.RESULTADO_DENEGADO,
           nuevo={"operacion": operacion, "roles_activos": ctx.roles_activos()})


def catalogo() -> list[dict]:
    return catalogos.como_lista()
