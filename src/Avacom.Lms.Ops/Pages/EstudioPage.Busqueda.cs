using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Paso 2 de «Asignar una lección» · el buscador de cursos. El catálogo llegará a ~25 000 cursos: no se pintan todos (sólo LimiteInicialCursos y
// «Mostrar más»), y el buscador mira TODOS, de todas las materias, por título, tema, grado, nivel, país o código. La búsqueda vive en Core
// (IndiceDeCursos: texto normalizado una vez, sin tildes) y es la misma que la de «Clase de hoy».
public partial class EstudioPage
{
    private Entry? _buscadorEntry;
    private Border? _buscadorBorde;

    /// <summary>La caja de búsqueda se construye una sola vez: el Entry nativo no puede pasar a otro contenedor mientras el anterior siga vivo (COMException).</summary>
    private Border CajaBuscador()
    {
        if (_buscadorBorde is not null) return _buscadorBorde;
        _buscadorEntry = new Entry
        {
            Placeholder = "Buscar entre todos los cursos: nombre, tema, grado, país o código", FontSize = 18, FontFamily = Ds.FuenteRegular, TextColor = Ds.Tinta,
            HeightRequest = 54, BackgroundColor = Colors.Transparent, IsSpellCheckEnabled = false, IsTextPredictionEnabled = false, ReturnType = ReturnType.Search,
            Text = _busqueda,
        };
        SemanticProperties.SetDescription(_buscadorEntry, "Buscar entre todos los cursos");
        _buscadorEntry.TextChanged += (_, e) => AlCambiarBusqueda(e.NewTextValue);
        var limpiar = Ds.Boton("Limpiar", Ds.Rango.Quiet, (_, _) => { if (_buscadorEntry is not null) _buscadorEntry.Text = string.Empty; }, 46);
        limpiar.FontSize = 15;
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 6 };
        fila.Add(_buscadorEntry, 0, 0);
        fila.Add(limpiar, 1, 0);
        _buscadorBorde = new Border
        {
            BackgroundColor = Ds.Lienzo, StrokeThickness = 1, Stroke = new SolidColorBrush(Ds.Filo), Padding = new Thickness(14, 2, 6, 2), Content = fila,
            StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 18 },
        };
        return _buscadorBorde;
    }

    private void LimpiarBusqueda()
    {
        _busqueda = string.Empty;
        _limiteCursos = LimiteInicialCursos;
        if (_buscadorEntry is not null) _buscadorEntry.Text = string.Empty;
    }

    /// <summary>Quita la caja de su contenedor anterior (el del paso ya repintado) antes de ponerla en el nuevo.</summary>
    private void DesengancharBuscador()
    {
        if (_buscadorBorde?.Parent is Layout padre) padre.Remove(_buscadorBorde);
    }

    /// <summary>Con 250 ms de calma tras la última tecla se repinta SÓLO la lista de resultados, no el paso: el cursor y el teclado táctil no se mueven.</summary>
    private void AlCambiarBusqueda(string? texto)
    {
        var nueva = (texto ?? string.Empty).Trim();
        var version = ++_versionBusqueda;
        Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(250), () =>
        {
            if (version != _versionBusqueda || _vista != Vista.Nueva || nueva == _busqueda) return;
            _busqueda = nueva;
            _limiteCursos = LimiteInicialCursos;
            PintarResultados();
        });
    }

    private void PintarResultados()
    {
        if (_resultados is null || _indice is null || _catalogo is null) return;
        _resultados.Clear();
        var asignaturas = _catalogo.Asignaturas;
        var buscando = _busqueda.Length > 0;
        if (!buscando && asignaturas.Count > 1 && _asignatura is null)
        {
            _resultados.Add(Ds.Secundario($"Elige una materia, o busca un curso por nombre, tema, grado o código entre los {_indice.Total} cursos.", 15));
            return;
        }
        var materia = !buscando && asignaturas.Count > 1 ? _asignatura : null;
        var r = _indice.Buscar(_busqueda, materia, _limiteCursos);
        if (r.Total == 0)
        {
            _resultados.Add(Ds.Secundario(buscando ? $"Ningún curso coincide con «{_busqueda}». Prueba con otra palabra." : "No hay cursos en esta materia.", 15));
            return;
        }
        _resultados.Add(Ds.Secundario(buscando
            ? $"{EstudioTexto.Plural(r.Total, "curso coincide", "cursos coinciden")} de {_indice.Total}"
            : "Curso", 15));
        foreach (var e in r.Mostrados) _resultados.Add(TarjetaDeCurso(e, buscando));
        if (r.HayMas)
        {
            _resultados.Add(Ds.Secundario($"Mostrando {r.Mostrados.Count} de {r.Total}. Afina la búsqueda o muestra más.", 14));
            _resultados.Add(EstudioUi.Accion("Mostrar más cursos", Ds.Rango.Secondary, () => { _limiteCursos += PasoDeMasCursos; PintarResultados(); return Task.CompletedTask; }, 240, "estudio-mas-cursos").Vista);
        }
    }

    private View TarjetaDeCurso(EntradaDeCurso e, bool conMateria)
    {
        var c = e.Curso;
        var disponible = c.NoDisponible is null;
        var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = c.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        texto.Add(Ds.Secundario(conMateria && e.Asignatura is not null ? $"{e.Asignatura.Nombre} · {c.Detalle}" : c.Detalle, 14));
        return EstudioUi.TarjetaElegible(texto, _curso?.CursoRef == c.CursoRef, async () => await ElegirCursoAsync(c),
            disponible ? $"Curso {c.Titulo}" : $"Curso {c.Titulo}, no disponible", $"estudio-curso-{c.CursoRef}", disponible);
    }
}
