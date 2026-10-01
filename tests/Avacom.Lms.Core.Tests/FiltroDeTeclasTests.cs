using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// kiosk.md §4.3: qué teclas traga el gancho de teclado de Windows. La lógica es pura (sin gancho, sin Windows), así que cada fila de la tabla se prueba aquí
/// sin instalar nada en el equipo de quien ejecuta las pruebas.
/// </summary>
public sealed class FiltroDeTeclasTests
{
    private const int VkA = 0x41;
    private const int VkC = 0x43;
    private const int VkV = 0x56;
    private const int VkEnter = 0x0D;
    private const int VkSpace = 0x20;
    private const int VkBack = 0x08;
    private const int VkLeft = 0x25;
    private const int VkF1 = 0x70;
    private const int VkF5 = 0x74;
    private const int VkF10 = 0x79;
    private const int VkF12 = 0x7B;
    private const int VkDelete = 0x2E;
    private const int VkLControl = 0xA2;
    private const int VkLMenu = 0xA4;
    private const int VkLShift = 0xA0;

    // --------------------------------------------------------------------------------------- lo que se descarta

    [Fact]
    public void LaTeclaWindowsIzquierdaYDerechaSeDescartanSolas()
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkLWin, false, false, false));
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkRWin, false, false, false));
        Assert.Equal("Windows", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkLWin, false, false, false));
        Assert.Equal("Windows", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkRWin, false, false, false));
    }

    [Theory]
    [InlineData(false, false, true)]
    [InlineData(false, true, false)]
    [InlineData(true, false, false)]
    [InlineData(true, true, true)]
    public void LaTeclaWindowsSeDescartaConCualquierModificador(bool alt, bool ctrl, bool shift)
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkLWin, alt, ctrl, shift));
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkRWin, alt, ctrl, shift));
        Assert.Equal("Windows", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkLWin, alt, ctrl, shift));
    }

    [Fact]
    public void AltTabSeDescarta_YSuNombreEsAltTab()
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, alt: true, ctrl: false, shift: false));
        Assert.Equal("Alt+Tab", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkTab, true, false, false));
    }

    [Fact]
    public void LasVariantesDeAltTabTambienSeDescartan()
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, true, false, true));    // Alt+Mayús+Tab: recorre las ventanas hacia atrás
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, true, true, false));    // Ctrl+Alt+Tab: el selector que se queda abierto
        Assert.Equal("Ctrl+Alt+Tab", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkTab, true, true, false));
        Assert.Equal("Alt+Mayús+Tab", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkTab, true, false, true));
    }

    [Fact]
    public void EscSeDescarta_YConEllaAltEscCtrlEscYCtrlMayusEsc()
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkEscape, false, false, false));
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkEscape, alt: true, ctrl: false, shift: false));              // Alt+Esc
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkEscape, alt: false, ctrl: true, shift: false));              // Ctrl+Esc: abre Inicio
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkEscape, alt: false, ctrl: true, shift: true));               // Ctrl+Mayús+Esc: Administrador de tareas
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkEscape, alt: false, ctrl: false, shift: true));
    }

    [Fact]
    public void LosNombresDeEscSonLosDeLaCombinacion()
    {
        Assert.Equal("Esc", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkEscape, false, false, false));
        Assert.Equal("Alt+Esc", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkEscape, true, false, false));
        Assert.Equal("Ctrl+Esc", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkEscape, false, true, false));
        Assert.Equal("Ctrl+Mayús+Esc", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkEscape, false, true, true));
    }

    [Fact]
    public void AltF4SeDescarta_YF4SolaPasa()
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkF4, alt: true, ctrl: false, shift: false));
        Assert.Equal("Alt+F4", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkF4, true, false, false));
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkF4, false, false, false));
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkF4, false, true, false));    // Ctrl+F4 cierra una pestaña interna, no la ventana
    }

    [Theory]
    [InlineData(false, false, false)]
    [InlineData(true, false, false)]
    [InlineData(false, true, false)]
    [InlineData(false, false, true)]
    public void F11SeDescartaConOSinModificadores(bool alt, bool ctrl, bool shift)
    {
        Assert.True(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkF11, alt, ctrl, shift));
        Assert.Equal("F11", FiltroDeTeclas.Nombre(FiltroDeTeclas.VkF11, alt, ctrl, shift));
    }

    // ------------------------------------------------------------------------------------------ lo que pasa

    [Fact]
    public void TabSolaPasa_ElAlumnoNavegaConElTeclado()
    {
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, false, false, false));
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, false, false, true));    // Mayús+Tab: hacia atrás dentro de la página
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkTab, false, true, false));    // Ctrl+Tab no cambia de ventana del sistema
        Assert.Equal(string.Empty, FiltroDeTeclas.Nombre(FiltroDeTeclas.VkTab, false, false, false));
    }

    [Theory]
    [InlineData(VkA, false, false, false)]
    [InlineData(VkA, false, false, true)]      // Mayús+A: escribir una mayúscula
    [InlineData(VkC, false, true, false)]      // Ctrl+C
    [InlineData(VkV, false, true, false)]      // Ctrl+V
    [InlineData(VkEnter, false, false, false)]
    [InlineData(VkSpace, false, false, false)]
    [InlineData(VkBack, false, false, false)]
    [InlineData(VkDelete, false, false, false)]
    [InlineData(VkLeft, false, false, false)]
    [InlineData(VkF1, false, false, false)]
    [InlineData(VkF5, false, false, false)]
    [InlineData(VkF10, false, false, false)]
    [InlineData(VkF12, false, false, false)]
    [InlineData(VkA, true, true, false)]       // Ctrl+Alt+A: el AltGr de algunos teclados escribe símbolos y no debe perderse
    public void EscribirYElRestoDeTeclasPasa(int vk, bool alt, bool ctrl, bool shift)
    {
        Assert.False(FiltroDeTeclas.Descartar(vk, alt, ctrl, shift));
        Assert.Equal(string.Empty, FiltroDeTeclas.Nombre(vk, alt, ctrl, shift));
    }

    [Fact]
    public void LosModificadoresSolosPasan_SoloLaCombinacionEsLaQueSeDescarta()
    {
        // El gancho recibe cada pulsación por separado: Alt, Ctrl y Mayús llegan antes que la tecla que los acompaña y no se tragan.
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkMenu, true, false, false));
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkControl, false, true, false));
        Assert.False(FiltroDeTeclas.Descartar(FiltroDeTeclas.VkShift, false, false, true));
        Assert.False(FiltroDeTeclas.Descartar(VkLMenu, true, false, false));
        Assert.False(FiltroDeTeclas.Descartar(VkLControl, false, true, false));
        Assert.False(FiltroDeTeclas.Descartar(VkLShift, false, false, true));
    }

    [Fact]
    public void LosCodigosDeTeclaVirtualSonLosDeWindows()
    {
        // winuser.h: un código mal escrito dejaría pasar la tecla que debía tragar y nada más lo notaría.
        Assert.Equal(0x09, FiltroDeTeclas.VkTab);
        Assert.Equal(0x1B, FiltroDeTeclas.VkEscape);
        Assert.Equal(0x73, FiltroDeTeclas.VkF4);
        Assert.Equal(0x7A, FiltroDeTeclas.VkF11);
        Assert.Equal(0x5B, FiltroDeTeclas.VkLWin);
        Assert.Equal(0x5C, FiltroDeTeclas.VkRWin);
        Assert.Equal(0x10, FiltroDeTeclas.VkShift);
        Assert.Equal(0x11, FiltroDeTeclas.VkControl);
        Assert.Equal(0x12, FiltroDeTeclas.VkMenu);
    }

    [Fact]
    public void DescartarYNombreSiempreCoinciden()
    {
        // Barrido completo del espacio de teclas: lo que se descarta tiene nombre y lo que no, no. El agregador cuenta por nombre.
        for (var vk = 0; vk <= 0xFF; vk++)
            foreach (var alt in new[] { false, true })
                foreach (var ctrl in new[] { false, true })
                    foreach (var shift in new[] { false, true })
                        Assert.Equal(FiltroDeTeclas.Descartar(vk, alt, ctrl, shift), FiltroDeTeclas.Nombre(vk, alt, ctrl, shift).Length > 0);
    }

    [Fact]
    public void SoloSeisTeclasBaseSeDescartanEnTodoElEspacio()
    {
        // La lista cerrada de kiosk.md §4.3: Windows (izq. y der.), Tab, Esc, F4 y F11. Cualquier otra aparecería aquí.
        var descartadas = new SortedSet<int>();
        for (var vk = 0; vk <= 0xFF; vk++)
            foreach (var alt in new[] { false, true })
                foreach (var ctrl in new[] { false, true })
                    foreach (var shift in new[] { false, true })
                        if (FiltroDeTeclas.Descartar(vk, alt, ctrl, shift)) descartadas.Add(vk);
        var esperadas = new[] { FiltroDeTeclas.VkTab, FiltroDeTeclas.VkEscape, FiltroDeTeclas.VkLWin, FiltroDeTeclas.VkRWin, FiltroDeTeclas.VkF4, FiltroDeTeclas.VkF11 }.Order().ToArray();
        Assert.Equal(esperadas, descartadas.ToArray());
    }
}

/// <summary>El agregador por minuto de las teclas descartadas, con un reloj falso: sin esperas.</summary>
public sealed class AgregadorDeTeclasTests
{
    private sealed class RelojFalso
    {
        public long Ms;
        public long Ahora() => Ms;
    }

    private static (AgregadorDeTeclas Agregador, RelojFalso Reloj) Crear(long inicioMs = 0)
    {
        var reloj = new RelojFalso { Ms = inicioMs };
        return (new AgregadorDeTeclas(reloj.Ahora), reloj);
    }

    [Fact]
    public void SinTeclasNoHayNadaQueInformar()
    {
        var (agregador, reloj) = Crear();
        reloj.Ms = 10 * 60_000;
        Assert.Empty(agregador.Vaciar());
        Assert.Empty(agregador.VaciarTodo());
        Assert.False(agregador.HayPendientes);
    }

    [Fact]
    public void ElMinutoEnCursoNoSeEntregaTodaviaPorqueAunPuedeCrecer()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("Alt+Tab");
        reloj.Ms = 59_999;
        agregador.Registrar("Alt+Tab");
        Assert.Empty(agregador.Vaciar());
        Assert.True(agregador.HayPendientes);
    }

    [Fact]
    public void UnMinutoTerminadoSaleEnUnSoloResumen_ConLasTeclasDistintasYElTotal()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("Alt+Tab");
        agregador.Registrar("Windows");
        agregador.Registrar("Alt+Tab");
        agregador.Registrar("Alt+Tab");
        agregador.Registrar("Esc");
        reloj.Ms = 60_000;      // ya es el minuto siguiente

        var resumenes = agregador.Vaciar();

        var uno = Assert.Single(resumenes);
        Assert.Equal(0, uno.Minuto);
        Assert.Equal(5, uno.Veces);
        Assert.Equal(["Alt+Tab", "Esc", "Windows"], uno.Teclas);    // de la más repetida a la menos; a igualdad, por nombre
        Assert.False(agregador.HayPendientes);
    }

    [Fact]
    public void UnResumenSeEntregaUnaSolaVez()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("F11");
        reloj.Ms = 120_000;
        Assert.Single(agregador.Vaciar());
        Assert.Empty(agregador.Vaciar());
        Assert.Empty(agregador.VaciarTodo());
    }

    [Fact]
    public void CadaMinutoTranscurridoDaSuPropioResumen_EnOrden()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("Windows");                 // minuto 0
        reloj.Ms = 61_000;
        agregador.Registrar("Alt+F4");                  // minuto 1
        agregador.Registrar("Alt+F4");
        reloj.Ms = 5 * 60_000 + 10;
        agregador.Registrar("Esc");                     // minuto 5 (los minutos 2 a 4 pasaron en silencio)
        reloj.Ms = 6 * 60_000;

        var resumenes = agregador.Vaciar();

        Assert.Equal(3, resumenes.Count);
        Assert.Equal([0L, 1L, 5L], resumenes.Select(r => r.Minuto).ToArray());
        Assert.Equal([1, 2, 1], resumenes.Select(r => r.Veces).ToArray());
        Assert.Equal(["Windows"], resumenes[0].Teclas);
        Assert.Equal(["Alt+F4"], resumenes[1].Teclas);
        Assert.Equal(["Esc"], resumenes[2].Teclas);
    }

    [Fact]
    public void ElMinutoEnCursoSeGuardaYSaleCuandoTermina()
    {
        var (agregador, reloj) = Crear();
        reloj.Ms = 3 * 60_000 + 30_000;
        agregador.Registrar("Alt+Tab");
        Assert.Empty(agregador.Vaciar());               // sigue siendo el minuto 3
        reloj.Ms = 3 * 60_000 + 59_999;
        agregador.Registrar("Alt+Tab");
        Assert.Empty(agregador.Vaciar());
        reloj.Ms = 4 * 60_000;
        var uno = Assert.Single(agregador.Vaciar());
        Assert.Equal(3, uno.Minuto);
        Assert.Equal(2, uno.Veces);
    }

    [Fact]
    public void VaciarTodoEntregaTambienElMinutoEnCurso()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("Windows");
        reloj.Ms = 61_000;
        agregador.Registrar("Esc");

        var resumenes = agregador.VaciarTodo();

        Assert.Equal(2, resumenes.Count);
        Assert.Equal(["Windows"], resumenes[0].Teclas);
        Assert.Equal(["Esc"], resumenes[1].Teclas);
        Assert.False(agregador.HayPendientes);
    }

    [Fact]
    public void ElDetalleTieneLaFormaDelCatalogoDeIncidentes()
    {
        // modelado-datos.md §4.7: tecla_bloqueada → {teclas, veces}.
        var (agregador, reloj) = Crear();
        agregador.Registrar("Alt+Tab");
        agregador.Registrar("Windows");
        agregador.Registrar("Windows");
        reloj.Ms = 60_000;

        var detalle = Assert.Single(agregador.Vaciar()).Detalle();

        Assert.Equal(2, detalle.Count);
        Assert.Equal(new[] { "Windows", "Alt+Tab" }, Assert.IsType<string[]>(detalle["teclas"]));
        Assert.Equal(3, Assert.IsType<int>(detalle["veces"]));
    }

    [Fact]
    public void UnNombreVacioNoSeAnota()
    {
        var (agregador, reloj) = Crear();
        agregador.Registrar("");
        agregador.Registrar(null!);
        reloj.Ms = 120_000;
        Assert.False(agregador.HayPendientes);
        Assert.Empty(agregador.Vaciar());
    }

    [Fact]
    public async Task ElGanchoYElTemporizadorPuedenUsarloAlMismoTiempo()
    {
        var (agregador, reloj) = Crear();
        var tareas = Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
        {
            for (var i = 0; i < 1000; i++) agregador.Registrar(i % 2 == 0 ? "Alt+Tab" : "Windows");
        })).ToArray();
        await Task.WhenAll(tareas);

        var total = agregador.VaciarTodo().Sum(r => r.Veces);

        Assert.Equal(8000, total);
    }

    [Fact]
    public void SinRelojNoSeCrea()
    {
        Assert.Throws<ArgumentNullException>(() => new AgregadorDeTeclas(null!));
    }
}
