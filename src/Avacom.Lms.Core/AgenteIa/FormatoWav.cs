using System.Buffers.Binary;
using System.Text;

namespace Avacom.Lms.Core.AgenteIa;

/// <summary>Lo que se necesita saber de un WAV PCM (frecuencia, canales, bits, cuántas muestras y cuánto dura). Sirve para NO entregarle al reproductor algo que no es audio y para calcular su duración.</summary>
public sealed record FormatoWav(int Canales, int Frecuencia, int Bits, int Desde, int Largo)
{
    public int DuracionMs => (int)(Largo / (double)(Frecuencia * Canales * (Bits / 8)) * 1000);

    /// <summary>El formato, o null si los bytes no son un WAV PCM utilizable (cabecera RIFF/WAVE, bloque «fmt » PCM, bloque «data» con muestras).</summary>
    public static FormatoWav? Leer(ReadOnlySpan<byte> wav)
    {
        if (wav.Length < 44 || !wav[..4].SequenceEqual("RIFF"u8) || !wav.Slice(8, 4).SequenceEqual("WAVE"u8)) return null;
        int canales = 0, frecuencia = 0, bits = 0, formato = 0, pos = 12;
        while (pos + 8 <= wav.Length)
        {
            var id = Encoding.ASCII.GetString(wav.Slice(pos, 4));
            var tam = BinaryPrimitives.ReadUInt32LittleEndian(wav[(pos + 4)..]);
            if (id == "fmt ")
            {
                if (pos + 8 + 16 > wav.Length) return null;
                formato = BinaryPrimitives.ReadUInt16LittleEndian(wav[(pos + 8)..]);
                canales = BinaryPrimitives.ReadUInt16LittleEndian(wav[(pos + 10)..]);
                frecuencia = (int)BinaryPrimitives.ReadUInt32LittleEndian(wav[(pos + 12)..]);
                bits = BinaryPrimitives.ReadUInt16LittleEndian(wav[(pos + 22)..]);
            }
            else if (id == "data")
            {
                if (formato is not (1 or 0xFFFE) || canales < 1 || frecuencia < 8000 || bits is not (8 or 16 or 24 or 32)) return null;
                var largo = (int)Math.Min(tam, (uint)(wav.Length - (pos + 8)));
                largo -= largo % (canales * (bits / 8));           // sin muestras a medias
                return largo <= 0 ? null : new FormatoWav(canales, frecuencia, bits, pos + 8, largo);
            }
            pos += 8 + (int)Math.Min(tam, int.MaxValue / 2) + (int)(tam & 1);
        }
        return null;
    }
}
