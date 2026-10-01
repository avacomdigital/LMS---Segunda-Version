using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Vista 3 · asignar una lección, en tres pasos: para quién, qué lección, para cuándo y cómo. Todo se elige con un toque (el nodo principal
// no tiene teclado): grupos y alumnos en tarjetas y chips, la fecha entre opciones y la consigna entre frases.
public partial class EstudioPage
{
    private const int MinutosFinDelDia = 23 * 60 + 59;
    /// <summary>Cursos que se pintan a la vez (el catálogo llegará a ~25 000): el resto se alcanza buscando o con «Mostrar más».</summary>
    private const int LimiteInicialCursos = 12;
    private const int PasoDeMasCursos = 12;

    private static readonly (string Rotulo, int Dias)[] DiasPredefinidos =
        [("Hoy", 0), ("Mañana", 1), ("En 3 días", 3), ("En 1 semana", 7), ("En 2 semanas", 14)];

    private static readonly (string Rotulo, int Minutos)[] HorasPredefinidas =
        [("8:00 a. m.", 8 * 60), ("Mediodía", 12 * 60), ("3:00 p. m.", 15 * 60), ("6:00 p. m.", 18 * 60), ("Final del día", MinutosFinDelDia)];

    private static readonly string[] Consignas =
    [
        "Lee con calma y haz la práctica al final.",
        "Termina todas las actividades.",
        "Haz la práctica dos veces.",
        "Repasa esta lección antes de la evaluación.",
        "Anota tus dudas para la próxima clase.",
    ];

    private int _paso = 1;
    private bool _enviando;

    // paso 1 · para quién
    private GruposDocente? _grupos;
    private string? _gruposError;
    private GrupoDocente? _grupo;
    private bool _todoElGrupo = true;
    private readonly HashSet<string> _elegidos = new(StringComparer.Ordinal);

    // paso 2 · qué lección
    private CatalogoAula? _catalogo;
    private string? _catalogoError;
    private bool _catalogoCargando;
    private string? _asignatura;
    private IndiceDeCursos? _indice;
    private string _busqueda = string.Empty;
    private int _limiteCursos = LimiteInicialCursos;
    private int _versionBusqueda;
    private VerticalStackLayout? _resultados;
    private FichaCurso? _curso;
    private VistaCurso? _vistaCurso;
    private string? _cursoError;
    private bool _cursoCargando;
    private LeccionAula? _leccion;

    // paso 3 · cuándo y cómo
    private int? _dias = 7;                     // null: sin elegir · -1: sin fecha
    private int _minutos = MinutosFinDelDia;
    private string _plazo = "blando";
    private int _graciaMin = 15;
    private bool _descarga = true;
    private string? _consigna;

    private void ReiniciarBorrador()
    {
        _paso = 1;
        _enviando = false;
        _grupo = null;
        _todoElGrupo = true;
        _elegidos.Clear();
        _asignatura = null;
        LimpiarBusqueda();
        _curso = null;
        _vistaCurso = null;
        _cursoError = null;
        _cursoCargando = false;
        _leccion = null;
        _dias = 7;
        _minutos = MinutosFinDelDia;
        _plazo = "blando";
        _graciaMin = 15;
        _descarga = true;
        _consigna = null;
    }

    private async Task MostrarNuevaAsync()
    {
        Entrar(Vista.Nueva);
        ReiniciarBorrador();
        PonerCabecera("MODO DE ESTUDIO · NUEVA ASIGNACIÓN", "Asignar una lección",
            "Tres pasos: para quién es, qué lección y para cuándo. Todo se elige con un toque.",
            AccionMenu().Vista);
        Vaciar(true);
        PintarPaso();

        var api = Api;
        _grupos = await api.GruposAsync(Actor);
        if (_vista != Vista.Nueva) return;
        _gruposError = _grupos is null ? EstudioTexto.Error(api.UltimoError, api.UltimoMotivo) : null;
        if (_grupos is { Instalado: true, Grupos.Count: 1 }) _grupo = _grupos.Grupos[0];   // un solo grupo: ya está elegido
        PintarPaso();
    }

    // ---------------------------------------------------------------------------------- armazón

    private void PintarPaso()
    {
        if (_vista != Vista.Nueva) return;
        Repintar(() =>
        {
            Vaciar(false);
            ContenidoHost.Add(Pasos());
            switch (_paso)
            {
                case 1: PasoUno(); break;
                case 2: PasoDos(); break;
                default: PasoTres(); break;
            }
        });
        PintarPie();
    }

    private View Pasos()
    {
        var fila = EstudioUi.Envolver();
        string[] nombres = ["Para quién", "Qué lección", "Cuándo y cómo"];
        for (var i = 0; i < nombres.Length; i++)
        {
            var n = i + 1;
            var hecho = n < _paso;
            var actual = n == _paso;
            var pildora = Ds.Pildora($"{(hecho ? "✓" : n.ToString())}   {nombres[i]}",
                actual ? Ds.Tinta : hecho ? Ds.ExitoSuave : EstudioUi.PistaBarra,
                actual ? Colors.White : hecho ? Color.FromArgb("#0B5D3B") : Ds.TintaSuave, 15);
            pildora.Padding = new Thickness(18, 9);
            pildora.Margin = new Thickness(0, 0, 10, 0);
            fila.Add(pildora);
        }
        return fila;
    }

    private (bool Valido, string Pista) ValidarPaso()
    {
        switch (_paso)
        {
            case 1:
                if (_grupo is null) return (false, "Elige un grupo para continuar.");
                if (_todoElGrupo) return _grupo.Alumnos.Count > 0 ? (true, $"Para {EstudioTexto.Plural(_grupo.Alumnos.Count, "alumno", "alumnos")} de {_grupo.Nombre ?? _grupo.Codigo}.") : (false, "Este grupo no tiene alumnos todavía.");
                return _elegidos.Count > 0 ? (true, $"Para {EstudioTexto.Plural(_elegidos.Count, "alumno elegido", "alumnos elegidos")}.") : (false, "Elige al menos un alumno para continuar.");
            case 2:
                return _leccion is null ? (false, _curso is null ? "Elige un curso y después una lección." : "Elige una lección para continuar.") : (true, _leccion.Titulo);
            default:
                var destino = FechaElegida(_dias, _minutos);
                if (destino is not null && destino <= DateTime.Now) return (false, "La fecha elegida ya pasó: elige otra hora.");
                return (true, destino is null ? "Sin fecha límite." : $"Entrega: {EstudioTexto.FechaLarga(destino.Value)}.");
        }
    }

    private void PintarPie()
    {
        PieAtras.Clear();
        PieSiguiente.Clear();
        var atras = _paso == 1
            ? EstudioUi.Accion("Cancelar", Ds.Rango.Quiet, async () => await MostrarListaAsync(), null, "estudio-cancelar")
            : EstudioUi.Accion("‹  Atrás", Ds.Rango.Secondary, () => { _paso--; PintarPaso(); return Task.CompletedTask; }, 150, "estudio-atras");
        PieAtras.Add(atras.Vista);

        var (valido, pista) = ValidarPaso();
        var siguiente = _paso < 3
            ? EstudioUi.Accion("Siguiente  ›", Ds.Rango.Primary, () => { _paso++; PintarPaso(); Iniciar(); return Task.CompletedTask; }, 190, "estudio-siguiente")
            : EstudioUi.Accion(_enviando ? "Asignando…" : "Asignar la lección", Ds.Rango.Primary, AsignarAsync, 250, "estudio-asignar");
        Ds.Habilitar(siguiente.Boton, valido && !_enviando);
        PieSiguiente.Add(siguiente.Vista);
        PieLabel.Text = pista;
    }

    /// <summary>Al entrar al paso de la lección por primera vez se lee el catálogo (una sola vez por asistente).</summary>
    private void Iniciar()
    {
        if (_paso == 2 && _catalogo is null && !_catalogoCargando)
            _ = CargarCatalogoAsync();
    }

    private static View Seccion(string titulo, string? explicacion, params View[] contenido)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo(titulo, 22));
        if (!string.IsNullOrWhiteSpace(explicacion)) pila.Add(Ds.Secundario(explicacion, 15));
        foreach (var vista in contenido) pila.Add(vista);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Colors.White);
    }

    // ------------------------------------------------------------------------- paso 1 · para quién

    private void PasoUno()
    {
        if (_grupos is null)
        {
            ContenidoHost.Add(_gruposError is null
                ? Cargando("Buscando tus grupos…")
                : EstudioUi.Aviso("No se pudieron leer tus grupos", _gruposError, Ds.PeligroSuave, EstudioUi.TintaPeligro));
            return;
        }
        if (!_grupos.Instalado)
        {
            ContenidoHost.Add(EstudioUi.Aviso("El nodo aún no tiene organización instalada",
                "Sin organización no hay grupos ni alumnos. Pide a la administración que instale el nodo y vuelve aquí.", Ds.AlertaSuave, Color.FromArgb("#806600")));
            return;
        }
        if (_grupos.Grupos.Count == 0)
        {
            ContenidoHost.Add(EstudioUi.Aviso("No tienes grupos a tu cargo",
                "Los grupos los define la administración. Cuando tengas uno, aparecerá aquí.", Ds.AlertaSuave, Color.FromArgb("#806600")));
            return;
        }

        var tarjetas = new VerticalStackLayout { Spacing = 10 };
        foreach (var grupo in _grupos.Grupos)
        {
            var g = grupo;
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14 };
            var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = g.Nombre ?? g.Codigo ?? g.Id, FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta });
            var detalle = string.Join(" · ", new[] { g.Codigo is not null && g.Nombre is not null ? g.Codigo : null, g.NivelClave }.Where(x => !string.IsNullOrWhiteSpace(x)));
            if (detalle.Length > 0) texto.Add(Ds.Secundario(detalle, 14));
            fila.Add(texto, 0, 0);
            var cuantos = Ds.Pildora(EstudioTexto.Plural(g.Alumnos.Count, "alumno", "alumnos"), Color.FromArgb("#F0F0F2"), Ds.TintaMedia, 14);
            fila.Add(cuantos, 1, 0);
            tarjetas.Add(EstudioUi.TarjetaElegible(fila, _grupo?.Id == g.Id, () =>
            {
                if (_grupo?.Id != g.Id)
                {
                    _grupo = g;
                    _todoElGrupo = true;
                    _elegidos.Clear();
                }
                PintarPaso();
                return Task.CompletedTask;
            }, $"Grupo {g.Nombre ?? g.Codigo}, {g.Alumnos.Count} alumnos", $"estudio-grupo-{g.Id}"));
        }
        ContenidoHost.Add(Seccion("¿Para quién es?", "Elige el grupo. Después puedes asignarla a todo el grupo o sólo a algunos alumnos. Cada alumno elige su nombre al entrar al modo de estudio; no hay código.", tarjetas));

        if (_grupo is not { } elegido) return;
        var quienes = EstudioUi.Envolver();
        quienes.Add(EstudioUi.Chip($"Todo el grupo · {elegido.Alumnos.Count}", _todoElGrupo, () => { _todoElGrupo = true; PintarPaso(); return Task.CompletedTask; }, "estudio-todo-el-grupo"));
        quienes.Add(EstudioUi.Chip("Elegir alumnos", !_todoElGrupo, () => { _todoElGrupo = false; PintarPaso(); return Task.CompletedTask; }, "estudio-elegir-alumnos"));
        var contenido = new List<View> { quienes };
        if (_todoElGrupo)
        {
            contenido.Add(Ds.Secundario("Se asigna a todos los alumnos del grupo, también a los que se inscriban después.", 14));
        }
        else
        {
            var atajos = EstudioUi.Envolver();
            atajos.Add(EstudioUi.Chip("Marcar a todos", _elegidos.Count == elegido.Alumnos.Count, () =>
            {
                foreach (var a in elegido.Alumnos) _elegidos.Add(a.Id);
                PintarPaso();
                return Task.CompletedTask;
            }, "estudio-marcar-todos", 48));
            atajos.Add(EstudioUi.Chip("Quitar a todos", false, () => { _elegidos.Clear(); PintarPaso(); return Task.CompletedTask; }, "estudio-quitar-todos", 48));
            contenido.Add(atajos);
            var alumnos = EstudioUi.Envolver();
            foreach (var alumno in elegido.Alumnos.OrderBy(a => a.Rotulo ?? a.Id, StringComparer.CurrentCultureIgnoreCase))
            {
                var id = alumno.Id;
                alumnos.Add(EstudioUi.Chip(alumno.Rotulo ?? id, _elegidos.Contains(id), () =>
                {
                    if (!_elegidos.Remove(id)) _elegidos.Add(id);
                    PintarPaso();
                    return Task.CompletedTask;
                }, $"estudio-alumno-{id}", 48));
            }
            contenido.Add(alumnos);
            contenido.Add(Ds.Secundario($"{_elegidos.Count} de {elegido.Alumnos.Count} elegidos.", 14));
        }
        ContenidoHost.Add(Seccion("¿A quiénes?", null, contenido.ToArray()));
    }

    // ------------------------------------------------------------------------ paso 2 · qué lección

    private async Task CargarCatalogoAsync()
    {
        _catalogoCargando = true;
        _catalogoError = null;
        PintarPaso();
        var api = Sesion.Aula;
        var catalogo = await api.CursosAsync();
        if (_vista != Vista.Nueva) return;
        _catalogoCargando = false;
        _catalogo = catalogo;
        _indice = catalogo is { Disponible: true } ? new IndiceDeCursos(catalogo) : null;
        _catalogoError = catalogo is null ? EstudioTexto.Error(api.UltimoError, api.UltimoMotivo) : null;
        if (catalogo is { Asignaturas.Count: 1 }) _asignatura = catalogo.Asignaturas[0].Codigo;
        if (_paso == 2) PintarPaso();
    }

    private async Task ElegirCursoAsync(FichaCurso ficha)
    {
        _curso = ficha;
        _vistaCurso = null;
        _leccion = null;
        _cursoError = null;
        _cursoCargando = true;
        PintarPaso();
        var api = Sesion.Aula;
        var curso = await api.CursoAsync(ficha.CursoRef, false);
        if (_vista != Vista.Nueva || _curso?.CursoRef != ficha.CursoRef) return;
        _cursoCargando = false;
        _vistaCurso = curso;
        _cursoError = curso is null ? EstudioTexto.Error(api.UltimoError, api.UltimoMotivo) : null;
        if (_paso == 2) PintarPaso();
    }

    private void PasoDos()
    {
        var fuenteChip = Ds.Pildora("Fuente: AVACOM Biblioteca", Ds.InfoSuave, Color.FromArgb("#02739E"), 13);
        fuenteChip.HorizontalOptions = LayoutOptions.Start;

        if (_catalogoCargando || (_catalogo is null && _catalogoError is null))
        {
            ContenidoHost.Add(Seccion("¿Qué lección?", "Leyendo los cursos disponibles…", fuenteChip));
            return;
        }
        if (_catalogo is null || !_catalogo.Disponible)
        {
            var acciones = new HorizontalStackLayout { Spacing = 12 };
            acciones.Add(EstudioUi.Accion("Reintentar", Ds.Rango.Secondary, async () => { _catalogo = null; await CargarCatalogoAsync(); }, 170, "estudio-reintentar").Vista);
            ContenidoHost.Add(Seccion("¿Qué lección?", null, fuenteChip,
                EstudioUi.Aviso("No se pueden leer los cursos",
                    _catalogoError ?? "AVACOM Biblioteca no está conectada. Una lección no se asigna a ciegas: conecta la biblioteca y vuelve a intentarlo.",
                    Ds.AlertaSuave, Color.FromArgb("#806600")), acciones));
            return;
        }

        var contenido = new List<View> { fuenteChip };
        var asignaturas = _catalogo.Asignaturas;
        // El buscador mira TODOS los cursos de TODAS las materias; la materia sólo acota cuando no se está buscando.
        DesengancharBuscador();
        contenido.Add(CajaBuscador());
        if (asignaturas.Count > 1)
        {
            var chips = EstudioUi.Envolver();
            foreach (var asignatura in asignaturas)
            {
                var codigo = asignatura.Codigo;
                chips.Add(EstudioUi.Chip($"{asignatura.Nombre} · {asignatura.Cursos.Count}", _asignatura == codigo && _busqueda.Length == 0, () =>
                {
                    _asignatura = codigo;
                    LimpiarBusqueda();
                    _curso = null; _vistaCurso = null; _leccion = null;
                    PintarPaso();
                    return Task.CompletedTask;
                }, $"estudio-asignatura-{codigo}"));
            }
            contenido.Add(Ds.Secundario(_busqueda.Length > 0 ? "Materia (la búsqueda mira todas)" : "Materia", 15));
            contenido.Add(chips);
        }
        _resultados = new VerticalStackLayout { Spacing = 10 };
        contenido.Add(_resultados);
        PintarResultados();
        ContenidoHost.Add(Seccion("¿Qué lección?", "Elige el curso y después la lección. La lección se lee de la biblioteca; aquí sólo se guarda a cuál te refieres.", contenido.ToArray()));

        if (_curso is null) return;
        if (_cursoCargando)
        {
            ContenidoHost.Add(Seccion($"Lecciones de «{_curso.Titulo}»", "Leyendo el curso…"));
            return;
        }
        if (_vistaCurso is null)
        {
            ContenidoHost.Add(EstudioUi.Aviso("No se pudo leer el curso", _cursoError, Ds.PeligroSuave, EstudioUi.TintaPeligro));
            return;
        }

        var lecciones = new VerticalStackLayout { Spacing = 10 };
        foreach (var leccion in _vistaCurso.Lecciones)
        {
            var l = leccion;
            var soloExamen = l.SoloExamen;
            var materiales = l.ObjetosDelAula.Count(o => o.Componente != "examen");
            var conPractica = l.ObjetosDelAula.Any(o => o.EsActividad);
            var conExamen = l.ObjetosDelAula.Any(o => o.Componente == "examen") || l.Objetos?.Any(o => o.FueraDeAlcance) == true;
            var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = l.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            if (!string.IsNullOrWhiteSpace(l.Resumen)) texto.Add(new Label { Text = l.Resumen, FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
            texto.Add(Ds.Secundario(string.Join(" · ", new[]
            {
                materiales > 0 ? EstudioTexto.Plural(materiales, "material", "materiales") : null,
                conPractica ? "con práctica" : null,
                conExamen ? "el examen se presenta en clase" : null,
                l.DuracionEstimadaMin is > 0 ? $"~{l.DuracionEstimadaMin} min" : null,
            }.Where(x => x is not null)), 13));
            if (soloExamen) texto.Add(Ds.Secundario("Sólo tiene examen: la evaluación formal no se asigna como estudio.", 13));
            lecciones.Add(EstudioUi.TarjetaElegible(texto, _leccion?.LeccionRef == l.LeccionRef, () =>
            {
                _leccion = l;
                PintarPaso();
                return Task.CompletedTask;
            }, $"Lección {l.Titulo}", $"estudio-leccion-{l.LeccionRef}", !soloExamen));
        }
        ContenidoHost.Add(Seccion($"Lecciones de «{_curso.Titulo}»", _vistaCurso.Lecciones.Count == 0 ? "Este curso no tiene lecciones." : "Toca la lección que van a estudiar.", lecciones));
    }

    // ------------------------------------------------------------------ paso 3 · cuándo y cómo

    internal static DateTime? FechaElegida(int? dias, int minutos) =>
        dias is null or < 0 ? null : DateTime.Today.AddDays(dias.Value).AddMinutes(minutos);

    /// <summary>
    /// La fecha límite entre opciones: el día (o «sin fecha») y la hora. Devuelve lo elegido con <paramref name="alCambiar"/>; la hora sólo se ofrece
    /// cuando hay día. Debajo, la fecha resultante escrita en claro, para que se vea qué se está eligiendo.
    /// </summary>
    private static View SelectorDeFecha(int? dias, int minutos, Action<int?, int> alCambiar, bool mostrarSinFecha)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        var dia = EstudioUi.Envolver();
        if (mostrarSinFecha) dia.Add(EstudioUi.Chip("Sin fecha", dias == -1, () => { alCambiar(-1, minutos); return Task.CompletedTask; }, "estudio-dia-sin"));
        foreach (var (rotulo, valor) in DiasPredefinidos)
        {
            var v = valor;
            dia.Add(EstudioUi.Chip(rotulo, dias == v, () => { alCambiar(v, minutos); return Task.CompletedTask; }, $"estudio-dia-{v}"));
        }
        pila.Add(dia);
        if (dias is >= 0)
        {
            pila.Add(Ds.Secundario("Hora", 15));
            var hora = EstudioUi.Envolver();
            foreach (var (rotulo, valor) in HorasPredefinidas)
            {
                var v = valor;
                hora.Add(EstudioUi.Chip(rotulo, minutos == v, () => { alCambiar(dias, v); return Task.CompletedTask; }, $"estudio-hora-{v}", 48));
            }
            pila.Add(hora);
        }
        var destino = FechaElegida(dias, minutos);
        if (destino is not null)
            pila.Add(new Label
            {
                Text = destino <= DateTime.Now ? $"{EstudioTexto.FechaLarga(destino.Value)} · esa hora ya pasó" : $"Entrega: {EstudioTexto.FechaLarga(destino.Value)}",
                FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = destino <= DateTime.Now ? EstudioUi.TintaPeligro : Ds.Tinta,
            });
        else if (dias == -1)
            pila.Add(Ds.Secundario("Sin fecha límite: la lección queda abierta hasta que la cierres.", 15));
        return pila;
    }

    private void PasoTres()
    {
        var fecha = SelectorDeFecha(_dias, _minutos, (dias, minutos) =>
        {
            _dias = dias;
            _minutos = minutos;
            PintarPaso();
        }, true);
        ContenidoHost.Add(Seccion("¿Para cuándo?", "Elige el día y la hora de entrega. Se cuenta con la hora del aula.", fecha));

        var plazo = EstudioUi.Envolver();
        plazo.Add(EstudioUi.Chip("Flexible", _plazo == "blando", () => { _plazo = "blando"; PintarPaso(); return Task.CompletedTask; }, "estudio-plazo-blando"));
        plazo.Add(EstudioUi.Chip("Estricto", _plazo == "endurecido", () => { _plazo = "endurecido"; PintarPaso(); return Task.CompletedTask; }, "estudio-plazo-endurecido"));
        var plazoContenido = new List<View> { plazo };
        if (_plazo == "endurecido")
        {
            plazoContenido.Add(Ds.Secundario("Gracia para lo que la tableta mande con retraso", 15));
            var gracia = EstudioUi.Envolver();
            foreach (var (rotulo, minutos) in new[] { ("5 min", 5), ("15 min", 15), ("30 min", 30), ("1 hora", 60) })
            {
                var m = minutos;
                gracia.Add(EstudioUi.Chip(rotulo, _graciaMin == m, () => { _graciaMin = m; PintarPaso(); return Task.CompletedTask; }, $"estudio-gracia-{m}", 48));
            }
            plazoContenido.Add(gracia);
        }
        plazoContenido.Add(Ds.Secundario(_plazo == "endurecido"
            ? "La asignación cierra al vencer. Lo que el alumno hizo antes de la hora y llega dentro de la gracia se acepta; lo que llega después espera tu decisión; lo hecho después de la hora se rechaza."
            : "Todo se acepta. Lo que el alumno haga después de la fecha queda marcado como «fuera de plazo».", 14));
        ContenidoHost.Add(Seccion("¿Qué pasa si algo llega tarde?", null, plazoContenido.ToArray()));

        var descarga = EstudioUi.Envolver();
        descarga.Add(EstudioUi.Chip("Se puede descargar", _descarga, () => { _descarga = true; PintarPaso(); return Task.CompletedTask; }, "estudio-descarga-si"));
        descarga.Add(EstudioUi.Chip("Sólo en línea", !_descarga, () => { _descarga = false; PintarPaso(); return Task.CompletedTask; }, "estudio-descarga-no"));
        ContenidoHost.Add(Seccion("¿Se la pueden llevar a casa?", null, descarga,
            Ds.Secundario("Sólo las tabletas asignadas a un alumno descargan la lección para estudiarla sin conexión; una tableta compartida nunca la descarga.", 14)));

        var frases = EstudioUi.Envolver();
        foreach (var frase in Consignas)
        {
            var f = frase;
            frases.Add(EstudioUi.Chip(f, _consigna == f, () => { _consigna = _consigna == f ? null : f; PintarPaso(); return Task.CompletedTask; }, $"estudio-consigna-{Array.IndexOf(Consignas, f)}", 48));
        }
        ContenidoHost.Add(Seccion("Consigna (opcional)", "Una frase que el alumno lee antes de empezar. Toca de nuevo para quitarla.", frases));

        ContenidoHost.Add(ResumenDeAsignar());
    }

    private View ResumenDeAsignar()
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(Ds.Titulo("Resumen", 22));
        void Linea(string rotulo, string valor)
        {
            var g = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(150)), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
            g.Add(Ds.Secundario(rotulo, 15), 0, 0);
            g.Add(new Label { Text = valor, FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap }, 1, 0);
            pila.Add(g);
        }
        Linea("Lección", _leccion is null ? "—" : $"{_leccion.Titulo}{(_curso is null ? string.Empty : $" · {_curso.Titulo}")}");
        Linea("Para", _grupo is null ? "—" : _todoElGrupo
            ? $"Todo {_grupo.Nombre ?? _grupo.Codigo} ({EstudioTexto.Plural(_grupo.Alumnos.Count, "alumno", "alumnos")})"
            : $"{EstudioTexto.Plural(_elegidos.Count, "alumno", "alumnos")} de {_grupo.Nombre ?? _grupo.Codigo}");
        var destino = FechaElegida(_dias, _minutos);
        Linea("Entrega", destino is null ? "Sin fecha límite" : EstudioTexto.FechaLarga(destino.Value));
        Linea("Si llega tarde", _plazo == "endurecido" ? $"Estricto, con gracia de {_graciaMin} min" : "Flexible: se acepta y se marca");
        Linea("Descarga", _descarga ? "Se puede descargar en tabletas asignadas" : "Sólo en línea");
        if (_consigna is not null) Linea("Consigna", _consigna);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(26, 22), Color.FromArgb("#FBFBFC"));
    }

    // ---------------------------------------------------------------------------------- asignar

    private async Task AsignarAsync()
    {
        if (_enviando || _grupo is null || _curso is null || _leccion is null) return;
        var destino = FechaElegida(_dias, _minutos);
        if (destino is not null && destino <= DateTime.Now) return;
        _enviando = true;
        PintarPie();
        try
        {
            var nueva = new NuevaAsignacion(
                Alcance: _todoElGrupo ? "grupo" : "seleccion",
                GrupoId: _grupo.Id,
                Alumnos: _todoElGrupo ? null : _elegidos.ToList(),
                CursoRef: _curso.CursoRef,
                Fuente: Sesion.FuenteAula,
                LeccionRef: _leccion.LeccionRef,
                Titulo: _leccion.Titulo,
                Consigna: _consigna,
                FechaLimite: destino is null ? null : EstudioTexto.AMs(destino.Value),
                Plazo: _plazo,
                GraciaMin: _plazo == "endurecido" ? _graciaMin : null,
                PaquetePermitido: _descarga);
            var api = Api;
            var creada = await api.CrearAsignacionAsync(Actor, Sesion.ProfesorRotulo, nueva);
            if (creada is null)
            {
                Avisar("No se pudo asignar la lección", EstudioTexto.Error(api.UltimoError, api.UltimoMotivo), true);
                return;
            }
            _enviando = false;
            await MostrarDetalleAsync(creada.Id,
                $"Lección asignada a {EstudioTexto.Plural(creada.DestinatariosTotal, "alumno", "alumnos")}. La verán en «Modo de estudio» al elegir su nombre.");
        }
        finally
        {
            _enviando = false;
            if (_vista == Vista.Nueva) PintarPie();
        }
    }
}
