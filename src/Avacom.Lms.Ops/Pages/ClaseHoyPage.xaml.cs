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
/// Desde 2026-09-28 la pantalla viste el lenguaje Liquid Glass (<see cref="Glass"/>): fondo lavanda con panal,
/// menú vertical fijo a la izquierda (Menú principal, Lección, Configuración y Cerrar sesión, apilados desde
/// abajo para el tablero táctil) y láminas de vidrio para las tarjetas, los avisos y el chip de la fuente. La lógica
/// no cambió: los mismos hosts (<c>AvisoHost</c>, <c>HexHost</c>, <c>ListaHost</c>), el mismo chip tocable con sus
/// cinco estados, las mismas rutas y la regla de un solo Primary por pantalla («Continuar la clase»).
/// </summary>
public partial class ClaseHoyPage : ContentPage
{
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
            SubtituloLabel.Text = catalogo.Asignaturas.Count == 1 ? "1 materia asignada" : $"{catalogo.Asignaturas.Count} materias asignadas";
            if (catalogo.Asignaturas.Count == 0)
            {
                ListaHost.Add(Glass.EstadoVacio("Nada por aquí todavía", "Cuando la escuela asigne una materia en AVACOM Biblioteca, aparecerá aquí.", Sesion.IconoLibro));
                return;
            }

            var indice = 0;
            foreach (var asignatura in catalogo.Asignaturas)
            {
                // Cada materia con su acento (rosa, azul, ámbar, violeta…): lo comparten el hexágono, la píldora y el icono del curso.
                var color = Glass.AcentoMateria(asignatura.Nombre, indice);
                var tile = new ProfessorHexTile
                {
                    Text = asignatura.Nombre, AccentColor = color, IconGeometry = Sesion.IconoLibro, Glass = true, Margin = new Thickness(8, 6),
                };
                var seccion = SeccionAsignatura(asignatura, color, indice++);
                tile.Tapped += async (_, _) => await Contenido.ScrollToAsync(seccion, ScrollToPosition.Start, true);
                HexHost.Children.Add(tile);
                ListaHost.Add(seccion);
            }
        }
        finally { _cargando = false; }
    }

    private View SeccionAsignatura(AsignaturaAula asignatura, Color color, int indice)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cabecera.Add(Glass.Pildora(asignatura.Nombre, color), 0, 0);
        var conteo = Glass.Secundario(asignatura.Cursos.Count == 1 ? "1 curso" : $"{asignatura.Cursos.Count} cursos", 15);
        conteo.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(conteo, 2, 0);
        pila.Add(cabecera);
        foreach (var curso in asignatura.Cursos) pila.Add(TarjetaCurso(curso, color));
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
        // Violeta más intenso que el resto de láminas: es la tarjeta que manda.
        return new LiquidGlassPanel
        {
            CornerRadius = Ds.RadioTarjeta, TintColor = Glass.Violeta, TintOpacity = 0.42, BlurRadius = 10,
            ContentPadding = new Thickness(22, 18), ShadowOpacity = 0.28, Content = grid,
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

    /// <summary>Menú fijo de 250 px en pantallas grandes, 224 en anchos intermedios y raíl de iconos si no cabe; nunca una barra horizontal.</summary>
    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var compacto = Width < 1100;
        Marco.ColumnDefinitions[0].Width = new GridLength(compacto ? 96 : Width < 1400 ? 224 : 250);
        Navegacion.Compact = compacto;
        MenuPanel.ContentPadding = compacto ? new Thickness(8, 18) : new Thickness(14, 18);
    }
}
