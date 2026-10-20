"""
El middleware de licencia (P-10) y las reglas que nunca se rompen (R-01, R-02, R-04, R-07): con la licencia degradada los módulos licenciables responden 402 «no disponible por licencia»
—no 403, y el permiso del rol se conserva (VER-10)—; cada ruta INTOCABLE de los `urls.py` reales responde IGUAL con la licencia degradada que sin licencia; un fallo interno deja pasar;
el camino de una petición no consulta la base de datos; y lo que se cuenta en memoria se asienta agregado (uno por actor, módulo y hora).
"""
from __future__ import annotations

import re
import threading
from unittest import mock

from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from audit.models import Bitacora
from licenciamiento import servicios
from licenciamiento.dominio import catalogos as cat
from licenciamiento.dominio import rutas
from licenciamiento.dominio.politica import DIA_MS, HORA_MS
from licenciamiento.interfaces.middleware import LicenciaMiddleware

from .base import L, BaseLicencia


def _ejemplo(patron: str) -> str:
    """Una ruta concreta a partir de un patrón de `urls.py`: `path()` con conversores o `re_path()` con grupos con nombre."""
    def grupo(g):
        cuerpo = g.group(2)
        if "|" in cuerpo and "/" not in cuerpo:             # (?P<accion>suspender|reanudar|cerrar)
            return cuerpo.split("|")[0]
        return "x1/y1" if cuerpo.startswith(".") else "x1"   # (?P<ruta>.+) · (?P<pk>[^/]+)
    ruta = re.sub(r"\(\?P<(\w+)>([^)]*)\)", grupo, patron)
    ruta = re.sub(r"<int:\w+>", "1", ruta)
    ruta = re.sub(r"<path:\w+>", "x1/y1", ruta)
    ruta = re.sub(r"<\w+:\w+>", "x1", ruta)
    return ruta.replace("^", "").replace("$", "")


def rutas_reales() -> list[tuple[str, tuple[str, ...]]]:
    """Todas las rutas HTTP del proyecto, tal como las ve el resolvedor de Django: `(ruta de ejemplo con barra inicial, métodos que define su vista)`."""
    def metodos(callback) -> tuple[str, ...]:
        clase = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        if clase is None:
            return ("GET",)
        return tuple(x.upper() for x in clase.http_method_names if x not in ("options", "head") and hasattr(clase, x))

    def recorrer(patrones, prefijo=""):
        for p in patrones:
            if isinstance(p, URLResolver):
                yield from recorrer(p.url_patterns, prefijo + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield "/" + _ejemplo(prefijo + str(p.pattern)), metodos(p.callback)
    return sorted(set(recorrer(get_resolver().url_patterns)))


def instantanea_degradada(base: BaseLicencia):
    """Una licencia ya vencida y fuera de su gracia, evaluada de verdad."""
    base.activar_ok(vence=base.t0 + 30 * DIA_MS)
    base.reloj.avanzar(61 * DIA_MS + 2 * HORA_MS)
    e = base.evaluar("tick")
    assert e.estado.estado == "degradada", e.estado
    return e


class ModulosApagadosTests(BaseLicencia):
    def test_con_la_licencia_degradada_un_modulo_licenciable_responde_402_y_no_403(self):
        instantanea_degradada(self)
        for metodo, ruta, capacidad in (("get", "/api/reportes/clases/", "reportes"), ("get", "/api/search/status/", "busqueda"), ("post", "/api/acceso/usuarios/importar/", "importacion"),
                                        ("post", "/api/acceso/roles/", "administracion_avanzada")):
            r = getattr(self.admin, metodo)(ruta, **({"data": {}, "format": "json"} if metodo == "post" else {}))
            self.assertEqual(r.status_code, 402, (ruta, r.content))
            self.assertEqual((r.json()["codigo"], r.json()["capacidad"]), ("no_disponible_por_licencia", capacidad))
            self.assertIn("módulo", r.json()["detail"])
        self.assertFalse(Bitacora.objects.filter(accion="acceso.denegado").exists())                  # NO es una denegación de acceso (VER-10)

    def test_ver_10_el_permiso_del_rol_se_conserva_y_vuelve_a_funcionar_al_renovar_sin_reasignar_roles(self):
        instantanea_degradada(self)
        self.assertEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        r = self.activar(via="renovar", serie=2, emitida=self.t0 + 61 * DIA_MS, desde=self.t0 + 60 * DIA_MS, vence=self.t0 + 400 * DIA_MS)
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "activa"), r.content)
        r = self.admin.get("/api/reportes/clases/")
        self.assertNotEqual(r.status_code, 402)
        self.assertNotEqual(r.status_code, 403)                                                        # el mismo rol, sin tocarlo

    def test_ver_10_el_bloqueo_se_asienta_como_bloqueo_de_licencia_uno_por_actor_modulo_y_hora(self):
        instantanea_degradada(self)
        for _ in range(5):
            self.assertEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        self.assertEqual(self.docente.get("/api/reportes/clases/").status_code, 402)                  # otro actor: otro asiento
        self.assertFalse(Bitacora.objects.filter(accion=cat.A_BLOQUEO).exists())                      # nada se escribió en el camino de la petición (R-07)
        self.evaluar("tick")                                                                           # el programador los asienta
        asientos = list(Bitacora.objects.filter(accion=cat.A_BLOQUEO).order_by("secuencia"))
        self.assertEqual(len(asientos), 2)
        por_actor = {a.valor_nuevo["actor"]: a.valor_nuevo for a in asientos}
        self.assertEqual(por_actor[self.admin_id]["capacidad"], "reportes")
        self.assertEqual(por_actor[self.admin_id]["cantidad"], 5)
        self.assertEqual(por_actor[self.docente_id]["cantidad"], 1)
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_BLOQUEO).count(), 2)                    # no se vuelve a asentar lo ya asentado
        self.assertEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_BLOQUEO).count(), 2)                    # misma hora: ya hay asiento de este actor y este módulo
        self.reloj.avanzar(HORA_MS)
        self.assertEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        self.evaluar("tick")
        self.assertEqual(Bitacora.objects.filter(accion=cat.A_BLOQUEO).count(), 3)                    # hora nueva: asiento nuevo

    def test_head_se_trata_como_get_y_options_pasa(self):
        """Revisión independiente: DRF atiende un HEAD con la vista GET, así que un HEAD a un módulo apagado también recibe el 402; la consulta previa (OPTIONS) no lleva datos y pasa."""
        instantanea_degradada(self)
        self.assertEqual(self.admin.head("/api/reportes/clases/").status_code, 402)
        self.assertEqual(self.admin.head("/api/search/status/").status_code, 402)
        mw = LicenciaMiddleware(lambda request: HttpResponse("ok"))
        self.assertEqual(mw(RequestFactory().head("/api/reportes/clases/")).status_code, 402)
        self.assertEqual(mw(RequestFactory().options("/api/reportes/clases/")).status_code, 200)
        self.assertEqual(mw(RequestFactory().head("/api/aula/sesiones/")).status_code, 200)             # una intocable, igual con HEAD
        self.assertEqual(mw(RequestFactory().head("/api/reportes/boletines/")).status_code, 200)        # y lo que no se licencia (D-6)

    def test_lo_que_cierra_puertas_y_las_calificaciones_no_se_licencian(self):
        """D-6: las políticas de acceso (interruptores del registro de profesores, autorregistro y visitantes) y los boletines y exportaciones de reportes siguen disponibles."""
        instantanea_degradada(self)
        for metodo, ruta in (("get", "/api/acceso/politicas/"), ("get", "/api/reportes/boletines/"), ("post", "/api/reportes/exportaciones/alcance/"), ("get", "/api/reportes/exportaciones/x1/"),
                             ("get", "/api/acceso/visitantes/")):
            r = getattr(self.admin, metodo)(ruta, **({"data": {}, "format": "json"} if metodo == "post" else {}))
            self.assertNotEqual(r.status_code, 402, (ruta, r.content))
        r = self.admin.put("/api/acceso/politicas/TEACHER/", {}, format="json")
        self.assertNotEqual(r.status_code, 402)

    def test_los_modulos_que_la_licencia_no_habilita_responden_402_aunque_este_activa(self):
        self.activar_ok(capacidades=frozenset({"reportes"}))
        self.assertNotEqual(self.admin.get("/api/reportes/clases/").status_code, 402)
        self.assertEqual(self.admin.get("/api/search/status/").status_code, 402)
        self.assertEqual(self.estado()["capacidades"], {"habilitadas": ["reportes"], "no_disponibles": ["administracion_avanzada", "busqueda", "importacion"]})


class ListaBlancaTests(BaseLicencia):
    """R-01: «lista blanca derivada de los `urls.py` reales, no de una enumeración»."""

    def test_las_rutas_intocables_salen_de_los_urls_reales_y_cubren_lo_que_dice_el_prompt(self):
        todas = rutas_reales()
        self.assertGreater(len(todas), 240)
        intocables = {ruta for ruta, _ in todas if rutas.es_intocable(ruta)}
        # todo el aula, todo el modo estudio y la propia licencia, sin excepción
        for prefijo in ("/api/aula/", "/api/modo-estudio/", "/api/licencia/"):
            delprefijo = {ruta for ruta, _ in todas if ruta.startswith(prefijo)}
            self.assertTrue(delprefijo, prefijo)
            self.assertEqual(delprefijo - intocables, set(), prefijo)
        for ruta in ("/health/", "/api/dispositivos/latido/", "/api/logs/clientes/", "/api/acceso/sesiones/", "/api/acceso/instalacion/", "/api/acceso/docentes/registro/",
                     "/api/acceso/estudiantes/registro/", "/api/evaluacion/estudiantes/", "/api/evaluacion/mias/"):
            self.assertIn(ruta, intocables, ruta)
        # la evaluación mientras se presenta: abrir el examen, responder, latido, incidentes, bloqueo, entregar, resultado
        for fragmento in ("antesala", "intentos"):
            self.assertTrue(any(re.fullmatch(rf"/api/evaluacion/asignaciones/[^/]+/{fragmento}/", r) for r in intocables), fragmento)
        for fragmento in ("estado", "latido", "preguntas", "medios", "respuestas", "incidentes", "bloqueo", "entregar", "resultado"):
            self.assertTrue(any(re.fullmatch(rf"/api/evaluacion/intentos/[^/]+/{fragmento}/(?:.*)?", r) for r in intocables), fragmento)
        # lo licenciable NO está en la lista blanca, y ninguna ruta es las dos cosas
        licenciables = {ruta for ruta, metodos in todas for metodo in metodos if rutas.capacidad_de(metodo, ruta)}
        self.assertEqual(licenciables & intocables, set())
        self.assertTrue(any(r.startswith("/api/reportes/clases") for r in licenciables) and any(r.startswith("/api/search/") for r in licenciables))

    def test_con_la_licencia_degradada_cada_ruta_intocable_responde_igual_que_sin_licencia(self):
        todas = [(ruta, metodo) for ruta, metodos in rutas_reales() if rutas.es_intocable(ruta) and not ruta.startswith("/api/licencia/") for metodo in metodos]
        self.assertGreaterEqual(len(todas), 90)
        cliente = APIClient(raise_request_exception=False)

        def pasar() -> dict:
            salida = {}
            for ruta, metodo in todas:
                r = getattr(cliente, metodo.lower())(ruta, **({"data": {}, "format": "json"} if metodo in ("POST", "PUT", "PATCH", "DELETE") else {}))
                salida[(ruta, metodo)] = r.status_code
            return salida
        with override_settings(AVACOM_LICENCIA_MODO="auto", AVACOM_LICENCIA_ENTORNO="pruebas"):          # sin licencia: modo ilimitada
            sin_licencia = pasar()
        instantanea_degradada(self)                                                                       # y ahora, firmada y degradada
        degradada = pasar()
        self.assertEqual({k: (sin_licencia[k], degradada[k]) for k in degradada if degradada[k] != sin_licencia[k]}, {})      # lo único que cambiaría es la licencia: nada cambia
        self.assertNotIn(402, set(degradada.values()))
        # la propia licencia depende del estado POR DISEÑO (no se puede liberar lo que no hay), pero jamás se apaga con la licencia degradada: sin ella no se podría renovar
        for ruta, metodos in rutas_reales():
            if ruta.startswith("/api/licencia/"):
                for metodo in metodos:
                    r = getattr(cliente, metodo.lower())(ruta, **({"data": {}, "format": "json"} if metodo == "POST" else {}))
                    self.assertNotEqual(r.status_code, 402, (ruta, metodo))
        # y la misma lista, que SÍ habría respondido 402 de ser licenciable, confirma que la licencia está degradada de verdad
        self.assertEqual(cliente.get("/api/reportes/clases/").status_code, 402)

    def test_las_rutas_que_cargan_colas_del_cliente_nunca_responden_402_r_02(self):
        """El cliente descarta su cola ante cualquier 4xx: un 402 de licencia en estas rutas BORRARÍA respuestas de alumnos."""
        instantanea_degradada(self)
        cliente = APIClient(raise_request_exception=False)
        for metodo, ruta in (("post", "/api/evaluacion/intentos/i1/respuestas/"), ("post", "/api/evaluacion/intentos/i1/latido/"), ("post", "/api/evaluacion/intentos/i1/incidentes/"),
                             ("post", "/api/evaluacion/intentos/i1/entregar/"), ("post", "/api/modo-estudio/sync/"), ("post", "/api/aula/sesiones/s1/distribuciones/d1/enviar/"),
                             ("post", "/api/aula/sesiones/unirse/"), ("post", "/api/dispositivos/latido/"), ("post", "/api/logs/clientes/")):
            self.assertNotEqual(getattr(cliente, metodo)(ruta, {}, format="json").status_code, 402, ruta)


class FalloInternoYCaminoCalienteTests(BaseLicencia):
    def peticion(self, ruta="/api/reportes/estado/", metodo="get"):
        return getattr(RequestFactory(), metodo)(ruta)

    @staticmethod
    def vista(request):
        return HttpResponse("ok")

    def test_un_fallo_interno_de_licenciamiento_deja_pasar_la_peticion_r_04(self):
        instantanea_degradada(self)                                                                       # con la licencia degradada esta ruta sería un 402…
        mw = LicenciaMiddleware(self.vista)
        self.assertEqual(mw(self.peticion()).status_code, 402)
        for objetivo in ("licenciamiento.servicios.capacidad_habilitada", "licenciamiento.dominio.rutas.capacidad_de", "licenciamiento.servicios.registrar_bloqueo_de_modulo"):
            with self.subTest(objetivo), mock.patch(objetivo, side_effect=RuntimeError("falla la licencia")):
                self.assertEqual(mw(self.peticion()).status_code, 200)                                 # …pero si algo falla DENTRO de licenciamiento, pasa
        with mock.patch("licenciamiento.infraestructura.contenedor.servicios", side_effect=RuntimeError("sin contenedor")):
            self.assertEqual(mw(self.peticion()).status_code, 200)
            self.assertTrue(servicios.capacidad_habilitada("reportes"))                                # y la fachada responde «sí» sin lanzar

    def test_sin_estado_todavia_el_nodo_deja_pasar_y_la_evaluacion_es_la_de_la_politica(self):
        self.assertIsNone(self.s.vivo.leer())
        self.assertTrue(servicios.capacidad_habilitada("reportes"))
        self.assertEqual(LicenciaMiddleware(self.vista)(self.peticion()).status_code, 200)

    def test_una_licencia_que_no_se_puede_evaluar_conserva_el_ultimo_estado_bueno(self):
        buena = self.evaluar("arranque")
        with mock.patch("licenciamiento.aplicacion.evaluar.Evaluar._leer", side_effect=RuntimeError("base caída")):
            devuelta = self.evaluar("tick")
        self.assertIs(devuelta, buena)
        self.assertIs(self.s.vivo.leer(), buena)

    def test_el_camino_caliente_no_consulta_la_base_de_datos_r_07(self):
        self.activar_ok()
        self.evaluar("tick")
        mw = LicenciaMiddleware(self.vista)
        with self.assertNumQueries(0):
            self.assertEqual(mw(self.peticion()).status_code, 200)                                    # una petición permitida
            self.assertEqual(mw(self.peticion("/api/aula/sesiones/")).status_code, 200)                # una intocable
            self.assertTrue(servicios.capacidad_habilitada("reportes"))
            self.assertEqual(servicios.concurrencia(50, 100), (50, 100))
            self.assertEqual(servicios.estado_resumido()["estado"], "activa")
            servicios.exigir_equipo_nuevo(10)                                                         # el cupo se decide con el número que trae quien llama
            servicios.exigir_usuario_nuevo(10)

    def test_y_tampoco_cuando_bloquea(self):
        instantanea_degradada(self)
        mw = LicenciaMiddleware(self.vista)
        with self.assertNumQueries(0):
            for _ in range(20):
                self.assertEqual(mw(self.peticion()).status_code, 402)

    def test_las_peticiones_que_no_son_de_modulos_licenciables_ni_miran_el_estado(self):
        mw = LicenciaMiddleware(self.vista)
        with mock.patch("licenciamiento.servicios.capacidad_habilitada", side_effect=AssertionError("no debía consultarse")):
            for ruta in ("/api/aula/sesiones/", "/health/", "/api/acceso/yo/", "/api/gradebook/libro/"):
                self.assertEqual(mw(self.peticion(ruta)).status_code, 200, ruta)

    def test_decenas_de_clientes_a_la_vez_no_chocan_con_el_programador(self):
        """Sin «database is locked»: 40 hilos piden módulos permitidos y bloqueados mientras el programador evalúa y asienta."""
        instantanea_degradada(self)
        errores: list[str] = []
        mw = LicenciaMiddleware(self.vista)

        def cliente(n: int):
            try:
                for i in range(60):
                    estado = mw(self.peticion("/api/reportes/estado/" if i % 2 else "/api/aula/sesiones/")).status_code
                    if estado != (402 if i % 2 else 200):
                        errores.append(f"hilo {n}: {estado}")
            except Exception as error:   # noqa: BLE001
                errores.append(f"hilo {n}: {error!r}")

        hilos = [threading.Thread(target=cliente, args=(n,)) for n in range(40)]
        for h in hilos:
            h.start()
        for _ in range(3):
            self.evaluar("tick")
        for h in hilos:
            h.join(30)
        self.assertEqual(errores, [])
