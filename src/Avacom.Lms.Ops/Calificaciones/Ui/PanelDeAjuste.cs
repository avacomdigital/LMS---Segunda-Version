using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Controls;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Lo que el panel pide ajustar: el valor nuevo, el motivo, la versión que se leyó y la <c>solicitud_id</c> de ESTE intento.</summary>
internal sealed record PeticionDeAjuste(decimal Puntaje, string Motivo, int VersionEsperada, string SolicitudId);

internal enum ResultadoDeAjuste { Confirmado, SinConexion, Conflicto, Rechazado }

/// <summary>Cómo terminó un ajuste; <c>Texto</c> es lo que el profesor lee (el error en palabras, o el valor actual tras un conflicto).</summary>
internal sealed record RespuestaDeAjuste(ResultadoDeAjuste Resultado, string? Texto = null);

/// <summary>
/// «Ajustar calificación» (FUN-123): la puntuación original (que no cambia jamás) y la efectiva a la vista, un teclado numérico táctil propio para la puntuación nueva (el nodo
/// principal no tiene teclado), el motivo OBLIGATORIO entre frases prehechas (con «Otro motivo» y un campo opcional) y «Confirmar ajuste», que sigue deshabilitado mientras
/// <see cref="GradebookTexto.ErroresDeAjuste"/> no esté vacío; los errores se dicen en palabras. El panel no calcula nada: valida la FORMA de lo escrito y manda; el nodo decide.
///
/// <b>Estados de la operación.</b> «Guardando…»; «Pendiente de confirmación» si no llegó al nodo (NO se muestra como confirmado: se conserva la solicitud y el botón dice «Reintentar»,
/// que reenvía la MISMA solicitud, así el nodo no duplica); «Confirmado» sólo tras el 2xx; y el conflicto de versión (otra persona cambió la calificación): se avisa, se vuelve a leer y
/// se muestra el valor actual SIN perder lo que el profesor escribió.
///
/// Se crea una vez y no cambia de contenedor (lleva un cuadro de texto): lo que cambia se repinta en una zona propia.
/// </summary>
internal sealed class PanelDeAjuste : ContentView
{
    private enum Fase { Libre, Guardando, Pendiente, Confirmado, Conflicto, Rechazado }

    private readonly Func<PeticionDeAjuste, Task<RespuestaDeAjuste>> _ajustar;
    private readonly SolicitudReintentable _solicitud = new();
    private readonly Label _original = new() { FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta };
    private readonly Label _efectiva = new() { FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta };
    private readonly Label _explicacion = new() { FontFamily = Ds.FuenteLigera, FontSize = 14, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap };
    private readonly TecladoDecimalView _teclado = new();
    private readonly SelectorDeMotivo _motivo = new(FrasesDeCalificaciones.MotivosDeAjuste, "ajuste");
    private readonly VerticalStackLayout _estado = new() { Spacing = 8 };

    private Calificacion _c;
    private Fase _fase = Fase.Libre;
    private string? _texto;
    private bool _limpiando;

    public PanelDeAjuste(Calificacion calificacion, Func<PeticionDeAjuste, Task<RespuestaDeAjuste>> ajustar)
    {
        _c = calificacion;
        _ajustar = ajustar;
        AutomationId = "ajuste-panel";

        var datos = new HorizontalStackLayout { Spacing = 40 };
        datos.Add(Dato("PUNTUACIÓN ORIGINAL", _original, "no cambia jamás"));
        datos.Add(Dato("PUNTUACIÓN EFECTIVA", _efectiva, "la vigente"));

        var izquierda = new VerticalStackLayout { Spacing = 8 };
        izquierda.Add(EstudioUi.Eyebrow("NUEVA PUNTUACIÓN (0 A 100)"));
        izquierda.Add(_teclado);
        var derecha = new VerticalStackLayout { Spacing = 8 };
        derecha.Add(EstudioUi.Eyebrow("MOTIVO DEL AJUSTE (OBLIGATORIO)"));
        derecha.Add(_motivo);
        var cuerpo = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 32 };
        cuerpo.Add(izquierda, 0, 0);
        cuerpo.Add(derecha, 1, 0);

        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(ExamenUi.Seccion("Ajustar calificación"));
        pila.Add(_explicacion);
        pila.Add(datos);
        pila.Add(cuerpo);
        pila.Add(_estado);
        Content = ExamenUi.Tarjeta(pila);

        _teclado.TextoCambiado += (_, _) => AlCambiar();
        _motivo.Cambio += (_, _) => AlCambiar();
        Actualizar(calificacion);
    }

    private static View Dato(string rotulo, Label valor, string nota)
    {
        var pila = new VerticalStackLayout { Spacing = 2 };
        pila.Add(EstudioUi.Eyebrow(rotulo));
        pila.Add(valor);
        pila.Add(Ds.Secundario(nota, 12));
        return pila;
    }

    /// <summary>El nodo mandó la calificación (otra vez): se actualizan los valores a la vista. Lo escrito y el estado de la operación NO se tocan (tras un conflicto, el profesor no pierde lo que escribió).</summary>
    public void Actualizar(Calificacion c)
    {
        _c = c;
        _original.Text = GradebookTexto.Puntaje(c.PuntajeOriginal);
        _efectiva.Text = GradebookTexto.Puntaje(c.PuntajeEfectivo) + (c.Ajustada ? "  · ajustada" : string.Empty);
        _explicacion.Text = "El ajuste cambia la puntuación efectiva; la original queda y el cambio, con su motivo, en el historial."
            + (c.Publicada ? " Como ya está publicada, el estudiante verá la presentación actualizada y el ajuste quedará marcado como posterior a la publicación." : string.Empty);
        PintarEstado();
    }

    // ----------------------------------------------------------------------------------------------- estado

    private IReadOnlyList<string> Errores() => GradebookTexto.ErroresDeAjuste(_teclado.Texto, _motivo.Motivo, _c.PuntajeEfectivo);

    /// <summary>Lo escrito cambió: lo que se iba a mandar es otra operación, así que se sale de «pendiente», «conflicto», «confirmado» o «rechazado» (la solicitud nueva la estrena Confirmar).</summary>
    private void AlCambiar()
    {
        if (_limpiando) return;
        if (_fase is Fase.Pendiente or Fase.Confirmado or Fase.Conflicto or Fase.Rechazado) { _fase = Fase.Libre; _texto = null; }
        PintarEstado();
    }

    private void PintarEstado()
    {
        _estado.Clear();
        var errores = Errores();
        switch (_fase)
        {
            case Fase.Guardando:
                _estado.Add(ExamenUi.Aviso("Guardando…", "Un momento: se está registrando el ajuste.", Tono.Info));
                break;
            case Fase.Pendiente:
                // Sin conexión: NO está confirmado. Se conserva la solicitud para reintentar sin duplicar.
                _estado.Add(ExamenUi.Aviso("Pendiente de confirmación", _texto ?? "No se pudo conectar con el aula: el ajuste no se registró todavía. Reintentar no lo duplica.", Tono.Ambar));
                break;
            case Fase.Confirmado:
                _estado.Add(ExamenUi.Aviso("Confirmado", _texto ?? "El ajuste quedó registrado en el historial.", Tono.Exito));
                break;
            case Fase.Conflicto:
                _estado.Add(ExamenUi.Aviso("Otra persona cambió esta calificación", _texto, Tono.Ambar));
                break;
            case Fase.Rechazado:
                _estado.Add(ExamenUi.Aviso("No se registró el ajuste", _texto, Tono.Ambar));
                break;
        }

        var enCurso = _fase == Fase.Guardando;
        if (errores.Count > 0 && !enCurso && _fase != Fase.Confirmado)
        {
            var lista = new VerticalStackLayout { Spacing = 2 };
            lista.Add(new Label { Text = "Para confirmar falta:", FontFamily = Ds.FuenteMedia, FontSize = 14, TextColor = Ds.TintaMedia });
            foreach (var e in errores) lista.Add(new Label { Text = "•  " + TextoDeCalificaciones.ErrorTactil(e), FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap });
            _estado.Add(lista);
        }

        var texto = enCurso ? "Guardando…" : _fase == Fase.Pendiente ? "Reintentar" : "Confirmar ajuste";
        var boton = ExamenUi.Accion(texto, Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(PanelDeAjuste), "Confirmar", ConfirmarAsync), null, "ajuste-confirmar", 56, margen: false);
        boton.Vista.HorizontalOptions = LayoutOptions.Start;
        // Deshabilitado mientras haya errores de forma (puntuación fuera de 0–100, más de dos decimales o motivo vacío), mientras se guarda o si la calificación ya no se puede ajustar.
        Ds.Habilitar(boton.Boton, errores.Count == 0 && !enCurso && GradebookTexto.PuedeAjustar(_c));
        _estado.Add(boton.Vista);
    }

    // ---------------------------------------------------------------------------------------------- confirmar

    private async Task ConfirmarAsync()
    {
        if (_fase == Fase.Guardando || Errores().Count > 0 || !GradebookTexto.PuedeAjustar(_c)) return;
        var puntaje = GradebookTexto.LeerPuntaje(_teclado.Texto).Valor!.Value;
        var motivo = _motivo.Motivo!;
        // La misma firma = el mismo intento: reintentar tras perder la señal reutiliza la solicitud. Cambiar el valor, el motivo o la versión leída es otra operación.
        var firma = $"ajuste|{_c.Id}|{_c.Version}|{GradebookTexto.Puntaje(puntaje)}|{motivo}";
        var peticion = new PeticionDeAjuste(puntaje, motivo, _c.Version, _solicitud.Para(firma));

        _fase = Fase.Guardando;
        _teclado.Habilitado = false;
        PintarEstado();
        RespuestaDeAjuste respuesta;
        try { respuesta = await _ajustar(peticion); }
        finally { _teclado.Habilitado = true; }

        _texto = respuesta.Texto;
        switch (respuesta.Resultado)
        {
            case ResultadoDeAjuste.Confirmado:
                _solicitud.Soltar();
                _fase = Fase.Confirmado;
                _limpiando = true;
                try { _teclado.Limpiar(); _motivo.Limpiar(); }
                finally { _limpiando = false; }
                break;
            case ResultadoDeAjuste.SinConexion:
                _fase = Fase.Pendiente;
                break;
            case ResultadoDeAjuste.Conflicto:
                _fase = Fase.Conflicto;      // lo escrito se conserva: la solicitud nueva la estrena la próxima confirmación (otra versión, otra firma)
                break;
            default:
                _fase = Fase.Rechazado;
                break;
        }
        PintarEstado();
    }
}
