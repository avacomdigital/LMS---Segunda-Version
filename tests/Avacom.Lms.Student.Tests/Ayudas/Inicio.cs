using System.Runtime.CompilerServices;

namespace Avacom.Lms.Student.Tests;

/// <summary>Antes de cualquier prueba: el registro de fallos va a una carpeta temporal, nunca al registro real de quien usa el equipo.</summary>
internal static class Inicio
{
    [ModuleInitializer]
    internal static void Preparar()
    {
        var carpeta = Path.Combine(Path.GetTempPath(), "avacom-student-tests", "fallos");
        Directory.CreateDirectory(carpeta);
        Environment.SetEnvironmentVariable("AVACOM_LMS_DIR_FALLOS", carpeta);
    }
}
