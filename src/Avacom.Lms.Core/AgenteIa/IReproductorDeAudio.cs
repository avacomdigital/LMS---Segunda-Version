namespace Avacom.Lms.Core.AgenteIa;

/// <summary>
/// Reproduce el WAV de la voz del asistente en el equipo (paso 5 del contrato). La implementación depende de la plataforma (OPS: Windows) y vive en cada app; Core sólo conoce esta puerta.
/// Debe completar cuando termina el audio (o se cancela con <paramref name="ct"/>), lanzar si no pudo reproducir, y <see cref="Detener"/> debe cortar el sonido YA.
/// </summary>
public interface IReproductorDeAudio
{
    /// <param name="wav">Un WAV PCM completo y válido (Core ya lo comprobó).</param>
    /// <param name="duracionMs">Lo que dura: el reproductor lo usa como tope de espera por si el sistema nunca avisa que terminó (sin tarjeta de sonido, por ejemplo).</param>
    Task ReproducirAsync(byte[] wav, int duracionMs, CancellationToken ct);

    /// <summary>Corta lo que esté sonando. Seguro de llamar siempre, aunque no suene nada.</summary>
    void Detener();
}

/// <summary>Para las plataformas sin reproductor: el asistente responde por escrito y la voz se avisa como «no disponible», sin romper nada.</summary>
public sealed class SinReproductor : IReproductorDeAudio
{
    public Task ReproducirAsync(byte[] wav, int duracionMs, CancellationToken ct) => throw new NotSupportedException("Este equipo no tiene reproductor de audio para el asistente.");
    public void Detener() { }
}
