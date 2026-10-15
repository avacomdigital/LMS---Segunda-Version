using System.Globalization;
using System.Text;
using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Core.Tests;

/// <summary>El nombre con que se guarda un reporte exportado: válido a la vez en NTFS, FAT32 y exFAT, determinista y de a lo sumo 100 caracteres.</summary>
public sealed class NombreDeArchivoTests
{
    private static readonly char[] Prohibidos = ['\\', '/', ':', '*', '?', '"', '<', '>', '|'];

    // Los nombres que Windows reserva, escritos aquí otra vez a propósito: la prueba no debe depender de la lista del código que prueba.
    private static readonly HashSet<string> Dispositivos = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "COM¹", "COM²", "COM³",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9", "LPT¹", "LPT²", "LPT³",
    };

    private static bool EsDispositivo(string nombre)
    {
        var punto = nombre.IndexOf('.');
        return Dispositivos.Contains((punto < 0 ? nombre : nombre[..punto]).TrimEnd(' '));
    }

    private static string Escapar(string texto) => string.Concat(texto.Select(c => c is < ' ' or > '~' ? $"\\u{(int)c:X4}" : c.ToString()));

    // ---------------------------------------------------------------------------------------------------- caracteres

    [Theory]
    [InlineData('\\')]
    [InlineData('/')]
    [InlineData(':')]
    [InlineData('*')]
    [InlineData('?')]
    [InlineData('"')]
    [InlineData('<')]
    [InlineData('>')]
    [InlineData('|')]
    public void CadaCaracterProhibido_PasaAGuion(char prohibido) => Assert.Equal("a-b", NombreDeArchivo.Sanear("a" + prohibido + "b"));

    [Fact]
    public void CadaControl_PasaAGuion()
    {
        for (var c = 0; c <= 0x1F; c++)
            Assert.Equal("a-b", NombreDeArchivo.Sanear($"a{(char)c}b"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\u007Fb"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\u0085b"));          // control de la zona C1 (NEL)
    }

    [Fact]
    public void LosEspaciosYGuionesRepetidos_SeColapsan()
    {
        Assert.Equal("a b", NombreDeArchivo.Sanear("a     b"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a-----b"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a//\\\\b"));          // cuatro prohibidos seguidos son un solo guion
        Assert.Equal("a - b", NombreDeArchivo.Sanear("a / b"));           // un guion con espacios alrededor se queda: no hay nada repetido
        Assert.Equal("a b", NombreDeArchivo.Sanear("a\u00A0\u00A0 \u2003b"));     // espacio no separable, espacio de ancho fijo: son espacios normales
    }

    [Fact]
    public void LosInvisiblesDeFormato_SeQuitan()
    {
        // marca de orden de bytes, ancho cero, control de dirección (el truco de «fdp.exe» que se lee «exe.pdf»): no dejan rastro en un nombre de archivo
        Assert.Equal("abcd", NombreDeArchivo.Sanear("\uFEFFa\u200Bb\u202Ec\u00ADd"));
    }

    [Theory]
    [InlineData("  hola  ", "hola")]
    [InlineData("..hola..", "hola")]
    [InlineData(". hola .", "hola")]
    [InlineData("hola. . .", "hola")]
    [InlineData("hola.", "hola")]
    [InlineData(".oculto", "oculto")]
    public void LosEspaciosYPuntosDeLosLados_SeRecortan(string propuesto, string esperado) => Assert.Equal(esperado, NombreDeArchivo.Sanear(propuesto));

    [Fact]
    public void ElPuntoDelMedio_SeRespeta() => Assert.Equal("Grupo 8.A", NombreDeArchivo.Sanear("Grupo 8.A"));

    [Fact]
    public void LasTildesYLaEnie_SeConservan()
    {
        const string nombre = "Año 2026 – Grupo «8°A» Educación física";
        Assert.Equal(nombre, NombreDeArchivo.Sanear(nombre));
    }

    [Fact]
    public void ElTexto_SeNormalizaAFormC()
    {
        var descompuesto = "Educacio\u0301n";                       // «o» + acento suelto
        var resultado = NombreDeArchivo.Sanear(descompuesto);
        Assert.Equal("Educaci\u00F3n", resultado);                  // «ó» de una pieza
        Assert.True(resultado.IsNormalized(NormalizationForm.FormC));
    }

    // Lo que descubrió el barrido: quitar un invisible deja pegadas una letra y su tilde que antes no lo estaban, y ESAS SÍ se componen. Si la normalización fuera antes de
    // quitar el invisible, el nombre saldría sin normalizar y volver a sanearlo lo cambiaría. Los caracteres van por su código (no escritos) para que sean visibles aquí.
    [Theory]
    [InlineData(0x007A, 0x200D, 0x0301, 0x017A)]                   // «z» + unión de ancho cero + acento agudo = «ź»
    [InlineData(0x00C5, 0xFEFF, 0x0301, 0x01FA)]                   // «Å» + marca de orden de bytes + acento agudo = «Ǻ»
    [InlineData(0x0065, 0x202E, 0x0301, 0x00E9)]                   // «e» + control de dirección + acento agudo = «é»
    public void QuitarUnInvisible_QueDejaJuntaUnaLetraConSuTilde_SigueEnFormC(int letra, int invisible, int acento, int esperada)
    {
        var resultado = NombreDeArchivo.Sanear(new string([(char)letra, (char)invisible, (char)acento]));
        Assert.Equal(((char)esperada).ToString(), resultado);
        Assert.True(resultado.IsNormalized(NormalizationForm.FormC));
        Assert.Equal(resultado, NombreDeArchivo.Sanear(resultado));         // y es estable
    }

    [Theory]
    [InlineData("reporte-grupo-8A")]
    [InlineData("Calificaciones 8A (2026-1)")]
    [InlineData("Boletín final · Grupo 8°A")]
    public void UnNombreSano_NoSeToca(string nombre) => Assert.Equal(nombre, NombreDeArchivo.Sanear(nombre));

    // ---------------------------------------------------------------------------------------------------- reservados

    [Theory]
    [InlineData("CON")]
    [InlineData("con")]
    [InlineData("Prn")]
    [InlineData("AUX")]
    [InlineData("nul")]
    [InlineData("COM1")]
    [InlineData("com9")]
    [InlineData("LPT1")]
    [InlineData("lpt9")]
    [InlineData("COM¹")]
    [InlineData("LPT³")]
    [InlineData("CONIN$")]
    [InlineData("CON.backup")]           // con «extensión» dentro del propio nombre: sigue siendo el dispositivo
    [InlineData("nul.txt")]
    [InlineData("COM1.tar.gz")]
    [InlineData("CON .x")]               // los espacios antes del punto no lo salvan
    public void UnNombreReservado_LlevaElPrefijo(string reservado) => Assert.Equal("reporte-" + reservado, NombreDeArchivo.Sanear(reservado));

    [Theory]
    [InlineData("COM0")]
    [InlineData("COM10")]
    [InlineData("CONSOLA")]
    [InlineData("COMEDOR")]
    [InlineData("LPT")]
    [InlineData("AUXILIAR")]
    [InlineData("NULO")]
    [InlineData("con-1")]
    [InlineData("mi CON")]
    public void UnNombreParecidoPeroNoReservado_NoSeToca(string nombre) => Assert.Equal(nombre, NombreDeArchivo.Sanear(nombre));

    [Fact]
    public void UnReservadoConExtension_TambienLlevaElPrefijo()
    {
        Assert.Equal("reporte-CON.xlsx", NombreDeArchivo.Sanear("CON", ".xlsx"));
        Assert.Equal("reporte-nul.csv", NombreDeArchivo.Sanear("nul", "csv"));
        Assert.Equal("reporte-con.backup.xlsx", NombreDeArchivo.Sanear("con.backup", ".xlsx"));
    }

    // ---------------------------------------------------------------------------------------------------- vacío y respaldo

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("...")]
    [InlineData(" . . ")]
    [InlineData("///")]
    [InlineData("???")]
    [InlineData("---")]
    [InlineData("\u200B\u200B")]
    public void SiNoQuedaNada_SeUsaElRespaldo(string? propuesto) => Assert.Equal("reporte", NombreDeArchivo.Sanear(propuesto));

    [Fact]
    public void ElRespaldoPropio_SeLimpiaComoCualquierNombre()
    {
        Assert.Equal("informe", NombreDeArchivo.Sanear(null, "", "informe"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("", "", "a/b"));
        Assert.Equal("reporte-con", NombreDeArchivo.Sanear("", "", "con"));           // un respaldo reservado también se prefija
        Assert.Equal("reporte", NombreDeArchivo.Sanear("", "", ""));                    // y uno vacío no deja sin nombre
        Assert.Equal("informe.xlsx", NombreDeArchivo.Sanear("...", ".xlsx", "informe"));
        Assert.Equal("grupo", NombreDeArchivo.Sanear("grupo", "", "informe"));          // el respaldo sólo entra cuando hace falta
    }

    // ---------------------------------------------------------------------------------------------------- extensión

    [Theory]
    [InlineData("XLSX", ".xlsx")]
    [InlineData(".XLSX", ".xlsx")]
    [InlineData("..csv", ".csv")]
    [InlineData(" .csv ", ".csv")]
    [InlineData(".xlsx.", ".xlsx")]
    [InlineData(".c*v", ".c-v")]
    [InlineData("tar.gz", ".tar.gz")]
    [InlineData("", "")]
    [InlineData(".", "")]
    [InlineData("...", "")]
    [InlineData("  ", "")]
    public void LaExtension_SeNormaliza(string extension, string esperada) => Assert.Equal("x" + esperada, NombreDeArchivo.Sanear("x", extension));

    [Fact]
    public void LaExtensionNula_EsNingunaExtension() => Assert.Equal("x", NombreDeArchivo.Sanear("x", null!));

    [Fact]
    public void LaExtensionNoSeRepite_SiLaBaseYaLaTraeAlFinal()
    {
        Assert.Equal("reporte.xlsx", NombreDeArchivo.Sanear("reporte.xlsx", ".xlsx"));
        Assert.Equal("reporte.xlsx", NombreDeArchivo.Sanear("reporte.XLSX", "xlsx"));
        Assert.Equal("informe.xlsx", NombreDeArchivo.Sanear("informe .xlsx", ".xlsx"));
        Assert.Equal("reporte.csv.xlsx", NombreDeArchivo.Sanear("reporte.csv", ".xlsx"));          // otra extensión: es parte del nombre
    }

    [Fact]
    public void LaExtensionSeMinusculizaSinMirarLaCulturaDelEquipo()
    {
        var anterior = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = new CultureInfo("tr-TR");           // en turco la «I» mayúscula se minusculiza a «ı»: aquí no debe pasar
            Assert.Equal("x.index", NombreDeArchivo.Sanear("x", ".INDEX"));
        }
        finally { CultureInfo.CurrentCulture = anterior; }
    }

    // ---------------------------------------------------------------------------------------------------- longitud

    [Fact]
    public void ElMaximo_SonCien() => Assert.Equal(100, NombreDeArchivo.MaximoDeCaracteres);

    [Fact]
    public void ElTotalConExtension_NuncaPasaDeCien()
    {
        var largo = NombreDeArchivo.Sanear(new string('a', 200), ".xlsx");
        Assert.Equal(100, largo.Length);
        Assert.EndsWith(".xlsx", largo);                                 // la extensión nunca se recorta
        Assert.Equal(new string('a', 95) + ".xlsx", largo);
    }

    [Theory]
    [InlineData(94, 99)]
    [InlineData(95, 100)]               // justo en el borde: no se toca
    [InlineData(96, 100)]               // uno de más: se recorta uno
    public void ElBorde_DeLosCienCaracteres(int largoDeLaBase, int largoEsperado)
    {
        var nombre = NombreDeArchivo.Sanear(new string('a', largoDeLaBase), ".xlsx");
        Assert.Equal(largoEsperado, nombre.Length);
        Assert.EndsWith(".xlsx", nombre);
    }

    [Fact]
    public void SinExtension_SeRecortaLaBaseA100() => Assert.Equal(new string('a', 100), NombreDeArchivo.Sanear(new string('a', 150)));

    [Fact]
    public void UnaExtensionDescomunal_TambienTieneTope()
    {
        var nombre = NombreDeArchivo.Sanear("hola", "." + new string('x', 50));
        Assert.True(nombre.Length <= 100);
        Assert.Equal("hola." + new string('x', 19), nombre);            // la extensión se queda en 20 caracteres con su punto: la base siempre tiene sitio
    }

    [Fact]
    public void ElRecorte_NoPartePareSustituto()
    {
        // la base mide 94 «a» + un emoji (dos unidades UTF-16) = 96 y el cupo es 95: el emoji ENTERO se va, no su mitad
        var nombre = NombreDeArchivo.Sanear(new string('a', 94) + "😀" + new string('b', 10), ".xlsx");
        Assert.Equal(new string('a', 94) + ".xlsx", nombre);
        EsTextoValido(nombre);

        // y si el par cabe justo, se conserva
        var justo = NombreDeArchivo.Sanear(new string('a', 93) + "😀" + "bbb", ".xlsx");
        Assert.Equal(new string('a', 93) + "😀.xlsx", justo);
        Assert.Equal(100, justo.Length);
        EsTextoValido(justo);
    }

    [Fact]
    public void ElRecorte_NoDejaUnaLetraSinSuTilde()
    {
        // «x» + tilde combinada no tiene versión de una pieza: son dos unidades que van juntas
        var nombre = NombreDeArchivo.Sanear(new string('a', 94) + "x\u0303", ".xlsx");
        Assert.Equal(new string('a', 94) + ".xlsx", nombre);
    }

    [Fact]
    public void UnaLetraConCientosDeMarcas_NoDejaElNombreVacio()
    {
        var nombre = NombreDeArchivo.Sanear("e" + new string('\u0301', 300), ".xlsx");
        Assert.True(nombre.Length is > 5 and <= 100);
        Assert.EndsWith(".xlsx", nombre);
        EsTextoValido(nombre);
    }

    [Fact]
    public void UnSustitutoSuelto_NoSeAceptaNiHaceLanzar()
    {
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\uD83Db"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\uDE00b"));
        Assert.Equal("reporte", NombreDeArchivo.Sanear("\uD83D"));
        EsTextoValido(NombreDeArchivo.Sanear("\uD83D\uD83D\uDE00\uDE00"));
    }

    [Fact]
    public void UnNoCaracterDeUnicode_PasaAGuion_ySinLanzar()
    {
        // normalizar con U+FFFE lanza: el saneado se adelanta y lo cambia por \u00AB-\u00BB antes
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\uFFFEb"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\uFFFFb"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a\uFDD0b"));
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a" + char.ConvertFromUtf32(0x1FFFE) + "b"));          // los de los otros planos tambi\u00E9n
        Assert.Equal("a-b", NombreDeArchivo.Sanear("a" + char.ConvertFromUtf32(0x10FFFF) + "b"));
        Assert.Equal("a\uFFFDb", NombreDeArchivo.Sanear("a\uFFFDb"));                                       // el car\u00E1cter de reemplazo s\u00ED es v\u00E1lido
    }

    private static void EsTextoValido(string texto) => new UTF8Encoding(false, throwOnInvalidBytes: true).GetBytes(texto);       // lanza ante un sustituto suelto

    // ---------------------------------------------------------------------------------------------------- determinismo, estabilidad y barrido

    [Fact]
    public void LaMismaEntrada_DaLaMismaSalida()
    {
        const string entrada = "  Reporte: grupo «8A»/2026?  ";
        Assert.Equal(NombreDeArchivo.Sanear(entrada, ".xlsx"), NombreDeArchivo.Sanear(entrada, ".xlsx"));
        Assert.Equal("Reporte- grupo «8A»-2026-.xlsx", NombreDeArchivo.Sanear(entrada, ".xlsx"));
    }

    /// <summary>
    /// Barrido con una semilla fija (siempre las mismas 4 000 entradas): todo lo que sale del saneado cumple a la vez TODAS las reglas, y es estable (volver a sanear un nombre ya
    /// sano no lo cambia, que es lo que hace el escritor con el nombre que recibe) y sus variantes «(n)» también lo son.
    /// </summary>
    [Fact]
    public void Barrido_ToLoQueSale_CumpleTodasLasReglasYEsEstable()
    {
        string[] piezas =
        [
            "a", "B", "z", "9", "0", " ", "  ", "\t", "\n", "\r", "\0", "\u007F", "\u0085", ".", "..", "-", "--", "_", "\\", "/", ":", "*", "?", "\"", "<", ">", "|",
            "é", "ñ", "Ñ", "e\u0301", "x\u0303", "😀", "👨‍👩‍👧", "\uD83D", "\uDE00", "\u00A0", "\u200B", "\u202E", "\uFEFF", "\u2028", "\u3000",
            "CON", "nul", "COM1", "lpt9", "AUX", "PRN", "COM¹", "con.", "Reporte", "grupo", "8A", "(2)", " (3)", ".xlsx", ".csv", "\uFFFF", "\uFFFE",
        ];
        string[] extensiones = ["", ".xlsx", "csv", "XLSX", "..tar.gz", " .x y ", ".c*v", "." + new string('q', 50), "...", ".e\u0301"];

        var azar = new Random(20261015);
        for (var i = 0; i < 4000; i++)
        {
            var entrada = new StringBuilder();
            var cuantas = azar.Next(0, 60);
            for (var k = 0; k < cuantas; k++) entrada.Append(piezas[azar.Next(piezas.Length)]);
            if (azar.Next(10) == 0) entrada.Append(new string('m', azar.Next(80, 220)));         // y algunas muy largas, para el recorte
            var texto = entrada.ToString();
            var extension = extensiones[azar.Next(extensiones.Length)];

            var nombre = NombreDeArchivo.Sanear(texto, extension);
            var contexto = $"entrada «{Escapar(texto)}», extensión «{Escapar(extension)}», salida «{Escapar(nombre)}»";

            Assert.True(nombre.Length is > 0 and <= NombreDeArchivo.MaximoDeCaracteres, contexto);
            Assert.True(nombre.All(c => !Prohibidos.Contains(c) && !char.IsControl(c)), contexto);
            Assert.True(nombre[0] is not (' ' or '.') && nombre[^1] is not (' ' or '.'), contexto);
            Assert.True(!nombre.Contains("  ") && !nombre.Contains("--"), contexto);
            Assert.True(nombre.IsNormalized(NormalizationForm.FormC), contexto);
            Assert.False(EsDispositivo(nombre), contexto);
            EsTextoValido(nombre);

            // estable: lo que ya es un nombre sano no cambia al volver a sanearlo, con o sin extensión aparte, y sus variantes tampoco
            Assert.True(NombreDeArchivo.Sanear(nombre) == nombre, contexto);
            var extensionDelNombre = NombreDeArchivo.SepararExtension(nombre).Extension;
            foreach (var n in new[] { 2, 3, 10, 999 })
            {
                var variante = NombreDeArchivo.ConSufijo(nombre, n);
                Assert.True(variante.Length <= NombreDeArchivo.MaximoDeCaracteres, contexto + $", variante {n}");
                Assert.True(NombreDeArchivo.Sanear(variante) == variante, contexto + $", variante {n}");
                Assert.True(variante.EndsWith($" ({n}){extensionDelNombre}", StringComparison.Ordinal), contexto + $", variante {n}");
            }
        }
    }

    // ---------------------------------------------------------------------------------------------------- variantes «(2)»

    [Theory]
    [InlineData(2, "reporte-grupo-8A (2).xlsx")]
    [InlineData(3, "reporte-grupo-8A (3).xlsx")]
    [InlineData(999, "reporte-grupo-8A (999).xlsx")]
    public void ConSufijo_VaAntesDeLaExtension(int numero, string esperado) => Assert.Equal(esperado, NombreDeArchivo.ConSufijo("reporte-grupo-8A.xlsx", numero));

    [Theory]
    [InlineData(1)]
    [InlineData(0)]
    [InlineData(-5)]
    public void ConSufijo_ConMenosDeDos_DejaElNombreComoEstaba(int numero) => Assert.Equal("reporte.xlsx", NombreDeArchivo.ConSufijo("reporte.xlsx", numero));

    [Fact]
    public void ConSufijo_SinExtensionOConPuntosDentro()
    {
        Assert.Equal("reporte (2)", NombreDeArchivo.ConSufijo("reporte", 2));
        Assert.Equal("reporte.v2 (2).xlsx", NombreDeArchivo.ConSufijo("reporte.v2.xlsx", 2));        // se parte en el ÚLTIMO punto
        Assert.Equal(".xlsx (2)", NombreDeArchivo.ConSufijo(".xlsx", 2));                              // un punto al inicio no es extensión
        // un punto en medio de un nombre sin extensión no vuelve «extensión» su cola (con espacios o larga): el número va al final
        Assert.Equal("Grupo 8.A de la tarde (2)", NombreDeArchivo.ConSufijo("Grupo 8.A de la tarde", 2));
        Assert.Equal("reporte.estadistica-anual-2026 (3)", NombreDeArchivo.ConSufijo("reporte.estadistica-anual-2026", 3));
    }

    [Theory]
    [InlineData("reporte.xlsx", "reporte", ".xlsx")]
    [InlineData("reporte.v2.xlsx", "reporte.v2", ".xlsx")]
    [InlineData("reporte.tar.gz", "reporte.tar", ".gz")]
    [InlineData("reporte", "reporte", "")]
    [InlineData(".xlsx", ".xlsx", "")]
    [InlineData("reporte.", "reporte.", "")]
    [InlineData("Grupo 8.A de la tarde", "Grupo 8.A de la tarde", "")]                          // la cola trae espacios: no parece una extensión
    [InlineData("reporte.estadistica-anual-2026", "reporte.estadistica-anual-2026", "")]       // y una cola larga tampoco
    public void SepararExtension_SoloSiLaColaPareceUnaExtension(string nombre, string baseEsperada, string extensionEsperada)
    {
        var (b, e) = NombreDeArchivo.SepararExtension(nombre);
        Assert.Equal((baseEsperada, extensionEsperada), (b, e));
    }

    [Fact]
    public void SepararExtension_ConNombreNulo_Lanza() => Assert.Throws<ArgumentNullException>(() => NombreDeArchivo.SepararExtension(null!));

    [Fact]
    public void ConSufijo_RespetaElTopeDeCien()
    {
        var cien = new string('a', 95) + ".xlsx";
        Assert.Equal(100, cien.Length);

        Assert.Equal(new string('a', 91) + " (2).xlsx", NombreDeArchivo.ConSufijo(cien, 2));
        Assert.Equal(new string('a', 89) + " (999).xlsx", NombreDeArchivo.ConSufijo(cien, 999));
        Assert.Equal(100, NombreDeArchivo.ConSufijo(cien, 999).Length);
    }

    [Fact]
    public void ConSufijo_AlRecortarNoDejaEspaciosNiPuntosAntesDelNumero()
    {
        // el corte cae justo después de un espacio: sin retoque saldría «aaa  (2)»
        var nombre = new string('a', 90) + " " + "bbbb" + ".xlsx";
        Assert.Equal(100, nombre.Length);
        var con = NombreDeArchivo.ConSufijo(nombre, 2);
        Assert.Equal(new string('a', 90) + " (2).xlsx", con);
        Assert.DoesNotContain("  ", con);
    }

    [Fact]
    public void ConSufijo_AlRecortarNoPartePareSustituto()
    {
        var nombre = new string('a', 90) + "😀" + "bbb" + ".xlsx";                   // base de 95; cupo con « (2)» = 91: el emoji (92) no cabe
        var con = NombreDeArchivo.ConSufijo(nombre, 2);
        Assert.Equal(new string('a', 90) + " (2).xlsx", con);
        EsTextoValido(con);
    }

    [Fact]
    public void ConSufijo_ConUnPuntoDentroYUnaColaLarga_NoPasaDeCien()
    {
        // lo que descubrió el barrido: el punto está DENTRO del nombre y la cola (93 caracteres) no es una extensión; si se contara como tal nunca se recortaría
        var nombre = "_ COM¹." + new string('x', 93);
        Assert.Equal(100, nombre.Length);
        var con = NombreDeArchivo.ConSufijo(nombre, 999);
        Assert.True(con.Length <= 100);
        Assert.EndsWith(" (999)", con);
    }

    [Fact]
    public void ConSufijo_ConNombreNulo_Lanza() => Assert.Throws<ArgumentNullException>(() => NombreDeArchivo.ConSufijo(null!, 2));

    // ---------------------------------------------------------------------------------------------------- elegir el primero libre

    [Fact]
    public void Elegir_SiEstaLibre_EsElMismoNombre() => Assert.Equal("reporte.xlsx", NombreDeArchivo.Elegir("reporte.xlsx", _ => false));

    [Fact]
    public void Elegir_ConUnoOcupado_EsElDos()
    {
        var ocupados = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "reporte.xlsx" };
        Assert.Equal("reporte (2).xlsx", NombreDeArchivo.Elegir("reporte.xlsx", ocupados.Contains));
    }

    [Fact]
    public void Elegir_SaltaLosOcupados_YNoMiraDeMas()
    {
        var ocupados = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "reporte.xlsx", "reporte (2).xlsx", "reporte (3).xlsx" };
        var consultas = new List<string>();
        var elegido = NombreDeArchivo.Elegir("reporte.xlsx", n => { consultas.Add(n); return ocupados.Contains(n); });
        Assert.Equal("reporte (4).xlsx", elegido);
        Assert.Equal(["reporte.xlsx", "reporte (2).xlsx", "reporte (3).xlsx", "reporte (4).xlsx"], consultas);          // se detiene en el primero libre
    }

    [Fact]
    public void Elegir_ConTodosOcupadosMenosElUltimo_EsElNovecientosNoventaYNueve()
    {
        var ocupados = Enumerable.Range(1, 998).Select(n => NombreDeArchivo.ConSufijo("reporte.xlsx", n)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        Assert.Equal("reporte (999).xlsx", NombreDeArchivo.Elegir("reporte.xlsx", ocupados.Contains));
    }

    [Fact]
    public void Elegir_ConTodosOcupados_LanzaConUnMensajeEnEspanol()
    {
        var ocupados = Enumerable.Range(1, 999).Select(n => NombreDeArchivo.ConSufijo("reporte.xlsx", n)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        Assert.Equal(999, ocupados.Count);
        var error = Assert.Throws<InvalidOperationException>(() => NombreDeArchivo.Elegir("reporte.xlsx", ocupados.Contains));
        Assert.Contains("No hay un nombre libre", error.Message);
        Assert.Contains("999", error.Message);
        Assert.Contains("reporte.xlsx", error.Message);
    }

    [Fact]
    public void Elegir_ConArgumentosNulos_Lanza()
    {
        Assert.Throws<ArgumentNullException>(() => NombreDeArchivo.Elegir(null!, _ => false));
        Assert.Throws<ArgumentNullException>(() => NombreDeArchivo.Elegir("x", null!));
    }

    // ---------------------------------------------------------------------------------------------------- rutas de red

    [Theory]
    [InlineData(@"\\servidor\recurso", true)]
    [InlineData(@"\\servidor\recurso\Reportes\2026", true)]
    [InlineData("//servidor/recurso", true)]
    [InlineData(@"\\?\UNC\servidor\recurso", true)]
    [InlineData(@"\\?\unc\servidor\recurso", true)]
    [InlineData(@"\\?\C:\Reportes", false)]              // ruta larga de un disco local: empieza igual y NO es de red
    [InlineData(@"\\.\E:", false)]
    [InlineData(@"E:\Reportes", false)]
    [InlineData(@"Z:\", false)]                          // una letra mapeada a la red no se distingue por el texto
    [InlineData(@"Reportes\2026", false)]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData(null, false)]
    public void EsRutaDeRed_SoloLasUnc(string? ruta, bool esperado) => Assert.Equal(esperado, NombreDeArchivo.EsRutaDeRed(ruta));
}
