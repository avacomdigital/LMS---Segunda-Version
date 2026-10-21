using Avacom.Lms.Ops.Navegacion;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// La guardia de la navegación de OPS: un doble toque (o el reintento de una prueba de UI Automation) no puede sacar al menú principal ni apilar dos pantallas iguales. Reproduce, sin ventanas,
/// el fallo que dejaba a OPS en el acceso con el proceso vivo y sin ningún 401 (2026-10-20): «Menú principal» activado dos veces seguidas hacía <c>GoToAsync("..")</c> dos veces.
/// </summary>
public sealed class GuardiaDeNavegacionTests
{
    private sealed class Reloj { public long Ms; }

    private static (GuardiaDeNavegacion Guardia, Reloj Reloj) Nueva()
    {
        var reloj = new Reloj();
        return (new GuardiaDeNavegacion(() => reloj.Ms), reloj);
    }

    // ------------------------------------------------------------------------------------------------------------- el menú no se saca con «..»

    [Theory]
    [InlineData("..")]
    [InlineData("../..")]
    [InlineData("../../..")]
    [InlineData(" .. ")]
    [InlineData("../")]
    public void Un_volver_con_el_menu_a_la_vista_se_ignora(string destino)
    {
        var (guardia, _) = Nueva();
        Assert.Equal(GuardiaDeNavegacion.Veredicto.YaEstaEnElMenu, guardia.Evaluar(destino, paginaActualEsElMenu: true));
    }

    [Theory]
    [InlineData("..")]
    [InlineData("../..")]
    public void Un_volver_desde_cualquier_otra_pantalla_pasa(string destino)
    {
        var (guardia, _) = Nueva();
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar(destino, paginaActualEsElMenu: false));
    }

    [Theory]
    [InlineData("licencia")]
    [InlineData("calificaciones?grupo=g1")]
    [InlineData("//login")]                                    // «Cerrar sesión» va al acceso a propósito
    [InlineData("../dashboard")]                               // sacar y empujar es otra cosa: no es sólo volver
    [InlineData("../examen-panel?asignacion=7")]
    public void Ir_a_otro_sitio_desde_el_menu_pasa(string destino)
    {
        var (guardia, _) = Nueva();
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar(destino, paginaActualEsElMenu: true));
    }

    /// <summary>La secuencia exacta que el 2026-10-20 dejaba a OPS en el acceso: dos «Menú principal» seguidos desde Licencia.</summary>
    [Fact]
    public void El_segundo_menu_principal_no_saca_al_menu_y_no_lleva_al_acceso()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 1000;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("..", paginaActualEsElMenu: false));            // con Licencia a la vista: saca Licencia
        reloj.Ms = 1084;                                                                                                  // el segundo, 84 ms después (medido), ya con el menú a la vista
        Assert.Equal(GuardiaDeNavegacion.Veredicto.YaEstaEnElMenu, guardia.Evaluar("..", paginaActualEsElMenu: true));
        reloj.Ms = 4000;                                                                                                  // el reintento de una prueba llega segundos después: lo para la misma regla
        Assert.Equal(GuardiaDeNavegacion.Veredicto.YaEstaEnElMenu, guardia.Evaluar("..", paginaActualEsElMenu: true));
    }

    // ------------------------------------------------------------------------------------------------------------- el doble toque

    [Fact]
    public void La_misma_peticion_dentro_de_la_ventana_se_ignora()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = 18;                                          // lo que tardó el segundo «Navigating» en la medición (E3, dobletoque)
        Assert.Equal(GuardiaDeNavegacion.Veredicto.DobleToque, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = 349;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.DobleToque, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
    }

    [Fact]
    public void Pasada_la_ventana_la_misma_peticion_vuelve_a_valer()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = (long)GuardiaDeNavegacion.VentanaDeDobleToque.TotalMilliseconds;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
    }

    [Fact]
    public void Una_peticion_ignorada_no_alarga_la_ventana()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = 200;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.DobleToque, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = 400;                                         // 400 ms desde la que sí pasó: vale, aunque la ignorada fue hace 200
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
    }

    [Fact]
    public void Peticiones_distintas_dentro_de_la_ventana_pasan()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("licencia", paginaActualEsElMenu: true));
        reloj.Ms = 50;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("grupos", paginaActualEsElMenu: false));
    }

    [Fact]
    public void Un_volver_repetido_desde_una_pantalla_profunda_tambien_es_un_doble_toque()
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("..", paginaActualEsElMenu: false));
        reloj.Ms = 80;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.DobleToque, guardia.Evaluar("..", paginaActualEsElMenu: false));    // no se salta un nivel de más
        reloj.Ms = 900;                                         // volver dos niveles a propósito (viendo cada pantalla) sí vale
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar("..", paginaActualEsElMenu: false));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Sin_destino_legible_no_se_toca_nada(string? destino)
    {
        var (guardia, reloj) = Nueva();
        reloj.Ms = 0;
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar(destino, paginaActualEsElMenu: true));
        Assert.Equal(GuardiaDeNavegacion.Veredicto.Pasa, guardia.Evaluar(destino, paginaActualEsElMenu: true));
    }

    // ------------------------------------------------------------------------------------------------------------- qué es «sólo volver»

    [Theory]
    [InlineData("..", true)]
    [InlineData("../..", true)]
    [InlineData("../../../..", true)]
    [InlineData("/../..", true)]
    [InlineData("../", true)]
    [InlineData("../dashboard", false)]
    [InlineData("./..", false)]
    [InlineData("licencia", false)]
    [InlineData("//login", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Solo_volver_son_las_rutas_hechas_unicamente_de_saltos(string? destino, bool esperado) =>
        Assert.Equal(esperado, GuardiaDeNavegacion.EsSoloVolver(destino));
}

/// <summary>Cuántas pantallas hay que sacar para dejar a la vista una pantalla concreta, y qué pasa cuando ya está a la vista.</summary>
public sealed class RutasDeVueltaTests
{
    private const bool N = false, S = true;       // N = otra pantalla, S = la buscada

    [Fact]
    public void Con_la_buscada_ya_a_la_vista_no_hay_nada_que_sacar() =>
        Assert.Null(RutasDeVuelta.Hasta([N, S], porDefecto: ".."));                  // raíz + menú: antes devolvía «..» y sacaba el menú

    [Theory]
    [InlineData(1, "..")]
    [InlineData(2, "../..")]
    [InlineData(4, "../../../..")]
    public void Cuenta_las_pantallas_que_hay_encima_de_la_buscada(int encima, string esperada)
    {
        var pila = new List<bool> { N, S };
        for (var i = 0; i < encima; i++) pila.Add(N);
        Assert.Equal(esperada, RutasDeVuelta.Hasta(pila, porDefecto: "x"));
    }

    [Fact]
    public void Cuenta_desde_la_ultima_coincidencia() =>
        Assert.Equal("..", RutasDeVuelta.Hasta([N, S, N, S, N], porDefecto: "x"));

    [Fact]
    public void Si_la_buscada_no_esta_en_la_pila_va_la_ruta_por_defecto()
    {
        Assert.Equal("../../..", RutasDeVuelta.Hasta([N, N, N], porDefecto: "../../.."));
        Assert.Equal("..", RutasDeVuelta.Hasta([], porDefecto: ".."));
        Assert.Null(RutasDeVuelta.Hasta([N, N], porDefecto: null));
    }

    /// <summary>El cierre de la clase: raíz, menú, «Clase de hoy», el curso, la sesión y el cierre. Ambas salidas, y el segundo toque de cada una.</summary>
    [Fact]
    public void Las_salidas_del_cierre_de_la_clase_cuentan_bien_y_el_segundo_toque_no_hace_nada()
    {
        // pila: raíz(0) menú(1) clase de hoy(2) curso(3) sesión(4) cierre(5)
        Assert.Equal("../../..", RutasDeVuelta.Hasta([N, N, S, N, N, N], "x"));         // «Volver a Clase de hoy»
        Assert.Equal("../../../..", RutasDeVuelta.Hasta([N, S, N, N, N, N], "x"));      // «Menú principal»
        // ya en «Clase de hoy» (el cierre se sacó): la ruta por defecto sacaría tres pantallas de más
        Assert.Null(RutasDeVuelta.Hasta([N, N, S], "../../.."));
        // ya en el menú
        Assert.Null(RutasDeVuelta.Hasta([N, S], "../../../.."));
    }
}
