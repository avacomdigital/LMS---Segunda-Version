# MOD-008 · Modo Estudio, 2026-09-29. Las seis tablas `m08_*` (asignación, tarea, paquete, práctica, libro de sincronización y cola de salida) con sus
# restricciones: `UNIQUE(emisor_id, secuencia)` (el reenvío no duplica), `CHECK modo = 'estudio'` en la práctica (la tabla no puede contener intentos
# formales) y un solo paquete por (asignación, alumno, aparato). Ninguna guarda contenido del curso ni claves de respuesta.
# `spec-driven/04-modo-estudio/02-modelo-y-api.md` §2 es el contrato; el modelo vive en `modo_estudio/models.py`.

import django.db.models.deletion
import modo_estudio.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Asignacion',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('grupo_id', models.CharField(blank=True, default='', max_length=36)),
                ('grupo_rotulo', models.CharField(blank=True, default='', max_length=120)),
                ('alcance', models.CharField(choices=[('grupo', 'grupo'), ('seleccion', 'seleccion')], default='grupo', max_length=16)),
                ('destinatarios', models.JSONField(default=list)),
                ('profesor_id', models.CharField(max_length=64)),
                ('profesor_rotulo', models.CharField(blank=True, default='', max_length=120)),
                ('fuente_curso', models.CharField(blank=True, default='', max_length=16)),
                ('curso_ref', models.CharField(max_length=200)),
                ('curso_version', models.CharField(blank=True, default='', max_length=32)),
                ('curso_rotulo', models.CharField(blank=True, default='', max_length=250)),
                ('leccion_ref', models.CharField(max_length=120)),
                ('leccion_rotulo', models.CharField(blank=True, default='', max_length=250)),
                ('titulo', models.CharField(max_length=250)),
                ('descripcion', models.CharField(blank=True, default='', max_length=500)),
                ('asignatura_rotulo', models.CharField(blank=True, default='', max_length=120)),
                ('unidad_rotulo', models.CharField(blank=True, default='', max_length=200)),
                ('consigna', models.TextField(blank=True, default='')),
                ('bloques', models.JSONField(default=list)),
                ('practica', models.JSONField(blank=True, null=True)),
                ('evaluacion', models.JSONField(blank=True, null=True)),
                ('bytes_estimados', models.BigIntegerField(blank=True, null=True)),
                ('paquete_permitido', models.BooleanField(default=True)),
                ('fecha_limite', models.BigIntegerField(blank=True, null=True)),
                ('plazo', models.CharField(choices=[('blando', 'blando'), ('endurecido', 'endurecido')], default='blando', max_length=12)),
                ('gracia_ms', models.IntegerField(default=900000)),
                ('estado', models.CharField(choices=[('activa', 'activa'), ('cerrada', 'cerrada')], default='activa', max_length=12)),
                ('creada_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('cerrada_en', models.BigIntegerField(blank=True, null=True)),
                ('creado_por', models.CharField(blank=True, default='', max_length=64)),
            ],
            options={
                'db_table': 'm08_asignacion',
                'indexes': [models.Index(fields=['grupo_id', 'estado'], name='ix_m08_asignacion_grupo'), models.Index(fields=['estado', 'fecha_limite'], name='ix_m08_asignacion_plazo')],
                'constraints': [models.CheckConstraint(condition=models.Q(('alcance__in', ('grupo', 'seleccion'))), name='ck_m08_asignacion_alcance'), models.CheckConstraint(condition=models.Q(('plazo__in', ('blando', 'endurecido'))), name='ck_m08_asignacion_plazo'), models.CheckConstraint(condition=models.Q(('estado__in', ('activa', 'cerrada'))), name='ck_m08_asignacion_estado'), models.CheckConstraint(condition=models.Q(models.Q(('estado', 'cerrada'), ('cerrada_en__isnull', False)), models.Q(models.Q(('estado', 'cerrada'), _negated=True), ('cerrada_en__isnull', True)), _connector='OR'), name='ck_m08_asignacion_cierre_fechado'), models.CheckConstraint(condition=models.Q(('gracia_ms__gte', 0)), name='ck_m08_asignacion_gracia')],
            },
        ),
        migrations.CreateModel(
            name='EventoSalida',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agregado_tipo', models.CharField(max_length=32)),
                ('agregado_id', models.CharField(max_length=64)),
                ('tipo_evento', models.CharField(max_length=64)),
                ('carga', models.JSONField(default=dict)),
                ('creado_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('publicado_en', models.BigIntegerField(blank=True, null=True)),
                ('intentos', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'db_table': 'm08_evento_salida',
                'indexes': [models.Index(fields=['publicado_en', 'creado_en'], name='ix_m08_outbox')],
            },
        ),
        migrations.CreateModel(
            name='Sincronizacion',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('emisor_id', models.CharField(max_length=64)),
                ('secuencia', models.BigIntegerField()),
                ('alumno_id', models.CharField(max_length=64)),
                ('dispositivo_id', models.CharField(blank=True, default='', max_length=36)),
                ('tipo', models.CharField(max_length=40)),
                ('asignacion_id', models.CharField(blank=True, default='', max_length=36)),
                ('estado', models.CharField(choices=[('integrado', 'integrado'), ('rechazado', 'rechazado'), ('pendiente_decision', 'pendiente_decision')], max_length=20)),
                ('motivo', models.CharField(blank=True, default='', max_length=64)),
                ('ocurrido_en', models.BigIntegerField()),
                ('ocurrido_en_tableta', models.BigIntegerField(blank=True, null=True)),
                ('recibido_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('carga', models.JSONField(default=dict)),
                ('resultado', models.JSONField(default=dict)),
            ],
            options={
                'db_table': 'm08_sincronizacion',
                'indexes': [models.Index(fields=['alumno_id', 'estado'], name='ix_m08_sync_alumno'), models.Index(fields=['asignacion_id', 'estado'], name='ix_m08_sync_asignacion')],
                'constraints': [models.UniqueConstraint(fields=('emisor_id', 'secuencia'), name='ux_m08_sync_emisor_secuencia'), models.CheckConstraint(condition=models.Q(('estado__in', ('integrado', 'rechazado', 'pendiente_decision'))), name='ck_m08_sync_estado')],
            },
        ),
        migrations.CreateModel(
            name='Tarea',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('alumno_id', models.CharField(max_length=64)),
                ('estado', models.CharField(choices=[('pendiente', 'pendiente'), ('en_curso', 'en_curso'), ('completada', 'completada')], default='pendiente', max_length=12)),
                ('bloques_vistos', models.JSONField(default=list)),
                ('ultimo_bloque_ref', models.CharField(blank=True, default='', max_length=200)),
                ('posicion_seg', models.IntegerField(blank=True, null=True)),
                ('avance_pct', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('fuera_de_plazo', models.BooleanField(default=False)),
                ('practica_intentos', models.SmallIntegerField(default=0)),
                ('practica_mejor', models.SmallIntegerField(blank=True, null=True)),
                ('practica_ultima', models.SmallIntegerField(blank=True, null=True)),
                ('practica_total', models.SmallIntegerField(default=0)),
                ('abierta_en', models.BigIntegerField(blank=True, null=True)),
                ('ultimo_avance_en', models.BigIntegerField(blank=True, null=True)),
                ('completada_en', models.BigIntegerField(blank=True, null=True)),
                ('creada_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('asignacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tareas', to='modo_estudio.asignacion')),
            ],
            options={
                'db_table': 'm08_tarea',
            },
        ),
        migrations.CreateModel(
            name='Practica',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('alumno_id', models.CharField(max_length=64)),
                ('objeto_ref', models.CharField(max_length=120)),
                ('objeto_rotulo', models.CharField(blank=True, default='', max_length=250)),
                ('numero', models.SmallIntegerField(default=1)),
                ('modo', models.CharField(default='estudio', max_length=8)),
                ('estado', models.CharField(choices=[('en_curso', 'en_curso'), ('terminada', 'terminada')], default='en_curso', max_length=12)),
                ('respuestas', models.JSONField(default=list)),
                ('total_preguntas', models.SmallIntegerField(default=0)),
                ('aciertos', models.SmallIntegerField(default=0)),
                ('puntaje', models.FloatField(blank=True, null=True)),
                ('puntaje_maximo', models.FloatField(blank=True, null=True)),
                ('origen', models.CharField(choices=[('directo', 'directo'), ('cola', 'cola')], default='directo', max_length=8)),
                ('dispositivo_id', models.CharField(blank=True, default='', max_length=36)),
                ('iniciada_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('terminada_en', models.BigIntegerField(blank=True, null=True)),
                ('tarea', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='practicas', to='modo_estudio.tarea')),
            ],
            options={
                'db_table': 'm08_practica',
            },
        ),
        migrations.CreateModel(
            name='Paquete',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('alumno_id', models.CharField(max_length=64)),
                ('dispositivo_id', models.CharField(max_length=36)),
                ('estado', models.CharField(choices=[('solicitado', 'solicitado'), ('descargandose', 'descargandose'), ('disponible', 'disponible'), ('vencido', 'vencido'), ('denegado', 'denegado')], default='solicitado', max_length=16)),
                ('motivo', models.CharField(blank=True, default='', max_length=48)),
                ('curso_version', models.CharField(blank=True, default='', max_length=32)),
                ('huella', models.CharField(blank=True, default='', max_length=64)),
                ('bytes_total', models.BigIntegerField(default=0)),
                ('archivos', models.JSONField(default=list)),
                ('no_incluidos', models.JSONField(default=list)),
                ('vigente_hasta', models.BigIntegerField(blank=True, null=True)),
                ('solicitado_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('descarga_iniciada_en', models.BigIntegerField(blank=True, null=True)),
                ('disponible_en', models.BigIntegerField(blank=True, null=True)),
                ('retirado_en', models.BigIntegerField(blank=True, null=True)),
                ('actualizado_en', models.BigIntegerField(default=modo_estudio.models.ahora_ms)),
                ('asignacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='paquetes', to='modo_estudio.asignacion')),
            ],
            options={
                'db_table': 'm08_paquete',
                'indexes': [models.Index(fields=['dispositivo_id', 'estado'], name='ix_m08_paquete_dispositivo')],
                'constraints': [models.UniqueConstraint(fields=('asignacion', 'alumno_id', 'dispositivo_id'), name='ux_m08_paquete'), models.CheckConstraint(condition=models.Q(('estado__in', ('solicitado', 'descargandose', 'disponible', 'vencido', 'denegado'))), name='ck_m08_paquete_estado'), models.CheckConstraint(condition=models.Q(models.Q(('estado', 'disponible'), _negated=True), models.Q(models.Q(('huella', ''), _negated=True), ('disponible_en__isnull', False)), _connector='OR'), name='ck_m08_paquete_disponible_con_huella')],
            },
        ),
        migrations.AddIndex(
            model_name='tarea',
            index=models.Index(fields=['alumno_id', 'estado'], name='ix_m08_tarea_alumno'),
        ),
        migrations.AddConstraint(
            model_name='tarea',
            constraint=models.UniqueConstraint(fields=('asignacion', 'alumno_id'), name='ux_m08_tarea'),
        ),
        migrations.AddConstraint(
            model_name='tarea',
            constraint=models.CheckConstraint(condition=models.Q(('estado__in', ('pendiente', 'en_curso', 'completada'))), name='ck_m08_tarea_estado'),
        ),
        migrations.AddConstraint(
            model_name='tarea',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('estado', 'completada'), _negated=True), ('completada_en__isnull', False), _connector='OR'), name='ck_m08_tarea_completada_fechada'),
        ),
        migrations.AddConstraint(
            model_name='tarea',
            constraint=models.CheckConstraint(condition=models.Q(('avance_pct__gte', 0), ('avance_pct__lte', 100)), name='ck_m08_tarea_avance'),
        ),
        migrations.AddIndex(
            model_name='practica',
            index=models.Index(fields=['tarea', 'objeto_ref'], name='ix_m08_practica_tarea'),
        ),
        migrations.AddConstraint(
            model_name='practica',
            constraint=models.UniqueConstraint(fields=('tarea', 'objeto_ref', 'numero'), name='ux_m08_practica_numero'),
        ),
        migrations.AddConstraint(
            model_name='practica',
            constraint=models.UniqueConstraint(condition=models.Q(('estado', 'en_curso')), fields=('tarea', 'objeto_ref'), name='ux_m08_practica_en_curso'),
        ),
        migrations.AddConstraint(
            model_name='practica',
            constraint=models.CheckConstraint(condition=models.Q(('modo', 'estudio')), name='ck_m08_practica_modo_estudio'),
        ),
        migrations.AddConstraint(
            model_name='practica',
            constraint=models.CheckConstraint(condition=models.Q(('estado__in', ('en_curso', 'terminada'))), name='ck_m08_practica_estado'),
        ),
        migrations.AddConstraint(
            model_name='practica',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('estado', 'terminada'), _negated=True), ('terminada_en__isnull', False), _connector='OR'), name='ck_m08_practica_terminada_fechada'),
        ),
    ]
