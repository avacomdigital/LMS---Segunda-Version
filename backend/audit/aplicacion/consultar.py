"""
Consulta filtrada por permiso (019-05, FUN-197, CAP-116, §4.2 y §4.4): sólo lectura, dentro del alcance de
`audit.read` (ORGANIZATION ve toda la organización), paginada por cursor de secuencia (estable aunque lleguen asientos
nuevos), y con los valores de los asientos sensibles ENMASCARADOS salvo que una escalada vigente lo autorice (BR-131).
Cada consulta deja un asiento `auditoria.consulta_realizada` con los filtros usados.
"""
from __future__ import annotations

from .. import servicios
from ..dominio import catalogos, errores
from ..models import Bitacora
from . import estado as app_estado

LIMITE_DEFECTO, LIMITE_MAXIMO = 100, 200
FILTROS = ("actor", "actor_tipo", "desde", "hasta", "modulo", "accion", "resultado", "objeto_tabla", "objeto_id", "dispositivo",
           "correlacion", "texto", "tramo", "sensible")
ENMASCARADO = {"enmascarado": True}


def aplicar_filtros(qs, filtros: dict):
    if filtros.get("actor"):
        qs = qs.filter(usuario_id=filtros["actor"])
    if filtros.get("actor_tipo"):
        qs = qs.filter(actor_tipo=filtros["actor_tipo"])
    if filtros.get("desde") is not None:
        qs = qs.filter(ocurrido_en__gte=int(filtros["desde"]))
    if filtros.get("hasta") is not None:
        qs = qs.filter(ocurrido_en__lte=int(filtros["hasta"]))
    if filtros.get("modulo"):
        qs = qs.filter(modulo=filtros["modulo"])
    if filtros.get("accion"):
        accion = str(filtros["accion"])
        qs = qs.filter(accion__startswith=accion[:-1]) if accion.endswith("*") else qs.filter(accion=accion)
    if filtros.get("resultado"):
        qs = qs.filter(resultado=filtros["resultado"])
    if filtros.get("objeto_tabla"):
        qs = qs.filter(objeto_tabla=filtros["objeto_tabla"])
    if filtros.get("objeto_id"):
        qs = qs.filter(objeto_id=str(filtros["objeto_id"]))
    if filtros.get("dispositivo"):
        qs = qs.filter(dispositivo_id=filtros["dispositivo"])
    if filtros.get("correlacion"):
        qs = qs.filter(correlacion_id=filtros["correlacion"])
    if filtros.get("texto"):
        qs = qs.filter(motivo__icontains=str(filtros["texto"])[:100])
    if filtros.get("tramo"):
        qs = qs.filter(tramo_id=filtros["tramo"])
    if filtros.get("sensible") is not None:
        claves = [c for c, a in catalogos.ACCIONES.items() if a.sensible]
        qs = qs.filter(accion__in=claves) if filtros["sensible"] else qs.exclude(accion__in=claves)
    return qs


def rotulos_de(usuario_ids: set[str]) -> dict[str, str]:
    """Alias de las personas (m01_usuario) para mostrar al actor sin exponer nombres ni documentos."""
    ids = {u for u in usuario_ids if u}
    if not ids:
        return {}
    try:
        from acceso.models import Usuario
        return {u.id: u.alias for u in Usuario.objects.filter(pk__in=ids).only("id", "alias")}
    except Exception:   # noqa: BLE001 — la consulta no cae porque el módulo de acceso cambie
        return {}


def es_sensible(accion: str) -> bool:
    definicion = catalogos.resolver(accion)
    return bool(definicion and definicion.sensible)


def dto(fila: Bitacora, rotulos: dict[str, str], enmascarar: bool, completo: bool = False) -> dict:
    definicion = catalogos.resolver(fila.accion)
    sensible = bool(definicion and definicion.sensible)
    ocultar = sensible and enmascarar
    salida = {
        "id": fila.id, "secuencia": fila.secuencia, "ocurrido_en": fila.ocurrido_en,
        "actor": {"tipo": fila.actor_tipo, "usuario_id": fila.usuario_id, "rotulo": rotulos.get(fila.usuario_id or "", "") or None},
        "roles_activos": fila.roles_activos, "modulo": fila.modulo, "modulo_etiqueta": catalogos.ETIQUETAS_MODULO.get(fila.modulo, fila.modulo),
        "accion": fila.accion, "etiqueta": definicion.etiqueta if definicion else fila.accion, "resultado": fila.resultado,
        "objeto": {"tabla": fila.objeto_tabla, "id": fila.objeto_id}, "motivo": fila.motivo, "origen": fila.origen,
        "dispositivo_id": fila.dispositivo_id, "correlacion_id": fila.correlacion_id, "evento_id": fila.evento_id, "tramo_id": fila.tramo_id,
        "sensible": sensible, "enmascarado": ocultar, "huella": app_estado.abreviada(fila.huella),
        "valor_anterior": ENMASCARADO if ocultar else fila.valor_anterior,
        "valor_nuevo": ENMASCARADO if ocultar else fila.valor_nuevo,
    }
    if completo:
        salida["huella"] = fila.huella
        salida["huella_previa"] = fila.huella_previa
    return salida


def listar(principal, filtros: dict, limite: int | None = None, antes: int | None = None, despues: int | None = None,
           enmascarar: bool = True) -> dict:
    limite = max(1, min(int(limite or LIMITE_DEFECTO), LIMITE_MAXIMO))
    qs = aplicar_filtros(Bitacora.objects.all(), filtros)
    total = qs.count()
    ascendente = despues is not None
    if despues is not None:
        qs = qs.filter(secuencia__gt=int(despues)).order_by("secuencia")
    else:
        if antes is not None:
            qs = qs.filter(secuencia__lt=int(antes))
        qs = qs.order_by("-secuencia")
    filas = list(qs[: limite + 1])
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    rotulos = rotulos_de({f.usuario_id for f in filas})
    asientos = [dto(f, rotulos, enmascarar) for f in filas]
    siguiente = filas[-1].secuencia if hay_mas and filas else None
    usados = {k: v for k, v in filtros.items() if v not in (None, "")}
    servicios.anexar(principal.usuario_id, "auditoria.consulta_realizada", "m19_bitacora", "",
                     nuevo={"filtros": usados, "limite": limite, "devueltos": len(asientos), "cursor": {"antes": antes, "despues": despues}})
    return {"asientos": asientos, "siguiente": siguiente, "orden": "asc" if ascendente else "desc", "limite": limite, "total": total,
            "enmascarado": enmascarar}


def detalle(principal, asiento_id: str, enmascarar: bool = True) -> dict:
    fila = Bitacora.objects.filter(pk=asiento_id).first()
    if fila is None and str(asiento_id).isdigit():
        fila = Bitacora.objects.filter(secuencia=int(asiento_id)).first()
    if fila is None:
        raise errores.NoEncontrado("No existe ese asiento.")
    salida = dto(fila, rotulos_de({fila.usuario_id}), enmascarar, completo=True)
    if salida["sensible"] and not enmascarar:
        # BR-131: ver el detalle de un asiento con datos personales es, a su vez, un hecho auditable.
        servicios.anexar(principal.usuario_id, "acceso.dato_personal.consultado", "m19_bitacora", fila.id,
                         nuevo={"accion": fila.accion, "secuencia": fila.secuencia, "objeto": {"tabla": fila.objeto_tabla, "id": fila.objeto_id}})
    return salida
