using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>Lo que la tarjeta pide guardar: un puntaje a mano o los criterios de la rúbrica, con el comentario y la <c>solicitud_id</c> de ESTE intento de guardar.</summary>
internal sealed record PeticionDeRevision(string PreguntaRef, decimal? Puntaje, IReadOnlyList<CriterioPuntuado>? Criterios, string? Comentario, bool YaPuntuada, string SolicitudId, string? MotivoPrevio);

internal enum ResultadoDeGuardado { Guardado, SinConexion, Rechazado, Cancelado }

/// <summary>Cómo terminó un guardado. <c>Motivo</c> es el que se usó (si hizo falta uno), para reutilizarlo al reintentar sin volver a preguntar.</summary>
internal sealed record RespuestaDeGuardado(ResultadoDeGuardado Resultado, string? Texto = null, string? Motivo = null);

/// <summary>
/// Un reactivo que requiere la revisión del profesor (respuesta abierta, dibujo, entrega): el enunciado, lo que respondió el alumno, la forma, su estado (pendiente o revisada,
/// con texto y con tono) y cómo se puntúa: con los criterios de la rúbrica de la biblioteca (un control por criterio y el total en vivo; deben ir TODOS) o, si no hay rúbrica,
/// en pasos de 0 a 100 % de lo que vale. Debajo, el comentario pedagógico con frases que se tocan y un campo opcional, y el botón de guardar.
///
/// <b>Idempotencia.</b> Cada intento de guardar lleva una <c>solicitud_id</c>. Si el guardado no llega al nodo, el botón pasa a «Reintentar» y reutiliza LA MISMA solicitud (y el
/// mismo motivo): el nodo no duplica la revisión. Cambiar el valor o el comentario es otra operación y estrena solicitud. Nunca se muestra como guardado lo que no llegó.
///
/// La tarjeta vive mientras dura la pantalla: su campo de texto no cambia de contenedor (WinUI no lo permite); lo que cambia se repinta en zonas propias.
/// </summary>
internal sealed class TarjetaDeReactivo : ContentView
{
    private enum Fase { Libre, Guardando, PendienteDeConfirmacion, Rechazado }

    private readonly string _intentoId;
    private readonly int _numero;
    private readonly Func<PeticionDeRevision, Task<RespuestaDeGuardado>> _guardar;
    private readonly SolicitudReintentable _solicitud = new();
    private readonly Dictionary<string, decimal> _criterios = [];
    private readonly VerticalStackLayout _cabecera = new() { Spacing = 6 };
    private readonly VerticalStackLayout _respuesta = new() { Spacing = 6 };
    private readonly VerticalStackLayout _puntuacion = new() { Spacing = 10 };
    private readonly VerticalStackLayout _pie = new() { Spacing = 8 };
    private readonly SelectorDeFrases _comentario;

    private ReactivoParaRevisar _fila;
    private decimal? _manual;
    private Fase _fase = Fase.Libre;
    private string? _textoDeFase;
    private string? _motivoDelIntento;
    private bool _guardadoReciente;

    public TarjetaDeReactivo(string intentoId, int numero, ReactivoParaRevisar fila, Func<PeticionDeRevision, Task<RespuestaDeGuardado>> guardar)
    {
        _intentoId = intentoId;
        _numero = numero;
        _fila = fila;
        _guardar = guardar;
        _comentario = new SelectorDeFrases(FrasesDeCalificaciones.ComentariosDeRevision, $"revision-{fila.PreguntaRef}-comentario", "Escribe un comentario (opcional)");
        _comentario.Cambio += (_, _) => AlCambiarLoElegido();

        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(_cabecera);
        pila.Add(_respuesta);
        pila.Add(Ds.Separador());
        pila.Add(_puntuacion);
        pila.Add(EstudioUi.Eyebrow("COMENTARIO PARA EL ESTUDIANTE (OPCIONAL)"));
        pila.Add(_comentario);
        pila.Add(_pie);
        Content = ExamenUi.Tarjeta(pila);
        AutomationId = $"revision-reactivo-{fila.PreguntaRef}";
        Actualizar(fila, reiniciarSeleccion: true);
    }

    public string PreguntaRef => _fila.PreguntaRef;

    /// <summary>
    /// El nodo volvió a mandar el reactivo. Con <paramref name="reiniciarSeleccion"/> (la primera vez y tras un guardado confirmado) el puntaje elegido pasa a ser el que el nodo tiene; si no,
    /// lo que el profesor tocó y todavía no guardó se conserva.
    /// </summary>
    public void Actualizar(ReactivoParaRevisar fila, bool reiniciarSeleccion)
    {
        _fila = fila;
        if (reiniciarSeleccion)
        {
            // Lo elegido pasa a ser lo que el nodo tiene. Los criterios que se tocaron se conservan: ya están guardados y el nodo no devuelve el desglose.
            _manual = fila.PuntajeActual;
            _fase = Fase.Libre;
            _textoDeFase = null;
        }
        Pintar();
    }

    /// <summary>Un guardado confirmado: el nodo ya tiene el valor y el comentario. Se suelta la solicitud y se limpia el comentario escrito.</summary>
    public void MarcarGuardado()
    {
        _solicitud.Soltar();
        _motivoDelIntento = null;
        _comentario.Limpiar();            // avisa de un cambio: la marca de «guardado» se pone DESPUÉS
        _guardadoReciente = true;
    }

    // ------------------------------------------------------------------------------------------ lo que hay

    private decimal? Maximo
    {
        get
        {
            if (_fila.PuntajeMaximo is { } max) return max;
            if (_fila.Rubrica?.Puntos is { } puntos) return puntos;
            return _fila.Rubrica is { Criterios.Count: > 0 } r ? PuntuacionDeRevision.MaximoDeRubrica(r.Criterios) : null;
        }
    }

    private bool YaPuntuada => _fila.Revisada || _fila.PuntajeActual is not null;

    private bool ConRubrica => _fila.Rubrica is { Criterios.Count: > 0 };

    /// <summary>¿Hay algo que guardar? Una elección completa que difiere de lo guardado, o la misma con un comentario nuevo, o algo que todavía no se asentó.</summary>
    private bool PuedeGuardar()
    {
        var hayComentario = !string.IsNullOrWhiteSpace(_comentario.Texto);
        if (ConRubrica)
        {
            if (!PuntuacionDeRevision.Completa(_fila.Rubrica!.Criterios, _criterios)) return false;
            return hayComentario || !_fila.Revisada || PuntuacionDeRevision.Total(_criterios.Values) != _fila.PuntajeActual;
        }
        return _manual is not null && (hayComentario || !_fila.Revisada || _manual != _fila.PuntajeActual);
    }

    private PeticionDeRevision? Peticion()
    {
        var comentario = _comentario.Texto;
        if (ConRubrica)
        {
            if (PuntuacionDeRevision.Armar(_fila.Rubrica!.Criterios, _criterios) is not { } criterios) return null;
            var firma = PuntuacionDeRevision.FirmaRubrica(_intentoId, _fila.PreguntaRef, criterios, comentario, null);
            if (!_solicitud.EsReintento(firma)) _motivoDelIntento = null;     // otra operación: el motivo, si hace falta, se vuelve a pedir
            return new PeticionDeRevision(_fila.PreguntaRef, null, criterios, comentario, YaPuntuada, _solicitud.Para(firma), _motivoDelIntento);
        }
        if (_manual is not { } puntaje) return null;
        var firmaManual = PuntuacionDeRevision.FirmaManual(_intentoId, _fila.PreguntaRef, puntaje, comentario, null);
        if (!_solicitud.EsReintento(firmaManual)) _motivoDelIntento = null;
        return new PeticionDeRevision(_fila.PreguntaRef, puntaje, null, comentario, YaPuntuada, _solicitud.Para(firmaManual), _motivoDelIntento);
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Pintar()
    {
        PintarCabecera();
        PintarRespuesta();
        PintarPuntuacion();
        PintarPie();
    }

    private void PintarCabecera()
    {
        _cabecera.Clear();
        var fila = ExamenUi.Fila();
        fila.Add(CalificacionesUi.PildoraEnFila($"Pregunta {_numero}", Matiz.Neutro, 13));
        // El estado del reactivo, con texto y con tono: pendiente (falta tu puntaje) o revisada (ya tiene tu puntaje).
        if (_fila.Pendiente && !_fila.Revisada) fila.Add(CalificacionesUi.PildoraEnFila("Pendiente · falta tu puntaje", Matiz.Violeta, 13));
        else if (YaPuntuada) fila.Add(CalificacionesUi.PildoraEnFila($"Revisada · {GradebookTexto.Puntaje(_fila.PuntajeActual)} de {GradebookTexto.Puntaje(Maximo)}", Matiz.Exito, 13));
        else fila.Add(CalificacionesUi.PildoraEnFila("Sin puntaje", Matiz.Neutro, 13));
        fila.Add(CalificacionesUi.PildoraEnFila(GradebookTexto.Forma(_fila.Forma), Matiz.Gris, 13));
        _cabecera.Add(fila);
        _cabecera.Add(new Label { Text = string.IsNullOrWhiteSpace(_fila.Enunciado) ? "Pregunta sin enunciado" : _fila.Enunciado, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (Maximo is { } max) _cabecera.Add(Ds.Secundario($"Vale {GradebookTexto.Puntaje(max)} {(max == 1 ? "punto" : "puntos")}", 13));
    }

    private void PintarRespuesta()
    {
        _respuesta.Clear();
        _respuesta.Add(EstudioUi.Eyebrow("RESPUESTA DEL ESTUDIANTE"));
        _respuesta.Add(ExamenUi.Zona(new Label
        {
            Text = RespuestaDeRevision.Para(_fila), FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = _fila.Respondida || _fila.Evidencias is { Count: > 0 } ? Ds.Tinta : Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap,
        }, ExamenUi.FondoNeutro));
        // Dibujo, audio o entrega: sólo su referencia (los archivos viven en otro módulo; aquí no se pintan).
        foreach (var linea in RespuestaDeRevision.Evidencias(_fila))
            _respuesta.Add(new Label { Text = linea, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(_fila.Comentario)) _respuesta.Add(Ds.Secundario($"Tu comentario guardado: {_fila.Comentario}", 14));
    }

    private void PintarPuntuacion()
    {
        _puntuacion.Clear();
        if (ConRubrica) PintarRubrica();
        else PintarPasos();
    }

    /// <summary>Sin rúbrica: 0, 25, 50, 75 y 100 % de lo que vale, como en el expediente del examen.</summary>
    private void PintarPasos()
    {
        if (Maximo is not { } max || max <= 0)
        {
            _puntuacion.Add(Ds.Secundario("No se sabe cuánto vale esta pregunta, así que no se puede puntuar desde aquí.", 14));
            return;
        }
        _puntuacion.Add(new Label { Text = "Puntúa esta respuesta", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        var fichas = EstudioUi.Envolver();
        foreach (var paso in PuntuacionDeRevision.Porcentuales(max))
        {
            var valor = paso.Valor;
            var texto = paso.Rotulo == "0" ? "0" : $"{paso.Rotulo} · {GradebookTexto.Puntaje(valor)}";
            fichas.Add(EstudioUi.Chip(texto, _manual == valor, CalificacionesUi.Seguro(nameof(TarjetaDeReactivo), "Puntuar", () => ElegirManualAsync(valor)), $"revision-{_fila.PreguntaRef}-puntaje-{paso.Rotulo.Replace(" ", string.Empty)}", 56));
        }
        _puntuacion.Add(fichas);
        _puntuacion.Add(Ds.Secundario(_manual is { } actual ? $"Elegiste {GradebookTexto.Puntaje(actual)} de {GradebookTexto.Puntaje(max)}." : "Elige un puntaje para poder guardar.", 13));
    }

    /// <summary>Con rúbrica: un control por criterio con sus puntos máximos y el total calculado en vivo. Deben ir todos los criterios.</summary>
    private void PintarRubrica()
    {
        var rubrica = _fila.Rubrica!;
        _puntuacion.Add(new Label { Text = "Rúbrica", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        if (!string.IsNullOrWhiteSpace(rubrica.RespuestaModelo)) _puntuacion.Add(Ds.Secundario($"Respuesta esperada: {rubrica.RespuestaModelo}", 14));
        foreach (var criterio in rubrica.Criterios)
        {
            var bloque = new VerticalStackLayout { Spacing = 4 };
            bloque.Add(new Label { Text = criterio.Criterio, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            bloque.Add(Ds.Secundario($"Vale {GradebookTexto.Puntaje(criterio.PuntosMax)} {(criterio.PuntosMax == 1 ? "punto" : "puntos")}", 13));
            var fichas = EstudioUi.Envolver();
            foreach (var paso in PuntuacionDeRevision.Pasos(criterio.PuntosMax))
            {
                var valor = paso;
                var criterioId = criterio.Id;
                fichas.Add(EstudioUi.Chip(PuntuacionDeRevision.Rotulo(valor, criterio.PuntosMax), _criterios.TryGetValue(criterio.Id, out var elegido) && elegido == valor,
                    CalificacionesUi.Seguro(nameof(TarjetaDeReactivo), "Criterio", () => ElegirCriterioAsync(criterioId, valor)),
                    $"revision-{_fila.PreguntaRef}-{criterio.Id}-{GradebookTexto.Puntaje(valor).Replace(',', '_')}", 52));
            }
            bloque.Add(fichas);
            _puntuacion.Add(bloque);
        }
        var maximo = PuntuacionDeRevision.MaximoDeRubrica(rubrica.Criterios);
        var faltan = rubrica.Criterios.Count(c => !_criterios.ContainsKey(c.Id));
        var total = $"Total: {GradebookTexto.Puntaje(PuntuacionDeRevision.Total(_criterios.Values))} de {GradebookTexto.Puntaje(maximo)}";
        _puntuacion.Add(new Label { Text = faltan == 0 ? total : $"{total} · faltan {(faltan == 1 ? "1 criterio" : $"{faltan} criterios")} por puntuar", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = faltan == 0 ? ExamenUi.TintaExito : ExamenUi.TintaVioleta, LineBreakMode = LineBreakMode.WordWrap });
    }

    private void PintarPie()
    {
        _pie.Clear();
        var puede = PuedeGuardar();
        switch (_fase)
        {
            case Fase.Guardando:
                _pie.Add(Ds.Secundario("Guardando…", 14));
                var guardando = ExamenUi.Accion("Guardando…", Ds.Rango.Primary, () => Task.CompletedTask, null, $"revision-{_fila.PreguntaRef}-guardar", 56, margen: false);
                guardando.Vista.HorizontalOptions = LayoutOptions.Start;
                Ds.Habilitar(guardando.Boton, false);
                _pie.Add(guardando.Vista);
                return;
            case Fase.PendienteDeConfirmacion:
                // Sin conexión: NO se muestra como confirmado. La misma solicitud se reenvía al reintentar.
                _pie.Add(ExamenUi.Aviso("Pendiente de confirmación", _textoDeFase ?? "No se pudo conectar con el aula: nada se guardó todavía. Reintentar no duplica la revisión.", Tono.Ambar));
                var reintentar = ExamenUi.Accion("Reintentar", Ds.Rango.Primary, GuardarAsync, null, $"revision-{_fila.PreguntaRef}-guardar", 56, margen: false);
                reintentar.Vista.HorizontalOptions = LayoutOptions.Start;
                _pie.Add(reintentar.Vista);
                return;
            case Fase.Rechazado:
                _pie.Add(ExamenUi.Aviso("No se guardó", _textoDeFase, Tono.Ambar));
                break;
        }
        if (_guardadoReciente && !puede) _pie.Add(CalificacionesUi.Pildora("Puntaje guardado", Matiz.Exito, 13));
        var guardar = ExamenUi.Accion(YaPuntuada ? "Guardar el cambio" : "Guardar puntaje", Ds.Rango.Primary, GuardarAsync, null, $"revision-{_fila.PreguntaRef}-guardar", 56, margen: false);
        guardar.Vista.HorizontalOptions = LayoutOptions.Start;
        Ds.Habilitar(guardar.Boton, puede);
        _pie.Add(guardar.Vista);
        if (!puede && !_guardadoReciente) _pie.Add(Ds.Secundario(ConRubrica ? "Puntúa todos los criterios para poder guardar." : "Elige un puntaje para poder guardar.", 13));
    }

    // ----------------------------------------------------------------------------------------- lo que se toca

    private void AlCambiarLoElegido()
    {
        // Cambiar lo que se iba a guardar es otra operación: se sale del «pendiente de confirmación» (la solicitud nueva la estrena Peticion()).
        if (_fase is Fase.PendienteDeConfirmacion or Fase.Rechazado) { _fase = Fase.Libre; _textoDeFase = null; }
        _guardadoReciente = false;
        PintarPie();
    }

    private Task ElegirManualAsync(decimal valor)
    {
        _manual = valor;
        AlCambiarLoElegido();
        PintarPuntuacion();
        return Task.CompletedTask;
    }

    private Task ElegirCriterioAsync(string criterioId, decimal valor)
    {
        _criterios[criterioId] = valor;
        AlCambiarLoElegido();
        PintarPuntuacion();
        return Task.CompletedTask;
    }

    private async Task GuardarAsync()
    {
        if (_fase == Fase.Guardando) return;
        var peticion = Peticion();
        if (peticion is null) return;
        _fase = Fase.Guardando;
        PintarPie();
        var respuesta = await _guardar(peticion);
        _motivoDelIntento = respuesta.Motivo ?? _motivoDelIntento;
        switch (respuesta.Resultado)
        {
            case ResultadoDeGuardado.Guardado:
                // La pantalla vuelve a leer la revisión y llama a Actualizar con lo que el nodo tiene; aquí sólo se cierra el intento.
                MarcarGuardado();
                _fase = Fase.Libre;
                break;
            case ResultadoDeGuardado.SinConexion:
                _fase = Fase.PendienteDeConfirmacion;
                _textoDeFase = respuesta.Texto;
                break;
            case ResultadoDeGuardado.Rechazado:
                _fase = Fase.Rechazado;
                _textoDeFase = respuesta.Texto;
                break;
            default:      // Cancelado: no se eligió motivo; no se hizo nada y la próxima vez es otra operación
                _fase = Fase.Libre;
                _solicitud.Soltar();
                _motivoDelIntento = null;
                break;
        }
        PintarPie();
    }
}
