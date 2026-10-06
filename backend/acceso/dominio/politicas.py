"""
Policy Pattern: las reglas de autorización, fortaleza de secretos y bloqueo por
intentos viven aquí, separadas de vistas, serializers y ORM. Se prueban con
datos en memoria.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import errores, plantillas
from .entidades import Concesion, IntentoAcceso, PoliticaCredencial, Principal, Rol, UsuarioPermiso
from .valores import Alcance, Avatar, BloqueoAlcance, ClaseSesion, Menu, Password, Pin, ResultadoIntento, TipoSecreto

# ------------------------------------------------------------------ objetivos


@dataclass(frozen=True)
class ObjetivoUsuario:
    usuario_id: str
    organizacion_id: str
    nivel: int


@dataclass(frozen=True)
class ObjetivoGrupo:
    grupo_id: str
    organizacion_id: str


@dataclass(frozen=True)
class ObjetivoOrganizacion:
    organizacion_id: str


@dataclass(frozen=True)
class SinObjetivo:
    """Operación sin objeto concreto (listar dispositivos, leer catálogos): basta tener el permiso."""


Objetivo = ObjetivoUsuario | ObjetivoGrupo | ObjetivoOrganizacion | SinObjetivo


@dataclass(frozen=True)
class Decision:
    permitido: bool
    permiso: str
    codigo: str = "ok"
    alcance_requerido: Alcance | None = None
    alcance_concedido: Alcance | None = None

    def exigir(self, ocultar_existencia: bool = False) -> "Decision":
        """Lanza el error de dominio correspondiente si la decisión es negativa."""
        if self.permitido:
            return self
        extra = {
            "permiso": self.permiso,
            "alcance_requerido": self.alcance_requerido.value if self.alcance_requerido else None,
            "alcance_concedido": self.alcance_concedido.value if self.alcance_concedido else None,
        }
        if self.codigo == "debe_cambiar_credencial":
            raise errores.DebeCambiarCredencial(**extra)
        if self.codigo == "sesion_temporal_limitada":
            raise errores.SesionTemporalLimitada(**extra)
        if self.codigo == "sesion_visitante_limitada":
            raise errores.SesionVisitanteLimitada(**extra)
        # Regla de alcance del Documento Maestro: «cualquier objeto fuera de esa unión se evalúa como
        # acceso denegado, nunca como objeto inexistente, para no revelar por omisión». Por eso fuera de
        # alcance es siempre 403; el 404 queda reservado para lo que de verdad no existe.
        # `ocultar_existencia` se conserva por compatibilidad de firma y ya no cambia la respuesta.
        raise errores.SinPermiso(**extra)


@dataclass
class ContextoActor:
    """Todo lo que la política necesita saber del actor; lo carga el caso de uso una sola vez.

    `grupos_docente` es la unión que el Documento Maestro llama «propio» para un profesor: los grupos
    donde es docente vigente MÁS los que le abre la asignación de su rol efectivo (un grupo concreto
    o todos los de un nivel educativo). `tope` es el alcance de esa asignación (BR-021): acota al del
    rol. Un rol que dice ORGANIZATION asignado con alcance LEVEL llega sólo hasta LEVEL.
    """

    principal: Principal
    concesiones: dict[str, Concesion]
    grupos_docente: frozenset[str] = field(default_factory=frozenset)  # grupos donde es DOCENTE vigente o que le abre su asignación
    grupos_miembro: frozenset[str] = field(default_factory=frozenset)  # grupos donde es miembro vigente (cualquier papel)
    tope: Alcance = Alcance.ORGANIZATION                                # alcance de la asignación del rol efectivo


# ---------------------------------------------------------------- autorización


class PoliticaAutorizacion:
    """RBAC + alcance + contexto. Denegar por defecto."""

    @staticmethod
    def concesiones_efectivas(rol: Rol, adicionales: list[UsuarioPermiso], ahora: int) -> dict[str, Concesion]:
        salida: dict[str, Concesion] = {}
        for rp in rol.permisos:
            salida[rp.permiso_codigo] = Concesion(rp.permiso_codigo, rp.alcance, "rol")
        for extra in adicionales:
            if not extra.vigente(ahora):
                continue
            actual = salida.get(extra.permiso_codigo)
            if actual is None or extra.alcance.orden > actual.alcance.orden:
                salida[extra.permiso_codigo] = Concesion(extra.permiso_codigo, extra.alcance, "adicional", extra.vigente_hasta)
        return salida

    @staticmethod
    def alcance_requerido(ctx: ContextoActor, objetivo: Objetivo, grupos_objetivo: frozenset[str]) -> Alcance | None:
        """El alcance mínimo con el que el actor alcanza al objetivo; None si no está en su organización."""
        actor = ctx.principal
        if isinstance(objetivo, SinObjetivo):
            return Alcance.SELF
        if objetivo.organizacion_id != actor.organizacion_id:
            return None
        if isinstance(objetivo, ObjetivoOrganizacion):
            return Alcance.ORGANIZATION
        if isinstance(objetivo, ObjetivoUsuario):
            if objetivo.usuario_id == actor.usuario_id:
                return Alcance.SELF
            if objetivo.nivel == 1 and ctx.grupos_docente & grupos_objetivo:
                return Alcance.ASSIGNED_GROUPS
            return Alcance.ORGANIZATION
        # grupo
        if objetivo.grupo_id in ctx.grupos_docente:
            return Alcance.ASSIGNED_GROUPS
        if objetivo.grupo_id in ctx.grupos_miembro:
            return Alcance.SELF
        return Alcance.ORGANIZATION

    def transversal(self, ctx: ContextoActor, permiso: str) -> Decision | None:
        """Reglas previas a cualquier permiso: credencial provisional y sesión temporal."""
        actor = ctx.principal
        if actor.debe_cambiar_credencial and permiso not in plantillas.PERMISOS_CON_CREDENCIAL_PROVISIONAL:
            return Decision(False, permiso, "debe_cambiar_credencial")
        if actor.clase_sesion is ClaseSesion.TEMPORAL and permiso not in plantillas.PERMISOS_SESION_TEMPORAL:
            return Decision(False, permiso, "sesion_temporal_limitada")
        if actor.clase_sesion is ClaseSesion.VISITANTE and permiso not in plantillas.PERMISOS_SESION_VISITANTE:
            return Decision(False, permiso, "sesion_visitante_limitada")
        return None

    def alcance_concedido(self, ctx: ContextoActor, permiso: str) -> Alcance | None:
        """El alcance efectivo con el que el actor tiene el permiso, tras las reglas transversales.

        Es el mínimo entre lo que dice el rol y lo que dice la asignación del rol (`tope`).
        LEVEL sólo tiene sentido cuando la asignación fija un nivel; si el rol dice LEVEL y la
        asignación es de toda la organización, se resuelve como «sus grupos».
        """
        if self.transversal(ctx, permiso) is not None:
            return None
        concesion = ctx.concesiones.get(permiso)
        if concesion is None:
            return None
        if ctx.principal.clase_sesion in (ClaseSesion.TEMPORAL, ClaseSesion.VISITANTE):
            return Alcance.SELF
        efectivo = Alcance.minimo(concesion.alcance, ctx.tope)
        if efectivo is Alcance.LEVEL and ctx.tope is not Alcance.LEVEL:
            efectivo = Alcance.ASSIGNED_GROUPS
        return efectivo

    def decidir(self, ctx: ContextoActor, permiso: str, objetivo: Objetivo,
                grupos_objetivo: frozenset[str] = frozenset()) -> Decision:
        previa = self.transversal(ctx, permiso)
        if previa is not None:
            return previa
        requerido = self.alcance_requerido(ctx, objetivo, grupos_objetivo)
        if requerido is None:
            return Decision(False, permiso, "fuera_de_organizacion")
        concedido = self.alcance_concedido(ctx, permiso)
        if concedido is None:
            return Decision(False, permiso, "sin_permiso", requerido, None)
        if not concedido.cubre(requerido):
            return Decision(False, permiso, "sin_permiso", requerido, concedido)
        if isinstance(objetivo, ObjetivoUsuario) and requerido is not Alcance.SELF:
            # Jerarquía: con alcance de grupos sólo se administran estudiantes; con alcance de
            # organización, nunca a alguien de nivel superior al propio.
            if requerido is Alcance.ASSIGNED_GROUPS and objetivo.nivel != 1:
                return Decision(False, permiso, "sin_permiso", Alcance.ORGANIZATION, concedido)
            if ctx.principal.nivel < objetivo.nivel:
                return Decision(False, permiso, "sin_permiso", requerido, concedido)
        return Decision(True, permiso, "ok", requerido, concedido)

    @staticmethod
    def alcance_otorgable(permiso_maximo: Alcance, alcance_pedido: Alcance, alcance_del_actor: Alcance | None) -> Alcance:
        """Un actor no puede otorgar más alcance del que él mismo tiene ni más que el techo del permiso."""
        if alcance_pedido.orden > permiso_maximo.orden:
            raise errores.DatosInvalidos(
                f"El permiso admite como máximo el alcance {permiso_maximo.value}.")
        if alcance_del_actor is None or alcance_pedido.orden > alcance_del_actor.orden:
            raise errores.SinPermiso("No puede otorgar un alcance mayor del que usted tiene sobre ese permiso.")
        return alcance_pedido


# ------------------------------------------------------------------ fortaleza


class PoliticaFortaleza:
    """Valida un secreto contra la política de credenciales vigente para el usuario."""

    @staticmethod
    def validar(secreto: str, politica: PoliticaCredencial) -> list[str]:
        reglas: list[str] = []
        if politica.tipo_secreto is TipoSecreto.AVATAR:
            try:
                Avatar(secreto)
            except ValueError as error:
                return [str(error)]
            return reglas
        if politica.tipo_secreto is TipoSecreto.PIN:
            try:
                pin = Pin(secreto)
            except ValueError as error:
                return [str(error)]
            # RN-31: el PIN del alumno es de 4 a 6 dígitos y SIN reglas de complejidad (`1234` vale): reconoce, no protege.
            es_alumno = politica.perfil is Menu.STUDENT
            maximo = 6 if es_alumno else 8
            if len(pin.valor) < politica.longitud_minima:
                reglas.append(f"El PIN debe tener al menos {politica.longitud_minima} dígitos.")
            if len(pin.valor) > maximo:
                reglas.append(f"El PIN no puede tener más de {maximo} dígitos.")
            if not es_alumno and pin.es_trivial():
                reglas.append("El PIN es demasiado fácil de adivinar (repetido o en secuencia).")
            return reglas
        try:
            clave = Password(secreto)
        except ValueError as error:
            return [str(error)]
        if len(clave.valor) < politica.longitud_minima:
            reglas.append(f"La contraseña debe tener al menos {politica.longitud_minima} caracteres.")
        if politica.exige_mayuscula and not clave.tiene_mayuscula:
            reglas.append("Debe incluir al menos una letra mayúscula.")
        if politica.exige_minuscula and not clave.tiene_minuscula:
            reglas.append("Debe incluir al menos una letra minúscula.")
        if politica.exige_digito and not clave.tiene_digito:
            reglas.append("Debe incluir al menos un dígito.")
        if politica.exige_simbolo and not clave.tiene_simbolo:
            reglas.append("Debe incluir al menos un símbolo (p. ej. . , ! # $ %).")
        return reglas

    @classmethod
    def exigir(cls, secreto: str, politica: PoliticaCredencial) -> None:
        reglas = cls.validar(secreto, politica)
        if reglas:
            raise errores.SecretoDebil("La clave no cumple la política del colegio.", reglas=reglas)


# -------------------------------------------------------------------- bloqueo


@dataclass(frozen=True)
class EstadoBloqueo:
    bloqueado: bool
    fallos: int
    hasta: int | None = None

    def segundos_restantes(self, ahora: int) -> int:
        if not self.bloqueado or self.hasta is None:
            return 0
        return max(0, (self.hasta - ahora + 999) // 1000)


class PoliticaBloqueo:
    """Bloqueo automático calculado sobre el registro de intentos, sin contador desnormalizado."""

    @staticmethod
    def evaluar(intentos_desc: list[IntentoAcceso], politica: PoliticaCredencial, ahora: int) -> EstadoBloqueo:
        ventana_ms = max(politica.ventana_intentos_min, politica.bloqueo_minutos) * 60_000
        fallos = 0
        ultimo_fallo: int | None = None
        for intento in intentos_desc:  # del más reciente al más antiguo
            if intento.resultado in (ResultadoIntento.EXITO, ResultadoIntento.DESBLOQUEO):
                break
            if intento.momento < ahora - ventana_ms:
                break
            if intento.resultado is ResultadoIntento.FALLO:
                fallos += 1
                if ultimo_fallo is None:
                    ultimo_fallo = intento.momento
        if fallos >= politica.intentos_maximos and ultimo_fallo is not None:
            hasta = ultimo_fallo + politica.bloqueo_minutos * 60_000
            if ahora < hasta:
                return EstadoBloqueo(True, fallos, hasta)
        return EstadoBloqueo(False, fallos, None)


    @staticmethod
    def evaluar_dispositivo(intentos_desc: list[IntentoAcceso], politica: PoliticaCredencial, ahora: int) -> EstadoBloqueo:
        """RN-33: el castigo por equivocarse recae en la TABLETA, no en la cuenta (así un compañero no puede bloquear a otro a propósito).

        Cuenta los fallos de PIN hechos desde la tableta, de cualquier alumno, dentro de la ventana de la política; al llegar al máximo la
        tableta espera `MINUTOS_PAUSA_DISPOSITIVO` minutos para probar un PIN. Un acierto desde la tableta borra la cuenta. Entrar como
        visitante no pasa por aquí: nunca se bloquea."""
        ventana_ms = politica.ventana_intentos_min * 60_000
        pausa_ms = plantillas.MINUTOS_PAUSA_DISPOSITIVO * 60_000
        fallos = 0
        ultimo_fallo: int | None = None
        for intento in intentos_desc:
            if intento.resultado in (ResultadoIntento.EXITO, ResultadoIntento.DESBLOQUEO):
                break
            if intento.momento < ahora - max(ventana_ms, pausa_ms):
                break
            if intento.resultado is ResultadoIntento.FALLO and intento.momento >= ahora - ventana_ms:
                fallos += 1
                if ultimo_fallo is None:
                    ultimo_fallo = intento.momento
        if fallos >= politica.intentos_maximos and ultimo_fallo is not None:
            hasta = ultimo_fallo + pausa_ms
            if ahora < hasta:
                return EstadoBloqueo(True, fallos, hasta)
        return EstadoBloqueo(False, fallos, None)


@dataclass(frozen=True)
class EstadoBloqueoPinMaestro:
    bloqueado: bool
    fallos: int                    # fallos acumulados en la ventana actual (aún sin bloqueo)
    hasta: int | None = None
    episodios: int = 0             # bloqueos seguidos, sin ningún acierto entre medias
    global_: bool = False          # el tope de todo el nodo, no el de este equipo

    def segundos_restantes(self, ahora: int) -> int:
        if not self.bloqueado or self.hasta is None:
            return 0
        return max(0, (self.hasta - ahora + 999) // 1000)


class PoliticaPinMaestro:
    """Las reglas del PIN maestro (D-A5), sin I/O: formato, trivialidad, vigencia anual y bloqueo contra la adivinación.

    Un millón de combinaciones es poco: por eso el PIN no se puede probar sin límite (RN-10) y no existe un endpoint que sólo diga
    «sí/no» (D-A6): se verifica DENTRO de la operación que autoriza.
    """

    LONGITUD = 6
    VIGENCIA_DIAS = 365           # RN-07: no es configurable; nadie la alarga ni la apaga
    AVISO_DIAS = 30               # RN-08
    INTENTOS_POR_EQUIPO = 5       # RN-10
    VENTANA_MIN = 15
    BLOQUEO_MIN = 15
    BLOQUEO_ESCALADO_MIN = 60     # tras tres bloqueos seguidos
    BLOQUEOS_PARA_ESCALAR = 3
    TOPE_GLOBAL_POR_HORA = 20
    ULTIMOS_NO_REUTILIZABLES = 3  # RN-05
    MINUTO = 60_000
    DIA = 24 * 60 * MINUTO

    @classmethod
    def validar_formato(cls, valor) -> str:
        """RN-02: exactamente seis dígitos. Devuelve el PIN normalizado."""
        texto = str(valor or "").strip()
        if len(texto) != cls.LONGITUD or not texto.isdigit() or not texto.isascii():
            raise errores.PinInvalido("El PIN maestro son exactamente seis dígitos, sin letras ni espacios.")
        return texto

    @staticmethod
    def es_trivial(valor: str) -> bool:
        """RN-05: seis iguales (`111111`), secuencias (`123456`, `654321`), parejas repetidas (`121212`) y tríos repetidos (`123123`)."""
        if len(set(valor)) == 1:
            return True
        pasos = [int(valor[i + 1]) - int(valor[i]) for i in range(len(valor) - 1)]
        if all(p == 1 for p in pasos) or all(p == -1 for p in pasos):
            return True
        return valor == valor[:2] * 3 or valor == valor[:3] * 2

    @classmethod
    def exigir_fuerte(cls, valor) -> str:
        pin = cls.validar_formato(valor)
        if cls.es_trivial(pin):
            raise errores.PinDebil("Ese PIN es demasiado fácil de adivinar: evita números repetidos, secuencias como 123456 y parejas repetidas.")
        return pin

    @classmethod
    def vence_en(cls, creado_en: int) -> int:
        return creado_en + cls.VIGENCIA_DIAS * cls.DIA

    @staticmethod
    def esta_vencido(vence_en: int, ahora: int) -> bool:
        return ahora >= vence_en

    @classmethod
    def dias_restantes(cls, vence_en: int, ahora: int) -> int:
        """Días que faltan, redondeando hacia arriba (con 30 días y una hora quedan 31) y sin bajar de cero."""
        return max(0, -((ahora - vence_en) // cls.DIA))

    @classmethod
    def en_aviso(cls, vence_en: int, ahora: int) -> bool:
        """RN-08: a 30 días o menos del vencimiento el administrador y el técnico ven el aviso; el profesorado, nada."""
        return cls.dias_restantes(vence_en, ahora) <= cls.AVISO_DIAS

    @classmethod
    def evaluar_bloqueo_equipo(cls, intentos_desc: list[IntentoAcceso], ahora: int) -> EstadoBloqueoPinMaestro:
        """RN-10: 5 fallos en 15 min desde un mismo equipo lo bloquean 15 min; tras tres bloqueos seguidos (sin aciertos entre ellos) el bloqueo
        sube a 60 min. Se calcula repasando el registro de intentos del equipo, del más antiguo al más nuevo: sin contadores que se desincronicen."""
        ventana = cls.VENTANA_MIN * cls.MINUTO
        fallos: list[int] = []
        bloqueado_hasta = 0
        episodios = 0
        for intento in reversed(intentos_desc):
            if intento.resultado in (ResultadoIntento.EXITO, ResultadoIntento.DESBLOQUEO):
                fallos, bloqueado_hasta, episodios = [], 0, 0
            elif intento.resultado is ResultadoIntento.FALLO and intento.momento >= bloqueado_hasta:
                fallos = [t for t in fallos if t > intento.momento - ventana] + [intento.momento]
                if len(fallos) >= cls.INTENTOS_POR_EQUIPO:
                    episodios += 1
                    minutos = cls.BLOQUEO_ESCALADO_MIN if episodios >= cls.BLOQUEOS_PARA_ESCALAR else cls.BLOQUEO_MIN
                    bloqueado_hasta = intento.momento + minutos * cls.MINUTO
                    fallos = []
        if ahora < bloqueado_hasta:
            return EstadoBloqueoPinMaestro(True, 0, bloqueado_hasta, episodios)
        fallos = [t for t in fallos if t > ahora - ventana]
        return EstadoBloqueoPinMaestro(False, len(fallos), None, episodios)

    @classmethod
    def evaluar_bloqueo_global(cls, fallos_de_la_hora_desc: list[int], ahora: int) -> EstadoBloqueoPinMaestro:
        """RN-10: tope de 20 fallos por hora en todo el nodo, sea cual sea el equipo. `fallos_de_la_hora_desc` = momentos, del más nuevo al más antiguo."""
        recientes = [t for t in fallos_de_la_hora_desc if t > ahora - 60 * cls.MINUTO]
        if len(recientes) >= cls.TOPE_GLOBAL_POR_HORA:
            hasta = recientes[cls.TOPE_GLOBAL_POR_HORA - 1] + 60 * cls.MINUTO
            return EstadoBloqueoPinMaestro(True, len(recientes), hasta, global_=True)
        return EstadoBloqueoPinMaestro(False, len(recientes))


def politica_aplicable(del_perfil: PoliticaCredencial, del_grupo: PoliticaCredencial | None,
                       del_nivel: PoliticaCredencial | None = None) -> PoliticaCredencial:
    """Qué reglamento manda sobre una persona: el de su grupo, si tiene uno propio; si no, el de su
    nivel educativo (BR-024: preescolar con avatar); si no, el de su perfil (BR-023)."""
    return del_grupo or del_nivel or del_perfil
