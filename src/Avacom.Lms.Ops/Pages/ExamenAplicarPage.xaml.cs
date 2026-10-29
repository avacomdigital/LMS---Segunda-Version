using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Aplicar un examen a un grupo (MOD-010 · Guion, pasos 1 a 4). El profesor decide, con toques y sin teclado: el NIVEL (Abierto, Supervisado o Controlado; nunca
/// viene elegido, el botón «Aplicar examen» sigue apagado hasta que toca uno), el tiempo, la fecha límite y qué pasa si algo llega tarde, cuántos intentos,
/// cuándo ven su resultado los alumnos y quién reactiva a quien se quede sin señal.
///
/// Al elegir un nivel se dice con sinceridad cuántas tabletas no lo alcanzan (MSG-036) y cuáles; no se bloquea nada: el profesor decide si aplica igual y qué hacer
/// con ellas después, desde el panel. Cada nivel muestra la condición que el alumno leerá antes de empezar, con las mismas palabras del nodo.
///
/// Llega con la ruta <c>examen-aplicar</c> y su consulta: <c>curso</c> (curso_ref), <c>objeto</c> (objeto_ref), <c>fuente</c>, <c>sesion</c> (la clase de la que nace,
/// opcional), <c>grupo</c> (opcional: si falta y la profesora tiene varios, lo elige aquí), <c>titulo</c> y <c>curso_titulo</c> para mostrar.
/// </summary>
[QueryProperty(nameof(Curso), "curso")]
[QueryProperty(nameof(Objeto), "objeto")]
[QueryProperty(nameof(Fuente), "fuente")]
[QueryProperty(nameof(SesionClase), "sesion")]
[QueryProperty(nameof(Grupo), "grupo")]
[QueryProperty(nameof(Titulo), "titulo")]
[QueryProperty(nameof(CursoTitulo), "curso_titulo")]
public partial class ExamenAplicarPage : ContentPage
{
    // Opciones de cada pregunta. Los valores son los que entiende el nodo (backend.md §4.1).
    private static readonly (string Clave, string Rotulo)[] OpcionesDeTiempo =
        [("biblioteca", "La del examen"), ("sin_limite", "Sin límite"), ("30", "30 min"), ("45", "45 min"), ("60", "60 min"), ("90", "90 min")];
    private static readonly (int? Minutos, string Rotulo)[] OpcionesDeFecha = [(null, "Sin fecha"), (30, "En 30 min"), (60, "En 1 h"), (120, "En 2 h")];
    private static readonly (int? Intentos, string Rotulo)[] OpcionesDeIntentos = [(1, "1"), (2, "2"), (3, "3"), (null, "Sin límite")];
    // RF-004: las cinco políticas de publicación. «Los publico yo» (manual) es el valor predeterminado seguro; «En una fecha» pide además cuándo.
    private static readonly string[] OpcionesDeResultados =
        [PoliticasDeResultados.TrasLiberar, PoliticasDeResultados.AlEntregar, PoliticasDeResultados.AlFinalizarGrupo, PoliticasDeResultados.Programada, PoliticasDeResultados.Nunca];
    private static readonly (int Minutos, string Rotulo)[] OpcionesDePublicacion = [(60, "En 1 h"), (180, "En 3 h"), (24 * 60, "Mañana a esta hora"), (7 * 24 * 60, "En una semana")];
    // RF-002/RF-003: cuántas preguntas por alumno. Las fichas se recortan al tamaño del banco que la biblioteca informa en la ficha del examen.
    private static readonly int[] OpcionesDePreguntas = [5, 10, 15, 20, 25, 30, 40, 50];

    public string Curso { get; set; } = string.Empty;
    public string Objeto { get; set; } = string.Empty;
    public string Fuente { get; set; } = string.Empty;
    public string SesionClase { get; set; } = string.Empty;
    public string Grupo { get; set; } = string.Empty;
    public string Titulo { get; set; } = string.Empty;
    public string CursoTitulo { get; set; } = string.Empty;

    // Lo que el profesor decide. El nivel empieza SIN elegir (Guion, paso 1 · DEC-009).
    private string? _nivel;
    private string _tiempo = "biblioteca";
    private int? _limiteMin;                       // nulo: sin fecha límite
    private string _plazo = "blando";
    private int? _intentos = 1;                    // nulo: sin límite
    private string _resultados = PoliticasDeResultados.TrasLiberar;
    private int _publicarEnMin = 60;               // con «En una fecha»: minutos desde que se aplica (reloj del nodo)
    private int? _preguntas;                       // nulo: las que diga el examen
    private string _reactivacion = "profesor";

    // Lo que se conoce del aula.
    private FichaDeExamen? _ficha;                 // RF-003: el banco de preguntas, leído de la biblioteca antes de asignar
    private GruposDocente? _grupos;
    private GrupoDocente? _grupo;
    private string? _gruposError;
    private IReadOnlyList<DispositivoAula>? _inventario;
    private SesionDeClase? _clase;
    private bool _cargado, _leyendo, _aplicando;

    private Button? _aplicarBtn;
    private View? _bloqueElegibilidad;
    private bool _revelarElegibilidad;
    private static string Actor => Sesion.ProfesorId;

    public ExamenAplicarPage()
    {
        InitializeComponent();
        CancelarSlot.Content = ExamenUi.Accion("Cancelar", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 150, "examen-aplicar-cancelar", 56, margen: false).Vista;
        _aplicarBtn = Ds.Boton("Aplicar examen", Ds.Rango.Primary, async (_, _) => await AplicarAsync(), 64, 250);
        _aplicarBtn.AutomationId = "examen-aplicar";
        AplicarSlot.Content = Ds.Capsula(_aplicarBtn);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        TituloLabel.Text = string.IsNullOrWhiteSpace(Titulo) ? "Examen" : Titulo;
        SubtituloLabel.Text = CursoTitulo;
        SubtituloLabel.IsVisible = !string.IsNullOrWhiteSpace(CursoTitulo);
        if (_cargado) return;
        _cargado = true;
        try { await LeerAulaAsync(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenAplicarPage.OnAppearing", ex); }
    }

    // ------------------------------------------------------------------------------------ lo que se lee del aula

    /// <summary>Los grupos de la profesora, el inventario de tabletas (con su capacidad declarada) y la clase, todo de una vez. Nada de esto bloquea el aplicar.</summary>
    private async Task LeerAulaAsync()
    {
        _leyendo = true;
        Pintar();
        var estudio = Sesion.Estudio;
        var tGrupos = estudio.GruposAsync(Actor);
        var tTabletas = Sesion.Dispositivos.ListarAsync();
        var tClase = string.IsNullOrWhiteSpace(SesionClase) ? Task.FromResult<SesionDeClase?>(null) : Sesion.Aula.SesionAsync(SesionClase);
        // RF-003: «carga banco de preguntas»: la ficha dice cuántas preguntas hay y qué sugiere el examen, antes de asignar. Si no llega, se aplica igual con lo que diga el examen.
        var tFicha = Sesion.Evaluacion.FichaAsync(Actor, string.IsNullOrWhiteSpace(Fuente) ? Sesion.FuenteAula : Fuente, Curso, Objeto);
        try { await Task.WhenAll(tGrupos, tTabletas, tClase, tFicha); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenAplicarPage.LeerAula", ex); }

        _grupos = tGrupos.IsCompletedSuccessfully ? tGrupos.Result : null;
        _gruposError = _grupos is null ? ExamenTexto.Error(estudio.UltimoError, estudio.UltimoMotivo) : null;
        _inventario = tTabletas.IsCompletedSuccessfully ? tTabletas.Result : null;
        _clase = tClase.IsCompletedSuccessfully ? tClase.Result : null;
        _ficha = tFicha.IsCompletedSuccessfully ? tFicha.Result : null;
        if (_ficha is { ServidorEn: > 0 }) RelojNodo.Aprender(_ficha.ServidorEn);
        if (_ficha?.ResultadosPorDefecto is { Length: > 0 } institucional && _resultados == PoliticasDeResultados.TrasLiberar)
            _resultados = PoliticasDeResultados.Normalizar(institucional) == PoliticasDeResultados.Programada ? _resultados : PoliticasDeResultados.Normalizar(institucional);
        // El reloj del nodo, para que «En 30 min» sea 30 minutos del aula y no de este equipo.
        if (_clase is { ServidorEn: > 0 }) RelojNodo.Aprender(_clase.ServidorEn);

        if (_grupos is { Instalado: true })
        {
            _grupo = _grupos.Grupos.FirstOrDefault(g => g.Id == Grupo);
            if (_grupo is null && _grupos.Grupos.Count == 1) _grupo = _grupos.Grupos[0];   // un solo grupo: ya está elegido
        }
        _leyendo = false;
        Pintar();
    }

    // ------------------------------------------------------------------------------------------------ pintar

    /// <summary>Repinta el cuerpo y el pie sin perder el sitio del desplazamiento.</summary>
    private void Pintar()
    {
        var y = Desplazable.ScrollY;
        CuerpoHost.Clear();
        _bloqueElegibilidad = null;
        if (_leyendo)
        {
            CuerpoHost.Add(Ds.Secundario("Leyendo tus grupos y las tabletas del aula…", 16));
        }
        else
        {
            PintarGrupo();
            PintarNivel();
            PintarPreguntas();
            PintarTiempo();
            PintarFecha();
            PintarIntentos();
            PintarResultados();
            PintarReactivacion();
        }
        PintarPie();
        // Al elegir un nivel, MSG-036 (qué tabletas no lo alcanzan) tiene que verse sin que el profesor tenga que buscarlo: se baja hasta él.
        if (_revelarElegibilidad && _bloqueElegibilidad is { } bloque)
        {
            _revelarElegibilidad = false;
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(80), async () =>
            {
                try { await Desplazable.ScrollToAsync(bloque, ScrollToPosition.End, true); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
        }
        else if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    private static View Seccion(string titulo, string? explicacion, params View[] contenido)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(Ds.Titulo(titulo, 19));
        if (!string.IsNullOrWhiteSpace(explicacion)) pila.Add(Ds.Secundario(explicacion, 14));
        foreach (var vista in contenido) pila.Add(vista);
        return pila;
    }

    /// <summary>Una ficha de elección de 56 px (el mínimo para un toque sin precisión). La fila se parte sola cuando no caben.</summary>
    private static Button Ficha(string rotulo, bool activa, Func<Task> alTocar, string id) => EstudioUi.Chip(rotulo, activa, alTocar, id, 56);

    // ---- el grupo
    private void PintarGrupo()
    {
        if (_grupos is null)
        {
            CuerpoHost.Add(ExamenUi.Aviso("No se pudieron leer tus grupos", _gruposError, Tono.Ambar));
            var reintentar = ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, async () => { _cargado = true; await LeerAulaAsync(); }, 170, "examen-aplicar-reintentar");
            CuerpoHost.Add(reintentar.Vista);
            return;
        }
        if (!_grupos.Instalado)
        {
            CuerpoHost.Add(ExamenUi.Aviso("El aula todavía no está configurada",
                "Aún no hay grupos ni alumnos. Pide a la administración que configure el aula y vuelve aquí.", Tono.Ambar));
            return;
        }
        if (_grupos.Grupos.Count == 0)
        {
            CuerpoHost.Add(ExamenUi.Aviso("No tienes grupos a tu cargo", "Los grupos los define la administración. Cuando tengas uno, podrás aplicarle el examen.", Tono.Ambar));
            return;
        }
        // Si la clase ya trajo el grupo o sólo hay uno, no hay nada que elegir: la línea de resumen del pie lo dice.
        if (_grupos.Grupos.Count == 1 || _grupos.Grupos.Any(g => g.Id == Grupo)) return;
        var fichas = EstudioUi.Envolver();
        foreach (var g in _grupos.Grupos)
        {
            var grupo = g;
            fichas.Add(Ficha($"{grupo.Nombre ?? grupo.Codigo ?? grupo.Id} · {grupo.Alumnos.Count}", _grupo?.Id == grupo.Id,
                () => { _grupo = grupo; Pintar(); return Task.CompletedTask; }, $"examen-grupo-{grupo.Id}"));
        }
        CuerpoHost.Add(Seccion("¿A qué grupo?", "Elige el grupo que va a presentar el examen.", fichas));
    }

    // ---- el nivel (paso 1) y la elegibilidad (paso 4)
    private void PintarNivel()
    {
        var tarjetas = new VerticalStackLayout { Spacing = 10 };
        foreach (var nivel in Niveles.Todos)   // Abierto · Supervisado · Controlado, sin ninguno elegido de antemano
        {
            var n = nivel;
            var condicion = ExamenTexto.Condiciones(n);
            var elegido = _nivel == n;
            var pila = new VerticalStackLayout { Spacing = 2 };
            var cabeza = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            cabeza.Add(new Label { Text = Niveles.Rotulo(n), FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center }, 0, 0);
            if (elegido) cabeza.Add(ExamenUi.Pildora("✓  Elegido", Tono.Exito, 13), 1, 0);
            pila.Add(cabeza);
            pila.Add(new Label { Text = condicion.TextoAlumno, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap });
            pila.Add(Ds.Secundario($"Tú verás: {condicion.QueVes}", 13));
            var tarjeta = EstudioUi.TarjetaElegible(pila, elegido, () => ElegirNivelAsync(n),
                $"Nivel {Niveles.Rotulo(n)}. {condicion.TextoAlumno}", $"examen-nivel-{n}");
            tarjeta.Padding = new Thickness(18, 10);
            tarjetas.Add(tarjeta);
        }
        var contenido = new List<View> { tarjetas };
        if (_nivel is not null && Elegibilidad() is { } calculo)
        {
            _bloqueElegibilidad = BloqueDeElegibilidad(calculo);
            contenido.Add(_bloqueElegibilidad);
        }
        CuerpoHost.Add(Seccion("¿Qué nivel de control tendrá?", null, contenido.ToArray()));
    }

    private Task ElegirNivelAsync(string nivel)
    {
        _nivel = nivel;
        _revelarElegibilidad = true;
        Pintar();
        return Task.CompletedTask;
    }

    /// <summary>La cuenta de tabletas para el nivel elegido, o nulo si todavía no hay nivel ni grupo.</summary>
    private CalculoDeElegibilidad? Elegibilidad() =>
        _nivel is null || _grupo is null ? null : CalculoDeElegibilidad.Calcular(_grupo, _nivel, _inventario, _clase);

    /// <summary>MSG-036 con sinceridad: cuántas tabletas no alcanzan el nivel y cuáles. Nunca bloquea; se puede aplicar igual.</summary>
    private static View BloqueDeElegibilidad(CalculoDeElegibilidad calculo)
    {
        if (calculo.Nivel == Niveles.Abierto)
            return ExamenUi.Aviso("Cualquier tableta sirve para un examen abierto", null, Tono.Neutro);
        if (!calculo.InventarioConocido)
            return ExamenUi.Aviso("No se pudo comprobar las tabletas",
                "El inventario de tabletas no respondió. Puedes aplicar el examen igual: lo que no alcance el nivel esperará tu decisión en el panel.", Tono.Neutro);
        if (calculo.NoAlcanzan == 0)
        {
            var conocidas = calculo.Alcanzan;
            if (conocidas == 0)
                return ExamenUi.Aviso("Todavía no sabemos qué tableta usará cada alumno",
                    "Se comprobará cuando abran el examen. Lo que no alcance el nivel esperará tu decisión en el panel.", Tono.Neutro);
            var cuerpo = calculo.SinTableta > 0
                ? $"{ExamenTexto.Plural(calculo.SinTableta, "alumno todavía no tiene una tableta conocida", "alumnos todavía no tienen una tableta conocida")}: se comprobará cuando abran el examen."
                : null;
            return ExamenUi.Aviso($"{ExamenTexto.Plural(conocidas, "tableta alcanza", "tabletas alcanzan")} este nivel", cuerpo, Tono.Exito);
        }

        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = calculo.Mensaje, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.WordWrap });
        foreach (var fila in calculo.LasQueNoAlcanzan)
            pila.Add(new Label
            {
                Text = $"{fila.Rotulo} · {fila.Tableta} · {(fila.Capacidad is null ? "no declaró su capacidad" : "declara " + fila.Capacidad.ToLowerInvariant())}",
                FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = ExamenUi.TintaAmbar, LineBreakMode = LineBreakMode.TailTruncation,
            });
        if (calculo.SinTableta > 0)
            pila.Add(Ds.Secundario($"{ExamenTexto.Plural(calculo.SinTableta, "alumno más no tiene", "alumnos más no tienen")} una tableta conocida todavía.", 13));
        return ExamenUi.Zona(pila, Ds.AlertaSuave);
    }

    // ---- tiempo
    private void PintarTiempo()
    {
        var fichas = EstudioUi.Envolver();
        foreach (var (clave, rotulo) in OpcionesDeTiempo)
        {
            var c = clave;
            fichas.Add(Ficha(rotulo, _tiempo == c, () => { _tiempo = c; Pintar(); return Task.CompletedTask; }, $"examen-tiempo-{c}"));
        }
        CuerpoHost.Add(Seccion("Tiempo", _tiempo == "biblioteca" ? "Se usa el tiempo que trae el examen." : null, fichas));
    }

    // ---- fecha límite y plazo
    private void PintarFecha()
    {
        var fichas = EstudioUi.Envolver();
        foreach (var (minutos, rotulo) in OpcionesDeFecha)
        {
            var m = minutos;
            fichas.Add(Ficha(rotulo, _limiteMin == m, () =>
            {
                _limiteMin = m;
                if (m is null) _plazo = "blando";   // el plazo endurecido necesita una fecha
                Pintar();
                return Task.CompletedTask;
            }, $"examen-fecha-{(m?.ToString() ?? "sin")}"));
        }
        var contenido = new List<View> { fichas };
        if (_limiteMin is { } min)
        {
            contenido.Add(new Label
            {
                Text = $"Cierra hacia las {ExamenTexto.Hora(RelojNodo.AhoraMs + min * 60_000L)}", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta,
            });
            contenido.Add(Ds.Secundario("¿Qué pasa cuando llegue esa hora?", 15));
            var plazo = EstudioUi.Envolver();
            plazo.Add(Ficha("Blando", _plazo == "blando", () => { _plazo = "blando"; Pintar(); return Task.CompletedTask; }, "examen-plazo-blando"));
            plazo.Add(Ficha("Endurecido", _plazo == "endurecido", () => { _plazo = "endurecido"; Pintar(); return Task.CompletedTask; }, "examen-plazo-endurecido"));
            contenido.Add(plazo);
            contenido.Add(Ds.Secundario(_plazo == "endurecido"
                ? "Cierra al vencer y entrega lo respondido. Lo que llegue más tarde, hecho a tiempo, espera tu decisión."
                : "Se sigue recibiendo y se marca fuera de plazo.", 14));
        }
        else contenido.Add(Ds.Secundario("El examen queda abierto hasta que tú lo cierres.", 14));
        CuerpoHost.Add(Seccion("Fecha límite", null, contenido.ToArray()));
    }

    // ---- intentos
    private void PintarIntentos()
    {
        var fichas = EstudioUi.Envolver();
        foreach (var (intentos, rotulo) in OpcionesDeIntentos)
        {
            var i = intentos;
            fichas.Add(Ficha(rotulo, _intentos == i, () => { _intentos = i; Pintar(); return Task.CompletedTask; }, $"examen-intentos-{(i?.ToString() ?? "sin")}"));
        }
        CuerpoHost.Add(Seccion("Intentos", null, fichas));
    }

    // ---- preguntas (RF-002, RF-003)
    private void PintarPreguntas()
    {
        var fichas = EstudioUi.Envolver();
        if (_ficha is null)
        {
            CuerpoHost.Add(Seccion("¿Cuántas preguntas por alumno?", "No se pudo leer el banco de preguntas de la biblioteca ahora: se aplicará con las que diga el examen.", fichas));
            return;
        }
        var total = _ficha.TotalBanco;
        var delExamen = _ficha.Estrategia == "random_balanced" && _ficha.PreguntasSugeridas < total
            ? $"Las del examen ({_ficha.PreguntasSugeridas} de {total}, al azar)"
            : $"Todas ({total})";
        fichas.Add(Ficha(delExamen, _preguntas is null, () => { _preguntas = null; Pintar(); return Task.CompletedTask; }, "examen-preguntas-examen"));
        foreach (var n in OpcionesDePreguntas.Where(n => n < total))
        {
            var cantidad = n;
            fichas.Add(Ficha(cantidad.ToString(System.Globalization.CultureInfo.InvariantCulture), _preguntas == cantidad,
                () => { _preguntas = cantidad; Pintar(); return Task.CompletedTask; }, $"examen-preguntas-{cantidad}"));
        }
        var temas = _ficha.Temas is { Count: > 1 } t ? $" en {ExamenTexto.Plural(t.Count, "tema", "temas")}" : string.Empty;
        var explicacion = _preguntas is { } elegidas
            ? $"Cada alumno recibe {elegidas} de las {total} preguntas del banco{temas}, elegidas al azar para él y sin repetir. La selección se hace una sola vez y queda congelada para su intento."
            : $"El banco tiene {ExamenTexto.Plural(total, "pregunta", "preguntas")}{temas}. {(delExamen.StartsWith("Todas", StringComparison.Ordinal) ? "Cada alumno las recibe todas." : "Cada alumno recibe una selección al azar, distinta y sin repetir.")}";
        CuerpoHost.Add(Seccion("¿Cuántas preguntas por alumno?", explicacion, fichas));
    }

    // ---- resultados (RF-004: calificar y publicar son dos cosas distintas; aquí el profesor decide cuándo verán los alumnos su nota)
    private void PintarResultados()
    {
        var fichas = EstudioUi.Envolver();
        foreach (var politica in OpcionesDeResultados)
        {
            var c = politica;
            fichas.Add(Ficha(ExamenTexto.PoliticaCorta(c), _resultados == c, () => { _resultados = c; Pintar(); return Task.CompletedTask; }, $"examen-resultados-{c}"));
        }
        var contenido = new List<View> { fichas };
        if (_resultados == PoliticasDeResultados.Programada)
        {
            contenido.Add(Ds.Secundario("¿Cuándo?", 15));
            var cuando = EstudioUi.Envolver();
            foreach (var (minutos, rotulo) in OpcionesDePublicacion)
            {
                var m = minutos;
                cuando.Add(Ficha(rotulo, _publicarEnMin == m, () => { _publicarEnMin = m; Pintar(); return Task.CompletedTask; }, $"examen-publicar-{m}"));
            }
            contenido.Add(cuando);
            contenido.Add(new Label
            {
                Text = $"Se publican solos hacia las {ExamenTexto.Hora(RelojNodo.AhoraMs + _publicarEnMin * 60_000L)}, con el reloj del aula.",
                FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta,
            });
        }
        var sugerido = _ficha?.ResultadosSugeridos is { Length: > 0 } s && PoliticasDeResultados.Normalizar(s) != _resultados
            ? $" El examen sugiere «{ExamenTexto.PoliticaCorta(s).ToLowerInvariant()}»; la decisión es tuya."
            : string.Empty;
        CuerpoHost.Add(Seccion("¿Cuándo ven su resultado?", _resultados switch
        {
            PoliticasDeResultados.AlEntregar => "Cada alumno ve su resultado apenas entrega y queda calificado del todo (lo que revises tú se ve cuando lo publiques)." + sugerido,
            PoliticasDeResultados.Nunca => "Los alumnos no verán su resultado desde la tableta." + sugerido,
            PoliticasDeResultados.AlFinalizarGrupo => "Se publican solos cuando todos hayan terminado y nada quede por revisar. Puedes adelantarlos tú o publicar a un alumno." + sugerido,
            PoliticasDeResultados.Programada => "Se publican solos a la hora fijada. Antes nadie ve su nota; puedes adelantarlos tú." + sugerido,
            _ => "Los alumnos verán su resultado cuando tú los publiques, a todos o uno por uno. Tú ves las notas antes." + sugerido,
        }, contenido.ToArray()));
    }

    // ---- reactivación
    private void PintarReactivacion()
    {
        var fichas = EstudioUi.Envolver();
        fichas.Add(Ficha("La hago yo", _reactivacion == "profesor", () => { _reactivacion = "profesor"; Pintar(); return Task.CompletedTask; }, "examen-reactivacion-profesor"));
        fichas.Add(Ficha("Automática", _reactivacion == "automatica", () => { _reactivacion = "automatica"; Pintar(); return Task.CompletedTask; }, "examen-reactivacion-automatica"));
        CuerpoHost.Add(Seccion("Si un alumno se queda sin señal", _reactivacion == "automatica"
            ? "Al volver la señal, su examen continúa solo desde donde iba."
            : "Su examen queda en pausa, con el tiempo detenido, hasta que tú lo reactives.", fichas));
    }

    // ---------------------------------------------------------------------------------------------- el pie

    private void PintarPie()
    {
        var nombreGrupo = _grupo is null ? null : _grupo.Nombre ?? _grupo.Codigo ?? _grupo.Id;
        string resumen;
        if (_grupo is null) resumen = _leyendo ? "Un momento…" : "Elige el grupo para poder aplicar el examen.";
        else
        {
            resumen = $"Se aplicará a {nombreGrupo} ({ExamenTexto.Plural(_grupo.Alumnos.Count, "alumno", "alumnos")})";
            resumen += _nivel is null ? ". Elige el nivel para poder aplicarlo." : $" · nivel {Niveles.Rotulo(_nivel)}.";
        }
        ResumenLabel.Text = resumen;
        if (_aplicarBtn is not null)
        {
            _aplicarBtn.Text = _aplicando ? "Aplicando…" : "Aplicar examen";
            Ds.Habilitar(_aplicarBtn, _nivel is not null && _grupo is { Alumnos.Count: > 0 } && !_aplicando && !_leyendo);
        }
    }

    private void Avisar(string titulo, string? detalle, Tono tono)
    {
        AvisoHost.Clear();
        AvisoHost.Add(ExamenUi.Aviso(titulo, detalle, tono));
    }

    // -------------------------------------------------------------------------------------------- aplicar

    private TiempoDeExamen TiempoElegido() => _tiempo switch
    {
        "sin_limite" => TiempoDeExamen.SinLimite,
        "biblioteca" => TiempoDeExamen.DeLaBiblioteca,
        var minutos => TiempoDeExamen.Fijo(int.Parse(minutos, System.Globalization.CultureInfo.InvariantCulture) * 60),
    };

    private async Task AplicarAsync()
    {
        if (_aplicando || _nivel is null || _grupo is null) return;
        _aplicando = true;
        AvisoHost.Clear();
        PintarPie();
        try
        {
            // La fecha límite se calcula ahora, con el reloj del nodo, no al tocar la ficha: «En 30 min» son 30 minutos desde que se aplica.
            long? limite = _limiteMin is { } min ? RelojNodo.AhoraMs + min * 60_000L : null;
            long? publicarEn = _resultados == PoliticasDeResultados.Programada ? RelojNodo.AhoraMs + _publicarEnMin * 60_000L : null;
            var nuevo = new NuevoExamen(
                Fuente: string.IsNullOrWhiteSpace(Fuente) ? Sesion.FuenteAula : Fuente,
                CursoRef: Curso, ObjetoRef: Objeto, NivelExamen: _nivel, GrupoId: _grupo.Id,
                SesionId: string.IsNullOrWhiteSpace(SesionClase) ? null : SesionClase,
                Tiempo: TiempoElegido(), IntentosPermitidos: _intentos, LimiteEn: limite,
                Plazo: limite is null ? "blando" : _plazo, Reactivacion: _reactivacion, Resultados: _resultados, Iniciar: true,
                Preguntas: _preguntas, PublicarEn: publicarEn);
            var api = Sesion.Evaluacion;
            var creada = await api.CrearAsync(Actor, Sesion.ProfesorRotulo, nuevo);
            if (creada is null)
            {
                Avisar("No se pudo aplicar el examen", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
                return;
            }
            _aplicando = false;
            // Se reemplaza esta pantalla por el panel: «Atrás» desde el panel vuelve a la clase, no a la hoja de aplicar.
            await Shell.Current.GoToAsync($"../examen-panel?asignacion={Uri.EscapeDataString(creada.Id)}");
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", "ExamenAplicarPage.Aplicar", ex);
            Avisar("No se pudo aplicar el examen", "Algo no salió como se esperaba. Vuelve a intentarlo.", Tono.Ambar);
        }
        finally
        {
            _aplicando = false;
            PintarPie();
        }
    }
}
