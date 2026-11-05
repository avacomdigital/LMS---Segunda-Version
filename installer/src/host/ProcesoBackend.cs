using System.Diagnostics;

namespace Avacom.Ops.Host;

/// <summary>
/// El proceso hijo que atiende la API: Python embebido -> Daphne (ASGI) -> Django/DRF y WebSocket.
///
/// Se lanza siempre igual, lo llame el servicio o el diagnostico, para que lo
/// que se prueba en la instalacion sea exactamente lo que corre despues.
/// </summary>
internal sealed class ProcesoBackend : IDisposable
{
    private readonly Registro _registro;
    private Process? _proceso;

    public ProcesoBackend(Registro registro) => _registro = registro;

    public bool EstaVivo => _proceso is { HasExited: false };

    /// <summary>
    /// ¿Estos argumentos arrancan codigo DEL BACKEND (manage.py o el servidor) en un paquete cifrado? Entonces Python no recibe el script: recibe <c>avacom_boot.py manage|script ...</c> y la llave K
    /// por su entrada estandar (<see cref="EntregarClave"/>). Lanza <see cref="Dispositivo.LiberacionFallida"/> si el TPM del equipo no entrega la llave.
    /// </summary>
    private static List<string> ParaPaqueteCifrado(List<string> argumentos)
    {
        if (!Dispositivo.LiberacionDeClave.HayPaqueteCifrado || argumentos.Count == 0) return argumentos;
        var manage = argumentos[0] == Rutas.ManagePy;
        var codigo = argumentos[0] == "-c" && argumentos.Count >= 2;                  // «python -c <codigo>»: puede importar modulos del backend (la configuracion efectiva)
        if (!manage && !codigo && argumentos[0] != Rutas.GuionServidor) return argumentos;
        _ = Dispositivo.LiberacionDeClave.Obtener();                                  // falla aqui, ANTES de lanzar nada
        if (manage) return [Rutas.GuionDeArranqueCifrado, "manage", .. argumentos.Skip(1)];
        return codigo ? [Rutas.GuionDeArranqueCifrado, "code", .. argumentos.Skip(1)] : [Rutas.GuionDeArranqueCifrado, "script", .. argumentos];
    }

    /// <summary>Despues de <c>Process.Start</c>: si el proceso es un arranque cifrado, le entrega la llave en la primera linea de su entrada. Un manage.py (corto) cierra la entrada; el servidor la deja abierta (es como se le pide parar).</summary>
    public static void EntregarClave(Process proceso)
    {
        var a = proceso.StartInfo.ArgumentList;
        if (a.Count < 2 || a[0] != Rutas.GuionDeArranqueCifrado) return;
        var k = Dispositivo.LiberacionDeClave.Obtener();
        proceso.StandardInput.WriteLine("AVACOM-CLAVE " + Convert.ToHexString(k).ToLowerInvariant());
        proceso.StandardInput.Flush();
        if (a[1] is "manage" or "code") proceso.StandardInput.Close();
    }

    public static ProcessStartInfo Preparar(string ejecutable, IEnumerable<string> argumentos)
    {
        var lista = ParaPaqueteCifrado(argumentos.ToList());
        var inicio = new ProcessStartInfo
        {
            FileName = ejecutable,
            WorkingDirectory = Rutas.CarpetaBackend,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            // Python escribe en UTF-8 (PYTHONIOENCODING, abajo): se lee igual para que los
            // acentos de los mensajes de Django no salgan rotos en los registros.
            StandardOutputEncoding = new System.Text.UTF8Encoding(false),
            StandardErrorEncoding = new System.Text.UTF8Encoding(false),
        };
        foreach (var argumento in lista) inicio.ArgumentList.Add(argumento);
        inicio.RedirectStandardInput = lista.Count > 0 && lista[0] == Rutas.GuionDeArranqueCifrado;       // la llave viaja por aqui, nunca por el entorno ni la linea de comandos

        // El backend se configura SOLO con backend.env. Todo AVACOM_* que traiga el entorno de
        // Windows (del usuario o del equipo: una base de pruebas, el curso de ejemplo, una nota
        // de enlace de pruebas) se descarta antes: lo que no esta en backend.env no cuenta.
        foreach (var heredada in inicio.Environment.Keys.Where(Configuracion.EsDeAvacom).ToList())
        {
            inicio.Environment.Remove(heredada);
        }

        // La configuracion del nodo, tal cual la lee settings.py.
        foreach (var (clave, valor) in Configuracion.Leer())
        {
            inicio.Environment[clave] = valor;
        }
        inicio.Environment["DJANGO_SETTINGS_MODULE"] = "avacom_lms.settings";
        inicio.Environment["PYTHONUNBUFFERED"] = "1";
        // El producto se instala en Program Files, que es de solo lectura para
        // quien da la clase. Sin esto, Python intentaria dejar ahi sus
        // __pycache__ (el servicio corre como SYSTEM y podria), y la carpeta
        // instalada dejaria de ser identica a lo que se empaqueto.
        inicio.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        // Sin esto, un error con caracteres acentuados en la consola de Windows
        // se convierte en un UnicodeEncodeError que oculta el error real.
        inicio.Environment["PYTHONIOENCODING"] = "utf-8";
        return inicio;
    }

    public bool Iniciar()
    {
        if (!File.Exists(Rutas.PythonExe))
        {
            _registro.Escribir($"No se encontro el runtime de Python en {Rutas.PythonExe}.");
            return false;
        }

        ProcessStartInfo inicio;
        try { inicio = Preparar(Rutas.PythonExe, [Rutas.GuionServidor]); }
        catch (Dispositivo.LiberacionFallida fallo)
        {
            _registro.Escribir($"No se pudo liberar la llave del codigo del nodo ({fallo.Motivo}): el backend no arranca. Se necesita el sello y la clave del paquete de AVACOM para ESTE equipo (carpeta Config, sello).");
            return false;
        }
        // La entrada estandar queda abierta a proposito: cerrarla es como se le
        // pide al backend que pare limpiamente (ver avacom_ops_backend.py).
        inicio.RedirectStandardInput = true;
        _proceso = new Process { StartInfo = inicio, EnableRaisingEvents = true };
        _proceso.OutputDataReceived += (_, e) => { if (e.Data is not null) _registro.Escribir($"[backend] {e.Data}"); };
        _proceso.ErrorDataReceived += (_, e) => { if (e.Data is not null) _registro.Escribir($"[backend] {e.Data}"); };

        try
        {
            _proceso.Start();
            EntregarClave(_proceso);
            _proceso.BeginOutputReadLine();
            _proceso.BeginErrorReadLine();
            _registro.Escribir($"Backend iniciado (pid {_proceso.Id}).");
            return true;
        }
        catch (Exception error)
        {
            _registro.Escribir("No se pudo iniciar el backend", error);
            return false;
        }
    }

    public async Task<int> EsperarSalidaAsync(CancellationToken cancelacion)
    {
        if (_proceso is null) return -1;
        try
        {
            await _proceso.WaitForExitAsync(cancelacion).ConfigureAwait(false);
            return _proceso.ExitCode;
        }
        catch (OperationCanceledException)
        {
            return -1;
        }
    }

    public void Detener()
    {
        if (_proceso is null || _proceso.HasExited) return;
        try
        {
            // Primero, parada limpia: Daphne no cierra por señal en Windows y
            // matar el proceso deja conexiones SQLite abiertas. Se le pide por
            // la entrada estandar; el backend detiene Twisted, cierra Django y
            // vuelca el WAL al archivo principal del expediente.
            try
            {
                _proceso.StandardInput.WriteLine("detener");
                _proceso.StandardInput.Close();
            }
            catch (IOException)
            {
                // Ya estaba cerrando.
            }

            if (_proceso.WaitForExit(15_000))
            {
                _registro.Escribir($"Backend detenido limpiamente (codigo {_proceso.ExitCode}).");
                return;
            }

            // Si no contesto, se termina el arbol de procesos para no dejar el
            // puerto 8000 ocupado por un huerfano. SQLite en modo WAL se recupera solo.
            _registro.Escribir("El backend no cerro a tiempo: se termina el proceso.");
            _proceso.Kill(entireProcessTree: true);
            _proceso.WaitForExit(10_000);
            _registro.Escribir("Backend detenido a la fuerza.");
        }
        catch (Exception error)
        {
            _registro.Escribir("No se pudo detener el backend limpiamente", error);
        }
    }

    public void Dispose()
    {
        Detener();
        _proceso?.Dispose();
        _proceso = null;
    }
}
