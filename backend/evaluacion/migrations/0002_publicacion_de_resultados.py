# MOD-010 · RF-004 (publicación de resultados) y RF-003 (descripción del profesor).
#
#   m10_asignacion   descripcion · publicar_en (política `programada`) · liberados_por (quién liberó: una persona o `sistema`)
#                    `resultados` crece a 20 caracteres para `al_finalizar_grupo`
#   m10_intento_formal   liberado_en · liberado_por (el profesor publicó el resultado de UN alumno)
#
# Las filas existentes no cambian de significado: `resultados` conserva sus tres valores y `liberados_en` sigue siendo la liberación de la asignación.
# Una liberación previa sin firma (anterior a esta migración) se asienta como `docente`, que era el actor implícito de la ruta.
from django.db import migrations, models
from django.db.models import Q


def firmar_liberaciones_previas(apps, schema_editor):
    Asignacion = apps.get_model("evaluacion", "Asignacion")
    Asignacion.objects.filter(liberados_en__isnull=False, liberados_por="").update(liberados_por="docente")


class Migration(migrations.Migration):

    dependencies = [
        ("evaluacion", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="asignacion", name="descripcion", field=models.TextField(blank=True, default="")),
        migrations.AlterField(
            model_name="asignacion", name="resultados",
            field=models.CharField(choices=[("nunca", "nunca"), ("al_entregar", "al_entregar"), ("tras_liberar", "tras_liberar"),
                                            ("al_finalizar_grupo", "al_finalizar_grupo"), ("programada", "programada")],
                                   default="tras_liberar", max_length=20)),
        migrations.AddField(model_name="asignacion", name="publicar_en", field=models.BigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="asignacion", name="liberados_por", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="intento", name="liberado_en", field=models.BigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="intento", name="liberado_por", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.RunPython(firmar_liberaciones_previas, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="asignacion", name="ck_m10_asignacion_resultados"),
        migrations.AddConstraint(
            model_name="asignacion",
            constraint=models.CheckConstraint(
                condition=Q(resultados__in=("nunca", "al_entregar", "tras_liberar", "al_finalizar_grupo", "programada")),
                name="ck_m10_asignacion_resultados")),
        migrations.AddConstraint(
            model_name="asignacion",
            constraint=models.CheckConstraint(condition=~Q(resultados="programada") | Q(publicar_en__isnull=False), name="ck_m10_asignacion_publicar_en")),
        migrations.AddConstraint(
            model_name="asignacion",
            constraint=models.CheckConstraint(condition=Q(liberados_en__isnull=True) | ~Q(liberados_por=""), name="ck_m10_asignacion_liberados_por")),
        migrations.AddConstraint(
            model_name="intento",
            constraint=models.CheckConstraint(condition=Q(liberado_en__isnull=True) | ~Q(liberado_por=""), name="ck_m10_intf_liberado_por")),
    ]
