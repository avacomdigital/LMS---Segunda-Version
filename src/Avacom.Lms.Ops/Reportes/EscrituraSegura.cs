using System.Security.Cryptography;
using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Cómo terminó el guardado. Si <see cref="Ok"/>, <see cref="RutaFinal"/> es el archivo ya con su nombre definitivo y <see cref="Sha256"/> el que se RELEYÓ de la unidad (no el que se
/// calculó al copiar). Si no, <see cref="Fallo"/> trae el motivo y qué decirle a la persona, y no queda nada en el destino: ni el archivo, ni el temporal (salvo que la unidad ya no
/// esté o no deje borrarlo, y entonces <see cref="Detalle"/> lo dice; el temporal tiene un nombre que empieza por un punto y termina en «.parte»).
/// </summary>
public sealed record ResultadoDeEscritura(bool Ok, string? RutaFinal, long Bytes, string? Sha256, FalloDeEscritura? Fallo)
{
    /// <summary>
    /// Para la bitácora y el soporte, NUNCA para la pantalla: el tipo y el código completo de la excepción que causó el fallo, qué no coincidió en una verificación, o si un temporal
    /// no se pudo borrar. Es lo que permite añadir a la tabla de <see cref="MotivosDeEscritura"/> un código que una unidad real devuelva y no estaba.
    /// </summary>
    public string? Detalle { get; init; }
}

/// <summary>
/// Guarda un archivo en una unidad que se puede retirar, llenar o proteger a mitad de la escritura SIN dejar nunca un archivo a medias con el nombre definitivo. Es lo que hay que
/// fiarle a una memoria USB real, y por eso el orden es el que es:
/// <list type="number">
/// <item>Se comprueba lo que se puede sin escribir: la carpeta existe, el nombre es seguro, el SHA-256 esperado es un SHA-256, y los bytes caben (si no, <see cref="MotivoDeEscritura.SinEspacio"/> sin tocar nada).</item>
/// <item>Se copia a un archivo TEMPORAL EN LA MISMA CARPETA (<c>.nombre.guid.parte</c>), nuevo y exclusivo, en bloques de 80 KiB, calculando el SHA-256 sobre la marcha. Si lo que viene del origen
/// no es lo que se prometió (otro tamaño u otro SHA-256), se para ahí: no se gasta una escritura en algo que no puede salir bien.</item>
/// <item>Se vacía a la unidad (<c>FlushFileBuffers</c>) y se cierra.</item>
/// <item>Se VERIFICA releyendo el temporal desde la unidad, sin pasar por la memoria del sistema: mismo tamaño y mismo SHA-256 que lo esperado.</item>
/// <item>Se le pone el nombre definitivo con un cambio de nombre que NO sobrescribe: si ya hay un archivo así se usa «(2)», «(3)»… y si otro proceso se queda con el nombre entre medias se prueba el siguiente.</item>
/// <item>Ante CUALQUIER fallo se borra el temporal y se devuelve el motivo; nunca se lanza una excepción por un problema de la unidad.</item>
/// </list>
/// Todo el trabajo con el disco va en el grupo de hebras: llamar a esto desde la pantalla no la congela aunque la unidad esté colgada.
/// </summary>
public static class EscrituraSegura
{
    private const int TamanoDeBloque = 81_920;      // lo que usa Stream.CopyTo; por debajo del límite del montón de objetos grandes

    // Esperas entre reintentos de lo que falla «de paso»: el antivirus que está leyendo el archivo recién cerrado hace que el cambio de nombre y el borrado fallen unas décimas de segundo.
    private static readonly TimeSpan[] Esperas = [TimeSpan.FromMilliseconds(50), TimeSpan.FromMilliseconds(150), TimeSpan.FromMilliseconds(400)];

    private static readonly OperacionesDeArchivoDelSistema Sistema = new();

    /// <summary>
    /// Guarda <paramref name="origen"/> (desde donde esté su posición, hasta el final) en <paramref name="carpetaDestino"/> con el nombre <paramref name="nombreSeguro"/>.
    /// <paramref name="sha256Esperado"/> y <paramref name="bytesEsperados"/> son los del contenido tal como lo calculó el backend. El avance (0 a 1) cuenta la copia y la verificación a
    /// partes iguales y llega a 1 sólo cuando el archivo ya tiene su nombre definitivo. No lanza por fallos de la unidad (devuelve <see cref="ResultadoDeEscritura.Fallo"/>); sólo por
    /// argumentos nulos o negativos, que son errores de quien llama.
    /// </summary>
    public static Task<ResultadoDeEscritura> EscribirAsync(
        Stream origen, string sha256Esperado, long bytesEsperados, string carpetaDestino, string nombreSeguro,
        IProgress<double>? progreso = null, CancellationToken ct = default, IOperacionesDeArchivo? io = null)
    {
        ArgumentNullException.ThrowIfNull(origen);
        ArgumentNullException.ThrowIfNull(sha256Esperado);
        ArgumentNullException.ThrowIfNull(carpetaDestino);
        ArgumentNullException.ThrowIfNull(nombreSeguro);
        ArgumentOutOfRangeException.ThrowIfNegative(bytesEsperados);

        // Sin pasar ct a Task.Run: una cancelación previa se resuelve dentro, como «Cancelado», y no como una tarea cancelada que lanzaría al esperarla.
        var operaciones = io ?? Sistema;
        return Task.Run(() => EjecutarAsync(origen, sha256Esperado, bytesEsperados, carpetaDestino, nombreSeguro, progreso, ct, operaciones));
    }

    private static async Task<ResultadoDeEscritura> EjecutarAsync(
        Stream origen, string sha256Esperado, long bytesEsperados, string carpetaDestino, string nombreSeguro,
        IProgress<double>? progreso, CancellationToken ct, IOperacionesDeArchivo io)
    {
        Stream? destino = null;
        string? temporal = null;
        string? carpetaCompleta = null;
        FalloDeEscritura fallo;
        string? detalle;
        try
        {
            ct.ThrowIfCancellationRequested();
            var avance = new MedidorDeAvance(progreso, bytesEsperados);
            avance.Empezar();

            // 1. Lo que se comprueba sin escribir nada.
            var esperado = HashNormalizado(sha256Esperado) ?? throw new FalloDeVerificacion("El SHA-256 esperado no es un valor de 64 dígitos hexadecimales.");
            if (string.IsNullOrWhiteSpace(carpetaDestino)) throw new ArgumentException("No se indicó la carpeta de destino.", nameof(carpetaDestino));
            var nombre = Resanear(nombreSeguro);
            var carpeta = carpetaCompleta = CarpetaCompleta(carpetaDestino);
            ComprobarElTamanoDelOrigen(origen, bytesEsperados);

            if (!io.ExisteCarpeta(carpeta)) throw new DirectoryNotFoundException($"No se encontró la carpeta «{carpeta}».");
            if (io.EspacioLibre(carpeta) is { } libre && bytesEsperados > libre)
                throw new IOException($"Hacen falta {bytesEsperados} bytes y la unidad tiene {libre} libres.", unchecked((int)0x80070070));      // ERROR_DISK_FULL: se clasifica igual que si lo hubiera dicho el disco

            // 2. La copia, a un temporal nuevo en la misma carpeta (así el cambio de nombre final no cruza de unidad ni se copia otra vez).
            var rutaTemporal = Path.Combine(carpeta, $".{nombre}.{Guid.NewGuid():N}.parte");
            destino = io.CrearNuevo(rutaTemporal);
            temporal = rutaTemporal;                // desde aquí existe y hay que borrarlo si algo falla

            long copiados = 0;
            string hashCopiado;
            using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256))
            {
                var bufer = new byte[TamanoDeBloque];
                while (true)
                {
                    ct.ThrowIfCancellationRequested();
                    int leidos;
                    try { leidos = await origen.ReadAsync(bufer.AsMemory(), ct).ConfigureAwait(false); }
                    catch (OperationCanceledException) { throw; }
                    catch (Exception e) { throw new FalloDelOrigen(e); }        // un fallo del ORIGEN (un archivo local) no es de la unidad: no se le echa la culpa a la memoria
                    if (leidos == 0) break;

                    copiados += leidos;
                    if (copiados > bytesEsperados) throw new FalloDeVerificacion($"El origen trae más de los {bytesEsperados} bytes esperados.");
                    hash.AppendData(bufer, 0, leidos);
                    await destino.WriteAsync(bufer.AsMemory(0, leidos), ct).ConfigureAwait(false);
                    avance.Avanzar(leidos);
                }
                hashCopiado = Convert.ToHexStringLower(hash.GetHashAndReset());
            }
            if (copiados != bytesEsperados) throw new FalloDeVerificacion($"El origen trae {copiados} bytes y se esperaban {bytesEsperados}.");
            if (!Iguales(hashCopiado, esperado)) throw new FalloDeVerificacion($"El SHA-256 del origen ({hashCopiado}) no es el esperado ({esperado}).");

            // 3. Vaciar a la unidad y cerrar. FlushAsync sólo vacía el búfer de .NET; FlushFileBuffers es lo que hace llegar los datos a la memoria USB.
            ct.ThrowIfCancellationRequested();
            await destino.FlushAsync(ct).ConfigureAwait(false);
            if (destino is FileStream archivo) archivo.Flush(flushToDisk: true);
            await destino.DisposeAsync().ConfigureAwait(false);
            destino = null;

            // 4. Verificar: releer de la unidad lo que quedó escrito.
            ct.ThrowIfCancellationRequested();
            var enLaUnidad = io.Tamano(rutaTemporal);
            if (enLaUnidad != bytesEsperados) throw new FalloDeVerificacion($"El archivo guardado mide {enLaUnidad} bytes y se esperaban {bytesEsperados}.");
            var (releidos, hashReleido) = await RelleerAsync(io, rutaTemporal, avance, ct).ConfigureAwait(false);
            if (releidos != bytesEsperados) throw new FalloDeVerificacion($"Al releer el archivo guardado se leyeron {releidos} bytes y se esperaban {bytesEsperados}.");
            if (!Iguales(hashReleido, esperado)) throw new FalloDeVerificacion($"El SHA-256 del archivo guardado ({hashReleido}) no es el esperado ({esperado}).");

            // 5. El nombre definitivo, sin sobrescribir nada. Éste es el último punto donde se puede cancelar: pasado el cambio de nombre el archivo ya es bueno y se entrega.
            ct.ThrowIfCancellationRequested();
            string? rutaFinal = null;
            for (var n = 1; n <= NombreDeArchivo.MaximoDeVariantes && rutaFinal is null; n++)
            {
                var candidata = Path.Combine(carpeta, NombreDeArchivo.ConSufijo(nombre, n));
                if (io.Existe(candidata)) continue;
                try
                {
                    await ReintentarAsync(() => { io.MoverSinSobrescribir(rutaTemporal, candidata); return true; }).ConfigureAwait(false);
                    rutaFinal = candidata;
                }
                catch (IOException) when (io.Existe(candidata))
                {
                    // otro proceso se quedó con ese nombre entre la comprobación y el cambio: se prueba con el siguiente número
                }
            }
            if (rutaFinal is null) throw new InvalidOperationException($"No hay un nombre libre para «{nombre}» en «{carpeta}».");
            temporal = null;                         // ya no hay temporal: el archivo tiene su nombre

            // 6. Mejor esfuerzo: que la entrada del directorio con el nombre nuevo también llegue a la unidad (en FAT32 y exFAT no hay bitácora que la proteja). Los DATOS ya se
            //    vaciaron y verificaron antes; si esto falla no se les quita el valor.
            try { io.VaciarADisco(rutaFinal); }
            catch { }

            avance.Terminar();
            return new ResultadoDeEscritura(true, rutaFinal, bytesEsperados, hashReleido, null);
        }
        catch (FalloDeVerificacion e)
        {
            fallo = MotivosDeEscritura.De(MotivoDeEscritura.VerificacionFallida);
            detalle = e.Message;
        }
        catch (FalloDelOrigen e)
        {
            fallo = MotivosDeEscritura.De(MotivoDeEscritura.Otro);
            detalle = "No se pudo leer el reporte de origen: " + MotivosDeEscritura.Detalle(e.InnerException);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            fallo = MotivosDeEscritura.De(MotivoDeEscritura.Cancelado);
            detalle = null;
        }
        catch (OperationCanceledException e)
        {
            // Nadie canceló: lo abortó Windows (ERROR_OPERATION_ABORTED, lo que pasa con una E/S en curso cuando la unidad desaparece). Decirle «cancelaste» a quien no tocó nada sería mentirle.
            fallo = MotivosDeEscritura.De(MotivoDeEscritura.MedioRetirado);
            detalle = "El sistema abortó la operación de E/S: " + MotivosDeEscritura.Detalle(e);
        }
        catch (Exception e)
        {
            // El temporal, ya cerrado, desapareció de una carpeta que SIGUE AHÍ: no es que la unidad se fuera, es que se lo llevó alguien; lo más probable, la cuarentena de un
            // antivirus que lo revisó al cerrarse (algunos lo hacen sin avisar con un error de «virus»: simplemente el archivo ya no está). Con el archivo todavía abierto, en cambio,
            // un «no encontrado» sí es la unidad que se fue, y eso lo dice Clasificar.
            if (destino is null && temporal is not null && carpetaCompleta is not null && EsArchivoQueDesaparecio(e) && io.ExisteCarpeta(carpetaCompleta))
            {
                fallo = MotivosDeEscritura.De(MotivoDeEscritura.BloqueadoPorAntivirus);
                detalle = "El archivo temporal ya cerrado desapareció de una carpeta que sigue existiendo (¿cuarentena del antivirus?): " + MotivosDeEscritura.Detalle(e);
            }
            else
            {
                fallo = MotivosDeEscritura.Clasificar(e, carpetaDestino, io.EsUnidadDeRed(carpetaDestino));
                detalle = MotivosDeEscritura.Detalle(e);
            }
        }

        // Sólo se llega aquí si algo falló: no se deja nada.
        var pendiente = await LimpiarAsync(destino, temporal, io).ConfigureAwait(false);
        return new ResultadoDeEscritura(false, null, 0, null, fallo) { Detalle = pendiente is null ? detalle : $"{detalle} | {pendiente}" };
    }

    // ---------------------------------------------------------------------------------------------------- piezas

    /// <summary>Lee de vuelta el temporal, tal como está en la unidad, y devuelve cuántos bytes eran y su SHA-256.</summary>
    private static async Task<(long Bytes, string Sha256)> RelleerAsync(IOperacionesDeArchivo io, string ruta, MedidorDeAvance avance, CancellationToken ct)
    {
        await using var lectura = await ReintentarAsync(() => io.AbrirLectura(ruta)).ConfigureAwait(false);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var bufer = new byte[TamanoDeBloque];
        long total = 0;
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            var leidos = await lectura.ReadAsync(bufer.AsMemory(), ct).ConfigureAwait(false);
            if (leidos == 0) break;
            hash.AppendData(bufer, 0, leidos);
            total += leidos;
            avance.Avanzar(leidos);
        }
        return (total, Convert.ToHexStringLower(hash.GetHashAndReset()));
    }

    /// <summary>
    /// Cierra lo que haya quedado abierto y borra el temporal, con reintentos cortos (un antivirus lo puede tener agarrado un instante). Si la unidad ya no está no hay nada que borrar y
    /// no se insiste. Un fallo al borrar no oculta el error original: sólo se devuelve su descripción para la bitácora.
    /// </summary>
    private static async Task<string?> LimpiarAsync(Stream? destino, string? temporal, IOperacionesDeArchivo io)
    {
        if (destino is not null)
        {
            try { await destino.DisposeAsync().ConfigureAwait(false); }
            catch { /* ya se está fallando: un cierre que falla no cambia nada */ }
        }
        if (temporal is null) return null;

        for (var intento = 0; ; intento++)
        {
            try
            {
                io.Borrar(temporal);
                return null;
            }
            catch (Exception e) when (e is DirectoryNotFoundException or DriveNotFoundException or FileNotFoundException)
            {
                return null;                         // la carpeta o el archivo ya no están (se retiró la unidad): nada que borrar
            }
            catch (Exception e)
            {
                if (intento >= Esperas.Length) return $"No se pudo borrar el temporal «{temporal}»: {MotivosDeEscritura.Detalle(e)}";
                await Task.Delay(Esperas[intento]).ConfigureAwait(false);
            }
        }
    }

    /// <summary>Repite lo que falla «de paso» (el archivo está en uso un instante, el antivirus lo revisa) unas pocas veces con esperas cortas; lo demás falla a la primera.</summary>
    private static async Task<T> ReintentarAsync<T>(Func<T> accion)
    {
        for (var intento = 0; ; intento++)
        {
            try { return accion(); }
            catch (Exception e) when (intento < Esperas.Length && EsPasajero(e)) { await Task.Delay(Esperas[intento]).ConfigureAwait(false); }
        }
    }

    private static bool EsPasajero(Exception e) =>
        MotivosDeEscritura.Clasificar(e).Motivo is MotivoDeEscritura.ArchivoEnUso or MotivoDeEscritura.SinPermiso;

    /// <summary>¿«no se encontró el archivo» (el .NET FileNotFoundException o el código 2 de Windows)?</summary>
    private static bool EsArchivoQueDesaparecio(Exception e) => e is FileNotFoundException || MotivosDeEscritura.CodigoDeWindows(e) == 0x02;

    /// <summary>Si el origen se puede medir y no mide lo prometido, no vale la pena ni abrir el temporal. (Si no se puede medir, ya lo dirá la copia.)</summary>
    private static void ComprobarElTamanoDelOrigen(Stream origen, long bytesEsperados)
    {
        long restantes;
        try
        {
            if (!origen.CanSeek) return;
            restantes = origen.Length - origen.Position;
        }
        catch
        {
            return;
        }
        if (restantes != bytesEsperados) throw new FalloDeVerificacion($"El origen trae {restantes} bytes desde su posición actual y se esperaban {bytesEsperados}.");
    }

    /// <summary>
    /// El nombre que se usa, a partir del que se recibió. Un nombre que ya es seguro se deja EXACTAMENTE como viene (ni siquiera cambia la caja de lo que sigue al último punto): el
    /// llamador lo saneó. Si no lo era, se sanea ahora conservando la extensión, para que el archivo siga abriéndose con su programa.
    /// </summary>
    private static string Resanear(string nombre)
    {
        if (NombreDeArchivo.Sanear(nombre) == nombre) return nombre;
        var (baseDelNombre, extension) = NombreDeArchivo.SepararExtension(nombre);
        return NombreDeArchivo.Sanear(baseDelNombre, extension);
    }

    /// <summary>La carpeta como ruta completa. «E:» sin barra significa «la carpeta actual de la unidad E», no su raíz, y combinada con un nombre daría «E:nombre»: se le pone la barra.</summary>
    private static string CarpetaCompleta(string carpeta)
    {
        var c = carpeta.Trim();
        if (c.Length == 2 && c[1] == ':') c += Path.DirectorySeparatorChar;
        return Path.GetFullPath(c);
    }

    private static string? HashNormalizado(string hash)
    {
        var h = hash.Trim();
        return h.Length == 64 && h.All(Uri.IsHexDigit) ? h.ToLowerInvariant() : null;
    }

    private static bool Iguales(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);

    /// <summary>El avance (0 a 1): copiar es la mitad del trabajo y verificar la otra mitad. No se informa por cada bloque, sino cada vez que se avanza medio punto porcentual.</summary>
    private sealed class MedidorDeAvance(IProgress<double>? progreso, long bytesEsperados)
    {
        private long _hecho;
        private double _ultimo = -1;

        public void Empezar() => Informar(0);

        public void Avanzar(long bytes)
        {
            _hecho += bytes;
            if (bytesEsperados <= 0) return;
            var valor = Math.Min(0.99, _hecho / (2.0 * bytesEsperados));          // hasta el cambio de nombre no es 100 %
            if (valor - _ultimo >= 0.005) Informar(valor);
        }

        public void Terminar() => Informar(1.0);

        private void Informar(double valor)
        {
            _ultimo = valor;
            try { progreso?.Report(valor); }
            catch { /* quien escucha el avance no puede hacer fallar el guardado */ }
        }
    }

    /// <summary>Lo copiado o releído no es lo prometido (otro tamaño, otro SHA-256). Es una excepción propia para llegar por el mismo camino de limpieza que cualquier otro fallo.</summary>
    private sealed class FalloDeVerificacion(string detalle) : Exception(detalle);

    /// <summary>El origen (el archivo local con el reporte) falló al leerlo: no es culpa de la unidad de destino.</summary>
    private sealed class FalloDelOrigen(Exception interna) : Exception(interna.Message, interna);
}
