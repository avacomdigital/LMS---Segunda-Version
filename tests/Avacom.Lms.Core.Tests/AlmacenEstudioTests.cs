using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Tests;

/// <summary>El almacén local cifrado: lista, tareas, paquetes y medios ida y vuelta; nada en claro; clave destruida; vigencia; borrado.</summary>
public sealed class AlmacenEstudioTests : IDisposable
{
    private const int B = ArchivoCifrado.LongitudBloque;
    private const string Ana = "ana-perez";
    private const string Beto = "beto-ruiz";

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly ProveedorDeClaveEnMemoria proveedor = new();
    private long ahora = 1_000;
    private readonly AlmacenEstudio almacen;
    private readonly List<string> avisos = [];

    public AlmacenEstudioTests()
    {
        almacen = EstudioAyudas.Almacen(carpeta, proveedor, () => ahora);
        almacen.Cambio += alumno => { lock (avisos) avisos.Add(alumno); };
    }

    public void Dispose() { try { Directory.Delete(carpeta, true); } catch { } }

    private string Raiz => Path.Combine(carpeta, "almacen");

    private static AsignacionAlumno Asignacion(string id = "asig-1", string titulo = "Área y volumen con lenguaje algebraico") =>
        new(id, titulo, null, "Calcula áreas y volúmenes", "Matemáticas", "Unidad 2", new CursoDeAsignacion("biblioteca", "curso-1", "1.0.0", "Matemáticas 6"), "l1",
            1_759_600_000_000, "blando", 900_000, "activa", "Ms. Carter", 1_759_000_000_000, null, null, null, null, null, null);

    private static AsignacionesEstudio Lista(params AsignacionAlumno[] asignaciones) =>
        new(new AlumnoEstudio(Ana, "Ana Pérez"), asignaciones, new ResumenEstudio(asignaciones.Length, 0, 0), 123);

    private static TareaLocal Tarea(string asignacionId = "asig-1") =>
        new(asignacionId, ["b1", "b2", "b3"], "b3", 208, false, 555,
        [
            new PracticaLocal("act-1", 2, "en_curso",
                new Dictionary<string, RespuestaLocal>
                {
                    ["q1"] = new(Ayudas.Json("""{"value":"a"}"""), 1, new VeredictoEstudio("q1", true, 1.5, 1.5, false, ["¡Bien!"])),
                    ["q2"] = new(Ayudas.Json("""{"value":["x","y"]}"""), 2, null),
                }, 8, false, null),
        ]);

    private static IReadOnlyList<ArchivoDePrueba> Archivos() =>
    [
        new("img-portada", EstudioAyudas.Datos(3 * B + 4321, 21), "image/png"),
        new("vid-intro", EstudioAyudas.Datos(70_000, 22), "video/mp4"),
        new("audio-corto", EstudioAyudas.Datos(9, 23), "audio/mpeg"),
    ];

    // ------------------------------------------------------------------------- lista y tareas

    [Fact]
    public void LaLista_IdaYVuelta_SinTextoEnClaro_NiElIdEnLasRutas()
    {
        Assert.Null(almacen.LeerLista(Ana));
        almacen.GuardarLista(Ana, Lista(Asignacion()));

        var leida = almacen.LeerLista(Ana)!;
        Assert.Equal("Ana Pérez", leida.Alumno!.Rotulo);
        Assert.Equal(123, leida.ServidorEn);
        var asignacion = Assert.Single(leida.Asignaciones);
        Assert.Equal(("asig-1", "Área y volumen con lenguaje algebraico", "Ms. Carter", "Unidad 2"), (asignacion.Id, asignacion.Titulo, asignacion.Profesor, asignacion.Unidad));
        Assert.Equal("curso-1", asignacion.Curso!.CursoRef);
        Assert.Null(almacen.LeerLista(Beto));                                       // cada alumno, lo suyo

        var archivos = EstudioAyudas.Archivos(Raiz).ToList();
        Assert.NotEmpty(archivos);
        foreach (var ruta in archivos)
        {
            Assert.DoesNotContain(Ana, ruta, StringComparison.OrdinalIgnoreCase);   // nada de identificadores en las rutas
            var bytes = File.ReadAllBytes(ruta);
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes("Área y volumen")));
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes("volumen")));
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes(Ana)));
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes("Ana P")));
        }
        Assert.Equal([Ana], avisos);
    }

    [Fact]
    public void LaTarea_IdaYVuelta_ConSusPracticasYRespuestas()
    {
        Assert.Null(almacen.LeerTarea(Ana, "asig-1"));
        almacen.GuardarTarea(Ana, Tarea("asig-1"));
        almacen.GuardarTarea(Ana, Tarea("asig-2") with { Completada = true });

        var tarea = almacen.LeerTarea(Ana, "asig-1")!;
        Assert.Equal(["b1", "b2", "b3"], tarea.BloquesVistos.ToArray());
        Assert.Equal(("b3", 208, false, 555L), (tarea.UltimoBloqueRef, tarea.PosicionSeg, tarea.Completada, tarea.ActualizadoEn));
        var practica = Assert.Single(tarea.Practicas);
        Assert.Equal(("act-1", 2, "en_curso", 8), (practica.ObjetoRef, practica.Numero, practica.Estado, practica.TotalPreguntas));
        Assert.Equal(["q1", "q2"], practica.Respuestas.Keys.OrderBy(k => k).ToArray());
        Assert.Equal("a", practica.Respuestas["q1"].Respuesta.GetProperty("value").GetString());
        Assert.True(practica.Respuestas["q1"].Veredicto!.Correcta);
        Assert.Equal(["¡Bien!"], practica.Respuestas["q1"].Veredicto!.Retroalimentacion!.ToArray());
        Assert.Null(practica.Respuestas["q2"].Veredicto);
        Assert.Equal(2, practica.Respuestas["q2"].Secuencia);
        Assert.True(almacen.LeerTarea(Ana, "asig-2")!.Completada);
        Assert.Null(almacen.LeerTarea(Ana, "asig-3"));
        Assert.Null(almacen.LeerTarea(Beto, "asig-1"));
    }

    [Fact]
    public void UnDocumentoCambiadoDeLugar_NoAutentica_ComoSiNoEstuviera()
    {
        almacen.GuardarTarea(Ana, Tarea("asig-1"));
        almacen.GuardarTarea(Ana, Tarea("asig-2"));
        var dos = Directory.GetFiles(Raiz, "tarea-*.avc", SearchOption.AllDirectories);
        Assert.Equal(2, dos.Length);
        var (a, b) = (File.ReadAllBytes(dos[0]), File.ReadAllBytes(dos[1]));
        File.WriteAllBytes(dos[0], b);                                               // se intercambian los archivos de dos tareas
        File.WriteAllBytes(dos[1], a);
        Assert.Null(almacen.LeerTarea(Ana, "asig-1"));
        Assert.Null(almacen.LeerTarea(Ana, "asig-2"));
    }

    [Fact]
    public void UnArchivoCorrupto_SeTrataComoAusente_YSeApartaSinLanzar()
    {
        almacen.GuardarLista(Ana, Lista(Asignacion()));
        almacen.GuardarTarea(Ana, Tarea());
        var lista = Directory.GetFiles(Raiz, "lista.avc", SearchOption.AllDirectories).Single();
        File.WriteAllText(lista, "esto no es un documento cifrado");
        var tarea = Directory.GetFiles(Raiz, "tarea-*.avc", SearchOption.AllDirectories).Single();
        var bytes = File.ReadAllBytes(tarea);
        bytes[^3] ^= 0x10;
        File.WriteAllBytes(tarea, bytes);

        Assert.Null(almacen.LeerLista(Ana));
        Assert.Null(almacen.LeerTarea(Ana, "asig-1"));
        Assert.True(File.Exists(lista + ".dañado"));
        Assert.True(File.Exists(tarea + ".dañado"));
        Assert.False(File.Exists(lista));

        almacen.GuardarLista(Ana, Lista(Asignacion()));                             // y se puede seguir guardando
        Assert.NotNull(almacen.LeerLista(Ana));
        Assert.Equal(0, almacen.BytesUsados("otro"));
    }

    // -------------------------------------------------------------------------- paquetes

    [Fact]
    public void UnPaqueteCompleto_ManifiestoYArchivos_IdaYVuelta_SinNadaEnClaro()
    {
        var archivos = Archivos();
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", archivos);

        var paquete = almacen.ObtenerPaquete(Ana, "asig-1")!;
        Assert.True(paquete.Disponible);
        Assert.Equal(("paq-asig-1", "disponible", "1.0.0"), (paquete.PaqueteId, paquete.Estado, paquete.CursoVersion));
        Assert.Equal(archivos.Sum(a => (long)a.Datos.Length), paquete.BytesTotal);
        Assert.Equal(paquete.BytesTotal, paquete.BytesDescargados);
        Assert.Equal(1.0, paquete.Fraccion);
        Assert.Single(almacen.ListarPaquetes(Ana));
        Assert.Empty(almacen.ListarPaquetes(Beto));
        Assert.Null(almacen.ObtenerPaquete(Ana, "asig-2"));

        var manifiesto = almacen.LeerManifiesto(Ana, "asig-1")!;
        Assert.Equal(("paq-asig-1", "l1"), (manifiesto.PaqueteId, manifiesto.LeccionRef));
        Assert.Equal(["img-portada", "vid-intro", "audio-corto"], manifiesto.Archivos.Select(a => a.MediaRef).ToArray());
        Assert.Equal("Los tres estados · ñandú", manifiesto.Leccion.GetProperty("titulo").GetString());
        Assert.Equal(EstudioAyudas.ManifiestoCrudo("paq-asig-1", "asig-1", archivos), almacen.LeerManifiestoCrudo(Ana, "asig-1"));   // el texto original, idéntico

        foreach (var a in archivos)
        {
            Assert.Equal((a.Datos.Length, a.Mime), almacen.InfoArchivo(Ana, "asig-1", a.MediaRef)!.Value);
            using var flujo = almacen.AbrirArchivo(Ana, "asig-1", a.MediaRef)!;
            Assert.Equal(a.Datos.Length, flujo.Length);
            Assert.Equal(a.Datos, EstudioAyudas.LeerTodo(flujo));
        }
        Assert.Null(almacen.AbrirArchivo(Ana, "asig-1", "no-existe"));
        Assert.Null(almacen.InfoArchivo(Ana, "asig-1", "no-existe"));
        Assert.Null(almacen.AbrirArchivo(Beto, "asig-1", "img-portada"));
        Assert.Null(almacen.LeerManifiesto(Beto, "asig-1"));

        foreach (var ruta in EstudioAyudas.Archivos(Raiz))
        {
            Assert.DoesNotContain(Ana, ruta, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("img-portada", ruta, StringComparison.OrdinalIgnoreCase);
            var bytes = File.ReadAllBytes(ruta);
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes("ñandú")));
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes("img-portada")));
            Assert.False(EstudioAyudas.Contiene(bytes, archivos[1].Datos.AsSpan(100, 32).ToArray()));
        }
    }

    [Fact]
    public void UnPaqueteAMedias_ReportaLoBajado_SinDescifrar_YSePuedeReanudar()
    {
        var archivos = Archivos();
        var paquete = EstudioAyudas.Paquete("paq-1", "asig-1", archivos);
        almacen.RegistrarPaquete(Ana, paquete);
        var crudo = EstudioAyudas.ManifiestoCrudo("paq-1", "asig-1", archivos);
        almacen.GuardarManifiesto(Ana, "asig-1", crudo, JsonSerializer.Deserialize<ManifiestoPaquete>(crudo, Ayudas.Web)!);

        var grande = archivos[0];
        using (var escritor = almacen.AbrirEscritura(Ana, "asig-1", grande.MediaRef)) escritor.Escribir(grande.Datos.AsSpan(0, 2 * B + 999));   // una pausa: 2 bloques a salvo

        var enCurso = almacen.ObtenerPaquete(Ana, "asig-1")!;
        Assert.Equal(("descargando", 2L * B), (enCurso.Estado, enCurso.BytesDescargados));
        Assert.False(enCurso.Disponible);
        Assert.True(enCurso.Fraccion is > 0 and < 1);
        Assert.Null(almacen.LeerManifiesto(Ana, "asig-1"));                           // aún no está completo
        Assert.Null(almacen.AbrirArchivo(Ana, "asig-1", grande.MediaRef));
        Assert.Equal((false, 2L * B), almacen.EstadoDeArchivo(Ana, "asig-1", grande.MediaRef));
        Assert.Equal(crudo.Length, almacen.LeerManifiestoCrudo(Ana, "asig-1")!.Length);

        using (var escritor = almacen.AbrirEscritura(Ana, "asig-1", grande.MediaRef))
        {
            Assert.Equal(2 * B, escritor.BytesEnClaro);                              // reanuda donde quedó
            escritor.Escribir(grande.Datos.AsSpan(2 * B));
            escritor.Cerrar();
        }
        almacen.CompletarArchivo(Ana, "asig-1", grande.MediaRef);
        Assert.Equal((true, (long)grande.Datos.Length), almacen.EstadoDeArchivo(Ana, "asig-1", grande.MediaRef));
        Assert.Throws<InvalidOperationException>(() => almacen.MarcarDisponible(Ana, "asig-1"));   // faltan los otros dos archivos

        foreach (var a in archivos.Skip(1))
        {
            using (var escritor = almacen.AbrirEscritura(Ana, "asig-1", a.MediaRef)) { escritor.Escribir(a.Datos); escritor.Cerrar(); }
            almacen.CompletarArchivo(Ana, "asig-1", a.MediaRef);
        }
        almacen.MarcarDisponible(Ana, "asig-1");
        using var flujo = almacen.AbrirArchivo(Ana, "asig-1", grande.MediaRef)!;
        Assert.Equal(grande.Datos, EstudioAyudas.LeerTodo(flujo));
    }

    [Fact]
    public void CompletarUnArchivoSinCerrar_OSinDescargar_Lanza()
    {
        var archivos = Archivos();
        almacen.RegistrarPaquete(Ana, EstudioAyudas.Paquete("paq-1", "asig-1", archivos));
        var crudo = EstudioAyudas.ManifiestoCrudo("paq-1", "asig-1", archivos);
        almacen.GuardarManifiesto(Ana, "asig-1", crudo, JsonSerializer.Deserialize<ManifiestoPaquete>(crudo, Ayudas.Web)!);
        Assert.Throws<InvalidOperationException>(() => almacen.CompletarArchivo(Ana, "asig-1", "vid-intro"));   // no hay nada descargado
        using (var escritor = almacen.AbrirEscritura(Ana, "asig-1", "vid-intro"))
        {
            escritor.Escribir(archivos[1].Datos);                                       // se escribió todo pero NO se cerró: falta la cola
            Assert.Throws<InvalidOperationException>(() => almacen.CompletarArchivo(Ana, "asig-1", "vid-intro"));
        }
        Assert.Throws<ArgumentException>(() => almacen.AbrirEscritura(Ana, "asig-1", "no-esta-en-el-manifiesto"));
        Assert.Throws<InvalidOperationException>(() => almacen.AbrirEscritura(Ana, "asig-2", "vid-intro"));      // paquete no registrado
    }

    [Fact]
    public void EliminarElPaquete_NoTocaElAvanceLocalDeLaTarea_NiLoDeOtroAlumno()
    {
        almacen.GuardarTarea(Ana, Tarea());
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", Archivos());
        EstudioAyudas.InstalarPaquete(almacen, Beto, "asig-1", Archivos());
        var antes = almacen.BytesUsados(Ana);
        avisos.Clear();

        almacen.EliminarPaquete(Ana, "asig-1");

        Assert.Null(almacen.ObtenerPaquete(Ana, "asig-1"));
        Assert.Null(almacen.AbrirArchivo(Ana, "asig-1", "img-portada"));
        Assert.NotNull(almacen.LeerTarea(Ana, "asig-1"));                           // el avance local sigue
        Assert.NotNull(almacen.ObtenerPaquete(Beto, "asig-1"));
        Assert.True(almacen.BytesUsados(Ana) < antes / 10);
        Assert.Contains(Ana, avisos);
        almacen.EliminarPaquete(Ana, "asig-1");                                     // repetirlo no falla
    }

    [Fact]
    public void LiberarVencidos_UsaElRelojDelNodoQueSePasa_YCuentaLoLiberado()
    {
        var archivos = Archivos();
        EstudioAyudas.InstalarPaquete(almacen, Ana, "a-vence-pronto", archivos, vigenteHasta: 2_000);
        EstudioAyudas.InstalarPaquete(almacen, Ana, "b-vence-luego", archivos, vigenteHasta: 9_000);
        EstudioAyudas.InstalarPaquete(almacen, Ana, "c-sin-fecha", archivos, vigenteHasta: null);
        var total = almacen.BytesUsados(Ana);

        Assert.Equal((0, 0L), almacen.LiberarVencidos(Ana, 1_500));               // todavía todos vigentes
        Assert.Equal("disponible", almacen.ObtenerPaquete(Ana, "a-vence-pronto")!.Estado);

        ahora = 2_500;                                                              // el reloj del almacén también dice que el primero ya venció
        Assert.Equal("vencido", almacen.ObtenerPaquete(Ana, "a-vence-pronto")!.Estado);
        Assert.Equal("disponible", almacen.ObtenerPaquete(Ana, "b-vence-luego")!.Estado);

        var (paquetes, bytes) = almacen.LiberarVencidos(Ana, 2_500);
        Assert.Equal(1, paquetes);
        Assert.Equal(total - almacen.BytesUsados(Ana), bytes);
        Assert.True(bytes > 100_000);
        Assert.Null(almacen.ObtenerPaquete(Ana, "a-vence-pronto"));
        Assert.NotNull(almacen.ObtenerPaquete(Ana, "b-vence-luego"));
        Assert.NotNull(almacen.ObtenerPaquete(Ana, "c-sin-fecha"));

        Assert.Equal(1, almacen.LiberarVencidos(Ana, 99_000).Paquetes);             // el de la fecha lejana también; el que no tiene fecha, nunca
        Assert.NotNull(almacen.ObtenerPaquete(Ana, "c-sin-fecha"));
        Assert.Null(almacen.ObtenerPaquete(Ana, "b-vence-luego"));
    }

    [Fact]
    public void LaClaveDestruida_DejaTodoAusente_YElAlmacenSigueSirviendo()
    {
        almacen.GuardarLista(Ana, Lista(Asignacion()));
        almacen.GuardarTarea(Ana, Tarea());
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", Archivos());
        Assert.NotNull(almacen.ObtenerPaquete(Ana, "asig-1"));

        proveedor.Destruir();                                                       // BR-053: lo cifrado con la clave anterior queda ilegible

        Assert.Null(almacen.LeerLista(Ana));
        Assert.Null(almacen.LeerTarea(Ana, "asig-1"));
        Assert.Null(almacen.ObtenerPaquete(Ana, "asig-1"));
        Assert.Empty(almacen.ListarPaquetes(Ana));
        Assert.Null(almacen.LeerManifiesto(Ana, "asig-1"));
        Assert.Null(almacen.AbrirArchivo(Ana, "asig-1", "img-portada"));
        Assert.Null(almacen.InfoArchivo(Ana, "asig-1", "img-portada"));

        almacen.GuardarLista(Ana, Lista(Asignacion("asig-9", "Otra lección")));    // con la clave nueva todo vuelve a funcionar
        Assert.Equal("asig-9", almacen.LeerLista(Ana)!.Asignaciones[0].Id);
    }

    [Fact]
    public void Destruir_DestruyeLaClaveYBorraLaCarpeta_YAvisaQueCambioTodo()
    {
        almacen.GuardarLista(Ana, Lista(Asignacion()));
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", Archivos());
        Assert.True(Directory.Exists(Raiz));
        avisos.Clear();

        almacen.Destruir();

        Assert.Equal(1, proveedor.Destrucciones);
        Assert.False(Directory.Exists(Raiz));
        Assert.Contains("", avisos);
        Assert.Null(almacen.LeerLista(Ana));
        Assert.Empty(almacen.ListarPaquetes(Ana));
        Assert.Equal(0, almacen.BytesUsados(Ana));
        almacen.GuardarLista(Ana, Lista(Asignacion()));                            // y sigue siendo usable
        Assert.NotNull(almacen.LeerLista(Ana));
    }

    [Fact]
    public void Destruir_SoloBorraLoQueCreoElAlmacen_YNoLoQueOtroDejoEnLaMismaCarpeta()
    {
        almacen.GuardarLista(Ana, Lista(Asignacion()));
        var ajeno = Path.Combine(Raiz, "notas-del-usuario.txt");
        File.WriteAllText(ajeno, "esto no es del almacén");

        almacen.Destruir();

        Assert.True(File.Exists(ajeno));
        Assert.Empty(Directory.GetDirectories(Raiz));
        Assert.Null(almacen.LeerLista(Ana));
    }

    [Fact]
    public void OlvidarAlumno_BorraTodoLoDeEseAlumno_ySoloLoDeEl()
    {
        foreach (var alumno in new[] { Ana, Beto })
        {
            almacen.GuardarLista(alumno, Lista(Asignacion()));
            almacen.GuardarTarea(alumno, Tarea());
            EstudioAyudas.InstalarPaquete(almacen, alumno, "asig-1", Archivos());
        }
        Assert.True(almacen.BytesUsados(Ana) > 100_000);

        almacen.OlvidarAlumno(Ana);

        Assert.Equal(0, almacen.BytesUsados(Ana));
        Assert.Null(almacen.LeerLista(Ana));
        Assert.Null(almacen.LeerTarea(Ana, "asig-1"));
        Assert.Empty(almacen.ListarPaquetes(Ana));
        Assert.NotNull(almacen.LeerLista(Beto));
        Assert.NotNull(almacen.LeerTarea(Beto, "asig-1"));
        Assert.NotNull(almacen.ObtenerPaquete(Beto, "asig-1"));
    }

    [Fact]
    public void UnArchivoTruncadoEnElDisco_InvalidaElPaquete_YLaProximaDescargaLoRepone()
    {
        var archivos = Archivos();
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", archivos);
        var medios = Directory.GetFiles(Raiz, "m-*.avc", SearchOption.AllDirectories);
        var mediano = medios.OrderBy(m => new FileInfo(m).Length).Skip(1).First();          // el de 70 000 bytes
        var bytes = File.ReadAllBytes(mediano);
        File.WriteAllBytes(mediano, bytes[..^100]);                                          // se le comieron 100 bytes

        Assert.Null(almacen.InfoArchivo(Ana, "asig-1", "vid-intro"));
        Assert.Equal("pausado", almacen.ObtenerPaquete(Ana, "asig-1")!.Estado);              // ya no está completo
        Assert.Null(almacen.LeerManifiesto(Ana, "asig-1"));
        Assert.Equal((false, 0L), almacen.EstadoDeArchivo(Ana, "asig-1", "vid-intro"));
        Assert.Equal((true, (long)archivos[0].Datos.Length), almacen.EstadoDeArchivo(Ana, "asig-1", "img-portada"));   // lo demás sigue bien
    }

    [Fact]
    public void UnManifiestoIlegible_DejaDeSerDisponible_SinLanzar()
    {
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", Archivos());
        var manifiesto = Directory.GetFiles(Raiz, "manifiesto.avc", SearchOption.AllDirectories).Single();
        File.WriteAllText(manifiesto, "basura");

        Assert.Null(almacen.LeerManifiesto(Ana, "asig-1"));
        Assert.Equal("pausado", almacen.ObtenerPaquete(Ana, "asig-1")!.Estado);              // la descarga siguiente rebaja el manifiesto
        Assert.True(File.Exists(manifiesto + ".dañado"));
    }

    [Fact]
    public void UnManifiestoNuevo_ConciliaLosArchivos_ConservaLosQueNoCambiaron()
    {
        var archivos = Archivos();
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", archivos);

        var cambiado = new ArchivoDePrueba("vid-intro", EstudioAyudas.Datos(70_000, 99), "video/mp4");     // mismo medio, otro contenido
        var nuevo = new ArchivoDePrueba("mapa", EstudioAyudas.Datos(500, 98), "image/png");
        IReadOnlyList<ArchivoDePrueba> segunda = [archivos[0], cambiado, nuevo];                          // el audio ya no forma parte del paquete
        var crudo = EstudioAyudas.ManifiestoCrudo("paq-asig-1", "asig-1", segunda);
        almacen.GuardarManifiesto(Ana, "asig-1", crudo, JsonSerializer.Deserialize<ManifiestoPaquete>(crudo, Ayudas.Web)!);

        Assert.Equal((true, (long)archivos[0].Datos.Length), almacen.EstadoDeArchivo(Ana, "asig-1", "img-portada"));   // sin cambios: se conserva
        Assert.Equal((false, 0L), almacen.EstadoDeArchivo(Ana, "asig-1", "vid-intro"));                                 // cambió: se tira lo anterior
        Assert.Equal((false, 0L), almacen.EstadoDeArchivo(Ana, "asig-1", "mapa"));
        Assert.Equal((false, 0L), almacen.EstadoDeArchivo(Ana, "asig-1", "audio-corto"));                               // ya no está
        Assert.Single(Directory.GetFiles(Raiz, "m-*", SearchOption.AllDirectories));                                    // sólo queda un archivo de medios
        var paquete = almacen.ObtenerPaquete(Ana, "asig-1")!;
        Assert.Equal("descargando", paquete.Estado);                                 // otra huella: hay que bajar lo que falta
        Assert.Equal(segunda.Sum(a => (long)a.Datos.Length), paquete.BytesTotal);
    }

    [Fact]
    public void RegistrarOtroPaquete_ParaLaMismaAsignacion_EmpiezaDeCero()
    {
        var archivos = Archivos();
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", archivos);
        almacen.RegistrarPaquete(Ana, EstudioAyudas.Paquete("paq-otro", "asig-1", archivos));
        var paquete = almacen.ObtenerPaquete(Ana, "asig-1")!;
        Assert.Equal(("paq-otro", "descargando"), (paquete.PaqueteId, paquete.Estado));
        Assert.Equal(0, paquete.BytesDescargados);
        Assert.Empty(Directory.GetFiles(Raiz, "m-*", SearchOption.AllDirectories));
    }

    [Fact]
    public void PublicarEstado_NoDegradaUnPaqueteDisponible_PeroSiLoVence()
    {
        EstudioAyudas.InstalarPaquete(almacen, Ana, "asig-1", Archivos());
        almacen.PublicarEstado(Ana, "asig-1", "pausado");
        Assert.Equal("disponible", almacen.ObtenerPaquete(Ana, "asig-1")!.Estado);
        almacen.PublicarEstado(Ana, "asig-1", "vencido");                            // el nodo dijo 410
        Assert.Equal("vencido", almacen.ObtenerPaquete(Ana, "asig-1")!.Estado);
        Assert.Equal(1, almacen.LiberarVencidos(Ana, 0).Paquetes);                   // «vencido» por decir el nodo 410 se libera aunque la fecha no haya llegado
        Assert.Null(almacen.ObtenerPaquete(Ana, "asig-1"));
        Assert.Throws<ArgumentException>(() => almacen.PublicarEstado(Ana, "asig-1", "disponible"));
        almacen.PublicarEstado(Ana, "asig-no-existe", "pausado");                    // sobre lo que no existe no hace nada
    }

    // ---------------------------------------------------------------------- utilidades

    [Fact]
    public void ElEspacioLibre_SeInyectaYPorDefectoSeMideDelVolumen()
    {
        Assert.Equal(1234L, new AlmacenEstudio(Path.Combine(carpeta, "otro"), proveedor, espacioLibreBytes: () => 1234).EspacioLibreBytes());
        var real = new AlmacenEstudio(Path.Combine(carpeta, "no-existe-aun", "todavia"), proveedor).EspacioLibreBytes();
        Assert.True(real is > 0);
    }

    [Fact]
    public void ElAlmacen_EsSeguroConVariosHilos()
    {
        var errores = new System.Collections.Concurrent.ConcurrentBag<Exception>();
        Parallel.For(0, 60, i =>
        {
            try
            {
                var id = "asig-" + (i % 6);
                almacen.GuardarTarea(Ana, Tarea(id));
                Assert.NotNull(almacen.LeerTarea(Ana, id));
                almacen.GuardarLista(Ana, Lista(Asignacion(id)));
                Assert.NotNull(almacen.LeerLista(Ana));
                _ = almacen.BytesUsados(Ana);
            }
            catch (Exception ex) { errores.Add(ex); }
        });
        Assert.Empty(errores);
    }

    [Fact]
    public void UnOyenteQueFalla_NoRompeLoQueSeEstaGuardando()
    {
        almacen.Cambio += _ => throw new InvalidOperationException("la pantalla ya no existe");
        almacen.GuardarLista(Ana, Lista(Asignacion()));
        Assert.NotNull(almacen.LeerLista(Ana));
    }
}
