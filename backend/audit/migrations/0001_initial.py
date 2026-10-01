"""
MOD-019 · Audit · 0001: la bitácora encadenada (§3.2 y §3.4 del prompt).

1. Crea m19_bitacora, m19_bitacora_tramo, m19_evento_salida y sus índices.
2. Copia cada fila de m19_auditoria por orden (momento, id) asignando secuencia, huella_previa y huella: la cadena
   nace con el historial actual (origen='migracion'). Crea el tramo activo con la cabeza resultante y asienta
   `auditoria.bitacora_abierta` (génesis) si la tabla origen estaba vacía, o `auditoria.cadena_migrada` con el conteo.
3. Deja m19_auditoria como m19_auditoria_legado (sólo lectura por triggers) durante un ciclo de versión, y crea la
   VISTA m19_auditoria sobre m19_bitacora con las columnas viejas, de modo que `expediente.Auditoria` (ya sin
   escritura) siga leyendo lo mismo que antes.
4. Crea los triggers de inmutabilidad de m19_bitacora (§3.3, capa 2).

Reversible sólo hacia adelante.
"""
import logging
import time

import audit.models
import django.db.models.deletion
import django.db.models.expressions
from django.db import migrations, models

from audit.dominio import catalogos, huella
from audit.infraestructura import migracion, triggers

log = logging.getLogger("avacom.instalacion")

GENESIS = huella.GENESIS


def _ahora() -> int:
    return int(time.time() * 1000)


def migrar_datos(apps, schema_editor):
    Bitacora = apps.get_model("audit", "Bitacora")
    Tramo = apps.get_model("audit", "BitacoraTramo")
    conexion = schema_editor.connection
    filas = []
    with conexion.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'm19_auditoria'")
        if cursor.fetchone():
            cursor.execute("SELECT id, actor_id, accion, objeto_tabla, objeto_id, valor_anterior, valor_nuevo, momento "
                           "FROM m19_auditoria ORDER BY momento, id")
            columnas = ("id", "actor_id", "accion", "objeto_tabla", "objeto_id", "valor_anterior", "valor_nuevo", "momento")
            for registro in cursor.fetchall():
                fila = dict(zip(columnas, registro))
                for clave in ("valor_anterior", "valor_nuevo"):
                    fila[clave] = _json(fila[clave])
                filas.append(fila)
    asientos = migracion.encadenar(filas)
    ahora = _ahora()
    tramo = Tramo.objects.create(desde_secuencia=1, hasta_secuencia=0, huella_cierre=GENESIS, estado="activa", creado_en=ahora)
    previa = GENESIS
    ultima = 0
    for a in asientos:
        Bitacora.objects.create(tramo=tramo, **{k: v for k, v in a.items()})
        previa, ultima = a["huella"], a["secuencia"]
    if asientos:
        cierre = {"secuencia": ultima + 1, "ocurrido_en": ahora, "usuario_id": None, "actor_tipo": "sistema", "roles_activos": None,
                  "modulo": catalogos.M_AUDITORIA, "accion": "auditoria.cadena_migrada", "resultado": "ok", "objeto_tabla": "m19_auditoria",
                  "objeto_id": None, "valor_anterior": None, "valor_nuevo": {"convertidos": len(asientos), "huella_final": previa},
                  "motivo": None, "origen": "migracion", "dispositivo_id": None, "correlacion_id": None, "evento_id": None}
    else:
        cierre = {"secuencia": 1, "ocurrido_en": ahora, "usuario_id": None, "actor_tipo": "sistema", "roles_activos": None,
                  "modulo": catalogos.M_AUDITORIA, "accion": "auditoria.bitacora_abierta", "resultado": "ok", "objeto_tabla": None,
                  "objeto_id": None, "valor_anterior": None, "valor_nuevo": {"version_catalogo": catalogos.VERSION_CATALOGO},
                  "motivo": None, "origen": "migracion", "dispositivo_id": None, "correlacion_id": None, "evento_id": None}
    cierre["huella_previa"] = previa
    cierre["huella"] = huella.calcular(previa, cierre)
    Bitacora.objects.create(tramo=tramo, **cierre)
    Tramo.objects.filter(pk=tramo.pk).update(hasta_secuencia=cierre["secuencia"], huella_cierre=cierre["huella"])
    log.info("Bitácora: %s filas de m19_auditoria convertidas; cabeza en #%s", len(asientos), cierre["secuencia"],
             extra={"evento": "instalacion.bitacora_migrada", "detalle": {"convertidos": len(asientos), "secuencia": cierre["secuencia"],
                                                                          "huella": cierre["huella"]}})


def _json(valor):
    if valor is None or not isinstance(valor, (str, bytes)):
        return valor
    import json
    try:
        return json.loads(valor)
    except (TypeError, ValueError):
        return valor


SQL_LEGADO_Y_VISTA = [
    "ALTER TABLE m19_auditoria RENAME TO m19_auditoria_legado;",
    """CREATE VIEW m19_auditoria AS
  SELECT secuencia AS id,
         COALESCE(usuario_id, actor_tipo) AS actor_id,
         accion,
         COALESCE(objeto_tabla, '') AS objeto_tabla,
         COALESCE(objeto_id, '') AS objeto_id,
         valor_anterior,
         valor_nuevo,
         ocurrido_en AS momento
  FROM m19_bitacora;""",
]


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('device_manager', '0004_perfil_y_dueno_del_equipo'),
        ('acceso', '0007_permisos_estudio'),
        ('expediente', '0003_auditoria_vista'),
    ]

    operations = [
        migrations.CreateModel(
            name='BitacoraTramo',
            fields=[
                ('id', models.CharField(default=audit.models._nuevo_id, max_length=36, primary_key=True, serialize=False)),
                ('desde_secuencia', models.BigIntegerField()),
                ('hasta_secuencia', models.BigIntegerField()),
                ('huella_cierre', models.CharField(max_length=64)),
                ('estado', models.CharField(default='activa', max_length=12)),
                ('abierta', models.BooleanField(default=True)),
                ('verificado_en', models.BigIntegerField(blank=True, null=True)),
                ('verificado_hasta', models.BigIntegerField(blank=True, null=True)),
                ('salto_en_secuencia', models.BigIntegerField(blank=True, null=True)),
                ('salto_causa', models.CharField(blank=True, default='', max_length=32)),
                ('exportado_en', models.BigIntegerField(blank=True, null=True)),
                ('firma', models.TextField(blank=True, null=True)),
                ('archivo', models.CharField(blank=True, max_length=260, null=True)),
                ('rotado_en', models.BigIntegerField(blank=True, null=True)),
                ('creado_en', models.BigIntegerField(default=audit.models.ahora_ms)),
            ],
            options={
                'db_table': 'm19_bitacora_tramo',
                'ordering': ['desde_secuencia'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('abierta', True)), fields=('abierta',), name='uq_m19_tramo_abierto'), models.CheckConstraint(condition=models.Q(('hasta_secuencia__gte', django.db.models.expressions.CombinedExpression(models.F('desde_secuencia'), '-', models.Value(1)))), name='ck_m19_tramo_rango'), models.CheckConstraint(condition=models.Q(('estado__in', ('activa', 'verificada', 'con_salto', 'rotada'))), name='ck_m19_tramo_estado'), models.CheckConstraint(condition=models.Q(('desde_secuencia__gte', 1)), name='ck_m19_tramo_desde')],
            },
        ),
        migrations.CreateModel(
            name='EventoSalida',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agregado_tipo', models.CharField(max_length=32)),
                ('agregado_id', models.CharField(max_length=36)),
                ('tipo_evento', models.CharField(max_length=64)),
                ('carga', models.JSONField(default=dict)),
                ('creado_en', models.BigIntegerField(default=audit.models.ahora_ms)),
                ('publicado_en', models.BigIntegerField(blank=True, null=True)),
                ('intentos', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'db_table': 'm19_evento_salida',
                'indexes': [models.Index(fields=['publicado_en', 'creado_en'], name='ix_m19_outbox')],
            },
        ),
        migrations.CreateModel(
            name='Bitacora',
            fields=[
                ('id', models.CharField(default=audit.models._nuevo_id, max_length=36, primary_key=True, serialize=False)),
                ('secuencia', models.BigIntegerField(unique=True)),
                ('huella_previa', models.CharField(max_length=64)),
                ('huella', models.CharField(max_length=64)),
                ('ocurrido_en', models.BigIntegerField()),
                ('usuario_id', models.CharField(blank=True, max_length=64, null=True)),
                ('actor_tipo', models.CharField(default='sistema', max_length=12)),
                ('roles_activos', models.JSONField(blank=True, null=True)),
                ('modulo', models.CharField(max_length=24)),
                ('accion', models.CharField(max_length=64)),
                ('resultado', models.CharField(default='ok', max_length=16)),
                ('objeto_tabla', models.CharField(blank=True, max_length=64, null=True)),
                ('objeto_id', models.CharField(blank=True, max_length=64, null=True)),
                ('valor_anterior', models.JSONField(blank=True, null=True)),
                ('valor_nuevo', models.JSONField(blank=True, null=True)),
                ('motivo', models.CharField(blank=True, max_length=250, null=True)),
                ('origen', models.CharField(max_length=12)),
                ('correlacion_id', models.CharField(blank=True, max_length=64, null=True)),
                ('evento_id', models.CharField(blank=True, max_length=64, null=True)),
                ('dispositivo', models.ForeignKey(blank=True, db_column='dispositivo_id', null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='asientos_bitacora', to='device_manager.dispositivo')),
                ('tramo', models.ForeignKey(db_column='tramo_id', on_delete=django.db.models.deletion.RESTRICT, related_name='asientos', to='audit.bitacoratramo')),
            ],
            options={
                'db_table': 'm19_bitacora',
                'ordering': ['secuencia'],
                'indexes': [models.Index(fields=['usuario_id', 'ocurrido_en'], name='ix_m19_bit_usuario'), models.Index(fields=['modulo', 'ocurrido_en'], name='ix_m19_bit_modulo'), models.Index(fields=['resultado', 'ocurrido_en'], name='ix_m19_bit_resultado'), models.Index(fields=['objeto_tabla', 'objeto_id', 'ocurrido_en'], name='ix_m19_bit_objeto'), models.Index(fields=['accion', 'ocurrido_en'], name='ix_m19_bit_accion'), models.Index(fields=['dispositivo', 'ocurrido_en'], name='ix_m19_bit_dispositivo'), models.Index(fields=['correlacion_id'], name='ix_m19_bit_corr')],
                'constraints': [models.CheckConstraint(condition=models.Q(('resultado__in', ('ok', 'denegado', 'fallido'))), name='ck_m19_bit_resultado'), models.CheckConstraint(condition=models.Q(('origen__in', ('api', 'ws', 'sistema', 'instalador', 'migracion', 'prueba'))), name='ck_m19_bit_origen'), models.CheckConstraint(condition=models.Q(('actor_tipo__in', ('usuario', 'declarado', 'sistema', 'dispositivo', 'instalador'))), name='ck_m19_bit_actor_tipo'), models.CheckConstraint(condition=models.Q(models.Q(('actor_tipo', 'usuario'), _negated=True), ('usuario_id__isnull', False), _connector='OR'), name='ck_m19_bit_usuario_con_id'), models.CheckConstraint(condition=models.Q(('secuencia__gte', 1)), name='ck_m19_bit_secuencia')],
            },
        ),
        migrations.RunPython(migrar_datos, migrations.RunPython.noop),
        migrations.RunSQL(SQL_LEGADO_Y_VISTA, migrations.RunSQL.noop),
        migrations.RunSQL(triggers.sentencias(triggers.SQL_CREAR_LEGADO), migrations.RunSQL.noop),
        migrations.RunSQL(triggers.sentencias(triggers.SQL_CREAR), migrations.RunSQL.noop),
    ]
