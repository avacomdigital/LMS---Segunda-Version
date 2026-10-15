using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Reportes.Ui;

/// <summary>
/// El filtro por nodo académico (país · nivel · grado · materia · tema) de un reporte (FUN-143), siempre con fichas que se tocan y nunca con un campo de texto. Cerrado, es un botón «Filtrar
/// por materia» y, si hay un filtro puesto, lo que se eligió en palabras con «Quitar filtro»; abierto, una fila de fichas por nivel que se va abriendo conforme se elige. Si la biblioteca
/// no respondió, dice que el filtro no está disponible y que el reporte lleva todo. La pantalla dueña recibe <see cref="Cambio"/> y vuelve a pedir el reporte.
/// </summary>
internal sealed class SelectorDeNodoView : ContentView
{
    private NodosAcademicos? _nodos;
    private NodoAcademico? _actual;
    private bool _abierto;

    /// <summary>La persona cambió el filtro (null = sin filtro). La pantalla guarda el nodo y vuelve a leer.</summary>
    public event Action<NodoAcademico?>? Cambio;

    public SelectorDeNodoView() => IsVisible = false;

    /// <summary>Pone el árbol y lo elegido. Con el árbol vacío y la biblioteca disponible no hay nada que filtrar y el selector se oculta.</summary>
    public void Mostrar(NodosAcademicos? nodos, NodoAcademico? actual)
    {
        _nodos = nodos;
        _actual = actual is { EstaVacio: true } ? null : actual;
        Pintar();
    }

    private void Pintar()
    {
        if (_nodos is null) { IsVisible = false; return; }
        if (_nodos.Disponible && _nodos.Arbol.Count == 0 && _actual is null) { IsVisible = false; return; }
        IsVisible = true;
        var pila = new VerticalStackLayout { Spacing = 8 };

        if (!_nodos.Disponible)
        {
            // No es algo que la persona deba arreglar ahora: una nota discreta (no una alerta) que dice por qué no hay filtro y que el reporte lleva todo.
            pila.Add(new Label
            {
                Text = (string.IsNullOrWhiteSpace(_nodos.Motivo) ? "El filtro por materia no está disponible: AVACOM Biblioteca no respondió." : $"El filtro por materia no está disponible. {_nodos.Motivo}") + " El reporte incluye todo.",
                FontFamily = Ds.FuenteRegular, FontSize = 13, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "reporte-filtro-no-disponible",
            });
            if (_actual is not null) pila.Add(Quitar());
            Content = pila;
            return;
        }

        var fila = EstudioUi.Envolver();
        fila.Add(EstudioUi.Chip(_abierto ? "Ocultar filtro por materia" : _actual is null ? "Filtrar por materia" : "Cambiar filtro por materia", _abierto, ReportesUi.Seguro(nameof(SelectorDeNodoView), "Abrir", () =>
        {
            _abierto = !_abierto;
            Pintar();
            return Task.CompletedTask;
        }), "reporte-filtro-nodo"));
        if (_actual is not null)
        {
            var resumen = ArbolDeNodos.Resumen(_nodos.Arbol, _actual);
            fila.Add(new Label { Text = resumen, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center, Margin = new Thickness(4, 0, 14, 10), AutomationId = "reporte-filtro-resumen" });
            fila.Add(Quitar());
        }
        pila.Add(fila);

        if (_abierto)
            foreach (var nivel in ArbolDeNodos.Filas(_nodos.Arbol, _actual))
            {
                pila.Add(EstudioUi.Eyebrow(ArbolDeNodos.RotuloDeNivel(nivel.Nivel).ToUpperInvariant()));
                var fichas = EstudioUi.Envolver();
                fichas.Add(EstudioUi.Chip("Todos", nivel.Elegido is null, Elegir(nivel.Nivel, null), $"reporte-filtro-{nivel.Nivel}-todos"));
                foreach (var opcion in nivel.Opciones)
                    fichas.Add(EstudioUi.Chip(ArbolDeNodos.Rotulo(opcion), opcion.Code == nivel.Elegido, Elegir(nivel.Nivel, opcion.Code), $"reporte-filtro-{nivel.Nivel}-{opcion.Code}"));
                pila.Add(fichas);
            }
        Content = pila;
    }

    private View Quitar() => EstudioUi.Chip("Quitar filtro", false, ReportesUi.Seguro(nameof(SelectorDeNodoView), "Quitar", () =>
    {
        _actual = null;
        _abierto = false;
        Pintar();
        Cambio?.Invoke(null);
        return Task.CompletedTask;
    }), "reporte-filtro-quitar");

    private Func<Task> Elegir(string nivel, string? codigo) => ReportesUi.Seguro(nameof(SelectorDeNodoView), "Elegir", () =>
    {
        _actual = ArbolDeNodos.Con(_actual, nivel, codigo);
        Pintar();
        Cambio?.Invoke(_actual);
        return Task.CompletedTask;
    });
}
