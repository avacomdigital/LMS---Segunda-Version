using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

// Lo que se hace con un intento YA ENTREGADO: revisar sus respuestas, puntuar lo que la biblioteca no califica sola, publicar la calificación, volver a calificar
// y —sólo aquí, nunca en el panel— anular. Todo con toques: los puntajes son pasos de 0 a 100 % del máximo y los motivos, frases prehechas.
public partial class ExamenExpedientePage
{
    private static readonly double[] PasosDePuntaje = [0, 0.25, 0.5, 0.75, 1];

    private bool _verRevision;
    private RevisionDeIntento? _revision;

    // ------------------------------------------------------------------------------------------ decisiones

    private View Decisiones(ExpedienteDeIntento exp)
    {
        var i = exp.Intento;
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Qué puedes hacer con este intento"));
        pila.Add(Ds.Secundario(i.Estado switch
        {
            EstadosIntento.EnRevision => "Tiene respuestas que sólo tú puedes puntuar. Cuando todas tengan puntaje, publica la calificación.",
            EstadosIntento.Calificado => "Está calificado. Si algo no te convence, puedes cambiar un puntaje (queda el valor anterior y el nuevo en la bitácora).",
            EstadosIntento.Anulado => "Este intento está anulado: no cuenta para nada. Sus respuestas se conservan como evidencia.",
            _ => _extra?.Intento.CalificacionPendiente == true
                ? "Se entregó, pero la biblioteca no estaba disponible para calificarlo. Cuando vuelva, califícalo de nuevo."
                : "Se entregó. Lo que se califica solo ya quedó calificado.",
        }, 14));

        var fila = ExamenUi.Fila();
        fila.Add(ExamenUi.Accion(_verRevision ? "Ocultar respuestas" : "Revisar respuestas", Ds.Rango.Secondary, AlternarRevisionAsync, null, "expediente-revisar").Vista);
        if (i.Estado == EstadosIntento.EnRevision)
            fila.Add(ExamenUi.Accion("Publicar calificación", Ds.Rango.Primary, PublicarAsync, null, "expediente-publicar").Vista);
        if (_extra?.Intento.CalificacionPendiente == true)
            fila.Add(ExamenUi.Accion("Calificar de nuevo", Ds.Rango.Secondary, RecalificarAsync, null, "expediente-recalificar").Vista);
        pila.Add(fila);

        // Anular: la única decisión que no se deshace. Discreta (sin relleno de color), explicada y sólo si el intento ya se entregó.
        if (i.Estado is EstadosIntento.Entregado or EstadosIntento.EnRevision or EstadosIntento.Calificado)
        {
            pila.Add(Ds.Separador());
            pila.Add(Ds.Secundario("Anular es una decisión tuya, con un motivo, y queda registrada con tu nombre. Nadie más la toma: el sistema nunca anula por sí solo.", 14));
            var anular = ExamenUi.Accion("Anular este intento", Ds.Rango.Quiet, AnularAsync, null, "expediente-anular");
            anular.Vista.HorizontalOptions = LayoutOptions.Start;
            pila.Add(anular.Vista);
        }
        return ExamenUi.Tarjeta(pila);
    }

    private async Task AlternarRevisionAsync()
    {
        _verRevision = !_verRevision;
        if (!_verRevision) _revision = null;
        await CargarAsync(forzar: true);
        if (_verRevision && _revision is null && _exp is not null)
        {
            var api = Sesion.Evaluacion;
            Avisar("No se pudieron leer las respuestas", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        }
    }

    private async Task PublicarAsync()
    {
        var api = Sesion.Evaluacion;
        var r = await api.PublicarAsync(Actor, IntentoId);
        // reactivos_pendientes: quedan respuestas sin puntuar. El nodo lo dice con su número; se muestra sin alarma.
        if (r is null) Avisar("Todavía no se puede publicar", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else Avisar("Calificación publicada", r.Porcentaje is { } pct ? $"Resultado: {ExamenTexto.Porcentaje(pct)}." : null, Tono.Exito);
        await CargarAsync(forzar: true);
    }

    private async Task RecalificarAsync()
    {
        var api = Sesion.Evaluacion;
        if (await api.RecalificarAsync(Actor, IntentoId)) Avisar("Se volvió a calificar", null, Tono.Exito);
        else Avisar("No se pudo calificar", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        await CargarAsync(forzar: true);
    }

    /// <summary>
    /// INV-018: anular es la única flecha que el sistema nunca toma. Una persona, con un motivo de la lista, y queda con su nombre. Tocar el motivo es la
    /// confirmación; la hoja no vuelve a preguntar.
    /// </summary>
    private async Task AnularAsync()
    {
        var nombre = _exp?.Intento.AlumnoRotulo ?? "este alumno";
        var motivo = await _hoja.PedirMotivoAsync($"¿Por qué anulas el intento de {nombre}?",
            "Es la única decisión que no se puede deshacer. Quedará registrado que la tomaste tú, con tu nombre y este motivo.", ExamenTexto.MotivosAnular);
        if (motivo is null) return;
        var api = Sesion.Evaluacion;
        if (await api.AnularAsync(Actor, IntentoId, motivo)) Avisar("Intento anulado", $"Anulado por {ExamenTexto.Persona(Actor)} · {motivo}", Tono.Info);
        else Avisar("No se pudo anular el intento", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        await CargarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------------ revisión de respuestas

    private View TarjetaDeRevision(ExpedienteDeIntento exp)
    {
        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(ExamenUi.Seccion("Respuestas del alumno"));
        if (_revision is null)
        {
            pila.Add(Ds.Secundario("Leyendo las respuestas…", 15));
            return ExamenUi.Tarjeta(pila);
        }
        var puedePuntuar = exp.Intento.Estado is EstadosIntento.EnRevision or EstadosIntento.Calificado;
        var numero = 0;
        foreach (var fila in _revision.Filas)
        {
            numero++;
            if (numero > 1) pila.Add(Ds.Separador());
            pila.Add(Pregunta(numero, fila, puedePuntuar));
        }
        if (_revision.Filas.Count == 0) pila.Add(Ds.Secundario("Este intento no tiene preguntas que mostrar.", 15));
        return ExamenUi.Tarjeta(pila);
    }

    private View Pregunta(int numero, PreguntaDeRevision fila, bool puedePuntuar)
    {
        var pregunta = fila.Pregunta;
        var veredicto = VeredictoLeido.De(fila.Veredicto);
        var propio = PuntajeDelProfesor.De(fila.Revision);
        var maximo = veredicto?.PuntajeMaximo ?? pregunta.Puntos;
        var manual = veredicto is { RequiereCorreccionManual: true } or { Pendiente: true } || propio is not null;

        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = $"{numero}.  {pregunta.Enunciado}", FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        pila.Add(Ds.Secundario($"{pregunta.TipoLegible} · vale {RespuestaLegible.Puntos(maximo)} {(maximo == 1 ? "punto" : "puntos")}", 13));

        var respuesta = RespuestaLegible.De(pregunta, fila.Respuesta, fila.Respondida);
        var caja = new Label
        {
            Text = respuesta, FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = fila.Respondida ? Ds.Tinta : Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap,
        };
        pila.Add(ExamenUi.Zona(caja, ExamenUi.FondoNeutro));

        var resultado = ExamenUi.Fila();
        if (propio?.Puntaje is { } puesto)
            resultado.Add(ExamenUi.PildoraEnFila($"Puntuaste {RespuestaLegible.Puntos(puesto)} de {RespuestaLegible.Puntos(maximo)}", Tono.Exito, 13));
        else if (manual)
            resultado.Add(ExamenUi.PildoraEnFila($"Espera tu puntaje (máximo {RespuestaLegible.Puntos(maximo)})", Tono.Violeta, 13));
        else if (!fila.Respondida)
            resultado.Add(ExamenUi.PildoraEnFila($"No respondió · cuenta 0 de {RespuestaLegible.Puntos(maximo)}", Tono.Neutro, 13));
        else if (veredicto?.Correcta == true)
            resultado.Add(ExamenUi.PildoraEnFila($"Correcta · {RespuestaLegible.Puntos(veredicto.Puntaje)} de {RespuestaLegible.Puntos(maximo)}", Tono.Exito, 13));
        else if (veredicto?.Correcta == false)
            resultado.Add(ExamenUi.PildoraEnFila($"No es la respuesta esperada · {RespuestaLegible.Puntos(veredicto.Puntaje)} de {RespuestaLegible.Puntos(maximo)}", Tono.Gris, 13));
        else if (veredicto?.Puntaje is { } parcial)
            resultado.Add(ExamenUi.PildoraEnFila($"{RespuestaLegible.Puntos(parcial)} de {RespuestaLegible.Puntos(maximo)}", Tono.Neutro, 13));
        else
            resultado.Add(ExamenUi.PildoraEnFila("Sin calificar", Tono.Neutro, 13));
        pila.Add(resultado);

        // Los pasos de puntaje: sólo en lo que la biblioteca marcó para corrección manual, y sólo cuando el nodo acepta puntuar (revisión docente o ya calificado).
        if (manual && maximo is { } max and > 0)
        {
            if (!puedePuntuar)
            {
                pila.Add(Ds.Secundario("Se podrá puntuar cuando termine la calificación automática.", 13));
            }
            else
            {
                pila.Add(Ds.Secundario("Puntúa esta respuesta", 14));
                var fichas = EstudioUi.Envolver();
                foreach (var paso in PasosDePuntaje)
                {
                    var valor = Math.Round(max * paso, 4);
                    var activo = propio?.Puntaje is { } actual && Math.Abs(actual - valor) < 0.0001;
                    var rotulo = paso == 0 ? "0" : $"{(int)(paso * 100)} %";
                    fichas.Add(EstudioUi.Chip(rotulo, activo, () => PuntuarAsync(pregunta.PreguntaRef, valor, propio is not null), $"expediente-puntaje-{pregunta.PreguntaRef}-{(int)(paso * 100)}", 56));
                }
                pila.Add(fichas);
                if (propio?.Puntaje is { } hecho) pila.Add(Ds.Secundario($"Puntaje actual: {RespuestaLegible.Puntos(hecho)} de {RespuestaLegible.Puntos(max)}", 13));
            }
        }
        return pila;
    }

    private async Task PuntuarAsync(string preguntaRef, double puntaje, bool yaTienePuntaje)
    {
        string? motivo = null;
        if (yaTienePuntaje)
        {
            // Cambiar un puntaje ya puesto exige un motivo (DEC-022): se ofrece entre frases.
            motivo = await _hoja.PedirMotivoAsync("¿Por qué cambias el puntaje?", "Quedan el valor anterior y el nuevo en la bitácora.", ExamenTexto.MotivosCambiarPuntaje);
            if (motivo is null) return;
        }
        var api = Sesion.Evaluacion;
        var r = await api.PuntuarAsync(Actor, IntentoId, preguntaRef, puntaje, null, motivo);
        if (r is null) Avisar("No se pudo guardar el puntaje", ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), Tono.Ambar);
        else
        {
            var faltan = r.Pendientes?.Count ?? 0;
            Avisar("Puntaje guardado", faltan == 0 ? "Ya no queda nada por puntuar." : $"Quedan {ExamenTexto.Plural(faltan, "respuesta", "respuestas")} por puntuar.", Tono.Exito);
        }
        await CargarAsync(forzar: true);
    }
}
