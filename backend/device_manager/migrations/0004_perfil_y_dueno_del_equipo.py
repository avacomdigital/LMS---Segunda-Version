# MOD-009 · perfil del equipo y su dueño (FUN-092, FUN-093; 008-01, 009-06). `compartido` por defecto: las tabletas que ya están en el
# inventario siguen siendo del aula. `CHECK (perfil = 'asignado') = (asignado_a_id IS NOT NULL)`: ser asignado y tener dueño es lo mismo.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_manager', '0003_telemetria_espacio_bateria'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispositivo',
            name='asignado_a_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='dispositivo',
            name='asignado_en',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='dispositivo',
            name='perfil',
            field=models.CharField(default='compartido', max_length=12),
        ),
        migrations.AddConstraint(
            model_name='dispositivo',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('perfil', 'asignado'), ('asignado_a_id__isnull', False)), models.Q(models.Q(('perfil', 'asignado'), _negated=True), ('asignado_a_id__isnull', True)), _connector='OR'), name='ck_m09_dispositivo_perfil_dueno'),
        ),
        migrations.AddConstraint(
            model_name='dispositivo',
            constraint=models.CheckConstraint(condition=models.Q(('perfil__in', ('compartido', 'asignado'))), name='ck_m09_dispositivo_perfil_valido'),
        ),
    ]
