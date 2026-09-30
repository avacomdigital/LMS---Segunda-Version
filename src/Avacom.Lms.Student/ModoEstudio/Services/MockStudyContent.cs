using System.Text.Json;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// El contenido de la lección de demostración («Área y volumen con lenguaje algebraico»): una presentación, una lectura, un laboratorio y
/// una práctica de ocho preguntas, con la misma forma que entrega el aula (<see cref="ObjetoAula"/>, <see cref="PreguntaAula"/>). Se arma
/// desde JSON para no repetir los constructores posicionales. La clave de las preguntas vive sólo aquí, en la demostración; el servicio
/// real jamás la recibe (la compara la biblioteca).
/// </summary>
internal static class MockStudyContent
{
    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    private static T Leer<T>(object anonimo) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(anonimo), Web)!;

    /// <summary>El «AVACOM Markdown» mínimo del aula: lo que va entre <c>**dobles asteriscos**</c> es negrita (un tramo por cada cambio).</summary>
    private static object[] Tramos(string texto) =>
        texto.Split("**").Select((t, i) => new { texto = t, negrita = i % 2 == 1, cursiva = false, matematica = false })
            .Where(x => x.texto.Length > 0).Cast<object>().ToArray();

    private static string Plano(string texto) => texto.Replace("**", string.Empty);

    private static object Titulo(string texto, int nivel = 1) =>
        new { tipo = "heading", componente = "titulo", texto, nivel, tramos = Tramos(texto) };

    private static object Texto(string texto, string? estilo = null) =>
        new { tipo = "text", componente = "texto", texto = Plano(texto), estilo, tramos = Tramos(texto) };

    private static object Lista(bool ordenada, params string[] items) =>
        new { tipo = "list", componente = "lista", ordenada, items, items_tramos = items.Select(Tramos).ToArray() };

    private static object Formula(string texto) => new { tipo = "formula", componente = "formula", texto, tramos = Tramos(texto) };

    private static object Unidad(string objeto, int indice, string titulo, params object[] bloques) =>
        new { unidad_ref = $"{objeto}-{indice}", indice, titulo, duracion_seg = 150, bloques };

    // ------------------------------------------------------------------------------ lo que se lee

    public static ObjetoAula Presentacion() => Leer<ObjetoAula>(new
    {
        objeto_ref = "obj-presentacion", tipo = "lecture", componente = "presentacion", titulo = "Del área al álgebra",
        fuera_de_alcance = false, modulo = "MOD-008", total_unidades = 3,
        laminas = new[]
        {
            Unidad("obj-presentacion", 1, "¿Qué es el área?",
                Titulo("El área mide una superficie"),
                Texto("El **área** es la cantidad de superficie que cubre una figura. Se mide en unidades cuadradas: cm², m²…", "definition"),
                Formula("A = base × altura")),
            Unidad("obj-presentacion", 2, "Áreas con letras",
                Titulo("Cuando no conocemos el número"),
                Texto("Si el lado de un cuadrado mide **x**, su área es x · x. Escribimos las medidas con letras para hablar de cualquier cuadrado."),
                Lista(false, "Cuadrado de lado x: A = x²", "Rectángulo de lados x y 3: A = 3x", "Triángulo de base x y altura 4: A = 2x")),
            Unidad("obj-presentacion", 3, "De la superficie al volumen",
                Titulo("Un paso más: el volumen"),
                Texto("El **volumen** mide cuánto espacio ocupa un cuerpo. Un prisma se calcula con el área de su base por su altura.", "highlight"),
                Formula("V = área de la base × altura")),
        },
    });

    public static ObjetoAula Lectura() => Leer<ObjetoAula>(new
    {
        objeto_ref = "obj-lectura", tipo = "explanation", componente = "lectura", titulo = "Volumen de sólidos", fuera_de_alcance = false,
        modulo = "MOD-008", total_unidades = 2,
        paginas = new[]
        {
            Unidad("obj-lectura", 1, "Volumen de prismas",
                Titulo("Prismas rectos"),
                Texto("Para un prisma recto, primero calcula el área de la base y luego multiplícala por la altura del prisma."),
                Lista(true, "Identifica la figura de la base.", "Calcula su área.", "Multiplica por la altura.")),
            Unidad("obj-lectura", 2, "Sólidos irregulares",
                Titulo("¿Y si no tiene una forma conocida?"),
                Texto("Un truco antiguo: sumergirlo en agua y medir cuánto sube el nivel. El agua que sube es el volumen del sólido.", "highlight")),
        },
    });

    public static ObjetoAula Laboratorio() => Leer<ObjetoAula>(new
    {
        objeto_ref = "obj-laboratorio", tipo = "simulation_lab", componente = "laboratorio_web", titulo = "Laboratorio de volúmenes",
        fuera_de_alcance = false, modulo = "MOD-008", objetivo_aprendizaje = "Comprobar cómo cambia el volumen al cambiar la altura.",
        instrucciones = "Mueve la altura del prisma y observa el volumen.",
    });

    // ------------------------------------------------------------------------------ la práctica

    private static object Opcion(string referencia, string texto) => new { opcion_ref = referencia, texto, tramos = Tramos(texto) };

    private static object Multiple(string referencia, string enunciado, params (string Ref, string Texto)[] opciones) => new
    {
        pregunta_ref = referencia, tipo = "multiple_choice", componente = "opcion_multiple", enunciado, enunciado_tramos = Tramos(enunciado),
        puntos = 1.0, permite_varias = false, opciones = opciones.Select(o => Opcion(o.Ref, o.Texto)).ToArray(),
    };

    private static object VerdaderoFalso(string referencia, string enunciado) => new
    {
        pregunta_ref = referencia, tipo = "true_false", componente = "verdadero_falso", enunciado, enunciado_tramos = Tramos(enunciado), puntos = 1.0,
        opciones = new[] { Opcion("true", "Verdadero"), Opcion("false", "Falso") },
    };

    public static ObjetoAula Practica() => Leer<ObjetoAula>(new
    {
        objeto_ref = "obj-practica", tipo = "activity", componente = "actividad", titulo = "Comprueba lo aprendido", fuera_de_alcance = false,
        modulo = "MOD-008", instrucciones = "Responde con calma. Puedes intentarlo las veces que quieras.",
        ajustes = new { retroalimentacion = "immediate", intentos_permitidos = (int?)null, barajar_preguntas = false, barajar_opciones = false },
        total_unidades = 8, puntos_totales = 8.0,
        preguntas = new object[]
        {
            Multiple("p1", "¿Cuál es el área de un cuadrado de lado x?", ("a", "2x"), ("b", "x²"), ("c", "4x")),
            Multiple("p2", "Un rectángulo mide x de base y 3 de altura. ¿Cuál es su área?", ("a", "3x"), ("b", "x + 3"), ("c", "x³")),
            VerdaderoFalso("p3", "El volumen mide la superficie que cubre una figura."),
            Multiple("p4", "¿Qué se multiplica para hallar el volumen de un prisma recto?", ("a", "El perímetro por la altura"), ("b", "El área de la base por la altura"), ("c", "Las tres aristas más pequeñas")),
            VerdaderoFalso("p5", "Si sumerges un sólido irregular, el agua que sube es su volumen."),
            new
            {
                pregunta_ref = "p6", tipo = "fill_blanks", componente = "completar", enunciado = "Completa la fórmula del área del triángulo.",
                enunciado_tramos = Tramos("Completa la fórmula del área del triángulo."), puntos = 1.0, plantilla = "A = (base × altura) ÷ {{1}}",
                espacios = new[] { new { espacio_ref = "1", modo_entrada = "text", opciones = Array.Empty<string>() } },
            },
            new
            {
                pregunta_ref = "p7", tipo = "ordering", componente = "ordenar", enunciado = "Ordena los pasos para hallar el volumen de un prisma.",
                enunciado_tramos = Tramos("Ordena los pasos para hallar el volumen de un prisma."), puntos = 1.0,
                elementos = new object[]
                {
                    new { @ref = "s2", texto = "Calcular el área de la base", tramos = Tramos("Calcular el área de la base") },
                    new { @ref = "s3", texto = "Multiplicar por la altura", tramos = Tramos("Multiplicar por la altura") },
                    new { @ref = "s1", texto = "Identificar la figura de la base", tramos = Tramos("Identificar la figura de la base") },
                },
            },
            Multiple("p8", "Un cubo de lado 2 cm tiene un volumen de…", ("a", "6 cm³"), ("b", "8 cm³"), ("c", "4 cm³")),
        },
    });

    /// <summary>La clave de la demostración: pregunta → función que dice si la respuesta (ya en la forma de <c>/v2/evaluate</c>) es correcta.</summary>
    public static bool EsCorrecta(string preguntaRef, JsonElement respuesta)
    {
        bool Igual(string clave, string esperado) =>
            respuesta.ValueKind == JsonValueKind.Object && respuesta.TryGetProperty(clave, out var v)
            && v.ValueKind == JsonValueKind.Array && v.GetArrayLength() == 1 && v[0].GetString() == esperado;

        switch (preguntaRef)
        {
            case "p1": return Igual("selectedOptionIds", "b");
            case "p2": return Igual("selectedOptionIds", "a");
            case "p4": return Igual("selectedOptionIds", "b");
            case "p8": return Igual("selectedOptionIds", "b");
            case "p3": return respuesta.TryGetProperty("value", out var v3) && v3.ValueKind == JsonValueKind.False;
            case "p5": return respuesta.TryGetProperty("value", out var v5) && v5.ValueKind == JsonValueKind.True;
            case "p6":
                return respuesta.TryGetProperty("blanks", out var huecos) && huecos.TryGetProperty("1", out var h) && h.GetString()?.Trim() == "2";
            case "p7":
                return respuesta.TryGetProperty("order", out var orden) && orden.ValueKind == JsonValueKind.Array
                    && orden.EnumerateArray().Select(e => e.GetString()).SequenceEqual(["s1", "s2", "s3"]);
            default: return false;
        }
    }

    public static string Retroalimentacion(string preguntaRef, bool correcta) => correcta
        ? preguntaRef switch
        {
            "p1" => "¡Correcto! El área del cuadrado es lado por lado: x · x = x².",
            "p7" => "¡Muy bien! Ese es el orden lógico de los pasos.",
            _ => "¡Correcto!",
        }
        : preguntaRef switch
        {
            "p1" => "Casi. Piensa en un cuadrado de lado 3: su área es 3 · 3.",
            "p3" => "No exactamente: la superficie que cubre una figura es su área; el volumen mide el espacio que ocupa.",
            "p6" => "Repasa la fórmula del triángulo: es la mitad del área del rectángulo.",
            "p7" => "Revisa el orden: primero se identifica la base, luego se calcula su área y al final se multiplica por la altura.",
            _ => "Todavía no. Vuelve a mirar la lección y tenlo otra vez.",
        };
}
