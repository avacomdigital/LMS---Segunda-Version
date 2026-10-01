"""
El asiento de la bitácora (019-01, FUN-195, BR-099, TST-071): quién (actor y roles activos), qué (acción del
catálogo), sobre qué (tabla y objeto), con qué resultado, con qué valores (sólo los campos que cambian), por qué
(motivo), desde dónde (origen y dispositivo) y con qué correlación. Sin Django: lo usa la migración de datos, el
anexador y las pruebas de cadena.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import catalogos, errores, huella

ACTOR_USUARIO = "usuario"          # una sesión de MOD-001 firma la operación
ACTOR_DECLARADO = "declarado"      # el cliente declaró quién es sin sesión (Q-34): el asiento no prueba su identidad
ACTOR_SISTEMA = "sistema"          # el programador del nodo o un caso de uso sin persona
ACTOR_DISPOSITIVO = "dispositivo"  # la tableta actúa por sí misma (registro, latido)
ACTOR_INSTALADOR = "instalador"
ACTORES = (ACTOR_USUARIO, ACTOR_DECLARADO, ACTOR_SISTEMA, ACTOR_DISPOSITIVO, ACTOR_INSTALADOR)

RESULTADO_OK, RESULTADO_DENEGADO, RESULTADO_FALLIDO = "ok", "denegado", "fallido"
RESULTADOS = (RESULTADO_OK, RESULTADO_DENEGADO, RESULTADO_FALLIDO)

ORIGENES = ("api", "ws", "sistema", "instalador", "migracion", "prueba")

MAX_MOTIVO = 250
MAX_OBJETO = 64


@dataclass
class Asiento:
    secuencia: int
    ocurrido_en: int
    accion: str
    modulo: str
    actor_tipo: str = ACTOR_SISTEMA
    usuario_id: str | None = None
    roles_activos: list[str] | None = None
    resultado: str = RESULTADO_OK
    objeto_tabla: str | None = None
    objeto_id: str | None = None
    valor_anterior: dict | list | None = None
    valor_nuevo: dict | list | None = None
    motivo: str | None = None
    origen: str = "sistema"
    dispositivo_id: str | None = None
    correlacion_id: str | None = None
    evento_id: str | None = None
    huella_previa: str = huella.GENESIS
    huella: str = field(default="")

    def canonico(self) -> dict:
        return {campo: getattr(self, campo) for campo in huella.CAMPOS_CANONICOS}

    def sellar(self, huella_previa: str) -> "Asiento":
        self.huella_previa = huella_previa
        self.huella = huella.calcular(huella_previa, self.canonico())
        return self

    def validar(self) -> None:
        if self.secuencia < 1:
            raise errores.DatosInvalidos("La secuencia empieza en 1.")
        if self.actor_tipo not in ACTORES:
            raise errores.DatosInvalidos(f"Tipo de actor desconocido: {self.actor_tipo}")
        if self.actor_tipo == ACTOR_USUARIO and not self.usuario_id:
            raise errores.DatosInvalidos("Un actor de tipo usuario exige usuario_id.")
        if self.resultado not in RESULTADOS:
            raise errores.DatosInvalidos(f"Resultado desconocido: {self.resultado}")
        if self.origen not in ORIGENES:
            raise errores.DatosInvalidos(f"Origen desconocido: {self.origen}")
        if self.modulo not in catalogos.MODULOS:
            raise errores.DatosInvalidos(f"Módulo desconocido: {self.modulo}")
        if self.motivo is not None and len(self.motivo) > MAX_MOTIVO:
            raise errores.DatosInvalidos(f"El motivo no puede superar {MAX_MOTIVO} caracteres.")

    def como_dict(self) -> dict:
        return asdict(self)


def preparar(accion: str, *, estricta: bool, motivo: str | None) -> tuple[str, catalogos.Accion | None, dict | None]:
    """Resuelve la acción contra el catálogo. Devuelve (accion efectiva, definición, valor extra si fue desconocida).

    Fuera del catálogo: en modo estricto (pruebas) falla; si no, se asienta `auditoria.accion_desconocida` con la clave
    original en `valor_nuevo`, porque perder el hecho es peor que registrarlo con otra etiqueta (§3.5)."""
    definicion = catalogos.resolver(accion)
    if definicion is None:
        if estricta:
            raise errores.AccionDesconocida(f"La acción «{accion}» no está en el catálogo (versión {catalogos.VERSION_CATALOGO}).", accion=accion)
        return "auditoria.accion_desconocida", catalogos.ACCIONES["auditoria.accion_desconocida"], {"accion_original": accion}
    if definicion.exige_motivo and not (motivo or "").strip():
        raise errores.MotivoRequerido(f"La acción «{accion}» exige un motivo.", accion=accion)
    return accion, definicion, None


def recortar_objeto(valor) -> str | None:
    if valor is None or valor == "":
        return None
    return str(valor)[:MAX_OBJETO]
