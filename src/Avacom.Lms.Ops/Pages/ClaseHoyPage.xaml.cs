using System.Globalization;
using System.Text;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P1 · Materias de hoy. Un hexágono por asignatura y, debajo, sus cursos como tarjetas.
/// Las materias las entrega AVACOM Biblioteca (API de Contenido v2) a través del backend, siempre:
/// si la biblioteca no está encendida se dice y se puede reintentar tocando el chip de la fuente.
/// Todo el journey de MOD-007 empieza aquí; nada se escribe en esta pantalla.
///
/// Desde 2026-09-28 la pantalla viste el lenguaje Liquid Glass (<see cref="Glass"/>): fondo claro con la imagen de
/// discos en relieve, menú vertical fijo y sólido a la izquierda (Menú principal, Lección, Configuración y Cerrar
/// sesión, apilados desde abajo para el tablero táctil) y láminas de vidrio para las tarjetas, los avisos y el chip
/// de la fuente. Bajo el hero, un buscador con picklists (País y Nivel y, en «Más filtros», Grado y Materia) y texto
/// libre filtra el catálogo que entrega la biblioteca: <see cref="PintarCatalogo"/> vuelve a pintar hexágonos y
/// tarjetas con los cursos que coinciden. El tema no tiene picklist: en producción se estiman unos 25 000 temas, así
/// que se busca escribiéndolo (el texto también entra por título, descripción, clasificación y códigos). La lógica de carga no cambió: los mismos hosts (<c>AvisoHost</c>, <c>HexHost</c>,
/// <c>ListaHost</c>), el mismo chip tocable con sus cinco estados, las mismas rutas y la regla de un solo Primary
/// por pantalla («Continuar la clase»).
/// </summary>
public partial class ClaseHoyPage : ContentPage
{
    /// <summary>Nombres de país para los códigos ISO que trae la clasificación; un código desconocido se muestra tal cual.</summary>
    private static readonly Dictionary<string, string> Paises = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CO"] = "Colombia", ["US"] = "Estados Unidos", ["MX"] = "México", ["ES"] = "España", ["AR"] = "Argentina",
        ["PE"] = "Perú", ["CL"] = "Chile", ["EC"] = "Ecuador", ["PA"] = "Panamá", ["CR"] = "Costa Rica", ["GT"] = "Guatemala",
    };

    private readonly FilterPicker _pais = new() { Placeholder = "Todos los países" };
    private readonly FilterPicker _nivel = new() { Placeholder = "Todos los niveles" };
    private readonly FilterPicker _grado = new() { Placeholder = "Todos los grados" };
    private readonly FilterPicker _materia = new() { Placeholder = "Todas las materias" };

    private CatalogoAula? _catalogo;
    private bool _cargando;

    public ClaseHoyPage()
    {
        InitializeComponent();
        // Tocar el chip vuelve a leer la biblioteca, sin teclado.
        Ds.Tocable(FuenteChip, async () => await CargarAsync());
        // Buscador: País y Nivel a la vista; Grado y Materia bajo «Más filtros». Cualquier cambio repinta el catálogo.
        foreach (var filtro in new[] { _pais, _nivel })
        {
            filtro.SelectionChanged += (_, _) => PintarCatalogo();
            Buscador.AgregarFiltro(filtro);
        }
        foreach (var filtro in new[] { _grado, _materia })
        {
            filtro.SelectionChanged += (_, _) => PintarCatalogo();
            Buscador.AgregarFiltro(filtro, extra: true);
        }
        Buscador.TextChanged += (_, _) => PintarCatalogo();
        Buscador.LimpiarTapped += (_, _) => PintarCatalogo();
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await CargarAsync();
    }

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            var aula = Sesion.Aula;
            _catalogo = null;
            AvisoHost.Clear();
            HexHost.Children.Clear();
            ListaHost.Clear();

            // Una clase quedó abierta en este equipo: ofrecer continuarla antes que nada (BR-051).
            if (Sesion.ClaseAbiertaId is { } abierta)
            {
                var sesion = await aula.SesionAsync(abierta);
                if (sesion is { Activa: true }) AvisoHost.Add(TarjetaContinuar(sesion));
                else if (sesion is { Cerrada: true } && (sesion.OrigenCierre ?? sesion.Resumen?.OrigenCierre) == "inactividad")
                {
                    // 007-03 · MSG-025: la clase se cerró sola a los 120 min sin actividad. Se cuenta una sola vez y se suelta: ya no se reabre.
                    Sesion.ClaseAbiertaId = null;
                    AvisoHost.Add(AvisoInactividad(sesion));
                }
                else if (sesion is not null) Sesion.ClaseAbiertaId = null;
                else if (Sesion.MensajeDePermiso(aula.UltimoError) is { } permiso)
                {
                    // La clase guardada es de otra persona: no se puede continuar desde aquí, y no se vuelve a ofrecer.
                    Sesion.ClaseAbiertaId = null;
                    AvisoHost.Add(Glass.Alerta("Esa clase no se puede continuar desde aquí", permiso, Glass.Tono.Info));
                }
            }

            var catalogo = await aula.CursosAsync();
            if (catalogo is null)
            {
                var error = aula.UltimoError;
                var sinBiblioteca = aula.Fuente == Sesion.FuenteBiblioteca && error?.Codigo == "fuente_no_disponible";
                // 007-10: el nodo contestó pero este perfil no puede ver las materias: se dice con palabras de aula, no con el detalle técnico.
                var sinPermiso = error?.Codigo == "sin_permiso";
                PintarFuente(sinPermiso, sinBiblioteca ? "sin_biblioteca" : sinPermiso ? aula.Fuente : aula.UltimoMotivo);
                var pila = new VerticalStackLayout { Spacing = 12 };
                pila.Add(sinPermiso
                    ? Glass.Alerta("Tu perfil no puede ver las materias de este aula", "No se cambió nada. Pide a la administración que te asigne una materia y vuelve a intentarlo.", Glass.Tono.Info)
                    : Glass.Alerta(sinBiblioteca ? "AVACOM Biblioteca no está encendida en este equipo" : "No se pudieron leer las materias",
                        string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))),
                        sinBiblioteca ? Glass.Tono.Alerta : Glass.Tono.Peligro));
                // Un solo Primary por pantalla: si ya hay «Continuar la clase», «Reintentar» baja a Secondary (vidrio).
                var botones = new HorizontalStackLayout { Spacing = 16 };
                EventHandler reintentar = async (_, _) => await CargarAsync();
                botones.Add(AvisoHost.Count == 0 ? Ds.Boton("Reintentar", Ds.Rango.Primary, reintentar, 64, 220) : Glass.Boton("Reintentar", reintentar, 64, 220));
                pila.Add(botones);
                AvisoHost.Add(pila);
                return;
            }

            PintarFuente(true, catalogo.Fuente);
            if (catalogo.Asignaturas.Count == 0)
            {
                SubtituloLabel.Text = "Sin materias asignadas";
                ListaHost.Add(Glass.EstadoVacio("Nada por aquí todavía", "Cuando la escuela asigne una materia en AVACOM Biblioteca, aparecerá aquí.", Sesion.IconoLibro));
                return;
            }

            _catalogo = catalogo;
            PoblarFiltros(catalogo);
            PintarCatalogo();
        }
        finally { _cargando = false; }
    }

    // ------------------------------------------------------------------ filtros

    /// <summary>Los picklists ofrecen sólo lo que hay en el catálogo: valores distintos, en el orden de la clasificación.</summary>
    private void PoblarFiltros(CatalogoAula catalogo)
    {
        var cursos = catalogo.Asignaturas.SelectMany(a => a.Cursos).ToList();
        _pais.Poblar(cursos.Select(c => NombrePais(c.Clasificacion?.Pais)).Where(x => x is not null).Distinct().OrderBy(x => x, StringComparer.CurrentCultureIgnoreCase)!);
        _nivel.Poblar(Ordenados(cursos.Select(c => c.Clasificacion?.Nivel)));
        _grado.Poblar(Ordenados(cursos.Select(c => c.Clasificacion?.Grado)));
        _materia.Poblar(catalogo.Asignaturas.Select(a => a.Nombre).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct());
    }

    private static IEnumerable<string> Ordenados(IEnumerable<NodoClasificacion?> nodos) => nodos
        .Where(n => !string.IsNullOrWhiteSpace(n?.Nombre))
        .GroupBy(n => n!.Nombre!)
        .OrderBy(g => g.Min(n => n!.Orden ?? int.MaxValue))
        .ThenBy(g => g.Key, StringComparer.CurrentCultureIgnoreCase)
        .Select(g => g.Key);

    private static string? NombrePais(string? codigo) =>
        string.IsNullOrWhiteSpace(codigo) ? null : Paises.TryGetValue(codigo, out var nombre) ? nombre : codigo;

    private bool HayFiltros => _pais.Selected is not null || _nivel.Selected is not null
        || _grado.Selected is not null || _materia.Selected is not null || Normalizar(Buscador.Text).Length > 0;

    /// <summary>Un curso coincide si pasa todos los picklists y, si hay texto, cada palabra aparece en algún campo (título, descripción, clasificación o códigos).</summary>
    private bool Coincide(FichaCurso curso, AsignaturaAula asignatura, string[] palabras)
    {
        var cl = curso.Clasificacion;
        if (_pais.Selected is { } pais && NombrePais(cl?.Pais) != pais) return false;
        if (_nivel.Selected is { } nivel && cl?.Nivel?.Nombre != nivel) return false;
        if (_grado.Selected is { } grado && cl?.Grado?.Nombre != grado) return false;
        if (_materia.Selected is { } materia && asignatura.Nombre != materia) return false;
        if (palabras.Length == 0) return true;
        var campos = new[]
        {
            curso.Titulo, curso.Subtitulo, curso.Descripcion, curso.CursoRef, asignatura.Nombre, asignatura.Codigo,
            cl?.Pais, NombrePais(cl?.Pais), cl?.Idioma, cl?.Nivel?.Nombre, cl?.Nivel?.Codigo, cl?.Grado?.Nombre, cl?.Grado?.Codigo,
            cl?.Tema?.Nombre, cl?.Tema?.Codigo, cl?.Asignatura?.Nombre, cl?.Asignatura?.Codigo,
        }.Where(x => !string.IsNullOrWhiteSpace(x)).Select(x => Normalizar(x!)).ToList();
        return palabras.All(p => campos.Any(c => c.Contains(p, StringComparison.Ordinal)));
    }

    /// <summary>Minúsculas y sin tildes, para que «matematicas» encuentre «Matemáticas».</summary>
    private static string Normalizar(string? texto)
    {
        if (string.IsNullOrWhiteSpace(texto)) return string.Empty;
        var descompuesto = texto.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(descompuesto.Length);
        foreach (var c in descompuesto)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
        return sb.ToString().Normalize(NormalizationForm.FormC);
    }

    /// <summary>Vuelve a pintar hexágonos y secciones con los cursos que pasan la búsqueda y los filtros. Los colores de materia no cambian al filtrar.</summary>
    private void PintarCatalogo()
    {
        if (_catalogo is null) return;
        HexHost.Children.Clear();
        ListaHost.Clear();
        var palabras = Normalizar(Buscador.Text).Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var indice = 0;
        var coincidencias = 0;
        foreach (var asignatura in _catalogo.Asignaturas)
        {
            // Cada materia con su acento (rosa, azul, ámbar, violeta…): lo comparten el hexágono, la píldora y el icono del curso.
            var color = Glass.AcentoMateria(asignatura.Nombre, indice++);
            var cursos = asignatura.Cursos.Where(c => Coincide(c, asignatura, palabras)).ToList();
            if (cursos.Count == 0) continue;
            coincidencias += cursos.Count;
            var tile = new ProfessorHexTile
            {
                Text = asignatura.Nombre, AccentColor = color, IconGeometry = Sesion.IconoLibro, Glass = true, Margin = new Thickness(8, 6),
            };
            var seccion = SeccionAsignatura(asignatura, cursos, color);
            tile.Tapped += async (_, _) => await Contenido.ScrollToAsync(seccion, ScrollToPosition.Start, true);
            HexHost.Children.Add(tile);
            ListaHost.Add(seccion);
        }

        var total = _catalogo.Asignaturas.Sum(a => a.Cursos.Count);
        var materias = _catalogo.Asignaturas.Count == 1 ? "1 materia asignada" : $"{_catalogo.Asignaturas.Count} materias asignadas";
        SubtituloLabel.Text = HayFiltros ? $"{materias} · {coincidencias} de {total} cursos coinciden" : materias;
        if (coincidencias == 0) ListaHost.Add(SinResultados());
    }

    private View SinResultados()
    {
        var pila = new VerticalStackLayout { Spacing = 16, HorizontalOptions = LayoutOptions.Center };
        pila.Add(Glass.EstadoVacio("Sin resultados con estos filtros", "Prueba con otra búsqueda o quita algún filtro para volver a ver las materias."));
        var limpiar = Glass.Boton("Limpiar filtros", (_, _) =>
        {
            Buscador.Limpiar();
            PintarCatalogo();
        }, 64, 220);
        limpiar.HorizontalOptions = LayoutOptions.Center;
        pila.Add(limpiar);
        return pila;
    }

    // --------------------------------------------------------------- secciones

    private View SeccionAsignatura(AsignaturaAula asignatura, IReadOnlyList<FichaCurso> cursos, Color color)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cabecera.Add(Glass.Pildora(asignatura.Nombre, color), 0, 0);
        var conteo = Glass.Secundario(cursos.Count == 1 ? "1 curso" : $"{cursos.Count} cursos", 15);
        conteo.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(conteo, 2, 0);
        pila.Add(cabecera);
        foreach (var curso in cursos) pila.Add(TarjetaCurso(curso, color));
        return pila;
    }

    private View TarjetaCurso(FichaCurso curso, Color color)
    {
        // Toda la tarjeta es tocable y el botón «Ver lecciones ›» hace lo mismo (lo resuelve CourseGlassCard).
        var tarjeta = new CourseGlassCard
        {
            Titulo = curso.Titulo, Subtitulo = curso.Subtitulo, Detalle = curso.Detalle, AccentColor = color, IconGeometry = Sesion.IconoLibro,
        };
        if (curso.NoDisponible is { } motivo)
        {
            // La biblioteca lo lista pero no lo sirve (paquete que no pasa su verificación): se ve atenuado y,
            // al tocarlo, explica qué hacer en vez de abrir una clase que fallaría.
            tarjeta.Opacity = 0.55;
            tarjeta.AccentColor = Ds.Alerta;
            tarjeta.Abrir += async (_, _) => await DisplayAlertAsync("Curso no disponible",
                motivo.Sugerencia ?? motivo.Detalle ?? "El paquete instalado no pasa la verificación de AVACOM Contenido.", "Entendido");
            return tarjeta;
        }
        tarjeta.Abrir += async (_, _) => await AbrirAsync(curso);
        return tarjeta;
    }

    private View TarjetaContinuar(SesionDeClase sesion)
    {
        var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        var suspendida = sesion.Suspendida;
        var estado = Glass.Pildora(suspendida ? "Clase suspendida · mismo código" : "Clase abierta", suspendida ? Ds.Alerta : Glass.AcentoRosa);
        estado.HorizontalOptions = LayoutOptions.Start;
        textos.Add(estado);
        textos.Add(Glass.Titulo(sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre", 22));
        // Suspendida (007-02): se dice dónde iba la clase y que el código sigue siendo el mismo; abierta: el conteo de siempre.
        textos.Add(Glass.Cuerpo(suspendida ? $"Código {sesion.CodigoUnion}" : $"Código {sesion.CodigoUnion} · {sesion.Conteo?.Conectados ?? 0} conectados", 15));
        if (suspendida)
            textos.Add(Glass.Cuerpo(string.Join(" ", new[] { sesion.Recuperacion?.Texto, "Puedes continuar cuando quieras." }.Where(x => !string.IsNullOrWhiteSpace(x))), 15));
        grid.Add(textos, 0, 0);
        // El único Primary de la pantalla: continuar la clase abierta o reanudar la suspendida.
        var mensajes = new VerticalStackLayout { Spacing = 8 };
        Button accion = null!;
        accion = suspendida
            ? Ds.Boton("Reanudar clase", Ds.Rango.Primary, async (_, _) => await ReanudarAsync(sesion, accion, mensajes), 64, 240)
            : Ds.Boton("Continuar la clase", Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(sesion.Id)}"), 64, 240);
        accion.VerticalOptions = LayoutOptions.Center;
        grid.Add(accion, 1, 0);
        // Tinte violeta (el VioletaSuave del kit, en vidrio) que la distingue del resto de láminas: es la tarjeta que manda.
        var tarjeta = new LiquidGlassPanel
        {
            CornerRadius = Ds.RadioTarjeta, TintColor = Glass.Violeta, TintOpacity = 0.18, BlurRadius = 10,
            ContentPadding = new Thickness(22, 18), ShadowOpacity = 0.14, Content = grid,
        };
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(tarjeta);
        pila.Add(mensajes);
        return pila;
    }

    /// <summary>
    /// «Reanudar clase» (007-02): la sesión suspendida vuelve a abierta con el mismo código y el profesor entra a ella. Si no se puede,
    /// la clase sigue guardada tal cual y se dice qué hacer (nunca el detalle técnico).
    /// </summary>
    private async Task ReanudarAsync(SesionDeClase sesion, Button boton, VerticalStackLayout mensajes)
    {
        mensajes.Clear();
        Ds.Habilitar(boton, false);
        try
        {
            var aula = Sesion.Aula;
            if (await aula.ReanudarAsync(sesion.Id, Sesion.ProfesorId) is not null)
            {
                Sesion.ClaseAbiertaId = sesion.Id;
                await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(sesion.Id)}");
                return;
            }
            var error = aula.UltimoError;
            var texto = Sesion.MensajeDePermiso(error, sesion.ProfesorRotulo)
                ?? (error?.Estado == 0
                    ? "No hay conexión con el aula. La clase sigue suspendida con el mismo código; revisa la red e inténtalo de nuevo."
                    : "No pudimos reanudar la clase ahora. Sigue guardada con el mismo código; inténtalo de nuevo en un momento.");
            mensajes.Add(Glass.Alerta("La clase todavía no se reanudó", texto, Glass.Tono.Alerta));
        }
        finally { Ds.Habilitar(boton, true); }
    }

    /// <summary>
    /// MSG-025 (007-03): «Cerramos tu clase por inactividad y guardamos todo lo del día.» Informativo y de una sola vez: «Entendido» lo quita
    /// y «Ver resumen» abre el cierre de esa clase, donde aún se puede anclar el tema y dejar tareas de estudio.
    /// </summary>
    private View AvisoInactividad(SesionDeClase sesion)
    {
        var raiz = new VerticalStackLayout { Spacing = 10 };
        raiz.Add(Glass.Alerta("Cerramos tu clase por inactividad y guardamos todo lo del día.",
            "No se perdió nada: el resumen de la clase quedó guardado. Puedes revisarlo o empezar otra clase desde aquí.", Glass.Tono.Info));
        var acciones = new HorizontalStackLayout { Spacing = 12, HorizontalOptions = LayoutOptions.End };
        acciones.Add(Glass.Boton("Ver resumen", async (_, _) => await Shell.Current.GoToAsync($"clase-cierre?sesion={Uri.EscapeDataString(sesion.Id)}"), 48, 170));
        acciones.Add(Ds.Boton("Entendido", Ds.Rango.Quiet, (_, _) => AvisoHost.Remove(raiz), 48, 140));
        raiz.Add(acciones);
        return raiz;
    }

    private void PintarFuente(bool ok, string? detalle)
    {
        var sinBiblioteca = detalle == "sin_biblioteca";
        FuenteChip.Mostrar(
            ok ? "Biblioteca conectada" : (sinBiblioteca ? "Biblioteca apagada · tocar para reintentar" : "Sin conexión con el aula"),
            ok ? Glass.Tono.Exito : (sinBiblioteca ? Glass.Tono.Alerta : Glass.Tono.Peligro));
    }

    private static Task AbrirAsync(FichaCurso curso) =>
        Shell.Current.GoToAsync($"clase-curso?curso={Uri.EscapeDataString(curso.CursoRef)}&titulo={Uri.EscapeDataString(curso.Titulo)}");

    private async void OnVolver(object? sender, EventArgs e) => await Shell.Current.GoToAsync("..");

    /// <summary>«Lección»: la clase abierta si la hay (P3); si no, baja a la lista de cursos, donde se elige la lección.</summary>
    private async void OnLeccion(object? sender, EventArgs e)
    {
        if (Sesion.ClaseAbiertaId is { } abierta)
        {
            await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(abierta)}");
            return;
        }
        if (ListaHost.Count > 0) await Contenido.ScrollToAsync(ListaHost, ScrollToPosition.Start, true);
    }

    /// <summary>La configuración del nodo está representada en el prototipo, como los módulos del tablero: un toque para cerrar.</summary>
    private async void OnConfiguracion(object? sender, EventArgs e) =>
        await DisplayAlertAsync("Configuración", "La configuración del nodo del aula está representada en este prototipo y lista para conectar su flujo.", "Entendido");

    /// <summary>Cierra la sesión de usuario (si el nodo exige una) y vuelve al acceso; la clase abierta sigue guardada.</summary>
    private async void OnCerrarSesion(object? sender, EventArgs e)
    {
        await Sesion.CerrarSesionDeUsuarioAsync();
        await Shell.Current.GoToAsync("//login");
    }

    /// <summary>Menú fijo de 216 px en pantallas grandes, 196 en anchos intermedios y raíl de iconos si no cabe; nunca una barra horizontal.</summary>
    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var compacto = Width < 1100;
        Marco.ColumnDefinitions[0].Width = new GridLength(compacto ? 84 : Width < 1400 ? 196 : 216);
        Navegacion.Compact = compacto;
        MenuPanel.Padding = compacto ? new Thickness(6, 16) : new Thickness(12, 16);
    }
}
