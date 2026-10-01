#if ANDROID
using Android.App;
using Android.App.Admin;
using Android.Content;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// El receptor de administración del dispositivo (kiosk.md §3.2): una clase casi vacía que Android exige para que la app pueda ser Device Owner y usar Lock Task.
///
/// El nombre del componente (<c>paquete/clase</c>) es lo que se pasa a <c>dpm set-device-owner</c> —ver <c>scripts\android\Provision-DeviceOwner.ps1</c>, que usa
/// <c>com.avacom.lms.student/com.avacom.lms.student.ExamDeviceAdminReceiver</c>—. Si el nombre de la clase y el del manifiesto difieren, el comando falla; por eso se fija
/// <c>Name</c> en vez de dejar que se genere un nombre automático. Activar «administrador del dispositivo» desde Ajustes NO basta: es un permiso mucho más débil;
/// hace falta <c>set-device-owner</c> (y un equipo recién restablecido, sin cuentas).
/// </summary>
[BroadcastReceiver(Name = ExamDeviceAdminReceiver.NombreCompleto, Permission = "android.permission.BIND_DEVICE_ADMIN", Exported = true)]
[IntentFilter(new[] { "android.app.action.DEVICE_ADMIN_ENABLED", "android.app.action.PROFILE_PROVISIONING_COMPLETE" })]
[MetaData("android.app.device_admin", Resource = "@xml/device_admin_receiver")]
public sealed class ExamDeviceAdminReceiver : DeviceAdminReceiver
{
    /// <summary>El nombre Java de la clase, el que lleva el manifiesto y el que espera <c>dpm set-device-owner</c>.</summary>
    public const string NombreCompleto = "com.avacom.lms.student.ExamDeviceAdminReceiver";
}
#endif
