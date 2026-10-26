"""
Respaldar y restaurar son SÓLO del personal de AVACOM WORLD (D-1, D-2, D-3): la administración de la institución lee y nada más. Estas pruebas recorren toda la matriz de roles, el
rol personalizado que la administración pueda componer, la petición anónima y el pase de soporte.
"""
from __future__ import annotations

from respaldo.dominio import catalogos as cat

from .base import BaseRespaldo, R

LECTURAS = ("estado/", "respaldos/", "resumen/", "informes/", "destinos/")
ESCRITURAS = [("post", "respaldos/ahora/", {}), ("post", "programacion/", {"retencion": 5}), ("post", "custodia/emitir/", {}), ("post", "restaurar/", {"respaldo_id": "x", "motivo": "otro"}),
              ("post", "restaurar/modulo/", {"modulo": "gradebook"}), ("post", "respaldos/x/verificar/", {}), ("post", "respaldos/x/exportar/", {"unidad": "u"})]


class MatrizDeRoles(BaseRespaldo):
    def llamar(self, cliente, metodo, ruta, cuerpo=None):
        return getattr(cliente, metodo)(f"{R}/{ruta}", cuerpo, format="json") if metodo == "post" else cliente.get(f"{R}/{ruta}")

    def test_la_administracion_lee_estado_y_constancias_pero_no_puede_hacer_nada_mas(self):
        f = self.respaldar()
        for ruta in LECTURAS + (f"respaldos/{f['respaldo_id']}/", f"respaldos/{f['respaldo_id']}/constancia/"):
            self.assertEqual(self.llamar(self.admin, "get", ruta).status_code, 200, ruta)
        for metodo, ruta, cuerpo in ESCRITURAS:
            r = self.llamar(self.admin, metodo, ruta, cuerpo)
            self.assertEqual(r.status_code, 403, f"{ruta}: la administración NO respalda ni restaura ({r.content[:100]})")

    def test_la_administracion_no_puede_conceder_por_escalada_lo_que_no_tiene(self):
        self.tecnico()
        for permiso in cat.PERMISOS_DE_AVACOM:
            r = self.admin.post(f"/api/acceso/usuarios/{self._tecnico_id}/escaladas/", {"permiso": permiso, "alcance": "ORGANIZATION", "motivo": "prueba", "vigente_hasta": self.reloj.t + 3_600_000},
                                format="json")
            self.assertEqual(r.status_code, 403, f"{permiso}: nadie concede un permiso que no tiene ({r.status_code})")
        r = self.admin.post(f"/api/acceso/usuarios/{self.docente_id}/escaladas/", {"permiso": "backup.read", "alcance": "ORGANIZATION", "motivo": "prueba", "vigente_hasta": self.reloj.t + 3_600_000},
                            format="json")
        self.assertIn(r.status_code, (201, 400), "backup.read sí es de la administración")

    def test_el_tecnico_de_avacom_respalda_programa_verifica_y_emite_la_custodia(self):
        t = self.tecnico()
        self.assertEqual(self.llamar(t, "get", "estado/").status_code, 200)
        f = self.respaldar()
        self.assertEqual(self.llamar(t, "post", f"respaldos/{f['respaldo_id']}/verificar/", {}).status_code, 200)
        self.assertEqual(self.llamar(t, "post", "programacion/", {"hora_min": 180}).status_code, 200)
        self.assertEqual(self.llamar(t, "post", "custodia/emitir/", {}).status_code, 201)

    def test_los_demas_roles_no_ven_nada(self):
        for nombre, cliente in (("profesor", self.sesion(self.DOCENTE_DNI, self.DOCENTE_PASS)), ("estudiante", self.sesion(self.ESTUDIANTE_CODIGO, self.ESTUDIANTE_PIN)),
                                ("reportes", self.reportes())):
            for ruta in LECTURAS:
                self.assertEqual(self.llamar(cliente, "get", ruta).status_code, 403, f"{nombre}: {ruta}")
            for metodo, ruta, cuerpo in ESCRITURAS:
                self.assertEqual(self.llamar(cliente, metodo, ruta, cuerpo).status_code, 403, f"{nombre}: {ruta}")

    def test_sin_sesion_nada_se_pide_de_forma_anonima(self):
        from rest_framework.test import APIClient
        anonimo = APIClient()
        for ruta in LECTURAS:
            self.assertEqual(self.llamar(anonimo, "get", ruta).status_code, 403, ruta)
        for metodo, ruta, cuerpo in ESCRITURAS:
            self.assertEqual(self.llamar(anonimo, metodo, ruta, cuerpo).status_code, 403, ruta)

    def test_un_actor_declarado_en_el_cuerpo_no_vale(self):
        from rest_framework.test import APIClient
        r = APIClient().post(f"{R}/respaldos/ahora/", {"actor": "sistema", "actor_rotulo": "interno"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_un_rol_que_no_es_el_del_tecnico_de_avacom_no_pasa_aunque_tuviera_el_permiso_D_3(self):
        from respaldo.aplicacion.puertos import Actor
        from respaldo.dominio.errores import SinPermiso
        from respaldo.infraestructura.autorizacion import AutorizacionRespaldo
        for rol in ("ADMIN", "TEACHER", "RESP", ""):
            actor = Actor(id="u", nivel=3, autenticado=True, principal=object(), rol=rol)
            for permiso in cat.PERMISOS_DE_AVACOM:
                with self.assertRaises(SinPermiso, msg=f"{rol}/{permiso}"):
                    AutorizacionRespaldo().exigir(actor, permiso)
        with self.assertRaises(SinPermiso):
            AutorizacionRespaldo().exigir(Actor(id="sistema", autenticado=False), cat.P_LEER)
        with self.assertRaises(ValueError):
            AutorizacionRespaldo().exigir(Actor(id="u", autenticado=True, principal=object(), rol="TECHNICIAN"), "backup.otra")


class PaseDeSoporte(BaseRespaldo):
    def probar(self, pase, accion="restaurar"):
        f = self.respaldar() if not hasattr(self, "_f") else self._f
        self._f = f
        return self.tecnico().post(f"{R}/restaurar/", {"respaldo_id": f["respaldo_id"], "motivo": "otro", **({"pase": pase} if pase is not None else {})}, format="json")

    def test_sin_pase_aunque_sea_el_tecnico_no_se_restaura(self):
        r = self.probar(None)
        self.assertEqual((r.status_code, r.json()["codigo"]), (403, "pase_requerido"))
        self.assertEqual(self.s.vivo.en_marcha(), None)

    def test_los_pases_malos_se_rechazan_con_su_motivo_y_quedan_en_la_bitacora(self):
        from . import emisor
        casos = {
            "vencido": emisor.emitir_b64([cat.P_RESTAURAR], self.reloj.t - 6 * cat.HORA_MS, horas=1),
            "accion_no_incluida": self.pase(cat.P_EXPORTAR),
            "otro_equipo": self.pase(cat.P_RESTAURAR, nodo="otro-equipo"),
            "kid_desconocido": self.pase(cat.P_RESTAURAR, kid="sop-2026-1"),
            "firma_invalida": self.pase(cat.P_RESTAURAR, indice=2, kid="sop-dev-1"),
            "vigencia_excesiva": emisor.emitir_b64([cat.P_RESTAURAR], self.reloj.t, horas=48),
        }
        for motivo, pase in casos.items():
            r = self.probar(pase)
            self.assertEqual((r.status_code, r.json().get("motivo")), (403, motivo), motivo)
        self.assertEqual(self.acciones_asentadas().count("respaldo.pase_rechazado"), len(casos))

    def test_un_nodo_de_produccion_no_acepta_la_llave_de_desarrollo(self):
        from django.test import override_settings
        from respaldo.infraestructura import contenedor
        with override_settings(AVACOM_LICENCIA_ENTORNO="produccion", AVACOM_RESPALDO_DIR=str(self.carpeta)):
            contenedor.reiniciar()
            llaves = contenedor.servicios().soporte.llaves_publicas()
        contenedor.reiniciar()
        self.assertEqual(llaves, {}, "claves/produccion.json está vacío hasta la ceremonia: la llave de desarrollo no se carga")

    def test_el_pase_nunca_viaja_en_la_respuesta_ni_en_la_bitacora(self):
        pase = self.pase(cat.P_RESTAURAR, kid="sop-2026-1")
        r = self.probar(pase)
        self.assertNotIn(pase, r.content.decode())
        from audit.models import Bitacora
        for b in Bitacora.objects.filter(modulo="respaldo"):
            self.assertNotIn(pase, str(b.__dict__))
