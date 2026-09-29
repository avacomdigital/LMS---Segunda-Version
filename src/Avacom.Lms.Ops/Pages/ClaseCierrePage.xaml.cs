using System.Globalization;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Layouts;
using RoundRectangle = Microsoft.Maui.Controls.Shapes.RoundRectangle;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P4 · Cierre (PAN-008). El resumen consolidado de la sesión en tarjetas y un solo Primary:
/// volver a «Clase de hoy». Una clase cerrada no se reabre (sección H del Maestro).
///
/// 007-09: bajo las seis tarjetas de contadores va lo que trae <see cref="ResumenSesion.Detalle"/> y el anclaje: la participación
/// por alumno (los que tienen pendientes, primero), los pendientes, «Dejar tarea de estudio» (un interruptor por actividad o recurso
/// y, encendido, chips de fecha límite) y «Tema de la clase» (anclaje curricular con chips tocables). Todo con toques, sin teclado.
/// Nada de esto se exige para cerrar ni para salir de la pantalla (BR-039, UXR-001, CMP-017): anclar es opcional y se puede dejar
/// pendiente. Si el resumen no trae detalle (clases anteriores a este cambio) esas secciones simplemente no se pintan.
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
public partial class ClaseCierrePage : ContentPage
{
    public string SesionId { get; set; } = string.Empty;

    public ClaseCierrePage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await CargarAsync();
    }

    private const long DiaMs = 86_400_000;
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es");
    private static readonly (string Texto, int? Dias)[] OpcionesDeFecha = [("Mañana", 1), ("En 3 días", 3), ("En 1 semana", 7), ("Sin fecha límite", null)];
    private const string TituloTema = "Tema de la clase";

    private SesionDeClase? _sesion;
    private long _nodoBase;
    private long _tickBase;
    private bool _cargando;

    /// <summary>La hora del nodo ahora mismo: la que dijo al leer la sesión más lo que pasó desde entonces (BR-062: la hora del aparato no decide nada).</summary>
    private long AhoraNodo => _nodoBase + (Environment.TickCount64 - _tickBase);

    /// <summary>Una actividad o un recurso de la clase que se puede dejar como tarea de estudio (PAN-008).</summary>
    private sealed class ItemEstudio(string id, string rotulo, bool esActividad, bool disponible, long? hasta)
    {
        public string Id { get; } = id;
        public string Rotulo { get; } = rotulo;
        public bool EsActividad { get; } = esActividad;
        public bool Disponible { get; set; } = disponible;
        public long? Hasta { get; set; } = hasta;
    }

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            AvisoHost.Clear();
            ResumenHost.Children.Clear();
            SeccionesHost.Clear();
            AccionesHost.Clear();
            var aula = Sesion.Aula;
            SesionDeClase? sesion = null;
            if (!string.IsNullOrWhiteSpace(SesionId))
                // «Cargando» sólo si la lectura pasa de 1 s: si llega antes, nadie ve un parpadeo.
                sesion = await EsperarAsync(aula.SesionAsync(SesionId), () => SeccionesHost.Add(Cargando("Leyendo el resumen de la clase…")));
            SeccionesHost.Clear();
            VerticalStackLayout? temaHost = null;
            if (sesion is null)
            {
                PintarSinSesion(aula);
            }
            else
            {
                _sesion = sesion;
                _nodoBase = sesion.ServidorEn > 0 ? sesion.ServidorEn : Avacom.Lms.Core.Services.RelojNodo.AhoraMs;
                _tickBase = Environment.TickCount64;
                TituloLabel.Text = sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre";
                SubtituloLabel.Text = string.Join(" · ", new[] { sesion.CursoRotulo, sesion.ProfesorRotulo, $"código {sesion.CodigoUnion}" }.Where(x => !string.IsNullOrWhiteSpace(x)));
                var r = sesion.Resumen;
                if (r is null)
                {
                    AvisoHost.Add(Ds.Alerta_("La clase aún no tiene resumen",
                        sesion.Activa ? "La clase sigue en curso. Cuando la termines, aquí verás cómo fue." : "El resumen todavía no está listo. Vuelve a abrir esta pantalla en un momento.",
                        Ds.AlertaSuave, Ds.Tinta));
                }
                else
                {
                    Tarjeta("Participantes", r.Participantes.ToString(), $"máximo {r.ConectadosMaximo} a la vez", Ds.CatClaseEnVivo);
                    Tarjeta("Proyecciones", r.Selectores.ToString(), "cambios de selector", Ds.Info);
                    Tarjeta("Actividades", r.Actividades.ToString(), r.Distribuciones == r.Actividades ? "lanzadas al grupo" : $"{r.Distribuciones} distribuciones en total", Ds.CatQuiz);
                    Tarjeta("Avisos", r.Avisos.ToString(), "enviados al grupo", Ds.CatLectura);
                    Tarjeta("Duración", r.DuracionTexto, CierreLegible(r.OrigenCierre), Ds.TintaSuave);
                    Tarjeta("Pendientes", r.Pendientes.ToString(), r.Pendientes == 0 ? "ningún intento abierto" : "intentos abiertos al cierre", r.Pendientes == 0 ? Ds.Exito : Ds.Alerta);
                    // Un resumen sin detalle (clase anterior a 007-09) se queda con sus tarjetas.
                    if (r.Detalle is { } detalle) PintarDetalle(sesion, detalle);
                    temaHost = new VerticalStackLayout();
                    SeccionesHost.Add(temaHost);
                }
            }
            if (sesion is null && !string.IsNullOrWhiteSpace(SesionId))
                AccionesHost.Add(Ds.Boton("Reintentar", Ds.Rango.Secondary, async (_, _) => await CargarAsync(), 64, 320));
            // Las salidas cuentan las páginas que hay encima de «Clase de hoy» (con «Continuar» hay una menos que si se llegó por el curso).
            AccionesHost.Add(Ds.Boton("Volver a Clase de hoy", Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync(RutaHasta<ClaseHoyPage>("../../..")), 64, 320));
            AccionesHost.Add(Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(RutaHasta<DashboardPage>("../../../..")), 64, 320));
            // El tema se pide al final: las salidas ya están a mano y la pantalla nunca espera por él.
            if (temaHost is not null && sesion is not null) await CargarTemaAsync(sesion, temaHost);
        }
        finally { _cargando = false; }
    }

    /// <summary>No se pudo leer la sesión: qué se conservó, qué falta y qué sigue, sin detalles técnicos (UXR-005, UXR-009).</summary>
    private void PintarSinSesion(IAulaApi aula)
    {
        if (string.IsNullOrWhiteSpace(SesionId))
        {
            AvisoHost.Add(Ds.Alerta_("No sabemos qué clase abrir", "Vuelve a Clase de hoy y elígela de nuevo.", Ds.AlertaSuave, Ds.Tinta));
            return;
        }
        var permiso = Sesion.MensajeDePermiso(aula.UltimoError);
        var texto = permiso ?? (aula.UltimoError?.Estado == 0
            ? "No hay conexión con el aula. La clase quedó guardada; revisa la red e inténtalo de nuevo."
            : "La clase quedó guardada. Inténtalo de nuevo en un momento.");
        AvisoHost.Add(permiso is null
            ? Ds.Alerta_("No pudimos abrir el resumen", texto, Ds.PeligroSuave, Color.FromArgb("#8A1C1F"))
            : Ds.Alerta_("Este resumen no es tuyo", texto, Ds.InfoSuave, Color.FromArgb("#0B4F70")));
    }

    private static string CierreLegible(string? origen) => origen switch
    {
        "profesor" => "cerrada por el profesor",
        "inactividad" => "cerrada por inactividad",
        "administrador" => "cerrada por la administración",
        "sistema" => "cerrada por el aula",
        _ => "clase cerrada",
    };

    /// <summary>Espera la tarea y avisa sólo si tarda más de un segundo (el estado «cargando» del Maestro no debe parpadear).</summary>
    private static async Task<T> EsperarAsync<T>(Task<T> tarea, Action alPasarUnSegundo)
    {
        if (!ReferenceEquals(await Task.WhenAny(tarea, Task.Delay(1000)), tarea)) alPasarUnSegundo();
        return await tarea;
    }

    /// <summary>Ruta relativa para volver hasta la página indicada, contando cuántas hay encima en la pila; <paramref name="porDefecto"/> si no está.</summary>
    private static string RutaHasta<TPagina>(string porDefecto) where TPagina : Page
    {
        var pila = Shell.Current.Navigation.NavigationStack;
        for (var i = pila.Count - 1; i >= 0; i--)
        {
            if (pila[i] is not TPagina) continue;
            var saltos = pila.Count - 1 - i;
            return saltos > 0 ? string.Join("/", Enumerable.Repeat("..", saltos)) : porDefecto;
        }
        return porDefecto;
    }

    // ------------------------------------------------------------------ secciones (007-09)

    private void PintarDetalle(SesionDeClase sesion, DetalleResumen detalle)
    {
        SeccionesHost.Add(SeccionParticipacion(detalle));
        if (detalle.Pendientes is { Count: > 0 } pendientes) SeccionesHost.Add(SeccionPendientes(pendientes));
        SeccionesHost.Add(SeccionEstudio(sesion, detalle));
    }

    /// <summary>Una sección del cierre: tarjeta con su píldora de título, una frase de apoyo a la derecha y el contenido debajo.</summary>
    private static Border Seccion(string titulo, Color color, string? apoyo, View contenido)
    {
        var pila = new VerticalStackLayout { Spacing = 14 };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14 };
        cabecera.Add(Ds.Pildora(titulo, color), 0, 0);
        if (!string.IsNullOrWhiteSpace(apoyo))
        {
            var texto = Ds.Secundario(apoyo, 14);
            texto.VerticalOptions = LayoutOptions.Center;
            cabecera.Add(texto, 1, 0);
        }
        pila.Add(cabecera);
        pila.Add(contenido);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(24, 20));
    }

    /// <summary>Estados vacío y «sin datos» del Maestro: qué pasó y qué sigue, centrado y sin adornos.</summary>
    private static View Vacio(string titulo, string? detalle = null)
    {
        var pila = new VerticalStackLayout { Spacing = 4, HorizontalOptions = LayoutOptions.Center, Padding = new Thickness(0, 6) };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(detalle))
            pila.Add(new Label { Text = detalle, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.TintaSuave, HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap });
        return pila;
    }

    private static View Cargando(string texto) =>
        Ds.Tarjeta(new Label { Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaSuave, HorizontalTextAlignment = TextAlignment.Center }, Ds.RadioTarjeta, new Thickness(24, 20));

    private static void Avisar(Label mensaje, string texto, Color color)
    {
        mensaje.Text = texto;
        mensaje.TextColor = color;
        mensaje.IsVisible = true;
    }

    private static readonly Color TintaBien = Color.FromArgb("#0B5A38");
    private static readonly Color TintaMal = Color.FromArgb("#8A1C1F");

    /// <summary>Por qué no se pudo guardar algo, con lo que se conservó y lo que sigue (sin códigos ni detalles técnicos).</summary>
    private string TextoDeError(ErrorAula? error, string queNoSePudo)
    {
        if (Sesion.MensajeDePermiso(error, _sesion?.ProfesorRotulo) is { } permiso) return permiso;
        if (error?.Estado == 0) return $"No hay conexión con el aula. {queNoSePudo} por ahora; lo que ya marcaste sigue igual. Revisa la red e inténtalo de nuevo.";
        return $"{queNoSePudo} ahora. Lo que ya marcaste sigue igual; inténtalo de nuevo en un momento.";
    }

    // ---- Participación

    private static int SinEntregar(AlumnoDelResumen alumno) => alumno.Actividades?.Count(a => !a.Entregado) ?? 0;

    private static View SeccionParticipacion(DetalleResumen detalle)
    {
        var alumnos = detalle.Participantes ?? [];
        if (alumnos.Count == 0)
            return Seccion("Participación", Ds.CatClaseEnVivo, null,
                Vacio("Nadie se unió a esta clase.", "El resumen quedó guardado igual. Cuando des otra clase, aquí verás quién participó y qué entregó."));
        // Quien tiene pendientes va primero: es a quien hay que volver.
        var ordenados = alumnos.OrderByDescending(SinEntregar).ThenBy(a => a.Nombre, StringComparer.CurrentCultureIgnoreCase).ToList();
        var lista = new VerticalStackLayout { Spacing = 0 };
        for (var i = 0; i < ordenados.Count; i++)
        {
            if (i > 0) lista.Add(Ds.Separador());
            lista.Add(FilaAlumno(ordenados[i]));
        }
        var conPendientes = ordenados.Count(a => SinEntregar(a) > 0);
        var apoyo = $"{alumnos.Count} {(alumnos.Count == 1 ? "participante" : "participantes")}" + (conPendientes > 0 ? $" · {conPendientes} con pendientes" : " · todo entregado");
        return Seccion("Participación", Ds.CatClaseEnVivo, apoyo, lista);
    }

    private static View FilaAlumno(AlumnoDelResumen alumno)
    {
        var fila = new VerticalStackLayout { Spacing = 6, Padding = new Thickness(0, 12) };
        var pendientes = SinEntregar(alumno);
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cabecera.Add(Ds.Titulo(alumno.Nombre, 18), 0, 0);
        if (pendientes > 0)
        {
            var marca = Ds.Pildora(pendientes == 1 ? "1 sin entregar" : $"{pendientes} sin entregar", Ds.AlertaSuave, Color.FromArgb("#6B5800"));
            marca.VerticalOptions = LayoutOptions.Center;
            cabecera.Add(marca, 1, 0);
        }
        fila.Add(cabecera);
        fila.Add(Ds.Secundario(alumno.AdmisionNominal ? $"estuvo {alumno.PresenteTexto} · admitido por nombre" : $"estuvo {alumno.PresenteTexto}", 14));
        if (alumno.Actividades is { Count: > 0 } actividades)
        {
            var etiquetas = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, AlignItems = FlexAlignItems.Start, Margin = new Thickness(0, 4, 0, 0) };
            foreach (var actividad in actividades) etiquetas.Add(EtiquetaActividad(actividad));
            fila.Add(etiquetas);
        }
        return fila;
    }

    /// <summary>Entregó / sin entregar: lo dicen el texto y el signo (✓ u ○); el color sólo acompaña.</summary>
    private static View EtiquetaActividad(ActividadDeAlumno actividad)
    {
        var rotulo = string.IsNullOrWhiteSpace(actividad.Rotulo) ? "Actividad" : actividad.Rotulo!;
        var etiqueta = actividad.Entregado
            ? Ds.Pildora($"✓  {rotulo} · entregó" + (actividad.Porcentaje is { } p ? $" · {Math.Round(p):0} %" : string.Empty), Ds.ExitoSuave, TintaBien)
            : Ds.Pildora($"○  {rotulo} · sin entregar", Ds.AlertaSuave, Color.FromArgb("#6B5800"));
        etiqueta.Margin = new Thickness(0, 0, 8, 8);
        return etiqueta;
    }

    // ---- Pendientes

    private static View SeccionPendientes(IReadOnlyList<PendienteDelResumen> pendientes)
    {
        var lista = new VerticalStackLayout { Spacing = 8 };
        lista.Add(Ds.Secundario("Estas entregas quedaron sin hacer. Para que se hagan después, deja la actividad como tarea de estudio (más abajo).", 14));
        foreach (var pendiente in pendientes.OrderBy(p => p.Rotulo ?? p.ParticipanteId, StringComparer.CurrentCultureIgnoreCase).ThenBy(p => p.Actividad))
            lista.Add(Ds.Cuerpo($"○  {(string.IsNullOrWhiteSpace(pendiente.Rotulo) ? pendiente.ParticipanteId : pendiente.Rotulo)} · {(string.IsNullOrWhiteSpace(pendiente.Actividad) ? "una actividad" : pendiente.Actividad)} sin entregar", 16));
        return Seccion("Pendientes", Ds.Alerta, pendientes.Count == 1 ? "1 sin entregar" : $"{pendientes.Count} sin entregar", lista);
    }

    // ---- Dejar tarea de estudio

    /// <summary>Las actividades y recursos de la clase. La fuente es la lista de lanzamientos (trae lo ya marcado); el detalle del resumen completa lo que falte.</summary>
    private static List<ItemEstudio> ItemsDeEstudio(SesionDeClase sesion, DetalleResumen detalle)
    {
        var items = new List<ItemEstudio>();
        foreach (var d in sesion.Distribuciones ?? [])
            if (d.Clase is "actividad" or "recurso")
                items.Add(new ItemEstudio(d.Id, string.IsNullOrWhiteSpace(d.Rotulo) ? (d.EsActividad ? "Actividad" : "Recurso") : d.Rotulo!, d.EsActividad, d.DisponibleEstudio, d.EstudioHasta));
        foreach (var r in detalle.Recursos ?? [])
            if (items.All(i => i.Id != r.DistribucionId))
                items.Add(new ItemEstudio(r.DistribucionId, string.IsNullOrWhiteSpace(r.Rotulo) ? "Recurso" : r.Rotulo!, false, r.DisponibleEstudio, null));
        foreach (var alumno in detalle.Participantes ?? [])
            foreach (var a in alumno.Actividades ?? [])
                if (items.All(i => i.Id != a.DistribucionId))
                    items.Add(new ItemEstudio(a.DistribucionId, string.IsNullOrWhiteSpace(a.Rotulo) ? "Actividad" : a.Rotulo!, true, false, null));
        return items;
    }

    private View SeccionEstudio(SesionDeClase sesion, DetalleResumen detalle)
    {
        const string titulo = "Dejar tarea de estudio";
        var items = ItemsDeEstudio(sesion, detalle);
        if (items.Count == 0)
            return Seccion(titulo, Ds.CatQuiz, null, Vacio("Esta clase no tuvo actividades ni recursos.", "Cuando lances alguno, podrás dejarlo aquí para que se estudie después."));
        var archivada = sesion.Estado == "archivada";
        var mensaje = new Label { FontFamily = Ds.FuenteMedia, FontSize = 14, LineBreakMode = LineBreakMode.WordWrap, IsVisible = false, Margin = new Thickness(0, 8, 0, 0) };
        var pila = new VerticalStackLayout { Spacing = 0 };
        if (archivada)
            pila.Add(Ds.Secundario("La clase ya está archivada, así que no se pueden dejar más tareas. Lo que marcaste antes sigue disponible.", 14));
        for (var i = 0; i < items.Count; i++)
        {
            if (i > 0) pila.Add(Ds.Separador());
            pila.Add(FilaEstudio(items[i], archivada, mensaje));
        }
        pila.Add(mensaje);
        return Seccion(titulo, Ds.CatQuiz, archivada ? null : "Elige qué se queda para estudiar y hasta cuándo", pila);
    }

    private View FilaEstudio(ItemEstudio item, bool archivada, Label mensaje)
    {
        var fila = new VerticalStackLayout { Spacing = 10, Padding = new Thickness(0, 12) };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
        var textos = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        textos.Add(Ds.Titulo(item.Rotulo, 18));
        var estado = Ds.Secundario(string.Empty, 14);
        textos.Add(estado);
        cabecera.Add(textos, 0, 0);
        var interruptor = Ds.Boton("Dejar para estudiar", Ds.Rango.Secondary, null, 48, 270);
        var cuerpo = Ds.Capsula(interruptor);
        cuerpo.VerticalOptions = LayoutOptions.Center;
        if (!archivada) cabecera.Add(cuerpo, 1, 0);
        fila.Add(cabecera);
        var fechas = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, AlignItems = FlexAlignItems.Start };
        fila.Add(fechas);
        var ocupado = false;

        void Pintar()
        {
            interruptor.Text = item.Disponible ? "✓  Dejar para estudiar" : "Dejar para estudiar";
            Ds.PintarRelieve(interruptor, item.Disponible ? Ds.Exito : Colors.White, item.Disponible ? Colors.White : Ds.Tinta);
            SemanticProperties.SetDescription(interruptor, item.Disponible ? $"{item.Rotulo}: dejada para estudiar. Tocar para quitarla" : $"{item.Rotulo}: no se dejó para estudiar. Tocar para dejarla");
            var clase = item.EsActividad ? "Actividad" : "Recurso";
            estado.Text = item.Disponible
                ? (item.Hasta is { } h ? $"{clase} · disponible para estudiar hasta el {Fecha(h)}" : $"{clase} · disponible para estudiar, sin fecha límite")
                : $"{clase} · sólo se usó en clase";
            fechas.Children.Clear();
            fechas.IsVisible = item.Disponible && !archivada;
            if (!item.Disponible || archivada) return;
            var cercana = OpcionMasCercana(item);
            foreach (var opcion in OpcionesDeFecha)
                fechas.Add(Chip(opcion.Texto, null, opcion.Dias == cercana, () => GuardarAsync(true, opcion.Dias is { } dias ? AhoraNodo + dias * DiaMs : null)));
        }

        async Task GuardarAsync(bool disponible, long? hasta)
        {
            if (ocupado) return;
            ocupado = true;
            Ds.Habilitar(interruptor, false);
            mensaje.IsVisible = false;
            try
            {
                var aula = Sesion.Aula;
                var guardada = await aula.EstudioAsync(SesionId, Sesion.ProfesorId, item.Id, disponible, hasta);
                if (guardada is null)
                {
                    Avisar(mensaje, TextoDeError(aula.UltimoError, "No pudimos guardar esta marca"), TintaMal);
                    return;
                }
                item.Disponible = guardada.DisponibleEstudio;
                item.Hasta = guardada.EstudioHasta;
                Avisar(mensaje, item.Disponible
                    ? $"Listo · «{item.Rotulo}» queda para estudiar " + (item.Hasta is { } h ? $"hasta el {Fecha(h)}." : "sin fecha límite.")
                    : $"Listo · «{item.Rotulo}» ya no queda para estudiar.", TintaBien);
            }
            finally
            {
                ocupado = false;
                Ds.Habilitar(interruptor, true);
                Pintar();
            }
        }

        interruptor.Clicked += async (_, _) => await GuardarAsync(!item.Disponible, item.Hasta);
        Pintar();
        return fila;
    }

    /// <summary>La fecha límite ya marcada, expresada como la opción más parecida (los chips se marcan por cercanía: el reloj sigue corriendo desde que se guardó).</summary>
    private int? OpcionMasCercana(ItemEstudio item)
    {
        if (item.Hasta is not { } hasta) return null;
        var restante = (hasta - AhoraNodo) / (double)DiaMs;
        var mejor = OpcionesDeFecha.Where(o => o.Dias is not null).OrderBy(o => Math.Abs(restante - o.Dias!.Value)).First();
        return Math.Abs(restante - mejor.Dias!.Value) <= 0.5 ? mejor.Dias : -1;   // -1: una fecha que no es ninguna de las tres; ningún chip se marca
    }

    private static string Fecha(long milisegundosDelNodo) =>
        DateTimeOffset.FromUnixTimeMilliseconds(milisegundosDelNodo).ToLocalTime().ToString("d 'de' MMMM", Es);

    // ---- Tema de la clase (anclaje curricular)

    private async Task CargarTemaAsync(SesionDeClase sesion, VerticalStackLayout host)
    {
        host.Clear();
        var aula = Sesion.Aula;
        var datos = await EsperarAsync(aula.AnclajeAsync(sesion.Id), () => host.Add(Seccion(TituloTema, Ds.CatClaseEnVivo, null, Vacio("Buscando los temas que tocó la clase…"))));
        host.Clear();
        if (datos is null)
        {
            // Degradado: el anclaje no se pudo leer. Nunca impide salir ni cerrar; se puede hacer más tarde.
            var permiso = Sesion.MensajeDePermiso(aula.UltimoError, sesion.ProfesorRotulo);
            var contenido = new VerticalStackLayout { Spacing = 12 };
            contenido.Add(Vacio(permiso is null ? "No pudimos leer los temas de la clase." : "No puedes anclar esta clase.",
                permiso ?? "La clase quedó guardada. Puedes anclarla más tarde; no hace falta para salir."));
            if (permiso is null)
            {
                var reintentar = Ds.Capsula(Ds.Boton("Reintentar", Ds.Rango.Secondary, async (_, _) => await CargarTemaAsync(sesion, host), 56, 200));
                reintentar.HorizontalOptions = LayoutOptions.Center;
                contenido.Add(reintentar);
            }
            host.Add(Seccion(TituloTema, Ds.CatClaseEnVivo, "Opcional", contenido));
            return;
        }
        host.Add(SeccionTema(sesion, datos));
    }

    private View SeccionTema(SesionDeClase sesion, AnclajeAula datos)
    {
        // Los ya anclados van elegidos; las sugerencias, sin elegir. Tocar un chip lo elige o lo quita; «Anclar» reemplaza la lista.
        var nodos = new List<NodoAnclaje>();
        var guardados = new HashSet<string>(StringComparer.Ordinal);
        foreach (var anclado in datos.Anclajes ?? [])
            if (nodos.All(n => n.Ref != anclado.Ref)) { nodos.Add(anclado); guardados.Add(anclado.Ref); }
        foreach (var sugerido in datos.Sugerencias ?? [])
            if (nodos.All(n => n.Ref != sugerido.Ref)) nodos.Add(sugerido);
        if (nodos.Count == 0)
            return Seccion(TituloTema, Ds.CatClaseEnVivo, "Opcional",
                Vacio("No hay sugerencias de tema para esta clase. Puedes anclarla más tarde.", string.IsNullOrWhiteSpace(datos.Motivo) ? null : datos.Motivo));

        var seleccion = new HashSet<string>(guardados, StringComparer.Ordinal);
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Secundario("Toca los temas que tocó la clase y pulsa Anclar. Sirve para ubicarla en el plan de estudios; no hace falta para salir.", 14));
        var chips = new FlexLayout { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, AlignItems = FlexAlignItems.Start };
        pila.Add(chips);
        var mensaje = new Label { FontFamily = Ds.FuenteMedia, FontSize = 14, LineBreakMode = LineBreakMode.WordWrap, IsVisible = false };
        pila.Add(mensaje);
        var anclar = Ds.Boton("Anclar", Ds.Rango.Secondary, null, 56, 170);
        var pendiente = Ds.Boton("Dejar pendiente", Ds.Rango.Quiet, null, 56, 210);
        var acciones = new HorizontalStackLayout { Spacing = 12 };
        acciones.Add(Ds.Capsula(anclar));
        acciones.Add(pendiente);
        pila.Add(acciones);

        void Pintar()
        {
            chips.Children.Clear();
            foreach (var nodo in nodos)
                chips.Add(Chip(nodo.Texto, guardados.Contains(nodo.Ref) ? "anclado" : nodo.Origen, seleccion.Contains(nodo.Ref), () =>
                {
                    if (!seleccion.Add(nodo.Ref)) seleccion.Remove(nodo.Ref);
                    mensaje.IsVisible = false;
                    Pintar();
                    return Task.CompletedTask;
                }));
            Ds.Habilitar(anclar, !seleccion.SetEquals(guardados));
        }

        async Task AnclarAsync()
        {
            Ds.Habilitar(anclar, false);
            try
            {
                var elegidos = nodos.Where(n => seleccion.Contains(n.Ref)).ToList();
                var aula = Sesion.Aula;
                var respuesta = await aula.AnclarAsync(sesion.Id, Sesion.ProfesorId, elegidos);
                if (respuesta is null)
                {
                    Avisar(mensaje, TextoDeError(aula.UltimoError, "No pudimos anclar los temas"), TintaMal);
                    return;
                }
                var vigentes = respuesta.Anclajes ?? elegidos;
                foreach (var nodo in vigentes)
                    if (nodos.All(n => n.Ref != nodo.Ref)) nodos.Add(nodo);
                guardados.Clear();
                seleccion.Clear();
                foreach (var nodo in vigentes) { guardados.Add(nodo.Ref); seleccion.Add(nodo.Ref); }
                Avisar(mensaje, vigentes.Count == 0
                    ? "Listo · la clase quedó sin tema anclado. Puedes anclarla más tarde."
                    : $"Listo · quedó anclado: {string.Join(", ", vigentes.Select(n => n.Texto))}. Se guardó con la clase.", TintaBien);
            }
            finally { Pintar(); }
        }

        anclar.Clicked += async (_, _) => await AnclarAsync();
        // «Dejar pendiente» no exige ni hace nada más que seguir (BR-039, UXR-001): la clase queda como está.
        pendiente.Clicked += (_, _) => Avisar(mensaje, "Quedó pendiente. Puedes anclar el tema de esta clase más tarde; nada te lo exige.", Ds.TintaSuave);
        Pintar();
        return Seccion(TituloTema, Ds.CatClaseEnVivo, "Opcional · puedes salir sin anclar", pila);
    }

    /// <summary>Chip tocable de selección: el estado lo dicen el ✓ y el fondo oscuro, no sólo el color. Al menos 44 px de alto.</summary>
    private static Border Chip(string texto, string? pie, bool elegido, Func<Task> alTocar)
    {
        var pila = new VerticalStackLayout { Spacing = 1, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label
        {
            Text = (elegido ? "✓  " : string.Empty) + texto, FontFamily = Ds.FuenteMedia, FontSize = 15,
            TextColor = elegido ? Colors.White : Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap,
        });
        if (!string.IsNullOrWhiteSpace(pie))
            pila.Add(new Label { Text = pie, FontFamily = Ds.FuenteRegular, FontSize = 11, TextColor = elegido ? Color.FromArgb("#D9FFFFFF") : Ds.TintaSuave });
        var chip = new Border
        {
            BackgroundColor = elegido ? Ds.Tinta : Colors.White,
            Stroke = new SolidColorBrush(elegido ? Ds.Tinta : Color.FromArgb("#33000000")),
            StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = 22 },
            Padding = new Thickness(16, 8),
            MinimumHeightRequest = 44,
            Margin = new Thickness(0, 0, 10, 10),
            Content = pila,
        };
        SemanticProperties.SetDescription(chip, $"{texto}. {(elegido ? "Elegido" : "Sin elegir")}. Tocar para cambiar");
        Ds.Tocable(chip, alTocar);
        return chip;
    }

    private void Tarjeta(string titulo, string valor, string detalle, Color color)
    {
        var pila = new VerticalStackLayout { Spacing = 4, WidthRequest = 250 };
        pila.Add(Ds.Pildora(titulo, color));
        pila.Add(new Label { Text = valor, FontSize = 44, FontAttributes = FontAttributes.Bold, TextColor = Ds.Tinta });
        pila.Add(Ds.Secundario(detalle, 14));
        var tarjeta = Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18));
        tarjeta.Margin = new Thickness(8);
        ResumenHost.Children.Add(tarjeta);
    }
}
