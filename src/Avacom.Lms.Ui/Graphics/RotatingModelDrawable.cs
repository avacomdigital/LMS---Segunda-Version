using System.Numerics;

namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Render por software de una <see cref="GlbMesh"/> pequeña en un <see cref="GraphicsView"/>: perspectiva moderada,
/// sombreado plano con luz de estudio (ambiente + principal + relleno, sin sombras ni brillos), orden de pintor y
/// descarte de caras traseras. El modelo se alinea solo (su eje más largo pasa a vertical y la pieza más pequeña, la
/// punta, queda abajo), se centra y se encuadra para ocupar <see cref="FillRatio"/> del alto o del ancho del área,
/// así que no hay coordenadas fijas para una resolución. Gira como una sola unidad sobre el eje vertical, inclinado
/// <see cref="TiltDegrees"/>, y flota <see cref="FloatPixels"/> píxeles; el avance lo marca <see cref="Avanzar"/> con
/// tiempo delta, independiente de los FPS. Se pinta sobre lienzo transparente: sólo aparece el modelo. Con un
/// centenar de triángulos cuesta menos que un icono vectorial, también en una tableta.
/// </summary>
public sealed class RotatingModelDrawable : IDrawable
{
    private GlbMesh? modelo;
    private Vector3[] alineados = [];
    private Vector3 tamano;
    private float angulo;
    private double tiempo;

    /// <summary>Segundos por vuelta completa (10–16).</summary>
    public double SecondsPerTurn { get; set; } = 12;

    /// <summary>Inclinación fija sobre un eje secundario, en grados (5–12).</summary>
    public double TiltDegrees { get; set; } = 8;

    /// <summary>Amplitud de la flotación, en píxeles (2–5).</summary>
    public double FloatPixels { get; set; } = 3;

    /// <summary>Velocidad de la flotación, en rad/s (0,7 ≈ una oscilación cada 9 s).</summary>
    public double FloatSpeed { get; set; } = 0.7;

    /// <summary>Fracción del área que ocupa el modelo (0,5–0,85).</summary>
    public double FillRatio { get; set; } = 0.78;

    /// <summary>Campo de visión vertical, en grados: moderado, sin deformar el modelo.</summary>
    public double FieldOfViewDegrees { get; set; } = 28;

    /// <summary>Luz de estudio: ambiente, principal arriba a la izquierda y relleno tenue desde el lado opuesto.</summary>
    public float Ambient { get; set; } = 0.42f;
    public float KeyIntensity { get; set; } = 0.66f;
    public float FillIntensity { get; set; } = 0.22f;
    public Vector3 KeyDirection { get; set; } = Vector3.Normalize(new Vector3(-3f, 5f, 4f));
    public Vector3 FillDirection { get; set; } = Vector3.Normalize(new Vector3(4f, -1f, -3f));

    public GlbMesh? Modelo
    {
        get => modelo;
        set
        {
            modelo = value;
            Preparar();
        }
    }

    /// <summary>Avanza la animación <paramref name="segundos"/> (acotado a 0,1 s para que una pausa no dé un salto).</summary>
    public void Avanzar(double segundos)
    {
        var dt = Math.Clamp(segundos, 0, 0.1);
        if (SecondsPerTurn > 0) angulo += (float)(Math.PI * 2 / SecondsPerTurn * dt);
        tiempo += dt;
    }

    public void Draw(ICanvas canvas, RectF area)
    {
        if (modelo is null || alineados.Length == 0 || area.Width <= 0 || area.Height <= 0) return;

        var inclinacion = (float)(TiltDegrees * Math.PI / 180);
        var transformacion = Matrix4x4.CreateRotationZ(inclinacion) * Matrix4x4.CreateRotationY(angulo);
        var distancia = Distancia(area.Width, area.Height, inclinacion);
        var ojo = new Vector3(0, distancia * 0.06f, distancia);
        var vista = Matrix4x4.CreateLookAt(ojo, Vector3.Zero, Vector3.UnitY);
        var fov = (float)(FieldOfViewDegrees * Math.PI / 180);
        var proyeccion = Matrix4x4.CreatePerspectiveFieldOfView(fov, area.Width / area.Height, distancia / 20, distancia * 20);
        var modeloVista = transformacion * vista;
        var completa = modeloVista * proyeccion;
        var flotacion = (float)(Math.Sin(tiempo * FloatSpeed) * FloatPixels);

        var n = alineados.Length;
        var mundo = new Vector3[n];
        var profundidad = new float[n];
        var pantalla = new PointF[n];
        for (var i = 0; i < n; i++)
        {
            var v = alineados[i];
            mundo[i] = Vector3.Transform(v, transformacion);
            profundidad[i] = Vector3.Transform(v, modeloVista).Z;
            var c = Vector4.Transform(new Vector4(v, 1f), completa);
            var x = c.X / c.W;
            var y = c.Y / c.W;
            pantalla[i] = new PointF(area.X + (x * 0.5f + 0.5f) * area.Width, area.Y + (0.5f - y * 0.5f) * area.Height + flotacion);
        }

        // Caras visibles, sombreadas, de la más lejana a la más cercana (orden de pintor).
        var triangulos = modelo.Triangulos;
        var visibles = new List<(float Z, int Indice, Color Color)>(triangulos.Length);
        foreach (var (t, indice) in triangulos.Select((t, i) => (t, i)))
        {
            var a = mundo[t.A];
            var b = mundo[t.B];
            var c = mundo[t.C];
            var normal = Vector3.Cross(b - a, c - a);
            if (normal.LengthSquared() <= 0) continue;
            normal = Vector3.Normalize(normal);
            var centro = (a + b + c) / 3f;
            if (Vector3.Dot(normal, ojo - centro) < 0)
            {
                if (!t.DobleCara) continue;
                normal = -normal;
            }
            var luz = Ambient + KeyIntensity * MathF.Max(0, Vector3.Dot(normal, KeyDirection)) + FillIntensity * MathF.Max(0, Vector3.Dot(normal, FillDirection));
            var color = new Color(ASrgb(t.Color.X * luz), ASrgb(t.Color.Y * luz), ASrgb(t.Color.Z * luz));
            visibles.Add(((profundidad[t.A] + profundidad[t.B] + profundidad[t.C]) / 3f, indice, color));
        }
        visibles.Sort((p, q) => p.Z.CompareTo(q.Z));

        canvas.Antialias = true;
        canvas.StrokeSize = 0.8f;
        canvas.StrokeLineJoin = LineJoin.Round;
        foreach (var (_, indice, color) in visibles)
        {
            var t = triangulos[indice];
            var trazo = new PathF();
            trazo.MoveTo(pantalla[t.A]);
            trazo.LineTo(pantalla[t.B]);
            trazo.LineTo(pantalla[t.C]);
            trazo.Close();
            canvas.FillColor = color;
            canvas.FillPath(trazo);
            // Un trazo fino del mismo color cierra las rendijas del antialias entre triángulos contiguos.
            canvas.StrokeColor = color;
            canvas.DrawPath(trazo);
        }
    }

    /// <summary>Distancia de la cámara para que el modelo inclinado, en cualquier fase del giro, ocupe FillRatio del área.</summary>
    private float Distancia(float ancho, float alto, float inclinacion)
    {
        var grosor = Math.Max(tamano.X, tamano.Z);
        var altoVisible = tamano.Y * MathF.Cos(inclinacion) + grosor * MathF.Sin(inclinacion);
        var anchoVisible = tamano.Y * MathF.Sin(inclinacion) + grosor;
        var fovV = (float)(FieldOfViewDegrees * Math.PI / 180);
        var fovH = 2 * MathF.Atan(MathF.Tan(fovV / 2) * (ancho / alto));
        var relleno = (float)Math.Clamp(FillRatio, 0.1, 1);
        return MathF.Max((altoVisible / relleno / 2) / MathF.Tan(fovV / 2), (anchoVisible / relleno / 2) / MathF.Tan(fovH / 2));
    }

    /// <summary>Alinea el modelo (eje más largo a vertical, punta abajo) y lo centra en el origen.</summary>
    private void Preparar()
    {
        alineados = [];
        tamano = Vector3.Zero;
        if (modelo is null || modelo.Vertices.Length == 0) return;

        var extension = modelo.Maximo - modelo.Minimo;
        var rotacion = Matrix4x4.Identity;
        if (extension.X >= extension.Y && extension.X >= extension.Z) rotacion = Matrix4x4.CreateRotationZ(MathF.PI / 2);
        else if (extension.Z > extension.Y) rotacion = Matrix4x4.CreateRotationX(-MathF.PI / 2);
        var vertices = modelo.Vertices.Select(v => Vector3.Transform(v, rotacion)).ToArray();

        // La pieza más pequeña es la punta: si quedó arriba, se da la vuelta al modelo.
        var minimoPieza = Enumerable.Repeat(new Vector3(float.MaxValue), modelo.Piezas).ToArray();
        var maximoPieza = Enumerable.Repeat(new Vector3(float.MinValue), modelo.Piezas).ToArray();
        foreach (var t in modelo.Triangulos)
        {
            foreach (var i in new[] { t.A, t.B, t.C })
            {
                minimoPieza[t.Pieza] = Vector3.Min(minimoPieza[t.Pieza], vertices[i]);
                maximoPieza[t.Pieza] = Vector3.Max(maximoPieza[t.Pieza], vertices[i]);
            }
        }
        var (minimo, maximo) = Limites(vertices);
        var centro = (minimo + maximo) / 2;
        var punta = -1;
        var menor = float.MaxValue;
        for (var p = 0; p < modelo.Piezas; p++)
        {
            if (minimoPieza[p].X == float.MaxValue) continue;
            var lados = maximoPieza[p] - minimoPieza[p];
            var volumen = lados.X * lados.Y * lados.Z;
            if (volumen < menor) { menor = volumen; punta = p; }
        }
        if (punta >= 0 && (minimoPieza[punta].Y + maximoPieza[punta].Y) / 2 > centro.Y)
        {
            var vuelta = Matrix4x4.CreateRotationZ(MathF.PI);
            vertices = vertices.Select(v => Vector3.Transform(v, vuelta)).ToArray();
            (minimo, maximo) = Limites(vertices);
            centro = (minimo + maximo) / 2;
        }

        alineados = vertices.Select(v => v - centro).ToArray();
        tamano = maximo - minimo;
    }

    private static (Vector3 Minimo, Vector3 Maximo) Limites(Vector3[] vertices)
    {
        var minimo = new Vector3(float.MaxValue);
        var maximo = new Vector3(float.MinValue);
        foreach (var v in vertices)
        {
            minimo = Vector3.Min(minimo, v);
            maximo = Vector3.Max(maximo, v);
        }
        return (minimo, maximo);
    }

    /// <summary>De lineal (como guarda el glTF sus colores) a sRGB, que es lo que pinta el lienzo.</summary>
    private static float ASrgb(float lineal)
    {
        var c = Math.Clamp(lineal, 0f, 1f);
        return c <= 0.0031308f ? 12.92f * c : 1.055f * MathF.Pow(c, 1f / 2.4f) - 0.055f;
    }
}
