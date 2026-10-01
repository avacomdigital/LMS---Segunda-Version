using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Grupos (MOD-001 · padrón): crear grupos y registrar estudiantes con su grupo, para tener alumnos reales con los que probar el modo de
/// estudio (repaso). Un grupo es una tarjeta a la izquierda; al elegirlo, a la derecha salen sus estudiantes (con «Quitar») y el formulario
/// de registro. Un estudiante que ya existe y no tiene grupo se agrega con un toque.
///
/// Es la única pantalla de OPS, además del acceso, que pide escribir (nombres del estudiante y nombre del grupo): en el nodo principal
/// eso lo atiende el teclado táctil de Windows; lo demás es por toque. Con sesión rige lo de siempre (un docente sólo registra en SUS grupos y
/// sólo la administración crea grupos): el motivo del rechazo se dice en la propia pantalla. Sin sesión (prototipo) actúa la administración del aula.
/// </summary>
public partial class GruposPage : ContentPage
{
    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");
    private static readonly (string Clave, string Rotulo)[] Niveles =
        [("preescolar", "Preescolar"), ("primaria", "Primaria"), ("secundaria", "Secundaria"), ("bachillerato", "Bachillerato")];

    private EstadoPadron? _estado;
    private string? _grupoId;
    private bool _creandoGrupo;
    private string _nivelNuevo = string.Empty;
    private bool _ocupado;
    private (string Texto, bool Problema)? _aviso;
    private EstudianteRegistrado? _ultimo;

    // Los campos viven en la página: un repintado no debe borrar lo que el docente ya escribió.
    private readonly Entry _nombresEntry = Campo("Nombres", "Nombres del estudiante");
    private readonly Entry _apellidosEntry = Campo("Apellidos", "Apellidos del estudiante");
    private readonly Entry _documentoEntry = Campo("Documento (opcional)", "Documento o código del estudiante, opcional");
    private readonly Entry _grupoNombreEntry = Campo("Nombre del grupo", "Nombre del grupo, por ejemplo Sexto A");

    // Los formularios se construyen UNA vez y se reutilizan. WinUI no deja pasar un TextBox nativo a otro contenedor mientras el anterior sigue
    // vivo (COMException al reinsertar el mismo Entry en un layout nuevo): lo que cambia entre repintados son sólo los textos y los botones.
    private readonly Border _formGrupo;
    private readonly FlexLayout _nivelesHost = new() { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row };
    private readonly Border _formEstudiante;
    private readonly Label _tituloEstudiante = Ds.Titulo(string.Empty, 20);
    private GrupoPadron? _grupoActual;

    public GruposPage()
    {
        InitializeComponent();
        var actualizar = Ds.Boton("Actualizar", Ds.Rango.Secondary, async (_, _) => await CargarAsync(), 56);
        var volver = Ds.Boton("Menú principal", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 56);
        foreach (var b in new[] { actualizar, volver }) b.FontSize = 16;
        AccionesHost.Add(Ds.Capsula(actualizar));
        AccionesHost.Add(volver);
        _formGrupo = ConstruirFormularioGrupo();
        _formEstudiante = ConstruirFormularioEstudiante();
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await CargarAsync();
    }

    private static Entry Campo(string marcador, string descripcion)
    {
        var e = new Entry
        {
            Placeholder = marcador, FontSize = 18, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta, HeightRequest = 54,
            BackgroundColor = Ds.Lienzo, IsSpellCheckEnabled = false, IsTextPredictionEnabled = false, ReturnType = ReturnType.Next,
        };
        SemanticProperties.SetDescription(e, descripcion);
        return e;
    }

    private async Task CargarAsync()
    {
        if (_ocupado) return;
        _ocupado = true;
        try
        {
            var api = Sesion.Padron;
            _estado = await api.EstadoAsync();
            if (_estado is null)
            {
                _aviso = (api.UltimoError?.Detalle ?? "No se pudo leer el padrón del aula.", true);
                _estado = new EstadoPadron(true, null, [], []);
            }
            if (_grupoId is not null && _estado.Grupos.All(g => g.Id != _grupoId)) _grupoId = null;
            _grupoId ??= _estado.Grupos.FirstOrDefault()?.Id;
            Pintar();
        }
        finally { _ocupado = false; }
    }

    // ------------------------------------------------------------------ pintar

    private void Pintar()
    {
        try { PintarInterno(); }
        catch (Exception ex)
        {
            // Una pantalla en blanco no le sirve a nadie: se anota el motivo y se dice qué pasó.
            RegistroDeFallos.Escribir(AulaContenidoView.NombreApp, "grupos · pintar", ex);
            DetalleHost.Clear();
            DetalleHost.Add(Ds.Alerta_("No se pudo dibujar esta pantalla", "Toca Actualizar. Si sigue igual, el motivo quedó anotado en el archivo de fallos.", Ds.PeligroSuave, TintaPeligro));
        }
    }

    private void PintarInterno()
    {
        ListaHost.Clear();
        DetalleHost.Clear();
        var e = _estado!;

        if (!e.Instalado)
        {
            SubtituloLabel.Text = "Este equipo todavía no tiene organización: sin ella no hay grupos ni estudiantes.";
            PintarNoInstalado();
            return;
        }

        var estudiantes = e.Grupos.Sum(g => g.Estudiantes.Count);
        SubtituloLabel.Text = string.Join(" · ", new[]
        {
            e.Organizacion?.Nombre,
            e.Grupos.Count == 1 ? "1 grupo" : $"{e.Grupos.Count} grupos",
            estudiantes == 1 ? "1 estudiante" : $"{estudiantes} estudiantes",
            "Con ellos se prueba el modo de estudio (repaso).",
        }.Where(x => !string.IsNullOrWhiteSpace(x)));

        var nuevo = Ds.Boton(_creandoGrupo ? "Cancelar" : "+ Nuevo grupo", _creandoGrupo ? Ds.Rango.Quiet : Ds.Rango.Primary, (_, _) => { _creandoGrupo = !_creandoGrupo; _aviso = null; Pintar(); }, 56);
        nuevo.FontSize = 16;
        ListaHost.Add(Ds.Capsula(nuevo));
        if (_creandoGrupo) ListaHost.Add(FormularioGrupo());
        foreach (var g in e.Grupos.OrderBy(g => g.Nombre)) ListaHost.Add(TarjetaGrupo(g));
        if (e.Grupos.Count == 0 && !_creandoGrupo)
            ListaHost.Add(Ds.Tarjeta(Ds.Secundario("Todavía no hay grupos. Crea el primero (por ejemplo «Sexto A») y registra a sus estudiantes.", 16), Ds.RadioTarjeta, new Thickness(20), Colors.White));

        if (_aviso is { } aviso) DetalleHost.Add(Ds.Alerta_(aviso.Problema ? "No se pudo" : "Listo", aviso.Texto, aviso.Problema ? Ds.PeligroSuave : Ds.ExitoSuave, aviso.Problema ? TintaPeligro : Ds.Tinta));
        if (_ultimo is not null) DetalleHost.Add(TarjetaUltimo(_ultimo));
        var grupo = e.Grupos.FirstOrDefault(g => g.Id == _grupoId);
        if (grupo is null)
        {
            DetalleHost.Add(Ds.Tarjeta(Ds.Secundario("Elige un grupo para ver sus estudiantes y registrar uno nuevo.", 16), Ds.RadioTarjeta, new Thickness(24), Colors.White));
            return;
        }
        DetalleHost.Add(DetalleGrupo(grupo));
        DetalleHost.Add(FormularioEstudiante(grupo));
        if (e.SinGrupo.Count > 0) DetalleHost.Add(SinGrupo(grupo, e.SinGrupo));
    }

    private void PintarNoInstalado()
    {
        DetalleHost.Add(Ds.Alerta_("El nodo aún no está instalado",
            "En un aula real la instalación la hace el asistente del instalador. Para probar aquí puedes preparar un aula de prueba: crea la organización «Aula de prueba» y deja todo listo para registrar grupos y estudiantes.",
            Ds.AlertaSuave, Ds.Tinta));
        var preparar = Ds.Boton("Preparar aula de prueba", Ds.Rango.Primary, async (_, _) =>
        {
            var api = Sesion.Padron;
            _aviso = await api.PrepararAulaDePruebaAsync() ? ("Aula de prueba lista. Ya puedes crear un grupo.", false) : (api.UltimoError?.Detalle ?? "No se pudo preparar el aula de prueba.", true);
            await CargarAsync();
        }, 60);
        preparar.HorizontalOptions = LayoutOptions.Start;
        DetalleHost.Add(Ds.Capsula(preparar));
        if (_aviso is { Problema: true } a) DetalleHost.Add(Ds.Alerta_("No se pudo", a.Texto, Ds.PeligroSuave, TintaPeligro));
    }

    private View TarjetaGrupo(GrupoPadron g)
    {
        var elegido = g.Id == _grupoId;
        var texto = new VerticalStackLayout { Spacing = 2 };
        texto.Add(Ds.Titulo(g.Nombre, 20));
        texto.Add(Ds.Secundario($"{g.Codigo} · {g.Periodo}{(string.IsNullOrWhiteSpace(g.NivelClave) ? "" : " · " + g.NivelClave)}", 14));
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
        fila.Add(texto, 0, 0);
        var cuenta = Ds.Pildora(g.Estudiantes.Count == 1 ? "1 estudiante" : $"{g.Estudiantes.Count} estudiantes", elegido ? Ds.InfoSuave : Ds.Lienzo, Ds.Tinta, 14);
        cuenta.VerticalOptions = LayoutOptions.Center;
        fila.Add(cuenta, 1, 0);
        var tarjeta = Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(18, 14), elegido ? Ds.InfoSuave : Colors.White);
        if (elegido) tarjeta.Stroke = new SolidColorBrush(Ds.Info);
        SemanticProperties.SetDescription(tarjeta, $"Grupo {g.Nombre}, {g.Estudiantes.Count} estudiantes");
        Ds.Tocable(tarjeta, () => { _grupoId = g.Id; _aviso = null; _ultimo = null; Pintar(); return Task.CompletedTask; });
        return tarjeta;
    }

    private Border ConstruirFormularioGrupo()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Ds.Secundario("Nombre del grupo", 14));
        pila.Add(_grupoNombreEntry);
        pila.Add(Ds.Secundario("Nivel (opcional)", 14));
        pila.Add(_nivelesHost);
        var crear = Ds.Boton("Crear grupo", Ds.Rango.Primary, async (_, _) => await CrearGrupoAsync(), 56);
        crear.FontSize = 16;
        pila.Add(Ds.Capsula(crear));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(18), Colors.White);
    }

    private View FormularioGrupo()
    {
        _nivelesHost.Clear();
        foreach (var (clave, rotulo) in Niveles)
        {
            var k = clave;
            var b = Ds.Boton(rotulo, _nivelNuevo == clave ? Ds.Rango.Primary : Ds.Rango.Secondary, (_, _) => { _nivelNuevo = _nivelNuevo == k ? string.Empty : k; Pintar(); }, 46);
            b.FontSize = 15;
            var c = Ds.Capsula(b);
            c.Margin = new Thickness(0, 0, 8, 8);
            _nivelesHost.Add(c);
        }
        return _formGrupo;
    }

    private View DetalleGrupo(GrupoPadron g)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(Ds.Titulo(g.Nombre, 24));
        pila.Add(Ds.Secundario(g.Estudiantes.Count == 0 ? "Este grupo todavía no tiene estudiantes. Registra el primero aquí abajo." : $"Estudiantes del grupo ({g.Estudiantes.Count})", 15));
        foreach (var est in g.Estudiantes.OrderBy(x => x.Alias))
        {
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10, Padding = new Thickness(0, 4) };
            fila.Add(Ds.Cuerpo(est.Alias, 18), 0, 0);
            var id = est.Id;
            var quitar = Ds.Boton("Quitar del grupo", Ds.Rango.Quiet, async (_, _) => await RetirarAsync(g.Id, id, est.Alias), 46);
            quitar.FontSize = 14;
            fila.Add(quitar, 1, 0);
            pila.Add(fila);
            pila.Add(Ds.Separador());
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
    }

    private Border ConstruirFormularioEstudiante()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(_tituloEstudiante);
        pila.Add(Ds.Secundario("Sólo los nombres son obligatorios. Sin documento, el aula le emite una clave; el PIN lo genera el aula y se muestra una sola vez.", 14));
        pila.Add(_nombresEntry);
        pila.Add(_apellidosEntry);
        pila.Add(_documentoEntry);
        var registrar = Ds.Boton("Registrar estudiante", Ds.Rango.Primary, async (_, _) => { if (_grupoActual is { } g) await RegistrarAsync(g); }, 60);
        registrar.HorizontalOptions = LayoutOptions.Start;
        pila.Add(Ds.Capsula(registrar));
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
    }

    private View FormularioEstudiante(GrupoPadron g)
    {
        _grupoActual = g;
        _tituloEstudiante.Text = $"Registrar un estudiante en {g.Nombre}";
        return _formEstudiante;
    }

    private View SinGrupo(GrupoPadron destino, IReadOnlyList<EstudianteSinGrupo> lista)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(Ds.Titulo("Estudiantes sin grupo", 20));
        pila.Add(Ds.Secundario($"Se agregan a {destino.Nombre} con un toque.", 14));
        foreach (var s in lista.OrderBy(x => x.Alias))
        {
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10, Padding = new Thickness(0, 4) };
            fila.Add(Ds.Cuerpo(s.Alias, 18), 0, 0);
            var id = s.Id;
            var agregar = Ds.Boton($"Agregar a {destino.Nombre}", Ds.Rango.Secondary, async (_, _) => await MatricularAsync(destino, id, s.Alias), 46);
            agregar.FontSize = 14;
            fila.Add(Ds.Capsula(agregar), 1, 0);
            pila.Add(fila);
        }
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(22, 18), Colors.White);
    }

    private View TarjetaUltimo(EstudianteRegistrado e)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(Ds.Titulo($"{e.Alias} quedó registrado", 19));
        pila.Add(Ds.Cuerpo($"Clave de acceso: {e.Identificador}", 17));
        pila.Add(string.IsNullOrWhiteSpace(e.SecretoInicial)
            ? Ds.Secundario("PIN: el que elegiste.", 15)
            : Ds.Cuerpo($"PIN inicial: {e.SecretoInicial}  ·  anótalo ahora, no vuelve a mostrarse.", 17));
        pila.Add(Ds.Secundario("En el modo de estudio el estudiante sólo elige su nombre en la tableta: no necesita escribir la clave ni el PIN.", 14));
        return new Border
        {
            BackgroundColor = Ds.ExitoSuave, StrokeThickness = 0, Padding = new Thickness(20, 16),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila,
        };
    }

    // ---------------------------------------------------------------- acciones

    private async Task CrearGrupoAsync()
    {
        var nombre = (_grupoNombreEntry.Text ?? string.Empty).Trim();
        if (nombre.Length == 0) { _aviso = ("Escribe el nombre del grupo, por ejemplo «Sexto A».", true); Pintar(); return; }
        var api = Sesion.Padron;
        var g = await api.CrearGrupoAsync(nombre, _nivelNuevo);
        if (g is null) { _aviso = (Motivo(api, "No se pudo crear el grupo."), true); Pintar(); return; }
        _grupoNombreEntry.Text = string.Empty;
        _nivelNuevo = string.Empty;
        _creandoGrupo = false;
        _grupoId = g.Id;
        _ultimo = null;
        _aviso = ($"Grupo {g.Nombre} creado.", false);
        await CargarAsync();
    }

    private async Task RegistrarAsync(GrupoPadron g)
    {
        var nombres = (_nombresEntry.Text ?? string.Empty).Trim();
        if (nombres.Length == 0) { _aviso = ("Escribe los nombres del estudiante.", true); _ultimo = null; Pintar(); return; }
        var api = Sesion.Padron;
        var registrado = await api.RegistrarEstudianteAsync(nombres, _apellidosEntry.Text, _documentoEntry.Text, g.Id);
        if (registrado is null) { _aviso = (Motivo(api, "No se pudo registrar al estudiante."), true); _ultimo = null; Pintar(); return; }
        _nombresEntry.Text = _apellidosEntry.Text = _documentoEntry.Text = string.Empty;
        _aviso = null;
        _ultimo = registrado;
        await CargarAsync();
    }

    private async Task RetirarAsync(string grupoId, string usuarioId, string alias)
    {
        var api = Sesion.Padron;
        _ultimo = null;
        _aviso = await api.RetirarAsync(grupoId, usuarioId) ? ($"{alias} salió del grupo.", false) : (Motivo(api, "No se pudo quitar al estudiante."), true);
        await CargarAsync();
    }

    private async Task MatricularAsync(GrupoPadron destino, string usuarioId, string alias)
    {
        var api = Sesion.Padron;
        _ultimo = null;
        _aviso = await api.MatricularAsync(destino.Id, usuarioId) ? ($"{alias} entró a {destino.Nombre}.", false) : (Motivo(api, "No se pudo agregar al estudiante."), true);
        await CargarAsync();
    }

    /// <summary>El motivo en palabras de aula: lo que dice el nodo, más qué hacer; sin códigos.</summary>
    private static string Motivo(IPadronApi api, string porDefecto)
    {
        var error = api.UltimoError;
        if (error is null) return porDefecto;
        var detalle = error.Codigo switch
        {
            "sin_permiso" => "Con tu perfil no puedes hacer esto. Pídele a la administración que lo haga o que te dé el permiso.",
            "identificador_duplicado" => "Ese documento ya pertenece a otra persona del aula. Déjalo en blanco para que el aula emita una clave, o agrega a la persona que ya existe.",
            "no_instalado" => "El nodo aún no está instalado.",
            "conflicto" => "Ya existe un grupo con ese nombre en este periodo.",
            _ => error.Detalle,
        };
        return string.IsNullOrWhiteSpace(error.Sugerencia) || error.Codigo is "sin_permiso" or "identificador_duplicado" ? detalle : $"{detalle} {error.Sugerencia}";
    }
}
