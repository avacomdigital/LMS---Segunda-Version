using System.Globalization;
using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ops.Pages;

namespace Avacom.Lms.Ops.Examen;

/// <summary>
/// Las palabras del examen en OPS (MOD-010): niveles con la condición que lee el alumno, estados con nombre de persona, el reloj, las horas del nodo, los
/// incidentes en lenguaje de aula y los motivos prehechos. El nodo principal no tiene teclado: todo motivo que el backend pide se ofrece aquí como una frase
/// que se toca. Ninguna frase usa jerga ni nombres de módulo, y ninguna alarma al profesor: un examen no es un panel de vigilancia.
/// </summary>
internal static class ExamenTexto
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-CO");

    // ------------------------------------------------------------------------------------------------ niveles
    /// <summary>Lo que dice el nodo de un nivel (<c>CONDICIONES</c> de <c>backend/evaluacion/dominio/catalogos.py</c>): lo que lee el alumno y lo que ve el profesor.</summary>
    public sealed record Condicion(string Titulo, string TextoAlumno, string QueVes, string QueHaceElSistema);

    public static Condicion Condiciones(string? nivel) => Niveles.Normalizar(nivel) switch
    {
        Niveles.Controlado => new("Examen controlado",
            "Durante este examen tu tableta solo muestra el examen. Si sales, tu profesor lo verá, y tus respuestas se guardan igual.",
            "Estado por alumno e incidentes conforme ocurren, sin sonido ni alarma.",
            "El dispositivo queda dedicado al examen. Salir de la aplicación se registra como incidente informativo."),
        Niveles.Supervisado => new("Examen supervisado",
            "Puedes consultar los materiales que tu profesor dejó disponibles. Quedará registrado qué consultaste.",
            "Qué recursos consultó cada alumno y cuánto tiempo.",
            "El alumno puede consultar los recursos que el profesor habilitó. Las consultas quedan registradas."),
        _ => new("Examen abierto",
            "Este examen es de consulta libre. Solo se registra tu respuesta y el tiempo que tomaste.",
            "Avance y entregas, sin registro de conducta.",
            "Sin restricción de uso del dispositivo. Solo se registran entrega y tiempo."),
    };

    /// <summary>Los niveles más bajos que <paramref name="nivel"/>, del más exigente al más libre: lo que se puede elegir al admitir o al bajar el nivel.</summary>
    public static IReadOnlyList<string> NivelesMasBajos(string? nivel)
    {
        var rango = Niveles.Rango(nivel);
        return Niveles.Todos.Where(n => Niveles.Rango(n) < rango).OrderByDescending(Niveles.Rango).ToList();
    }

    public static string Capacidad(string? capacidad) => string.IsNullOrWhiteSpace(capacidad) ? "No declarada" : Niveles.Rotulo(capacidad);

    /// <summary>MSG-036, con el plural que corresponde: las tabletas que no alcanzan el nivel y la salida que tiene el profesor (admitirlas en un nivel menor o cambiarlas).</summary>
    public static string Msg036(int noAlcanzan, string? nivel)
    {
        var n = Niveles.Normalizar(nivel);
        return noAlcanzan == 1
            ? $"1 tableta no alcanza para el nivel {n}. Puedes admitirla en un nivel menor o cambiarla."
            : $"{noAlcanzan} tabletas no alcanzan para el nivel {n}. Puedes admitirlas en un nivel menor o cambiarlas.";
    }

    // ------------------------------------------------------------------------------------------- asignación
    public static string EstadoAsignacion(string? estado) => estado switch
    {
        "borrador" => "En borrador",
        "programada" => "Programado",
        "activa" => "Abierto",
        "activa_fuera_de_plazo" => "Abierto · pasó la fecha límite",
        "cerrada" => "Cerrado",
        "archivada" => "Archivado",
        _ => estado ?? "—",
    };

    public static Tono TonoAsignacion(string? estado) => estado switch
    {
        "activa" => Tono.Exito,
        "activa_fuera_de_plazo" => Tono.Ambar,
        "programada" => Tono.Info,
        _ => Tono.Gris,
    };

    public static string PlazoLegible(string? plazo) => plazo == "endurecido" ? "Plazo endurecido: cierra al vencer" : "Plazo blando: se sigue recibiendo";

    public static string ResultadosLegible(string? resultados) => resultados switch
    {
        "al_entregar" => "Los alumnos ven su resultado al entregar",
        "nunca" => "Los alumnos no ven su resultado",
        _ => "Tú liberas los resultados",
    };

    public static string Plural(int n, string singular, string plural) => n == 1 ? $"1 {singular}" : $"{n} {plural}";

    // ------------------------------------------------------------------------------------------------ horas
    /// <summary>El instante del nodo como hora local del equipo, «10:41:12». El nodo manda milisegundos; ninguna hora con valor académico sale del reloj de este equipo.</summary>
    public static string HoraCompleta(long ms) => EstudioTexto.Local(ms).ToString("HH:mm:ss", Es);

    /// <summary>«10:41 a. m.»</summary>
    public static string Hora(long ms) => EstudioTexto.Hora(EstudioTexto.Local(ms));

    /// <summary>El cronómetro de un intento: «12:34» o «1:02:03»; sin límite, «Sin límite». Nunca rojo, nunca parpadea.</summary>
    public static string Reloj(long? ms)
    {
        if (ms is null) return "Sin límite";
        var seg = Math.Max(0, ms.Value) / 1000;
        var h = seg / 3600;
        var m = seg % 3600 / 60;
        var s = seg % 60;
        return h > 0 ? $"{h}:{m:00}:{s:00}" : $"{m:00}:{s:00}";
    }

    /// <summary>«hace 38 s» o «hace 2 min»: cuánto lleva una tableta sin dar señal.</summary>
    public static string Silencio(long ms)
    {
        var seg = Math.Max(0, ms) / 1000;
        return seg < 60 ? $"{seg} s" : seg < 3600 ? $"{seg / 60} min" : $"{seg / 3600} h";
    }

    /// <summary>Una duración corta: «4 s», «2 min», «1 h 5 min».</summary>
    public static string Duracion(long ms)
    {
        var seg = Math.Max(0, ms) / 1000;
        if (seg < 60) return $"{seg} s";
        if (seg < 3600) return $"{seg / 60} min";
        var h = seg / 3600;
        var m = seg % 3600 / 60;
        return m == 0 ? $"{h} h" : $"{h} h {m} min";
    }

    public static string Porcentaje(double? valor) => valor is null ? "—" : $"{valor.Value.ToString("0.#", Es)} %";

    public static string Fecha(long? limite, long ahora) =>
        limite is null ? "Sin fecha límite" : limite.Value > ahora ? $"Cierra a las {Hora(limite.Value)}" : $"La fecha límite pasó a las {Hora(limite.Value)}";

    // ------------------------------------------------------------------------------------------ el intento
    /// <summary>El estado de un intento en palabras de aula. El nombre del enum nunca llega a la pantalla.</summary>
    public static string EstadoIntento(string? estado) => estado switch
    {
        "sin_intento" => "Todavía no empieza",
        "no_iniciado" => "Todavía no empieza",
        EstadosIntento.EnCurso => "Presentando",
        EstadosIntento.EnCursoFueraDePlazo => "Presentando · fuera de plazo",
        EstadosIntento.Pausado or EstadosIntento.Restaurando => "Esperando que lo reactives",
        EstadosIntento.Entregado => "Entregó",
        EstadosIntento.EnRevision => "Entregó · por revisar",
        EstadosIntento.Calificado => "Calificado",
        EstadosIntento.Anulado => "Anulado",
        _ => estado ?? "—",
    };

    public static Tono TonoIntento(string? estado) => estado switch
    {
        EstadosIntento.EnCurso or EstadosIntento.EnCursoFueraDePlazo => Tono.Info,
        EstadosIntento.Pausado or EstadosIntento.Restaurando => Tono.Ambar,
        EstadosIntento.Entregado or EstadosIntento.Calificado => Tono.Exito,
        EstadosIntento.EnRevision => Tono.Violeta,
        EstadosIntento.Anulado => Tono.Gris,
        _ => Tono.Neutro,
    };

    /// <summary>De dónde vino la entrega, en una frase.</summary>
    public static string OrigenEntrega(string? origen) => origen switch
    {
        "alumno" => "Lo entregó el alumno",
        "tiempo" => "Se entregó al acabarse el tiempo",
        "plazo" => "Se entregó al vencer el plazo",
        "profesor" => "Lo cerraste tú",
        "cierre" => "Se entregó al cerrar el examen",
        _ => string.Empty,
    };

    /// <summary>El renglón de «entregó» en la línea de tiempo, según de dónde vino la entrega.</summary>
    public static string EntregaEnLinea(string? origen, bool fueraDePlazo)
    {
        var texto = origen switch
        {
            "tiempo" => "El examen se entregó con lo que había respondido",
            "plazo" => "El examen se entregó con lo que había respondido",
            "profesor" => "Cerraste su examen y se entregó lo respondido",
            "cierre" => "Se cerró el examen y se entregó lo respondido",
            _ => "Entregó el examen",
        };
        return fueraDePlazo ? texto + " (fuera de plazo)" : texto;
    }

    /// <summary>El resultado del bloqueo que informó la tableta, en palabras de aula, o nulo si no hay nada que decir.</summary>
    public static string? Bloqueo(string? resultado) => resultado switch
    {
        ResultadosDeBloqueo.Parcial => "Bloqueo parcial: la tableta no tiene la capa del sistema",
        ResultadosDeBloqueo.Fallido => "Bloqueo no aplicado: la tableta no pudo bloquearse",
        ResultadosDeBloqueo.Liberado => "El bloqueo se soltó con el examen en marcha",
        _ => null,
    };

    public static string BloqueoCompleto(string? resultado) => resultado switch
    {
        ResultadosDeBloqueo.Aplicado => "Bloqueo aplicado como se pidió",
        ResultadosDeBloqueo.Parcial => "Bloqueo parcial: la tableta no tiene la capa del sistema",
        ResultadosDeBloqueo.Fallido => "Bloqueo no aplicado: la tableta no pudo bloquearse",
        ResultadosDeBloqueo.Liberado => "El bloqueo se soltó con el examen en marcha",
        _ => "La tableta todavía no informó el bloqueo",
    };

    // ------------------------------------------------------------------------------------- incidentes
    public static string SeveridadLegible(string? severidad) => severidad switch
    {
        "alta" => "Importante",
        "atencion" => "Atención",
        _ => "Informativa",
    };

    /// <summary>Informativa → neutro; atención → ámbar; alta → ámbar fuerte. Nunca rojo: un incidente se registra, no se castiga (BR-077).</summary>
    public static Tono TonoSeveridad(string? severidad) => severidad switch
    {
        "alta" => Tono.AmbarFuerte,
        "atencion" => Tono.Ambar,
        _ => Tono.Neutro,
    };

    /// <summary>Lo que ocurrió, en una frase de aula, a partir del tipo y de su detalle.</summary>
    public static string Incidente(string? tipo, JsonElement? detalle)
    {
        string? Texto(string clave) => Dato(detalle, clave);
        long? Numero(string clave) => DatoNumero(detalle, clave);
        return tipo switch
        {
            "intento_abierto" => Texto("nivel_efectivo") is { Length: > 0 } nivel ? $"Empezó el examen en nivel {Niveles.Rotulo(nivel)}" : "Empezó el examen",
            "pausa" => Texto("causa") switch
            {
                "reinicio_nodo" => "El aula se reinició: el tiempo quedó detenido",
                "manual" => "El examen quedó en pausa",
                _ => "Se perdió la señal de la tableta: el tiempo quedó detenido",
            },
            "salida_de_app" => "Salió de la aplicación",
            "regreso_a_app" => Numero("fuera_ms") is { } fuera and > 0 ? $"Volvió a la aplicación (estuvo fuera {Duracion(fuera)})" : "Volvió a la aplicación",
            "cierre_bloqueado" => "Intentó cerrar la aplicación y no se le dejó",
            "tecla_bloqueada" => Numero("veces") is { } veces and > 1 ? $"Pulsó {veces} teclas que están bloqueadas" : "Pulsó una tecla que está bloqueada",
            "pantalla_adicional" => "Hay otra pantalla conectada a la tableta",
            "bloqueo_parcial" => "El bloqueo se aplicó a medias en su tableta",
            "bloqueo_fallido" => "El bloqueo no se pudo aplicar en su tableta",
            "bloqueo_liberado" => "El bloqueo se soltó con el examen en marcha",
            "consulta_recurso" => "Consultó un material habilitado",
            "desconexion" => "Se perdió la señal de la tableta",
            "reconexion" => Numero("pausa_ms") is { } pausa and > 0 ? $"La tableta volvió a dar señal (estuvo {Duracion(pausa)} sin señal)" : "La tableta volvió a dar señal",
            "reinicio_nodo" => "El aula se reinició y el examen quedó en pausa",
            "cambio_de_dispositivo" => "Siguió desde otra tableta",
            "respuesta_tardia" => "Llegaron respuestas que la tableta había guardado sin señal",
            "reloj_desfasado" => "El reloj de la tableta no coincide con el del aula",
            "tiempo_agotado" => "Se acabó el tiempo del examen",
            "entrega_automatica" => "Venció la fecha límite y el examen se cerró",
            "reactivado" => "Se reactivó su examen",
            "degradacion" => Texto("a") is { Length: > 0 } a ? $"Se bajó el nivel del examen a {Niveles.Rotulo(a)}" : "Se bajó el nivel del examen",
            "admitido_bajo_nivel" => Texto("nivel_admitido") is { Length: > 0 } adm ? $"Lo admitiste en nivel {Niveles.Rotulo(adm)}" : "Lo admitiste con un nivel menor",
            "entregado" => "Entregó el examen",
            "anulado" => "Se anuló este intento",
            _ => tipo ?? "Sucedió algo",
        };
    }

    public static string? Dato(JsonElement? detalle, string clave) =>
        detalle is { ValueKind: JsonValueKind.Object } d && d.TryGetProperty(clave, out var v)
            ? v.ValueKind switch { JsonValueKind.String => v.GetString(), JsonValueKind.Number => v.ToString(), JsonValueKind.True => "true", JsonValueKind.False => "false", _ => null }
            : null;

    public static long? DatoNumero(JsonElement? detalle, string clave) =>
        detalle is { ValueKind: JsonValueKind.Object } d && d.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var n) ? n : null;

    // ------------------------------------------------------------------------------------------ personas
    /// <summary>
    /// A quién nombra un <c>anulado_por</c> o un <c>revisada_por</c>. El nodo guarda el identificador de la persona que firmó; si es quien está al frente de este
    /// equipo se dice su nombre, y si es el identificador del prototipo («docente-ms-carter») se vuelve legible. Cualquier otro identificador es de otra persona
    /// del profesorado o de la administración, y no hay forma de preguntar su nombre desde aquí.
    /// </summary>
    public static string Persona(string? id)
    {
        if (string.IsNullOrWhiteSpace(id)) return "una persona del profesorado";
        if (string.Equals(id, Sesion.ProfesorId, StringComparison.Ordinal)) return Sesion.ProfesorRotulo;
        if (id.StartsWith("docente-", StringComparison.OrdinalIgnoreCase))
        {
            var partes = id["docente-".Length..].Split('-', StringSplitOptions.RemoveEmptyEntries);
            return partes.Length == 0 ? "el profesor" : string.Join(' ', partes.Select(p => char.ToUpper(p[0], Es) + p[1..]));
        }
        return Guid.TryParse(id, out _) ? "otra persona del profesorado o de la administración" : id;
    }

    // -------------------------------------------------------------------------------------- motivos prehechos
    public const string OtroMotivo = "Otro motivo (se registra sin detalle)";

    public static readonly string[] MotivosAdmitir =
    [
        "La tableta no está aprovisionada",
        "No hay otra tableta disponible",
        "El alumno no trajo su tableta de siempre",
        OtroMotivo,
    ];

    public static readonly string[] MotivosRechazar =
    [
        "El alumno debe cambiar de tableta",
        "La tableta no es del alumno",
        "Prefiero que presente en otro momento",
        OtroMotivo,
    ];

    public static readonly string[] MotivosBajarNivel =
    [
        "La tableta no está aprovisionada",
        "Falla de red en el aula",
        "Varios alumnos no pueden entrar",
        OtroMotivo,
    ];

    public static readonly string[] MotivosCerrarExamen =
    [
        "Terminó el tiempo de la clase",
        "Todos los que iban a presentar ya terminaron",
        "Hubo un problema en el aula",
        OtroMotivo,
    ];

    public static readonly string[] MotivosAceptarEnvio =
    [
        "Hubo una falla de red",
        "El alumno respondió a tiempo",
        OtroMotivo,
    ];

    public static readonly string[] MotivosDescartarEnvio =
    [
        "Llegó después de cerrar",
        "No corresponde a este examen",
        OtroMotivo,
    ];

    public static readonly string[] MotivosAnular =
    [
        "Falla técnica que impidió presentar con normalidad",
        "Se presentó fuera de las condiciones acordadas",
        "El alumno lo pidió y estuvo de acuerdo",
        OtroMotivo,
    ];

    public static readonly string[] MotivosCambiarPuntaje =
    [
        "Volví a leer la respuesta",
        "Me equivoqué al puntuar",
        OtroMotivo,
    ];

    // --------------------------------------------------------------------------------------------- errores
    /// <summary>
    /// Un error del nodo en una frase tranquila (UXR-009): sin códigos, sin la palabra «error» y diciendo qué sigue. Lo que el nodo cuenta de más
    /// (<c>detail</c> y <c>sugerencia</c>) se conserva cuando es lo único que hay.
    /// </summary>
    public static string Error(ErrorAula? error, string? motivo)
    {
        if (error is { Estado: 0 }) return "No hay conexión con el aula. Revisa que el nodo esté encendido y vuelve a intentarlo.";
        var detalle = string.Join(" ", new[] { string.IsNullOrWhiteSpace(error?.Detalle) ? motivo : error!.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x)));
        return error?.Codigo switch
        {
            "fuente_no_disponible" => "AVACOM Biblioteca no está disponible. Abre la aplicación de contenido y vuelve a intentarlo.",
            "fuente_error" => "AVACOM Biblioteca respondió con un problema. Espera un momento y vuelve a intentarlo.",
            "no_instalado" => "El nodo todavía no tiene una organización instalada; sin ella no hay grupos ni alumnos.",
            "sin_permiso" or "no_es_el_titular" => "Sólo el profesor titular del grupo o la administración puede hacerlo.",
            "no_encontrado" => "Eso ya no existe en el aula. Vuelve atrás y actualiza la pantalla.",
            "intentos_abiertos" => "Todavía hay alumnos presentando. Cuando terminen, o cuando cierres el examen, podrás hacerlo.",
            "reactivos_pendientes" => $"{(string.IsNullOrWhiteSpace(error.Detalle) ? "Quedan reactivos sin puntuar." : error.Detalle)} Puntúalos y vuelve a publicar.",
            "demasiados_intentos" => "Demasiados intentos seguidos. Espera un momento y vuelve a probar.",
            _ => detalle.Length > 0 ? detalle : "No fue posible. Vuelve a intentarlo en un momento.",
        };
    }
}
