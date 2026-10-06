# Dibuja la cuadrícula de tercios sobre una captura (líneas rojas en 1/3 y 2/3, puntos azules en las intersecciones, líneas tenues en 1/6 y 5/6 de Y),
# que es como el usuario juzga la composición de las pantallas de tarjeta. Uso: powershell -File tercios.ps1 -Entrada a.png -Salida a-tercios.png
param([string]$Entrada, [string]$Salida)
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($Entrada)
$bmp = New-Object System.Drawing.Bitmap $img.Width, $img.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.DrawImage($img, 0, 0, $img.Width, $img.Height)
$w = $img.Width; $h = $img.Height
$rojo = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(230, 220, 30, 30)), 2
$tenue = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(110, 220, 30, 30)), 1
$azul = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(240, 20, 90, 230))
foreach ($i in 1, 2) {
    $x = [int]($w * $i / 3); $y = [int]($h * $i / 3)
    $g.DrawLine($rojo, $x, 0, $x, $h); $g.DrawLine($rojo, 0, $y, $w, $y)
}
foreach ($f in 1, 5) { $y = [int]($h * $f / 6); $g.DrawLine($tenue, 0, $y, $w, $y) }
foreach ($i in 1, 2) { foreach ($j in 1, 2) { $g.FillEllipse($azul, [int]($w * $i / 3) - 7, [int]($h * $j / 3) - 7, 14, 14) } }
$g.Dispose(); $img.Dispose()
$bmp.Save($Salida, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
Write-Output "TERCIOS $Salida"
