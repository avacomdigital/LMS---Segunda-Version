using System.Diagnostics;
using System.Text;

namespace Avacom.Ops.Host;

/// <summary>
/// La pantalla "Backend Configuration" del instalador, hecha de verdad.
///
/// Todo lo que el README del backend le pide a una persona -crear el entorno,
/// instalar dependencias, migrar, arrancar- ocurre aqui sin que nadie escriba
/// un comando. Las dependencias ya vienen dentro del paquete, asi que este
/// paso no necesita internet ni pip.
///
/// Es idempotente: se puede repetir en una actualizacion sin perder la base ni
/// regenerar las claves del nodo.
/// </summary>
internal static class Preparar
{
    /// <summary>Lo que la pantalla del instalador lee para decir como fue.</summary>
    public static string ArchivoEstado => Path.Combine(Rutas.CarpetaLogs, "preparacion-estado.txt");

    /// <summary>Avisos que no son fallos (base reemplazada, claves conservadas): la pantalla final los muestra.</summary>
    public static string ArchivoAviso => Path.Combine(Rutas.CarpetaLogs, "preparacion-aviso.txt");

    private const string ImportacionesDelRuntime =
        "import django, rest_framework, channels, daphne, twisted, autobahn, zoneinfo, sqlite3; print(django.get_version())";

    // Cuenta las personas guardadas sin abrir Django: solo lee la tabla si existe.
    private const string ContarPersonas =
        "import os, sqlite3\n" +
        "p = os.environ.get('AVACOM_LMS_DB', '')\n" +
        "if not p or not os.path.exists(p):\n" +
        "    print(0)\n" +
        "else:\n" +
        "    c = sqlite3.connect(p, timeout=5)\n" +
        "    try:\n" +
        "        print(c.execute('select count(*) from m01_persona').fetchone()[0])\n" +
        "    except sqlite3.Error:\n" +
        "        print(0)\n" +
        "    finally:\n" +
        "        c.close()\n";

    public static int Ejecutar()
    {
        var registro = new Registro("instalacion.log");
        registro.Escribir("--- Preparacion del backend ---");
        registro.Escribir($"Instalacion: {Rutas.RaizInstalacion}");
        registro.Escribir($"Estado del nodo: {Rutas.RaizDatos}");

        try
        {
            Rutas.AsegurarCarpetasDeEstado();
            File.Delete(ArchivoEstado);
            File.Delete(ArchivoAviso);
            var avisos = new List<string>();

            var politica = Manifiesto.PoliticaDeDatos();
            registro.Escribir($"Politica de datos de esta version: {politica}.");
            var nueva = Configuracion.CrearSiFalta(registro);

            if (!File.Exists(Rutas.PythonExe))
            {
                return Terminar(registro, 2, "No se encontro el runtime del backend en la carpeta de instalacion.");
            }
            if (!File.Exists(Rutas.ManagePy))
            {
                return Terminar(registro, 3, "No se encontro el backend en la carpeta de instalacion.");
            }

            // 1. El runtime distribuido puede importar lo que el backend necesita.
            var comprobacion = Python(registro, ["-c", ImportacionesDelRuntime]);
            if (comprobacion.Codigo != 0)
            {
                return Terminar(registro, 4, "El runtime del backend no esta completo.");
            }
            registro.Escribir($"Runtime verificado. Django {comprobacion.Salida.Trim()}.");

            // 2. Claves de acceso. Una configuracion de la version 2.0.0 solo
            //    tiene AVACOM_LMS_SECRET: se completa unicamente si la base no
            //    guarda personas (ver Configuracion.CompletarClavesDeAcceso).
            AnotarAviso(avisos, Configuracion.CompletarClavesDeAcceso(registro, HayPersonas(registro)));

            // 3. Configuracion valida antes de tocar la base de datos: si algo
            //    esta mal en el .env generado, se ve aqui y no a mitad de migrar.
            var revision = Python(registro, [Rutas.ManagePy, "check"]);
            if (revision.Codigo != 0)
            {
                return Terminar(registro, 5, "La configuracion del backend no paso la revision de Django.");
            }
            registro.Escribir("Revision de configuracion de Django correcta.");

            // 4. Base de datos. Crea el archivo si no existe y aplica solo lo que
            //    falte si ya venia de una version anterior. Si no migra:
            //      protegidos     -> se detiene; el asistente restaura la copia.
            //      reemplazables  -> ya hay copia: se retira la base y se crea otra.
            var migracion = Python(registro, [Rutas.ManagePy, "migrate", "--noinput"]);
            if (migracion.Codigo != 0)
            {
                var respaldo = Datos.UltimoRespaldo();
                if (politica != Manifiesto.Reemplazables || respaldo is null || !File.Exists(Rutas.BaseDeDatos))
                {
                    return Terminar(registro, 6,
                        "No se pudieron aplicar las migraciones de la base de datos" +
                        (respaldo is null ? "." : "; se conserva la copia de seguridad."));
                }

                registro.Escribir("La base anterior no migra limpia y la politica la declara reemplazable: se crea una nueva.");
                Datos.VaciarBase(registro);
                AnotarAviso(avisos, Configuracion.CompletarClavesDeAcceso(registro, false));
                migracion = Python(registro, [Rutas.ManagePy, "migrate", "--noinput"]);
                if (migracion.Codigo != 0)
                {
                    return Terminar(registro, 6, "No se pudieron aplicar las migraciones ni sobre una base nueva.");
                }
                AnotarAviso(avisos,
                    "La base de datos de la version anterior no era compatible y se empezo con una nueva: " +
                    "hay que volver a instalar la organizacion, importar el padron y registrar las tabletas. " +
                    $"La copia de la anterior esta en {respaldo}.");
            }
            registro.Escribir("Base de datos al dia.");

            // 5. Archivos estaticos: solo si el backend declara donde recogerlos.
            //    Este backend sirve JSON y no define STATIC_ROOT, asi que no hay
            //    nada que recoger. Se comprueba en vez de suponerlo, porque si
            //    una version futura lo define, la instalacion debe cubrirlo.
            var estaticos = Python(registro,
                ["-c",
                 "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','avacom_lms.settings');" +
                 "django.setup();from django.conf import settings;print(settings.STATIC_ROOT or '')"]);
            if (estaticos.Codigo == 0 && estaticos.Salida.Trim().Length > 0)
            {
                var recogida = Python(registro, [Rutas.ManagePy, "collectstatic", "--noinput"]);
                registro.Escribir(recogida.Codigo == 0
                    ? "Archivos estaticos recogidos."
                    : "No se pudieron recoger los archivos estaticos; la API no los necesita.");
            }
            else
            {
                registro.Escribir("El backend no publica archivos estaticos: nada que recoger.");
            }

            // 6. Validacion de ejecucion: el puerto que va a usar el servicio.
            var puerto = Configuracion.PuertoConfigurado();
            if (!Salud.PuertoLibre(puerto))
            {
                var propio = Salud.EsNuestroBackendAsync(puerto).GetAwaiter().GetResult();
                registro.Escribir(propio
                    ? $"El puerto {puerto} lo esta usando un backend de AVACOM OPS que ya estaba corriendo."
                    : $"El puerto {puerto} esta ocupado por otro programa.");
                if (!propio)
                {
                    return Terminar(registro, 7,
                        $"El puerto {puerto} esta ocupado por otro programa. " +
                        "Cierra ese programa y vuelve a ejecutar la instalacion.");
                }
            }

            if (avisos.Count > 0)
            {
                File.WriteAllText(ArchivoAviso, string.Join(Environment.NewLine + Environment.NewLine, avisos), new UTF8Encoding(false));
            }

            var resumen = nueva
                ? "Backend configurado: configuracion del nodo creada y base de datos inicializada."
                : "Backend configurado: se conservo la configuracion y la base de datos existentes.";
            return Terminar(registro, 0, resumen);
        }
        catch (Exception error)
        {
            registro.Escribir("Fallo inesperado en la preparacion", error);
            return Terminar(registro, 1, "La preparacion del backend no se pudo completar.");
        }
    }

    private static void AnotarAviso(List<string> avisos, string? texto)
    {
        if (!string.IsNullOrWhiteSpace(texto)) avisos.Add(texto);
    }

    /// <summary>true/false segun la base guarde o no personas; null si no se pudo saber.</summary>
    private static bool? HayPersonas(Registro registro)
    {
        var resultado = Python(registro, ["-c", ContarPersonas]);
        if (resultado.Codigo != 0 || !long.TryParse(resultado.Salida.Trim(), out var cuantas)) return null;
        registro.Escribir($"Personas guardadas en la base: {cuantas}.");
        return cuantas > 0;
    }

    private static int Terminar(Registro registro, int codigo, string mensaje)
    {
        registro.Escribir($"Resultado ({codigo}): {mensaje}");
        try
        {
            File.WriteAllText(ArchivoEstado, mensaje, new UTF8Encoding(false));
        }
        catch (IOException)
        {
        }
        return codigo;
    }

    private sealed record Resultado(int Codigo, string Salida);

    private static Resultado Python(Registro registro, IEnumerable<string> argumentos)
    {
        var inicio = ProcesoBackend.Preparar(Rutas.PythonExe, argumentos);
        try
        {
            using var proceso = Process.Start(inicio);
            if (proceso is null) return new Resultado(-1, string.Empty);

            // Las dos salidas se leen a la vez: leerlas una tras otra bloquea el
            // proceso si un traceback largo llena el pipe de stderr mientras
            // aqui se espera a stdout (justo lo que pasa cuando falla migrate).
            var tareaErrores = proceso.StandardError.ReadToEndAsync();
            var salida = proceso.StandardOutput.ReadToEnd();
            var errores = tareaErrores.GetAwaiter().GetResult();
            if (!proceso.WaitForExit(300_000))
            {
                proceso.Kill(entireProcessTree: true);
                return new Resultado(-1, salida);
            }

            foreach (var linea in (salida + errores).Split('\n', StringSplitOptions.RemoveEmptyEntries))
            {
                registro.Escribir($"[python] {linea.TrimEnd('\r')}");
            }
            return new Resultado(proceso.ExitCode, salida);
        }
        catch (Exception error)
        {
            registro.Escribir("No se pudo ejecutar el runtime de Python", error);
            return new Resultado(-1, string.Empty);
        }
    }
}
