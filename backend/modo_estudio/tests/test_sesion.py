"""
La pregunta del menú y la sesión de estudio (FUN-080, FUN-089, FUN-090, 008-01, 008-07; D-15 «identidad declarada»): `GET /estado/` nunca falla y dice
si la tableta puede usar el modo de estudio (cualquier tableta registrada, activa y no bloqueada) y quién puede llevarse el paquete; `GET /estudiantes/`
da los nombres de la pantalla «¿Quién eres?»; abrir y cerrar la sesión de alumno en MOD-009; y avisar de que el aparato terminó de limpiarse.
"""
from __future__ import annotations

from django.test import override_settings

from acceso.models import Grupo, Organizacion, Usuario
from device_manager import models as m9
from expediente.models import Auditoria

from .. import models as m
from .base import BASE, LECCION_2, BaseEstudio

CLAVES_ESTADO = {"disponible", "motivo", "perfil", "alumno", "dueno", "dispositivo", "descarga_permitida", "servidor_en"}


class EstadoTests(BaseEstudio):
    def estado(self, hw: str | None = None, cliente=None, **params) -> dict:
        return self.json_ok(self.ver("/estado/", hw=hw, cliente=cliente, **params))

    def test_una_tableta_asignada_esta_disponible_y_su_dueno_es_quien_puede_llevarse_el_paquete(self):
        e = self.estado()                       # nadie se declaró: se presume a su dueño para la descarga, pero `alumno` sólo es el declarado
        self.assertEqual(set(e), CLAVES_ESTADO)
        self.assertEqual((e["disponible"], e["motivo"], e["perfil"], e["descarga_permitida"]), (True, "", "asignado", True))
        self.assertIsNone(e["alumno"])
        self.assertEqual(e["dueno"], {"id": self.estudiante_id, "rotulo": "Juan P."})
        self.assertEqual((e["dispositivo"]["id"], e["dispositivo"]["nombre"], e["dispositivo"]["identificador_hw"]),
                         (self.propia["id"], "Tableta de Juan", self.hw_juan))
        self.assertGreater(e["servidor_en"], 0)
        propio = self.estado(alumno_id=self.estudiante_id)              # el dueño se declara
        self.assertEqual((propio["disponible"], propio["descarga_permitida"], propio["alumno"]), (True, True, {"id": self.estudiante_id, "rotulo": "Juan P."}))

    def test_una_tableta_asignada_a_otro_esta_disponible_pero_su_visitante_no_se_lleva_el_paquete(self):
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        e = self.estado(alumno_id=ana_id)          # Ana declarada sobre la tableta de Juan
        self.assertEqual((e["disponible"], e["motivo"], e["perfil"], e["descarga_permitida"]), (True, "", "asignado", False))
        self.assertEqual((e["alumno"], e["dueno"]), ({"id": ana_id, "rotulo": "Ana R."}, {"id": self.estudiante_id, "rotulo": "Juan P."}))

    def test_una_tableta_compartida_tambien_esta_disponible_y_no_lleva_paquete(self):
        e = self.estado(self.hw_compartida)
        self.assertEqual(set(e), CLAVES_ESTADO)
        self.assertEqual((e["disponible"], e["motivo"], e["perfil"], e["descarga_permitida"], e["alumno"], e["dueno"]),
                         (True, "", "compartido", False, None, None))
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        declarado = self.estado(self.hw_compartida, alumno_id=ana_id)       # en cualquier tableta, quien el cliente declare
        self.assertEqual((declarado["disponible"], declarado["alumno"], declarado["descarga_permitida"]), (True, {"id": ana_id, "rotulo": "Ana R."}, False))

    def test_un_alumno_declarado_que_no_existe_o_esta_inactivo_no_se_devuelve_como_alumno(self):
        e = self.estado(self.hw_compartida, alumno_id="fantasma")
        self.assertEqual((e["disponible"], e["alumno"]), (True, None))         # la pregunta no falla; sólo no reconoce a esa persona
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        Usuario.objects.filter(pk=ana_id).update(estado="INACTIVO")
        self.assertIsNone(self.estado(self.hw_compartida, alumno_id=ana_id)["alumno"])
        propio = self.estado(alumno_id="fantasma")                            # en una asignada tampoco se ofrece la descarga a quien no es el dueño
        self.assertEqual((propio["alumno"], propio["descarga_permitida"]), (None, False))

    def test_el_aparato_que_no_se_conoce_o_falta_no_hace_fallar_la_pregunta(self):
        e = self.estado("hw-desconocida")
        self.assertEqual((e["disponible"], e["motivo"], e["perfil"], e["dueno"]), (False, "dispositivo_desconocido", "", None))
        sin_aparato = self.json_ok(self.api.get(f"{BASE}/estado/"))
        self.assertEqual((sin_aparato["disponible"], sin_aparato["motivo"], sin_aparato["dispositivo"]), (False, "dispositivo_desconocido", None))

    def test_sin_organizacion_instalada_el_nodo_no_esta_listo(self):
        Organizacion.objects.all().delete()
        e = self.estado()
        self.assertEqual(set(e), CLAVES_ESTADO)
        self.assertEqual((e["disponible"], e["motivo"], e["alumno"], e["dueno"], e["descarga_permitida"]), (False, "nodo_no_instalado", None, None, False))

    def test_un_aparato_bloqueado_o_retirado_no_estudia_ni_descarga(self):
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        e = self.estado()
        self.assertEqual((e["disponible"], e["motivo"], e["descarga_permitida"]), (False, "dispositivo_bloqueado", False))
        self.assertEqual(e["dueno"]["id"], self.estudiante_id)                    # se sigue sabiendo de quién es
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=False, activo=False)
        self.assertEqual(self.estado()["motivo"], "dispositivo_inactivo")

    def test_ya_no_hay_motivos_de_perfil(self):
        """Compartida y ajena eran motivos de «no disponible» (D-1, D-2): con D-15 no lo son."""
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        motivos = {self.estado(self.hw_compartida)["motivo"], self.estado(alumno_id=ana_id)["motivo"], self.estado(self.hw_compartida, alumno_id=ana_id)["motivo"]}
        self.assertEqual(motivos, {""})

    def test_con_sesion_manda_la_persona_del_token(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        propio = self.estado(cliente=juan)
        self.assertEqual((propio["disponible"], propio["alumno"]["id"], propio["descarga_permitida"]), (True, self.estudiante_id, True))
        ana_id, _ = self.alumno_con_tableta("Ana R.", "300111")
        ana = self.sesion("300111", "573920")
        en_la_de_juan = self.estado(cliente=ana)                                  # Ana, con sesión, sobre la tableta de Juan: estudia, no descarga
        self.assertEqual((en_la_de_juan["disponible"], en_la_de_juan["motivo"], en_la_de_juan["alumno"]["id"], en_la_de_juan["descarga_permitida"]),
                         (True, "", ana_id, False))
        en_la_suya = self.estado(hw="hw-300111", cliente=ana)
        self.assertEqual((en_la_suya["disponible"], en_la_suya["descarga_permitida"], en_la_suya["dueno"]["id"]), (True, True, ana_id))

    def test_el_aparato_de_la_sesion_se_usa_cuando_no_se_declara_otro(self):
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.hw_juan)
        e = self.json_ok(juan.get(f"{BASE}/estado/"))
        self.assertEqual((e["disponible"], e["dispositivo"]["identificador_hw"]), (True, self.hw_juan))


class EstudiantesTests(BaseEstudio):
    """`GET /estudiantes/`: los nombres de la pantalla «¿Quién eres?». Sin sesión ni permiso; sólo rótulos; siempre 200."""

    def lista(self, hw: str | None = None, cliente=None, **params) -> dict:
        return self.json_ok(self.ver("/estudiantes/", hw=hw, cliente=cliente, **params))

    def rotulos(self, r: dict) -> dict[str, list[str]]:
        return {g["nombre"]: [a["rotulo"] for a in g["alumnos"]] for g in r["grupos"]}

    def test_sin_trabajo_asignado_no_hay_a_quien_elegir(self):
        r = self.lista()
        self.assertEqual(set(r), {"disponible", "motivo", "grupos", "dueno", "servidor_en"})
        self.assertEqual((r["disponible"], r["motivo"], r["grupos"]), (True, "", []))
        self.assertEqual(r["dueno"], {"id": self.estudiante_id, "rotulo": "Juan P."})
        self.assertGreater(r["servidor_en"], 0)
        self.assertIsNone(self.lista(self.hw_compartida)["dueno"])

    def test_los_grupos_con_trabajo_activo_con_sus_alumnos_activos_y_nada_mas_que_nombres(self):
        self.crear_asignacion()
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        r = self.lista(self.hw_compartida)
        self.assertEqual(len(r["grupos"]), 1)
        grupo = r["grupos"][0]
        self.assertEqual({k: grupo[k] for k in ("id", "codigo", "nombre")}, {k: self.grupo[k] for k in ("id", "codigo", "nombre")})
        self.assertEqual(set(grupo), {"id", "codigo", "nombre", "alumnos"})
        self.assertEqual(grupo["alumnos"], [{"id": ana_id, "rotulo": "Ana R."}, {"id": self.estudiante_id, "rotulo": "Juan P."}])      # por nombre
        self.assertTrue(all(set(a) == {"id", "rotulo"} for a in grupo["alumnos"]))
        Usuario.objects.filter(pk=ana_id).update(estado="INACTIVO")          # un alumno inactivo no se ofrece
        self.assertEqual([a["id"] for a in self.lista()["grupos"][0]["alumnos"]], [self.estudiante_id])

    def test_una_asignacion_cerrada_o_de_un_grupo_inactivo_no_aporta_grupo(self):
        a = self.crear_asignacion()
        self.api.post(f"{BASE}/docente/asignaciones/{a['id']}/cerrar/", {}, format="json")
        self.assertEqual(self.lista()["grupos"], [])
        self.crear_asignacion(LECCION_2)
        self.assertEqual(len(self.lista()["grupos"]), 1)
        Grupo.objects.filter(pk=self.grupo["id"]).update(activo=False)
        self.assertEqual(self.lista()["grupos"], [])

    def test_los_grupos_salen_ordenados_por_nombre_y_sin_los_que_no_tienen_alumnos_activos(self):
        self.crear_asignacion()
        self.crear_asignacion(LECCION_2, grupo_id=self.otro_grupo["id"])
        self.assertEqual([g["id"] for g in self.lista()["grupos"]], [self.grupo["id"]])          # el otro grupo no tiene alumnos: nadie que elegir
        luis = self.nuevo_alumno("Luis", "400222", grupo_id=self.otro_grupo["id"])
        grupos = self.lista()["grupos"]
        self.assertEqual({g["id"] for g in grupos}, {self.grupo["id"], self.otro_grupo["id"]})
        self.assertEqual([g["nombre"] for g in grupos], sorted(g["nombre"] for g in grupos))
        self.assertEqual([a["id"] for g in grupos if g["id"] == self.otro_grupo["id"] for a in g["alumnos"]], [luis])

    def test_una_seleccion_de_algunos_alumnos_de_un_grupo_lista_a_todo_el_grupo(self):
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        self.crear_asignacion(alcance="seleccion", alumnos=[ana_id])                # sólo Ana, dentro del grupo 8A
        self.assertEqual(self.rotulos(self.lista()), {self.grupo["nombre"]: ["Ana R.", "Juan P."]})

    def test_los_destinatarios_de_una_seleccion_sin_grupo_van_en_el_grupo_alumnos(self):
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        self.crear_asignacion(alcance="seleccion", grupo_id="", alumnos=[ana_id, self.estudiante_id])
        r = self.lista()
        self.assertEqual(r["grupos"], [{"id": "", "codigo": "", "nombre": "Alumnos",
                                        "alumnos": [{"id": ana_id, "rotulo": "Ana R."}, {"id": self.estudiante_id, "rotulo": "Juan P."}]}])
        Usuario.objects.filter(pk=ana_id).update(estado="INACTIVO")
        self.assertEqual([a["rotulo"] for a in self.lista()["grupos"][0]["alumnos"]], ["Juan P."])

    def test_una_tableta_que_no_se_puede_usar_no_lista_a_nadie(self):
        self.crear_asignacion()
        r = self.lista("hw-desconocida")
        self.assertEqual((r["disponible"], r["motivo"], r["grupos"], r["dueno"]), (False, "dispositivo_desconocido", [], None))
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        r = self.lista()
        self.assertEqual((r["disponible"], r["motivo"], r["grupos"]), (False, "dispositivo_bloqueado", []))
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=False, activo=False)
        self.assertEqual(self.lista()["motivo"], "dispositivo_inactivo")
        Organizacion.objects.all().delete()
        r = self.lista()
        self.assertEqual((r["disponible"], r["motivo"], r["grupos"], r["dueno"]), (False, "nodo_no_instalado", [], None))

    def test_sin_sesion_ni_dispositivo_es_400_y_con_sesion_basta_con_la_del_token(self):
        r = self.api.get(f"{BASE}/estudiantes/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))
        self.assertEqual(self.ver("/estudiantes/", hw="").status_code, 400)
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.hw_juan)
        r = self.json_ok(juan.get(f"{BASE}/estudiantes/"))               # el aparato de la sesión de login
        self.assertEqual((r["disponible"], r["dueno"]["id"]), (True, self.estudiante_id))

    def test_no_pide_sesion_ni_permiso_aunque_el_nodo_la_exija_y_declarar_a_alguien_no_cambia_nada(self):
        self.crear_asignacion()
        base = self.lista()
        base.pop("servidor_en")
        con_alumno = self.lista(alumno_id=self.estudiante_id)
        con_alumno.pop("servidor_en")
        juan = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        con_sesion = self.lista(cliente=juan)
        con_sesion.pop("servidor_en")
        self.assertEqual(base, con_alumno)
        self.assertEqual(base, con_sesion)
        with override_settings(AVACOM_LMS_EXIGIR_SESION=True):
            self.assertEqual(self.ver("/estado/").status_code, 401)                   # las demás rutas sí exigen sesión
            estricta = self.lista()
        estricta.pop("servidor_en")
        self.assertEqual(estricta, base)
        for cliente in (self.docente, self.admin):                                    # ni siquiera importa el rol de quien pregunte
            self.assertEqual(self.ver("/estudiantes/", cliente=cliente).status_code, 200)

    def test_es_solo_lectura_no_registra_la_tableta_ni_abre_sesiones(self):
        antes = (m9.Dispositivo.objects.count(), m9.DimSesionAlumno.objects.count(), m.EventoSalida.objects.count())
        r = self.lista("hw-recien-llegada")
        self.assertEqual(r["motivo"], "dispositivo_desconocido")
        self.assertEqual((m9.Dispositivo.objects.count(), m9.DimSesionAlumno.objects.count(), m.EventoSalida.objects.count()), antes)


class AbrirYCerrarSesionTests(BaseEstudio):
    def test_abrir_la_sesion_en_el_aparato_asignado_abre_la_de_alumno_en_mod_009(self):
        s = self.json_ok(self.enviar("post", "/sesion/", {"nombre": "Tableta de Juan", "plataforma": "android", "version_app": "0.5"}))
        self.assertEqual((s["alumno"]["id"], s["perfil"], s["dispositivo"]["id"]), (self.estudiante_id, "asignado", self.propia["id"]))
        abierta = m9.DimSesionAlumno.objects.get(pk=s["sesion_id"])
        self.assertEqual((abierta.alumno_id, abierta.dispositivo_id, abierta.finalizada_en), (self.estudiante_id, self.propia["id"], None))
        self.assertEqual(m9.Dispositivo.objects.get(pk=self.propia["id"]).plataforma, "android")
        self.assertEqual(self.eventos("estudio.sesion.abierta.v1"), ["estudio.sesion.abierta.v1"])
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.sesion.abierta.v1").carga
        self.assertEqual((carga["alumno_id"], carga["dispositivo_id"], carga["sesion_id"], carga["perfil"]),
                         (self.estudiante_id, self.propia["id"], s["sesion_id"], "asignado"))
        # abrir de nuevo no abre otra ni repite el evento
        otra = self.json_ok(self.enviar("post", "/sesion/"))
        self.assertEqual(otra["sesion_id"], s["sesion_id"])
        self.assertEqual(len(self.eventos("estudio.sesion.abierta.v1")), 1)

    def test_la_api_acepta_un_aparato_compartido_con_la_persona_declarada_pero_no_sin_ella(self):
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        s = self.json_ok(self.enviar("post", "/sesion/", {"alumno_id": ana_id}, hw=self.hw_compartida))
        self.assertEqual((s["alumno"], s["perfil"]), ({"id": ana_id, "rotulo": "Ana R."}, "compartido"))
        r = self.enviar("post", "/sesion/", hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_alumno"))
        r = self.api.post(f"{BASE}/sesion/", {}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "falta_dispositivo"))

    def test_quien_se_declara_debe_existir_y_estar_activo(self):
        r = self.enviar("post", "/sesion/", {"alumno_id": "fantasma"}, hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "sin_permiso", "alumno_desconocido"))
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        Usuario.objects.filter(pk=ana_id).update(estado="INACTIVO")
        r = self.enviar("post", "/sesion/", {"alumno_id": ana_id}, hw=self.hw_compartida)
        self.assertEqual((r.status_code, r.json()["motivo"]), (403, "alumno_desconocido"))
        self.assertEqual(m9.DimSesionAlumno.objects.count(), 0)
        self.assertEqual(self.eventos("estudio.sesion.abierta.v1"), [])

    def test_un_aparato_asignado_a_otra_persona_tambien_admite_a_quien_se_declara(self):
        """D-15: la tableta de Juan sirve para que Ana estudie; lo único que sigue siendo del dueño es el paquete."""
        ana_id = self.nuevo_alumno("Ana R.", "300111")
        juan = self.json_ok(self.enviar("post", "/sesion/"))                        # sin declarar a nadie: su dueño
        self.assertEqual(juan["alumno"]["id"], self.estudiante_id)
        s = self.json_ok(self.enviar("post", "/sesion/", {"alumno_id": ana_id}))    # Ana declarada sobre la tableta de Juan: lo declarado gana al dueño
        self.assertEqual((s["alumno"]["id"], s["perfil"], s["dispositivo"]["id"]), (ana_id, "asignado", self.propia["id"]))
        self.assertIsNotNone(m9.DimSesionAlumno.objects.get(pk=juan["sesion_id"]).finalizada_en)     # INV-011: el relevo cerró la de Juan en esa tableta
        self.assertIsNone(m9.DimSesionAlumno.objects.get(pk=s["sesion_id"]).finalizada_en)
        ana = self.sesion("300111", "573920")
        con_sesion = self.json_ok(self.enviar("post", "/sesion/", cliente=ana))     # y con sesión de Ana sobre la de Juan tampoco hay 403
        self.assertEqual((con_sesion["alumno"]["id"], con_sesion["sesion_id"]), (ana_id, s["sesion_id"]))

    def test_un_aparato_bloqueado_o_retirado_no_abre_sesion(self):
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        r = self.enviar("post", "/sesion/")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_bloqueado"))
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=False, activo=False)
        self.assertEqual(self.enviar("post", "/sesion/").json()["codigo"], "dispositivo_inactivo")

    def test_el_profesor_y_la_administracion_no_abren_una_sesion_de_estudio(self):
        for cliente in (self.docente, self.admin):
            r = self.enviar("post", "/sesion/", cliente=cliente)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "sin_permiso"))
        self.assertEqual(m.EventoSalida.objects.filter(tipo_evento="estudio.sesion.abierta.v1").count(), 0)

    def test_cerrar_la_sesion_la_cierra_en_mod_009_con_lo_que_queda_por_enviar_y_es_idempotente(self):
        s = self.json_ok(self.enviar("post", "/sesion/"))
        r = self.json_ok(self.enviar("post", "/sesion/cerrar/", {"cola_pendiente": 3, "limpieza": "pendiente"}))
        self.assertEqual(r, {"cerrada": True})
        cerrada = m9.DimSesionAlumno.objects.get(pk=s["sesion_id"])
        self.assertEqual((cerrada.motivo_cierre, cerrada.finalizada_en is not None), ("usuario", True))
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.sesion.cerrada.v1").carga
        self.assertEqual((carga["alumno_id"], carga["sesion_id"], carga["motivo"], carga["cola_pendiente"], carga["limpieza"]),
                         (self.estudiante_id, s["sesion_id"], "usuario", 3, "pendiente"))
        self.assertEqual(self.json_ok(self.enviar("post", "/sesion/cerrar/")), {"cerrada": True})    # idempotente: sin otra sesión ni otro evento
        self.assertEqual(len(self.eventos("estudio.sesion.cerrada.v1")), 1)
        r = self.enviar("post", "/sesion/cerrar/", {"limpieza": "a_medias"})
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "datos_invalidos"))

    def test_un_aparato_bloqueado_tambien_puede_cerrar_su_sesion(self):
        s = self.json_ok(self.enviar("post", "/sesion/"))
        m9.Dispositivo.objects.filter(pk=self.propia["id"]).update(bloqueado=True)
        self.assertEqual(self.enviar("post", "/sesion/cerrar/").status_code, 200)
        self.assertIsNotNone(m9.DimSesionAlumno.objects.get(pk=s["sesion_id"]).finalizada_en)

    def test_avisar_que_el_aparato_termino_de_limpiarse_deja_constancia(self):
        r = self.json_ok(self.enviar("post", "/sesion/limpieza/", {"resultado": "completa"}))
        self.assertEqual(r, {"ok": True})
        carga = m.EventoSalida.objects.get(tipo_evento="estudio.limpieza.reintentada.v1").carga
        self.assertEqual((carga["alumno_id"], carga["dispositivo_id"], carga["resultado"]), (self.estudiante_id, self.propia["id"], "completa"))
        self.assertEqual(self.enviar("post", "/sesion/limpieza/", {"resultado": "quizas"}).status_code, 400)
        # en un aparato compartido sin nadie identificado también se puede avisar
        self.assertEqual(self.enviar("post", "/sesion/limpieza/", {"resultado": "pendiente"}, hw=self.hw_compartida).status_code, 200)

    def test_abrir_la_sesion_no_deja_asientos_de_auditoria_ajenos(self):
        self.json_ok(self.enviar("post", "/sesion/"))
        self.assertFalse(Auditoria.objects.filter(accion__startswith="estudio.").exists())
