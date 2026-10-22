using System.Diagnostics;
using System.Text.Json;

namespace Avacom.Ops.Host.Actualizacion;

/// <summary>El checkpoint (checkpoint.json): lo ultimo que el host sabe de la orden que esta aplicando. Se escribe ANTES de cada paso (P-07, A4).</summary>
internal sealed record Punto(string OrdenId, string PaqueteId, string Accion, string Fase, string Paso, string? Respaldo, long IniciadoEn)
{
    public const string Avance = "avance";
    public const string Retroceso = "retroceso";

    public static string Ruta => Path.Combine(Rutas.CarpetaActualizaciones, "checkpoint.json");

    public void Guardar() => Disco.EscribirAtomico(Ruta, JsonSerializer.Serialize(new Dictionary<string, object?>
    {
        ["formato"] = 1, ["orden_id"] = OrdenId, ["paquete_id"] = PaqueteId, ["accion"] = Accion, ["fase"] = Fase, ["paso"] = Paso, ["respaldo"] = Respaldo, ["iniciado_en"] = IniciadoEn,
    }, new JsonSerializerOptions { WriteIndented = true }));

    public static Punto? Leer()
    {
        try
        {
            if (!File.Exists(Ruta)) return null;
            using var documento = JsonDocument.Parse(File.ReadAllText(Ruta));
            var r = documento.RootElement;
            string T(string n) => r.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
            return new Punto(T("orden_id"), T("paquete_id"), T("accion"), T("fase"), T("paso"), T("respaldo") is { Length: > 0 } rs ? rs : null,
                r.TryGetProperty("iniciado_en", out var i) && i.ValueKind == JsonValueKind.Number ? i.GetInt64() : Disco.Ahora());
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public static void Borrar()
    {
        try { File.Delete(Ruta); } catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
    }
}

/// <summary>
/// La aplicacion real de un paquete de modulo (MOD-017 · Fase 4, P-06, P-07, P-09): el host (servicio SYSTEM) obedece la orden que el backend dejo en
/// Actualizaciones\orden.json, con el backend PARADO, paso a paso y con un checkpoint antes de cada uno:
///
///   comprobar → respaldar → instantanea → copiar → migrar → verificar      (revertir: comprobar → respaldar → migrar → copiar → verificar)
///
/// Si un paso que ya cambio algo falla, o el host muere a mitad, se vuelve atras SOLO: el codigo desde la instantanea y la base desde la copia (INV-008), se arranca el
/// backend viejo y se comprueba que responde. Si ni eso se logra, no se borra nada y el resultado es <c>reversion_fallida</c>. El resultado (resultado.json) lo registra
/// el backend al volver a arrancar (FUN-187). Una clase abierta aplaza la aplicacion antes de parar nada (R-01): el host NUNCA detiene una clase.
/// </summary>
internal sealed class Aplicador
{
    public const string ArchivoDeOrden = "orden.json";
    public const string ArchivoDeResultado = "resultado.json";

    private readonly Registro _r;

    public Aplicador(Registro registro) => _r = registro;

    public static string RutaDeOrden => Path.Combine(Rutas.CarpetaActualizaciones, ArchivoDeOrden);
    public static string RutaDeResultado => Path.Combine(Rutas.CarpetaActualizaciones, ArchivoDeResultado);

    private sealed record MigracionHecha(string Modulo, string Nombre, bool Ok);

    private sealed class Contexto(Orden orden)
    {
        public Orden Orden { get; } = orden;
        public Stopwatch Reloj { get; } = Stopwatch.StartNew();
        public long IniciadoEn { get; set; } = Disco.Ahora();
        public string Paso { get; set; } = Pasos.Comprobar;
        public string Fase { get; set; } = Punto.Avance;
        public string? Respaldo { get; set; }
        public List<MigracionHecha> Migraciones { get; } = [];
        public TimeSpan Restante => TimeSpan.FromMinutes(Orden.LimiteMinutos) - Reloj.Elapsed;
        public int Indice => Orden.Secuencia.ToList().IndexOf(Paso);
        /// <summary>El primer paso que cambia algo en el equipo: antes de el, un fallo no deja nada que deshacer.</summary>
        public int PrimerPasoQueCambia => Orden.Secuencia.ToList().IndexOf(Orden.EsReversion ? Pasos.Migrar : Pasos.Copiar);
        public int IndiceDeMigrar => Orden.Secuencia.ToList().IndexOf(Pasos.Migrar);
    }

    // ------------------------------------------------------------------------------------------------------------- entrada: una orden nueva
    /// <summary>
    /// Obedece una orden. <paramref name="pararBackend"/> se llama UNA vez, despues de las comprobaciones (con el backend aun vivo: asi la clase se ve y nada se detiene si
    /// la hay) y antes de tocar nada. Siempre deja un resultado.json.
    /// </summary>
    public void Procesar(Orden orden, Action pararBackend)
    {
        var ctx = new Contexto(orden);
        _r.Escribir($"=== Orden {orden.OrdenId}: {orden.Accion} el paquete {orden.PaqueteId} ({orden.NombreDelPaquete}); limite {orden.LimiteMinutos} min ===");
        if (!ComprobarYDecidir(ctx, vivo: true)) return;
        pararBackend();
        Correr(ctx, desde: 1);
    }

    /// <summary>Fase 1: lo que se puede saber sin parar nada. false = ya se dejo el resultado (aplazada o rechazada) y no hay nada mas que hacer.</summary>
    private bool ComprobarYDecidir(Contexto ctx, bool vivo)
    {
        try
        {
            EmpezarPaso(ctx, Pasos.Comprobar);
            Comprobar(ctx.Orden);
            var clase = HayClase();
            if (clase != false)
            {
                Terminar(ctx, "aplazada", clase == true
                    ? "Hay una clase en curso: la actualizacion se aplaza (R-01). El host no detiene nada."
                    : "No se pudo saber si hay una clase en curso: por seguridad la actualizacion se aplaza.", null);
                return false;
            }
            return true;
        }
        catch (FalloDePaso fallo)
        {
            _r.Escribir($"La orden se rechaza: {fallo.Message}");
            Terminar(ctx, "rechazada", fallo.Message, fallo.Message);
            return false;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            _r.Escribir("La orden se rechaza", error);
            Terminar(ctx, "rechazada", "No se pudo comprobar la orden: " + error.Message, error.Message);
            return false;
        }
    }

    // ------------------------------------------------------------------------------------------------------------- los pasos
    private void Correr(Contexto ctx, int desde)
    {
        var secuencia = ctx.Orden.Secuencia;
        try
        {
            for (var i = desde; i < secuencia.Count; i++)
            {
                EmpezarPaso(ctx, secuencia[i]);
                switch (secuencia[i])
                {
                    case Pasos.Respaldar: Respaldar(ctx); break;
                    case Pasos.Instantanea: HacerInstantanea(ctx); break;
                    case Pasos.Copiar: Copiar(ctx); break;
                    case Pasos.Migrar: Migrar(ctx); break;
                    case Pasos.Verificar: Verificar(ctx); break;
                }
            }
        }
        catch (Exception error) when (error is FalloDePaso or IOException or UnauthorizedAccessException)
        {
            var motivo = error is FalloDePaso ? error.Message : $"{error.GetType().Name}: {error.Message}";
            _r.Escribir($"Fallo en el paso «{ctx.Paso}»: {motivo}");
            if (ctx.Indice < ctx.PrimerPasoQueCambia)
            {
                // Aun no se habia cambiado nada: no hay que volver a ninguna parte.
                Terminar(ctx, "rechazada", $"El paso «{ctx.Paso}» fallo antes de cambiar nada: {motivo}", motivo);
                return;
            }
            Deshacer(ctx, motivo);
            return;
        }

        if (ctx.Orden.EsReversion) Disco.BorrarCarpeta(ctx.Orden.CarpetaDeVersion);     // lo que se queria ya paso: la instantanea no hace falta
        Terminar(ctx, ctx.Orden.EsReversion ? "revertido" : "aplicado",
            ctx.Orden.EsReversion ? "El paquete se revirtio y el aula verifico la version anterior." : "El paquete se aplico y el aula verifico la version nueva.", null);
    }

    private void EmpezarPaso(Contexto ctx, string paso)
    {
        ctx.Paso = paso;
        new Punto(ctx.Orden.OrdenId, ctx.Orden.PaqueteId, ctx.Orden.Accion, ctx.Fase, paso, ctx.Respaldo, ctx.IniciadoEn).Guardar();
        _r.Escribir($"Paso «{paso}» ({ctx.Fase}); quedan {ctx.Restante.TotalSeconds:0} s del limite.");
        Inyeccion.Cortar(paso, 0);
        Inyeccion.Fallar(paso, 0);
        if (ctx.Fase == Punto.Avance && paso != Pasos.Comprobar && ctx.Restante <= TimeSpan.Zero)
            throw new FalloDePaso(paso, $"Se agoto el tiempo de la operacion ({ctx.Orden.LimiteMinutos} min).");
    }

    private void Comprobar(Orden o)
    {
        // Cada ruta del paquete resuelta dentro de Backend\ (sin enlaces en el camino): lo que el host va a escribir.
        foreach (var a in o.Archivos)
        {
            try { Disco.Confinar(Rutas.CarpetaBackend, a.Ruta); }
            catch (IOException error) { throw new FalloDePaso(Pasos.Comprobar, error.Message); }
        }

        if (!o.EsReversion)
        {
            if (!File.Exists(o.ArchivoDelPaquete)) throw new FalloDePaso(Pasos.Comprobar, "El paquete .avupd guardado no esta.");
            var paquete = new FileInfo(o.ArchivoDelPaquete);
            if (paquete.Length != o.PaqueteBytes || !string.Equals(Disco.Sha256DeArchivo(o.ArchivoDelPaquete), o.PaqueteSha256, StringComparison.OrdinalIgnoreCase))
                throw new FalloDePaso(Pasos.Comprobar, "El paquete guardado no coincide con la huella de la orden (alterado).");
            foreach (var a in o.Archivos)
            {
                var origen = Disco.Confinar(o.Staging, a.Ruta);
                if (!File.Exists(origen) || new FileInfo(origen).Length != a.Bytes
                    || !string.Equals(Disco.Sha256DeArchivo(origen), a.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new FalloDePaso(Pasos.Comprobar, $"El staging no coincide con la orden en {a.Ruta}.");
            }
        }
        else
        {
            var anterior = new Instantanea(o.Anterior);
            var indice = anterior.Leer() ?? throw new FalloDePaso(Pasos.Comprobar, "No hay instantanea completa del codigo anterior: no se puede revertir.");
            if (indice.PaqueteId != o.PaqueteId) throw new FalloDePaso(Pasos.Comprobar, "La instantanea es de otro paquete.");
            // Si un instalador completo cambio el programa despues, el codigo de la instantanea ya no es el de este producto: volver a el lo mezclaria.
            if (indice.Producto != Manifiesto.Version())
                throw new FalloDePaso(Pasos.Comprobar, $"El programa paso de la version {indice.Producto} a la {Manifiesto.Version()} (instalacion completa) desde que se tomo la instantanea: ya no se puede volver a ese codigo.");
            var enIndice = indice.Entradas.Select(e => e.Ruta).ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (o.Archivos.Any(a => !enIndice.Contains(a.Ruta))) throw new FalloDePaso(Pasos.Comprobar, "La instantanea no cubre todos los archivos del paquete.");
            foreach (var e in indice.Entradas.Where(e => e.Existia))
            {
                var guardado = Disco.Confinar(anterior.Carpeta, e.Ruta);
                if (!File.Exists(guardado) || !string.Equals(Disco.Sha256DeArchivo(guardado), e.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new FalloDePaso(Pasos.Comprobar, $"La instantanea esta danada en {e.Ruta}.");
            }
        }

        // Espacio para la copia de la base, la instantanea (y su posterior en una reversion) y el codigo nuevo.
        var baseBytes = new[] { Rutas.BaseDeDatos, Rutas.BaseDeDatos + "-wal", Rutas.BaseDeDatos + "-shm" }.Where(File.Exists).Sum(f => new FileInfo(f).Length);
        var necesario = baseBytes + o.Archivos.Sum(a => a.Bytes) * 3 + 64L * 1024 * 1024;
        foreach (var carpeta in new[] { Rutas.CarpetaRespaldos, Rutas.CarpetaBackend })
        {
            try
            {
                var libre = new DriveInfo(Path.GetPathRoot(Path.GetFullPath(carpeta))!).AvailableFreeSpace;
                if (libre < necesario) throw new FalloDePaso(Pasos.Comprobar, $"No hay espacio: hacen falta {necesario / 1024 / 1024} MB y quedan {libre / 1024 / 1024} MB.");
            }
            catch (Exception error) when (error is IOException or ArgumentException) { /* sin medida no se bloquea */ }
        }
    }

    private static string LeerOrdenDe(string archivo)
    {
        try
        {
            using var d = JsonDocument.Parse(File.ReadAllText(archivo));
            return d.RootElement.TryGetProperty("orden_id", out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { return ""; }
    }

    /// <summary>true/false segun haya una clase abierta o suspendida; null si no se pudo saber. Lo responde el propio backend (classroom_engine) leyendo la base: no depende de una sesion.</summary>
    private bool? HayClase()
    {
        const string codigo =
            "import os, django\n" +
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'avacom_lms.settings')\n" +
            "django.setup()\n" +
            "from classroom_engine import servicios as s\n" +
            "print('CLASE=' + ('1' if s.hay_sesion_activa() else '0'))\n";
        var salida = Interprete.Ejecutar(_r, ["-c", codigo], TimeSpan.FromSeconds(90));
        if (salida.Codigo != 0) return null;
        var linea = salida.Texto.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.StartsWith("CLASE=", StringComparison.Ordinal));
        return linea switch { "CLASE=1" => true, "CLASE=0" => false, _ => null };
    }

    private void Respaldar(Contexto ctx)
    {
        try
        {
            ctx.Respaldo = Datos.Respaldar(_r, $"act-{ctx.Orden.OrdenId[..Math.Min(8, ctx.Orden.OrdenId.Length)]}");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            throw new FalloDePaso(Pasos.Respaldar, $"No se pudo copiar la base de datos: {error.Message}");
        }
        new Punto(ctx.Orden.OrdenId, ctx.Orden.PaqueteId, ctx.Orden.Accion, ctx.Fase, Pasos.Respaldar, ctx.Respaldo, ctx.IniciadoEn).Guardar();
        Inyeccion.Fallar(Pasos.Respaldar, 100);
    }

    private void HacerInstantanea(Contexto ctx)
    {
        Disco.BorrarCarpeta(ctx.Orden.Posterior);
        new Instantanea(ctx.Orden.Anterior).Crear(_r, ctx.Orden.PaqueteId, Manifiesto.Version(), ctx.Orden.Archivos.Select(a => a.Ruta),
            avance => { Inyeccion.Cortar(Pasos.Instantanea, avance); Inyeccion.Fallar(Pasos.Instantanea, avance); });
    }

    private void Copiar(Contexto ctx)
    {
        var o = ctx.Orden;
        if (!o.EsReversion)
        {
            for (var i = 0; i < o.Archivos.Count; i++)
            {
                var a = o.Archivos[i];
                Disco.CopiarVerificado(Disco.Confinar(o.Staging, a.Ruta), Disco.Confinar(Rutas.CarpetaBackend, a.Ruta), a.Sha256);
                var avance = (i + 1) * 100 / o.Archivos.Count;
                Inyeccion.Cortar(Pasos.Copiar, avance);
                Inyeccion.Fallar(Pasos.Copiar, avance);
            }
            _r.Escribir($"{o.Archivos.Count} archivo(s) copiados a Backend\\ con su huella comprobada.");
            return;
        }

        // Reversion: antes de poner el codigo viejo, el de ahora se guarda (por si hay que deshacer la reversion).
        var anterior = new Instantanea(o.Anterior);
        var indice = anterior.Leer() ?? throw new FalloDePaso(Pasos.Copiar, "La instantanea ya no esta completa.");
        new Instantanea(o.Posterior).Crear(_r, o.PaqueteId, Manifiesto.Version(), indice.Entradas.Select(e => e.Ruta));
        Inyeccion.Cortar(Pasos.Copiar, 50);
        Inyeccion.Fallar(Pasos.Copiar, 50);
        anterior.Restaurar(_r);
        Inyeccion.Cortar(Pasos.Copiar, 100);
        Inyeccion.Fallar(Pasos.Copiar, 100);
    }

    private void Migrar(Contexto ctx)
    {
        var o = ctx.Orden;
        TimeSpan Limite() => TimeSpan.FromSeconds(Math.Max(30, Math.Min(300, ctx.Restante.TotalSeconds)));

        if (!o.EsReversion)
        {
            // Antes de tocar la base, que Django lea el codigo nuevo entero (un error de sintaxis o un modulo que falta sale aqui, y no a mitad de una migracion).
            var revision = Interprete.Manage(_r, Limite(), "check");
            if (revision.Codigo != 0) throw new FalloDePaso(Pasos.Migrar, "La revision de configuracion de Django (check) fallo con el codigo nuevo.");
        }

        var modulos = o.EsReversion ? o.Modulos.Reverse().ToList() : o.Modulos.ToList();
        var total = Math.Max(1, modulos.Sum(m => m.Migraciones.Count));
        var hechas = 0;
        foreach (var modulo in modulos)
        {
            foreach (var migracion in modulo.Migraciones)
            {
                var objetivo = o.EsReversion ? migracion.Reverso : migracion.Nombre;
                var salida = Interprete.Manage(_r, Limite(), "migrate", modulo.Nombre, objetivo, "--noinput");
                ctx.Migraciones.Add(new MigracionHecha(modulo.Nombre, migracion.Nombre, salida.Codigo == 0));
                if (salida.Codigo != 0) throw new FalloDePaso(Pasos.Migrar, $"La migracion {modulo.Nombre} {objetivo} fallo (codigo {salida.Codigo}).");
                hechas++;
                var avance = hechas * 100 / total;
                Inyeccion.Cortar(Pasos.Migrar, avance);
                Inyeccion.Fallar(Pasos.Migrar, avance);
            }
        }
        Inyeccion.Cortar(Pasos.Migrar, 100);
        Inyeccion.Fallar(Pasos.Migrar, 100);
    }

    private void Verificar(Contexto ctx)
    {
        var o = ctx.Orden;
        // 1) Lo que hay en disco es exactamente lo que se queria.
        if (!o.EsReversion)
        {
            foreach (var a in o.Archivos)
            {
                var ruta = Disco.Confinar(Rutas.CarpetaBackend, a.Ruta);
                if (!File.Exists(ruta) || !string.Equals(Disco.Sha256DeArchivo(ruta), a.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new FalloDePaso(Pasos.Verificar, $"El archivo {a.Ruta} instalado no coincide con el del paquete.");
            }
        }
        else
        {
            VerificarContraInstantanea(new Instantanea(o.Anterior), Pasos.Verificar);
        }

        // 2) La base dice lo mismo: las migraciones del paquete estan aplicadas (o, en una reversion, ya no lo estan).
        var pares = o.Modulos.SelectMany(m => m.Migraciones.Select(g => new[] { m.Nombre, g.Nombre })).ToList();
        if (pares.Count > 0)
        {
            const string consulta =
                "import json, os, sqlite3, sys\n" +
                "c = sqlite3.connect(os.environ['AVACOM_LMS_DB'], timeout=15)\n" +
                "for app, nombre in json.loads(sys.argv[1]):\n" +
                "    n = c.execute('select count(*) from django_migrations where app=? and name=?', (app, nombre)).fetchone()[0]\n" +
                "    print('MIG|%s|%s|%d' % (app, nombre, n))\n" +
                "c.close()\n";
            var salida = Interprete.Ejecutar(_r, ["-c", consulta, JsonSerializer.Serialize(pares)], TimeSpan.FromSeconds(60));
            if (salida.Codigo != 0) throw new FalloDePaso(Pasos.Verificar, "No se pudo leer el historial de migraciones de la base.");
            foreach (var par in pares)
            {
                var linea = salida.Texto.Split('\n').Select(l => l.Trim()).FirstOrDefault(l => l.StartsWith($"MIG|{par[0]}|{par[1]}|", StringComparison.Ordinal));
                var aplicada = linea is not null && linea.EndsWith("|1", StringComparison.Ordinal);
                if (aplicada == o.EsReversion)
                    throw new FalloDePaso(Pasos.Verificar, o.EsReversion ? $"La migracion {par[0]} {par[1]} sigue aplicada tras la reversion." : $"La migracion {par[0]} {par[1]} no quedo aplicada.");
            }
        }

        // 3) El nodo arranca, responde y lee su base. Se arranca aparte y se apaga al terminar: el servicio lo levantara a su manera.
        Inyeccion.Cortar(Pasos.Verificar, 50);
        Inyeccion.Fallar(Pasos.Verificar, 50);
        var (ok, detalle) = ArrancarYComprobar(TimeSpan.FromSeconds(Math.Max(45, Math.Min(120, ctx.Restante.TotalSeconds))));
        if (!ok) throw new FalloDePaso(Pasos.Verificar, detalle);
        _r.Escribir("Verificacion: " + detalle);
    }

    private void VerificarContraInstantanea(Instantanea instantanea, string paso)
    {
        var indice = instantanea.Leer() ?? throw new FalloDePaso(paso, "La instantanea no esta completa.");
        foreach (var e in indice.Entradas)
        {
            var ruta = Disco.Confinar(Rutas.CarpetaBackend, e.Ruta);
            var bien = e.Existia
                ? File.Exists(ruta) && string.Equals(Disco.Sha256DeArchivo(ruta), e.Sha256, StringComparison.OrdinalIgnoreCase)
                : !File.Exists(ruta);
            if (!bien) throw new FalloDePaso(paso, $"El archivo {e.Ruta} no es el de la version anterior.");
        }
    }

    /// <summary>Arranca el backend (el mismo comando que el servicio), espera /health/, el canal en tiempo real y la lectura de la base, y lo apaga limpio.</summary>
    private (bool Ok, string Detalle) ArrancarYComprobar(TimeSpan limite)
    {
        var puerto = Configuracion.PuertoConfigurado();
        using var backend = new ProcesoBackend(_r);
        if (!backend.Iniciar()) return (false, "El backend no se pudo iniciar.");
        var salud = Salud.EsperarAsync(puerto, (int)limite.TotalSeconds).GetAwaiter().GetResult();
        if (!salud.Correcto) return (false, $"El backend no respondio: {salud.Detalle}.");
        var socket = Salud.ProbarWebSocketAsync(puerto).GetAwaiter().GetResult();
        if (!socket.Correcto) return (false, $"El canal en tiempo real no acepta conexiones: {socket.Detalle}.");
        var estado = Salud.EstadoAsync(puerto).GetAwaiter().GetResult();
        if (estado.Error is not null) return (false, $"El backend no puede leer su base de datos: {estado.Error}.");
        return (true, "el backend responde, el canal en tiempo real acepta conexiones y la base se lee");
    }

    // ------------------------------------------------------------------------------------------------------------- volver atras
    /// <summary>
    /// La reversion automatica (INV-008). En una aplicacion: el codigo desde la instantanea y, si la migracion llego a empezar, la base desde la copia. En una reversion
    /// manual que fallo: la base desde la copia y el codigo desde la instantanea «posterior». Despues se arranca el backend y se comprueba. Es idempotente (un corte a mitad se repite).
    /// </summary>
    private void Deshacer(Contexto ctx, string causa)
    {
        var o = ctx.Orden;
        var inicio = Stopwatch.StartNew();
        ctx.Fase = Punto.Retroceso;
        _r.Escribir($"--- Volviendo atras ({(o.EsReversion ? "la reversion fallo" : "la aplicacion fallo")}): {causa}");
        string? falloDeLaReversion = null;
        try
        {
            new Punto(o.OrdenId, o.PaqueteId, o.Accion, Punto.Retroceso, ctx.Paso, ctx.Respaldo, ctx.IniciadoEn).Guardar();
            var secuencia = o.Secuencia.ToList();
            var dbTocada = secuencia.IndexOf(ctx.Paso) >= ctx.IndiceDeMigrar;

            if (!o.EsReversion)
            {
                new Instantanea(o.Anterior).Restaurar(_r);
            }
            else if (new Instantanea(o.Posterior) is { Completa: true } posterior)
            {
                // La reversion cambio el codigo antes de fallar: el de antes de ella vuelve.
                posterior.Restaurar(_r);
            }

            if (dbTocada && ctx.Respaldo is not null)
            {
                if (!Datos.RestaurarDesde(_r, ctx.Respaldo)) throw new IOException("No se pudo restaurar la base de datos desde la copia.");
            }

            Inyeccion.Cortar("deshacer", 0);
            if (!o.EsReversion) VerificarContraInstantanea(new Instantanea(o.Anterior), "deshacer");
            var (ok, detalle) = ArrancarYComprobar(TimeSpan.FromSeconds(120));
            if (!ok) throw new FalloDePaso("deshacer", detalle);
            _r.Escribir($"Reversion automatica correcta en {inicio.Elapsed.TotalSeconds:0.0} s: {detalle}.");
        }
        catch (Exception error) when (error is FalloDePaso or IOException or UnauthorizedAccessException)
        {
            falloDeLaReversion = error.Message;
        }

        var duracion = $"La reversion tardo {inicio.Elapsed.TotalSeconds:0.0} s (la operacion entera, {ctx.Reloj.Elapsed.TotalSeconds:0.0} s; limite {o.LimiteMinutos} min).";
        if (falloDeLaReversion is not null)
        {
            // Nada se borra: el aula se queda con la copia de la base y con la instantanea, y se avisa (Q-U4).
            _r.Escribir($"LA REVERSION AUTOMATICA FALLO: {falloDeLaReversion}. No se borro nada: la copia esta en {ctx.Respaldo ?? "(sin copia)"} y la instantanea en {o.CarpetaDeVersion}.");
            Terminar(ctx, "reversion_fallida", $"Fallo ({causa}) y tampoco se pudo volver atras: {falloDeLaReversion}. {duracion}", $"{causa} | {falloDeLaReversion}");
            return;
        }

        if (o.EsReversion)
            Terminar(ctx, "reversion_fallida", $"La reversion fallo ({causa}); el aula volvio a como estaba antes de intentarla. {duracion}", causa);
        else
            Terminar(ctx, "revertido", $"La aplicacion fallo ({causa}) y el aula volvio sola a la version anterior (INV-008). {duracion}", causa);
    }

    // ------------------------------------------------------------------------------------------------------------- recuperacion tras un corte (A4)
    /// <summary>
    /// Al arrancar el servicio, ANTES de levantar el backend: si quedo un checkpoint de una orden sin resultado, el host murio a mitad. Antes del primer paso que cambia algo se
    /// vuelve a empezar; en «verificar» se repite la verificacion; en cualquier otro punto se vuelve atras. Un backend no se levanta sobre un codigo a medias.
    /// </summary>
    public void Recuperar()
    {
        var punto = Punto.Leer();
        if (punto is null)
        {
            if (File.Exists(Punto.Ruta)) { _r.Escribir("checkpoint.json es ilegible: se retira (sin orden que recuperar)."); Punto.Borrar(); }
            return;
        }
        if (File.Exists(RutaDeResultado) && LeerOrdenDe(RutaDeResultado) == punto.OrdenId)
        {
            _r.Escribir($"La orden {punto.OrdenId} ya tiene resultado: se retira el checkpoint.");
            Punto.Borrar();
            return;
        }
        Orden orden;
        try
        {
            if (!File.Exists(RutaDeOrden))
            {
                _r.Escribir($"Checkpoint de la orden {punto.OrdenId} sin orden.json: ya la cerro el backend; se retira.");
                Punto.Borrar();
                return;
            }
            orden = Orden.Leer(RutaDeOrden);
        }
        catch (OrdenInvalida error)
        {
            _r.Escribir("No se puede recuperar: " + error.Message);
            return;
        }
        if (orden.OrdenId != punto.OrdenId)
        {
            _r.Escribir($"El checkpoint es de la orden {punto.OrdenId} y orden.json es de otra ({orden.OrdenId}): se retira el checkpoint.");
            Punto.Borrar();
            return;
        }

        _r.Escribir($"=== Recuperacion: el host se detuvo en el paso «{punto.Paso}» ({punto.Fase}) de la orden {orden.OrdenId} ===");
        var ctx = new Contexto(orden) { Paso = punto.Paso, Fase = punto.Fase, Respaldo = punto.Respaldo, IniciadoEn = punto.IniciadoEn };
        var indice = orden.Secuencia.ToList().IndexOf(punto.Paso);
        if (indice < 0) { Deshacer(ctx, "checkpoint con un paso desconocido"); return; }

        if (punto.Fase == Punto.Retroceso)
        {
            Deshacer(ctx, "la reversion se corto: se repite");
        }
        else if (indice < ctx.PrimerPasoQueCambia)
        {
            _r.Escribir("Todavia no se habia cambiado nada: se reanuda la orden desde el principio.");
            ctx.Respaldo = null;
            if (ComprobarYDecidir(ctx, vivo: false)) Correr(ctx, desde: 1);
        }
        else if (punto.Paso == Pasos.Verificar)
        {
            _r.Escribir("Todo estaba aplicado y solo faltaba verificar: se repite la verificacion.");
            Correr(ctx, desde: indice);
        }
        else
        {
            Deshacer(ctx, $"el host se detuvo a mitad del paso «{punto.Paso}»");
        }
    }

    // ------------------------------------------------------------------------------------------------------------- el resultado
    private void Terminar(Contexto ctx, string resultado, string detalle, string? error)
    {
        var o = ctx.Orden;
        var terminado = Disco.Ahora();
        var texto = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["formato"] = 1,
            ["orden_id"] = o.OrdenId,
            ["paquete_id"] = o.PaqueteId,
            ["accion"] = o.Accion,
            ["resultado"] = resultado,
            ["paso"] = ctx.Paso,
            ["iniciado_en"] = ctx.IniciadoEn,
            ["terminado_en"] = Math.Max(terminado, ctx.IniciadoEn),
            ["duracion_ms"] = Math.Max(0, (long)ctx.Reloj.Elapsed.TotalMilliseconds),
            ["detalle"] = detalle,
            ["respaldo"] = ctx.Respaldo,
            ["migraciones"] = ctx.Migraciones.Select(m => new Dictionary<string, object?> { ["modulo"] = m.Modulo, ["nombre"] = m.Nombre, ["ok"] = m.Ok }).ToList(),
            ["error"] = error,
        }, new JsonSerializerOptions { WriteIndented = true });
        Disco.EscribirAtomico(RutaDeResultado, texto);
        Punto.Borrar();
        _r.Escribir($"Resultado «{resultado}» en el paso «{ctx.Paso}» ({ctx.Reloj.Elapsed.TotalSeconds:0.0} s): {detalle}");
    }

    /// <summary>
    /// Una orden que no se puede ni leer: si al menos dice de quien es, se devuelve «rechazada» para que el backend la cierre y levante el 503 del inicio de clases;
    /// si ni eso, solo se anota (el backend cierra una orden huerfana a los 10 minutos si desaparece).
    /// </summary>
    public void RechazarOrdenIlegible(string motivo)
    {
        _r.Escribir("orden.json no se puede obedecer: " + motivo);
        try
        {
            using var d = JsonDocument.Parse(File.ReadAllText(RutaDeOrden));
            var r = d.RootElement;
            string T(string n) => r.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
            var ordenId = T("orden_id");
            var paqueteId = T("paquete_id");
            var accion = T("accion") is Orden.Revertir ? Orden.Revertir : Orden.Aplicar;
            if (ordenId.Length == 0 || paqueteId.Length == 0) return;
            var ahora = Disco.Ahora();
            Disco.EscribirAtomico(RutaDeResultado, JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["formato"] = 1, ["orden_id"] = ordenId, ["paquete_id"] = paqueteId, ["accion"] = accion, ["resultado"] = "rechazada", ["paso"] = Pasos.Comprobar,
                ["iniciado_en"] = ahora, ["terminado_en"] = ahora, ["duracion_ms"] = 0, ["detalle"] = "El host no pudo obedecer la orden: " + motivo, ["respaldo"] = null,
                ["migraciones"] = new List<object>(), ["error"] = motivo,
            }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException)
        {
            _r.Escribir("Tampoco se pudo dejar un resultado para ella", error);
        }
    }

    // ------------------------------------------------------------------------------------------------------------- 14 dias (P-09)
    private static readonly TimeSpan PlazoDeReversion = TimeSpan.FromDays(14) + TimeSpan.FromHours(1);

    /// <summary>
    /// Retira las instantaneas de mas de 14 dias (el backend las deja «archivadas» en el mismo momento; el margen de una hora cubre la diferencia entre sus relojes). Nunca la de una
    /// orden en curso ni la de un paquete cuya reversion fallo (esa se conserva hasta que alguien la resuelva).
    /// </summary>
    public void Mantenimiento()
    {
        try
        {
            var versiones = Path.Combine(Rutas.CarpetaActualizaciones, "versiones");
            if (!Directory.Exists(versiones)) return;
            var enCurso = File.Exists(RutaDeOrden) ? SafeOrdenPaquete() : null;
            var conservar = PaquetesConReversionFallida();
            foreach (var carpeta in Directory.GetDirectories(versiones))
            {
                var id = Path.GetFileName(carpeta);
                if (id == enCurso || conservar.Contains(id)) continue;
                var indice = new Instantanea(Path.Combine(carpeta, "anterior")).Leer();
                // Sin indice: una instantanea que nunca se completo (o un resto) sin orden que la espere; se retira cuando es vieja.
                var creada = indice is not null ? DateTimeOffset.FromUnixTimeMilliseconds(indice.CreadoEn) : new DirectoryInfo(carpeta).CreationTimeUtc;
                if (DateTimeOffset.UtcNow - creada <= PlazoDeReversion) continue;
                _r.Escribir($"La instantanea del paquete {id} cumplio 14 dias: se retira.");
                Disco.BorrarCarpeta(carpeta);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            _r.Escribir("No se pudo hacer el mantenimiento de las instantaneas", error);
        }
    }

    private static string? SafeOrdenPaquete()
    {
        try
        {
            using var d = JsonDocument.Parse(File.ReadAllText(RutaDeOrden));
            return d.RootElement.TryGetProperty("paquete_id", out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { return null; }
    }

    private static HashSet<string> PaquetesConReversionFallida()
    {
        var salida = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var carpeta = Path.Combine(Rutas.CarpetaActualizaciones, "resultados");
        var archivos = Directory.Exists(carpeta) ? Directory.GetFiles(carpeta, "*.json") : [];
        if (File.Exists(RutaDeResultado)) archivos = [.. archivos, RutaDeResultado];
        foreach (var archivo in archivos)
        {
            try
            {
                using var d = JsonDocument.Parse(File.ReadAllText(archivo));
                var r = d.RootElement;
                if (r.TryGetProperty("resultado", out var res) && res.GetString() == "reversion_fallida" && r.TryGetProperty("paquete_id", out var p) && p.GetString() is { } id)
                    salida.Add(id);
            }
            catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { }
        }
        return salida;
    }
}
