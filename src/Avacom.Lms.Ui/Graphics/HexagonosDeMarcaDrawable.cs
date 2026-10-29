using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Graphics;

/// <summary>Dibujo del efecto «Hexágonos de marca»: cuatro hexágonos grandes de puntas redondeadas, de los colores del logo al 8–14 %.</summary>
public sealed class HexagonosDeMarcaDrawable : IDrawable
{
    // (centro x, centro y) en fracción del área, ancho en fracción del alto, color y opacidad.
    private static readonly (float X, float Y, float Ancho, Color Color, float Alfa)[] Hexagonos =
    [
        (0.06f, 0.18f, 0.62f, Ds.Azul500, 0.10f),
        (0.97f, 0.12f, 0.46f, Ds.Magenta500, 0.08f),
        (0.92f, 0.92f, 0.70f, Ds.Amarillo500, 0.14f),
        (0.10f, 0.98f, 0.40f, Ds.Verde500, 0.10f),
    ];

    public void Draw(ICanvas canvas, RectF area)
    {
        if (area.Width <= 0 || area.Height <= 0) return;
        canvas.Antialias = true;
        foreach (var (x, y, ancho, color, alfa) in Hexagonos)
        {
            var w = ancho * area.Height;
            var h = w * 184f / 160f;
            var r = new RectF(area.X + x * area.Width - w / 2, area.Y + y * area.Height - h / 2, w, h);
            canvas.FillColor = color.WithAlpha(alfa);
            canvas.FillPath(Hexagono(r));
        }
    }

    /// <summary>El mismo hexágono redondeado del panal (referencia 160 × 184, puntas arriba y abajo).</summary>
    private static PathF Hexagono(RectF a)
    {
        PointF P(float x, float y) => new(a.X + x * a.Width / 160f, a.Y + y * a.Height / 184f);
        var p = new PathF();
        p.MoveTo(P(67, 7)); p.QuadTo(P(80, 0), P(93, 7));
        p.LineTo(P(147, 39)); p.QuadTo(P(160, 47), P(160, 61));
        p.LineTo(P(160, 123)); p.QuadTo(P(160, 137), P(147, 145));
        p.LineTo(P(93, 177)); p.QuadTo(P(80, 184), P(67, 177));
        p.LineTo(P(13, 145)); p.QuadTo(P(0, 137), P(0, 123));
        p.LineTo(P(0, 61)); p.QuadTo(P(0, 47), P(13, 39));
        p.Close();
        return p;
    }
}
