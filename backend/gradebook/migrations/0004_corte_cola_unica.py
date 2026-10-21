"""
Corte de MOD-011 a la cola única de MOD-015 (Fase 3, P-05): desde aquí el módulo escribe sus eventos SÓLO en `m15_evento` (`nodo.servicios.publicar`, en la transacción del hecho) y
`m11_evento_salida` queda intacta como historia de sólo lectura (BR-016), servida por `gradebook.servicios.eventos_legados` detrás de la fachada `nodo.servicios.leer`.

El corte es UNA fila en `m15_corte` (`ultima_legada` = el último id de la tabla antigua; 0 en una instalación nueva) escrita junto con el salto del contador global, para que toda
marca de lectura anterior siga valiendo (D-20). Idempotente (si el módulo ya está cortado no hace nada), silenciosa (sin asiento ni evento técnico: D-24) y de una sola vía (deshacer
la migración no retira el corte). Usa los modelos VIVOS de `nodo` por su interfaz: si una migración posterior de `nodo` cambiara `m15_corte` o `m15_evento`, debe declararse aquí.
"""
from django.db import migrations
from django.db.models import Max

MODULO = "gradebook"


def cortar(apps, schema_editor):
    from nodo import servicios as nodo

    if nodo.corte_de(MODULO) is not None:
        return
    EventoSalida = apps.get_model(MODULO, "EventoSalida")
    ultima_legada = int(EventoSalida.objects.aggregate(u=Max("id"))["u"] or 0)
    nodo.cortar(MODULO, ultima_legada, asentar=False)


class Migration(migrations.Migration):
    dependencies = [
        ("gradebook", "0003_puntos_brutos_y_observaciones"),
        ("nodo", "0003_agregado_id_256"),
    ]

    operations = [migrations.RunPython(cortar, migrations.RunPython.noop)]
