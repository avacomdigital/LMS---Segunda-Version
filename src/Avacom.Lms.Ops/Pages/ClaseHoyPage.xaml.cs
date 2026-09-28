using System.Globalization;
using System.Text;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// P1 · Materias de hoy. Un hexágono por asignatura y, debajo, sus cursos como tarjetas.
/// Las materias las entrega AVACOM Biblioteca (API de Contenido v2) a través del backend; si la
/// biblioteca no está en el equipo, se ofrece el curso de ejemplo («Ciencias naturales») con un
/// toque, y el chip de la fuente permite volver. Todo el journey de MOD-007 empieza aquí; nada se
/// escribe en esta pantalla.
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
        // Tocar el chip alterna la fuente sin teclado: de ejemplo a biblioteca y viceversa.
        Ds.Tocable(FuenteChip, async () =>
        {
            Sesion.FuenteAula = Sesion.FuenteAula == Sesion.FuenteEjemplo ? Sesion.FuenteBiblioteca : Sesion.FuenteEjemplo;
            await CargarAsync();
        });
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
                else if (sesion is not null) Sesion.ClaseAbiertaId = null;
            }

            var catalogo = await aula.CursosAsync();
            if (catalogo is null)
            {
                var error = aula.UltimoError;
                var sinBiblioteca = aula.Fuente == Sesion.FuenteBiblioteca && error?.Codigo == "fuente_no_disponible";
                PintarFuente(false, sinBiblioteca ? "sin_biblioteca" : aula.UltimoMotivo);
                var pila = new VerticalStackLayout { Spacing = 12 };
                pila.Add(Glass.Alerta(sinBiblioteca ? "AVACOM Biblioteca no está encendida en este equipo" : "No se pudieron leer las materias",
                    string.Join(" ", new[] { error?.Detalle, error?.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x))),
                    sinBiblioteca ? Glass.Tono.Alerta : Glass.Tono.Peligro));
                var botones = new HorizontalStackLayout { Spacing = 16 };
                botones.Add(Glass.Boton("Reintentar", async (_, _) => await CargarAsync(), 64, 220));
                if (sinBiblioteca)
                {
                    // Un toque, sin teclado: seguir con el manifiesto de ejemplo hasta que la biblioteca esté.
                    // Un solo Primary por pantalla: si ya hay «Continuar la clase», este baja a Secondary (vidrio).
                    EventHandler usarEjemplo = async (_, _) =>
                    {
                        Sesion.FuenteAula = Sesion.FuenteEjemplo;
                        await CargarAsync();
                    };
                    botones.Add(AvisoHost.Count == 0
                        ? Ds.Boton("Usar el curso de ejemplo", Ds.Rango.Primary, usarEjemplo, 64, 300)
                        : Glass.Boton("Usar el curso de ejemplo", usarEjemplo, 64, 300));
                }
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
        tarjeta.Abrir += async (_, _) => await AbrirAsync(curso);
        return tarjeta;
    }

    private View TarjetaContinuar(SesionDeClase sesion)
    {
        var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        var suspendida = sesion.Estado == "suspendida";
        var estado = Glass.Pildora(suspendida ? "Clase suspendida · mismo código" : "Clase abierta", suspendida ? Ds.Alerta : Glass.AcentoRosa);
        estado.HorizontalOptions = LayoutOptions.Start;
        textos.Add(estado);
        textos.Add(Glass.Titulo(sesion.LeccionRotulo ?? sesion.CursoRotulo ?? "Clase libre", 22));
        textos.Add(Glass.Cuerpo($"Código {sesion.CodigoUnion} · {sesion.Conteo?.Conectados ?? 0} conectados", 15));
        grid.Add(textos, 0, 0);
        // El único Primary de la pantalla.
        var continuar = Ds.Boton("Continuar la clase", Ds.Rango.Primary, async (_, _) => await Shell.Current.GoToAsync($"clase-sesion?sesion={Uri.EscapeDataString(sesion.Id)}"), 64, 240);
        continuar.VerticalOptions = LayoutOptions.Center;
        grid.Add(continuar, 1, 0);
        // Tinte violeta (el VioletaSuave del kit, en vidrio) que la distingue del resto de láminas: es la tarjeta que manda.
        return new LiquidGlassPanel
        {
            CornerRadius = Ds.RadioTarjeta, TintColor = Glass.Violeta, TintOpacity = 0.18, BlurRadius = 10,
            ContentPadding = new Thickness(22, 18), ShadowOpacity = 0.14, Content = grid,
        };
    }

    private void PintarFuente(bool ok, string? detalle)
    {
        var ejemplo = detalle == Sesion.FuenteEjemplo;
        var sinBiblioteca = detalle == "sin_biblioteca";
        FuenteChip.Mostrar(
            ok ? (ejemplo ? "Curso de ejemplo · tocar para usar Biblioteca" : "Biblioteca conectada")
               : (sinBiblioteca ? "Biblioteca apagada · tocar para usar el ejemplo" : "Sin conexión con el aula"),
            ok ? (ejemplo ? Glass.Tono.Alerta : Glass.Tono.Exito) : (sinBiblioteca ? Glass.Tono.Alerta : Glass.Tono.Peligro));
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

    private async void OnCerrarSesion(object? sender, EventArgs e) => await Shell.Current.GoToAsync("//login");

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
