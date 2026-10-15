using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// La configuración académica (MOD-011 · FUN-124, FUN-125), sólo para la administración. Muestra los cinco niveles educativos con su modo (por defecto, SIMPLE: sin notas) y su escala; por
/// nivel se alterna entre «Simple» y «Calificaciones», se elige la escala entre las adoptadas o se adopta una plantilla (orientativa: la advertencia se muestra SIEMPRE), se ve la vista previa de
/// cómo convierte la escala (0, 40, 60, 80 y 100 → nota presentada, nivel de desempeño y criterio de aprobación), se VALIDA el cambio (bloqueos y advertencias) y sólo entonces se aplica. Si el nodo
/// dice que hay evaluaciones en curso, se cuenta con palabras. También se elige la política de intentos (último, mejor, primero o promedio). Todo con toques: aquí no hay ni un campo de texto.
///
/// El nodo decide todo: esta pantalla no convierte ninguna nota (la vista previa la calcula el nodo) ni decide si un cambio se puede hacer (lo dice la validación).
/// </summary>
public partial class CalificacionesConfigPage : ContentPage
{
    private const double AnchoMaximo = 1280;

    private readonly AvisoTemporal _aviso;
    private bool _visible, _cargando, _aplicandoPolitica;
    private string? _politicaPropuesta;
    private ConfiguracionAcademica? _config;
    private long _ultimaLectura;

    private static IGradebookApi Api => Sesion.Gradebook;

    public CalificacionesConfigPage()
    {
        InitializeComponent();
        _aviso = new AvisoTemporal(ResultadoHost);
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Actualizar", CargarAsync), 170, "config-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 150, "config-volver").Vista);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!CalificacionesUi.PuedeLeer)
            {
                // TST-069: el rol técnico no accede a datos académicos; se dice sin llamar al nodo.
                SubtituloLabel.Text = string.Empty;
                PoliticaHost.Clear();
                PoliticaHost.Add(CalificacionesUi.SinAcceso("Este rol no accede a datos académicos", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (!CalificacionesUi.PuedeConfigurar)
            {
                SubtituloLabel.Text = string.Empty;
                PoliticaHost.Clear();
                PoliticaHost.Add(CalificacionesUi.SinAcceso("La configuración académica es de la administración",
                    "Sólo la administración elige el modo y la escala de cada nivel. El profesorado y los reportes ven las calificaciones en el libro."));
                return;
            }
            if (_config is null)
            {
                PoliticaHost.Clear();
                PoliticaHost.Add(CalificacionesUi.Estado("Leyendo la configuración…", "Un momento."));
            }
            await CargarAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "CalificacionesConfigPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    // ---------------------------------------------------------------------------------------------- leer

    private async Task CargarAsync()
    {
        if (_cargando || !_visible || !CalificacionesUi.PuedeConfigurar) return;
        _cargando = true;
        try
        {
            var api = Api;
            var configuracion = await api.ConfiguracionAsync(CalificacionesUi.Actor);
            if (!_visible) return;
            if (configuracion is null)
            {
                if (_config is not null)
                {
                    // Un tropiezo no borra lo que ya se ve.
                    ConexionHost.Clear();
                    ConexionHost.Add(CalificacionesUi.SinConexion(api)
                        ? ExamenUi.Aviso("Sin conexión con el nodo", $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}.", Tono.Ambar)
                        : ExamenUi.Aviso("No se pudo actualizar la configuración", CalificacionesUi.Error(api), Tono.Ambar));
                    return;
                }
                PoliticaHost.Clear();
                NivelesHost.Clear();
                EscalasHost.Clear();
                PoliticaHost.Add(CalificacionesUi.Estado("No se pudo leer la configuración", CalificacionesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Reintentar", CargarAsync), 170, "config-reintentar", margen: false).Vista));
                return;
            }
            ConexionHost.Clear();
            _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            _config = configuracion;
            Pintar();
        }
        finally { _cargando = false; }
        await CargarPlantillasAsync();
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Pintar()
    {
        if (_config is not { } c) return;
        var y = Desplazable.ScrollY;
        SistemaHost.Clear();
        SistemaHost.Add(SistemaPorPais(c));
        PoliticaHost.Clear();
        PoliticaHost.Add(Politica(c.Politica));
        NivelesHost.Clear();
        NivelesHost.Add(Niveles(c));
        EscalasHost.Clear();
        EscalasHost.Add(Escalas(c));
        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    /// <summary>
    /// La política de intentos: qué intento cuenta cuando un estudiante presenta una evaluación más de una vez. La administración la elige con cuatro fichas y la aplica con un botón (dos
    /// toques: cambia lo que cuenta para todos). Cambiarla recalcula lo derivado del libro y no modifica ninguna calificación ya registrada.
    /// </summary>
    private View Politica(PoliticaInstitucional p)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Política de intentos"));
        var fila = ExamenUi.Fila();
        fila.Add(CalificacionesUi.PildoraEnFila(GradebookTexto.Politica(p.PoliticaIntentos), Matiz.Info, 14));
        if (p.PoliticaProvisional) fila.Add(CalificacionesUi.PildoraEnFila("Provisional", Matiz.Ambar, 14));
        pila.Add(fila);
        pila.Add(Ds.Secundario(p.PoliticaProvisional
            ? "La institución todavía no confirmó qué intento cuenta; mientras tanto se usa el último. Elige uno para dejarlo confirmado."
            : "Es el intento que cuenta para la calificación de una evaluación.", 14));
        pila.Add(Ds.Secundario(GradebookTexto.PoliticaExplicada(p.PoliticaIntentos), 14));

        // ---- elegir otra
        pila.Add(EstudioUi.Eyebrow("QUÉ INTENTO CUENTA"));
        var fichas = EstudioUi.Envolver();
        var elegida = _politicaPropuesta ?? p.PoliticaIntentos;
        foreach (var politica in GradebookTexto.PoliticasDeIntentos)
        {
            var clave = politica;
            fichas.Add(EstudioUi.Chip(GradebookTexto.Politica(clave), clave == elegida,
                CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Política", () => ProponerPoliticaAsync(p, clave)), $"config-politica-{clave}", 56));
        }
        pila.Add(fichas);
        if (_politicaPropuesta is { } propuesta && propuesta != p.PoliticaIntentos)
        {
            pila.Add(Ds.Secundario($"{GradebookTexto.Politica(propuesta)}: {GradebookTexto.PoliticaExplicada(propuesta).ToLowerInvariant().TrimEnd('.')}. Cambiarla recalcula el libro de todos los grupos; ninguna calificación ya registrada se modifica.", 14));
            var aplicar = ExamenUi.Accion(_aplicandoPolitica ? "Un momento…" : "Aplicar esta política", Ds.Rango.Primary,
                CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Aplicar política", () => AplicarPoliticaAsync(propuesta)), 280, "config-politica-aplicar", 56, margen: false);
            Ds.Habilitar(aplicar.Boton, !_aplicandoPolitica);
            aplicar.Vista.HorizontalOptions = LayoutOptions.Start;
            pila.Add(aplicar.Vista);
        }
        var datos = new List<string>();
        if (!string.IsNullOrWhiteSpace(p.Institucion)) datos.Add(p.Institucion!);
        if (!string.IsNullOrWhiteSpace(p.Pais)) datos.Add(FiltroDePlantillas.NombreDePais(p.Pais!.ToUpperInvariant()));
        if (!string.IsNullOrWhiteSpace(p.Jurisdiccion)) datos.Add(p.Jurisdiccion!);
        if (datos.Count > 0) pila.Add(Ds.Secundario(string.Join(" · ", datos), 14));
        pila.Add(Ds.Secundario("Las ponderaciones por evaluación se guardan para una versión posterior y no se aplican: el promedio simple del libro es informativo.", 13));
        return ExamenUi.Tarjeta(pila);
    }

    private Task ProponerPoliticaAsync(PoliticaInstitucional actual, string politica)
    {
        _politicaPropuesta = politica == actual.PoliticaIntentos ? null : politica;
        Pintar();
        return Task.CompletedTask;
    }

    private async Task AplicarPoliticaAsync(string politica)
    {
        if (_aplicandoPolitica) return;
        _aplicandoPolitica = true;
        Pintar();
        try
        {
            var api = Api;
            var r = await api.ConfigurarPoliticaAsync(CalificacionesUi.Actor, politica);
            if (r is null)
            {
                _aviso.Mostrar("No se cambió la política", CalificacionesUi.SinConexion(api) ? "Sin conexión con el nodo del aula: nada se guardó. Puedes volver a tocar «Aplicar»." : CalificacionesUi.Error(api), Tono.Ambar);
                return;
            }
            _politicaPropuesta = null;
            _aviso.Mostrar(r.Cambiado ? $"Política actualizada: {GradebookTexto.Politica(r.Politica.PoliticaIntentos).ToLowerInvariant()}" : "Sin cambios: la política ya era esa",
                "El libro se recalculó con ella. Ninguna calificación registrada cambió.", Tono.Exito);
        }
        finally
        {
            _aplicandoPolitica = false;
        }
        await CargarAsync();
    }

    private View Niveles(ConfiguracionAcademica c)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Niveles educativos"));
        pila.Add(Ds.Secundario("Un nivel sin configurar está en modo simple: sus estudiantes sólo ven si completaron cada evaluación, sin notas ni números. En modo calificaciones se presenta la nota con la escala elegida.", 14));
        // El orden de la escuela, aunque el nodo mande otro; los niveles que el nodo no conozca van al final.
        foreach (var nivel in c.Niveles.OrderBy(n => NivelesEducativos.Todos.ToList().IndexOf(n.NivelClave) is var i and >= 0 ? i : int.MaxValue))
            pila.Add(TarjetaDeNivel(nivel));
        return ExamenUi.Tarjeta(pila);
    }

    private View TarjetaDeNivel(NivelConfigurado nivel)
    {
        var enEdicion = _nivelEditando == nivel.NivelClave;
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = SelectorDeGrupo.RotuloDeNivel(nivel.NivelClave), FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta });
        var pastillas = ExamenUi.Fila();
        pastillas.Add(CalificacionesUi.PildoraEnFila($"Modo {GradebookTexto.Modo(nivel.Modo).ToLowerInvariant()}", nivel.EnModoCalificaciones ? Matiz.Info : Matiz.Neutro, 13));
        if (nivel.PorDefecto) pastillas.Add(CalificacionesUi.PildoraEnFila("Por defecto: nadie lo configuró", Matiz.Gris, 13));
        if (nivel.Escala is { } escala) pastillas.Add(CalificacionesUi.PildoraEnFila($"Escala: {escala.Nombre}", Matiz.Exito, 13));
        textos.Add(pastillas);
        textos.Add(Ds.Secundario(nivel.EnModoCalificaciones
            ? "Los estudiantes ven su nota presentada con esta escala cuando el profesor la publica."
            : "Los estudiantes ven sólo el estado de cada evaluación, sin notas.", 14));
        cabecera.Add(textos, 0, 0);
        var editar = ExamenUi.Accion(enEdicion ? "Cerrar" : "Cambiar", enEdicion ? Ds.Rango.Quiet : Ds.Rango.Secondary,
            CalificacionesUi.Seguro(nameof(CalificacionesConfigPage), "Cambiar", () => AlternarEdicionAsync(nivel)), 150, $"config-nivel-{nivel.NivelClave}", 56, margen: false);
        editar.Vista.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(editar.Vista, 1, 0);

        var contenido = new VerticalStackLayout { Spacing = 12 };
        contenido.Add(cabecera);
        if (enEdicion) contenido.Add(Editor(nivel));
        return CalificacionesUi.Fila(contenido, new Thickness(18, 14));
    }

    private View Escalas(ConfiguracionAcademica c)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Escalas adoptadas"));
        if (c.Escalas.Count == 0)
        {
            pila.Add(Ds.Secundario("La institución todavía no adoptó ninguna escala. Al cambiar un nivel a modo calificaciones podrás adoptar una plantilla orientativa y revisarla antes de usarla.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        pila.Add(Ds.Secundario("Una escala adoptada es de la institución. Cada versión que se publique queda guardada y no cambia; lo que ya se publicó con una versión sigue presentándose igual.", 14));
        foreach (var e in c.Escalas)
        {
            var textos = new VerticalStackLayout { Spacing = 2 };
            textos.Add(new Label { Text = e.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            var datos = new List<string> { TramosDeEscala.TipoLegible(e.Tipo) };
            if (!string.IsNullOrWhiteSpace(e.Pais)) datos.Add(FiltroDePlantillas.NombreDePais(e.Pais!.ToUpperInvariant()));
            if (!string.IsNullOrWhiteSpace(e.Jurisdiccion)) datos.Add(e.Jurisdiccion!);
            if (!e.Activa) datos.Add("desactivada");
            textos.Add(Ds.Secundario(string.Join(" · ", datos), 13));
            pila.Add(CalificacionesUi.Fila(textos, new Thickness(16, 10)));
        }
        return ExamenUi.Tarjeta(pila);
    }
}
