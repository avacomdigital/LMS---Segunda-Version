"""
Los valores del dominio de Search (MOD-021): tipos de entidad, permisos, estados del índice, eventos y límites. Son VALORES, no tablas: nada de esto describe
contenido de un curso (artículo 14).

Qué se busca y dónde vive cada cosa:

  curso · lección · recurso     del CATÁLOGO de AVACOM Biblioteca. El LMS no los guarda (artículo 14): se preguntan EN VIVO a la biblioteca en cada consulta (su
                                `GET /v2/search`) y lo que ella retira deja de aparecer en ese mismo instante. Aquí sólo se les aplica el permiso `content.read`.
  evaluación · estudio · clase  del LMS (MOD-010, MOD-008 y MOD-007). Se indexan en `m21_documento` (SQLite FTS5) a partir de los eventos de sus colas de salida.
"""
from __future__ import annotations

SISTEMA = "sistema"

# ------------------------------------------------------------------------------------------------ tipos de entidad
CURSO, LECCION, RECURSO = "course", "lesson", "resource"
EVALUACION, ESTUDIO, CLASE = "assessment", "study", "class"
TIPOS_DE_CATALOGO = (CURSO, LECCION, RECURSO)
TIPOS_LOCALES = (EVALUACION, ESTUDIO, CLASE)
TIPOS = TIPOS_DE_CATALOGO + TIPOS_LOCALES

ROTULOS_DE_TIPO = {
    CURSO: "Curso", LECCION: "Lección", RECURSO: "Recurso", EVALUACION: "Evaluación", ESTUDIO: "Estudio asignado", CLASE: "Clase",
}

# El permiso de LECTURA del módulo propietario de cada tipo (BR-088: la búsqueda sólo devuelve lo que el usuario puede leer). Sin él, el tipo no se busca.
PERMISO_DE_LECTURA = {
    CURSO: "content.read", LECCION: "content.read", RECURSO: "content.read",
    EVALUACION: "assessment.read",
    ESTUDIO: "study.assignment.review",
    CLASE: "classroom.results.view",
}

# ------------------------------------------------------------------------------------------------ permisos propios
P_CONSULTAR = "search.query"
P_REINDEXAR = "search.reindex"
PERMISOS = (P_CONSULTAR, P_REINDEXAR)

# ------------------------------------------------------------------------------------------------ alcances (los de MOD-001)
ORGANIZACION, GRUPOS, PROPIO = "ORGANIZATION", "GROUPS", "SELF"

# ------------------------------------------------------------------------------------------------ estados del índice
CONSTRUYENDOSE, CONSULTABLE, REZAGADO, RECONSTRUYENDOSE = "construyendose", "consultable", "rezagado", "reconstruyendose"
ESTADOS_DEL_INDICE = (CONSTRUYENDOSE, CONSULTABLE, REZAGADO, RECONSTRUYENDOSE)
# Los que se GUARDAN: «rezagado» no se guarda, se DERIVA (hay eventos sin aplicar o el último ciclo falló) para que nunca quede un estado viejo.
ESTADOS_GUARDADOS = (CONSTRUYENDOSE, CONSULTABLE, RECONSTRUYENDOSE)
AVISOS_DEL_INDICE = {
    CONSTRUYENDOSE: "El índice de búsqueda se está construyendo: por ahora pueden faltar resultados.",
    CONSULTABLE: "",
    REZAGADO: "El índice de búsqueda va un poco atrás: los resultados podrían no incluir los cambios más recientes.",
    RECONSTRUYENDOSE: "El índice de búsqueda se está reconstruyendo: los resultados podrían estar incompletos unos instantes.",
}
# Una reconstrucción que lleva más de esto sin terminar se considera abandonada (el nodo se apagó a la mitad): se puede volver a pedir.
RECONSTRUCCION_ABANDONADA_MS = 10 * 60 * 1000

# ------------------------------------------------------------------------------------------------ fuentes de eventos (una por módulo propietario)
FUENTE_EVALUACION, FUENTE_ESTUDIO, FUENTE_AULA = "evaluacion", "estudio", "aula"
FUENTE_DE_TIPO = {EVALUACION: FUENTE_EVALUACION, ESTUDIO: FUENTE_ESTUDIO, CLASE: FUENTE_AULA}

# ------------------------------------------------------------------------------------------------ eventos `busqueda.*.v1` (Documento Maestro, sección L)
EV_ENTIDAD_INDEXADA = "busqueda.entidad_indexada.v1"                   # FUN-209
EV_TEXTO_INDEXADO = "busqueda.texto_indexado.v1"                       # FUN-210 (V1: texto interno de archivos)
EV_REINDEXACION_INCREMENTAL = "busqueda.reindexacion_incremental.v1"   # FUN-214
EV_INDICE_RECONSTRUIDO = "busqueda.indice_reconstruido.v1"             # FUN-215
EV_EXTRACCION_ENCOLADA = "busqueda.extraccion_encolada.v1"             # FUN-216 (V1)
EV_ENTRADAS_PURGADAS = "busqueda.entradas_purgadas.v1"                 # FUN-217
EVENTOS = (EV_ENTIDAD_INDEXADA, EV_TEXTO_INDEXADO, EV_REINDEXACION_INCREMENTAL, EV_INDICE_RECONSTRUIDO, EV_EXTRACCION_ENCOLADA, EV_ENTRADAS_PURGADAS)
# Los que HOY se emiten. Los dos de V1 (texto de archivos) están declarados y NO se emiten: no hay extracción de texto todavía, y un evento sin hecho es mentira.
EVENTOS_QUE_SE_EMITEN = (EV_ENTIDAD_INDEXADA, EV_REINDEXACION_INCREMENTAL, EV_INDICE_RECONSTRUIDO, EV_ENTRADAS_PURGADAS)

# ------------------------------------------------------------------------------------------------ acciones de la bitácora (MOD-019)
A_INDICE_RECONSTRUIDO = "busqueda.indice_reconstruido"
A_APERTURA_DENEGADA = "busqueda.apertura_denegada"
A_SINONIMOS_CONFIGURADOS = "busqueda.sinonimos_configurados"
A_EVENTO_OMITIDO = "busqueda.evento_omitido"

# ------------------------------------------------------------------------------------------------ límites
MIN_CONSULTA = 2                 # caracteres normalizados: «a» no es una búsqueda, es ruido
MAX_CONSULTA = 120
MAX_VALOR_FILTRO = 80
LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 50
PAGINA_MAXIMA = 40
TOPE_DE_CANDIDATOS = 300         # lo máximo que se trae del índice por consulta, antes de verificar en vivo y paginar
TOPE_DEL_CATALOGO = 100          # lo máximo que se pide a la biblioteca por consulta
LOTE_DE_EVENTOS = 200
MAX_FALLOS_DE_EVENTO = 5         # un evento que no se puede aplicar se reintenta esto de ciclos; luego se deja atrás CON un asiento en la bitácora
MAX_PALABRAS_DE_LA_CONSULTA = 12
MAX_SINONIMOS = 500

# Pesos de las columnas del índice para `bm25(...)`: el título manda, luego las palabras clave, la descripción y el contexto.
PESOS = {"titulo": 10.0, "palabras": 6.0, "descripcion": 2.0, "contexto": 1.0}

# Los códigos de error que Search comparte con los demás módulos (el mismo contrato de degradación).
COD_SIN_PERMISO = "sin_permiso"
COD_FUERA_DE_ALCANCE = "fuera_de_alcance"

# ------------------------------------------------------------------------------------------------ sinónimos que se siembran (configurables después)
# Palabras que quien enseña usa como si fueran una: grupos de equivalentes ya normalizados. Son de Search, no del contenido; la administración los cambia con
# `PUT /api/search/synonyms/`. Es un punto de partida prudente, no un diccionario: sólo equivalencias que casi nunca se contradicen.
SINONIMOS_POR_DEFECTO = (
    ("examen", "evaluacion", "prueba"),
    ("matematicas", "mates"),
    ("lengua", "lenguaje"),
    ("ingles", "english"),
    ("clase", "sesion"),
    ("leccion", "tema"),
)
