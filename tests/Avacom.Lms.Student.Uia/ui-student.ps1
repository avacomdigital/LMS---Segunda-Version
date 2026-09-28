# Manejo de AVACOM Student por UI Automation, sin ratón ni foco: lista controles, invoca botones por su
# nombre, escribe en entradas por ValuePattern y captura sólo la ventana con PrintWindow.
# Uso: powershell -File ui-student.ps1 -Pid 1234 -Accion list|invoke|set|shot|text -Nombre "..." -Valor "..." -Salida x.png
param(
    [int]$ProcId,
    [string]$Accion = "list",
    [string]$Nombre = "",
    [string]$Valor = "",
    [string]$Salida = "",
    [int]$Espera = 0
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Win { [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; } }
"@
if ($Espera -gt 0) { Start-Sleep -Milliseconds $Espera }
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcId)
$win = $null
for ($i = 0; $i -lt 10 -and $null -eq $win; $i++) {
    $win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
    if ($null -eq $win) { Start-Sleep -Milliseconds 500 }
}
if ($null -eq $win) { Write-Output "SIN VENTANA para pid $ProcId"; exit 1 }
$hwnd = [IntPtr]$win.Current.NativeWindowHandle

function Todos($raiz) {
    $c = [System.Windows.Automation.Condition]::TrueCondition
    return $raiz.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c)
}

switch ($Accion) {
    "list" {
        foreach ($e in Todos $win) {
            $t = $e.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
            if ($t -in @("Button","Edit","Text","CheckBox","Image","Hyperlink","Custom") -and ($e.Current.Name -ne "" -or $t -eq "Edit")) {
                Write-Output ("{0}`t{1}`t{2}" -f $t, $e.Current.Name, $e.Current.AutomationId)
            }
        }
    }
    "text" {
        foreach ($e in Todos $win) {
            if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Text" -and $e.Current.Name -ne "") { Write-Output $e.Current.Name }
        }
    }
    "invoke" {
        # La tarjeta de pendientes se reconstruye en cada sondeo (2 s): el elemento puede quedar obsoleto entre
        # buscarlo e invocarlo, así que se reintenta.
        $hecho = $false
        for ($intento = 0; $intento -lt 6 -and -not $hecho; $intento++) {
            $hallado = $null
            foreach ($e in Todos $win) {
                if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Button" -and $e.Current.Name.Trim() -like ("*" + $Nombre.Trim() + "*")) { $hallado = $e; break }
            }
            if ($null -ne $hallado) {
                try { $p = $hallado.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); $p.Invoke(); $hecho = $true }
                catch { Start-Sleep -Milliseconds 400 }
            } else { Start-Sleep -Milliseconds 700 }
        }
        if (-not $hecho) { Write-Output "NO HAY BOTON '$Nombre'"; exit 2 }
        Write-Output "INVOCADO '$Nombre'"
    }
    "set" {
        $hallado = $null
        foreach ($e in Todos $win) {
            if ($e.Current.ControlType.ProgrammaticName -eq "ControlType.Edit" -and ($Nombre -eq "" -or $e.Current.Name -like ("*" + $Nombre + "*") -or $e.Current.AutomationId -eq $Nombre)) { $hallado = $e; break }
        }
        if ($null -eq $hallado) { Write-Output "NO HAY ENTRADA '$Nombre'"; exit 2 }
        $p = $hallado.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $p.SetValue($Valor); Write-Output "ESCRITO '$Valor'"
    }
    "shot" {
        $r = New-Object Win+RECT
        [Win]::GetWindowRect($hwnd, [ref]$r) | Out-Null
        $w = $r.R - $r.L; $h = $r.B - $r.T
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $hdc = $g.GetHdc()
        [Win]::PrintWindow($hwnd, $hdc, 2) | Out-Null
        $g.ReleaseHdc($hdc); $g.Dispose()
        $bmp.Save($Salida, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
        Write-Output "CAPTURA $Salida ${w}x${h}"
    }
}
