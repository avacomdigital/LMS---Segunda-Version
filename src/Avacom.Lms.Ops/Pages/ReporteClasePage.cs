using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Reporte de la clase (CAP-081): lo que hizo cada estudiante en una clase ya cerrada —cómo quedó su tableta, cuántas actividades entregó, su participación y sus aciertos— y, abajo, el
/// promedio de la clase. La cabecera del CORTE (BR-083) queda fija arriba junto con el encabezado de la tabla; sólo las filas se desplazan. Con el umbral de privacidad aplicado
/// (BR-086) no hay filas: sólo los totales, y la pantalla lo dice. Un estudiante sin nada entregado no tiene «0 %»: tiene «—».
/// </summary>
public sealed class ReporteClasePage : PaginaDeReporte
{
    private static readonly TablaDeReporte Tabla = new(
        new ColumnaDeTabla("Estudiante", GridLength.Star),
        new ColumnaDeTabla("Su tableta al cerrar", new GridLength(230)),
        new ColumnaDeTabla("Entregó", new GridLength(150), Derecha: true),
        new ColumnaDeTabla("Participación", new GridLength(200), Derecha: true),
        new ColumnaDeTabla("Aciertos", new GridLength(200), Derecha: true));

    public ReporteClasePage() : base("REPORTES · UNA CLASE", "Reporte de la clase", "Lo que hizo cada estudiante en esta clase.") { }

    protected override async Task LeerAsync(bool forzar)
    {
        if (Parametro("sesion") is not { } sesion)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Falta elegir la clase", "Vuelve a Reportes y elige una de las clases cerradas."));
            return;
        }
        var api = ReportesUi.Api;
        await LeerYPintarAsync(api, () => api.ClaseAsync(ReportesUi.Actor, sesion), Pintar, "No se pudo armar el reporte de la clase",
            e => e?.Codigo == "clase_en_curso" ? ("Esta clase aún no termina", EstadosVaciosDeReportes.ClaseEnCurso) : null);
    }

    private void Pintar(ReporteDeClase r)
    {
        var c = r.Clase;
        var grupo = c.Grupo is { } g ? g.Rotulo : "Sin grupo";
        var detalle = new List<string> { grupo, FormatoDeReportes.FechaLarga(c.FinalizadaEn), FormatoDeReportes.Duracion(c.DuracionMs), FormatoDeReportes.Plural(r.Totales.Participantes, "estudiante", "estudiantes"),
                                         FormatoDeReportes.Plural(r.Totales.Actividades, "actividad", "actividades"), FormatoDeReportes.Plural(c.Equipos, "tableta", "tabletas") };
        Poner("Reporte de la clase", $"{c.CursoRotulo} · {c.LeccionRotulo}\n{string.Join(" · ", detalle)}");
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeClase(c.SesionId));

        EncabezadoFijo(null);
        ContenidoHost.Clear();

        if (r.Privacidad.Aplicada)
        {
            // Sin filas identificables quedan sólo los totales, y la pantalla lo dice.
            var totales = ExamenUi.Fila();
            totales.Add(ReportesUi.Total("Estudiantes", r.Totales.Participantes.ToString(System.Globalization.CultureInfo.InvariantCulture), "participaron en la clase", 230));
            totales.Add(ReportesUi.Total("Actividades", r.Totales.Actividades.ToString(System.Globalization.CultureInfo.InvariantCulture), r.Totales.Actividades == 1 ? "se lanzó" : "se lanzaron", 230));
            totales.Add(ReportesUi.Total("Participación media", FormatoDeReportes.Porcentaje(r.Totales.PromedioParticipacion), null, 230));
            totales.Add(ReportesUi.Total("Aciertos medios", FormatoDeReportes.Porcentaje(r.Totales.PromedioAciertos), null, 230));
            ContenidoHost.Add(totales);
        }

        if (r.Privacidad.Aplicada)
        {
            ContenidoHost.Add(ReportesUi.Estado("Sólo se muestran los totales", "Los estudiantes no se listan uno por uno, para cuidar su privacidad. Lo mismo vale para el archivo que se exporte."));
        }
        else if (r.Filas.Count == 0)
        {
            ContenidoHost.Add(ReportesUi.Estado("No hubo estudiantes en esta clase", "Nadie se conectó, así que no hay nada que comparar. Elige otra clase en Reportes."));
        }
        else
        {
            if (r.Totales.Actividades == 0) ContenidoHost.Add(ExamenUi.Aviso(EstadosVaciosDeReportes.SinActividades, null, Tono.Info));
            // El encabezado va FIJO, fuera de lo que se desplaza; las filas y el promedio de la clase, abajo, sí se desplazan.
            EncabezadoFijo(Tabla.Encabezado());
            var filas = new List<View>();
            for (var i = 0; i < r.Filas.Count; i++) filas.Add(Fila(r.Filas[i], i));
            filas.Add(Tabla.Fila(["Promedio de la clase", string.Empty, string.Empty, ReportesUi.CeldaDePorcentaje(r.Totales.PromedioParticipacion, Ds.Info), ReportesUi.CeldaDePorcentaje(r.Totales.PromedioAciertos, Ds.Exito)],
                cebra: false, pie: true));
            ContenidoHost.Add(Tabla.Cuerpo(filas));
        }
        ContenidoHost.Add(ReportesUi.ObjetivosNoDisponibles(r.Objetivos));
    }

    private static View Fila(FilaDeClase f, int indice)
    {
        var entrego = new VerticalStackLayout { Spacing = 0, VerticalOptions = LayoutOptions.Center };
        entrego.Add(ReportesUi.Celda(f.ActividadesRecibidas == 0 ? "—" : FormatoDeReportes.DeTotal(f.ActividadesEntregadas, f.ActividadesRecibidas), derecha: true));
        if (f.EntregasPorCola > 0)
            entrego.Add(new Label { Text = f.EntregasPorCola == 1 ? "1 llegó al reconectar" : $"{f.EntregasPorCola} llegaron al reconectar", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, HorizontalTextAlignment = TextAlignment.End });
        return Tabla.Fila([
            ReportesUi.Celda(f.Alumno, medio: true),
            ReportesUi.ConPunto(FormatoDeReportes.Presencia(f.Estado), ReportesUi.ColorDePresencia(f.Estado)),
            entrego,
            ReportesUi.CeldaDePorcentaje(f.PorcentajeParticipacion, Ds.Info),
            ReportesUi.CeldaDePorcentaje(f.PorcentajeAciertos, Ds.Exito),
        ], cebra: indice % 2 == 1);
    }
}
