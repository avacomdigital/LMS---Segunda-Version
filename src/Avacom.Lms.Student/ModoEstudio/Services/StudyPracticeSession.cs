using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// Una práctica real (BR-055: aparte de la evaluación formal). Con el aula a la vista cada respuesta se califica en ≤ 2 s y el veredicto vuelve
/// con su retroalimentación; sin ella la respuesta se guarda en la tableta y sale por la cola cifrada, y se califica al integrarse (D-6: la clave
/// de respuesta nunca está en la tableta). En los dos casos LA RESPUESTA SE GUARDA PRIMERO en la tableta. La secuencia de cada respuesta crece
/// siempre (segundos del reloj del nodo o la anterior + 1): si el alumno cambia una respuesta, gana la última (INV-013).
/// </summary>
internal sealed class StudyPracticeSession : IStudyPracticeSession
{
    private static readonly TimeSpan TopeDelAula = TimeSpan.FromSeconds(6);

    private readonly StudyModeService _servicio;
    private readonly string _asignacionId;
    private readonly string _objetoRef;
    private readonly string? _practicaId;
    private readonly Dictionary<string, StudyAnswerVerdict> _veredictos = new(StringComparer.Ordinal);
    private readonly HashSet<string> _respondidas = new(StringComparer.Ordinal);
    private bool _sinAula;
    private int _ultimaSecuencia;

    public StudyPracticeSession(StudyModeService servicio, string asignacionId, ObjetoAula actividad, string objetoRef, int numero, string? practicaId,
                                Dictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)> previas)
    {
        _servicio = servicio;
        _asignacionId = asignacionId;
        _objetoRef = objetoRef;
        _practicaId = practicaId;
        Activity = actividad;
        Title = actividad.Titulo;
        Number = numero;
        Previous = previas;
        foreach (var (pregunta, (_, veredicto)) in previas)
        {
            _respondidas.Add(pregunta);
            if (veredicto is not null) _veredictos[pregunta] = veredicto;
        }
        _ultimaSecuencia = servicio.LeerTarea(asignacionId).Practicas
            .Where(p => p.ObjetoRef == objetoRef && p.Numero == numero)
            .SelectMany(p => p.Respuestas.Values).Select(r => r.Secuencia).DefaultIfEmpty(0).Max();
    }

    public string Title { get; }
    public ObjetoAula Activity { get; }
    public int Number { get; }
    public IReadOnlyDictionary<string, (JsonElement Answer, StudyAnswerVerdict? Verdict)> Previous { get; }

    /// <summary>Hay aula y no se ha caído a mitad de la práctica.</summary>
    public bool CanGradeNow => _practicaId is not null && !_sinAula;

    private int TotalPreguntas => Activity.Preguntas?.Count ?? 0;

    internal static StudyAnswerVerdict Traducir(VeredictoEstudio v) =>
        new(v.PreguntaRef, v.Correcta, v.Pendiente, v.Retroalimentacion ?? []);

    private int SiguienteSecuencia()
    {
        _ultimaSecuencia = Math.Max(_ultimaSecuencia + 1, (int)(RelojNodo.AhoraMs / 1000));
        return _ultimaSecuencia;
    }

    public async Task<StudyAnswerVerdict> SubmitAsync(PreguntaAula question, JsonElement answer, CancellationToken ct = default)
    {
        var respuesta = answer.Clone();
        var secuencia = SiguienteSecuencia();
        var capturada = RelojNodo.AhoraMs;
        _respondidas.Add(question.PreguntaRef);

        // 1) En la tableta primero: si la app se cierra ahora, la respuesta no se pierde.
        _servicio.GuardarPractica(_asignacionId, _objetoRef, Number, TotalPreguntas, p => p with
        {
            Respuestas = new Dictionary<string, RespuestaLocal>(p.Respuestas) { [question.PreguntaRef] = new RespuestaLocal(respuesta, secuencia, null) },
        });

        // 2) Con el aula a la vista: se califica y vuelve la retroalimentación.
        if (CanGradeNow)
        {
            var api = _servicio.Local.Api;
            try
            {
                using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
                tope.CancelAfter(TopeDelAula);
                var acuse = await api.ResponderAsync(_servicio.Local.Dispositivo, _practicaId!,
                    [new RespuestaPractica(question.PreguntaRef, respuesta, secuencia, capturada)], false, _servicio.Alumno, tope.Token);
                if (acuse is not null)
                {
                    if (acuse.Veredictos?.FirstOrDefault(x => x.PreguntaRef == question.PreguntaRef) is { } v)
                    {
                        var traducido = Traducir(v);
                        _veredictos[question.PreguntaRef] = traducido;
                        GuardarVeredicto(question.PreguntaRef, respuesta, secuencia, v);
                        return traducido;
                    }
                    return Pendiente(question.PreguntaRef);   // el aula la guardó; la biblioteca la calificará después
                }
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { /* el aula no contestó a tiempo */ }
            _sinAula = true;
        }

        // 3) Sin aula (o desde que se cayó): a la cola cifrada, que sale sola en cuanto la vea.
        _servicio.Encolar(TiposEventoEstudio.RespuestaEnviada, new
        {
            asignacion_id = _asignacionId,
            objeto_ref = _objetoRef,
            intento_numero = Number,
            pregunta_ref = question.PreguntaRef,
            respuesta,
            secuencia_respuesta = secuencia,
        });
        return Pendiente(question.PreguntaRef);
    }

    private static StudyAnswerVerdict Pendiente(string preguntaRef) => new(preguntaRef, null, true, []);

    private void GuardarVeredicto(string preguntaRef, JsonElement respuesta, int secuencia, VeredictoEstudio veredicto) =>
        _servicio.GuardarPractica(_asignacionId, _objetoRef, Number, TotalPreguntas, p => p with
        {
            Respuestas = new Dictionary<string, RespuestaLocal>(p.Respuestas) { [preguntaRef] = new RespuestaLocal(respuesta, secuencia, veredicto) },
        });

    public async Task<StudyPracticeResult> FinishAsync(CancellationToken ct = default)
    {
        // Terminar la práctica cuenta como haber atendido su bloque (D-4): se marca ya en la tableta.
        _servicio.RegistrarBloquePractica(_asignacionId, _objetoRef);

        if (CanGradeNow)
        {
            var api = _servicio.Local.Api;
            try
            {
                using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
                tope.CancelAfter(TopeDelAula);
                var acuse = await api.TerminarPracticaAsync(_servicio.Local.Dispositivo, _practicaId!, _servicio.Alumno, tope.Token);
                if (acuse is not null)
                {
                    var resultado = acuse.Resultado is { } r ? DelAula(r) : Local();
                    _servicio.GuardarPractica(_asignacionId, _objetoRef, Number, TotalPreguntas, p => p with
                    {
                        Estado = "terminada", Sincronizada = true, Correctas = acuse.Resultado?.Correctas ?? resultado.Correct,
                    });
                    _servicio.Refrescar(_asignacionId);
                    return resultado;
                }
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { /* sin aula */ }
            _sinAula = true;
        }

        _servicio.Encolar(TiposEventoEstudio.PracticaTerminada, new { asignacion_id = _asignacionId, objeto_ref = _objetoRef, intento_numero = Number });
        var local = Local();
        _servicio.GuardarPractica(_asignacionId, _objetoRef, Number, TotalPreguntas, p => p with
        {
            Estado = "terminada", Correctas = local.Ungraded == 0 ? local.Correct : null,
        });
        _servicio.Refrescar(_asignacionId);
        return local;
    }

    private int NumeroDe(string preguntaRef, int alternativo)
    {
        var i = (Activity.Preguntas ?? []).ToList().FindIndex(p => p.PreguntaRef == preguntaRef);
        return i >= 0 ? i + 1 : alternativo;
    }

    private string? EnunciadoDe(string preguntaRef) => Activity.Preguntas?.FirstOrDefault(p => p.PreguntaRef == preguntaRef)?.Enunciado;

    private static string MensajePorPorcentaje(int correctas, int total) =>
        total <= 0 ? "¡Buen trabajo!" : correctas * 100 >= total * 85 ? "¡Muy bien!" : correctas * 100 >= total * 60 ? "¡Buen avance!" : "Sigue practicando: puedes intentarlo otra vez.";

    /// <summary>El resultado que calculó el aula al terminar («7 de 8 correctas»). Nunca «nota» ni «evaluación».</summary>
    private StudyPracticeResult DelAula(ResultadoPractica r)
    {
        var revision = (r.Revision ?? []).Select((x, i) =>
            new StudyPracticeReview(x.PreguntaRef, NumeroDe(x.PreguntaRef, i + 1), EnunciadoDe(x.PreguntaRef), x.Correcta, x.Retroalimentacion ?? [])).ToList();
        return new StudyPracticeResult(r.Correctas, r.Total, string.IsNullOrWhiteSpace(r.Mensaje) ? MensajePorPorcentaje(r.Correctas, r.Total) : r.Mensaje!, r.SinCalificar, revision);
    }

    /// <summary>Lo que se sabe en la tableta: lo calificado hasta ahora y lo que espera al aula. Si nada está calificado, «Práctica guardada».</summary>
    private StudyPracticeResult Local()
    {
        var preguntas = Activity.Preguntas ?? [];
        var revision = preguntas.Select((p, i) =>
        {
            var respondida = _respondidas.Contains(p.PreguntaRef);
            _veredictos.TryGetValue(p.PreguntaRef, out var v);
            return new StudyPracticeReview(p.PreguntaRef, i + 1, p.Enunciado,
                v is { Known: true } ? v.Correct : null,
                v?.Feedback ?? (respondida ? [] : ["Sin responder."]));
        }).ToList();
        var correctas = revision.Count(r => r.Correct == true);
        var sinCalificar = preguntas.Count(p => _respondidas.Contains(p.PreguntaRef) && !(_veredictos.TryGetValue(p.PreguntaRef, out var v) && v.Known));
        var mensaje = sinCalificar > 0
            ? "Guardamos tu práctica en la tableta. Se calificará cuando vuelva a ver el aula."
            : MensajePorPorcentaje(correctas, preguntas.Count);
        return new StudyPracticeResult(correctas, preguntas.Count, mensaje, sinCalificar, revision);
    }
}
