using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

// Vista 2 · una asignación por dentro: sus totales, los cambios rápidos y «quién completó», alumno por alumno (CAP-051).
public partial class EstudioPage
{
    private string? _detalleId;
    private AsignacionDocente? _detalle;
    private string _filtroAlumnos = "todos";
    private int? _fechaDias;                        // el cambio de fecha que la profesora eligió y todavía no guarda
    private int _fechaMinutos = MinutosFinDelDia;

    private async Task MostrarDetalleAsync(string id, string? avisoDeExito)
    {
        Entrar(Vista.Detalle);
        _detalleId = id;
        _detalle = null;
        _filtroAlumnos = "todos";
        _fechaDias = null;
        _fechaMinutos = MinutosFinDelDia;
        PonerCabecera("ASIGNACIÓN", "Cargando…", string.Empty, CabeceraDeDetalle().ToArray());
        Vaciar(true);
        ContenidoHost.Add(Cargando("Leyendo cómo va el grupo…"));
        if (avisoDeExito is not null) Avisar("Listo", avisoDeExito, false);
        await CargarDetalleAsync(_generacion, true);
    }

    /// <summary>Lo que hace que el detalle se vea distinto: lo que dice el nodo y lo que la profesora tiene elegido en esta página.</summary>
    private string FirmaDeDetalle(AsignacionDocente detalle) => $"{_filtroAlumnos}|{_fechaDias}|{_fechaMinutos}|{JsonSerializer.Serialize(detalle)}";

    private IEnumerable<View> CabeceraDeDetalle()
    {
        yield return EstudioUi.Accion("‹  Asignaciones", Ds.Rango.Secondary, async () => await MostrarListaAsync(), 210, "estudio-volver").Vista;
        yield return AccionActualizar().Vista;
        yield return AccionMenu().Vista;
    }

    private async Task CargarDetalleAsync(int generacion, bool forzar)
    {
        if (_detalleId is null) return;
        var api = Api;
        var detalle = await api.AsignacionDocenteAsync(Actor, _detalleId);
        if (generacion != _generacion || _vista != Vista.Detalle) return;
        if (detalle is null)
        {
            var error = api.UltimoError;
            var firmaError = $"error|{error?.Estado}|{error?.Codigo}";
            if (!forzar && firmaError == _firma) return;
            _firma = firmaError;
            Repintar(() =>
            {
                Vaciar(false);
                ContenidoHost.Add(EstudioUi.Aviso("No se pudo leer la asignación", EstudioTexto.Error(error, api.UltimoMotivo), Ds.PeligroSuave, EstudioUi.TintaPeligro));
            });
            return;
        }

        var firma = FirmaDeDetalle(detalle);
        if (!forzar && firma == _firma) return;
        _firma = firma;
        _detalle = detalle;
        PonerCabecera("ASIGNACIÓN", detalle.Titulo,
            string.Join(" · ", new[] { detalle.Asignatura, detalle.Unidad, detalle.GrupoRotulo ?? (detalle.Alcance == "seleccion" ? "Alumnos elegidos" : null),
                EstudioTexto.Plural(detalle.DestinatariosTotal, "alumno", "alumnos") }.Where(x => !string.IsNullOrWhiteSpace(x))),
            CabeceraDeDetalle().ToArray());
        Repintar(() =>
        {
            Vaciar(false);
            ContenidoHost.Add(Resumen(detalle));
            if (!detalle.Cerrada) ContenidoHost.Add(CambiosRapidos(detalle));
            ContenidoHost.Add(QuienCompleto(detalle));
        });
    }

    // ---------------------------------------------------------------------------------- resumen

    private View Resumen(AsignacionDocente a)
    {
        var ahora = RelojNodo.AhoraMs;
        var vencida = !a.Cerrada && a.FechaLimite is { } limite && limite < ahora;

        var texto = new VerticalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        var estados = EstudioUi.Envolver();
        void Etiqueta(string rotulo, Color fondo, Color tinta)
        {
            var p = Ds.Pildora(rotulo, fondo, tinta, 13);
            p.Margin = new Thickness(0, 0, 8, 8);
            estados.Add(p);
        }
        Etiqueta(a.Cerrada ? "CERRADA" : "ABIERTA", a.Cerrada ? EstudioUi.PistaBarra : Ds.ExitoSuave, a.Cerrada ? Ds.TintaSuave : Color.FromArgb("#0B5D3B"));
        Etiqueta(a.Plazo == "endurecido" ? "PLAZO ESTRICTO" : "PLAZO FLEXIBLE", Color.FromArgb("#F0F0F2"), Ds.TintaMedia);
        Etiqueta(a.PaquetePermitido ? "SE PUEDE DESCARGAR" : "SÓLO EN LÍNEA", a.PaquetePermitido ? Ds.InfoSuave : Ds.AlertaSuave, a.PaquetePermitido ? Color.FromArgb("#02739E") : Color.FromArgb("#806600"));
        texto.Add(estados);
        texto.Add(new Label
        {
            Text = EstudioTexto.Entrega(a.FechaLimite) + (vencida ? " · ya pasó" : string.Empty),
            FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = vencida && a.Pendientes + a.EnCurso > 0 ? EstudioUi.TintaPeligro : Ds.Tinta,
        });
        texto.Add(Ds.Secundario(EstudioTexto.PlazoLegible(a.Plazo) + (a.Plazo == "endurecido" && a.GraciaMs is > 0 ? $" · gracia de {a.GraciaMs / 60_000} min" : string.Empty), 15));
        if (!string.IsNullOrWhiteSpace(a.Consigna))
            texto.Add(new Label { Text = $"Consigna: {a.Consigna}", FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, Margin = new Thickness(0, 4, 0, 0) });

        var totales = new HorizontalStackLayout { Spacing = 34, VerticalOptions = LayoutOptions.Center };
        totales.Add(EstudioUi.Total(a.Completaron, "completaron", Color.FromArgb("#017A48")));
        totales.Add(EstudioUi.Total(a.EnCurso, "en curso", Color.FromArgb("#02739E")));
        totales.Add(EstudioUi.Total(a.Pendientes, "sin empezar", Color.FromArgb("#806600")));
        totales.Add(EstudioUi.Total(a.FueraDePlazo, "fuera de plazo", EstudioUi.TintaPeligro));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 30 };
        fila.Add(texto, 0, 0);
        fila.Add(totales, 1, 0);
        return Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
    }

    // ------------------------------------------------------------------------- cambios rápidos

    private View CambiosRapidos(AsignacionDocente a)
    {
        var pila = new VerticalStackLayout { Spacing = 16 };
        pila.Add(Ds.Titulo("Cambios rápidos", 20));

        // Fecha límite: se elige, se ve qué día queda, y sólo entonces se guarda.
        pila.Add(Ds.Secundario("Fecha límite", 15));
        pila.Add(SelectorDeFecha(_fechaDias, _fechaMinutos, (dias, minutos) =>
        {
            _fechaDias = dias;
            _fechaMinutos = minutos;
            Repintar(() => { Vaciar(false); PintarDetalleGuardado(); });
        }, mostrarSinFecha: a.FechaLimite is not null));
        if (_fechaDias is not null)
        {
            var quitar = _fechaDias == -1;
            var destino = quitar ? null : FechaElegida(_fechaDias, _fechaMinutos);
            var pasada = destino is not null && destino <= DateTime.Now;
            var guardar = EstudioUi.Accion(quitar ? "Quitar la fecha límite" : "Guardar la nueva fecha", Ds.Rango.Primary, async () => await GuardarFechaAsync(a, quitar ? null : destino), 260, "estudio-guardar-fecha");
            Ds.Habilitar(guardar.Boton, !pasada);
            var cancelar = EstudioUi.Accion("Dejarla como estaba", Ds.Rango.Quiet, () =>
            {
                _fechaDias = null;
                Repintar(() => { Vaciar(false); PintarDetalleGuardado(); });
                return Task.CompletedTask;
            }, null, "estudio-cancelar-fecha");
            var acciones = new HorizontalStackLayout { Spacing = 12, Margin = new Thickness(0, 2, 0, 0) };
            acciones.Add(guardar.Vista);
            acciones.Add(cancelar.Vista);
            pila.Add(acciones);
            if (pasada) pila.Add(new Label { Text = "Esa hora ya pasó. Elige otra.", FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = EstudioUi.TintaPeligro });
        }

        pila.Add(Ds.Separador());
        pila.Add(Ds.Secundario("Si un envío llega tarde", 15));
        var plazo = EstudioUi.Envolver();
        plazo.Add(EstudioUi.Chip("Flexible", a.Plazo != "endurecido", async () => await CambiarAsync(a, new CambiosAsignacion(Plazo: "blando"), "El plazo quedó flexible."), "estudio-plazo-blando"));
        plazo.Add(EstudioUi.Chip("Estricto", a.Plazo == "endurecido", async () => await CambiarAsync(a, new CambiosAsignacion(Plazo: "endurecido"), "El plazo quedó estricto."), "estudio-plazo-endurecido"));
        pila.Add(plazo);
        pila.Add(Ds.Secundario(a.Plazo == "endurecido"
            ? "Lo que el alumno hizo antes de la hora y llega dentro de la gracia se acepta. Lo que llega más tarde espera tu decisión; lo hecho después de la hora se rechaza."
            : "Todo se acepta. Lo que el alumno haga después de la fecha queda marcado como «fuera de plazo».", 14));

        pila.Add(Ds.Separador());
        pila.Add(Ds.Secundario("Llevársela a casa", 15));
        var descarga = EstudioUi.Envolver();
        descarga.Add(EstudioUi.Chip("Se puede descargar", a.PaquetePermitido, async () => await CambiarAsync(a, new CambiosAsignacion(PaquetePermitido: true), "Ahora se puede descargar."), "estudio-descarga-si"));
        descarga.Add(EstudioUi.Chip("Sólo en línea", !a.PaquetePermitido, async () => await CambiarAsync(a, new CambiosAsignacion(PaquetePermitido: false), "Ahora sólo se estudia en línea."), "estudio-descarga-no"));
        pila.Add(descarga);
        pila.Add(Ds.Secundario("Sólo las tabletas asignadas a un alumno se llevan la lección; una tableta compartida nunca la descarga.", 14));

        pila.Add(Ds.Separador());
        var cerrar = EstudioUi.Accion("Cerrar la asignación", Ds.Rango.Destructive, async () => await CerrarAsync(a), 260, "estudio-cerrar");
        cerrar.Vista.HorizontalOptions = LayoutOptions.Start;
        pila.Add(cerrar.Vista);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
    }

    /// <summary>Repinta el detalle con lo último que se leyó (sin volver a preguntar al nodo): la elección de fecha vive sólo en esta página.</summary>
    private void PintarDetalleGuardado()
    {
        if (_detalle is not { } detalle) return;
        _firma = FirmaDeDetalle(detalle);
        ContenidoHost.Add(Resumen(detalle));
        if (!detalle.Cerrada) ContenidoHost.Add(CambiosRapidos(detalle));
        ContenidoHost.Add(QuienCompleto(detalle));
    }

    private async Task GuardarFechaAsync(AsignacionDocente a, DateTime? destino)
    {
        var cambios = destino is null ? new CambiosAsignacion(QuitarFecha: true) : new CambiosAsignacion(FechaLimite: EstudioTexto.AMs(destino.Value));
        _fechaDias = null;
        await CambiarAsync(a, cambios, destino is null ? "La asignación ya no tiene fecha límite." : $"Nueva fecha límite: {EstudioTexto.FechaLarga(destino.Value)}.");
    }

    private async Task CambiarAsync(AsignacionDocente a, CambiosAsignacion cambios, string confirmacion)
    {
        var api = Api;
        var nueva = await api.CambiarAsignacionAsync(Actor, a.Id, cambios);
        if (nueva is null)
        {
            Avisar("No se pudo guardar el cambio", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), true);
            return;
        }
        Avisar("Guardado", confirmacion, false);
        await RefrescarAsync(true);
    }

    private async Task CerrarAsync(AsignacionDocente a)
    {
        var quedan = a.Pendientes + a.EnCurso;
        var seguro = await DisplayAlertAsync("¿Cerrar esta asignación?",
            quedan > 0
                ? $"{EstudioTexto.Plural(quedan, "alumno todavía no la termina", "alumnos todavía no la terminan")}. Al cerrarla ya no se acepta trabajo nuevo y desaparece de «Pendientes» en las tabletas. Lo ya hecho se conserva."
                : "Todos la terminaron. Al cerrarla desaparece de «Pendientes» y lo hecho se conserva.",
            "Cerrar", "Mejor no");
        if (!seguro) return;
        var api = Api;
        var cerrada = await api.CerrarAsignacionAsync(Actor, a.Id);
        if (cerrada is null)
        {
            Avisar("No se pudo cerrar la asignación", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), true);
            return;
        }
        Avisar("Asignación cerrada", "Ya no se acepta trabajo nuevo. Lo hecho se conserva.", false);
        await RefrescarAsync(true);
    }

    // ---------------------------------------------------------------------------- quién completó

    private static bool Coincide(FilaDeAlumno f, string filtro) => filtro switch
    {
        "completada" => f.Estado == "completada",
        "en_curso" => f.Estado == "en_curso",
        "pendiente" => f.Estado == "pendiente",
        "vencida" => f.Vencida && f.Estado != "completada",
        "decidir" => f.PendientesDecision > 0,
        _ => true,
    };

    private View QuienCompleto(AsignacionDocente a)
    {
        var filas = a.Alumnos ?? [];
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo("Quién completó", 22));

        var filtros = EstudioUi.Envolver();
        void Filtro(string rotulo, string valor)
        {
            var n = filas.Count(f => Coincide(f, valor));
            if (valor is "vencida" or "decidir" && n == 0 && _filtroAlumnos != valor) return;   // sólo se ofrecen si hay de qué hablar
            filtros.Add(EstudioUi.Chip($"{rotulo} · {n}", _filtroAlumnos == valor, () =>
            {
                _filtroAlumnos = valor;
                Repintar(() => { Vaciar(false); PintarDetalleGuardado(); });
                return Task.CompletedTask;
            }, $"estudio-alumnos-{valor}", 48));
        }
        Filtro("Todos", "todos");
        Filtro("Completaron", "completada");
        Filtro("En curso", "en_curso");
        Filtro("Sin empezar", "pendiente");
        Filtro("Vencidos", "vencida");
        Filtro("Por decidir", "decidir");
        pila.Add(filtros);

        if (filas.Count == 0)
        {
            pila.Add(Ds.Secundario("Esta asignación todavía no tiene alumnos. Si es de un grupo, aparecerán los que se inscriban en él.", 16));
            return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
        }

        var visibles = filas.Where(f => Coincide(f, _filtroAlumnos))
            .OrderByDescending(f => f.PendientesDecision > 0)
            .ThenByDescending(f => f.Vencida && f.Estado != "completada")
            .ThenBy(f => f.Estado == "completada" ? 2 : f.Estado == "en_curso" ? 1 : 0)
            .ThenBy(f => f.Rotulo ?? f.AlumnoId, StringComparer.CurrentCultureIgnoreCase)
            .ToList();
        if (visibles.Count == 0)
        {
            pila.Add(Ds.Secundario("Nadie coincide con este filtro.", 16));
            return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
        }

        pila.Add(EncabezadoDeTabla());
        foreach (var fila in visibles) pila.Add(FilaDeAlumnoView(a, fila));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
    }

    private static Grid RejillaDeTabla() => new()
    {
        ColumnDefinitions =
        [
            new ColumnDefinition(new GridLength(2.3, GridUnitType.Star)),
            new ColumnDefinition(new GridLength(150)),
            new ColumnDefinition(new GridLength(2.1, GridUnitType.Star)),
            new ColumnDefinition(new GridLength(1.5, GridUnitType.Star)),
            new ColumnDefinition(new GridLength(1.4, GridUnitType.Star)),
            new ColumnDefinition(new GridLength(1.9, GridUnitType.Star)),
        ],
        ColumnSpacing = 16,
    };

    private static View EncabezadoDeTabla()
    {
        var g = RejillaDeTabla();
        g.Margin = new Thickness(4, 6, 4, 0);
        string[] titulos = ["ALUMNO", "ESTADO", "AVANCE", "PRÁCTICA", "EN SU TABLETA", "APARATO"];
        for (var i = 0; i < titulos.Length; i++) g.Add(EstudioUi.Eyebrow(titulos[i]), i, 0);
        return g;
    }

    private View FilaDeAlumnoView(AsignacionDocente a, FilaDeAlumno f)
    {
        var g = RejillaDeTabla();
        var nombre = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        nombre.Add(new Label { Text = f.Rotulo ?? f.AlumnoId, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
        nombre.Add(Ds.Secundario(f.CompletadaEn is { } fin ? $"terminó {EstudioTexto.Relativo(fin)}"
            : f.UltimoAvanceEn is { } ult ? $"último avance {EstudioTexto.Relativo(ult)}" : "todavía no empieza", 13));
        g.Add(nombre, 0, 0);

        var (texto, fondo, tinta) = EstudioTexto.Estado(f.Estado, f.Vencida);
        var estado = Ds.Pildora(texto, fondo, tinta, 12);
        estado.HorizontalOptions = LayoutOptions.Start;
        var estadoPila = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        estadoPila.Add(estado);
        if (f.FueraDePlazo) estadoPila.Add(new Label { Text = "fuera de plazo", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = EstudioUi.TintaPeligro });
        g.Add(estadoPila, 1, 0);

        var avance = new VerticalStackLayout { Spacing = 5, VerticalOptions = LayoutOptions.Center };
        avance.Add(EstudioUi.Barra(Math.Clamp(f.AvancePct / 100d, 0, 1), f.Estado == "completada" ? Ds.Exito : Ds.Info, 8));
        avance.Add(Ds.Secundario(f.BloquesTotal > 0 ? $"{f.BloquesAtendidos} de {f.BloquesTotal} actividades · {f.AvancePct:0} %" : $"{f.AvancePct:0} %", 13));
        g.Add(avance, 2, 0);

        var practica = f.Practica is { Intentos: > 0 } p
            ? (p.MejorCorrectas is { } mejor && p.Total is { } total ? $"{mejor} de {total} correctas · {EstudioTexto.Plural(p.Intentos, "intento", "intentos")}" : EstudioTexto.Plural(p.Intentos, "intento", "intentos"))
            : "Sin practicar";
        var practicaLabel = Ds.Secundario(practica, 14);
        practicaLabel.VerticalOptions = LayoutOptions.Center;
        g.Add(practicaLabel, 3, 0);

        var paquete = Ds.Secundario(EstudioTexto.PaqueteLegible(f.Paquete?.Estado), 14);
        paquete.VerticalOptions = LayoutOptions.Center;
        g.Add(paquete, 4, 0);

        var aparato = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        if (f.Dispositivo is { } d)
        {
            aparato.Add(new Label { Text = string.IsNullOrWhiteSpace(d.Nombre) ? "Tableta" : d.Nombre, FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
            aparato.Add(Ds.Secundario(d.Perfil == "asignado" ? "asignada a este alumno" : "compartida", 13));
        }
        else aparato.Add(Ds.Secundario("Sin tableta registrada", 14));
        g.Add(aparato, 5, 0);

        var contenido = new VerticalStackLayout { Spacing = 10 };
        contenido.Add(g);
        foreach (var pendiente in f.Decisiones ?? []) contenido.Add(DecisionPendienteView(a, f, pendiente));
        var vencidaSinTerminar = f.Vencida && f.Estado != "completada";
        return new Border
        {
            BackgroundColor = vencidaSinTerminar ? Color.FromArgb("#FFF8F8") : Color.FromArgb("#FAFAFB"),
            Stroke = new SolidColorBrush(Ds.Filo),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Padding = new Thickness(18, 12),
            Content = contenido,
        };
    }

    private static string AccionDeEvento(string? tipo) => tipo switch
    {
        "study.lesson.completed" => "terminó la lección",
        "study.answer.submitted" => "mandó una respuesta de la práctica",
        "study.practice.finished" => "terminó la práctica",
        "study.block.viewed" => "avanzó en la lección",
        _ => "mandó trabajo",
    };

    /// <summary>BR-074: lo que llegó fuera de la ventana de gracia nunca se descarta en silencio; el profesor lo acepta o lo descarta.</summary>
    private View DecisionPendienteView(AsignacionDocente a, FilaDeAlumno f, DecisionPendiente d)
    {
        var nombre = f.Rotulo ?? f.AlumnoId;
        var cuando = d.OcurridoEn is { } o ? EstudioTexto.Momento(o) : "sin hora";
        var llego = d.RecibidoEn is { } r ? EstudioTexto.Momento(r) : "sin hora";
        var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = $"{nombre} {AccionDeEvento(d.Tipo)} y su tableta lo mandó tarde", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Color.FromArgb("#5C0F45"), LineBreakMode = LineBreakMode.WordWrap });
        texto.Add(new Label { Text = $"Lo hizo el {cuando} y llegó el {llego}, fuera de la gracia. ¿Lo aceptas?", FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Color.FromArgb("#5C0F45"), LineBreakMode = LineBreakMode.WordWrap });

        var aceptar = EstudioUi.Accion("Aceptar", Ds.Rango.Secondary, async () => await DecidirAsync(a, f, d, "aceptar"), 150, $"estudio-aceptar-{f.AlumnoId}-{d.Secuencia}");
        var descartar = EstudioUi.Accion("Descartar", Ds.Rango.Quiet, async () => await DecidirAsync(a, f, d, "descartar"), 150, $"estudio-descartar-{f.AlumnoId}-{d.Secuencia}");
        var botones = new HorizontalStackLayout { Spacing = 10, VerticalOptions = LayoutOptions.Center };
        botones.Add(aceptar.Vista);
        botones.Add(descartar.Vista);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(texto, 0, 0);
        fila.Add(botones, 1, 0);
        return new Border
        {
            BackgroundColor = Ds.VioletaSuave, StrokeThickness = 0, Padding = new Thickness(16, 12),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl }, Content = fila,
        };
    }

    private async Task DecidirAsync(AsignacionDocente a, FilaDeAlumno f, DecisionPendiente d, string decision)
    {
        var api = Api;
        var bien = await api.DecidirAsync(Actor, a.Id, f.AlumnoId, d.Secuencia, d.EmisorId, decision);
        if (!bien)
        {
            Avisar("No se pudo guardar tu decisión", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), true);
            return;
        }
        Avisar("Listo", decision == "aceptar" ? "Aceptaste el envío: ya cuenta en el avance del alumno." : "Descartaste el envío: no cuenta en el avance del alumno.", false);
        await RefrescarAsync(true);
    }
}
