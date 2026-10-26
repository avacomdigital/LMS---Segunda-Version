using System.Globalization;
using System.Text;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Licencia;

/// <summary>Un mensaje listo para la pantalla: un título corto, qué pasó y qué hacer.</summary>
public sealed record MensajeDeLicencia(string Titulo, string Texto, string? Accion = null)
{
    public string Completo => string.IsNullOrWhiteSpace(Accion) ? Texto : $"{Texto} {Accion}";
}

/// <summary>Cómo suena un aviso: informa, pide atención o avisa de algo que ya está en pausa. Nunca es una alarma: ningún aviso de licencia interrumpe una clase (R-01).</summary>
public enum TonoDeAviso { Informativo, Atencion, Fuerte }

/// <summary>
/// TODOS los textos de la licencia (MOD-018), para que OPS, Student y las pruebas digan lo mismo: el título y la frase de cada estado, la vigencia con fechas en español, la huella, cada
/// bandera y cada aviso, cada motivo de rechazo y cada código de error con su acción, el texto común de los dos 402 (<see cref="ParaError"/>), los tres pasos de la activación, la
/// copia de custodia con su hoja (CAP-111), la liberación (con MSG-063) y la confirmación de la fecha. Puro y sin MAUI. Quien lee es una persona frente a una pantalla táctil de 86",
/// sin teclado: frases cortas, sin jerga ni códigos, y siempre qué hacer.
/// </summary>
public static class LicenciaTexto
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-ES");

    // ================================================================================================== fechas y días

    private static DateTimeOffset Local(long ms, TimeZoneInfo? zona) => TimeZoneInfo.ConvertTime(DateTimeOffset.FromUnixTimeMilliseconds(ms), zona ?? TimeZoneInfo.Local);

    /// <summary>«12 de octubre de 2027».</summary>
    public static string Fecha(long ms, TimeZoneInfo? zona = null) => Local(ms, zona).ToString("d 'de' MMMM 'de' yyyy", Es);

    /// <summary>«12 de octubre de 2027 a las 10:42».</summary>
    public static string FechaYHora(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.ToString("d 'de' MMMM 'de' yyyy", Es)} a las {l.ToString("HH:mm", CultureInfo.InvariantCulture)}";
    }

    /// <summary>«357 días», «1 día».</summary>
    public static string Dias(int dias) => dias == 1 ? "1 día" : $"{Math.Max(0, dias)} días";

    /// <summary>«quedan 357 días», «queda 1 día», «hoy es el último día».</summary>
    public static string Quedan(int dias) => dias switch { <= 0 => "hoy es el último día", 1 => "queda 1 día", _ => $"quedan {dias} días" };

    private static string Mayuscula(string texto) => string.IsNullOrEmpty(texto) ? texto : char.ToUpper(texto[0], Es) + texto[1..];

    // ================================================================================================== el estado

    /// <summary>El título grande del estado.</summary>
    public static string Titulo(EstadoLicencia e)
    {
        if (e.Ilimitada) return "Modo de desarrollo: sin licencia";
        return (e.Estado, e.Motivo) switch
        {
            (EstadosDeLicencia.SinLicencia, MotivosDeEstado.AunNoVigente) => "La licencia todavía no empieza",
            (EstadosDeLicencia.SinLicencia, _) => "Sin licencia · periodo de evaluación",
            (EstadosDeLicencia.Activa, _) => "Licencia activa",
            (EstadosDeLicencia.Reactivada, _) => "Licencia reactivada",
            (EstadosDeLicencia.EnGracia, MotivosDeEstado.HuellaDistinta) => "Licencia de otro equipo · periodo de gracia",
            (EstadosDeLicencia.EnGracia, _) => "Licencia vencida · periodo de gracia",
            (EstadosDeLicencia.LiberacionPendiente, _) => "Licencia en espera de liberación",
            (EstadosDeLicencia.Degradada, MotivosDeEstado.EvaluacionVencida) => "Terminó la evaluación · algunas funciones en pausa",
            (EstadosDeLicencia.Degradada, MotivosDeEstado.HuellaDistinta) => "Licencia de otro equipo · algunas funciones en pausa",
            (EstadosDeLicencia.Degradada, MotivosDeEstado.LiberacionNoConfirmada) => "Liberación sin confirmar · algunas funciones en pausa",
            (EstadosDeLicencia.Degradada, MotivosDeEstado.Vencida) => "Licencia vencida · algunas funciones en pausa",
            (EstadosDeLicencia.Degradada, _) => "Algunas funciones en pausa por la licencia",
            _ => "Estado de la licencia",
        };
    }

    /// <summary>Una etiqueta corta del estado, para una píldora: «Activa», «En evaluación», «Vencida · en gracia»…</summary>
    public static string EstadoBreve(EstadoLicencia e)
    {
        if (e.Ilimitada) return "Modo de desarrollo";
        return (e.Estado, e.Motivo) switch
        {
            (EstadosDeLicencia.SinLicencia, MotivosDeEstado.AunNoVigente) => "Todavía no empieza",
            (EstadosDeLicencia.SinLicencia, _) => "En evaluación",
            (EstadosDeLicencia.Activa, _) => "Activa",
            (EstadosDeLicencia.Reactivada, _) => "Reactivada",
            (EstadosDeLicencia.EnGracia, MotivosDeEstado.HuellaDistinta) => "Otro equipo · en gracia",
            (EstadosDeLicencia.EnGracia, _) => "Vencida · en gracia",
            (EstadosDeLicencia.LiberacionPendiente, _) => "Liberación pendiente",
            (EstadosDeLicencia.Degradada, _) => "Funciones en pausa",
            _ => "Sin datos",
        };
    }

    /// <summary>Cómo suena el estado: lo sano informa, lo que vence o espera pide atención, lo que ya tiene funciones en pausa es fuerte.</summary>
    public static TonoDeAviso TonoDelEstado(EstadoLicencia e) => e.Ilimitada ? TonoDeAviso.Informativo : e.Estado switch
    {
        EstadosDeLicencia.Activa or EstadosDeLicencia.Reactivada => TonoDeAviso.Informativo,
        EstadosDeLicencia.SinLicencia => e.Vigencia?.DiasRestantes is <= 7 ? TonoDeAviso.Atencion : TonoDeAviso.Informativo,
        EstadosDeLicencia.Degradada => TonoDeAviso.Fuerte,
        _ => TonoDeAviso.Atencion,
    };

    /// <summary>La frase del estado, con fechas y días en español: «Vence el 12 de octubre de 2027 · quedan 357 días.»</summary>
    public static string Frase(EstadoLicencia e, TimeZoneInfo? zona = null)
    {
        if (e.Ilimitada) return "En desarrollo y en pruebas este equipo no verifica ninguna licencia y nada se restringe. Un aula instalada sí la verifica.";
        var v = e.Vigencia;
        var dias = v?.DiasRestantes;
        string? hasta = v?.Hasta is { } h ? Fecha(h, zona) : null;
        string? vence = (v?.Vence ?? e.Licencia?.Vence) is { } ve ? Fecha(ve, zona) : null;
        string? desde = (v?.Desde ?? e.Licencia?.Desde) is { } de ? Fecha(de, zona) : null;
        string Hasta() => hasta is null ? string.Empty : $", hasta el {hasta}";
        switch (e.Estado, e.Motivo)
        {
            case (EstadosDeLicencia.SinLicencia, MotivosDeEstado.AunNoVigente):
                return (desde is null ? "La licencia instalada todavía no empieza." : $"La licencia instalada empieza el {desde}.")
                       + (dias is { } d0 ? $" Mientras tanto sigue la evaluación: {Quedan(d0)}." : " Mientras tanto sigue la evaluación.");
            case (EstadosDeLicencia.SinLicencia, _):
                return "Este equipo funciona completo mientras dura la evaluación"
                       + (dias is { } d1 ? $": {Quedan(d1)}{Hasta()}." : ".")
                       + " Activa la licencia antes de que termine para que nada se ponga en pausa.";
            case (EstadosDeLicencia.Activa or EstadosDeLicencia.Reactivada, _):
            {
                var previo = e.Estado == EstadosDeLicencia.Reactivada ? "Se volvió a instalar en este equipo después de una restauración. " : string.Empty;
                if (vence is null) return previo + "La licencia está en uso.";
                return previo + $"Vence el {vence}" + (dias is { } d2 ? $" · {Quedan(d2)}." : ".");
            }
            case (EstadosDeLicencia.EnGracia, MotivosDeEstado.HuellaDistinta):
                return "Este equipo no coincide con el de la licencia (¿se cambió el equipo o una pieza?). "
                       + (dias is { } d3 ? $"Todo sigue funcionando {Dias(d3)} más{Hasta()}. " : "Todo sigue funcionando por ahora. ")
                       + "Pide a AVACOM una licencia para este equipo.";
            case (EstadosDeLicencia.EnGracia, _):
                return (vence is null ? "La licencia venció. " : $"La licencia venció el {vence}. ")
                       + (dias is { } d4 ? $"Todo sigue funcionando {Dias(d4)} más{Hasta()}: " : "Todo sigue funcionando por ahora: ")
                       + "renuévala antes de que algunas funciones se pongan en pausa.";
            case (EstadosDeLicencia.LiberacionPendiente, _):
                return Msg063(dias ?? e.Licencia?.LiberacionDias ?? 0);
            case (EstadosDeLicencia.Degradada, MotivosDeEstado.EvaluacionVencida):
                return "Terminó el periodo de evaluación y este equipo todavía no tiene licencia. " + NucleoSigue + " Los módulos con licencia están en pausa hasta que la actives.";
            case (EstadosDeLicencia.Degradada, MotivosDeEstado.HuellaDistinta):
                return "La licencia es de otro equipo y terminó el periodo de gracia. " + NucleoSigue + " Los módulos con licencia están en pausa: pide a AVACOM una licencia para este equipo.";
            case (EstadosDeLicencia.Degradada, MotivosDeEstado.LiberacionNoConfirmada):
                return "La licencia se emitió mientras se liberaba el equipo anterior y el plazo terminó. " + NucleoSigue
                       + " Los módulos con licencia están en pausa: entrega a AVACOM el archivo de liberación del equipo anterior.";
            case (EstadosDeLicencia.Degradada, _):
                return (vence is null ? "La licencia venció y terminó el periodo de gracia. " : $"La licencia venció el {vence} y terminó el periodo de gracia. ")
                       + NucleoSigue + " Los módulos con licencia están en pausa hasta que la renueves.";
            default:
                return "El aula informó un estado de la licencia que esta versión de OPS no conoce. " + NucleoSigue + " Actualiza AVACOM OPS o avisa a soporte técnico.";
        }
    }

    /// <summary>Lo que NUNCA se pone en pausa por la licencia (R-01, P-07): se dice siempre que algo esté en pausa.</summary>
    public const string NucleoSigue = "Las clases, las evaluaciones y el modo de estudio siguen igual.";

    /// <summary>MSG-063: licencia emitida mientras el equipo anterior se libera.</summary>
    public static string Msg063(int dias) => $"Puedes seguir instalando y dar clase {Dias(dias)} mientras se libera. Esta licencia está en uso en otra aula.";

    /// <summary>«Del 1 de octubre de 2026 al 12 de octubre de 2027 · 30 días de gracia»; sin licencia, null.</summary>
    public static string? Vigencia(EstadoLicencia e, TimeZoneInfo? zona = null)
    {
        var desde = e.Vigencia?.Desde ?? e.Licencia?.Desde;
        var vence = e.Vigencia?.Vence ?? e.Licencia?.Vence;
        if (desde is null || vence is null) return null;
        var gracia = e.Vigencia?.GraciaDias ?? e.Licencia?.GraciaDias;
        return $"Del {Fecha(desde.Value, zona)} al {Fecha(vence.Value, zona)}" + (gracia is { } g && g > 0 ? $" · {Dias(g)} de gracia" : string.Empty);
    }

    /// <summary>El tipo de licencia en palabras.</summary>
    public static string Tipo(string? tipo) => tipo switch
    {
        TiposDeLicencia.Produccion => "Producción",
        TiposDeLicencia.Evaluacion => "Evaluación",
        TiposDeLicencia.Desarrollo => "Desarrollo (sólo para pruebas)",
        null or "" => "Sin licencia",
        _ => "Otro tipo",
    };

    /// <summary>El nivel de la huella en una palabra: «Hardware» o «Instalación (más débil)».</summary>
    public static string NivelDeHuella(string? nivel) => nivel switch
    {
        NivelesDeHuella.Hardware => "Hardware",
        NivelesDeHuella.Instalacion => "Instalación (más débil)",
        _ => "Sin datos",
    };

    /// <summary>La huella explicada: a qué se selló la licencia y cuántas piezas del equipo coinciden. Nunca un identificador.</summary>
    public static string Huella(HuellaDelEquipo? h)
    {
        if (h is null) return "El aula no informó la huella de este equipo.";
        var instalacion = h.Nivel == NivelesDeHuella.Instalacion;
        if (h.Coincide is null)
            return instalacion
                ? "Este equipo no tiene datos de hardware fiables: su licencia se sellará a una huella de instalación, más débil que la de hardware."
                : "Este equipo tiene datos de hardware suficientes para sellar su licencia.";
        var cifras = h is { Coinciden: { } c, Factores: { } f, K: { } k } ? $"coinciden {c} de {f} piezas y hacen falta {k}" : null;
        if (h.Coincide == false)
            return "Este equipo no coincide con el de la licencia" + (cifras is null ? "." : $": {cifras}.");
        var texto = instalacion
            ? "Esta licencia se selló a una huella de instalación: es más débil que la de hardware."
            : "La licencia está sellada al hardware de este equipo" + (cifras is null ? "." : $": {cifras}.");
        return h.Parcial ? texto + " Una pieza del equipo cambió y la licencia sigue valiendo." : texto;
    }

    /// <summary>Lo que significa cada bandera y qué hacer.</summary>
    public static string Bandera(string bandera) => bandera switch
    {
        BanderasDeLicencia.RelojSospechoso => "La fecha de este equipo cambió de golpe. Nada se pone en pausa por eso: si la fecha de hoy es la correcta, confírmala.",
        BanderasDeLicencia.RelojAdelantado => "La fecha de este equipo está adelantada y el aula no la aceptó: la licencia sigue contando con la fecha real y nada se pone en pausa por eso. " +
            "Corrígela en la configuración de Windows; si la fecha del equipo es la correcta, confírmala.",
        BanderasDeLicencia.HuellaParcial => "Una pieza del equipo cambió y la licencia sigue valiendo. Si cambian más piezas, habrá que pedir una licencia nueva.",
        BanderasDeLicencia.IntegridadAlterada => "Cambiaron archivos del programa del aula. Todo sigue funcionando; avisa a soporte técnico para que lo revise.",
        _ => "El aula marcó algo de la licencia que esta versión no conoce. Avisa a soporte técnico.",
    };

    /// <summary>La bandera en dos o tres palabras, para una píldora.</summary>
    public static string BanderaBreve(string bandera) => bandera switch
    {
        BanderasDeLicencia.RelojSospechoso => "Fecha por confirmar",
        BanderasDeLicencia.RelojAdelantado => "Fecha adelantada",
        BanderasDeLicencia.HuellaParcial => "Una pieza cambió",
        BanderasDeLicencia.IntegridadAlterada => "Programa modificado",
        _ => "Otra señal",
    };

    // ================================================================================================== los módulos

    /// <summary>El nombre de un módulo licenciable.</summary>
    public static string Capacidad(string? codigo) => codigo switch
    {
        CapacidadesLicenciables.Reportes => "Reportes",
        CapacidadesLicenciables.Busqueda => "Búsqueda",
        CapacidadesLicenciables.Importacion => "Importación de usuarios",
        CapacidadesLicenciables.AdministracionAvanzada => "Administración avanzada",
        _ => "Otro módulo",
    };

    /// <summary>Qué hace un módulo licenciable, en una línea.</summary>
    public static string DescripcionDeCapacidad(string? codigo) => codigo switch
    {
        CapacidadesLicenciables.Reportes => "Reportes de clases, estudiantes, grupos y uso. Los boletines y las exportaciones no se pausan.",
        CapacidadesLicenciables.Busqueda => "Buscar cursos, lecciones, evaluaciones y clases desde el menú principal.",
        CapacidadesLicenciables.Importacion => "Importar el padrón o muchos usuarios a la vez. Crear de uno en uno sigue funcionando.",
        CapacidadesLicenciables.AdministracionAvanzada => "Crear roles, escalas de calificación y reconstruir datos derivados.",
        _ => "Un módulo que esta versión de OPS no conoce.",
    };

    /// <summary>Lo que ninguna licencia apaga, para la tarjeta de módulos.</summary>
    public const string NuncaSePausa = "Nunca se pausan: las clases, las evaluaciones, el modo de estudio, el acceso al aula y la lectura de calificaciones.";

    // ================================================================================================== el consumo

    /// <summary>«1 de 55 equipos (2 %)», «3 usuarios · sin tope»; sin dato, «Sin datos».</summary>
    public static string Uso(UsoDelCupo? uso, string tipo)
    {
        var (singular, plural) = tipo == "equipos" ? ("equipo", "equipos") : ("usuario", "usuarios");
        if (uso?.EnUso is not { } enUso) return "Sin datos";
        if (uso.Limite is not { } limite) return $"{enUso} {(enUso == 1 ? singular : plural)} · sin tope";
        return $"{enUso} de {limite} {(limite == 1 ? singular : plural)}" + (uso.Porcentaje is { } p ? $" ({p} %)" : string.Empty);
    }

    /// <summary>«Hasta 50 conexiones a la vez (100 en un pico)».</summary>
    public static string Concurrencia(int? normal, int? pico)
    {
        if (normal is null && pico is null) return "Sin tope de conexiones a la vez.";
        if (normal is { } n && pico is { } p) return n == p ? $"Hasta {n} conexiones a la vez." : $"Hasta {n} conexiones a la vez ({p} en un pico).";
        return $"Hasta {normal ?? pico} conexiones a la vez.";
    }

    // ================================================================================================== los avisos

    /// <summary>
    /// El texto de un aviso (banner del menú principal y pantalla de Licencia). <paramref name="estado"/> aporta la fecha de vencimiento cuando el aviso sólo trae los días. Un código que esta
    /// versión no conoce no se calla: dice que hay un aviso y dónde verlo.
    /// </summary>
    public static string Aviso(AvisoDeLicencia aviso, EstadoLicencia? estado = null, TimeZoneInfo? zona = null)
    {
        var dias = aviso.Dias ?? estado?.Vigencia?.DiasRestantes ?? 0;
        switch (aviso.Codigo)
        {
            case AvisosDeLicencia.Degradada:
                return aviso.Motivo switch
                {
                    MotivosDeEstado.EvaluacionVencida => "Terminó la evaluación y este equipo no tiene licencia: algunas funciones están en pausa. Las clases siguen igual.",
                    MotivosDeEstado.HuellaDistinta => "La licencia es de otro equipo y algunas funciones están en pausa. Las clases siguen igual.",
                    MotivosDeEstado.LiberacionNoConfirmada => "La liberación del equipo anterior no se confirmó a tiempo y algunas funciones están en pausa. Las clases siguen igual.",
                    MotivosDeEstado.Vencida => "La licencia venció y algunas funciones están en pausa (Reportes, Búsqueda…). Las clases siguen igual.",
                    _ => "Algunas funciones están en pausa por la licencia. Las clases siguen igual.",
                };
            case AvisosDeLicencia.Gracia:
                return aviso.Motivo == MotivosDeEstado.HuellaDistinta
                    ? $"Este equipo no es el de la licencia: {Quedan(dias)} de gracia. Pide a AVACOM una licencia para este equipo."
                    : $"La licencia venció: {Quedan(dias)} de gracia. Renuévala antes de que algunas funciones se pongan en pausa.";
            case AvisosDeLicencia.LiberacionPendiente:
                return Msg063(dias);
            case AvisosDeLicencia.Evaluacion:
                return aviso.Urgente == true
                    ? $"Este equipo todavía no tiene licencia y {Quedan(dias)} de evaluación. Actívala cuanto antes para que nada se ponga en pausa."
                    : $"Este equipo todavía no tiene licencia: te {(dias == 1 ? "queda 1 día" : $"quedan {Math.Max(0, dias)} días")} de evaluación.";
            case AvisosDeLicencia.PorVencer:
            {
                var cuando = dias switch { <= 0 => "hoy", 1 => "mañana", _ => $"en {dias} días" };
                var fecha = (estado?.Vigencia?.Vence ?? estado?.Licencia?.Vence) is { } v ? $" (el {Fecha(v, zona)})" : string.Empty;
                return $"La licencia vence {cuando}{fecha}. Pide a AVACOM la renovación.";
            }
            case AvisosDeLicencia.Cupo:
                return Cupo(aviso);
            case AvisosDeLicencia.RelojAdelantado when aviso is { FechaEquipo: { } equipo, FechaEsperada: { } esperada }:
                return $"La fecha de este equipo ({FechaYHora(equipo, zona)}) está adelantada: el aula esperaba el {Fecha(esperada, zona)}. No se aceptó y nada se pone en pausa por eso. " +
                       "Corrígela en Windows.";
            case AvisosDeLicencia.RelojSospechoso:
            case AvisosDeLicencia.RelojAdelantado:
            case AvisosDeLicencia.HuellaParcial:
            case AvisosDeLicencia.IntegridadAlterada:
                return Bandera(aviso.Codigo);
            default:
                return "Hay un aviso de la licencia. Revisa la pantalla «Licencia».";
        }
    }

    private static string Cupo(AvisoDeLicencia aviso)
    {
        var equipos = aviso.Tipo != "usuarios";
        var que = equipos ? "equipos" : "usuarios";
        var cifras = aviso is { EnUso: { } u, Limite: { } l } ? $" ({u} de {l})" : string.Empty;
        if (aviso.Porcentaje is >= 100 || (aviso.EnUso is { } enUso && aviso.Limite is { } limite && enUso >= limite))
            return equipos
                ? $"Se llegó al cupo de equipos de la licencia{cifras}. Los que ya están registrados siguen funcionando; para sumar más hay que ampliar la licencia."
                : $"Se llegó al cupo de usuarios de la licencia{cifras}. Quienes ya tienen usuario siguen entrando; para crear más hay que ampliar la licencia.";
        var porcentaje = aviso.Porcentaje is { } p ? $"el {p} % del" : "casi todo el";
        return $"Se usa {porcentaje} cupo de {que} de la licencia{cifras}. Si van a llegar más, pide a AVACOM ampliar la licencia.";
    }

    /// <summary>Lo que el banner del menú principal añade al aviso: qué tocar.</summary>
    public static string LlamadaDelBanner(AvisoDeLicencia aviso) => aviso.Codigo switch
    {
        AvisosDeLicencia.Evaluacion => "Toca «Ver la licencia» para activarla.",
        AvisosDeLicencia.Degradada when aviso.Motivo == MotivosDeEstado.EvaluacionVencida => "Toca «Ver la licencia» para activarla.",
        AvisosDeLicencia.Gracia or AvisosDeLicencia.Degradada or AvisosDeLicencia.PorVencer => "Toca «Ver la licencia» para renovarla.",
        AvisosDeLicencia.RelojSospechoso => "Toca «Ver la licencia» para confirmar la fecha.",
        AvisosDeLicencia.RelojAdelantado => "Si es la correcta, toca «Ver la licencia» para confirmarla.",
        _ => "Toca «Ver la licencia» para ver qué hacer.",
    };

    /// <summary>«Hay 1 aviso más.» / «Hay 3 avisos más.»; sin más, vacío.</summary>
    public static string MasAvisos(int mas) => mas switch { <= 0 => string.Empty, 1 => "Hay 1 aviso más.", _ => $"Hay {mas} avisos más." };

    // ================================================================================================== los motivos de rechazo y los errores

    private const string NoSeInstalo = "La licencia no se instaló";

    /// <summary>Qué significa cada <c>motivo</c> de un 400 <c>licencia_invalida</c> y qué hacer.</summary>
    public static MensajeDeLicencia Motivo(string? motivo) => motivo switch
    {
        MotivosDeRechazo.FirmaInvalida => new(NoSeInstalo, "La firma de la licencia no es válida: el archivo fue modificado o no es de AVACOM.",
            "Usa el archivo tal como lo entregó AVACOM, sin abrirlo ni editarlo, o pide uno nuevo."),
        MotivosDeRechazo.KidDesconocido => new(NoSeInstalo, "La licencia fue firmada con una llave que este equipo no reconoce.",
            "Actualiza AVACOM OPS o pide a AVACOM una licencia para esta versión."),
        MotivosDeRechazo.VersionNoSoportada => new(NoSeInstalo, "Esta licencia usa una versión del formato que este equipo no entiende.",
            "Actualiza AVACOM OPS y vuelve a intentarlo."),
        MotivosDeRechazo.Formato => new(NoSeInstalo, "El archivo no tiene el formato de una licencia de AVACOM.",
            "Elige el archivo .avlic que entregó AVACOM."),
        MotivosDeRechazo.Texto => new(NoSeInstalo, "El texto no es una licencia completa.",
            "Usa el archivo .avlic que entregó AVACOM o copia el texto completo, sin cortes."),
        MotivosDeRechazo.DemasiadoGrande => new(NoSeInstalo, "El archivo es demasiado grande para ser una licencia.",
            "Elige el archivo .avlic que entregó AVACOM."),
        MotivosDeRechazo.DemasiadoCorta => new(NoSeInstalo, "El archivo está incompleto o dañado.",
            "Vuelve a copiarlo desde el original o pide a AVACOM que lo envíe otra vez."),
        MotivosDeRechazo.CampoFaltante => new(NoSeInstalo, "A la licencia le falta información obligatoria.",
            "Pide a AVACOM un archivo de licencia nuevo."),
        MotivosDeRechazo.CampoInvalido => new(NoSeInstalo, "La licencia trae un dato fuera de rango.",
            "Pide a AVACOM un archivo de licencia nuevo."),
        MotivosDeRechazo.EtiquetaCriticaDesconocida => new(NoSeInstalo, "La licencia exige algo que esta versión de OPS no entiende.",
            "Actualiza AVACOM OPS y vuelve a intentarlo."),
        MotivosDeRechazo.SolicitudAjena => new(NoSeInstalo, "La solicitud no fue generada por este equipo.",
            "Guarda una solicitud nueva desde este equipo (paso 1) y envíasela a AVACOM."),
        MotivosDeRechazo.SerieNoPosterior => new(NoSeInstalo, "Esta licencia no es más reciente que la que ya está instalada.",
            "Elige el archivo más nuevo que entregó AVACOM."),
        MotivosDeRechazo.OtraLicencia => new(NoSeInstalo, "Es otra licencia, distinta de la que está instalada.",
            "Para cambiarla, primero libera este equipo con «Liberar este equipo» y después actívala."),
        MotivosDeRechazo.SinLicenciaInstalada => new("Todavía no hay licencia instalada", "Este equipo todavía no tiene una licencia instalada.",
            "Usa «Activar o renovar» y elige el archivo de licencia."),
        MotivosDeRechazo.TipoNoAdmitido => new(NoSeInstalo, "Esa licencia no se puede usar en este equipo.",
            "Pide a AVACOM una licencia para este equipo."),
        MotivosDeRechazo.AunNoVigente => new(NoSeInstalo, "La licencia todavía no empieza según la fecha de este equipo.",
            "Revisa que la fecha y la hora del equipo estén bien y vuelve a intentarlo."),
        _ => new(NoSeInstalo, "El archivo no es una licencia válida.", "Pide a AVACOM un archivo de licencia nuevo."),
    };

    /// <summary>Lo que dice la pantalla de Licencia ante cualquier error del nodo o de la red: título, qué pasó y qué hacer. Nunca el código ni la palabra «error».</summary>
    public static MensajeDeLicencia DeError(ErrorAula? error)
    {
        if (error is null) return new("No se pudo completar", "El aula no contestó lo esperado.", "Vuelve a intentarlo.");
        if (error.Estado == 0 || error.Codigo == "sin_conexion")
            return new("Sin conexión con el aula", "No hay conexión con el equipo del aula.", "Revisa que esté encendido y en la misma red, y vuelve a intentarlo.");
        if (error.PorLicencia) return new("No disponible por la licencia", ParaError(error) ?? NucleoSigue);
        if (error.Estado == -1)
            return new("No se pudo completar", string.IsNullOrWhiteSpace(error.Detalle) ? "No se pudo completar en este equipo." : error.Detalle,
                string.IsNullOrWhiteSpace(error.Sugerencia) ? "Vuelve a intentarlo." : error.Sugerencia);
        if (error.Estado == 401 || error.SesionPerdida)
            return new("Tu sesión terminó", "El aula pide que vuelvas a identificarte.", "Vuelve a entrar con tu usuario.");
        var motivo = error.Texto("motivo");
        switch (error.Codigo)
        {
            case CodigosDeLicencia.LicenciaInvalida:
                return Motivo(motivo);
            case CodigosDeLicencia.HuellaNoCoincide:
            {
                var cifras = error.Numero("coinciden") is { } c && error.Numero("k") is { } k ? $": coinciden {c} de las {k} piezas necesarias" : string.Empty;
                return new("Esta licencia es de otro equipo", $"Fue emitida para otro equipo{cifras}.",
                    "Pide a AVACOM una licencia para este equipo: guarda la solicitud (paso 1) y envíasela.");
            }
            case CodigosDeLicencia.Conflicto when motivo == MotivosDeRechazo.SinLicenciaInstalada:
                return new("No hay licencia que liberar", "Este equipo no tiene una licencia instalada.", "No hace falta liberarlo.");
            case CodigosDeLicencia.Conflicto:
                return new("No se pudo completar", "La acción no encaja con el estado actual de la licencia.", "Toca «Actualizar» y vuelve a intentarlo.");
            case CodigosDeLicencia.NoEncontrado when motivo == MotivosDeRechazo.SinLicenciaInstalada:
                return new("No hay licencia que copiar", "Este equipo no tiene una licencia instalada.", "Activa la licencia primero.");
            case CodigosDeLicencia.NoEncontrado:
                return new("No se encontró", "El aula no encontró lo que se pidió.", "Toca «Actualizar» y vuelve a intentarlo.");
            case CodigosDeLicencia.SinPermiso:
                return error.Texto("permiso") switch
                {
                    PermisosDeLicencia.Renovar => new("Renovar es de la administración", "Tu rol no puede renovar la licencia.", "Pídeselo a la administración del colegio."),
                    PermisosDeLicencia.Activar => new("Tu rol no puede hacerlo", "Activar, liberar o confirmar la fecha lo hacen la administración y el soporte técnico.",
                        "Pídeselo a la administración del colegio."),
                    _ => new("Tu rol no ve la licencia", "La licencia la ven la administración y el soporte técnico.", "Si la necesitas, pídesela a la administración del colegio."),
                };
            case CodigosDeLicencia.DatosInvalidos:
                return new("El archivo no llegó completo", "El aula no recibió completo el archivo de licencia.", "Vuelve a elegirlo.");
        }
        if (error.Estado >= 500)
            return new("El aula no pudo completarlo", "El equipo del aula tuvo un problema al hacerlo.", "Espera un momento y vuelve a intentarlo. Las clases no se ven afectadas.");
        return new("No se pudo completar", string.IsNullOrWhiteSpace(error.Detalle) ? "El aula no lo permitió." : error.Detalle, "Vuelve a intentarlo.");
    }

    /// <summary>
    /// El texto COMÚN de los dos 402 de licencia, para cualquier pantalla que muestre un error (OPS y Student): <c>no_disponible_por_licencia</c> (un módulo en pausa; el permiso se
    /// conserva) y <c>cupo_agotado</c> (se llegó al cupo de equipos o de usuarios al CREAR algo nuevo; lo que ya existe sigue). Lo usa <see cref="ClienteJson"/> para que el motivo de
    /// cualquier cliente lo diga así sin parchear pantalla por pantalla. Null si el error no es de licencia. El personal (OPS) lee a quién le toca; el alumno (Student), a quién pedir ayuda.
    /// </summary>
    public static string? ParaError(ErrorAula? error, Audiencia audiencia = Audiencia.Personal)
    {
        if (error is null || !error.PorLicencia) return null;
        if (error.EsModuloNoDisponible)
        {
            if (audiencia == Audiencia.Alumno) return "Esto no está disponible ahora en el aula. Pídele ayuda a tu profesor.";
            var modulo = error.Texto("modulo") is { Length: > 0 } m ? m : error.Texto("capacidad") is { Length: > 0 } c ? Capacidad(c) : null;
            var cual = modulo is null ? "Este módulo no está disponible" : $"«{modulo}» no está disponible";
            return $"{cual} con la licencia de este equipo. Tu permiso se conserva: vuelve a funcionar cuando se renueve la licencia. " +
                   "Lo hace la administración del colegio en «Licencia», en el menú principal.";
        }
        var usuarios = error.Texto("tipo") == "usuarios";
        if (audiencia == Audiencia.Alumno)
            return usuarios
                ? "Ahora no se pueden crear usuarios nuevos en esta aula. Pídele ayuda a tu profesor; si ya tienes usuario, búscate en la lista."
                : "Esta tableta todavía no puede entrar al aula. Pídele ayuda a tu profesor.";
        var cifras = error.Numero("en_uso") is { } u && error.Numero("limite") is { } l ? $" ({u} de {l})" : string.Empty;
        return usuarios
            ? $"Se llegó al cupo de usuarios de la licencia{cifras}. Quienes ya tienen usuario siguen entrando; para crear más hay que ampliar la licencia con AVACOM. Lo gestiona la administración del colegio en «Licencia»."
            : $"Se llegó al cupo de equipos de la licencia{cifras}. Los equipos ya registrados siguen funcionando; para registrar más hay que ampliar la licencia con AVACOM. Lo gestiona la administración del colegio en «Licencia».";
    }

    // ================================================================================================== cargar la pantalla

    public const string Cargando = "Leyendo la licencia del equipo del aula…";
    public const string SoloAdministracion = "Esta pantalla es de la administración y del soporte técnico.";
    public const string SoloAdministracionDetalle = "Aquí se ve y se activa la licencia del equipo del aula. Entra con una cuenta de administración o de soporte técnico para verla.";
    public const string SinAccionesEnDesarrollo = "En modo de desarrollo no hay nada que activar, copiar ni liberar.";

    // ================================================================================================== activar o renovar en tres pasos (P-18)

    public const string ActivarTitulo = "Activar o renovar la licencia";
    public const string ActivarDescripcion = "En tres pasos, sin internet: guarda la solicitud, AVACOM la firma y eliges el archivo de licencia.";
    public const string Paso1Titulo = "1 · Guarda la solicitud de este equipo";
    public const string Paso1Texto = "Elige una memoria USB o una carpeta y guarda ahí la solicitud. Es un archivo pequeño (.avreq) que identifica a este equipo, sin datos de personas.";
    public const string Paso1YaTengo = "Si ya tienes el archivo de licencia (.avlic), pasa directo a elegirlo.";
    public const string Paso2Titulo = "2 · AVACOM firma tu licencia";
    public const string Paso2Texto = "Envía la solicitud a AVACOM. AVACOM te devuelve un archivo de licencia (.avlic) hecho sólo para este equipo. Esto se hace fuera de este programa.";
    public const string Paso3Titulo = "3 · Elige el archivo de licencia";
    public const string Paso3Texto = "Conecta la memoria con el archivo .avlic y tócalo en la lista; si no aparece, búscalo tú en el Explorador. El equipo del aula comprueba que sea de AVACOM y de este equipo antes de instalarlo.";
    public const string Buscando = "Buscando archivos de licencia en las memorias y carpetas de este equipo…";
    public const string SinArchivos = "No encontramos ningún archivo de licencia (.avlic) en las memorias conectadas ni en Documentos, Escritorio o Descargas.";
    public const string SinArchivosAccion = "Copia el archivo en la carpeta principal de una memoria USB, conéctala y toca «Buscar de nuevo», o toca «Buscar en el Explorador» para elegirlo en cualquier carpeta o disco.";
    public const string BuscarEnElExplorador = "Buscar en el Explorador…";
    public const string ArchivoDelExploradorNoVale = "El archivo que elegiste no es una licencia de AVACOM (.avlic) que se pueda leer: no tiene la marca de licencia, es demasiado grande o ya no se puede abrir.";
    public const string ArchivoDelExploradorNoValeAccion = "Elige el archivo .avlic que te devolvió AVACOM, sin cambiarle el nombre ni la extensión.";
    public const string Instalando = "Instalando la licencia. Las clases no se interrumpen.";
    public const string ArchivoYaNoEsta = "El archivo ya no está en ese lugar (¿se retiró la memoria?).";
    public const string ArchivoYaNoEstaAccion = "Vuelve a conectar la memoria y toca «Buscar de nuevo».";

    /// <summary>La frase del paso 1 cuando la solicitud quedó guardada.</summary>
    public static string SolicitudGuardada(string ruta) => $"La solicitud quedó guardada en {ruta}. Envíasela a AVACOM.";

    /// <summary>Lo que el paso 1 avisa cuando este equipo no tiene datos de hardware fiables (la solicitud viaja con una huella de instalación).</summary>
    public const string SolicitudConHuellaDeInstalacion =
        "Este equipo no tiene datos de hardware fiables: la solicitud usa una huella de instalación, más débil que la de hardware. AVACOM lo sabrá al emitir la licencia.";

    /// <summary>La confirmación ÚNICA antes de instalar: qué archivo, de dónde, y qué va a pasar.</summary>
    public static string Confirmacion(string nombre, string lugar, long modificadoMs, string via, TimeZoneInfo? zona = null) =>
        (via == ViasDeInstalacion.Renovar ? "Vas a renovar la licencia de este equipo con" : "Vas a instalar")
        + $" «{nombre}» ({lugar}, guardado el {FechaYHora(modificadoMs, zona)}). "
        + "Si es una licencia de AVACOM para este equipo, queda instalada al momento. Las clases no se interrumpen.";

    /// <summary>El resultado de instalar: qué hizo el nodo y el estado nuevo.</summary>
    public static MensajeDeLicencia ResultadoDeInstalacion(EstadoLicencia nuevo, TimeZoneInfo? zona = null) => nuevo.Accion switch
    {
        AccionesDeInstalacion.Renovada => new("Licencia renovada", Frase(nuevo, zona)),
        AccionesDeInstalacion.Reactivada => new("Licencia reactivada", "Era el mismo archivo que ya estaba instalado: se volvió a poner en uso. " + Frase(nuevo, zona)),
        _ => new("Licencia activada", Frase(nuevo, zona)),
    };

    // ================================================================================================== la copia de custodia (CAP-111)

    public const string CopiaTitulo = "Guardar una copia de la licencia";
    public const string CopiaDescripcion = "Guarda la licencia, una solicitud y una hoja que explica cómo volver a activarla.";
    public const string CopiaTexto = "Se guardan tres archivos en el lugar que elijas: la licencia (.avlic), una solicitud de este equipo (.avreq) y una hoja de texto que explica qué es cada uno y cómo volver a activarla.";
    public const string NombreDeLaHoja = "LEEME-licencia-AVACOM.txt";

    public static string CopiaGuardada(string carpeta) => $"La copia quedó guardada en {carpeta}. Guárdala en un lugar seguro.";

    /// <summary>
    /// La hoja de texto que acompaña a la copia (CAP-111): qué es cada archivo, cómo reactivar y la advertencia de guardarla en un lugar seguro. SIN datos de personas ni la huella del
    /// equipo: sólo el nombre del aula, la serie, las fechas, los nombres de los archivos y sus SHA-256 (para comprobar que no cambiaron).
    /// </summary>
    public static string HojaDeCustodia(CopiaDeLicencia copia, SolicitudDeLicencia solicitud, string nombreLicencia, string nombreSolicitud, long ahoraMs, TimeZoneInfo? zona = null)
    {
        var lic = copia.Licencia;
        var aula = string.IsNullOrWhiteSpace(lic?.Aula) ? "este equipo del aula" : lic!.Aula!.Trim();
        var t = new StringBuilder();
        void L(string linea = "") => t.Append(linea).Append("\r\n");
        L($"COPIA DE LA LICENCIA DE AVACOM · {aula}");
        L($"Guardada el {FechaYHora(ahoraMs, zona)} desde el equipo del aula.");
        L();
        L("QUÉ HAY AQUÍ");
        L($"• {nombreLicencia}: el archivo de licencia instalado en el equipo del aula" + (lic is null ? "." : $" (serie {lic.Serie}, vence el {Fecha(lic.Vence, zona)})."));
        L("  Sirve para volver a activarla en ese mismo equipo, por ejemplo después de restaurar una copia de seguridad.");
        L($"• {nombreSolicitud}: la solicitud de ese equipo. Si alguna vez hay que pedir a AVACOM una licencia nueva para él, envía este archivo.");
        L($"• {NombreDeLaHoja}: esta hoja.");
        L();
        L("CÓMO VOLVER A ACTIVAR LA LICENCIA");
        L("1. En AVACOM OPS, abre «Licencia» desde el menú principal (lo hace la administración o el soporte técnico).");
        L("2. Toca «Activar o renovar» y luego «Ya tengo el archivo de licencia».");
        L($"3. Conecta esta memoria, toca el archivo {nombreLicencia} y confirma.");
        L();
        L("GUÁRDALA EN UN LUGAR SEGURO");
        L("Esta copia no tiene datos de personas ni contraseñas, pero es la licencia del colegio: guárdala bajo llave junto con los papeles del equipo");
        L("y no la compartas fuera de la institución. La licencia sólo funciona en el equipo para el que se emitió.");
        L();
        L("PARA COMPROBAR QUE LOS ARCHIVOS NO CAMBIARON (SHA-256)");
        L($"{nombreLicencia}: {copia.Sha256}");
        L($"{nombreSolicitud}: {solicitud.Sha256}");
        return t.ToString();
    }

    // ================================================================================================== liberar este equipo (JRN-020)

    public const string LiberarTitulo = "Liberar este equipo";
    public const string LiberarDescripcion = "Para pasar la licencia a otro equipo. Se puede deshacer.";
    public const string LiberarQueEs = "Liberar sirve para pasar la licencia a otro equipo. Este equipo deja de usar la licencia y guarda un archivo de liberación (.avrel) para entregar a AVACOM.";
    public const string LiberarQuePasa = "Las clases, las evaluaciones y los datos no se tocan. Si ya pasó el periodo de evaluación de este equipo, Reportes, Búsqueda y los demás módulos con licencia se ponen en pausa.";
    public const string LiberarDeshacer = "Se puede deshacer: vuelve a activar en este equipo el mismo archivo de licencia.";
    public const string LiberarElegirDestino = "Primero elige dónde guardar el archivo de liberación.";
    public const string LiberarSinGuardar = "Este equipo quedó liberado, pero el archivo de liberación no se pudo guardar.";
    public const string LiberarSinGuardarAccion = "Elige otro destino para guardarlo: el archivo sigue en esta pantalla hasta que la cierres.";

    public static string LiberadaGuardada(string ruta) => $"Este equipo quedó liberado. El archivo de liberación quedó en {ruta}: entrégaselo a AVACOM.";

    // ================================================================================================== confirmar la fecha (P-06)

    public const string FechaTitulo = "Confirmar la fecha de hoy";
    public const string FechaDescripcion = "La fecha del equipo no coincide con la que el aula lleva: si la de hoy es la correcta, confírmala; si no, corrígela en Windows.";
    public const string FechaHecha = "Fecha confirmada. El aviso de la fecha se quitó.";

    /// <summary>
    /// La única confirmación: la fecha y la hora que tiene el equipo del aula (la adelantada que el aula no aceptó, Q-L13) y qué hacer si están mal. Sólo al confirmarla el aula la guarda;
    /// si se corrige la fecha en Windows, el aviso se quita solo.
    /// </summary>
    public static string ConfirmacionDeFecha(long ahoraDelNodoMs, TimeZoneInfo? zona = null) =>
        $"El equipo del aula tiene una fecha que no coincide con la que el aula llevaba. Si hoy es {FechaYHora(ahoraDelNodoMs, zona)}, confírmalo: el aviso se quita y el aula guarda esa fecha. " +
        "Si la fecha está mal, corrígela en la configuración de Windows en lugar de confirmar: el aviso se quita solo.";

    // ================================================================================================== escribir en la memoria

    public const string ElegirDestino = "Elige dónde guardarlo";
    public const string Guardando = "Guardando y comprobando el archivo…";
    public const string NoRetiresLaMemoria = "No retires la memoria hasta que termine.";
}
