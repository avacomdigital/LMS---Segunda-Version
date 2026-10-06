"""
Cómo entra un alumno a la tableta (RN-30…RN-37, RB-16…RB-18, RB-22): elige su grupo, toca su nombre, marca su PIN; si no está en la lista se crea
solo; si su PIN quedó pendiente lo elige ahí; y el castigo por equivocarse recae en la TABLETA, no en la cuenta. Cubre AC-A11…A13, A17, A18 y A20.
"""
from __future__ import annotations

from django.db.models import F

from acceso import models as m

from .base import BaseAcceso

MIN = 60_000


class ListaDelAulaTests(BaseAcceso):
    def grupos(self, **extra):
        return self.api.get(f"/api/acceso/aula/grupos/?dispositivo={self.TABLETA}", **extra)

    def test_sin_una_tableta_registrada_no_se_ve_ninguna_lista(self):
        # BR-056
        for ruta in ("/api/acceso/aula/grupos/", f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/",
                     "/api/acceso/aula/grupos/?dispositivo=desconocida"):
            r = self.api.get(ruta)
            self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"), ruta)

    def test_la_lista_de_nombres_trae_solo_el_alias_y_si_falta_el_pin(self):
        # D-A8 / PAN-002: nunca documento, apellidos ni estado
        r = self.api.get(f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/?dispositivo={self.TABLETA}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), [{"id": self.estudiante_id, "alias": "Juan P.", "pin_pendiente": False}])
        texto = r.content.decode()
        for privado in (self.ESTUDIANTE_CODIGO, "Pérez", "1.020.334.556", "2012-04-09"):
            self.assertNotIn(privado, texto)

    def test_la_tableta_tambien_se_reconoce_por_el_id_que_aprendio_del_nodo(self):
        r = self.api.get("/api/acceso/aula/grupos/", HTTP_X_AVACOM_DISPOSITIVO=self.tableta["id"])
        self.assertEqual(r.status_code, 200, r.content)

    def test_los_grupos_traen_su_reglamento_para_que_la_tableta_sepa_si_pedir_teclado_o_dibujos(self):
        lista = {g["id"]: g for g in self.grupos().json()}
        g = lista[self.grupo["id"]]
        self.assertEqual((g["tipo_secreto"], g["longitud_pin"], g["alumnos"], g["registro_abierto"]), ("PIN", 4, 1, True))

    def test_un_grupo_vacio_solo_se_ofrece_mientras_el_registro_propio_siga_abierto(self):
        self.assertEqual({g["id"] for g in self.grupos().json()}, {self.grupo["id"], self.otro_grupo["id"]})
        self.admin.put("/api/acceso/politicas/student/", {"autoregistro": False}, format="json")
        self.assertEqual({g["id"] for g in self.grupos().json()}, {self.grupo["id"]})
        # el profesor, al crear su usuario, ve todos los que puede elegir
        todos = self.api.get(f"/api/acceso/aula/grupos/?dispositivo={self.TABLETA}&para=docente").json()
        self.assertEqual({g["id"] for g in todos}, {self.grupo["id"], self.otro_grupo["id"]})

    def test_un_grupo_desactivado_o_inexistente_no_se_lista(self):
        self.admin.patch(f"/api/acceso/grupos/{self.otro_grupo['id']}/", {"activo": False}, format="json")
        self.assertEqual({g["id"] for g in self.grupos().json()}, {self.grupo["id"]})
        r = self.api.get(f"/api/acceso/aula/grupos/{self.otro_grupo['id']}/estudiantes/?dispositivo={self.TABLETA}")
        self.assertEqual(r.status_code, 404)

    def test_los_retirados_no_aparecen_en_la_lista(self):
        self.admin.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"estado": "RETIRADO"}, format="json")
        r = self.api.get(f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/?dispositivo={self.TABLETA}")
        self.assertEqual(r.json(), [])


class EntrarTocandoElNombreTests(BaseAcceso):
    def entrar(self, usuario_id, pin, dispositivo=None):
        return self.api.post("/api/acceso/sesiones/", {"usuario_id": usuario_id, "secreto": pin,
                                                        "dispositivo": dispositivo or self.TABLETA}, format="json")

    def crear_alumno(self, alias, codigo, pin="4821"):
        r = self.docente.post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": alias, "persona": {"nombres": alias.split()[0]},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": codigo}], "secreto": pin, "secreto_definitivo": True,
            "grupo_id": self.grupo["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def test_el_alumno_toca_su_nombre_marca_su_pin_y_entra(self):
        # AC-A11 / RB-22
        r = self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["usuario"]["rol"], "STUDENT")
        self.assertEqual(r.json()["usuario"]["clase_sesion"], "NORMAL")
        self.assertEqual(self.con_token(r.json()["token"]).get("/api/acceso/yo/").status_code, 200)

    def test_sin_tableta_registrada_no_se_entra_por_nombre(self):
        r = self.api.post("/api/acceso/sesiones/", {"usuario_id": self.estudiante_id, "secreto": self.ESTUDIANTE_PIN}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "dispositivo_no_autorizado"))

    def test_un_pin_equivocado_no_dice_mas_que_los_intentos_que_quedan(self):
        r = self.entrar(self.estudiante_id, "0000")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["intentos_restantes"]), (401, "credenciales_invalidas", 4))

    def test_por_nombre_solo_entran_alumnos(self):
        # el profesor y la administración tienen identificador y contraseña: su nombre en una lista no abre nada
        for ajeno in (self.docente_id, self.admin_id, "no-existe"):
            r = self.entrar(ajeno, self.DOCENTE_PASS)
            self.assertEqual((r.status_code, r.json()["codigo"]), (401, "credenciales_invalidas"), ajeno)

    def test_por_nombre_no_entra_un_alumno_de_un_grupo_con_contrasena(self):
        politicas = {p["perfil"]: p for p in self.admin.get("/api/acceso/politicas/").json() if not p["nivel_clave"]}
        self.admin.patch(f"/api/acceso/grupos/{self.grupo['id']}/", {"politica_credencial_id": politicas["teacher"]["id"]}, format="json")
        r = self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN)
        self.assertEqual((r.status_code, r.json()["codigo"]), (401, "credenciales_invalidas"))

    def test_cinco_pin_equivocados_ponen_en_pausa_la_tableta_no_la_cuenta(self):
        # AC-A13 · RN-33 · D-A2
        maria = self.crear_alumno("María R.", "130010")
        self.api.post("/api/dispositivos/", {"identificador": "otra-hw", "nombre": "tableta-03"}, format="json")
        for quedan in (4, 3, 2, 1):
            r = self.entrar(self.estudiante_id, "0000")
            self.assertEqual((r.status_code, r.json()["intentos_restantes"]), (401, quedan))
        r = self.entrar(self.estudiante_id, "0000")
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "dispositivo_en_pausa"))
        self.assertIn("2 minutos", r.json()["detail"])
        self.assertIn("visitante", r.json()["detail"])
        self.assertLessEqual(r.json()["reintentar_en_seg"], 120)
        # otro alumno, en esa misma tableta, espera igual con su PIN correcto: el castigo es de la tableta y no menciona a nadie
        r = self.entrar(maria, "4821")
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "dispositivo_en_pausa"))
        self.assertNotIn("Juan", r.content.decode())
        # la cuenta de Juan NO está bloqueada: desde otra tableta entra con su PIN
        self.assertEqual(self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN, "otra-hw").status_code, 200)
        ficha = self.docente.get(f"/api/acceso/usuarios/{self.estudiante_id}/").json()
        self.assertIsNone(ficha["bloqueado_hasta"])
        self.assertEqual(ficha["estado"], "ACTIVO")
        # y pasados los 2 minutos la tableta vuelve a aceptar PIN
        m.IntentoAcceso.objects.update(momento=F("momento") - 3 * MIN)
        self.assertEqual(self.entrar(maria, "4821").status_code, 200)

    def test_el_castigo_de_la_tableta_tambien_aplica_al_codigo_y_clave_de_siempre(self):
        for _ in range(5):
            self.login(self.ESTUDIANTE_CODIGO, "0000", self.TABLETA)
        r = self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN, self.TABLETA)
        self.assertEqual((r.status_code, r.json()["codigo"]), (423, "dispositivo_en_pausa"))
        # sin tableta que castigar, el reglamento sigue protegiendo la cuenta
        for _ in range(5):
            self.login(self.ESTUDIANTE_CODIGO, "0000")
        self.assertEqual(self.login(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN).status_code, 423)

    def test_un_acierto_desde_la_tableta_borra_la_cuenta_de_fallos(self):
        for _ in range(4):
            self.entrar(self.estudiante_id, "0000")
        self.assertEqual(self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN).status_code, 200)
        self.assertEqual(self.entrar(self.estudiante_id, "0000").json()["intentos_restantes"], 4)

    def test_el_personal_se_sigue_bloqueando_por_cuenta(self):
        # RN-33 aplica sólo a los alumnos: al profesor, desde la tableta que sea, se le bloquea la cuenta
        for _ in range(5):
            self.login(self.DOCENTE_DNI, "mala", self.TABLETA)
        self.assertEqual(self.login(self.DOCENTE_DNI, self.DOCENTE_PASS, "otra-hw").status_code, 423)

    def test_un_pin_de_alumno_sin_reglas_de_complejidad_entra_como_cualquiera(self):
        facil = self.crear_alumno("Rita S.", "130020", pin="1234")
        self.assertEqual(self.entrar(facil, "1234").status_code, 200)


class RegistroPropioDelAlumnoTests(BaseAcceso):
    def registrar(self, **cambios):
        cuerpo = {"grupo_id": self.grupo["id"], "nombres": "Pedro", "apellidos": "Gómez", "pin": "1234", "dispositivo": self.TABLETA}
        cuerpo.update(cambios)
        return self.api.post("/api/acceso/estudiantes/registro/", cuerpo, format="json")

    def test_el_alumno_se_crea_solo_con_grupo_nombre_y_pin_y_entra_tocando_su_nombre(self):
        # AC-A11 · RN-30
        r = self.registrar()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["alias"], "Pedro G.")
        usuario = m.Usuario.objects.get(id=r.json()["id"])
        self.assertEqual((usuario.origen, usuario.estado, usuario.rol.codigo), ("AUTOALTA_ALUMNO", "ACTIVO", "STUDENT"))
        self.assertIsNone(usuario.confirmado_en)                                        # «sin confirmar» hasta que el profesor lo respalde
        self.assertEqual(m.MiembroGrupo.objects.get(usuario=usuario).grupo_id, self.grupo["id"])
        self.assertEqual(usuario.identificadores.get().tipo, "CLAVE_INSTALACION")      # DEC-049: oculto, nunca lo teclea
        self.assertFalse(m.Credencial.objects.get(usuario=usuario, activa=True).debe_cambiar)
        lista = self.api.get(f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/?dispositivo={self.TABLETA}").json()
        self.assertIn("Pedro G.", [a["alias"] for a in lista])
        entrada = self.api.post("/api/acceso/sesiones/", {"usuario_id": usuario.id, "secreto": "1234", "dispositivo": self.TABLETA}, format="json")
        self.assertEqual(entrada.status_code, 200, entrada.content)
        self.assertEqual(entrada.json()["usuario"]["confirmado"], False)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.estudiante.registrado.v1", agregado_id=usuario.id).exists())

    def test_no_necesita_documento_ni_codigo_ni_apellido(self):
        r = self.registrar(nombres="Luz", apellidos="")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["alias"], "Luz")

    def test_el_pin_del_alumno_valen_1234_y_111111_pero_no_3_ni_7_digitos_ni_letras(self):
        # RN-31
        self.assertEqual(self.registrar(nombres="Ana", pin="1234").status_code, 201)
        self.assertEqual(self.registrar(nombres="Beto", pin="111111").status_code, 201)
        for malo in ("123", "1234567", "12a4", ""):
            r = self.registrar(nombres="Zoe", pin=malo)
            self.assertEqual(r.status_code, 400, malo)
        self.assertFalse(m.Usuario.objects.filter(alias="Zoe G.").exists())

    def test_alias_repetido_en_el_grupo_pide_una_letra_mas_y_no_crea_el_duplicado(self):
        # AC-A12 · RN-34
        antes = m.Usuario.objects.count()
        r = self.registrar(nombres="Juan", apellidos="Pérez")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "alias_duplicado"))
        self.assertEqual(r.json()["sugerencia"], "Juan Pé.")
        self.assertEqual(r.json()["detail"], "Ya hay alguien llamado Juan P. en este grupo. Añade una letra: Juan Pé.")
        self.assertEqual(m.Usuario.objects.count(), antes)
        # sin distinguir mayúsculas ni tildes
        r = self.registrar(nombres="x", alias="JUAN P.")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "alias_duplicado"))
        self.assertEqual(self.registrar(nombres="Juan", apellidos="Pérez", alias=r.json().get("sugerencia") or "Juan Pé.").status_code, 201)

    def test_otro_grupo_si_admite_el_mismo_alias(self):
        self.assertEqual(self.registrar(nombres="Juan", apellidos="Pérez", grupo_id=self.otro_grupo["id"]).status_code, 201)

    def test_sin_apellido_el_alias_repetido_pide_escribir_una_letra_o_el_apellido(self):
        self.assertEqual(self.registrar(nombres="Sofía", apellidos="").status_code, 201)
        r = self.registrar(nombres="Sofía", apellidos="")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["sugerencia"]), (409, "alias_duplicado", None))
        self.assertIn("Añade una letra o tu apellido", r.json()["detail"])

    def test_si_la_administracion_apaga_el_registro_propio_se_cierra_y_el_boton_ya_no_aparece(self):
        # AC-A20 · RN-37
        self.admin.put("/api/acceso/politicas/student/", {"autoregistro": False}, format="json")
        r = self.registrar()
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "registro_cerrado"))
        self.assertFalse(self.api.get("/api/acceso/configuracion/").json()["autoregistro_alumnos"])
        # el padrón o el alta del profesor siguen funcionando
        self.assertEqual(self.docente.post("/api/acceso/padron/estudiantes/", {"nombres": "Luisa", "grupo_id": self.grupo["id"]}, format="json").status_code, 201)

    def test_una_tableta_no_crea_mas_de_cinco_cuentas_por_hora(self):
        # R-4
        for i, nombre in enumerate(("Ana", "Beto", "Carla", "Dani", "Eva")):
            self.assertEqual(self.registrar(nombres=nombre).status_code, 201, nombre)
        r = self.registrar(nombres="Fede")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["motivo"]), (403, "registro_cerrado", "tope_por_tableta"))
        # pasada la hora, otra vez
        m.IntentoAcceso.objects.update(momento=F("momento") - 61 * MIN)
        self.assertEqual(self.registrar(nombres="Fede").status_code, 201)

    def test_solo_desde_una_tableta_registrada_y_a_un_grupo_que_existe(self):
        self.assertEqual(self.registrar(dispositivo="desconocida").json()["codigo"], "dispositivo_no_autorizado")
        self.assertEqual(self.registrar(dispositivo="").json()["codigo"], "dispositivo_no_autorizado")
        r = self.registrar(grupo_id="no-existe")
        self.assertEqual((r.status_code, r.json()["codigo"]), (404, "no_encontrado"))

    def test_el_profesor_confirma_a_su_alumno_y_no_a_los_de_otro_grupo(self):
        # RB-20 / RN-36
        propio = self.registrar().json()["id"]
        ajeno = self.registrar(nombres="Gina", grupo_id=self.otro_grupo["id"]).json()["id"]
        r = self.docente.post(f"/api/acceso/usuarios/{propio}/confirmar/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["confirmado_en"])
        self.assertTrue(self.docente.get(f"/api/acceso/usuarios/{propio}/").json()["confirmado"])
        self.assertEqual(self.docente.post(f"/api/acceso/usuarios/{ajeno}/confirmar/").status_code, 403)
        self.assertEqual(self.docente.post(f"/api/acceso/usuarios/{propio}/confirmar/").json()["confirmado_en"], r.json()["confirmado_en"])   # idempotente
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.usuario.confirmado.v1", agregado_id=propio).exists())

    def test_el_alumno_no_puede_confirmar_a_nadie(self):
        propio = self.registrar().json()["id"]
        alumno = self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)
        self.assertEqual(alumno.post(f"/api/acceso/usuarios/{propio}/confirmar/").status_code, 403)

    def test_preescolar_se_registra_con_su_avatar_en_vez_de_pin(self):
        # RF-28 · BR-024 · TST-074
        self.admin.put("/api/acceso/politicas/student/?nivel=preescolar", {"tipo_secreto": "AVATAR", "longitud_minima": 4}, format="json")
        pre = self.admin.post("/api/acceso/grupos/", {"codigo": "TR-A", "nombre": "Transición A", "periodo": "2026", "nivel_clave": "preescolar"}, format="json").json()
        lista = {g["id"]: g for g in self.api.get(f"/api/acceso/aula/grupos/?dispositivo={self.TABLETA}").json()}
        self.assertEqual(lista[pre["id"]]["tipo_secreto"], "AVATAR")
        self.assertEqual(lista[self.grupo["id"]]["tipo_secreto"], "PIN")
        r = self.registrar(grupo_id=pre["id"], nombres="Mía", apellidos="", pin="gato-azul")
        self.assertEqual(r.status_code, 201, r.content)
        entrada = self.api.post("/api/acceso/sesiones/", {"usuario_id": r.json()["id"], "secreto": "gato-azul", "dispositivo": self.TABLETA}, format="json")
        self.assertEqual(entrada.status_code, 200, entrada.content)


class PinPendienteTests(BaseAcceso):
    def poner_pin(self, usuario_id, pin, dispositivo=None):
        return self.api.post(f"/api/acceso/estudiantes/{usuario_id}/pin/", {"pin": pin, "dispositivo": dispositivo or self.TABLETA}, format="json")

    def entrar(self, usuario_id, pin):
        return self.api.post("/api/acceso/sesiones/", {"usuario_id": usuario_id, "secreto": pin, "dispositivo": self.TABLETA}, format="json")

    def test_el_profesor_restablece_el_pin_y_el_alumno_elige_uno_nuevo_sin_que_nadie_vea_un_numero(self):
        # AC-A17 · RN-35
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn("secreto_inicial", r.json())
        self.assertIsNone(r.json()["secreto_provisional"])
        lista = self.api.get(f"/api/acceso/aula/grupos/{self.grupo['id']}/estudiantes/?dispositivo={self.TABLETA}").json()
        self.assertEqual([(a["alias"], a["pin_pendiente"]) for a in lista], [("Juan P.", True)])
        # el PIN viejo ya no sirve y tocar su nombre manda a elegir uno
        r = self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pin_pendiente"))
        self.assertEqual(r.json()["detail"], "Todavía no tienes PIN. Elige uno de 4 números que recuerdes.")
        self.assertEqual(self.poner_pin(self.estudiante_id, "4321").status_code, 200)
        self.assertEqual(self.entrar(self.estudiante_id, "4321").status_code, 200)
        self.assertEqual(self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN).status_code, 401)
        self.assertTrue(m.EventoSalida.objects.filter(tipo_evento="identidad.estudiante.pin_establecido.v1", agregado_id=self.estudiante_id).exists())

    def test_puede_volver_a_elegir_el_mismo_pin_de_antes(self):
        self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual(self.poner_pin(self.estudiante_id, self.ESTUDIANTE_PIN).status_code, 200)

    def test_un_alumno_creado_por_el_padron_sin_pin_lo_elige_al_tocar_su_nombre(self):
        # AC-A18 · RB-26
        nuevo = self.docente.post("/api/acceso/padron/estudiantes/", {"nombres": "Luisa", "apellidos": "Mora", "grupo_id": self.grupo["id"]}, format="json").json()
        self.assertTrue(nuevo["pin_pendiente"])
        self.assertEqual(self.entrar(nuevo["id"], "1234").json()["codigo"], "pin_pendiente")
        self.assertEqual(self.poner_pin(nuevo["id"], "1234").status_code, 200)
        self.assertEqual(self.entrar(nuevo["id"], "1234").status_code, 200)
        fila = next(e for e in self.docente.get("/api/acceso/padron/").json()["grupos"][0]["estudiantes"] if e["id"] == nuevo["id"])
        self.assertEqual((fila["pin_pendiente"], fila["origen"]), (False, "PROFESOR"))

    def test_una_cuenta_que_ya_tiene_pin_no_se_puede_reclamar(self):
        r = self.poner_pin(self.estudiante_id, "9999")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "pin_ya_establecido"))
        self.assertEqual(self.entrar(self.estudiante_id, self.ESTUDIANTE_PIN).status_code, 200)   # el PIN de siempre sigue valiendo

    def test_solo_los_alumnos_eligen_pin_asi_y_siempre_desde_una_tableta_registrada(self):
        self.assertEqual(self.poner_pin(self.docente_id, "1234").status_code, 404)
        self.assertEqual(self.poner_pin("no-existe", "1234").status_code, 404)
        self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {}, format="json")
        self.assertEqual(self.poner_pin(self.estudiante_id, "1234", dispositivo="desconocida").json()["codigo"], "dispositivo_no_autorizado")
        self.assertEqual(self.poner_pin(self.estudiante_id, "12").status_code, 400)               # RN-31: de 4 a 6 dígitos
        self.assertEqual(self.poner_pin(self.estudiante_id, "").status_code, 400)

    def test_restablecer_a_un_alumno_con_un_pin_explicito_sigue_siendo_posible(self):
        # el contrato anterior (el profesor dicta un secreto) se conserva para quien lo necesite
        r = self.docente.post(f"/api/acceso/usuarios/{self.estudiante_id}/credencial/restablecer/", {"secreto": "5555"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["secreto_provisional"], r.json()["pin_pendiente"]), ("5555", False))
