"""
El cupo (P-08, BR-027, BR-063): se aplica SÓLO al crear. Un equipo nuevo y una identidad nueva cuentan contra la licencia; lo que ya existe, el latido de un equipo ya registrado, la
readmisión a una clase y el equipo maestro NUNCA. El error es un 402 `cupo_agotado` (no un 403) con el tipo; la concurrencia de la clase (50/100) sale de la licencia.
"""
from __future__ import annotations

from audit.models import Bitacora
from device_manager import models as m9
from licenciamiento import servicios
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio.licencia import ILIMITADO, Limites

from .base import L, BaseLicencia

CSV = "rol,alias,nombres,apellidos,tipo_identificador,identificador,grupo,secreto\n" + "\n".join(
    f"STUDENT,Alumno {n},Alumno{n},Prueba,CODIGO_ESTUDIANTIL,70000{n},8A," for n in range(1, 6))


class CupoDeEquiposTests(BaseLicencia):
    """BaseAcceso ya dejó UN equipo registrado (la tableta de las pruebas)."""

    def setUp(self):
        super().setUp()
        self.activar_ok(limites=Limites(equipos=2, usuarios=1200, concurrentes_normal=50, concurrentes_pico=100))

    def registrar(self, identificador: str, tipo: str = "TABLETA", ruta: str = "/api/dispositivos/"):
        return self.api.post(ruta, {"identificador": identificador, "nombre": identificador, "tipo": tipo}, format="json")

    def test_un_equipo_nuevo_cabe_hasta_el_limite_y_el_siguiente_recibe_402_cupo_agotado(self):
        self.assertEqual(self.registrar("tab-02").status_code, 201)                                    # 2 de 2
        r = self.registrar("tab-03")
        self.assertEqual(r.status_code, 402, r.content)
        self.assertEqual((r.json()["codigo"], r.json()["tipo"], r.json()["limite"], r.json()["en_uso"]), ("cupo_agotado", "equipos", 2, 2))
        self.assertFalse(m9.Dispositivo.objects.filter(identificador_hw="tab-03").exists())            # no queda a medias
        self.assertEqual(self.estado()["estado"], "activa")                                            # y el estado de la licencia ni se enteró

    def test_el_latido_de_un_equipo_nuevo_tambien_cuenta_y_el_de_uno_ya_registrado_nunca(self):
        self.registrar("tab-02")
        r = self.registrar("tab-03", ruta="/api/dispositivos/latido/")
        self.assertEqual((r.status_code, r.json()["codigo"], r.json()["tipo"]), (402, "cupo_agotado", "equipos"))
        for existente in (self.TABLETA, "tab-02"):                                                     # lo existente sigue funcionando
            r = self.registrar(existente, ruta="/api/dispositivos/latido/")
            self.assertEqual(r.status_code, 200, (existente, r.content))
            self.assertEqual(self.registrar(existente).status_code, 200)                              # y volver a registrarlo es idempotente

    def test_el_equipo_maestro_no_consume_cupo_ni_se_bloquea_aunque_el_cupo_este_lleno(self):
        self.registrar("tab-02")
        self.assertEqual(self.registrar("ops-master-1", tipo="MASTER", ruta="/api/dispositivos/latido/").status_code, 200)
        self.assertEqual(self.registrar("ops-master-2", tipo="MASTER").status_code, 201)
        self.assertEqual(self.admin.get(f"{L}/consumo/").json()["equipos"]["en_uso"], 2)               # los maestros no cuentan
        self.assertEqual(self.registrar("tab-03").status_code, 402)

    def test_un_equipo_que_aparece_por_el_aula_no_se_bloquea_nunca_r_01(self):
        """El aula, la evaluación y el login resuelven el equipo por `device_manager.servicios.resolver`, que NO consulta el cupo: bloquear a una tableta que ya está en clase la sacaría de clase."""
        self.registrar("tab-02")
        sesion = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, format="json").json()
        r = self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": "ana", "persona_rotulo": "Ana", "dispositivo": "tab-nueva-en-clase"}, format="json")
        self.assertIn(r.status_code, (200, 201), r.content)

    def test_el_bloqueo_por_cupo_se_asienta_agregado_como_bloqueo_de_licencia(self):
        self.registrar("tab-02")
        for n in range(3, 6):
            self.assertEqual(self.registrar(f"tab-0{n}").status_code, 402)
        self.assertFalse(Bitacora.objects.filter(accion=cat.A_BLOQUEO).exists())                       # no se escribe dentro de una transacción que se revierte
        self.evaluar("tick")
        asiento = Bitacora.objects.get(accion=cat.A_BLOQUEO)
        self.assertEqual((asiento.valor_nuevo["cupo"], asiento.valor_nuevo["cantidad"]), ("equipos", 3))

    def test_sin_licencia_en_desarrollo_y_pruebas_no_hay_cupo(self):
        from django.test import override_settings
        from licenciamiento.infraestructura import contenedor
        with override_settings(AVACOM_LICENCIA_MODO="auto"):
            contenedor.reiniciar()
            for n in range(2, 8):
                self.assertEqual(self.registrar(f"tab-{n:02d}").status_code, 201)


class CupoDeUsuariosTests(BaseLicencia):
    """BaseAcceso dejó TRES identidades activas: administración, docente y estudiante."""

    def setUp(self):
        super().setUp()
        self.activar_ok(limites=Limites(equipos=55, usuarios=4, concurrentes_normal=50, concurrentes_pico=100))

    def crear(self, n: int, cliente=None):
        return (cliente or self.admin).post("/api/acceso/usuarios/", {
            "rol": "STUDENT", "alias": f"Nuevo {n}", "persona": {"nombres": f"Nuevo{n}", "apellidos": "Prueba"},
            "identificadores": [{"tipo": "CODIGO_ESTUDIANTIL", "valor": f"80000{n}", "es_login": True}], "secreto": "4321", "secreto_definitivo": True,
            "grupo_id": self.grupo["id"]}, format="json")

    def test_una_identidad_nueva_cabe_hasta_el_limite_y_la_siguiente_recibe_402(self):
        self.assertEqual(self.crear(1).status_code, 201)                                               # 4 de 4
        r = self.crear(2)
        self.assertEqual(r.status_code, 402, r.content)
        self.assertEqual((r.json()["codigo"], r.json()["tipo"], r.json()["limite"], r.json()["en_uso"]), ("cupo_agotado", "usuarios", 4, 4))
        self.assertEqual(self.admin.get(f"{L}/consumo/").json()["usuarios"]["en_uso"], 4)              # no se creó nada

    def test_lo_que_ya_existe_sigue_funcionando_con_el_cupo_lleno(self):
        self.crear(1)
        self.assertEqual(self.crear(2).status_code, 402)
        r = self.login(self.DOCENTE_DNI, self.DOCENTE_PASS)                                            # inicia sesión (una sola por persona: la de antes se cierra)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.con_token(r.json()["token"]).get("/api/acceso/yo/").status_code, 200)
        r = self.admin.patch(f"/api/acceso/usuarios/{self.estudiante_id}/", {"alias": "Juan Pablo"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)                                                # actualizar una cuenta existente no es una alta

    def test_la_importacion_crea_hasta_el_cupo_y_rechaza_el_resto_fila_por_fila(self):
        r = self.admin.post("/api/acceso/usuarios/importar/", {"contenido": CSV}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        cuerpo = r.json()
        self.assertEqual((cuerpo["resumen"]["creados"], cuerpo["resumen"]["rechazadas"]), (1, 4))      # sólo cabía uno más
        self.assertEqual({x["codigo"] for x in cuerpo["rechazadas"]}, {"cupo_agotado"})

    def test_el_autorregistro_del_alumno_tambien_cuenta_y_el_ingreso_de_un_visitante_nunca_se_bloquea(self):
        self.crear(1)
        r = self.api.post("/api/acceso/estudiantes/registro/", {"grupo_id": self.grupo["id"], "nombres": "Pedro", "apellidos": "Gómez", "pin": "1234", "dispositivo": self.TABLETA}, format="json")
        self.assertEqual((r.status_code, r.json()["codigo"]), (402, "cupo_agotado"))
        for _ in range(3):                                                                              # RN-33: entrar como visitante NUNCA se bloquea…
            r = self.api.post("/api/acceso/sesiones/visitante/", {"dispositivo": self.TABLETA}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.admin.get(f"{L}/consumo/").json()["usuarios"]["en_uso"], 4)              # …y las visitas no cuentan para el cupo

    def test_un_profesor_tampoco_puede_dar_de_alta_sobre_el_cupo_pero_su_clase_sigue(self):
        self.crear(1)
        self.assertEqual(self.crear(2, cliente=self.docente).status_code, 402)
        self.assertEqual(self.docente.get("/api/aula/sesiones/").status_code, 200)

    def test_sin_licencia_en_desarrollo_y_pruebas_no_hay_cupo_de_usuarios(self):
        from django.test import override_settings
        from licenciamiento.infraestructura import contenedor
        with override_settings(AVACOM_LICENCIA_MODO="auto"):
            contenedor.reiniciar()
            for n in range(1, 6):
                self.assertEqual(self.crear(n).status_code, 201)

    def test_limite_sin_tope_no_bloquea_nada(self):
        self.activar_ok(via="renovar", serie=2, emitida=self.t0 - 1, limites=Limites(ILIMITADO, ILIMITADO, 50, 100))
        for n in range(1, 4):
            self.assertEqual(self.crear(n).status_code, 201)


class ConcurrenciaDeLaClaseTests(BaseLicencia):
    """BR-063: los 50 y 100 dispositivos de la clase salen de la licencia; al llegar al pico se rechaza lo NUEVO, nunca a quien ya estaba."""

    def setUp(self):
        super().setUp()
        self.activar_ok(limites=Limites(equipos=55, usuarios=1200, concurrentes_normal=1, concurrentes_pico=2))

    def test_la_configuracion_del_aula_toma_la_concurrencia_de_la_licencia(self):
        from classroom_engine.infraestructura.contenedor import configuracion
        c = configuracion()
        self.assertEqual((c.dispositivos_normal, c.dispositivos_pico), (1, 2))
        self.assertEqual(servicios.concurrencia(50, 100), (1, 2))

    def test_el_tercer_dispositivo_nuevo_no_entra_pero_el_ya_admitido_se_readmite_sin_problema(self):
        sesion = self.api.post("/api/aula/sesiones/", {"via": "libre", "profesor_id": "prof-1"}, format="json").json()

        def unir(persona: str, dispositivo: str):
            return self.api.post("/api/aula/sesiones/unirse/", {"codigo_union": sesion["codigo_union"], "persona_id": persona, "persona_rotulo": persona, "dispositivo": dispositivo}, format="json")
        self.assertIn(unir("ana", "tab-1").status_code, (200, 201))
        self.assertIn(unir("beto", "tab-2").status_code, (200, 201))
        r = unir("carla", "tab-3")
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "aula_llena"))
        self.assertIn(unir("ana", "tab-1").status_code, (200, 201))                                    # la readmisión de quien ya estaba pasa

    def test_sin_licencia_la_concurrencia_es_la_de_settings(self):
        from django.test import override_settings
        from licenciamiento.infraestructura import contenedor
        with override_settings(AVACOM_LICENCIA_MODO="auto", AVACOM_AULA_DISPOSITIVOS_PICO=7, AVACOM_AULA_DISPOSITIVOS_NORMAL=3):
            contenedor.reiniciar()
            from classroom_engine.infraestructura.contenedor import configuracion
            self.assertEqual((configuracion().dispositivos_normal, configuracion().dispositivos_pico), (3, 7))
