"""
MOD-007 visto desde la evaluación: la clase de la que nace un examen. SÓLO LECTURA (la evaluación no escribe `m07_*`). Si el módulo del aula cambia o
la sesión no existe, la evaluación sigue funcionando sin ella: el aviso de tiempo real es opcional y los dispositivos de la clase sólo enriquecen el
panel.
"""
from __future__ import annotations


class AulaClasesLectura:
    def sesion(self, sesion_id: str) -> dict | None:
        from classroom_engine.models import SesionDeClase
        fila = SesionDeClase.objects.filter(pk=sesion_id).first() if sesion_id else None
        return {"id": fila.id, "grupo_id": fila.grupo_id, "profesor_id": fila.profesor_id, "estado": fila.estado} if fila else None

    def dispositivos_de(self, sesion_id: str) -> dict[str, str]:
        from classroom_engine.dominio import sesion as dom
        from classroom_engine.models import Participante
        filas = Participante.objects.filter(sesion_id=sesion_id, estado__in=dom.ADMITIDOS).exclude(dispositivo_id="")
        return {f.persona_id: f.dispositivo_id for f in filas}
