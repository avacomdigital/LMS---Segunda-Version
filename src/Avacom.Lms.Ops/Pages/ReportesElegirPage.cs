using System.Globalization;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Llegar a un reporte sin escribir (FUN-143): elegir la CLASE (las cerradas de tus grupos, por periodo, grupo y materia), el GRUPO o el ESTUDIANTE (primero el grupo y luego la inicial de su
/// nombre). Todo son fichas y filas que se tocan: ningún campo de texto, porque el equipo del aula puede no tener teclado. Lo que se ofrece es lo que el nodo deja ver a esta persona.
/// </summary>
public sealed class ReportesElegirPage : PaginaDeReporte
{
    private readonly VerticalStackLayout _fichasHost = new() { Spacing = 8 };
    private readonly SelectorDeNodoView _selector = new();
    private FiltrosDeReportes? _filtros;
    private string _que = RutasDeReportes.ElegirClase;
    private string? _periodo, _grupoId, _inicial;
    private NodoAcademico? _nodo;
    private bool _inicializado;

    public ReportesElegirPage() : base("REPORTES", "Elegir", string.Empty)
    {
        SelectorHost.Add(_fichasHost);
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReportesElegirPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    private static (string Titulo, string Subtitulo) Textos(string que) => que switch
    {
        RutasDeReportes.ElegirGrupo => ("Elegir un grupo", "Los grupos que puedes ver. Elige uno para ver quién necesita atención."),
        RutasDeReportes.ElegirAlumno => ("Elegir un estudiante", "Elige el grupo y, si hace falta, la inicial de su nombre."),
        RutasDeReportes.ElegirBoletin => ("Boletines académicos", "Elige el grupo: se arma un boletín por estudiante, con sus puntos, su calificación y las recomendaciones del profesor."),
        _ => ("Elegir una clase", "Las clases cerradas de tus grupos, la más reciente primero."),
    };

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_inicializado)
        {
            _inicializado = true;
            _que = Parametro("que") is { } q && q is RutasDeReportes.ElegirClase or RutasDeReportes.ElegirGrupo or RutasDeReportes.ElegirAlumno or RutasDeReportes.ElegirBoletin ? q : RutasDeReportes.ElegirClase;
            _nodo = NodoDeLaRuta;
            var (titulo, subtitulo) = Textos(_que);
            Poner(titulo, subtitulo);
        }
        var api = ReportesUi.Api;
        var filtros = await LeerYPintarAsync(api, () => ReportesUi.FiltrosAsync(forzar: true), f => _filtros = f, "No se pudieron leer tus grupos");
        if (filtros is null) return;

        if (!Puede(filtros.Puede))
        {
            _fichasHost.Clear();
            _selector.Mostrar(null, null);
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Tu rol no puede ver este reporte", MensajesDeReportes.De(new Avacom.Lms.Core.Models.ErrorAula(403, "sin_permiso", string.Empty, null, null))));
            return;
        }
        if (filtros.Grupos.Count == 0)
        {
            _fichasHost.Clear();
            _selector.Mostrar(null, null);
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Todavía no hay grupos", EstadosVaciosDeReportes.SinGrupos));
            return;
        }

        var eleccion = ListasDeReportes.Resolver(filtros.Grupos, _periodo, _grupoId, grupoObligatorio: _que == RutasDeReportes.ElegirAlumno);
        (_periodo, _grupoId) = (eleccion.Periodo, eleccion.Grupo?.Id);
        PintarFichas(filtros);
        _selector.Mostrar(_que == RutasDeReportes.ElegirClase ? filtros.Nodos : null, _nodo);

        switch (_que)
        {
            case RutasDeReportes.ElegirGrupo: PintarGrupos(filtros); break;
            case RutasDeReportes.ElegirBoletin: PintarGrupos(filtros); break;
            case RutasDeReportes.ElegirAlumno: await PintarAlumnosAsync(api); break;
            default: await PintarClasesAsync(api); break;
        }
    }

    private bool Puede(PermisosDeReportes p) => _que switch
    {
        RutasDeReportes.ElegirGrupo => p.Grupo,
        RutasDeReportes.ElegirAlumno => p.Alumno,
        RutasDeReportes.ElegirBoletin => p.Alumno,            // el boletín es el informe nominal de cada estudiante: mismo permiso
        _ => p.Clase,
    };

    // ------------------------------------------------------------------------------------------------------------ las fichas

    private void PintarFichas(FiltrosDeReportes filtros)
    {
        _fichasHost.Clear();
        var periodos = ListasDeReportes.Periodos(filtros.Grupos);
        if (periodos.Count > 1)
        {
            _fichasHost.Add(EstudioUi.Eyebrow("PERIODO"));
            var fila = EstudioUi.Envolver();
            fila.Add(EstudioUi.Chip("Todos", _periodo is null, ReportesUi.Seguro(nameof(ReportesElegirPage), "Periodo", () => ElegirAsync(null, _grupoId)), "reportes-elegir-periodo-todos"));
            foreach (var periodo in periodos)
                fila.Add(EstudioUi.Chip(periodo, periodo == _periodo, ReportesUi.Seguro(nameof(ReportesElegirPage), "Periodo", () => ElegirAsync(periodo, _grupoId)), $"reportes-elegir-periodo-{periodo}"));
            _fichasHost.Add(fila);
        }
        if (_que is RutasDeReportes.ElegirGrupo or RutasDeReportes.ElegirBoletin) return;
        var grupos = ListasDeReportes.Grupos(filtros.Grupos, _periodo);
        if (_que == RutasDeReportes.ElegirAlumno && grupos.Count <= 1) return;           // el único grupo ya quedó elegido: no hay nada que tocar
        _fichasHost.Add(EstudioUi.Eyebrow("GRUPO"));
        var filaGrupos = EstudioUi.Envolver();
        if (_que == RutasDeReportes.ElegirClase)
            filaGrupos.Add(EstudioUi.Chip("Todos los grupos", _grupoId is null, ReportesUi.Seguro(nameof(ReportesElegirPage), "Grupo", () => ElegirAsync(_periodo, null)), "reportes-elegir-grupo-todos"));
        foreach (var g in grupos)
        {
            var id = g.Id;
            filaGrupos.Add(EstudioUi.Chip(g.Rotulo, _grupoId == id, ReportesUi.Seguro(nameof(ReportesElegirPage), "Grupo", () => ElegirAsync(_periodo, id)), $"reportes-elegir-grupo-{g.Codigo}"));
        }
        _fichasHost.Add(filaGrupos);
    }

    private async Task ElegirAsync(string? periodo, string? grupoId)
    {
        if (periodo == _periodo && grupoId == _grupoId) return;
        (_periodo, _grupoId, _inicial) = (periodo, grupoId, null);
        await CargarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------------------------------------ clases

    private async Task PintarClasesAsync(ReportesApi api)
    {
        var lista = await api.ClasesAsync(ReportesUi.Actor, new FiltroDeClases(GrupoId: _grupoId, Nodo: _nodo));
        if (!EstaVisible) return;
        if (lista is null) { ErrorDeLista(api, "No se pudieron leer las clases"); return; }
        ConexionHost.Clear();
        ContenidoHost.Clear();
        foreach (var aviso in lista.Avisos) ContenidoHost.Add(ExamenUi.Aviso(aviso.Aplicado ? "Filtro aplicado" : "Filtro no aplicado", aviso.Texto, aviso.Aplicado ? Tono.Info : Tono.Ambar));
        var clases = lista.Clases.Where(c => _periodo is null || c.Grupo?.Periodo == _periodo).ToList();
        if (clases.Count == 0)
        {
            // Dice POR QUÉ no hay: lo último que se tocó es lo que explica el vacío (un filtro de materia, un periodo, un grupo), y siempre qué hacer.
            var (titulo, texto) = _nodo is { EstaVacio: false } ? ("Ninguna clase de esa materia", "No hay clases cerradas de esa materia. Toca «Quitar filtro» para ver todas.")
                : _periodo is not null ? ("No hay clases en este periodo", EstadosVaciosDeReportes.SinClases)
                : _grupoId is not null ? ("Este grupo todavía no tiene clases cerradas", "Cuando termine una clase, su reporte aparece aquí.")
                : ("Todavía no hay clases cerradas", "Cuando termine una clase, su reporte aparece aquí.");
            ContenidoHost.Add(ReportesUi.Estado(titulo, texto));
            return;
        }
        var resumen = clases.Count < lista.Total ? $"Se muestran las {clases.Count} clases cerradas más recientes de {lista.Total}." : FormatoDeReportes.Plural(clases.Count, "clase cerrada", "clases cerradas") + ".";
        ContenidoHost.Add(ReportesUi.Seccion("Clases cerradas", $"{resumen} Tocar una abre su reporte."));
        foreach (var c in clases) ContenidoHost.Add(FilaDeClase(c));
    }

    private static View FilaDeClase(ClaseDeLista c)
    {
        var cuando = new VerticalStackLayout { Spacing = 0, VerticalOptions = LayoutOptions.Center };
        cuando.Add(new Label { Text = FormatoDeReportes.Dia(c.FinalizadaEn), FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta });
        cuando.Add(Ds.Secundario(FormatoDeReportes.Hora(c.FinalizadaEn), 14));

        var titulo = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        titulo.Add(new Label { Text = $"{c.Grupo?.Rotulo ?? "Sin grupo"} · {c.LeccionRotulo}", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
        titulo.Add(Ds.Secundario(c.CursoRotulo, 14));

        var datos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End };
        datos.Add(new Label { Text = $"{FormatoDeReportes.Plural(c.Participantes, "estudiante", "estudiantes")} · {FormatoDeReportes.Duracion(c.DuracionMs)}", FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaMedia, HorizontalTextAlignment = TextAlignment.End });
        if (c.Incompleta)
        {
            var p = ExamenUi.Fila();
            p.HorizontalOptions = LayoutOptions.End;
            p.Add(ExamenUi.PildoraEnFila("Incompleto", Tono.Ambar, 12));
            datos.Add(p);
        }

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(150), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 18, MinimumHeightRequest = 44 };
        fila.Add(cuando, 0, 0);
        fila.Add(titulo, 1, 0);
        fila.Add(datos, 2, 0);
        return ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(ReportesElegirPage), "AbrirClase", () => Shell.Current.GoToAsync(RutasDeReportes.DeClase(c.SesionId))),
            $"Clase del {FormatoDeReportes.FechaCorta(c.FinalizadaEn)}, {c.Grupo?.Rotulo ?? "sin grupo"}, {c.LeccionRotulo}", $"reportes-clase-{c.SesionId}", Colors.White, new Thickness(22, 12));
    }

    // ------------------------------------------------------------------------------------------------------------ grupos

    private void PintarGrupos(FiltrosDeReportes filtros)
    {
        ContenidoHost.Clear();
        var grupos = ListasDeReportes.Grupos(filtros.Grupos, _periodo);
        if (grupos.Count == 0)
        {
            ContenidoHost.Add(ReportesUi.Estado("No hay grupos en este periodo", "Elige otro periodo."));
            return;
        }
        var boletines = _que == RutasDeReportes.ElegirBoletin;
        ContenidoHost.Add(ReportesUi.Seccion("Grupos", $"{FormatoDeReportes.Plural(grupos.Count, "grupo", "grupos")}. {(boletines ? "Tocar uno arma un boletín por estudiante." : "Tocar uno abre su reporte.")}"));
        foreach (var g in grupos)
        {
            var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = ListasDeReportes.RotuloLargo(g), FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta });
            texto.Add(Ds.Secundario(ListasDeReportes.ResumenDeGrupo(g), 15));
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 18, MinimumHeightRequest = 52 };
            fila.Add(texto, 0, 0);
            fila.Add(new Label { Text = boletines ? "Boletines  ›" : "Ver  ›", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Rojo, VerticalOptions = LayoutOptions.Center }, 1, 0);
            var id = g.Id;
            var ruta = boletines ? RutasDeReportes.DeBoletines(id) : RutasDeReportes.DeGrupo(id);
            ContenidoHost.Add(ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(ReportesElegirPage), boletines ? "AbrirBoletines" : "AbrirGrupo", () => Shell.Current.GoToAsync(ruta)),
                $"Grupo {g.Rotulo}. {ListasDeReportes.ResumenDeGrupo(g)}", $"reportes-grupo-{g.Codigo}", Colors.White, new Thickness(24, 14)));
        }
    }

    // ------------------------------------------------------------------------------------------------------------ estudiantes

    private async Task PintarAlumnosAsync(ReportesApi api)
    {
        if (_grupoId is null)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Elige un grupo", "Toca el grupo del estudiante que buscas."));
            return;
        }
        var grupoId = _grupoId;
        var alumnos = await api.AlumnosAsync(ReportesUi.Actor, grupoId);
        if (!EstaVisible || grupoId != _grupoId) return;
        if (alumnos is null) { ErrorDeLista(api, "No se pudieron leer los estudiantes"); return; }
        ConexionHost.Clear();
        ContenidoHost.Clear();
        if (alumnos.Alumnos.Count == 0)
        {
            ContenidoHost.Add(ReportesUi.Estado("Este grupo todavía no tiene estudiantes", EstadosVaciosDeReportes.SinAlumnos));
            return;
        }
        _inicial = ListasDeReportes.InicialValida(alumnos.Iniciales, _inicial);
        if (alumnos.Iniciales.Count > 1)
        {
            ContenidoHost.Add(EstudioUi.Eyebrow("INICIAL DEL NOMBRE"));
            var fila = EstudioUi.Envolver();
            fila.Add(EstudioUi.Chip($"Todos ({alumnos.Alumnos.Count})", _inicial is null, ReportesUi.Seguro(nameof(ReportesElegirPage), "Inicial", () => ElegirInicialAsync(null)), "reportes-inicial-todos"));
            foreach (var i in alumnos.Iniciales)
            {
                var letra = i.Inicial;
                fila.Add(EstudioUi.Chip($"{letra} ({i.Cantidad})", string.Equals(_inicial, letra, StringComparison.OrdinalIgnoreCase), ReportesUi.Seguro(nameof(ReportesElegirPage), "Inicial", () => ElegirInicialAsync(letra)), $"reportes-inicial-{letra}"));
            }
            ContenidoHost.Add(fila);
        }
        var lista = ListasDeReportes.PorInicial(alumnos.Alumnos, _inicial);
        ContenidoHost.Add(ReportesUi.Seccion("Estudiantes", $"{FormatoDeReportes.Plural(lista.Count, "estudiante", "estudiantes")}. Tocar uno abre su reporte."));
        foreach (var a in lista)
        {
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14, MinimumHeightRequest = 44 };
            fila.Add(new Label { Text = a.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center }, 0, 0);
            if (a.NecesitaAtencion) fila.Add(ExamenUi.Pildora("Necesita atención", Tono.Ambar, 13), 1, 0);
            var id = a.Id;
            ContenidoHost.Add(ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(ReportesElegirPage), "AbrirAlumno", () => Shell.Current.GoToAsync(RutasDeReportes.DeAlumno(id, grupoId))),
                $"{a.Rotulo}{(a.NecesitaAtencion ? ". Necesita atención" : string.Empty)}", $"reportes-alumno-{id}", Colors.White, new Thickness(22, 10)));
        }
    }

    private async Task ElegirInicialAsync(string? inicial)
    {
        if (string.Equals(inicial, _inicial, StringComparison.OrdinalIgnoreCase)) return;
        _inicial = inicial;
        await CargarAsync(forzar: true);
    }

    private void ErrorDeLista(ReportesApi api, string titulo)
    {
        var error = ReportesUi.Error(api);
        ContenidoHost.Clear();
        ContenidoHost.Add(ReportesUi.Estado(titulo, error,
            ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(ReportesElegirPage), "Reintentar", () => CargarAsync(forzar: true)), 170, "reporte-reintentar", margen: false).Vista));
        MostrarBanner(ReportesUi.SinConexion(api) ? null : error, ReportesUi.SinConexion(api));
    }
}
