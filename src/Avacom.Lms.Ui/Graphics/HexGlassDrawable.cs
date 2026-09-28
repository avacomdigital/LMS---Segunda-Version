namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Cuerpo Liquid Glass de un <c>ProfessorHexTile</c>: el mismo hexágono redondeado del control (referencia 160 × 184,
/// puntas arriba y abajo) pintado en un <see cref="GraphicsView"/> con resplandor del color de acento (sombra
/// difusa), cuerpo translúcido con degradado vertical, reflejo blanco en la mitad superior y canto luminoso, más
/// vivo en los lados que reciben la luz (arriba y a la izquierda).
///
/// Va en un lienzo propio y no en un <c>Path</c> con pincel degradado porque, en Windows, <c>ShapeDrawable</c>
/// recorta al trazado antes de rellenar con un degradado y Direct2D falla (D2DERR_BAD_NUMBER) en el primer cuadro;
/// aquí no hay recorte: los degradados se rellenan directamente sobre las geometrías. El lienzo se dibuja con un
/// margen (<see cref="Inset"/>) alrededor del hexágono para que el resplandor no quede cortado.
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
        var mitad = MitadSuperior(area, Inset);
        var caja = hex.Bounds;

        canvas.SaveState();
        canvas.Antialias = true;

        // Resplandor: el cuerpo con una sombra difusa del propio acento.
        canvas.SaveState();
        canvas.SetShadow(new SizeF(0, 6), 22, acento.WithAlpha(0.55f));
        canvas.FillColor = acento.WithAlpha(0.72f);
        canvas.FillPath(hex);
        canvas.RestoreState();

        // Cuerpo: el acento algo más claro arriba, donde da la luz, y más hondo abajo.
        canvas.SetFillPaint(new LinearGradientPaint
        {
            StartColor = acento.AddLuminosity(0.08f).WithAlpha(0.84f),
            EndColor = acento.AddLuminosity(-0.08f).WithAlpha(0.80f),
            StartPoint = new Point(0, 0), EndPoint = new Point(0, 1),
        }, caja);
        canvas.FillPath(hex);

        // Reflejo: blanco que se funde hacia la mitad del hexágono.
        canvas.SetFillPaint(new LinearGradientPaint
        {
            StartColor = Colors.White.WithAlpha(0.55f),
            EndColor = Colors.White.WithAlpha(0f),
            StartPoint = new Point(0, 0), EndPoint = new Point(0, 1),
        }, mitad.Bounds);
        canvas.FillPath(mitad);

        // Canto: un filo blanco tenue alrededor y otro más vivo en los lados iluminados (izquierda y arriba).
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.StrokeLineCap = LineCap.Round;
        canvas.StrokeColor = Colors.White.WithAlpha(0.42f);
        canvas.StrokeSize = 1.2f;
        canvas.DrawPath(hex);
        canvas.StrokeColor = Colors.White.WithAlpha(0.9f);
        canvas.StrokeSize = 1.5f;
        canvas.DrawPath(LadoIluminado(area, Inset));

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

    /// <summary>La parte superior del hexágono hasta el 55 % de su alto, para el reflejo (sin recortar).</summary>
    private static PathF MitadSuperior(RectF a, float i)
    {
        var p = new PathF();
        p.MoveTo(P(a, i, 0, 101));
        p.LineTo(P(a, i, 0, 61));
        p.QuadTo(P(a, i, 0, 47), P(a, i, 13, 39));
        p.LineTo(P(a, i, 67, 7));
        p.QuadTo(P(a, i, 80, 0), P(a, i, 93, 7));
        p.LineTo(P(a, i, 147, 39));
        p.QuadTo(P(a, i, 160, 47), P(a, i, 160, 61));
        p.LineTo(P(a, i, 160, 101));
        p.Close();
        return p;
    }

    /// <summary>Del lado izquierdo (abajo) hasta la punta superior derecha: los cantos que reciben la luz.</summary>
    private static PathF LadoIluminado(RectF a, float i)
    {
        var p = new PathF();
        p.MoveTo(P(a, i, 0, 118));
        p.LineTo(P(a, i, 0, 61));
        p.QuadTo(P(a, i, 0, 47), P(a, i, 13, 39));
        p.LineTo(P(a, i, 67, 7));
        p.QuadTo(P(a, i, 80, 0), P(a, i, 93, 7));
        p.LineTo(P(a, i, 135, 32));
        return p;
    }
}
