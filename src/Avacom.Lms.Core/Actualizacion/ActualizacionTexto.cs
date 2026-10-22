using System.Globalization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Actualizacion;

/// <summary>Lo que dice la pantalla ante un resultado o un error: título, qué pasó y qué hacer. Nunca el código ni la palabra «error».</summary>
public sealed record MensajeDeActualizacion(string Titulo, string Texto, string? Accion = null)
{
    public string Completo => string.IsNullOrWhiteSpace(Accion) ? Texto : $"{Texto} {Accion}";
}

/// <summary>Cómo suena un estado en la pantalla (el color nunca es el único aviso: siempre va con su texto).</summary>
public enum TonoDeActualizacion { Neutro, Info, Atencion, Bien }

/// <summary>Un motivo de la lista cerrada con que se revierte una actualización: la nota que viaja al nodo (obligatoria) se elige, nunca se escribe (OPS no tiene teclado).</summary>
public sealed record MotivoDeReversion(string Codigo, string Titulo, string Nota);

/// <summary>
/// Todos los textos del cliente de actualizaciones (MOD-017), en español claro y sin tecnicismos para quien administra el aula. Puro: sin MAUI y sin red, para probarlo contra las
/// respuestas reales del nodo. Los códigos del nodo (<see cref="CodigosDeActualizacion"/>, los <c>motivo</c> de un rechazo, los <c>tipo</c> del historial) se traducen aquí; un código que esta
/// versión no conoce se dice con una frase general, nunca se calla ni se muestra crudo.
/// </summary>
public static class ActualizacionTexto
{
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es");

    public const string Cargando = "Leyendo las actualizaciones del aula…";
    public const string SoloAdministracion = "Las actualizaciones las ven la administración y el soporte técnico.";
    public const string SoloAdministracionDetalle = "Si necesitas actualizar el aula, pídeselo a la administración del colegio.";
    public const string NucleoSigue = "Una clase abierta nunca se interrumpe: si hay una, la actualización espera a que termine.";
    public const string SinConexion = "Sin conexión con el aula";

    /// <summary>Lo que ve quien intenta iniciar una clase mientras el aula se actualiza (503 <c>actualizacion_en_curso</c>, sólo en el inicio de clases, R-01 · R-02).</summary>
    public const string EnCursoParaProfesor = "El aula se está actualizando; vuelve a intentarlo en unos minutos.";

    /// <summary>
    /// Lo que ve una tableta (P-20): lo mismo, dicho a quien no administra nada. Nunca bloquea a una tableta ya registrada: lo que el alumno hizo sigue guardado y su cola de respuestas se
    /// conserva (un 5xx no descarta nada), así que sólo se le pide esperar.
    /// </summary>
    public const string EnCursoParaTableta = "El aula se está actualizando; vuelve a intentarlo en unos minutos.";

    public const string EnCursoDetalleTableta = "Lo que hiciste está guardado. No necesitas hacer nada más que esperar.";

    // ================================================================================================== fechas y tamaños

    private static DateTime Local(long ms, TimeZoneInfo? zona) =>
        TimeZoneInfo.ConvertTime(DateTimeOffset.FromUnixTimeMilliseconds(ms), zona ?? TimeZoneInfo.Local).DateTime;

    /// <summary>«12 de octubre de 2027».</summary>
    public static string Fecha(long ms, TimeZoneInfo? zona = null) => Local(ms, zona).ToString("d 'de' MMMM 'de' yyyy", Es);

    /// <summary>«12 de octubre a las 22:00».</summary>
    public static string FechaYHora(long ms, TimeZoneInfo? zona = null)
    {
        var l = Local(ms, zona);
        return $"{l.ToString("d 'de' MMMM", Es)} a las {l.ToString("HH:mm", CultureInfo.InvariantCulture)}";
    }

    /// <summary>La hora sola, «22:00».</summary>
    public static string Hora(long ms, TimeZoneInfo? zona = null) => Local(ms, zona).ToString("HH:mm", CultureInfo.InvariantCulture);

    /// <summary>«hoy», «mañana» o la fecha, frente a <paramref name="ahoraMs"/> (la hora del nodo).</summary>
    public static string Dia(long ms, long ahoraMs, TimeZoneInfo? zona = null)
    {
        var dias = (Local(ms, zona).Date - Local(ahoraMs, zona).Date).Days;
        return dias switch
        {
            0 => "hoy",
            1 => "mañana",
            _ => Local(ms, zona).ToString("d 'de' MMMM", Es),
        };
    }

    /// <summary>«hoy de 22:00 a 23:00», «mañana de 06:00 a 07:30» o, si cruza de día, «del 12 de octubre a las 23:00 al 13 de octubre a las 00:30».</summary>
    public static string Ventana(VentanaDeActualizacion ventana, long ahoraMs, TimeZoneInfo? zona = null)
    {
        var d = Local(ventana.Desde, zona);
        var h = Local(ventana.Hasta, zona);
        if (d.Date == h.Date) return $"{Dia(ventana.Desde, ahoraMs, zona)} de {Hora(ventana.Desde, zona)} a {Hora(ventana.Hasta, zona)}";
        return $"del {FechaYHora(ventana.Desde, zona)} al {FechaYHora(ventana.Hasta, zona)}";
    }

    /// <summary>«1,8 KB», «64 MB», «1,2 GB». Con 0 o sin dato, «—».</summary>
    public static string Peso(long? bytes)
    {
        if (bytes is null or <= 0) return "—";
        double v = bytes.Value;
        string[] unidades = ["B", "KB", "MB", "GB", "TB"];
        var i = 0;
        while (v >= 1024 && i < unidades.Length - 1) { v /= 1024; i++; }
        var texto = i == 0 ? ((long)v).ToString(CultureInfo.InvariantCulture) : v >= 100 ? v.ToString("0", Es) : v.ToString("0.#", Es);
        return $"{texto} {unidades[i]}";
    }

    /// <summary>«13 días», «1 día», «menos de un día».</summary>
    public static string DiasHasta(long hastaMs, long ahoraMs)
    {
        var restante = hastaMs - ahoraMs;
        if (restante <= 0) return "ya pasó el plazo";
        var dias = (int)Math.Ceiling(restante / 86_400_000.0);
        if (restante < 86_400_000) return "menos de un día";
        return dias == 1 ? "1 día" : $"{dias} días";
    }

    // ================================================================================================== el estado del equipo

    /// <summary>El titular de la tarjeta del equipo.</summary>
    public static string TituloDelEstado(EstadoDeActualizacion e) => e.Aplicando
        ? "El aula se está actualizando"
        : e.ProgramadosOVacio.Count > 0 ? "Hay una actualización programada" : "El aula está al día";

    public static string FraseDelEstado(EstadoDeActualizacion e, long ahoraMs, TimeZoneInfo? zona = null)
    {
        if (e.EnCurso is { } curso)
            return curso.Accion == AccionesDeOrden.Revertir
                ? $"Se está volviendo a la versión anterior de «{curso.Nombre}». Iniciar una clase espera unos minutos; las que ya están abiertas siguen."
                : $"Se está aplicando «{curso.Nombre}». Iniciar una clase espera unos minutos; las que ya están abiertas siguen.";
        if (e.Aplicando) return "El aula está terminando de aplicar una actualización. Iniciar una clase espera unos minutos.";
        if (e.ProgramadosOVacio.FirstOrDefault() is { } p)
            return p.Ventana is { } v ? $"«{p.Nombre}» se aplica {Ventana(v, ahoraMs, zona)}, siempre que no haya una clase abierta." : $"«{p.Nombre}» está programada.";
        return "No hay nada pendiente. Cuando tengas un paquete de actualización de AVACOM en una memoria USB, aparecerá a la derecha.";
    }

    public static TonoDeActualizacion TonoDelEstado(EstadoDeActualizacion e) =>
        e.Aplicando ? TonoDeActualizacion.Atencion : e.ProgramadosOVacio.Count > 0 ? TonoDeActualizacion.Info : TonoDeActualizacion.Bien;

    /// <summary>«Versión 2.12.0 · contrato de la biblioteca 2».</summary>
    public static string Version(EstadoDeActualizacion e) =>
        string.IsNullOrWhiteSpace(e.Version) ? "Versión sin determinar" : $"Versión {e.Version}";

    /// <summary>La línea de un módulo: «1.0.0 · datos 20 · contrato 1».</summary>
    public static string Modulo(ModuloInstalado m) => $"{m.Version} · datos {m.VersionDatos} · contrato {m.VersionContrato}";

    /// <summary>El nombre que ve la persona de un módulo del nodo: el de su ficha si lo trae («MOD-017»), si no, el nombre técnico.</summary>
    public static string NombreDeModulo(ModuloInstalado m) => m.Nombre switch
    {
        "acceso" => "Acceso e identidad",
        "actualizacion" => "Actualizaciones",
        "audit" => "Auditoría y registros",
        "biblioteca" => "Biblioteca de AVACOM Contenido",
        "classroom_engine" => "Clase en vivo",
        "cola_medios" => "Cola de medios",
        "device_manager" => "Dispositivos",
        "evaluacion" => "Evaluación",
        "expediente" => "Expediente",
        "gradebook" => "Libro de calificaciones",
        "licenciamiento" => "Licencia",
        "modo_estudio" => "Modo estudio",
        "nodo" => "Plataforma del nodo",
        "reporting" => "Reportes",
        "search" => "Búsqueda",
        _ => m.Nombre.Replace('_', ' '),
    };

    public static string EspacioLibre(long? bytes) => bytes is null or <= 0 ? "—" : Peso(bytes);

    // ================================================================================================== un paquete

    /// <summary>La etiqueta corta del estado de un paquete.</summary>
    public static string EstadoDelPaquete(string? estado) => estado switch
    {
        EstadosDePaquete.Recibido => "Recibido",
        EstadosDePaquete.Verificado => "Listo para aplicar",
        EstadosDePaquete.Incompatible => "No compatible",
        EstadosDePaquete.Programado => "Programado",
        EstadosDePaquete.Aplicando => "Aplicándose",
        EstadosDePaquete.Aplicado => "Aplicado",
        EstadosDePaquete.Revertido => "Revertido",
        EstadosDePaquete.ReversionFallida => "Revisar con soporte",
        EstadosDePaquete.Archivado => "Archivado",
        _ => "Estado desconocido",
    };

    public static TonoDeActualizacion TonoDelPaquete(string? estado) => estado switch
    {
        EstadosDePaquete.Verificado or EstadosDePaquete.Aplicado => TonoDeActualizacion.Bien,
        EstadosDePaquete.Programado or EstadosDePaquete.Recibido => TonoDeActualizacion.Info,
        EstadosDePaquete.Incompatible or EstadosDePaquete.Aplicando or EstadosDePaquete.ReversionFallida => TonoDeActualizacion.Atencion,
        _ => TonoDeActualizacion.Neutro,
    };

    /// <summary>La frase que dice qué pasa con el paquete y qué sigue.</summary>
    public static string FraseDelPaquete(FichaDePaquete f, long ahoraMs, TimeZoneInfo? zona = null, bool puedeAplicar = true) => f.Estado switch
    {
        EstadosDePaquete.Verificado => puedeAplicar
            ? "Firma y contenido verificados. Puedes aplicarlo ahora o programarlo para una hora en que el aula esté libre."
            : "Firma y contenido verificados. La administración del colegio puede aplicarlo ahora o programarlo para una hora en que el aula esté libre.",
        EstadosDePaquete.Recibido => "El paquete llegó y se está verificando.",
        EstadosDePaquete.Incompatible => "El paquete es auténtico, pero no es compatible con lo que tiene instalado el aula; no se instala nada.",
        EstadosDePaquete.Programado => f.Ventana is { } v
            ? $"Se aplicará {Ventana(v, ahoraMs, zona)}, siempre que no haya una clase abierta. Si la hay, espera a que termine."
            : "Está programado.",
        EstadosDePaquete.Aplicando => f.Accion == AccionesDeOrden.Revertir
            ? "Se está volviendo a la versión anterior. Tarda unos minutos."
            : "Se está aplicando. Tarda unos minutos y el aula vuelve sola.",
        EstadosDePaquete.Aplicado => f.RevertibleHasta is { } hasta && hasta > ahoraMs
            ? $"Aplicado. Si algo falla, puedes volver a la versión anterior durante {DiasHasta(hasta, ahoraMs)}."
            : "Aplicado. Ya no se puede volver a la versión anterior desde aquí.",
        EstadosDePaquete.Revertido => "Se volvió a la versión anterior. El aula quedó como estaba antes de este paquete.",
        EstadosDePaquete.ReversionFallida => "No se pudo volver a la versión anterior sola. Nada se borró: el aula conserva una copia de sus datos. Avisa al soporte técnico de AVACOM.",
        EstadosDePaquete.Archivado => "Pasaron los 14 días: la versión anterior ya no se conserva.",
        _ => "El aula informó un estado que esta versión no conoce.",
    };

    /// <summary>Qué módulos cambia el paquete, en palabras: «Reportes», «Reportes y Búsqueda».</summary>
    public static string ModulosQueCambia(FichaDePaquete f)
    {
        var nombres = f.ModulosDelManifiesto.Select(m => NombreDeModulo(new ModuloInstalado(m.Nombre, null, m.Version, m.VersionDatos, m.VersionContrato, m.Serie, true))).ToList();
        if (nombres.Count == 0 && f.Modulos is { Count: > 0 } viejos)
            nombres = viejos.Select(n => NombreDeModulo(new ModuloInstalado(n, null, "", 0, 0, 0, true))).ToList();
        return nombres.Count switch
        {
            0 => "Sin módulos declarados",
            1 => nombres[0],
            _ => string.Join(", ", nombres.Take(nombres.Count - 1)) + " y " + nombres[^1],
        };
    }

    /// <summary>«Reportes 1.4.0 · 2 archivos».</summary>
    public static string LineaDeModulo(ModuloDelPaquete m) =>
        $"{NombreDeModulo(new ModuloInstalado(m.Nombre, null, m.Version, m.VersionDatos, m.VersionContrato, m.Serie, true))} {m.Version}" + (m.Migraciones is { Count: > 0 } mig ? $" · {mig.Count} cambio{(mig.Count == 1 ? "" : "s")} en los datos" : string.Empty) +
        (m.CambiaContrato ? " · cambia cómo se comunica con otros módulos" : string.Empty);

    /// <summary>«Necesita 64 MB libres; hay 500 GB.»</summary>
    public static string Espacio(FichaDePaquete f, EstadoDeActualizacion? estado)
    {
        var necesario = f.Historial?.Where(h => h.Tipo == TiposDeHistorial.Verificado).Select(h => h.Detalle).FirstOrDefault(d => d is { ValueKind: System.Text.Json.JsonValueKind.Object });
        long? requerido = null;
        if (necesario is { } d && d.TryGetProperty("compatibilidad", out var c) && c.ValueKind == System.Text.Json.JsonValueKind.Object
            && c.TryGetProperty("espacio_requerido", out var r) && r.ValueKind == System.Text.Json.JsonValueKind.Number && r.TryGetInt64(out var n)) requerido = n;
        if (requerido is null) return $"El paquete pesa {Peso(f.Bytes)}.";
        var libre = estado?.EspacioLibre;
        return libre is null ? $"Hacen falta {Peso(requerido)} libres (el paquete y las copias de seguridad)." : $"Hacen falta {Peso(requerido)} libres (el paquete y las copias de seguridad); hay {Peso(libre)}.";
    }

    // ================================================================================================== incompatibilidades y rechazos

    public static string Incompatibilidad(Incompatibilidad i) => i.Codigo switch
    {
        "version_minima_no_cumplida" => "El paquete pide una versión del aula más nueva que la instalada.",
        "serie_menor" => "El paquete es más antiguo que lo que el aula ya tiene: no se vuelve atrás con un paquete viejo.",
        "ya_aplicado" => "Este paquete ya está aplicado en el aula.",
        "modulo_desconocido" => "El paquete trae un módulo que este aula no tiene.",
        "modulo_no_actualizable" => "El paquete toca un módulo que sólo se actualiza con el instalador completo.",
        "version_datos_retrocede" => "El paquete dejaría los datos en una versión anterior a la que ya tienen.",
        "contrato_requerido" => "El paquete necesita de otro módulo una versión que el aula no tiene.",
        "contrato_incompatible" => "El paquete rompería la comunicación con otro módulo instalado.",
        "contrato_biblioteca" => "El paquete habla otra versión de AVACOM Contenido que la del aula.",
        "espacio_insuficiente" => "No hay espacio libre suficiente para aplicarlo con sus copias de seguridad.",
        "licencia" => "La licencia del aula no permite esta actualización.",
        _ => string.IsNullOrWhiteSpace(i.Detalle) ? "El paquete no es compatible con el aula." : i.Detalle!,
    };

    /// <summary>La frase de un rechazo (422) por su <c>motivo</c>, del catálogo cerrado del nodo (<c>MENSAJES_DE_MOTIVO</c>).</summary>
    public static MensajeDeActualizacion Rechazo(string? codigo, string? motivo)
    {
        if (codigo == CodigosDeActualizacion.FirmaInvalida)
        {
            return motivo switch
            {
                "sin_firma" => new("El paquete no está firmado", "El aula no instala nada que no venga firmado por AVACOM.", "Pide el paquete otra vez a AVACOM."),
                "kid_desconocido" => new("Firma que el aula no reconoce", "El paquete fue firmado con una llave que este equipo no conoce.", "Confirma con AVACOM que el paquete es para este aula."),
                "firma_invalida" => new("La firma no coincide", "El paquete fue alterado o está dañado: la firma no corresponde a su contenido.", "No se guardó nada. Pide el paquete otra vez a AVACOM."),
                _ => new("La firma del paquete no es válida", "El aula no pudo comprobar que el paquete viene de AVACOM.", "No se guardó nada. Pide el paquete otra vez a AVACOM."),
            };
        }
        return motivo switch
        {
            "demasiado_grande" => new("El paquete es demasiado grande", "El archivo supera el tamaño que el aula acepta para una actualización.", "Revisa que sea el archivo correcto."),
            "demasiado_corto" or "truncado" => new("El paquete está incompleto", "El archivo no se copió completo a la memoria.", "Cópialo otra vez a la memoria y vuelve a intentarlo."),
            "sha_distinto" or "tamano_distinto" or "bytes_sobrantes" => new("El paquete está dañado", "Un archivo del paquete no coincide con lo que AVACOM firmó.", "No se guardó nada. Pide el paquete otra vez a AVACOM."),
            "ruta_invalida" or "ruta_absoluta" or "ruta_con_retroceso" or "ruta_duplicada" or "ruta_fuera_del_modulo" or "ruta_intocable" or "extension_prohibida" =>
                new("El paquete trae algo que no se permite", "El paquete intenta escribir donde una actualización no puede escribir.", "No se instaló nada. Avisa a AVACOM."),
            "version_formato_desconocida" or "etiqueta_critica_desconocida" => new("Paquete de una versión más nueva", "Este aula todavía no sabe leer este tipo de paquete.", "Actualiza el aula con el instalador completo o pide a AVACOM un paquete compatible."),
            "producto_distinto" => new("El paquete no es de este producto", "El paquete es de otro producto de AVACOM.", "Revisa que sea el archivo correcto."),
            _ => new("El archivo no es un paquete válido", "El archivo no tiene la forma de un paquete de actualización de AVACOM.", "No se guardó nada. Pide el paquete otra vez a AVACOM."),
        };
    }

    // ================================================================================================== el historial

    /// <summary>La frase de una fila del historial.</summary>
    public static string Hecho(HechoDeHistorial h) => h.Tipo switch
    {
        TiposDeHistorial.Recibido => "El paquete llegó al aula",
        TiposDeHistorial.Verificado => "Firma y compatibilidad verificadas",
        TiposDeHistorial.Incompatible => "No es compatible con el aula",
        TiposDeHistorial.Rechazado => "Paquete rechazado: " + Rechazo(h.Texto("codigo"), h.Texto("motivo")).Titulo.ToLowerInvariant(),
        TiposDeHistorial.Programado => "Se programó una ventana",
        TiposDeHistorial.Desprogramado => "Se canceló la programación",
        TiposDeHistorial.VentanaVencida => "La ventana pasó sin aplicarse",
        TiposDeHistorial.Bloqueada => "Esperó porque había una clase abierta",
        TiposDeHistorial.Aplicando => h.Texto("accion") == AccionesDeOrden.Revertir ? "Empezó a volver a la versión anterior" : "Empezó a aplicarse",
        TiposDeHistorial.Aplicado => "Se aplicó con éxito",
        TiposDeHistorial.Revertido => h.Texto("accion") == AccionesDeOrden.Revertir ? "Se volvió a la versión anterior" : "Algo falló y el aula volvió sola a la versión anterior",
        TiposDeHistorial.ReversionFallida => "No se pudo volver atrás sola; el aula conserva una copia de sus datos",
        TiposDeHistorial.Aplazada => "Se aplazó porque había una clase abierta",
        TiposDeHistorial.Archivado => "Se archivó: pasaron los 14 días",
        _ => "Hubo un movimiento que esta versión no conoce",
    };

    public static TonoDeActualizacion TonoDelHecho(string tipo) => tipo switch
    {
        TiposDeHistorial.Aplicado or TiposDeHistorial.Verificado => TonoDeActualizacion.Bien,
        TiposDeHistorial.Incompatible or TiposDeHistorial.Rechazado or TiposDeHistorial.ReversionFallida or TiposDeHistorial.Bloqueada or TiposDeHistorial.Aplazada or TiposDeHistorial.Revertido =>
            TonoDeActualizacion.Atencion,
        _ => TonoDeActualizacion.Neutro,
    };

    // ================================================================================================== revertir (lista cerrada, sin teclado)

    public static readonly IReadOnlyList<MotivoDeReversion> MotivosDeReversion =
    [
        new("falla", "Algo dejó de funcionar", "Algo dejó de funcionar después de la actualización."),
        new("pantalla", "Una pantalla o un reporte sale mal", "Una pantalla o un reporte sale mal después de la actualización."),
        new("lento", "El aula quedó más lenta", "El aula quedó más lenta después de la actualización."),
        new("error", "Se aplicó por error", "La actualización se aplicó por error."),
        new("soporte", "Lo pidió el soporte de AVACOM", "El soporte de AVACOM pidió volver a la versión anterior."),
    ];

    // ================================================================================================== lo que dice la pantalla tras cada acción

    public static MensajeDeActualizacion Importado(FichaDePaquete f, bool puedeAplicar = true) => f.Estado == EstadosDePaquete.Incompatible
        ? new("El paquete llegó, pero no es compatible", string.Join(" ", f.IncompatibilidadesOVacio.Select(Incompatibilidad).Distinct()), "No se instala nada. Pide a AVACOM un paquete para esta versión del aula.")
        : new("Paquete verificado", $"«{f.Nombre}» está firmado por AVACOM y su contenido está completo.",
            puedeAplicar ? "Ahora puedes aplicarlo o programarlo." : "Ahora la administración del colegio puede aplicarlo o programarlo.");

    public static MensajeDeActualizacion Programado(FichaDePaquete f, long ahoraMs, TimeZoneInfo? zona = null) =>
        new("Actualización programada", f.Ventana is { } v ? $"Se aplicará {Ventana(v, ahoraMs, zona)}." : "La actualización quedó programada.", NucleoSigue);

    public static readonly MensajeDeActualizacion Desprogramado = new("Programación cancelada", "La actualización ya no se aplicará sola.", "Cuando quieras, puedes aplicarla o programarla de nuevo.");

    public static MensajeDeActualizacion Aplicando(FichaDePaquete f) => new("Aplicando la actualización",
        $"El aula tarda hasta {(f.Orden?.LimiteMinutos is { } m and > 0 ? m : 5)} minutos y vuelve sola. Iniciar una clase espera unos minutos; las que ya están abiertas siguen.", "No apagues el equipo del aula.");

    public static MensajeDeActualizacion Revirtiendo(FichaDePaquete f) => new("Volviendo a la versión anterior",
        $"El aula tarda hasta {(f.Orden?.LimiteMinutos is { } m and > 0 ? m : 5)} minutos y vuelve sola. Iniciar una clase espera unos minutos; las que ya están abiertas siguen.", "No apagues el equipo del aula.");

    /// <summary>Lo que dice la pantalla cuando una actualización que se estaba aplicando o revirtiendo termina: cómo quedó el aula.</summary>
    public static MensajeDeActualizacion Terminada(FichaDePaquete f) => f.Estado switch
    {
        EstadosDePaquete.Aplicado => new("La actualización terminó", $"«{f.Nombre}» se aplicó. El aula ya funciona con la versión nueva.", "Si algo falla, puedes volver a la versión anterior durante 14 días."),
        EstadosDePaquete.Revertido => new("El aula volvió a la versión anterior", $"«{f.Nombre}» no quedó aplicada y el aula quedó como estaba antes.", "No se perdió nada de lo que tenía el aula."),
        EstadosDePaquete.ReversionFallida => new("Hace falta soporte técnico", "El aula no pudo volver sola a la versión anterior. No se borró nada: conserva una copia de sus datos.", "Avisa al soporte técnico de AVACOM."),
        _ => new("La actualización terminó", FraseDelPaquete(f, 0), null),
    };

    // ================================================================================================== errores

    /// <summary>Lo que dice la pantalla de Actualizaciones ante cualquier error del nodo o de la red: título, qué pasó y qué hacer.</summary>
    public static MensajeDeActualizacion DeError(ErrorAula? error)
    {
        if (error is null) return new("No se pudo completar", "El aula no contestó lo esperado.", "Vuelve a intentarlo.");
        if (error.Estado == 0 || error.Codigo == "sin_conexion")
            return new(SinConexion, "No hay conexión con el equipo del aula.", "Revisa que esté encendido y en la misma red, y vuelve a intentarlo.");
        if (error.Estado == -1)
            return new("No se pudo completar", string.IsNullOrWhiteSpace(error.Detalle) ? "No se pudo completar en este equipo." : error.Detalle,
                string.IsNullOrWhiteSpace(error.Sugerencia) ? "Vuelve a intentarlo." : error.Sugerencia);
        if (error.Estado == 401 || error.SesionPerdida)
            return new("Tu sesión terminó", "El aula pide que vuelvas a identificarte.", "Vuelve a entrar con tu usuario.");
        if (error.PorLicencia)
            return new("No disponible por la licencia", error.Detalle);
        switch (error.Codigo)
        {
            case CodigosDeActualizacion.FirmaInvalida:
            case CodigosDeActualizacion.PaqueteInvalido:
                return Rechazo(error.Codigo, error.Texto("motivo"));
            case CodigosDeActualizacion.SesionActiva:
                return new("Hay una clase abierta", "Una clase en curso nunca se interrumpe, así que la actualización no se aplicó.",
                    "Espera a que la clase termine, o programa una hora en que el aula esté libre.");
            case CodigosDeActualizacion.ContratoIncompatible:
            {
                var lista = Incompatibilidades(error);
                return new("El paquete no es compatible", lista.Count > 0 ? string.Join(" ", lista.Select(Incompatibilidad)) : "El paquete no encaja con lo que tiene el aula.",
                    "No se instaló nada. Pide a AVACOM un paquete para esta versión del aula.");
            }
            case CodigosDeActualizacion.EspacioInsuficiente:
                return new("No hay espacio suficiente", $"Hacen falta {Peso(error.Numero("espacio_requerido"))} libres y hay {Peso(error.Numero("espacio_libre"))}.", "Libera espacio en el equipo del aula y vuelve a intentarlo.");
            case CodigosDeActualizacion.YaAplicado:
                return new("Ya está aplicado", "Este paquete ya está aplicado en el aula.", "No hace falta hacer nada.");
            case CodigosDeActualizacion.SerieMenor:
                return new("Paquete más antiguo", "El aula ya tiene una versión más nueva que la de este paquete.", "No se vuelve atrás con un paquete viejo.");
            case CodigosDeActualizacion.FueraDePlazoReversion:
                return new("Ya pasó el plazo", "Sólo se puede volver a la versión anterior durante 14 días después de aplicar.", "Pide ayuda al soporte técnico de AVACOM.");
            case CodigosDeActualizacion.EstadoInvalido:
                return new("No se puede hacer ahora", "Lo que pediste no encaja con el estado del paquete.", "Toca «Actualizar» y vuelve a intentarlo.");
            case CodigosDeActualizacion.EnCurso:
                return new("El aula se está actualizando", EnCursoParaProfesor, "Espera unos minutos.");
            case CodigosDeActualizacion.PaqueteRepetido:
                return new("Paquete repetido", "Ya hay un paquete con el mismo identificador y distinto contenido.", "Pide el paquete otra vez a AVACOM.");
            case CodigosDeActualizacion.NoEncontrado:
                return new("Ya no está", "El paquete ya no está en la memoria o en el aula.", "Vuelve a colocar la memoria y toca «Actualizar».");
            case CodigosDeActualizacion.DatosInvalidos:
                return new("No se pudo programar", string.IsNullOrWhiteSpace(error.Detalle) ? "La ventana elegida no es válida." : error.Detalle, "Elige otra hora.");
            case CodigosDeActualizacion.SinPermiso:
                return error.Texto("permiso") switch
                {
                    PermisosDeActualizacion.Aplicar => new("Aplicar es de la administración", "Aplicar o revertir una actualización lo hace la administración (el soporte técnico, con una autorización temporal).",
                        "Pídeselo a la administración del colegio."),
                    PermisosDeActualizacion.Programar => new("Programar es de la administración", "Programar una ventana lo hace la administración del colegio.", "Pídeselo a la administración."),
                    PermisosDeActualizacion.Importar => new("Tu rol no puede importar", "Traer un paquete al aula lo hacen la administración y el soporte técnico.", "Pídeselo a la administración."),
                    _ => new("Tu rol no ve las actualizaciones", SoloAdministracion, SoloAdministracionDetalle),
                };
        }
        if (error.Estado >= 500)
            return new("El aula no pudo responder", "El equipo del aula tuvo un problema.", "Espera un momento y vuelve a intentarlo.");
        return new("No se pudo completar", string.IsNullOrWhiteSpace(error.Detalle) ? "El aula no contestó lo esperado." : error.Detalle, "Vuelve a intentarlo.");
    }

    /// <summary>La lista <c>incompatibilidades[]</c> de un 409 <c>contrato_incompatible</c> o <c>espacio_insuficiente</c>.</summary>
    public static IReadOnlyList<Incompatibilidad> Incompatibilidades(ErrorAula error)
    {
        if (error.Extra is not { ValueKind: System.Text.Json.JsonValueKind.Object } raiz || !raiz.TryGetProperty("incompatibilidades", out var lista) || lista.ValueKind != System.Text.Json.JsonValueKind.Array)
            return [];
        var salida = new List<Incompatibilidad>();
        foreach (var item in lista.EnumerateArray())
        {
            if (item.ValueKind != System.Text.Json.JsonValueKind.Object) continue;
            var codigo = item.TryGetProperty("codigo", out var c) && c.ValueKind == System.Text.Json.JsonValueKind.String ? c.GetString() : null;
            if (string.IsNullOrEmpty(codigo)) continue;
            string? Cadena(string clave) => item.TryGetProperty(clave, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.String ? v.GetString() : null;
            salida.Add(new Incompatibilidad(codigo, Cadena("modulo"), Cadena("detalle")));
        }
        return salida;
    }

    /// <summary>
    /// El texto con que cualquier pantalla dice «el aula se está actualizando» ante un error del nodo, o null si el error es otra cosa. Sirve a OPS al iniciar una clase y a Student
    /// al unirse: lo que la persona hizo no se pierde (un 5xx conserva las colas del cliente).
    /// </summary>
    public static MensajeDeActualizacion? SiEstaActualizando(ErrorAula? error, bool paraTableta = false) =>
        error?.ActualizacionEnCurso == true
            ? new("El aula se está actualizando", paraTableta ? EnCursoParaTableta : EnCursoParaProfesor, paraTableta ? EnCursoDetalleTableta : "Las clases que ya están abiertas siguen igual.")
            : null;
}
