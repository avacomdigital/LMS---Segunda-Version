using Microsoft.Maui.Graphics;

namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Fondo decorativo de panal para las pantallas del kit: hexágonos grandes con la punta arriba (lados verticales),
/// las seis esquinas redondeadas, sólo contorno, en filas alternas desplazadas medio hexágono y cada uno separado
/// del vecino por unos pocos píxeles, como en la referencia (blanco, líneas gris muy claro de 1–1,5 px).
///
/// Vive en un único <see cref="GraphicsView"/> y se traza entero en <see cref="Draw"/>: calcula cuántas filas y
/// columnas cubren el lienzo, añade margen fuera del área visible (los hexágonos cortados por el borde son
/// deseados; los huecos, no) y dibuja todos los contornos con un solo <see cref="PathF"/> y una sola llamada de
/// trazo, así que cuesta lo mismo en una tableta Android que en Windows. La retícula se ancla al centro del lienzo,
/// de modo que el patrón queda simétrico respecto a una tarjeta centrada y se adapta solo a cualquier tamaño de
/// ventana u orientación: el <c>GraphicsView</c> vuelve a dibujar cuando cambia de tamaño.
///
/// Uso, como capa más baja de la página y sin tocar el contenido existente:
/// <code>
/// xmlns:gfx="clr-namespace:Avacom.Lms.Ui.Graphics;assembly=Avacom.Lms.Ui"
/// ...
/// &lt;Grid&gt;
///     &lt;GraphicsView InputTransparent="True" HorizontalOptions="Fill" VerticalOptions="Fill"&gt;
///         &lt;GraphicsView.Drawable&gt;
///             &lt;gfx:RoundedHexagonBackgroundDrawable HexagonWidth="240" CornerRadius="12" Gap="6" StrokeColor="#E5E7EB" StrokeWidth="1.25"/&gt;
///         &lt;/GraphicsView.Drawable&gt;
///     &lt;/GraphicsView&gt;
///     &lt;!-- contenido existente, tal cual --&gt;
/// &lt;/Grid&gt;
/// </code>
/// <c>InputTransparent="True"</c> es obligatorio: la capa es 100 % decorativa y nunca debe capturar toques, clics,
/// desplazamiento, gestos ni el foco de un <c>Entry</c>.
/// </summary>
public sealed class RoundedHexagonBackgroundDrawable : IDrawable
{
    private const float Raiz3 = 1.7320508f;

    /// <summary>Ancho de cada hexágono, medido entre sus dos lados verticales (unidades independientes del dispositivo).</summary>
    public float HexagonWidth { get; set; } = 240f;

    /// <summary>Alto de cada hexágono, de punta a punta. 0 = hexágono regular (ancho × 2/√3, diagonales a 30°).</summary>
    public float HexagonHeight { get; set; }

    /// <summary>Radio con que se redondean las seis esquinas. Se recorta si no cabe en los lados.</summary>
    public float CornerRadius { get; set; } = 12f;

    /// <summary>Color del contorno. Sobre blanco, #E5E7EB; sobre un fondo con tinte conviene una tinta translúcida.</summary>
    public Color StrokeColor { get; set; } = Color.FromArgb("#E5E7EB");

    /// <summary>Grosor del contorno (1–1,5).</summary>
    public float StrokeWidth { get; set; } = 1.25f;

    /// <summary>Separación entre hexágonos vecinos, igual en todas las direcciones. 0 = comparten el borde.</summary>
    public float Gap { get; set; } = 6f;

    /// <summary>Distancia horizontal entre centros de una misma fila. 0 = automática (ancho + separación).</summary>
    public float HorizontalSpacing { get; set; }

    /// <summary>Distancia vertical entre filas. 0 = automática: la que encaja las filas dejando la misma separación en diagonal.</summary>
    public float VerticalSpacing { get; set; }

    /// <summary>Opacidad global del patrón (0–1); multiplica el alfa de <see cref="StrokeColor"/>.</summary>
    public float Opacity { get; set; } = 1f;

    /// <summary>Relleno de todo el lienzo antes del patrón. null = transparente: se ve el fondo de la página.</summary>
    public Color? BackgroundColor { get; set; }

    public void Draw(ICanvas canvas, RectF dirtyRect)
    {
        if (BackgroundColor is not null)
        {
            canvas.FillColor = BackgroundColor;
            canvas.FillRectangle(dirtyRect);
        }

        var alfa = StrokeColor.Alpha * Math.Clamp(Opacity, 0f, 1f);
        if (dirtyRect.Width <= 0 || dirtyRect.Height <= 0 || HexagonWidth <= 0 || StrokeWidth <= 0 || alfa <= 0) return;

        // Retícula: paso horizontal entre centros de una fila, paso vertical entre filas y desfase de las filas impares.
        var anchoHex = HexagonWidth;
        var altoHex = HexagonHeight > 0 ? HexagonHeight : anchoHex * 2f / Raiz3;
        var separacion = Math.Max(0f, Gap);
        var pasoH = HorizontalSpacing > 0 ? HorizontalSpacing : anchoHex + separacion;
        var pasoV = VerticalSpacing > 0 ? VerticalSpacing : PasoVertical(anchoHex, altoHex, separacion);
        var desfaseFila = pasoH / 2f;

        // Cuántos hexágonos hacen falta para cubrir el lienzo, más dos de margen para que no queden huecos en los bordes.
        var columnas = (int)Math.Ceiling(dirtyRect.Width / pasoH) + 2;
        var filas = (int)Math.Ceiling(dirtyRect.Height / pasoV) + 2;
        var mitadColumnas = columnas / 2 + 1;
        var mitadFilas = filas / 2 + 1;
        var centro = dirtyRect.Center;

        var esquinas = EsquinasRedondeadas(anchoHex, altoHex, CornerRadius);
        var trazo = new PathF();
        for (var fila = -mitadFilas; fila <= mitadFilas; fila++)
        {
            var cy = centro.Y + fila * pasoV;
            if (cy + altoHex / 2f < dirtyRect.Top || cy - altoHex / 2f > dirtyRect.Bottom) continue;
            var desfase = (fila & 1) != 0 ? desfaseFila : 0f;
            for (var columna = -mitadColumnas; columna <= mitadColumnas; columna++)
            {
                var cx = centro.X + columna * pasoH + desfase;
                if (cx + anchoHex / 2f < dirtyRect.Left || cx - anchoHex / 2f > dirtyRect.Right) continue;
                AgregarHexagono(trazo, esquinas, cx, cy);
            }
        }

        canvas.Antialias = true;
        canvas.StrokeColor = StrokeColor.WithAlpha(alfa);
        canvas.StrokeSize = StrokeWidth;
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.StrokeLineCap = LineCap.Round;
        canvas.DrawPath(trazo);
    }

    /// <summary>
    /// Paso entre filas con el que las puntas de una fila entran en las muescas de la anterior dejando en las
    /// diagonales la misma separación que entre lados verticales. Sin separación es ¾ del alto del hexágono.
    /// </summary>
    private static float PasoVertical(float anchoHex, float altoHex, float separacion)
    {
        var punta = altoHex / 4f;                                   // alto del triángulo de cada punta
        var hipotenusa = MathF.Sqrt(punta * punta + anchoHex * anchoHex / 4f);
        var seno = punta / hipotenusa;                              // de la diagonal respecto a la horizontal
        var coseno = anchoHex / 2f / hipotenusa;
        return altoHex - punta + separacion * (1f - seno / 2f) / coseno;
    }

    /// <summary>
    /// Por cada vértice del hexágono (relativo a su centro): dónde acaba el lado que llega (A), los dos puntos de
    /// control de la curva y dónde empieza el lado que sale (B). El arco es tangente a ambos lados; la cúbica que lo
    /// aproxima lleva los manejadores sobre las tangentes, hacia el vértice.
    /// </summary>
    private static (PointF A, PointF C1, PointF C2, PointF B)[] EsquinasRedondeadas(float anchoHex, float altoHex, float radio)
    {
        var w = anchoHex / 2f;
        var h = altoHex / 2f;
        var p = altoHex / 4f;
        PointF[] vertices = { new(0, -h), new(w, -h + p), new(w, h - p), new(0, h), new(-w, h - p), new(-w, -h + p) };
        var n = vertices.Length;
        var esquinas = new (PointF, PointF, PointF, PointF)[n];
        for (var i = 0; i < n; i++)
        {
            var v = vertices[i];
            var anterior = vertices[(i + n - 1) % n];
            var siguiente = vertices[(i + 1) % n];
            var (haciaAnterior, largoAnterior) = Unitario(anterior.X - v.X, anterior.Y - v.Y);
            var (haciaSiguiente, largoSiguiente) = Unitario(siguiente.X - v.X, siguiente.Y - v.Y);

            // Ángulo interior θ: el arco de radio r tangente a ambos lados empieza a r / tan(θ/2) del vértice.
            var coseno = Math.Clamp(haciaAnterior.X * haciaSiguiente.X + haciaAnterior.Y * haciaSiguiente.Y, -1f, 1f);
            var theta = MathF.Acos(coseno);
            var r = Math.Max(0f, radio);
            var distancia = r / MathF.Tan(theta / 2f);
            var maxima = Math.Min(largoAnterior, largoSiguiente) / 2f;
            if (distancia > maxima)
            {
                distancia = maxima;
                r = distancia * MathF.Tan(theta / 2f);
            }

            // Giro del arco α = π − θ; manejadores de (4/3)·tan(α/4)·r, la aproximación cúbica clásica de un arco.
            var manejador = 4f / 3f * MathF.Tan((MathF.PI - theta) / 4f) * r;
            var a = new PointF(v.X + haciaAnterior.X * distancia, v.Y + haciaAnterior.Y * distancia);
            var b = new PointF(v.X + haciaSiguiente.X * distancia, v.Y + haciaSiguiente.Y * distancia);
            var c1 = new PointF(a.X - haciaAnterior.X * manejador, a.Y - haciaAnterior.Y * manejador);
            var c2 = new PointF(b.X - haciaSiguiente.X * manejador, b.Y - haciaSiguiente.Y * manejador);
            esquinas[i] = (a, c1, c2, b);
        }
        return esquinas;
    }

    /// <summary>Añade al trazo un hexágono cerrado centrado en (cx, cy): línea hasta cada esquina y curva por ella.</summary>
    private static void AgregarHexagono(PathF trazo, (PointF A, PointF C1, PointF C2, PointF B)[] esquinas, float cx, float cy)
    {
        for (var i = 0; i < esquinas.Length; i++)
        {
            var (a, c1, c2, b) = esquinas[i];
            if (i == 0) trazo.MoveTo(cx + a.X, cy + a.Y);
            else trazo.LineTo(cx + a.X, cy + a.Y);
            if (a != b) trazo.CurveTo(cx + c1.X, cy + c1.Y, cx + c2.X, cy + c2.Y, cx + b.X, cy + b.Y);
        }
        trazo.Close();
    }

    private static (PointF Direccion, float Largo) Unitario(float dx, float dy)
    {
        var largo = MathF.Sqrt(dx * dx + dy * dy);
        return largo > 0 ? (new PointF(dx / largo, dy / largo), largo) : (new PointF(0, 0), 0f);
    }
}
