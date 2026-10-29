using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Lo que el panel pide guardar: sólo los apartados con algo (el nodo conserva los demás), la versión que se leyó y la <c>solicitud_id</c> de ESTE intento.</summary>
internal sealed record PeticionDeRetroalimentacion(IReadOnlyDictionary<string, string> Campos, int VersionEsperada, string SolicitudId);

internal enum ResultadoDeRetroalimentacion { Guardado, SinConexion, Conflicto, Rechazado }

internal sealed record RespuestaDeRetroalimentacion(ResultadoDeRetroalimentacion Resultado, string? Texto = null);

/// <summary>
/// «Retroalimentación»: lo que el profesor le dice al estudiante de su resultado, en tres apartados (fortalezas, dificultades, oportunidades de mejora) y un comentario. Todo se arma
/// con frases que se tocan; el texto es un extra opcional (el nodo principal no tiene teclado). No toca ninguna cifra. Lo que se elige en un apartado REEMPLAZA lo que ya había en ese
/// apartado; los apartados que se dejan vacíos se conservan.
///
/// Como el ajuste, una operación que no llegó al nodo NO se da por guardada: «Pendiente de confirmación», con «Reintentar» sobre la MISMA solicitud. Se crea una vez (lleva cajas de texto).
/// </summary>
internal sealed class PanelDeRetroalimentacion : ContentView
{
    private enum Fase { Libre, Guardando, Pendiente, Rechazado }

    private readonly Func<PeticionDeRetroalimentacion, Task<RespuestaDeRetroalimentacion>> _guardar;
    private readonly SolicitudReintentable _solicitud = new();
    private readonly SelectorDeFrases _fortalezas = new(FrasesDeCalificaciones.Fortalezas, "retro-fortalezas", null);
    private readonly SelectorDeFrases _dificultades = new(FrasesDeCalificaciones.Dificultades, "retro-dificultades", null);
    private readonly SelectorDeFrases _oportunidades = new(FrasesDeCalificaciones.Oportunidades, "retro-oportunidades", null);
    private readonly SelectorDeFrases _comentario = new([], "retro-comentario", "Escribe un comentario (opcional)");
    private readonly VerticalStackLayout _estado = new() { Spacing = 8 };

    private Calificacion _c;
    private Fase _fase = Fase.Libre;
    private string? _texto;
    private bool _limpiando;

    public PanelDeRetroalimentacion(Calificacion calificacion, Func<PeticionDeRetroalimentacion, Task<RespuestaDeRetroalimentacion>> guardar)
    {
        _c = calificacion;
        _guardar = guardar;
        AutomationId = "retro-panel";
        IsVisible = false;

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(ExamenUi.Seccion("Retroalimentación para el estudiante"));
        pila.Add(Ds.Secundario("Toca las frases que apliquen. Lo que elijas en un apartado reemplaza lo que ya había en ese apartado; los apartados que dejes vacíos se conservan. No cambia ninguna cifra.", 14));
        Apartado(pila, "FORTALEZAS", _fortalezas);
        Apartado(pila, "DIFICULTADES", _dificultades);
        Apartado(pila, "OPORTUNIDADES DE MEJORA", _oportunidades);
        Apartado(pila, "COMENTARIO (OPCIONAL)", _comentario);
        pila.Add(_estado);
        Content = ExamenUi.Tarjeta(pila);

        foreach (var s in new[] { _fortalezas, _dificultades, _oportunidades, _comentario }) s.Cambio += (_, _) => AlCambiar();
        PintarEstado();
    }

    private static void Apartado(VerticalStackLayout pila, string rotulo, View selector)
    {
        pila.Add(EstudioUi.Eyebrow(rotulo));
        pila.Add(selector);
    }

    public void Actualizar(Calificacion c)
    {
        _c = c;
        PintarEstado();
    }

    private Dictionary<string, string> Campos()
    {
        var campos = new Dictionary<string, string>();
        if (_fortalezas.Texto is { } f) campos["fortalezas"] = f;
        if (_dificultades.Texto is { } d) campos["dificultades"] = d;
        if (_oportunidades.Texto is { } o) campos["oportunidades"] = o;
        if (_comentario.Texto is { } c) campos["comentario"] = c;
        return campos;
    }

    private void AlCambiar()
    {
        if (_limpiando) return;
        if (_fase is Fase.Pendiente or Fase.Rechazado) { _fase = Fase.Libre; _texto = null; }
        PintarEstado();
    }

    private void PintarEstado()
    {
        _estado.Clear();
        var hayAlgo = Campos().Count > 0;
        switch (_fase)
        {
            case Fase.Guardando:
                _estado.Add(ExamenUi.Aviso("Guardando…", null, Tono.Info));
                break;
            case Fase.Pendiente:
                _estado.Add(ExamenUi.Aviso("Pendiente de confirmación", _texto ?? "No se pudo conectar con el aula: nada se guardó todavía. Reintentar no lo duplica.", Tono.Ambar));
                break;
            case Fase.Rechazado:
                _estado.Add(ExamenUi.Aviso("No se guardó la retroalimentación", _texto, Tono.Ambar));
                break;
        }
        var enCurso = _fase == Fase.Guardando;
        if (!hayAlgo && !enCurso) _estado.Add(Ds.Secundario("Elige al menos una frase o escribe algo para poder guardar.", 13));
        var boton = ExamenUi.Accion(enCurso ? "Guardando…" : _fase == Fase.Pendiente ? "Reintentar" : "Guardar retroalimentación", Ds.Rango.Primary,
            CalificacionesUi.Seguro(nameof(PanelDeRetroalimentacion), "Guardar", GuardarAsync), null, "retro-guardar", 56, margen: false);
        boton.Vista.HorizontalOptions = LayoutOptions.Start;
        Ds.Habilitar(boton.Boton, hayAlgo && !enCurso && _c.Estado != EstadosDeCalificacion.Anulada);
        _estado.Add(boton.Vista);
    }

    private async Task GuardarAsync()
    {
        var campos = Campos();
        if (_fase == Fase.Guardando || campos.Count == 0) return;
        var firma = $"retro|{_c.Id}|{_c.Version}|{string.Join("|", campos.OrderBy(k => k.Key, StringComparer.Ordinal).Select(k => $"{k.Key}={k.Value}"))}";
        var peticion = new PeticionDeRetroalimentacion(campos, _c.Version, _solicitud.Para(firma));
        _fase = Fase.Guardando;
        PintarEstado();
        var respuesta = await _guardar(peticion);
        _texto = respuesta.Texto;
        switch (respuesta.Resultado)
        {
            case ResultadoDeRetroalimentacion.Guardado:
                _solicitud.Soltar();
                _fase = Fase.Libre;
                _texto = null;
                _limpiando = true;
                try { foreach (var s in new[] { _fortalezas, _dificultades, _oportunidades, _comentario }) s.Limpiar(); }
                finally { _limpiando = false; }
                IsVisible = false;
                break;
            case ResultadoDeRetroalimentacion.SinConexion:
                _fase = Fase.Pendiente;
                break;
            default:
                // Un conflicto de versión conserva lo elegido: la página vuelve a leer la calificación y la próxima vez va con la versión nueva (otra solicitud).
                _fase = Fase.Rechazado;
                break;
        }
        PintarEstado();
    }
}
