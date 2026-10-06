"""Políticas del dominio con datos en memoria: RBAC + alcance, fortaleza y bloqueo. Sin base de datos."""
from __future__ import annotations

from django.test import SimpleTestCase

from acceso.dominio import errores, plantillas
from acceso.dominio.entidades import IntentoAcceso, PoliticaCredencial, Principal, Rol, RolPermiso, UsuarioPermiso
from acceso.dominio.politicas import (
    ContextoActor,
    ObjetivoGrupo,
    ObjetivoOrganizacion,
    ObjetivoUsuario,
    PoliticaAutorizacion,
    PoliticaBloqueo,
    PoliticaFortaleza,
    SinObjetivo,
)
from acceso.dominio.valores import Alcance, ClaseSesion, Menu, ResultadoIntento, TipoIdentificador, TipoSecreto

ORG = "org-1"


def rol_sistema(codigo: str) -> Rol:
    nombre, menu, nivel, permisos = plantillas.ROLES_SISTEMA[codigo]
    return Rol(codigo.lower(), None, codigo, nombre, menu, nivel, True, 0,
               [RolPermiso(p, a) for p, a in permisos.items()])


def principal(usuario_id: str, rol: Rol, clase=ClaseSesion.NORMAL, debe_cambiar=False) -> Principal:
    return Principal(usuario_id, ORG, rol.id, rol.codigo, rol.menu_principal, rol.nivel, "ses", clase, debe_cambiar)


def contexto(usuario_id: str, rol: Rol, docente_en=(), miembro_en=(), adicionales=(), tope=Alcance.ORGANIZATION, **kw) -> ContextoActor:
    return ContextoActor(principal(usuario_id, rol, **kw),
                         PoliticaAutorizacion.concesiones_efectivas(rol, list(adicionales), 1_000),
                         frozenset(docente_en), frozenset(docente_en) | frozenset(miembro_en), tope)


def politica(tipo=TipoSecreto.PIN, longitud=6, **kw) -> PoliticaCredencial:
    base = dict(id="p", organizacion_id=ORG, perfil=Menu.STUDENT, tipo_identificador=TipoIdentificador.CODIGO_ESTUDIANTIL,
                tipo_secreto=tipo, longitud_minima=longitud, exige_mayuscula=False, exige_minuscula=False,
                exige_digito=True, exige_simbolo=False, intentos_maximos=5, ventana_intentos_min=15, bloqueo_minutos=15,
                duracion_sesion_min=240, vigencia_credencial_dias=None, permite_acceso_temporal=True, creado_en=0,
                actualizado_en=0)
    base.update(kw)
    return PoliticaCredencial(**base)


class AutorizacionTests(SimpleTestCase):
    def setUp(self):
        self.pol = PoliticaAutorizacion()
        self.student, self.teacher, self.admin = rol_sistema("STUDENT"), rol_sistema("TEACHER"), rol_sistema("ADMIN")
        self.juan = ObjetivoUsuario("juan", ORG, 1)

    def test_estudiante_solo_se_ve_a_si_mismo(self):
        ctx = contexto("juan", self.student)
        self.assertTrue(self.pol.decidir(ctx, "student.progress.read", self.juan).permitido)
        otro = ObjetivoUsuario("maria", ORG, 1)
        d = self.pol.decidir(ctx, "student.progress.read", otro)
        self.assertFalse(d.permitido)
        self.assertEqual((d.alcance_requerido, d.alcance_concedido), (Alcance.ORGANIZATION, Alcance.SELF))

    def test_docente_alcanza_a_los_estudiantes_de_sus_grupos_y_no_a_otros(self):
        ctx = contexto("prof", self.teacher, docente_en={"8A"})
        self.assertTrue(self.pol.decidir(ctx, "identity.password.reset", self.juan, frozenset({"8A"})).permitido)
        d = self.pol.decidir(ctx, "identity.password.reset", self.juan, frozenset({"9B"}))
        self.assertFalse(d.permitido)
        self.assertEqual(d.alcance_requerido, Alcance.ORGANIZATION)

    def test_fuera_de_alcance_es_acceso_denegado_nunca_inexistente(self):
        # Regla del Documento Maestro: no se revela por omisión, pero tampoco se finge que no existe.
        ctx = contexto("prof", self.teacher, docente_en={"8A"})
        d = self.pol.decidir(ctx, "identity.password.reset", self.juan, frozenset({"9B"}))
        with self.assertRaises(errores.SinPermiso):
            d.exigir(ocultar_existencia=True)

    def test_docente_no_administra_a_otro_docente_aunque_comparta_grupo(self):
        ctx = contexto("prof", self.teacher, docente_en={"8A"})
        colega = ObjetivoUsuario("colega", ORG, 2)
        self.assertFalse(self.pol.decidir(ctx, "identity.password.reset", colega, frozenset({"8A"})).permitido)

    def test_admin_alcanza_la_organizacion_pero_no_a_alguien_de_mas_nivel(self):
        ctx = contexto("adm", self.admin)
        self.assertTrue(self.pol.decidir(ctx, "identity.password.reset", ObjetivoUsuario("colega", ORG, 2)).permitido)
        self.assertTrue(self.pol.decidir(ctx, "identity.policy.manage", ObjetivoOrganizacion(ORG)).permitido)
        coordinador = contexto("coord", Rol("c", ORG, "COORD", "Coordinador", Menu.TEACHER, 2, False, 0,
                                            [RolPermiso("identity.user.update", Alcance.ORGANIZATION)]))
        self.assertFalse(self.pol.decidir(coordinador, "identity.user.update", ObjetivoUsuario("adm", ORG, 3)).permitido)

    def test_otra_organizacion_se_deniega(self):
        ctx = contexto("adm", self.admin)
        d = self.pol.decidir(ctx, "identity.user.read", ObjetivoUsuario("x", "otra-org", 1))
        self.assertEqual(d.codigo, "fuera_de_organizacion")
        with self.assertRaises(errores.SinPermiso):
            d.exigir()

    def test_la_asignacion_del_rol_acota_el_alcance_del_rol(self):
        # BR-021: un rol con permisos de organización asignado sobre un nivel llega sólo hasta ese nivel.
        coordinador = Rol("c", ORG, "COORD", "Coordinador", Menu.TEACHER, 2, False, 0,
                          [RolPermiso("identity.user.read", Alcance.ORGANIZATION)])
        ctx = contexto("coord", coordinador, docente_en={"8A", "8B"}, tope=Alcance.LEVEL)  # 8A y 8B son de su nivel
        self.assertIs(self.pol.alcance_concedido(ctx, "identity.user.read"), Alcance.LEVEL)
        self.assertTrue(self.pol.decidir(ctx, "identity.user.read", self.juan, frozenset({"8B"})).permitido)
        self.assertFalse(self.pol.decidir(ctx, "identity.user.read", ObjetivoUsuario("pedro", ORG, 1), frozenset({"11A"})).permitido)
        self.assertFalse(self.pol.decidir(ctx, "identity.user.read", ObjetivoOrganizacion(ORG)).permitido)

    def test_level_sin_asignacion_de_nivel_se_resuelve_como_sus_grupos(self):
        rol = Rol("r", ORG, "R", "R", Menu.TEACHER, 2, False, 0, [RolPermiso("identity.user.read", Alcance.LEVEL)])
        ctx = contexto("x", rol, docente_en={"8A"})
        self.assertIs(self.pol.alcance_concedido(ctx, "identity.user.read"), Alcance.ASSIGNED_GROUPS)

    def test_escalada_amplia_el_alcance_mientras_esta_vigente(self):
        extra = UsuarioPermiso("up", "prof", "audit.read", Alcance.ORGANIZATION, "adm", "coordinación", 0, vigente_hasta=5_000)
        ctx = contexto("prof", self.teacher, adicionales=[extra])
        self.assertTrue(self.pol.decidir(ctx, "audit.read", ObjetivoOrganizacion(ORG)).permitido)
        caducado = UsuarioPermiso("up", "prof", "audit.read", Alcance.ORGANIZATION, "adm", "x", 0, vigente_hasta=500)
        ctx2 = contexto("prof", self.teacher, adicionales=[caducado])
        self.assertFalse(self.pol.decidir(ctx2, "audit.read", ObjetivoOrganizacion(ORG)).permitido)

    def test_sesion_temporal_solo_rinde_examen(self):
        ctx = contexto("juan", self.student, clase=ClaseSesion.TEMPORAL)
        self.assertTrue(self.pol.decidir(ctx, "student.exam.attempt", self.juan).permitido)
        d = self.pol.decidir(ctx, "identity.password.change_own", self.juan)
        self.assertEqual(d.codigo, "sesion_temporal_limitada")
        with self.assertRaises(errores.SesionTemporalLimitada):
            d.exigir()

    def test_credencial_provisional_solo_permite_cambiarla(self):
        ctx = contexto("prof", self.teacher, docente_en={"8A"}, debe_cambiar=True)
        self.assertTrue(self.pol.decidir(ctx, "identity.password.change_own", ObjetivoUsuario("prof", ORG, 2)).permitido)
        self.assertEqual(self.pol.decidir(ctx, "identity.user.read", self.juan, frozenset({"8A"})).codigo, "debe_cambiar_credencial")

    def test_grupo_como_objetivo_y_sin_objetivo(self):
        ctx = contexto("prof", self.teacher, docente_en={"8A"})
        self.assertTrue(self.pol.decidir(ctx, "identity.group.member.manage", ObjetivoGrupo("8A", ORG)).permitido)
        self.assertFalse(self.pol.decidir(ctx, "identity.group.member.manage", ObjetivoGrupo("9B", ORG)).permitido)
        self.assertTrue(self.pol.decidir(ctx, "identity.role.read", SinObjetivo()).permitido)
        self.assertFalse(self.pol.decidir(contexto("juan", self.student), "identity.role.read", SinObjetivo()).permitido)

    def test_los_cinco_roles_del_maestro(self):
        self.assertEqual(set(plantillas.ROLES_SISTEMA), {"STUDENT", "TEACHER", "ADMIN", "REPORTS", "TECHNICIAN"})
        reportes, tecnico = rol_sistema("REPORTS"), rol_sistema("TECHNICIAN")
        # Reportes: sólo lectura, ninguna escritura académica ni de identidad.
        self.assertFalse(any(p.permiso_codigo.endswith((".create", ".update", ".reset", ".assign")) for p in reportes.permisos))
        self.assertTrue(self.pol.decidir(contexto("rep", reportes), "reports.student.view", self.juan).permitido)
        # Técnico: sin datos personales.
        self.assertFalse(self.pol.decidir(contexto("tec", tecnico), "identity.user.read", self.juan).permitido)
        self.assertTrue(self.pol.decidir(contexto("tec", tecnico), "identity.device.manage", ObjetivoOrganizacion(ORG)).permitido)

    def test_alcance_otorgable_respeta_techo_y_alcance_del_actor(self):
        with self.assertRaises(errores.DatosInvalidos):
            PoliticaAutorizacion.alcance_otorgable(Alcance.SELF, Alcance.ORGANIZATION, Alcance.ORGANIZATION)
        with self.assertRaises(errores.SinPermiso):
            PoliticaAutorizacion.alcance_otorgable(Alcance.ORGANIZATION, Alcance.ORGANIZATION, Alcance.ASSIGNED_GROUPS)
        self.assertIs(PoliticaAutorizacion.alcance_otorgable(Alcance.ORGANIZATION, Alcance.ASSIGNED_GROUPS, Alcance.ORGANIZATION),
                      Alcance.ASSIGNED_GROUPS)


class FortalezaTests(SimpleTestCase):
    def test_pin_de_seis_digitos_valido(self):
        self.assertEqual(PoliticaFortaleza.validar("691302", politica()), [])

    def test_pin_del_alumno_sin_reglas_de_complejidad(self):
        """RN-31: el PIN del alumno reconoce, no protege. `1234` y `111111` valen; sólo cuentan el largo (4 a 6) y que sean dígitos."""
        corto = politica(TipoSecreto.PIN, 4)
        for pin in ("1234", "1111", "123456", "4321"):
            self.assertEqual(PoliticaFortaleza.validar(pin, corto), [], pin)
        self.assertTrue(PoliticaFortaleza.validar("123", corto))
        self.assertTrue(PoliticaFortaleza.validar("1234567", corto))   # más de seis
        self.assertTrue(PoliticaFortaleza.validar("69a3", corto))

    def test_pin_trivial_o_corto_o_con_letras_en_otros_perfiles(self):
        """Un PIN de personal (si la institución lo elige) conserva las reglas: nada de secuencias ni repetidos."""
        pin_personal = politica(TipoSecreto.PIN, 6, perfil=Menu.TEACHER)
        self.assertTrue(PoliticaFortaleza.validar("123456", pin_personal))
        self.assertTrue(PoliticaFortaleza.validar("111111", pin_personal))
        self.assertTrue(PoliticaFortaleza.validar("6913", pin_personal))
        self.assertTrue(PoliticaFortaleza.validar("69a302", pin_personal))

    def test_avatar_para_preescolar(self):
        avatar = politica(TipoSecreto.AVATAR, 4, nivel_clave="preescolar")
        self.assertEqual(PoliticaFortaleza.validar("gato-azul", avatar), [])
        self.assertTrue(PoliticaFortaleza.validar("Gato Azul!", avatar))
        avatar.validar()
        with self.assertRaises(ValueError):
            politica(TipoSecreto.AVATAR, 4, perfil=Menu.TEACHER).validar()

    def test_contrasena_docente_exige_mayuscula_y_simbolo(self):
        docente = politica(TipoSecreto.PASSWORD, 8, exige_mayuscula=True, exige_simbolo=True, exige_digito=False)
        self.assertEqual(PoliticaFortaleza.validar("Docente.2026", docente), [])
        self.assertEqual(len(PoliticaFortaleza.validar("docente2026", docente)), 2)
        self.assertTrue(PoliticaFortaleza.validar("Doc.26", docente))
        with self.assertRaises(errores.SecretoDebil) as ctx:
            PoliticaFortaleza.exigir("docente", docente)
        self.assertEqual(len(ctx.exception.extra["reglas"]), 3)

    def test_inactividad_coherente_con_la_sesion(self):
        with self.assertRaises(ValueError):
            politica(inactividad_min=300).validar()
        politica(inactividad_min=20).validar()


class BloqueoTests(SimpleTestCase):
    def intento(self, resultado, momento):
        return IntentoAcceso("h", resultado, "", momento, "juan")

    def test_cinco_fallos_bloquean_quince_minutos(self):
        ahora = 10_000_000
        fallos = [self.intento(ResultadoIntento.FALLO, ahora - i * 1000) for i in range(5)]
        estado = PoliticaBloqueo.evaluar(fallos, politica(), ahora)
        self.assertTrue(estado.bloqueado)
        self.assertEqual(estado.hasta, ahora + 15 * 60_000)
        self.assertEqual(estado.segundos_restantes(ahora), 900)

    def test_un_exito_o_un_desbloqueo_reinician_la_cuenta(self):
        ahora = 10_000_000
        historial = [self.intento(ResultadoIntento.FALLO, ahora - 1000), self.intento(ResultadoIntento.DESBLOQUEO, ahora - 2000)] + \
                    [self.intento(ResultadoIntento.FALLO, ahora - 3000 - i) for i in range(6)]
        estado = PoliticaBloqueo.evaluar(historial, politica(), ahora)
        self.assertFalse(estado.bloqueado)
        self.assertEqual(estado.fallos, 1)

    def test_los_fallos_viejos_no_cuentan(self):
        ahora = 10_000_000
        viejos = [self.intento(ResultadoIntento.FALLO, ahora - 16 * 60_000 - i) for i in range(5)]
        self.assertFalse(PoliticaBloqueo.evaluar(viejos, politica(), ahora).bloqueado)
