using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

public class PerfilDePantallaTests
{
    [Theory]
    [InlineData(ResolucionPantalla.FullHd, 100, 1920, 1080)]
    [InlineData(ResolucionPantalla.FullHd, 80, 2400, 1350)]
    [InlineData(ResolucionPantalla.FullHd, 200, 960, 540)]
    [InlineData(ResolucionPantalla.Uhd4k, 100, 3840, 2160)]
    [InlineData(ResolucionPantalla.Uhd4k, 200, 1920, 1080)]
    [InlineData(ResolucionPantalla.Uhd4k, 80, 4800, 2700)]
    public void Las_unidades_logicas_son_pixeles_entre_escala(ResolucionPantalla res, int escala, double ancho, double alto)
    {
        var p = new PerfilDePantalla(res, escala);
        Assert.Equal(ancho, p.AnchoLogico, 3);
        Assert.Equal(alto, p.AltoLogico, 3);
    }

    [Fact]
    public void Un_4k_al_200_maqueta_igual_que_un_full_hd_al_100()
    {
        Assert.Equal(new PerfilDePantalla(ResolucionPantalla.FullHd, 100).TechoDeMedio, new PerfilDePantalla(ResolucionPantalla.Uhd4k, 200).TechoDeMedio);
    }

    [Theory]
    [InlineData("auto", ResolucionPantalla.Auto, 100)]
    [InlineData("1920x1080@125", ResolucionPantalla.FullHd, 125)]
    [InlineData("3840x2160@200", ResolucionPantalla.Uhd4k, 200)]
    [InlineData("", ResolucionPantalla.Auto, 100)]
    [InlineData(null, ResolucionPantalla.Auto, 100)]
    [InlineData("1920x1080@33", ResolucionPantalla.Auto, 100)]
    [InlineData("800x600@100", ResolucionPantalla.Auto, 100)]
    [InlineData("basura", ResolucionPantalla.Auto, 100)]
    public void La_clave_guardada_se_lee_y_lo_raro_cae_en_automatico(string? clave, ResolucionPantalla res, int escala)
    {
        var p = PerfilDePantalla.Leer(clave);
        Assert.Equal(res, p.Resolucion);
        Assert.Equal(escala, p.EscalaPct);
    }

    [Theory]
    [InlineData(ResolucionPantalla.Auto, 100)]
    [InlineData(ResolucionPantalla.FullHd, 80)]
    [InlineData(ResolucionPantalla.Uhd4k, 150)]
    public void La_clave_ida_y_vuelta(ResolucionPantalla res, int escala)
    {
        var p = res == ResolucionPantalla.Auto ? PerfilDePantalla.Auto : new PerfilDePantalla(res, escala);
        Assert.Equal(p, PerfilDePantalla.Leer(p.Clave));
    }

    [Theory]
    [InlineData(1920, 1.0, ResolucionPantalla.FullHd, 100)]
    [InlineData(1920, 1.25, ResolucionPantalla.FullHd, 125)]
    [InlineData(3840, 2.0, ResolucionPantalla.Uhd4k, 200)]
    [InlineData(3840, 1.5, ResolucionPantalla.Uhd4k, 150)]
    [InlineData(1920, 0.8, ResolucionPantalla.FullHd, 80)]
    public void Se_detecta_el_perfil_estandar_mas_parecido(double anchoPx, double densidad, ResolucionPantalla res, int escala)
    {
        var p = PerfilDePantalla.Detectar(anchoPx, densidad);
        Assert.Equal(res, p.Resolucion);
        Assert.Equal(escala, p.EscalaPct);
    }

    [Fact]
    public void Sin_medidas_la_deteccion_es_automatica() => Assert.True(PerfilDePantalla.Detectar(0, 1).EsAuto);
}

public class AjusteDeMedioTests
{
    private const double P169 = 9.0 / 16.0;

    [Fact]
    public void El_video_de_la_captura_cabe_entero_en_la_proyeccion_de_1920x1080()
    {
        // El visor medido en la captura del defecto: 1432 de ancho útil × 682 de alto visible (−32 de margen).
        var caja = AjusteDeMedio.Ajustar(1432, 650, P169);
        Assert.True(caja.Alto <= 650);
        Assert.True(caja.Ancho <= 1432);
        Assert.Equal(caja.Ancho * P169, caja.Alto, 0);   // conserva el 16∶9
    }

    [Fact]
    public void Un_video_ancho_se_limita_por_el_alto_y_uno_alto_por_el_ancho()
    {
        var ancho = AjusteDeMedio.Ajustar(1400, 600, P169);
        Assert.Equal(600, ancho.Alto, 0);
        Assert.True(ancho.Ancho < 1400);

        var vertical = AjusteDeMedio.Ajustar(1400, 600, 16.0 / 9);   // 9∶16 vertical
        Assert.Equal(600, vertical.Alto, 0);
        Assert.True(vertical.Ancho < 400);
    }

    [Fact]
    public void Si_hay_alto_de_sobra_manda_el_ancho()
    {
        var caja = AjusteDeMedio.Ajustar(900, 2000, P169);
        Assert.Equal(900, caja.Ancho);
        Assert.Equal(506, caja.Alto);
    }

    [Fact]
    public void Sin_ancho_conocido_no_se_maqueta_nada() => Assert.True(AjusteDeMedio.Ajustar(0, 0, P169).EsVacia);

    [Fact]
    public void Con_alto_desconocido_se_ajusta_al_ancho()
    {
        var caja = AjusteDeMedio.Ajustar(1000, 0, P169);
        Assert.Equal(1000, caja.Ancho);
    }

    [Fact]
    public void Con_muy_poco_alto_gana_el_ancho_minimo_y_la_pagina_se_desplaza()
    {
        var caja = AjusteDeMedio.Ajustar(1000, 60, P169);
        Assert.Equal(AjusteDeMedio.AnchoMinimo, caja.Ancho);
    }

    [Theory]
    [InlineData(null, null, P169)]
    [InlineData(1280, 720, P169)]
    [InlineData(1600, 1000, 0.625)]
    [InlineData(640, 480, 0.75)]
    [InlineData(0, 720, P169)]
    [InlineData(1280, 0, P169)]
    [InlineData(100, 1000, P169)]   // proporción absurda: se ignora
    public void La_proporcion_sale_del_medio_o_es_16_9(int? w, int? h, double esperada) =>
        Assert.Equal(esperada, AjusteDeMedio.Proporcion(w, h), 4);

    [Theory]
    [InlineData(ResolucionPantalla.FullHd, 100)]
    [InlineData(ResolucionPantalla.FullHd, 80)]
    [InlineData(ResolucionPantalla.FullHd, 200)]
    [InlineData(ResolucionPantalla.Uhd4k, 100)]
    [InlineData(ResolucionPantalla.Uhd4k, 80)]
    [InlineData(ResolucionPantalla.Uhd4k, 200)]
    public void Cada_perfil_deja_el_video_dentro_de_su_techo_y_en_16_9(ResolucionPantalla res, int escala)
    {
        var perfil = new PerfilDePantalla(res, escala);
        // Ventana más grande que el perfil: manda el perfil.
        var caja = AjusteDeMedio.Ajustar(9000, 9000, P169, perfil);
        // Un Full HD al 200 % (960×540 lógicos) no deja ni el chrome de OPS: ahí manda el mínimo legible y la página se desplaza.
        Assert.True(caja.Ancho <= Math.Max(perfil.TechoDeMedio.Ancho, AjusteDeMedio.AnchoMinimo));
        Assert.True(caja.Alto <= Math.Max(perfil.TechoDeMedio.Alto, AjusteDeMedio.AltoMinimo));
        Assert.Equal(caja.Ancho * P169, caja.Alto, 0);
    }

    [Fact]
    public void El_perfil_manual_nunca_agranda_mas_de_lo_que_mide_la_ventana()
    {
        var caja = AjusteDeMedio.Ajustar(700, 400, P169, new PerfilDePantalla(ResolucionPantalla.Uhd4k, 100));
        Assert.True(caja.Ancho <= 700);
        Assert.True(caja.Alto <= 400);
    }

    [Fact]
    public void Sin_medidas_de_ventana_el_perfil_manual_da_el_recuadro()
    {
        var caja = AjusteDeMedio.Ajustar(0, 0, P169, new PerfilDePantalla(ResolucionPantalla.FullHd, 100));
        Assert.False(caja.EsVacia);
    }
}
