using System.Numerics;
using System.Text.Json;

namespace Avacom.Lms.Ui.Graphics;

/// <summary>
/// Malla triangulada de un glTF binario (.glb) tal como la necesita un render plano por software: vértices ya en el
/// espacio de la escena (con las transformaciones de los nodos aplicadas) y triángulos con el color base de su
/// material y la pieza (primitiva) a la que pertenecen. Lee POSITION, índices, la jerarquía de nodos y
/// <c>pbrMetallicRoughness.baseColorFactor</c>; no lee normales (se calculan por triángulo), texturas, pieles ni
/// animaciones. Basta para modelos pequeños de decoración como el lápiz de la pantalla de ingreso.
/// </summary>
public sealed class GlbMesh
{
    private const uint MagiaGltf = 0x46546C67;   // "glTF"
    private const uint ChunkJson = 0x4E4F534A;   // "JSON"
    private const uint ChunkBin = 0x004E4942;    // "BIN\0"

    private GlbMesh(Vector3[] vertices, Triangulo[] triangulos, int piezas)
    {
        Vertices = vertices;
        Triangulos = triangulos;
        Piezas = piezas;
        var minimo = new Vector3(float.MaxValue);
        var maximo = new Vector3(float.MinValue);
        foreach (var v in vertices)
        {
            minimo = Vector3.Min(minimo, v);
            maximo = Vector3.Max(maximo, v);
        }
        Minimo = vertices.Length > 0 ? minimo : Vector3.Zero;
        Maximo = vertices.Length > 0 ? maximo : Vector3.Zero;
    }

    /// <summary>Un triángulo: tres índices en <see cref="Vertices"/>, color base lineal (0–1), pieza y si se ve por las dos caras.</summary>
    public readonly record struct Triangulo(int A, int B, int C, Vector3 Color, int Pieza, bool DobleCara);

    public Vector3[] Vertices { get; }
    public Triangulo[] Triangulos { get; }
    public int Piezas { get; }
    public Vector3 Minimo { get; }
    public Vector3 Maximo { get; }

    public static GlbMesh Leer(Stream flujo)
    {
        using var memoria = new MemoryStream();
        flujo.CopyTo(memoria);
        return Leer(memoria.ToArray());
    }

    public static GlbMesh Leer(byte[] datos)
    {
        if (datos.Length < 12 || BitConverter.ToUInt32(datos, 0) != MagiaGltf || BitConverter.ToUInt32(datos, 4) != 2)
            throw new InvalidDataException("No es un glTF binario (versión 2).");
        var largo = Math.Min((int)BitConverter.ToUInt32(datos, 8), datos.Length);
        ReadOnlyMemory<byte> json = default, bin = default;
        for (var pos = 12; pos + 8 <= largo;)
        {
            var tamano = (int)BitConverter.ToUInt32(datos, pos);
            var tipo = BitConverter.ToUInt32(datos, pos + 4);
            var cuerpo = new ReadOnlyMemory<byte>(datos, pos + 8, Math.Min(tamano, largo - pos - 8));
            if (tipo == ChunkJson) json = cuerpo;
            else if (tipo == ChunkBin) bin = cuerpo;
            pos += 8 + tamano;
        }
        if (json.IsEmpty) throw new InvalidDataException("El glb no trae el bloque JSON.");

        using var documento = JsonDocument.Parse(json);
        var raiz = documento.RootElement;
        var vertices = new List<Vector3>();
        var triangulos = new List<Triangulo>();
        var piezas = 0;

        var escena = raiz.TryGetProperty("scene", out var e) ? e.GetInt32() : 0;
        if (raiz.TryGetProperty("scenes", out var escenas) && escenas.GetArrayLength() > escena
            && escenas[escena].TryGetProperty("nodes", out var nodosRaiz))
        {
            foreach (var indice in nodosRaiz.EnumerateArray())
                RecorrerNodo(raiz, bin.Span, indice.GetInt32(), Matrix4x4.Identity, vertices, triangulos, ref piezas);
        }
        return new GlbMesh(vertices.ToArray(), triangulos.ToArray(), piezas);
    }

    private static void RecorrerNodo(JsonElement raiz, ReadOnlySpan<byte> bin, int indice, Matrix4x4 padre,
        List<Vector3> vertices, List<Triangulo> triangulos, ref int piezas)
    {
        var nodo = raiz.GetProperty("nodes")[indice];
        var mundo = MatrizLocal(nodo) * padre;
        if (nodo.TryGetProperty("mesh", out var malla))
            LeerMalla(raiz, bin, malla.GetInt32(), mundo, vertices, triangulos, ref piezas);
        if (nodo.TryGetProperty("children", out var hijos))
            foreach (var hijo in hijos.EnumerateArray())
                RecorrerNodo(raiz, bin, hijo.GetInt32(), mundo, vertices, triangulos, ref piezas);
    }

    /// <summary>Transformación del nodo: matriz column-major de glTF (que en System.Numerics es su traspuesta) o T·R·S.</summary>
    private static Matrix4x4 MatrizLocal(JsonElement nodo)
    {
        if (nodo.TryGetProperty("matrix", out var m))
        {
            var v = m.EnumerateArray().Select(x => x.GetSingle()).ToArray();
            return new Matrix4x4(v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11], v[12], v[13], v[14], v[15]);
        }
        var escala = nodo.TryGetProperty("scale", out var s) ? LeerVector3(s) : Vector3.One;
        var rotacion = nodo.TryGetProperty("rotation", out var r) ? LeerCuaternion(r) : Quaternion.Identity;
        var traslacion = nodo.TryGetProperty("translation", out var t) ? LeerVector3(t) : Vector3.Zero;
        return Matrix4x4.CreateScale(escala) * Matrix4x4.CreateFromQuaternion(rotacion) * Matrix4x4.CreateTranslation(traslacion);
    }

    private static void LeerMalla(JsonElement raiz, ReadOnlySpan<byte> bin, int indice, Matrix4x4 mundo,
        List<Vector3> vertices, List<Triangulo> triangulos, ref int piezas)
    {
        foreach (var primitiva in raiz.GetProperty("meshes")[indice].GetProperty("primitives").EnumerateArray())
        {
            if (primitiva.TryGetProperty("mode", out var modo) && modo.GetInt32() != 4) continue; // sólo TRIANGLES
            if (!primitiva.GetProperty("attributes").TryGetProperty("POSITION", out var posicion)) continue;

            var base_ = vertices.Count;
            foreach (var v in LeerVec3(raiz, bin, posicion.GetInt32()))
                vertices.Add(Vector3.Transform(v, mundo));
            var cuenta = vertices.Count - base_;

            var indices = primitiva.TryGetProperty("indices", out var acc) ? LeerIndices(raiz, bin, acc.GetInt32()) : Enumerable.Range(0, cuenta).ToArray();
            var (color, dobleCara) = LeerMaterial(raiz, primitiva);
            var pieza = piezas++;
            for (var i = 0; i + 2 < indices.Length; i += 3)
                triangulos.Add(new Triangulo(base_ + indices[i], base_ + indices[i + 1], base_ + indices[i + 2], color, pieza, dobleCara));
        }
    }

    private static (Vector3 Color, bool DobleCara) LeerMaterial(JsonElement raiz, JsonElement primitiva)
    {
        if (!primitiva.TryGetProperty("material", out var im) || !raiz.TryGetProperty("materials", out var materiales))
            return (Vector3.One, false);
        var material = materiales[im.GetInt32()];
        var color = Vector3.One;
        if (material.TryGetProperty("pbrMetallicRoughness", out var pbr) && pbr.TryGetProperty("baseColorFactor", out var factor))
            color = LeerVector3(factor);
        var dobleCara = material.TryGetProperty("doubleSided", out var ds) && ds.GetBoolean();
        return (color, dobleCara);
    }

    private static (int Inicio, int Paso, int Cuenta, int Tipo) Accesor(JsonElement raiz, int indice, int tamanoElemento)
    {
        var accesor = raiz.GetProperty("accessors")[indice];
        var vista = raiz.GetProperty("bufferViews")[accesor.GetProperty("bufferView").GetInt32()];
        var inicio = (vista.TryGetProperty("byteOffset", out var vo) ? vo.GetInt32() : 0)
                   + (accesor.TryGetProperty("byteOffset", out var ao) ? ao.GetInt32() : 0);
        var paso = vista.TryGetProperty("byteStride", out var bs) ? bs.GetInt32() : tamanoElemento;
        return (inicio, paso, accesor.GetProperty("count").GetInt32(), accesor.GetProperty("componentType").GetInt32());
    }

    private static Vector3[] LeerVec3(JsonElement raiz, ReadOnlySpan<byte> bin, int indice)
    {
        var (inicio, paso, cuenta, tipo) = Accesor(raiz, indice, 12);
        if (tipo != 5126) throw new InvalidDataException("POSITION debe ser float.");
        var resultado = new Vector3[cuenta];
        for (var i = 0; i < cuenta; i++)
        {
            var o = inicio + i * paso;
            resultado[i] = new Vector3(BitConverter.ToSingle(bin.Slice(o, 4)), BitConverter.ToSingle(bin.Slice(o + 4, 4)), BitConverter.ToSingle(bin.Slice(o + 8, 4)));
        }
        return resultado;
    }

    private static int[] LeerIndices(JsonElement raiz, ReadOnlySpan<byte> bin, int indice)
    {
        var tamano = raiz.GetProperty("accessors")[indice].GetProperty("componentType").GetInt32() switch { 5121 => 1, 5123 => 2, 5125 => 4, _ => throw new InvalidDataException("Tipo de índice no admitido.") };
        var (inicio, paso, cuenta, _) = Accesor(raiz, indice, tamano);
        var resultado = new int[cuenta];
        for (var i = 0; i < cuenta; i++)
        {
            var o = inicio + i * paso;
            resultado[i] = tamano switch { 1 => bin[o], 2 => BitConverter.ToUInt16(bin.Slice(o, 2)), _ => (int)BitConverter.ToUInt32(bin.Slice(o, 4)) };
        }
        return resultado;
    }

    private static Vector3 LeerVector3(JsonElement e) => new(e[0].GetSingle(), e[1].GetSingle(), e[2].GetSingle());

    private static Quaternion LeerCuaternion(JsonElement e) => new(e[0].GetSingle(), e[1].GetSingle(), e[2].GetSingle(), e[3].GetSingle());
}
