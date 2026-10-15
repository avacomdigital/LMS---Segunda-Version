using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Piezas que comparten las cinco pantallas de Calificaciones (MOD-011): quién actúa y qué rol tiene, los tonos de <see cref="Matiz"/> traducidos a los del examen, las filas y
/// las tarjetas de aviso. Sólo Border, Label y Button del kit: nada de Path ni de Ellipse (un Path degenerado deja sin pintar todos los lienzos Win2D de la ventana).
/// </summary>
internal static class CalificacionesUi
{
    // ---------------------------------------------------------------------------------------- quién actúa
    public static string Actor => Sesion.ProfesorId;
    public static bool HaySesion => Sesion.Usuario is not null;
    public static string? Rol => Sesion.Usuario?.Rol;
    public static bool PuedeLeer => PermisosDeCalificaciones.Leer(HaySesion, Rol);
    public static bool PuedeCalificar => PermisosDeCalificaciones.Calificar(HaySesion, Rol);
    public static bool PuedeConfigurar => PermisosDeCalificaciones.Configurar(HaySesion, Rol);

    // --------------------------------------------------------------------------------------------- tonos
    public static Tono ATono(Matiz matiz) => matiz switch
    {
        Matiz.Info => Tono.Info,
        Matiz.Ambar => Tono.Ambar,
        Matiz.Exito => Tono.Exito,
        Matiz.Violeta => Tono.Violeta,
        Matiz.Gris => Tono.Gris,
        _ => Tono.Neutro,
    };

    public static Border Pildora(string texto, Matiz matiz, double tamano = 13) => ExamenUi.Pildora(texto, ATono(matiz), tamano);

    public static Border PildoraEnFila(string texto, Matiz matiz, double tamano = 13) => ExamenUi.PildoraEnFila(texto, ATono(matiz), tamano);

    // ------------------------------------------------------------------------------------------ superficies

    /// <summary>Una fila de una lista: fondo suave, filo de 1 px y las esquinas del kit (el renglón de un alumno, de una revisión, de una versión).</summary>
    public static Border Fila(View contenido, Thickness? relleno = null) => new()
    {
        BackgroundColor = Color.FromArgb("#FAFAFB"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = relleno ?? new Thickness(16, 12),
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = contenido,
    };

    /// <summary>
    /// La tarjeta de lo que no se puede ver con este rol (TST-069): se dice sin llamar al nodo. El nodo igualmente lo denegaría; la pantalla sólo evita ofrecer lo que no aplica.
    /// </summary>
    public static View SinAcceso(string titulo, string texto)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion(titulo));
        pila.Add(Ds.Secundario(texto, 16));
        return ExamenUi.Tarjeta(pila);
    }

    /// <summary>Una tarjeta con un título, una frase y, si hace falta, un botón (el estado «no se pudo leer» de cada pantalla).</summary>
    public static View Estado(string titulo, string texto, params View[] acciones)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion(titulo));
        pila.Add(Ds.Secundario(texto, 16));
        foreach (var accion in acciones)
        {
            accion.HorizontalOptions = LayoutOptions.Start;        // la cápsula de un botón llena la fila si no se le dice dónde quedarse
            pila.Add(accion);
        }
        return ExamenUi.Tarjeta(pila);
    }

    /// <summary>La caja gris de un valor con su rótulo (los cuatro bloques de la calificación): rótulo pequeño arriba, valor grande, una nota debajo.</summary>
    public static Border Bloque(string rotulo, string valor, string? nota, double ancho = 250, string? id = null)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(EstudioUi.Eyebrow(rotulo.ToUpperInvariant()));
        pila.Add(new Label { Text = valor, FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(nota)) pila.Add(Ds.Secundario(nota!, 13));
        var caja = new Border
        {
            BackgroundColor = Color.FromArgb("#F7F7F8"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(18, 14),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila, WidthRequest = ancho,
            Margin = new Thickness(0, 0, 12, 12),
        };
        if (id is not null) caja.AutomationId = id;
        SemanticProperties.SetDescription(caja, $"{rotulo}: {valor}{(string.IsNullOrWhiteSpace(nota) ? string.Empty : ". " + nota)}");
        return caja;
    }

    /// <summary>Un renglón «etiqueta pequeña · valor» para las fichas de datos.</summary>
    public static View Dato(string rotulo, string valor, double ancho = 200) => ExamenUi.Dato(rotulo, valor, ancho);

    // ------------------------------------------------------------------------------------------ toques

    /// <summary>
    /// Lo que se toca corre en un <c>async void</c>: una excepción que se escapara cerraría la aplicación en plena clase. Se anota en el registro de fallos con la pantalla y el
    /// lugar, y la pantalla sigue.
    /// </summary>
    public static Func<Task> Seguro(string pantalla, string donde, Func<Task> accion) => async () =>
    {
        try { await accion(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", $"{pantalla}.{donde}", ex); }
    };

    // ------------------------------------------------------------------------------------------- errores

    /// <summary>El error del último intento del cliente de Gradebook, en palabras (sin conexión, conflicto, permiso, modo simple…).</summary>
    public static string Error(IGradebookApi api) => GradebookTexto.Error(api.UltimoError, api.UltimoMotivo);

    /// <summary>¿El último error fue por no llegar al nodo? Entonces lo hecho NO se confirmó y lo que se veía se conserva.</summary>
    public static bool SinConexion(IGradebookApi api) => GradebookTexto.SinConexion(api.UltimoError);
}

/// <summary>
/// El aviso de lo que acaba de pasar, arriba de la pantalla: uno a la vez, se quita solo a los 9 s si es de buenas noticias o informa, y se queda si pide atención (ámbar). Un
/// aviso nuevo reemplaza al anterior y su temporizador no lo borra.
/// </summary>
internal sealed class AvisoTemporal(VerticalStackLayout host)
{
    private int _version;

    public void Mostrar(string titulo, string? detalle, Tono tono)
    {
        host.Clear();
        host.Add(ExamenUi.Aviso(titulo, detalle, tono));
        var version = ++_version;
        if (tono is Tono.Exito or Tono.Info)
            host.Dispatcher.DispatchDelayed(TimeSpan.FromSeconds(9), () => { if (version == _version) host.Clear(); });
    }

    public void Quitar()
    {
        _version++;
        host.Clear();
    }
}
