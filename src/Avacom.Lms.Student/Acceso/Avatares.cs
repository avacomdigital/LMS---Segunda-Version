namespace Avacom.Lms.Student.Acceso;

/// <summary>Un dibujo que el niño de preescolar toca en lugar de marcar un PIN (BR-024, TST-074). <see cref="Clave"/> es lo que viaja al nodo como secreto.</summary>
public sealed record Avatar(string Clave, string Nombre, string Dibujo, string Color);

/// <summary>
/// RF-28: los doce dibujos del acceso de preescolar. El nodo guarda el dibujo elegido como guarda un PIN (huella Argon2id) y sólo acepta un código de 3 a 32
/// caracteres en minúsculas (<c>Avatar</c> del dominio de acceso), así que cada dibujo viaja como una palabra sin tildes. El dibujo es un emoji: se pinta como
/// texto (sin geometría que Win2D tenga que recortar) y se ve igual en Windows y en Android.
/// </summary>
public static class Avatares
{
    public static IReadOnlyList<Avatar> Todos { get; } =
    [
        new("gato", "Gato", "\U0001F431", "#FDECEC"),
        new("perro", "Perro", "\U0001F436", "#FEF9E6"),
        new("leon", "León", "\U0001F981", "#FEF3D6"),
        new("pez", "Pez", "\U0001F41F", "#E6F6FC"),
        new("pajaro", "Pájaro", "\U0001F426", "#E6F5EE"),
        new("oso", "Oso", "\U0001F43B", "#F3ECE6"),
        new("conejo", "Conejo", "\U0001F430", "#F5E8F1"),
        new("tortuga", "Tortuga", "\U0001F422", "#E6F5EE"),
        new("mariposa", "Mariposa", "\U0001F98B", "#E6F6FC"),
        new("estrella", "Estrella", "⭐", "#FEF9E6"),
        new("sol", "Sol", "☀️", "#FEF3D6"),
        new("luna", "Luna", "\U0001F319", "#ECEBF7"),
    ];

    public static Avatar? Por(string? clave) => Todos.FirstOrDefault(a => string.Equals(a.Clave, clave, StringComparison.Ordinal));
}
