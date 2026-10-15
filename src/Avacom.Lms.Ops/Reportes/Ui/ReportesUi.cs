using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Reportes.Ui;

/// <summary>
/// Piezas que comparten las pantallas de Reportes (MOD-013): quién actúa y qué ofrece su rol, las filas que se tocan, las tarjetas de estado y la cabecera fija del CORTE de los datos
/// (BR-083). Sólo Border, Label, Button y FlexLayout del kit: ningún Path ni Ellipse (una geometría degenerada deja sin pintar todos los lienzos Win2D de la ventana).
/// </summary>
internal static class ReportesUi
{
    public const double AnchoMaximo = 1280;
    public static readonly Color FondoDeFila = Color.FromArgb("#FAFAFB");
    public static readonly Color FondoDeEncabezado = Color.FromArgb("#EFEFF2");

    // ------------------------------------------------------------------------------------------------------------------ quién actúa
    public static string Actor => Sesion.ProfesorId;
    public static bool HaySesion => Sesion.Usuario is not null;
    public static string? Rol => Sesion.Usuario?.Rol;
    public static bool PuedeLeer => AccesoAReportes.Leer(HaySesion, Rol);
    public static ReportesApi Api => Sesion.Reportes;

    // Lo que el nodo dice que esta persona puede: se pide una vez y se recuerda un rato, para no preguntarlo en cada pantalla. Cambiar de persona lo invalida.
    private static (FiltrosDeReportes Filtros, long En, string Actor)? _filtros;

    /// <summary>Los filtros (grupos, periodos, árbol académico y lo que esta persona puede hacer). Null si el nodo no contestó; la causa queda en <see cref="IReportesApi.UltimoError"/>.</summary>
    public static async Task<FiltrosDeReportes?> FiltrosAsync(bool forzar = false)
    {
        var actor = Actor;
        if (!forzar && _filtros is { } f && f.Actor == actor && Environment.TickCount64 - f.En < 30_000) return f.Filtros;
        var filtros = await Api.FiltrosAsync(actor);
        if (filtros is not null) _filtros = (filtros, Environment.TickCount64, actor);
        return filtros;
    }

    public static void OlvidarFiltros() => _filtros = null;

    // ------------------------------------------------------------------------------------------------------------------ archivos temporales

    /// <summary>Dónde se baja el archivo de un reporte antes de escribirlo en el destino: una carpeta de la caché de este equipo, nunca el destino mismo.</summary>
    public static string CarpetaTemporal => System.IO.Path.Combine(FileSystem.CacheDirectory, "reportes");

    private static bool _temporalesLimpiados;

    /// <summary>
    /// Una vez por arranque, borra los temporales «.parte» de más de 20 minutos: los que dejó un cierre brusco (un reporte con nombres de estudiantes no debe quedarse en la caché de un equipo
    /// compartido). Una exportación en curso no los pierde: su autorización caduca a los 15 minutos, así que ninguna usa un temporal más viejo que eso.
    /// </summary>
    public static void LimpiarTemporalesViejos()
    {
        if (_temporalesLimpiados) return;
        _temporalesLimpiados = true;
        try
        {
            if (!Directory.Exists(CarpetaTemporal)) return;
            foreach (var archivo in Directory.EnumerateFiles(CarpetaTemporal, "*.parte"))
                if (File.GetLastWriteTimeUtc(archivo) < DateTime.UtcNow.AddMinutes(-20)) File.Delete(archivo);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* se limpia en el próximo arranque */ }
    }

    // ------------------------------------------------------------------------------------------------------------------ toques y errores

    /// <summary>
    /// Lo que se toca corre en un <c>async void</c>: una excepción que se escapara cerraría la aplicación en plena clase. Se anota en el registro de fallos con la pantalla y el lugar, y la
    /// pantalla sigue.
    /// </summary>
    public static Func<Task> Seguro(string pantalla, string donde, Func<Task> accion) => async () =>
    {
        try { await accion(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", $"{pantalla}.{donde}", ex); }
    };

    /// <summary>
    /// Un destino que no se pudo escribir queda en el registro local (ADVERTENCIA del canal «escritura», que lo entrega al nodo): el motivo de la lista cerrada y el detalle técnico SIN rutas
    /// (<see cref="MotivosDeEscritura.Detalle"/>). Sin esto, el código de Windows de una memoria real que la tabla no conozca se perdería justo cuando hace falta ampliarla.
    /// </summary>
    public static void AnotarFalloDeEscritura(ResultadoDelGuardado resultado, TipoDeDestino tipo) =>
        RegistroLocal.Advertencia(Canal.Escritura, "reportes.escritura_fallida", $"No se pudo guardar un reporte exportado ({resultado.Fallo?.Codigo ?? "archivo_danado"}).",
            new { motivo = resultado.Fallo?.Codigo ?? "archivo_danado", estado = resultado.Estado.ToString(), tipo_destino = tipo.Codigo(), detalle = resultado.Detalle });

    /// <summary>El error del último intento del cliente, en palabras (sin conexión, permiso, clase en curso…).</summary>
    public static string Error(IReportesApi api) => MensajesDeReportes.De(api.UltimoError, string.IsNullOrWhiteSpace(api.UltimoMotivo) ? "No se pudo armar el reporte. Vuelve a intentarlo." : api.UltimoMotivo);

    /// <summary>¿El último error fue por no llegar al nodo? Entonces lo que se veía se conserva.</summary>
    public static bool SinConexion(IReportesApi api) => MensajesDeReportes.SinConexion(api.UltimoError);

    // ------------------------------------------------------------------------------------------------------------------ superficies

    /// <summary>Una tarjeta blanca (lo que se lee), con el relleno de las pantallas de reportes.</summary>
    public static Border Tarjeta(View contenido, Thickness? relleno = null) => Ds.Tarjeta(contenido, Ds.RadioTarjeta, relleno ?? new Thickness(26, 20), Colors.White);

    /// <summary>Una fila de una lista: fondo suave, filo de 1 px y las esquinas del kit.</summary>
    public static Border Fila(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = FondoDeFila, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = relleno ?? new Thickness(18, 12),
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = contenido,
    };

    /// <summary>La tarjeta de lo que no se puede ver con este rol (TST-069): se dice sin llamar al nodo.</summary>
    public static View SinAcceso(string? rol)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Este rol no accede a los reportes"));
        pila.Add(Ds.Secundario(AccesoAReportes.SinAcceso(rol), 16));
        return Tarjeta(pila);
    }

    /// <summary>Una tarjeta con un título, una frase y, si hace falta, botones (los estados «cargando», «vacío» y «no se pudo leer» de cada pantalla: siempre dicen qué hacer).</summary>
    public static View Estado(string titulo, string texto, params View[] acciones)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion(titulo));
        pila.Add(Ds.Secundario(texto, 16));
        var fila = ExamenUi.Fila();
        foreach (var accion in acciones)
        {
            accion.HorizontalOptions = LayoutOptions.Start;
            fila.Add(accion);
        }
        if (acciones.Length > 0) pila.Add(fila);
        return Tarjeta(pila);
    }

    /// <summary>El título de una sección de la página, con una línea de ayuda opcional.</summary>
    public static View Seccion(string titulo, string? ayuda = null)
    {
        var pila = new VerticalStackLayout { Spacing = 2, Margin = new Thickness(2, 10, 0, 2) };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(ayuda)) pila.Add(Ds.Secundario(ayuda!, 14));
        return pila;
    }

    /// <summary>
    /// Una fila o tarjeta que se toca. El contenido se pinta debajo y un botón transparente lo cubre: el toque es un botón de verdad (lo ven el lector de pantalla y la automatización),
    /// la superficie se hunde al pulsarla como los botones del kit y nada exige precisión de ratón.
    /// </summary>
    public static Border Tocable(View contenido, Func<Task> alTocar, string descripcion, string? id = null, Color? fondo = null, Thickness? relleno = null, bool elegida = false)
    {
        contenido.InputTransparent = true;
        var cuerpo = new Grid();
        cuerpo.Add(contenido);
        var boton = new Button { BackgroundColor = Colors.Transparent, BorderWidth = 0, Text = string.Empty, Padding = 0 };
        SemanticProperties.SetDescription(boton, descripcion);
        if (id is not null) boton.AutomationId = id;
        cuerpo.Add(boton);
        var superficie = new Border
        {
            BackgroundColor = fondo ?? Colors.White, Stroke = new SolidColorBrush(elegida ? Ds.Tinta : Ds.Filo), StrokeThickness = elegida ? 2.5 : 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = relleno ?? new Thickness(18, 10), Content = cuerpo,
        };
        boton.Pressed += async (_, _) => await superficie.ScaleToAsync(0.985, 80, Easing.CubicOut);
        boton.Released += async (_, _) => await superficie.ScaleToAsync(1, 130, Easing.CubicOut);
        boton.Clicked += async (_, _) => await alTocar();
        return superficie;
    }

    // ------------------------------------------------------------------------------------------------------------------ cifras

    /// <summary>La caja de un total: rótulo pequeño arriba, el valor grande y una nota debajo.</summary>
    public static Border Total(string rotulo, string valor, string? nota = null, double ancho = 250)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(EstudioUi.Eyebrow(rotulo.ToUpperInvariant()));
        pila.Add(new Label { Text = valor, FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(nota)) pila.Add(Ds.Secundario(nota!, 13));
        var caja = new Border
        {
            BackgroundColor = Color.FromArgb("#F7F7F8"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(18, 14),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila, MinimumWidthRequest = ancho, Margin = new Thickness(0, 0, 12, 12),
        };
        SemanticProperties.SetDescription(caja, $"{rotulo}: {valor}{(string.IsNullOrWhiteSpace(nota) ? string.Empty : ". " + nota)}");
        return caja;
    }

    /// <summary>Un texto de celda: a la izquierda, o a la derecha si es un número (los números se alinean a la derecha para poder compararlos de un vistazo).</summary>
    public static Label Celda(string? texto, bool derecha = false, bool medio = false, Color? color = null, double tamano = 15) => new()
    {
        Text = texto ?? string.Empty, FontFamily = medio ? Ds.FuenteMedia : Ds.FuenteRegular, FontSize = tamano, TextColor = color ?? Ds.Tinta,
        HorizontalTextAlignment = derecha ? TextAlignment.End : TextAlignment.Start, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.WordWrap,
    };

    /// <summary>
    /// El porcentaje de una celda con su barra: el número a la derecha y debajo la barra desde el CERO (el eje empieza en cero y la barra llena la fila al 100 %). Sin dato, «—» y ninguna
    /// barra: un promedio sin valores NO es un cero.
    /// </summary>
    public static View CeldaDePorcentaje(decimal? valor, Color? color = null)
    {
        var pila = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        pila.Add(Celda(FormatoDeReportes.Porcentaje(valor), derecha: true, medio: valor is not null, color: valor is null ? Ds.TintaSuave : Ds.Tinta));
        if (valor is { } v) pila.Add(EstudioUi.Barra((double)(v / 100m), color ?? Ds.Info, 6));
        return pila;
    }

    /// <summary>Un punto de color con su texto: el estado de la tableta de un alumno al cerrar la clase (el color nunca es el único aviso).</summary>
    public static View ConPunto(string texto, Color color)
    {
        var fila = new HorizontalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        fila.Add(new Label { Text = "●", FontSize = 12, TextColor = color, VerticalOptions = LayoutOptions.Center });
        fila.Add(Celda(texto));
        return fila;
    }

    public static Color ColorDePresencia(string estado) => estado switch
    {
        "conectado" => Ds.Exito,
        "reconectando" => ColorDeAdvertencia,
        "salio" => Ds.TintaSuave,
        "expulsado" => Ds.Peligro,
        _ => Ds.TintaSuave,
    };

    /// <summary>El ámbar del kit con tinta legible (el amarillo de marca no se lee como texto).</summary>
    public static readonly Color ColorDeAdvertencia = Color.FromArgb("#B58A00");

    // ------------------------------------------------------------------------------------------------------------------ la cabecera de corte (BR-083)

    /// <summary>
    /// La cabecera fija de todo reporte: hasta qué instante llegan los datos y en qué estado quedó la integración de los equipos (BR-083), con la insignia «Incompleto» en ámbar y el
    /// motivo en una línea cuando faltan tabletas por sincronizar. Además dice si el umbral de privacidad recortó el reporte (BR-086) y cualquier aviso del nodo (por ejemplo, que el
    /// filtro por materia no se pudo aplicar). Es lo que se ve mientras el cuerpo se desplaza: un reporte suelto siempre dice qué tan fresco es.
    /// </summary>
    public static View CabeceraDeCorte(CorteDeDatos corte, Privacidad? privacidad, IReadOnlyList<AvisoDeReporte>? avisos)
    {
        var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        texto.Add(EstudioUi.Eyebrow("CORTE DE LOS DATOS"));
        texto.Add(new Label { Text = FormatoDeReportes.LineaDeCorte(corte), FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "reporte-corte" });
        var explicacion = corte.Estado == EstadosDeProyeccion.AlDia ? corte.Explicacion : $"{corte.Explicacion} {FormatoDeReportes.Antiguedad(corte)}";
        texto.Add(Ds.Secundario(explicacion, 14));

        var integracion = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End };
        var pildoras = ExamenUi.Fila();
        if (corte.Incompleto || corte.Integracion.Incompleta)
        {
            pildoras.Add(ExamenUi.PildoraEnFila("Incompleto", Tono.Ambar, 14));
            integracion.Add(pildoras);
            if (!string.IsNullOrWhiteSpace(corte.Integracion.MotivoLinea))
                integracion.Add(new Label { Text = corte.Integracion.MotivoLinea, FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "reporte-incompleto-motivo" });
        }
        else
        {
            pildoras.Add(ExamenUi.PildoraEnFila("Integración completa", Tono.Exito, 14));
            integracion.Add(pildoras);
        }
        if (privacidad is { Aplicada: true })
        {
            var p = ExamenUi.Fila();
            p.Add(ExamenUi.PildoraEnFila("Privacidad activa · sólo totales", Tono.Info, 13));
            integracion.Add(p);
        }

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24 };
        fila.Add(texto, 0, 0);
        fila.Add(integracion, 1, 0);

        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Tarjeta(fila, new Thickness(24, 14)));
        if (privacidad is { Aplicada: true } && !string.IsNullOrWhiteSpace(privacidad.Aviso))
            pila.Add(ExamenUi.Aviso("Privacidad", privacidad.Aviso, Tono.Info));
        foreach (var aviso in avisos ?? [])
            pila.Add(ExamenUi.Aviso(aviso.Aplicado ? "Filtro aplicado" : "Filtro no aplicado", aviso.Texto, aviso.Aplicado ? Tono.Info : Tono.Ambar));
        return pila;
    }

    /// <summary>El dominio por objetivo no existe todavía (MOD-012): se dice «Aún no disponible», nunca un cero.</summary>
    public static View ObjetivosNoDisponibles(DominioPorObjetivo objetivos)
    {
        if (objetivos.Disponible) return new VerticalStackLayout();
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = "Dominio por objetivo", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.TintaMedia });
        pila.Add(new Label { Text = EstadosVaciosDeReportes.AunNoDisponible, FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = Ds.TintaSuave });
        pila.Add(Ds.Secundario(objetivos.Texto, 13));
        return Fila(pila);
    }
}

/// <summary>Una columna de una tabla de reporte: su rótulo, su ancho y si lleva números (se alinean a la derecha).</summary>
internal sealed record ColumnaDeTabla(string Titulo, GridLength Ancho, bool Derecha = false);

/// <summary>
/// Una tabla de reporte para pantalla grande y táctil: encabezado aparte (para dejarlo fijo mientras las filas se desplazan), filas de al menos 52 px, cebra suave y los números a la derecha.
/// El encabezado y las filas usan las mismas columnas, así que alinean. Una fila puede tocarse (abre otro reporte).
/// </summary>
internal sealed class TablaDeReporte(params ColumnaDeTabla[] columnas)
{
    public const double AltoDeFila = 52;

    private Grid NuevoGrid()
    {
        var g = new Grid { ColumnSpacing = 14 };
        foreach (var c in columnas) g.ColumnDefinitions.Add(new ColumnDefinition(c.Ancho));
        return g;
    }

    public View Encabezado()
    {
        var g = NuevoGrid();
        for (var i = 0; i < columnas.Length; i++)
            g.Add(new Label
            {
                Text = columnas[i].Titulo, FontFamily = Ds.FuenteMedia, FontSize = 13, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.WordWrap,
                HorizontalTextAlignment = columnas[i].Derecha ? TextAlignment.End : TextAlignment.Start,
            }, i, 0);
        return new Border
        {
            BackgroundColor = ReportesUi.FondoDeEncabezado, StrokeThickness = 0, Padding = new Thickness(18, 10), MinimumHeightRequest = 44,
            StrokeShape = new RoundRectangle { CornerRadius = new CornerRadius(Ds.RadioInterno, Ds.RadioInterno, 0, 0) }, Content = g,
        };
    }

    /// <summary>Una fila: cada celda es un texto (se alinea según su columna) o una vista ya hecha. Con <paramref name="alTocar"/> la fila entera es un botón.</summary>
    public View Fila(IReadOnlyList<object?> celdas, bool cebra, Func<Task>? alTocar = null, string? id = null, string? descripcion = null, bool pie = false)
    {
        var g = NuevoGrid();
        for (var i = 0; i < columnas.Length; i++)
        {
            var celda = i < celdas.Count ? celdas[i] : null;
            View vista = celda as View ?? ReportesUi.Celda(celda?.ToString(), columnas[i].Derecha, medio: pie);
            g.Add(vista, i, 0);
        }
        var fondo = pie ? ReportesUi.FondoDeEncabezado : cebra ? ReportesUi.FondoDeFila : Colors.White;
        if (alTocar is not null)
        {
            var tocable = ReportesUi.Tocable(g, alTocar, descripcion ?? "Abrir", id, fondo, new Thickness(18, 8));
            tocable.StrokeThickness = 0;
            tocable.StrokeShape = new RoundRectangle { CornerRadius = 0 };
            tocable.MinimumHeightRequest = AltoDeFila;
            return tocable;
        }
        return new Border { BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(18, 8), MinimumHeightRequest = AltoDeFila, StrokeShape = new RoundRectangle { CornerRadius = 0 }, Content = g };
    }

    /// <summary>
    /// Sólo las filas, en una tarjeta con las esquinas redondeadas ABAJO: para cuando el encabezado va aparte, fijo sobre el cuerpo que se desplaza.
    /// </summary>
    public View Cuerpo(IEnumerable<View> filas)
    {
        var pila = new VerticalStackLayout { Spacing = 0 };
        foreach (var fila in filas) pila.Add(fila);
        return new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = new CornerRadius(0, 0, Ds.RadioInterno, Ds.RadioInterno) }, Content = pila, Shadow = Ds.SombraTarjeta(),
        };
    }

    /// <summary>Una tabla completa en una tarjeta: encabezado, filas y un renglón de pie opcional. Para las tablas que se desplazan con la página.</summary>
    public View EnTarjeta(IEnumerable<View> filas, View? pie = null)
    {
        var pila = new VerticalStackLayout { Spacing = 0 };
        pila.Add(Encabezado());
        foreach (var fila in filas) pila.Add(fila);
        if (pie is not null) pila.Add(pie);
        return new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = pila, Shadow = Ds.SombraTarjeta(),
        };
    }
}
