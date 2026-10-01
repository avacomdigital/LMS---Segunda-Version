"""
«Accesos del técnico» (019-10, BR-097, CAP-118, AC-003, VER-01): las acciones y las DENEGACIONES de quienes tienen el rol
técnico. La prueba de que el técnico no accedió a datos personales es la ausencia de `acceso.dato_personal.consultado` (y
de cualquier acción sensible con resultado `ok`) a su nombre, con la cadena verificada.
"""
from __future__ import annotations

from .. import servicios
from ..dominio import catalogos
from ..dominio import tramo as dom_tramo
from ..models import Bitacora, BitacoraTramo
from . import consultar

ROL_TECNICO = "TECHNICIAN"


def ids_tecnicos() -> set[str]:
    try:
        from acceso.models import Usuario, UsuarioRol
        ids = set(Usuario.objects.filter(rol__codigo=ROL_TECNICO).values_list("id", flat=True))
        ids |= set(UsuarioRol.objects.filter(rol__codigo=ROL_TECNICO, revocado_en__isnull=True).values_list("usuario_id", flat=True))
        return {str(i) for i in ids}
    except Exception:   # noqa: BLE001 — sin módulo de acceso no hay técnicos
        return set()


def accesos(principal, desde: int | None = None, hasta: int | None = None, limite: int = 100, antes: int | None = None, enmascarar: bool = True) -> dict:
    tecnicos = ids_tecnicos()
    qs = Bitacora.objects.filter(usuario_id__in=tecnicos) if tecnicos else Bitacora.objects.none()
    periodo = qs
    if desde is not None:
        periodo = periodo.filter(ocurrido_en__gte=int(desde))
    if hasta is not None:
        periodo = periodo.filter(ocurrido_en__lte=int(hasta))
    sensibles = [c for c, a in catalogos.ACCIONES.items() if a.sensible]
    accedio = periodo.filter(accion="acceso.dato_personal.consultado").exists() or periodo.filter(accion__in=sensibles, resultado="ok").exists()
    denegaciones = periodo.filter(resultado="denegado").count()
    con_salto = BitacoraTramo.objects.filter(estado=dom_tramo.ESTADO_CON_SALTO).exists()
    verificado = BitacoraTramo.objects.exclude(verificado_en__isnull=True).exists() and not con_salto
    pagina = periodo.filter(secuencia__lt=int(antes)) if antes is not None else periodo
    limite = max(1, min(int(limite or 100), consultar.LIMITE_MAXIMO))
    filas = list(pagina.order_by("-secuencia")[: limite + 1])
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    rotulos = consultar.rotulos_de({f.usuario_id for f in filas} | tecnicos)
    servicios.anexar(principal.usuario_id, "auditoria.consulta_realizada", "m19_bitacora", "",
                     nuevo={"filtros": {"tecnico": True, "desde": desde, "hasta": hasta}, "limite": limite, "devueltos": len(filas)})
    return {
        "tecnicos": [{"usuario_id": t, "rotulo": rotulos.get(t, "") or None} for t in sorted(tecnicos)],
        "asientos": [consultar.dto(f, rotulos, enmascarar) for f in filas],
        "siguiente": filas[-1].secuencia if hay_mas and filas else None,
        "total": periodo.count(),
        "denegaciones": denegaciones,
        "sin_acceso_a_datos_personales": not accedio,
        "cadena_verificada": verificado,
        "salto_detectado": con_salto,
        "periodo": {"desde": desde, "hasta": hasta},
    }
