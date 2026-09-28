namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Ilustración decorativa de «Clase de hoy»: un libro abierto de cristal blanco-lavanda con halo violeta y tres
/// hexágonos pequeños (azul, rosa, violeta) que flotan alrededor. Se pinta entero en un <see cref="GraphicsView"/>
/// transparente sobre una caja lógica de 320 × 240 que se escala (uniforme) al área asignada, así que no hay
/// coordenadas fijas para una resolución. <see cref="Phase"/> mueve la flotación (el libro y cada hexágono con su
/// propio ritmo); el reloj lo lleva <c>GlassBookView</c>. Sombras y degradados van con las primitivas de
/// Microsoft.Maui.Graphics, idénticas en Windows y Android; el libro se inclina 6° para que se lea el volumen.
/// </summary>
public sealed class GlassBookDrawable : IDrawable
{
    private static readonly Color TapaClara = Color.FromArgb("#7A55B0");
    private static readonly Color TapaOscura = Color.FromArgb("#4E2E7F");
    private static readonly Color HaloLibro = Color.FromArgb("#4A2A7A");
    private static readonly Color PaginaBaja = Color.FromArgb("#EDE6F5");
    private static readonly Color PaginaBajaDerecha = Color.FromArgb("#E6DDF2");
    private static readonly Color Surco = Color.FromArgb("#5B3C8C");
    private static readonly Color Linea = Color.FromArgb("#9C86C4");
    private static readonly Color Azul = Color.FromArgb("#3D8BFF");
    private static readonly Color Rosa = Color.FromArgb("#FF5FB7");
    private static readonly Color Violeta = Color.FromArgb("#9B6CFF");

    /// <summary>Fase de la flotación, en radianes; avanza con el tiempo.</summary>
    public float Phase { get; set; }

    public void Draw(ICanvas canvas, RectF area)
    {
        try { Dibujar(canvas, area); }
        catch (Exception error) { Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ui", $"GlassBookDrawable · {area}", error); }
    }

    private void Dibujar(ICanvas canvas, RectF area)
    {
        if (area.Width <= 0 || area.Height <= 0) return;
        var escala = Math.Min(area.Width / 320f, area.Height / 240f);
        canvas.SaveState();
        canvas.Antialias = true;
        canvas.Translate(area.X + (area.Width - 320f * escala) / 2f, area.Y + (area.Height - 240f * escala) / 2f);
        canvas.Scale(escala, escala);
        var t = Phase;

        // Hexágonos de atrás, cada uno con su ritmo.
        Hexagono(canvas, 268, 52 + MathF.Sin(t + 1.3f) * 5f, 21, Azul);
        Hexagono(canvas, 46, 46 + MathF.Sin(t + 2.6f) * 4f, 15, Rosa);

        // Libro: flota 4 px e inclinado 6° sobre su centro.
        canvas.SaveState();
        canvas.Translate(160, 136 + MathF.Sin(t) * 4f);
        canvas.Rotate(-6);
        canvas.Translate(-160, -136);
        Libro(canvas);
        canvas.RestoreState();

        // Hexágono de delante.
        Hexagono(canvas, 288, 150 + MathF.Sin(t + 0.6f) * 6f, 13, Violeta);
        canvas.RestoreState();
    }

    private static void Libro(ICanvas canvas)
    {
        var tapa = new PathF();
        tapa.MoveTo(36, 70);
        tapa.QuadTo(100, 58, 160, 86);
        tapa.QuadTo(220, 58, 284, 70);
        tapa.LineTo(284, 202);
        tapa.QuadTo(220, 196, 160, 218);
        tapa.QuadTo(100, 196, 36, 202);
        tapa.Close();

        var izquierda = new PathF();
        izquierda.MoveTo(160, 74);
        izquierda.QuadTo(104, 50, 46, 62);
        izquierda.LineTo(46, 192);
        izquierda.QuadTo(104, 184, 160, 206);
        izquierda.Close();

        var derecha = new PathF();
        derecha.MoveTo(160, 74);
        derecha.QuadTo(216, 50, 274, 62);
        derecha.LineTo(274, 192);
        derecha.QuadTo(216, 184, 160, 206);
        derecha.Close();

        // Halo violeta bajo el libro y la tapa de cristal oscuro.
        canvas.SaveState();
        canvas.SetShadow(new SizeF(0, 16), 30, HaloLibro.WithAlpha(0.55f));
        canvas.FillColor = TapaOscura.WithAlpha(0.9f);
        canvas.FillPath(tapa);
        canvas.RestoreState();
        canvas.SetFillPaint(Degradado(TapaClara.WithAlpha(0.88f), TapaOscura.WithAlpha(0.92f)), tapa.Bounds);
        canvas.FillPath(tapa);

        // Páginas: cristal blanco que se vuelve lavanda hacia abajo; la derecha apenas más apagada.
        canvas.SetFillPaint(Degradado(Colors.White.WithAlpha(0.94f), PaginaBaja.WithAlpha(0.80f)), izquierda.Bounds);
        canvas.FillPath(izquierda);
        canvas.SetFillPaint(Degradado(Colors.White.WithAlpha(0.90f), PaginaBajaDerecha.WithAlpha(0.76f)), derecha.Bounds);
        canvas.FillPath(derecha);

        // Surco del lomo: sombra que nace en el centro y se disuelve hacia fuera en cada página.
        canvas.SetFillPaint(Degradado(Surco.WithAlpha(0f), Surco.WithAlpha(0.30f), new Point(0.55, 0), new Point(1, 0)), izquierda.Bounds);
        canvas.FillPath(izquierda);
        canvas.SetFillPaint(Degradado(Surco.WithAlpha(0.30f), Surco.WithAlpha(0f), new Point(0, 0), new Point(0.45, 0)), derecha.Bounds);
        canvas.FillPath(derecha);

        // Líneas de texto: siguen la leve caída de las páginas hacia el lomo; la primera es más corta, como un título.
        canvas.StrokeColor = Linea.WithAlpha(0.55f);
        canvas.StrokeSize = 2.4f;
        canvas.StrokeLineCap = LineCap.Round;
        for (var i = 0; i < 4; i++)
        {
            var y = 96 + i * 23;
            var largo = i == 0 ? 56 : 80;
            canvas.DrawLine(62, y, 62 + largo, y + largo * 0.075f);
            canvas.DrawLine(258 - largo, y + largo * 0.075f, 258, y);
        }

        // Cantos de las páginas y reflejo de la luz en la mitad superior.
        canvas.StrokeColor = Colors.White.WithAlpha(0.9f);
        canvas.StrokeSize = 1.2f;
        canvas.DrawPath(izquierda);
        canvas.DrawPath(derecha);
        canvas.SetFillPaint(Degradado(Colors.White.WithAlpha(0.55f), Colors.White.WithAlpha(0f), new Point(0, 0), new Point(0, 0.5)), izquierda.Bounds);
        canvas.FillPath(izquierda);
        canvas.SetFillPaint(Degradado(Colors.White.WithAlpha(0.35f), Colors.White.WithAlpha(0f), new Point(0, 0), new Point(0, 0.5)), derecha.Bounds);
        canvas.FillPath(derecha);
    }

    /// <summary>Hexágono de cristal de color con puntas redondeadas, resplandor propio, canto blanco y un brillo arriba a la izquierda.</summary>
    private static void Hexagono(ICanvas canvas, float cx, float cy, float radio, Color color)
    {
        var trazo = new PathF();
        for (var i = 0; i < 6; i++)
        {
            var angulo = -MathF.PI / 2f + i * MathF.PI / 3f;
            var x = cx + radio * MathF.Cos(angulo);
            var y = cy + radio * MathF.Sin(angulo);
            if (i == 0) trazo.MoveTo(x, y);
            else trazo.LineTo(x, y);
        }
        trazo.Close();

        canvas.SaveState();
        canvas.SetShadow(new SizeF(0, 0), 16, color.WithAlpha(0.75f));
        canvas.FillColor = color.WithAlpha(0.92f);
        canvas.FillPath(trazo);
        // Un trazo grueso con uniones redondas del mismo color redondea las puntas.
        canvas.StrokeColor = color.WithAlpha(0.92f);
        canvas.StrokeSize = radio * 0.36f;
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.DrawPath(trazo);
        canvas.RestoreState();

        canvas.StrokeColor = Colors.White.WithAlpha(0.85f);
        canvas.StrokeSize = 1.4f;
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.DrawPath(trazo);
        canvas.FillColor = Colors.White.WithAlpha(0.55f);
        canvas.FillEllipse(cx - radio * 0.6f, cy - radio * 0.75f, radio * 0.7f, radio * 0.4f);
    }

    private static LinearGradientPaint Degradado(Color inicio, Color fin) => Degradado(inicio, fin, new Point(0, 0), new Point(0, 1));

    private static LinearGradientPaint Degradado(Color inicio, Color fin, Point desde, Point hasta) => new()
    {
        StartColor = inicio, EndColor = fin, StartPoint = desde, EndPoint = hasta,
    };
}
