# 2026-09-28 · Segunda versión del modelo de datos aplicada al aula:
#   · `Foco` pasa a llamarse `Selector` (m07_selector), con sus restricciones e índice renombrados;
#   · la distribución es el «lanzamiento»: alcance + destinatarios, reglas (intentos, tiempo) y los excluidos por bloqueo;
#   · el participante referencia (lógicamente) la tableta y su sesión de alumno en MOD-009;
#   · el resumen cuenta selectores en vez de focos.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classroom_engine", "0001_initial"),
    ]

    operations = [
        # --- Foco → Selector ---
        migrations.RenameModel(old_name="Foco", new_name="Selector"),
        migrations.AlterModelTable(name="selector", table="m07_selector"),
        migrations.AlterField(
            model_name="selector",
            name="sesion",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="selectores", to="classroom_engine.sesiondeclase"),
        ),
        migrations.RemoveIndex(model_name="selector", name="ix_m07_foco"),
        migrations.RemoveConstraint(model_name="selector", name="ux_m07_foco_vigente"),
        migrations.RemoveConstraint(model_name="selector", name="ck_m07_foco_sustitucion"),
        migrations.RemoveConstraint(model_name="selector", name="ck_m07_foco_referencia"),
        migrations.AddIndex(model_name="selector", index=models.Index(fields=["sesion", "declarado_en"], name="ix_m07_selector")),
        migrations.AddConstraint(
            model_name="selector",
            constraint=models.UniqueConstraint(condition=models.Q(("vigente", True)), fields=("sesion",), name="ux_m07_selector_vigente"),
        ),
        migrations.AddConstraint(
            model_name="selector",
            constraint=models.CheckConstraint(condition=models.Q(("vigente", True), ("sustituido_en__isnull", False), _connector="OR"), name="ck_m07_selector_sustitucion"),
        ),
        migrations.AddConstraint(
            model_name="selector",
            constraint=models.CheckConstraint(condition=models.Q(models.Q(("curso_ref", ""), _negated=True), models.Q(("media_ref", ""), _negated=True), _connector="OR"), name="ck_m07_selector_referencia"),
        ),
        migrations.RenameField(model_name="resumen", old_name="focos", new_name="selectores"),
        # --- el participante y su tableta (MOD-009) ---
        migrations.AddField(model_name="participante", name="dispositivo_id", field=models.CharField(blank=True, default="", max_length=36)),
        migrations.AddField(model_name="participante", name="dim_sesion_alumno_id", field=models.CharField(blank=True, default="", max_length=36)),
        # --- la distribución como lanzamiento ---
        migrations.AddField(model_name="distribucion", name="destinatarios", field=models.JSONField(default=list)),
        migrations.AddField(model_name="distribucion", name="excluidos_bloqueados", field=models.JSONField(default=list)),
        migrations.AddField(model_name="distribucion", name="intentos_permitidos", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="distribucion", name="tiempo_limite_seg", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddConstraint(
            model_name="distribucion",
            constraint=models.CheckConstraint(condition=models.Q(("intentos_permitidos__isnull", True), ("intentos_permitidos__gte", 1), _connector="OR"), name="ck_m07_dist_intentos"),
        ),
        migrations.AddConstraint(
            model_name="distribucion",
            constraint=models.CheckConstraint(condition=models.Q(("tiempo_limite_seg__isnull", True), ("tiempo_limite_seg__gte", 1), _connector="OR"), name="ck_m07_dist_tiempo"),
        ),
    ]
