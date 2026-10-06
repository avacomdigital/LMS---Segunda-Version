using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>Quién lee el mensaje: el personal (OPS, con documento y contraseña) o el alumno (Student, con su PIN). Cambia el sujeto de «no coinciden».</summary>
public enum Audiencia { Personal, Alumno }

/// <summary>
/// Los textos del §5 de los requisitos de acceso (UXR-005 y UXR-009): dicen qué pasó y qué sigue, sin códigos ni la palabra «error». Los comparten OPS y
/// Student para que la misma situación se diga igual en las dos apps, y viven en el Core para poder probarse contra el catálogo de códigos del §C.4.3.
/// </summary>
public static class MensajesDeAcceso
{
    public const string ContrasenaRestablecida = "Listo. Cerramos tus sesiones abiertas. Entra con tu nueva contraseña.";
    public const string AvisoVisitante = "Entraste como visitante. Lo que hagas no se guardará en tu historial.";
    public const string BandaVisitante = "Entraste como visitante: lo que hagas no se guarda en tu historial.";
    public const string PinPendiente = "Todavía no tienes PIN. Elige uno de 4 números que recuerdes.";
    public const string DesdeElEquipoDelProfesor = "Esto se hace desde el equipo del profesor.";
    public const string SinConexion = "No hay conexión con el aula. Revisa que el equipo del aula esté encendido y en la misma red.";
    public const string Generico = "No pudimos hacerlo ahora. Vuelve a intentarlo en un momento.";

    /// <summary>«Te quedan 3 intentos.» / «Te queda 1 intento.»</summary>
    public static string Intentos(long restantes) => restantes == 1 ? "Te queda 1 intento." : $"Te quedan {restantes} intentos.";

    /// <summary>Los minutos que se dicen en voz alta: siempre hacia arriba y nunca menos de uno.</summary>
    public static int Minutos(long segundos) => (int)Math.Max(1, (segundos + 59) / 60);

    public static string Texto(ErrorAula? error, Audiencia audiencia = Audiencia.Personal)
    {
        if (error is null) return Generico;
        if (error.Estado == 0) return SinConexion;
        switch (error.Codigo)
        {
            // ---------- PIN maestro
            case "pin_maestro_invalido":
                return "Ese PIN no es." + (error.IntentosRestantes is { } quedan ? " " + Intentos(quedan) : string.Empty);
            case "pin_maestro_bloqueado":
                return error.ReintentarEnSeg is { } segundos and > 0
                    ? $"Demasiados intentos desde este equipo. Vuelve a probar en {Minutos(segundos)} minutos."
                    : "Demasiados intentos desde este equipo. Espera unos minutos y vuelve a probar.";
            case "pin_maestro_vencido":
                return "El PIN maestro venció. Pídele a administración que lo cambie y vuelve a intentarlo.";
            case "pin_maestro_requerido":
                return "La administración entra además con el PIN maestro. Escríbelo para continuar.";
            case "pin_maestro_no_configurado":
                return "Este equipo todavía no tiene PIN maestro. Pídele a la administración que lo configure.";
            case "pin_debil":
                return "Ese PIN es demasiado fácil de adivinar: evita números repetidos, secuencias como 123456 y parejas repetidas.";
            case "pin_invalido":
                return "El PIN maestro son exactamente seis dígitos.";

            // ---------- dónde se hace
            case "dispositivo_no_autorizado":
                return audiencia == Audiencia.Alumno
                    ? "Esta tableta no está registrada en el aula. Pídele ayuda al profesor."
                    : DesdeElEquipoDelProfesor;
            case "dispositivo_bloqueado" or "dispositivo_inactivo":
                // UXR-007: la tableta nunca aparece bloqueada ni ocupada ante el alumno.
                return "No pudimos abrir tu sesión en esta tableta. Avisa a tu profesor; tu trabajo está a salvo.";

            // ---------- alumnos
            case "dispositivo_en_pausa":
                return error.ReintentarEnSeg is { } espera and > 0
                    ? $"Esperemos un momento: vuelve a probar en {Minutos(espera)} minutos, o entra como visitante."
                    : "Esperemos un momento: vuelve a probar en 2 minutos, o entra como visitante.";
            case "pin_pendiente":
                return PinPendiente;
            case "alias_duplicado":
            {
                var alias = error.Texto("alias");
                var sugerencia = error.Texto("sugerencia") ?? error.Sugerencia;
                var quien = string.IsNullOrWhiteSpace(alias) ? "alguien con ese nombre" : $"alguien llamado {alias}";
                return string.IsNullOrWhiteSpace(sugerencia)
                    ? $"Ya hay {quien} en este grupo. Añade una letra o tu apellido."
                    : $"Ya hay {quien} en este grupo. Añade una letra: {sugerencia}";
            }
            case "registro_cerrado":
                return error.Texto("motivo") == "tope_por_tableta"
                    ? "Esta tableta creó varios usuarios hace poco. Pídele ayuda al profesor."
                    : audiencia == Audiencia.Alumno
                        ? "Crear un usuario nuevo está apagado. Pídele al profesor que te anote en el grupo."
                        : "El registro de profesores está cerrado. Pídele a la administración que te cree el usuario.";
            case "visitante_no_permitido":
                return "Hoy no se puede entrar como visitante. Pídele ayuda al profesor.";
            case "sesion_visitante_limitada":
                return "Estás como visitante: esto no está disponible. Pídele a tu profesor que te anote en el grupo.";
            case "pin_ya_establecido":
                return "Ese nombre ya tiene PIN: escríbelo para entrar.";

            // ---------- identificarse
            case "credenciales_invalidas":
            {
                var basico = audiencia == Audiencia.Alumno
                    ? "Ese PIN no es."
                    : "Ese documento o esa clave no coinciden.";
                return error.IntentosRestantes is { } restantes and > 0 ? $"{basico} {Intentos(restantes)}" : basico;
            }
            case "usuario_bloqueado":
                return error.ReintentarEnSeg is { } bloqueo and > 0
                    ? $"Demasiados intentos. Vuelve a intentarlo en {Minutos(bloqueo)} min."
                    : audiencia == Audiencia.Alumno
                        ? "Demasiados intentos. Pide a tu profesor que te ayude."
                        : "Tu cuenta está bloqueada. Pide a la administración que la desbloquee.";
            case "demasiados_intentos":
                return error.Numero("reintentar_en_ms") is { } milisegundos and > 0
                    ? $"Demasiados intentos. Vuelve a intentarlo en {Minutos((milisegundos + 999) / 1000)} min."
                    : "Demasiados intentos. Espera unos minutos y vuelve a intentarlo.";
            case "no_instalado":
                return "Este equipo todavía no tiene la escuela instalada. Avisa a la administración.";

            // ---------- crear o recuperar la cuenta
            case "secreto_debil":
                return error.Reglas.Count > 0 ? string.Join(" ", error.Reglas) : "Esa clave no cumple lo que pide la escuela. Prueba con otra.";
            case "identificador_duplicado":
                return "Ese documento ya tiene un usuario. Si es tuyo, usa «Olvidé mi contraseña».";
            case "no_encontrado":
                return error.Estado == 404 && error.Detalle.Contains("profesor", StringComparison.OrdinalIgnoreCase)
                    ? "No encontramos un profesor con ese documento. Revisa que esté bien escrito."
                    : "No encontramos lo que buscabas. Vuelve a intentarlo.";
            case "datos_invalidos":
                return string.IsNullOrWhiteSpace(error.Detalle) ? Generico : error.Detalle;
            default:
                return Generico;
        }
    }
}
