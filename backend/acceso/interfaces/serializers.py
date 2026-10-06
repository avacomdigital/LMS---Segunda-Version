"""
Serializers de entrada: validan la FORMA del JSON (tipos, campos obligatorios,
longitudes). Las reglas de negocio (fortaleza, alcances, jerarquía) viven en el
dominio y no se repiten aquí. No hay ModelSerializer: el ORM no sale de la
infraestructura.
"""
from __future__ import annotations

from rest_framework import serializers

ALCANCES = ["SELF", "ASSIGNED_GROUPS", "LEVEL", "ORGANIZATION"]
ALCANCES_ASIGNACION = ["ORGANIZATION", "LEVEL", "ASSIGNED_GROUPS"]
NIVELES = ["preescolar", "primaria", "secundaria", "bachillerato", "preuniversitario"]
TIPOS_IDENTIFICADOR = ["DNI", "CODIGO_ESTUDIANTIL", "CLAVE_INSTALACION", "EMAIL"]
TIPOS_SECRETO = ["PIN", "PASSWORD", "AVATAR"]
PERFILES = ["student", "teacher", "admin", "reports", "technician"]


class OrganizacionEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=32)
    nombre = serializers.CharField(max_length=200)
    pais = serializers.CharField(max_length=2, required=False, default="CO")
    idioma = serializers.CharField(max_length=8, required=False, default="es")
    locale = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    zona_horaria = serializers.CharField(max_length=64, required=False, default="America/Bogota")


class AdministradorEntrada(serializers.Serializer):
    alias = serializers.CharField(max_length=64, required=False, default="Administración")
    nombres = serializers.CharField(max_length=120)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    dni = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", trim_whitespace=False)


class InstalacionEntrada(serializers.Serializer):
    organizacion = OrganizacionEntrada()
    administrador = AdministradorEntrada()
    # RN-03: sin PIN maestro no se instala. La forma (seis dígitos, nada trivial) la valida el dominio, con el mensaje que explica la regla.
    pin_maestro = serializers.CharField(max_length=32, trim_whitespace=False)


class LoginEntrada(serializers.Serializer):
    """Tres formas de identificarse: documento o código + clave; o (alumnos) `usuario_id` + PIN, tocando el nombre en la lista (RB-22).
    La administración añade el PIN maestro (`pin_maestro`) cuando el nodo lo exige."""

    identificador = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    usuario_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
    secreto = serializers.CharField(max_length=128, trim_whitespace=False)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    # BR-021: si la persona tiene varios roles, elige con cuál trabaja en esta sesión.
    rol = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    pin_maestro = serializers.CharField(max_length=32, required=False, allow_blank=True, default="", trim_whitespace=False)

    def validate(self, datos):
        if not datos.get("identificador") and not datos.get("usuario_id"):
            raise serializers.ValidationError("Envíe el identificador o el usuario_id.")
        return datos


class TraspasoEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=2048, trim_whitespace=True)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class CanjeEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    grant_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
    token = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")

    def validate(self, datos):
        if not datos.get("codigo") and not (datos.get("grant_id") and datos.get("token")):
            raise serializers.ValidationError("Envíe un código, o bien grant_id y token.")
        return datos


class CambioCredencialEntrada(serializers.Serializer):
    secreto_actual = serializers.CharField(max_length=128, trim_whitespace=False)
    secreto_nuevo = serializers.CharField(max_length=128, trim_whitespace=False)


class PersonaEntrada(serializers.Serializer):
    nombres = serializers.CharField(max_length=120, required=False)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True)
    pais = serializers.CharField(max_length=2, required=False)
    fecha_nacimiento = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    telefono = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)


class IdentificadorEntrada(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TIPOS_IDENTIFICADOR)
    valor = serializers.CharField(max_length=128)
    es_login = serializers.BooleanField(required=False, default=True)
    emisor = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    principal = serializers.BooleanField(required=False, default=False)


class UsuarioEntrada(serializers.Serializer):
    rol = serializers.CharField(max_length=32)
    alias = serializers.CharField(max_length=64)
    idioma = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    persona = PersonaEntrada(required=False, default=dict)
    # Puede omitirse: el nodo emite una CLAVE_INSTALACION (DEC-049). Obligatorio salvo admisión nominal.
    identificadores = IdentificadorEntrada(many=True, required=False, default=list)
    secreto = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", trim_whitespace=False)
    secreto_definitivo = serializers.BooleanField(required=False, default=False)
    grupo_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
    # Admisión nominal (JRN-007): el profesor deja entrar «por su nombre» y vincula después.
    provisional = serializers.BooleanField(required=False, default=False)
    # RN-35: el alumno nace sin PIN y lo elige él al tocar su nombre (nadie imprime ni dicta un número).
    pin_pendiente = serializers.BooleanField(required=False, default=False)

    def validate(self, datos):
        if not datos.get("provisional") and not datos.get("persona", {}).get("nombres"):
            raise serializers.ValidationError({"persona": "Faltan los nombres."})
        return datos


class ImportacionEntrada(serializers.Serializer):
    """FUN-003: o bien el texto del archivo delimitado en `contenido`, o bien las filas ya parseadas."""

    contenido = serializers.CharField(required=False, allow_blank=True, default="", trim_whitespace=False)
    filas = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    delimitador = serializers.CharField(max_length=1, required=False, default=",")
    grupo_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")

    def validate(self, datos):
        if not datos.get("contenido") and not datos.get("filas"):
            raise serializers.ValidationError("Envíe el contenido del archivo o la lista de filas.")
        return datos


class VinculacionEntrada(serializers.Serializer):
    usuario_definitivo_id = serializers.CharField(max_length=36)


class UsuarioCambios(serializers.Serializer):
    alias = serializers.CharField(max_length=64, required=False)
    idioma = serializers.CharField(max_length=8, required=False)
    estado = serializers.ChoiceField(choices=["ACTIVO", "SUSPENDIDO", "RETIRADO"], required=False)
    persona = PersonaEntrada(required=False)
    identificadores = IdentificadorEntrada(many=True, required=False)


class RolAsignacion(serializers.Serializer):
    """FUN-002: asignar un rol con alcance concreto y vigencia (m01_persona_rol)."""

    rol = serializers.CharField(max_length=32)
    alcance_tipo = serializers.ChoiceField(choices=ALCANCES_ASIGNACION, required=False, default="ORGANIZATION")
    alcance_id = serializers.CharField(max_length=36, required=False, allow_blank=True, allow_null=True, default=None)
    vigente_hasta = serializers.IntegerField(required=False, allow_null=True, default=None)
    principal = serializers.BooleanField(required=False, default=False)


class EscaladaEntrada(serializers.Serializer):
    """BR-101: escalada temporal. La caducidad es obligatoria; el motivo también."""

    permiso = serializers.CharField(max_length=64)
    alcance = serializers.ChoiceField(choices=ALCANCES)
    motivo = serializers.CharField(max_length=200)
    vigente_hasta = serializers.IntegerField()


class RestablecerEntrada(serializers.Serializer):
    secreto = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", trim_whitespace=False)


class AutorizacionEntrada(serializers.Serializer):
    usuario_id = serializers.CharField(max_length=36)
    tipo = serializers.ChoiceField(choices=["DISPOSITIVO", "CODIGO"])
    dispositivo_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
    evaluacion_ref = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    minutos = serializers.IntegerField(required=False, min_value=1, max_value=30, default=5)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class PermisoRolEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=64)
    alcance = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, default=None)


class RolEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=32)
    nombre = serializers.CharField(max_length=80)
    plantilla = serializers.CharField(max_length=32, required=False, default="TEACHER")
    menu_principal = serializers.ChoiceField(choices=PERFILES, required=False)
    nivel = serializers.IntegerField(required=False, min_value=1, max_value=3)
    permisos = PermisoRolEntrada(many=True, required=False, default=list)


class PoliticaCambios(serializers.Serializer):
    tipo_identificador = serializers.ChoiceField(choices=TIPOS_IDENTIFICADOR + ["CUALQUIERA"], required=False)
    tipo_secreto = serializers.ChoiceField(choices=TIPOS_SECRETO, required=False)
    longitud_minima = serializers.IntegerField(required=False, min_value=1, max_value=64)
    exige_mayuscula = serializers.BooleanField(required=False)
    exige_minuscula = serializers.BooleanField(required=False)
    exige_digito = serializers.BooleanField(required=False)
    exige_simbolo = serializers.BooleanField(required=False)
    intentos_maximos = serializers.IntegerField(required=False, min_value=3, max_value=20)
    ventana_intentos_min = serializers.IntegerField(required=False, min_value=1, max_value=1440)
    bloqueo_minutos = serializers.IntegerField(required=False, min_value=1, max_value=1440)
    duracion_sesion_min = serializers.IntegerField(required=False, min_value=5, max_value=1440)
    inactividad_min = serializers.IntegerField(required=False, min_value=5, max_value=1440)
    vigencia_credencial_dias = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    permite_acceso_temporal = serializers.BooleanField(required=False)
    # RB-27: registro propio (RN-37), castigo a la cuenta o a la tableta (RN-33) y el interruptor institucional de visitantes (RN-47).
    autoregistro = serializers.BooleanField(required=False)
    bloqueo_alcance = serializers.ChoiceField(choices=["CUENTA", "DISPOSITIVO"], required=False)
    visitante = serializers.BooleanField(required=False)


class GrupoEntrada(serializers.Serializer):
    codigo = serializers.CharField(max_length=32)
    nombre = serializers.CharField(max_length=120)
    periodo = serializers.CharField(max_length=16)
    nivel_clave = serializers.ChoiceField(choices=NIVELES, required=False, allow_null=True, allow_blank=True, default=None)
    politica_credencial_id = serializers.CharField(max_length=36, required=False, allow_blank=True, allow_null=True, default=None)


class GrupoCambios(serializers.Serializer):
    nombre = serializers.CharField(max_length=120, required=False)
    activo = serializers.BooleanField(required=False)
    nivel_clave = serializers.ChoiceField(choices=NIVELES, required=False, allow_null=True, allow_blank=True)
    politica_credencial_id = serializers.CharField(max_length=36, required=False, allow_blank=True, allow_null=True)


class MiembroEntrada(serializers.Serializer):
    usuario_id = serializers.CharField(max_length=36)
    papel = serializers.ChoiceField(choices=["ESTUDIANTE", "DOCENTE"], required=False, default="ESTUDIANTE")


class GrupoPadronEntrada(serializers.Serializer):
    """Pantalla «Grupos» de OPS: lo mínimo para crear un grupo. El código sale del nombre y el periodo es el año si no se dan."""

    nombre = serializers.CharField(max_length=120)
    codigo = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    periodo = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    nivel_clave = serializers.ChoiceField(choices=NIVELES, required=False, allow_null=True, allow_blank=True, default=None)


class EstudiantePadronEntrada(serializers.Serializer):
    """Registrar a un estudiante con su grupo. `documento` y `pin` son opcionales: el nodo emite la clave y genera el PIN."""

    nombres = serializers.CharField(max_length=120)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    documento = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    pin = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", trim_whitespace=False)
    grupo_id = serializers.CharField(max_length=36)


class MatriculaEntrada(serializers.Serializer):
    usuario_id = serializers.CharField(max_length=36)


# ----------------------------------------------------- PIN maestro, profesores y alumnos (requisitos de acceso 2026-10-05)


class PinMaestroCambioEntrada(serializers.Serializer):
    pin_nuevo = serializers.CharField(max_length=32, trim_whitespace=False)


class DocenteRegistroEntrada(serializers.Serializer):
    """RB-13: la autorización la da el PIN maestro, no una sesión."""

    pin_maestro = serializers.CharField(max_length=32, trim_whitespace=False)
    documento = serializers.CharField(max_length=64)
    nombres = serializers.CharField(max_length=120)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    secreto = serializers.CharField(max_length=128, trim_whitespace=False)
    grupos = serializers.ListField(child=serializers.CharField(max_length=36), required=False, default=list, max_length=50)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class DocenteRestablecerEntrada(serializers.Serializer):
    pin_maestro = serializers.CharField(max_length=32, trim_whitespace=False)
    documento = serializers.CharField(max_length=64)
    secreto_nuevo = serializers.CharField(max_length=128, trim_whitespace=False)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class EstudianteRegistroEntrada(serializers.Serializer):
    """RB-17: el alumno se crea solo con grupo, nombre y PIN."""

    grupo_id = serializers.CharField(max_length=36)
    nombres = serializers.CharField(max_length=120)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    alias = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    pin = serializers.CharField(max_length=128, trim_whitespace=False)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class EstudiantePinEntrada(serializers.Serializer):
    pin = serializers.CharField(max_length=128, trim_whitespace=False)
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class VisitanteEntrada(serializers.Serializer):
    dispositivo = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    grupo_id = serializers.CharField(max_length=36, required=False, allow_blank=True, default="")
