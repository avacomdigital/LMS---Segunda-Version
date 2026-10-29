namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Cuerpo lleno de un <c>ProfessorHexTile</c> (Aula · Design System): el mismo hexágono redondeado del control
/// (referencia 160 × 184, puntas arriba y abajo) pintado en un <see cref="GraphicsView"/> con sombra difusa del color
/// de acento y relleno 600 → 700 del mismo color a 135°.
///
/// Va en un lienzo propio y no en un <c>Path</c> con pincel degradado porque, en Windows, <c>ShapeDrawable</c>
/// recorta al trazado antes de rellenar con un degradado y Direct2D falla (D2DERR_BAD_NUMBER) en el primer cuadro;
/// aquí no hay recorte. El lienzo se dibuja con un margen (<see cref="Inset"/>) para que la sombra no quede cortada.
/// </summary>
public sealed class HexGlassDrawable : IDrawable
{
    /// <summary>Color de acento de la materia o módulo.</summary>
    public Color Accent { get; set; } = Colors.MediumPurple;

    /// <summary>Aire entre el borde del lienzo y el hexágono, donde vive el resplandor.</summary>
    public float Inset { get; set; } = 24f;

    public void Draw(ICanvas canvas, RectF area)
    {
        try { Dibujar(canvas, area); }
        catch (Exception error) { Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ui", $"HexGlassDrawable · {area}", error); }
    }

    private void Dibujar(ICanvas canvas, RectF area)
    {
        if (area.Width <= Inset * 2 || area.Height <= Inset * 2) return;
        var acento = Accent ?? Colors.MediumPurple;
        var hex = Hexagono(area, Inset);
        var caja = hex.Bounds;

        canvas.SaveState();
        canvas.Antialias = true;

        // Aula · Design System: sombra difusa del mismo color y relleno 600 → 700 del acento a 135°. Sin reflejo ni canto.
        canvas.SaveState();
        canvas.SetShadow(new SizeF(0, 8), 20, acento.WithAlpha(0.30f));
        canvas.FillColor = acento;
        canvas.FillPath(hex);
        canvas.RestoreState();

        canvas.SetFillPaint(new LinearGradientPaint
        {
            StartColor = acento,
            EndColor = Avacom.Lms.Ui.Design.Ds.Oscuro(acento),
            StartPoint = new Point(0, 0), EndPoint = new Point(1, 1),
        }, caja);
        canvas.FillPath(hex);

        canvas.RestoreState();
    }

    /// <summary>Escala un punto de la referencia 160 × 184 al hexágono dentro del área, dejando el margen.</summary>
    private static PointF P(RectF area, float inset, float x, float y) => new(
        area.X + inset + x * (area.Width - inset * 2) / 160f,
        area.Y + inset + y * (area.Height - inset * 2) / 184f);

    /// <summary>El mismo trazado que el Path del control: seis lados rectos y seis puntas redondeadas con curvas cuadráticas.</summary>
    private static PathF Hexagono(RectF a, float i)
    {
        var p = new PathF();
        p.MoveTo(P(a, i, 67, 7));
        p.QuadTo(P(a, i, 80, 0), P(a, i, 93, 7));
        p.LineTo(P(a, i, 147, 39));
        p.QuadTo(P(a, i, 160, 47), P(a, i, 160, 61));
        p.LineTo(P(a, i, 160, 123));
        p.QuadTo(P(a, i, 160, 137), P(a, i, 147, 145));
        p.LineTo(P(a, i, 93, 177));
        p.QuadTo(P(a, i, 80, 184), P(a, i, 67, 177));
        p.LineTo(P(a, i, 13, 145));
        p.QuadTo(P(a, i, 0, 137), P(a, i, 0, 123));
        p.LineTo(P(a, i, 0, 61));
        p.QuadTo(P(a, i, 0, 47), P(a, i, 13, 39));
        p.Close();
        return p;
    }
}
