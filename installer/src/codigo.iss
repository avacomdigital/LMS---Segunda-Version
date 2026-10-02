// Logica del asistente de AVACOM OPS Master.
//
// Vive en su propio archivo para que build\PruebaAsistente.iss pueda
// ejecutarla tal cual, sin instalar nada, y comprobar que las diez
// comprobaciones del equipo funcionan de verdad en un Windows real.
//
// Se incluye desde la seccion [Code]; aqui no va ninguna cabecera de seccion.


const
  PuertoApi = {#PuertoBackend};
  NumeroChecks = 10;
  ClaveDesinstalar =
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}_is1';

var
  PaginaValidacion: TWizardPage;
  PaginaDatos: TInputOptionWizardPage;
  EtiquetaCheck: array[0..9] of TNewStaticText;
  ResumenValidacion: TNewStaticText;
  BotonRevalidar: TNewButton;
  BotonRutaRecomendada: TNewButton;
  ValidacionSuperada: Boolean;
  InstalacionIniciada: Boolean;
  AvisoConfiguracion: String;
  AvisoInformativo: String;
  { La actualizacion aparta el programa anterior a <app>\Anterior mientras la
    nueva se copia y se valida; si algo falla se vuelve a poner en su sitio. }
  VersionAnterior: String;
  HayProgramaApartado: Boolean;
  SeHizoRespaldo: Boolean;
  ActualizacionRevertida: Boolean;

{ ------------------------------------------------------------------ Utiles }

function PoliticaReemplazable: Boolean;
begin
  { La politica de datos es un dato de cada version (ver manifiesto.json), no
    logica cableada: Build-Installer.ps1 -PoliticaDatos la fija al compilar. }
  Result := CompareText('{#PoliticaDatos}', 'reemplazables') = 0;
end;

function CarpetaDeEstado: String;
begin
  Result := ExpandConstant('{commonappdata}\AVACOM\{#NombreCorto}');
end;

function HayDatosPrevios: Boolean;
begin
  Result := FileExists(CarpetaDeEstado + '\Data\ops-master.sqlite3')
         or FileExists(CarpetaDeEstado + '\Config\backend.env');
end;

function EjecutarYLeer(const Orden: String): String;
var
  Temporal: String;
  Codigo: Integer;
  Contenido: AnsiString;
begin
  Result := '';
  Temporal := ExpandConstant('{tmp}\avacom-salida.txt');
  if Exec(ExpandConstant('{cmd}'), '/C ' + Orden + ' > "' + Temporal + '" 2>&1',
          '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
  begin
    if LoadStringFromFile(Temporal, Contenido) then
      Result := String(Contenido);
    DeleteFile(Temporal);
  end;
end;

{ Devuelve la linea completa de netstat que escucha en el puerto, o ''.
  Se mira la columna de direccion local en lugar de la palabra LISTENING,
  porque netstat traduce esa palabra segun el idioma de Windows. }
function QuienEscuchaEnPuerto(Puerto: Integer): String;
var
  Salida: String;
  Lineas: TArrayOfString;
  Linea, Local, Sufijo: String;
  i, Corte: Integer;
begin
  Result := '';
  Sufijo := ':' + IntToStr(Puerto);
  Salida := EjecutarYLeer('netstat -ano -p tcp');
  if Salida = '' then Exit;

  Lineas := StringSplitEx(Salida, [#10], #0, stExcludeEmpty);
  for i := 0 to GetArrayLength(Lineas) - 1 do
  begin
    Linea := Trim(Lineas[i]);
    if Copy(Linea, 1, 4) <> 'TCP ' then Continue;

    { Tras "TCP" viene la direccion local, y despues el resto de columnas. }
    Linea := Trim(Copy(Linea, 5, Length(Linea)));
    Corte := Pos(' ', Linea);
    if Corte = 0 then Continue;

    Local := Copy(Linea, 1, Corte - 1);
    if Length(Local) < Length(Sufijo) then Continue;

    { Se compara el final de la direccion local: asi cuentan 0.0.0.0:8000 y
      127.0.0.1:8000, y no cuenta una conexion saliente hacia el :8000 de otro
      equipo, que aparece en la columna remota. }
    if Copy(Local, Length(Local) - Length(Sufijo) + 1, Length(Sufijo)) = Sufijo then
    begin
      Result := Trim(Lineas[i]);
      Exit;
    end;
  end;
end;

{ ¿Lo que contesta en el puerto es un backend de AVACOM OPS? Distinguirlo
  evita tratar una reinstalacion como un conflicto con otro programa. }
function RespondeNuestroBackend(Puerto: Integer): Boolean;
var
  Peticion: Variant;
  Estado: Integer;
  Cuerpo: String;
begin
  Result := False;
  try
    Peticion := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Peticion.SetTimeouts(2000, 2000, 2000, 4000);
    Peticion.Open('GET', 'http://127.0.0.1:' + IntToStr(Puerto) + '/health/', False);
    Peticion.Send('');
    { Las propiedades del objeto COM llegan como Variant: hay que convertirlas
      antes de pasarlas a Pos, que espera String. }
    Estado := Integer(Peticion.Status);
    Cuerpo := String(Peticion.ResponseText);
    Result := (Estado = 200) and (Pos('avacom-lms-backend', Cuerpo) > 0);
  except
    Result := False;
  end;
end;

function ProcesoActivo(const Imagen: String): Boolean;
var
  Salida: String;
begin
  Salida := EjecutarYLeer('tasklist /FI "IMAGENAME eq ' + Imagen + '" /NH');
  Result := Pos(LowerCase(Imagen), LowerCase(Salida)) > 0;
end;

function ServicioRegistrado(const Nombre: String): Boolean;
var
  Codigo: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\sc.exe'), 'query "' + Nombre + '"',
                 '', SW_HIDE, ewWaitUntilTerminated, Codigo) and (Codigo = 0);
end;

{ AVACOM Contenido (la biblioteca de cursos) publica su nota de enlace en
  %ProgramData%\AVACOM\content\link.json. La comprobacion es informativa: sin
  biblioteca el producto instala y arranca, pero el aula no tendra cursos. }
function ContenidoPresente: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonappdata}\AVACOM\content\link.json'))
         or DirExists(ExpandConstant('{autopf}\AVACOM\Contenido'));
end;

{ El runtime de WebView2 (el de Edge) lo usa la leccion para audio, video, PDF y
  laboratorios. Windows 11 lo trae; un Windows 10 limpio puede no traerlo. }
function WebView2Presente: Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function VersionInstalada: String;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, ClaveDesinstalar, 'DisplayVersion', Result) then
    Result := '';
end;

{ Cuantas de las redes conectadas Windows las clasifica como publicas. La
  regla de firewall de la API solo abre los perfiles privado y de dominio: en
  una red publica las tabletas no llegarian. -1 si no se pudo saber. }
function RedesPublicasConectadas: Integer;
var
  Salida: String;
begin
  Result := -1;
  Salida := Trim(EjecutarYLeer(
    'powershell -NoProfile -NonInteractive -Command "@(Get-NetConnectionProfile | ' +
    'Where-Object { $_.NetworkCategory -eq ''Public'' }).Count"'));
  if Salida <> '' then
    Result := StrToIntDef(Salida, -1);
end;

{ Cierra la aplicacion del profesor, y solo esa: el asistente no toca procesos
  ajenos. Primero se le pide que cierre; si no lo hace, se fuerza. }
procedure CerrarAplicacionPropia;
var
  Codigo, Intento: Integer;
begin
  if not ProcesoActivo('{#EjecutableApp}') then Exit;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#EjecutableApp}', '', SW_HIDE,
       ewWaitUntilTerminated, Codigo);
  for Intento := 1 to 8 do
  begin
    if not ProcesoActivo('{#EjecutableApp}') then Exit;
    Sleep(500);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#EjecutableApp}', '', SW_HIDE,
       ewWaitUntilTerminated, Codigo);
  Sleep(1000);
end;

{ ----------------------------------------------- Asistente para pantalla tactil }

procedure AgrandarBoton(Boton: TNewButton; AnchoNuevo, AltoNuevo: Integer);
begin
  if Boton = nil then Exit;
  { Se mantiene fijo el borde inferior derecho y el boton crece hacia
    arriba y hacia la izquierda: asi no se sale de la ventana. }
  Boton.Left := Boton.Left - (AnchoNuevo - Boton.Width);
  Boton.Top := Boton.Top - (AltoNuevo - Boton.Height);
  Boton.Width := AnchoNuevo;
  Boton.Height := AltoNuevo;
  Boton.Font.Size := 11;
end;

{ Los tres botones de navegacion crecen hacia la izquierda y hacia arriba para
  poder tocarlos con el dedo; si cada uno crece sobre su sitio, pisa al de su
  izquierda (Atras tapaba a Siguiente y este a Cancelar). Se colocan desde el
  borde derecho, uno junto al otro, todos del mismo tamano. }
procedure DistribuirBotonesDeNavegacion(Ancho, Alto: Integer);
var
  Derecha, Hueco, Arriba: Integer;
begin
  Hueco := ScaleX(10);
  Derecha := WizardForm.CancelButton.Left + WizardForm.CancelButton.Width;
  Arriba := WizardForm.CancelButton.Top - (Alto - WizardForm.CancelButton.Height);

  WizardForm.CancelButton.Width := Ancho;
  WizardForm.CancelButton.Height := Alto;
  WizardForm.CancelButton.Left := Derecha - Ancho;
  WizardForm.CancelButton.Top := Arriba;

  WizardForm.NextButton.Width := Ancho;
  WizardForm.NextButton.Height := Alto;
  WizardForm.NextButton.Left := WizardForm.CancelButton.Left - Hueco - Ancho;
  WizardForm.NextButton.Top := Arriba;

  WizardForm.BackButton.Width := Ancho;
  WizardForm.BackButton.Height := Alto;
  WizardForm.BackButton.Left := WizardForm.NextButton.Left - Hueco - Ancho;
  WizardForm.BackButton.Top := Arriba;

  WizardForm.NextButton.Font.Size := 11;
  WizardForm.BackButton.Font.Size := 11;
  WizardForm.CancelButton.Font.Size := 11;
end;

{ «Examinar...» crecia hacia la izquierda por debajo de la caja de la ruta y la
  tapaba. Se alinea con la caja, a su derecha, y la caja cede el espacio. }
procedure AjustarExaminar;
var
  Derecha: Integer;
begin
  Derecha := WizardForm.DirBrowseButton.Left + WizardForm.DirBrowseButton.Width;
  WizardForm.DirBrowseButton.Width := ScaleX(150);
  WizardForm.DirBrowseButton.Height := ScaleY(38);
  WizardForm.DirBrowseButton.Font.Size := 11;
  WizardForm.DirBrowseButton.Left := Derecha - WizardForm.DirBrowseButton.Width;
  WizardForm.DirBrowseButton.Top := WizardForm.DirEdit.Top - ((WizardForm.DirBrowseButton.Height - WizardForm.DirEdit.Height) div 2);
  WizardForm.DirEdit.Width := WizardForm.DirBrowseButton.Left - ScaleX(10) - WizardForm.DirEdit.Left;
end;

procedure AjustarParaPantallaTactil;
var
  Ancho, Alto, Delta: Integer;
begin
  Ancho := ScaleX(150);
  Alto := ScaleY(46);
  Delta := Alto - WizardForm.NextButton.Height;

  { Los botones crecen hacia arriba; se le quita ese alto al area de las
    paginas para que no queden encima del contenido. }
  if Delta > 0 then
  begin
    WizardForm.Bevel.Top := WizardForm.Bevel.Top - Delta;
    WizardForm.OuterNotebook.Height := WizardForm.OuterNotebook.Height - Delta;
  end;

  DistribuirBotonesDeNavegacion(Ancho, Alto);

  { Casillas y textos que hay que poder tocar sin precision de raton. }
  WizardForm.TasksList.Font.Size := 11;
  WizardForm.TasksList.MinItemHeight := ScaleY(34);
  WizardForm.RunList.Font.Size := 11;
  WizardForm.RunList.MinItemHeight := ScaleY(34);
  WizardForm.InfoBeforeMemo.Font.Size := 10;
  WizardForm.ReadyMemo.Font.Size := 10;

  { Sin teclado no se puede escribir una ruta: la caja se vuelve de solo
    lectura y la carpeta se elige con Examinar o con el boton de al lado. }
  WizardForm.DirEdit.ReadOnly := True;
  WizardForm.DirEdit.Font.Size := 11;
  WizardForm.DirEdit.Height := ScaleY(32);
  AjustarExaminar;
end;

procedure UsarRutaRecomendadaClick(Sender: TObject);
begin
  WizardForm.DirEdit.Text := ExpandConstant('{autopf}\AVACOM\{#NombreCorto}');
end;

procedure CrearBotonRutaRecomendada;
begin
  BotonRutaRecomendada := TNewButton.Create(WizardForm);
  BotonRutaRecomendada.Parent := WizardForm.SelectDirPage;
  BotonRutaRecomendada.Left := WizardForm.DirEdit.Left;
  BotonRutaRecomendada.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + ScaleY(14);
  BotonRutaRecomendada.Width := ScaleX(330);
  BotonRutaRecomendada.Height := ScaleY(42);
  BotonRutaRecomendada.Font.Size := 11;
  BotonRutaRecomendada.Caption := 'Usar la carpeta recomendada';
  BotonRutaRecomendada.OnClick := @UsarRutaRecomendadaClick;
end;

{ --------------------------------------------------- Pantalla de validaciones }

procedure PonerCheck(Indice: Integer; Correcto, Bloqueante: Boolean; const Texto: String);
begin
  if Correcto then
  begin
    EtiquetaCheck[Indice].Caption := '✓   ' + Texto;
    EtiquetaCheck[Indice].Font.Color := clGreen;
  end
  else if Bloqueante then
  begin
    EtiquetaCheck[Indice].Caption := '✗   ' + Texto;
    EtiquetaCheck[Indice].Font.Color := clRed;
  end
  else
  begin
    EtiquetaCheck[Indice].Caption := '⚠   ' + Texto;
    EtiquetaCheck[Indice].Font.Color := clOlive;
  end;
end;

procedure EjecutarValidaciones;
var
  Version: TWindowsVersion;
  Libres, Total: Int64;
  Bloqueo: String;
  Anterior, Ocupante: String;
  RequeridoMb, Publicas: Integer;
begin
  Bloqueo := '';
  RequeridoMb := 1500;

  { 1. Version de Windows. La aplicacion lleva el Windows App SDK autocontenido,
    que pide Windows 10 version 1809 (compilacion 17763) o posterior. }
  GetWindowsVersionEx(Version);
  if (Version.Major > 10) or ((Version.Major = 10) and (Version.Build >= 17763)) then
  begin
    if Version.Build >= 22000 then
      PonerCheck(0, True, True, 'Windows 11 (compilación ' + IntToStr(Version.Build) + ')')
    else
      PonerCheck(0, True, True, 'Windows 10 (compilación ' + IntToStr(Version.Build) + ')');
  end
  else
  begin
    PonerCheck(0, False, True, 'Se necesita Windows 10 versión 1809 (compilación 17763) o posterior');
    Bloqueo := 'Este equipo tiene una versión de Windows demasiado antigua para AVACOM OPS Master. ' +
               'Se necesita Windows 10 versión 1809 o posterior; actualiza Windows y vuelve a comprobar.';
  end;

  { 2. Arquitectura }
  if IsX64OS then
    PonerCheck(1, True, True, 'Procesador de 64 bits compatible')
  else
  begin
    PonerCheck(1, False, True, 'Se necesita Windows de 64 bits (x64)');
    if Bloqueo = '' then Bloqueo := 'La arquitectura de este equipo no es compatible.';
  end;

  { 3. Espacio en disco. Una actualizacion necesita sitio para la version
    nueva y para la anterior apartada, por si hay que volver atras. }
  if GetSpaceOnDisk64(ExtractFileDrive(WizardDirValue), Libres, Total) then
  begin
    if Libres >= Int64(RequeridoMb) * 1048576 then
      PonerCheck(2, True, True, 'Espacio disponible: ' + IntToStr(Libres div 1048576) + ' MB')
    else
    begin
      PonerCheck(2, False, True, 'Espacio insuficiente: hay ' + IntToStr(Libres div 1048576) +
                                 ' MB y se necesitan ' + IntToStr(RequeridoMb) + ' MB');
      if Bloqueo = '' then Bloqueo := 'Libera espacio en el disco y vuelve a comprobar.';
    end;
  end
  else
    PonerCheck(2, False, False, 'No se pudo medir el espacio libre del disco');

  { 4. Permisos }
  if IsAdmin then
    PonerCheck(3, True, True, 'Permisos de administrador concedidos')
  else
  begin
    PonerCheck(3, False, True, 'Se necesitan permisos de administrador');
    if Bloqueo = '' then Bloqueo := 'Vuelve a abrir la instalación como administrador.';
  end;

  { 5. Puerto de la API local (HTTP y tiempo real usan el mismo) }
  Ocupante := QuienEscuchaEnPuerto(PuertoApi);
  if Ocupante = '' then
    PonerCheck(4, True, True, 'Puerto ' + IntToStr(PuertoApi) + ' libre para la API local')
  else if RespondeNuestroBackend(PuertoApi) then
    PonerCheck(4, True, False, 'Puerto ' + IntToStr(PuertoApi) +
                               ' en uso por un backend de AVACOM OPS ya instalado; se detendrá y se reemplazará')
  else
  begin
    PonerCheck(4, False, True, 'Puerto ' + IntToStr(PuertoApi) + ' ocupado por otro programa');
    if Bloqueo = '' then
      Bloqueo := 'El puerto ' + IntToStr(PuertoApi) + ' lo está usando otra aplicación.' + #13#10#13#10 +
                 'AVACOM OPS Master necesita ese puerto para su API local.' + #13#10#13#10 +
                 'Cierra la aplicación que lo ocupa y toca «Volver a comprobar». ' +
                 'La instalación no va a detener programas ajenos por su cuenta.';
  end;

  { 6. Instalacion previa }
  Anterior := VersionInstalada;
  if Anterior = '' then
    PonerCheck(5, True, True, 'Primera instalación de AVACOM OPS Master en este equipo')
  else if PoliticaReemplazable then
    PonerCheck(5, True, False, 'Ya está instalada la versión ' + Anterior +
                               '; se actualizará y se hará una copia de seguridad de los datos')
  else
    PonerCheck(5, True, False, 'Ya está instalada la versión ' + Anterior +
                               '; se actualizará. Los datos están protegidos y se conservan siempre');

  { 7. Aplicacion abierta: ya no bloquea; el asistente cierra solo la propia }
  if ProcesoActivo('{#EjecutableApp}') then
    PonerCheck(6, True, False, 'AVACOM OPS Master está abierto; el asistente lo cerrará al instalar')
  else
    PonerCheck(6, True, True, 'Ninguna ventana de AVACOM OPS Master está abierta');

  { 8. Dependencias criticas: van dentro del paquete, no se instalan aparte }
  if FileExists(ExpandConstant('{sys}\sc.exe')) and FileExists(ExpandConstant('{sys}\netsh.exe')) then
  begin
    if WebView2Presente then
      PonerCheck(7, True, True, 'Python, .NET y la API van dentro del instalador; WebView2 presente (lecciones)')
    else
      PonerCheck(7, False, False, 'Falta el runtime de WebView2 de Microsoft: las lecciones con audio, video o PDF pueden cerrar la aplicación');
  end
  else
    PonerCheck(7, False, False, 'No se encontraron herramientas del sistema para registrar el servicio');

  { 9. Convivencia con AVACOM Contenido }
  if ContenidoPresente then
    PonerCheck(8, True, True, 'AVACOM Contenido detectado: se instalará junto a él sin modificarlo')
  else
    PonerCheck(8, False, False, 'AVACOM Contenido no está en este equipo; el aula no tendrá cursos hasta instalarlo');

  { 10. Red del aula. Informativa: la regla de firewall abre solo redes privadas }
  Publicas := RedesPublicasConectadas;
  if Publicas = 0 then
    PonerCheck(9, True, True, 'Las redes conectadas no son públicas: las tabletas podrán llegar')
  else if Publicas > 0 then
    PonerCheck(9, False, False, 'Windows clasifica una red conectada como pública; si las tabletas no llegan, cámbiala a privada')
  else
    PonerCheck(9, False, False, 'No se pudo comprobar si la red del aula es privada');

  ValidacionSuperada := (Bloqueo = '');
  if ValidacionSuperada then
  begin
    ResumenValidacion.Caption := 'Todo listo. Toca Siguiente para continuar.';
    ResumenValidacion.Font.Color := clGreen;
  end
  else
  begin
    ResumenValidacion.Caption := Bloqueo;
    ResumenValidacion.Font.Color := clRed;
  end;

  WizardForm.NextButton.Enabled := ValidacionSuperada;
end;

procedure RevalidarClick(Sender: TObject);
begin
  EjecutarValidaciones;
end;

procedure CrearPaginaValidacion;
var
  Titulo: TNewStaticText;
  i, y: Integer;
begin
  PaginaValidacion := CreateCustomPage(wpSelectDir,
    'Comprobación del equipo',
    'Antes de instalar nada, se revisa que este equipo pueda ejecutar AVACOM OPS Master.');

  Titulo := TNewStaticText.Create(PaginaValidacion);
  Titulo.Parent := PaginaValidacion.Surface;
  Titulo.Left := 0;
  Titulo.Top := 0;
  Titulo.Width := PaginaValidacion.SurfaceWidth;
  Titulo.AutoSize := False;
  Titulo.Height := ScaleY(20);
  Titulo.Font.Size := 10;
  Titulo.Caption := 'Resultado de la comprobación:';

  y := ScaleY(26);
  for i := 0 to NumeroChecks - 1 do
  begin
    EtiquetaCheck[i] := TNewStaticText.Create(PaginaValidacion);
    EtiquetaCheck[i].Parent := PaginaValidacion.Surface;
    EtiquetaCheck[i].Left := 0;
    EtiquetaCheck[i].Top := y;
    EtiquetaCheck[i].Width := PaginaValidacion.SurfaceWidth;
    EtiquetaCheck[i].AutoSize := False;
    EtiquetaCheck[i].Height := ScaleY(22);
    EtiquetaCheck[i].Font.Size := 10;
    EtiquetaCheck[i].Caption := '';
    y := y + ScaleY(24);
  end;

  ResumenValidacion := TNewStaticText.Create(PaginaValidacion);
  ResumenValidacion.Parent := PaginaValidacion.Surface;
  ResumenValidacion.Left := 0;
  ResumenValidacion.Top := y + ScaleY(10);
  ResumenValidacion.Width := PaginaValidacion.SurfaceWidth;
  ResumenValidacion.AutoSize := False;
  ResumenValidacion.Height := ScaleY(76);
  ResumenValidacion.WordWrap := True;
  ResumenValidacion.Font.Size := 10;
  ResumenValidacion.Font.Style := [fsBold];
  ResumenValidacion.Caption := '';

  BotonRevalidar := TNewButton.Create(PaginaValidacion);
  BotonRevalidar.Parent := PaginaValidacion.Surface;
  BotonRevalidar.Left := 0;
  BotonRevalidar.Top := PaginaValidacion.SurfaceHeight - ScaleY(44);
  ResumenValidacion.Height := BotonRevalidar.Top - ResumenValidacion.Top - ScaleY(6);
  BotonRevalidar.Width := ScaleX(240);
  BotonRevalidar.Height := ScaleY(44);
  BotonRevalidar.Font.Size := 11;
  BotonRevalidar.Caption := 'Volver a comprobar';
  BotonRevalidar.OnClick := @RevalidarClick;
end;

{ ------------------------------------------- Pantalla «Datos del aula» (tactil) }

{ Solo aparece si ya hay datos de una instalacion anterior Y la politica de esta
  version deja elegir (datos reemplazables). Cuando llegue el modulo de progreso
  y calificaciones y la politica pase a protegidos, la pantalla desaparece sola
  y los datos se conservan siempre. Son dos opciones grandes, sin escribir. }
procedure CrearPaginaDatos;
begin
  PaginaDatos := CreateInputOptionPage(PaginaValidacion.ID,
    'Datos del aula',
    'Este equipo ya guarda la organización, las personas, las tabletas y las clases del aula.',
    'Elige qué hacer con esos datos. Se hace una copia de seguridad antes de cualquier cambio.',
    True, False);
  { El alto minimo de cada opcion se fija ANTES de agregarlas: una vez agregadas ya
    no se recalcula, y las dos opciones quedaban apretadas, demasiado bajas para el dedo. }
  PaginaDatos.CheckListBox.Font.Size := 12;
  PaginaDatos.CheckListBox.MinItemHeight := ScaleY(64);
  PaginaDatos.Add('Conservar los datos (recomendado)');
  PaginaDatos.Add('Empezar de cero: hay que volver a crear la organización, importar el padrón y registrar las tabletas');
  PaginaDatos.SelectedValueIndex := 0;
end;

function EligioEmpezarDeCero: Boolean;
begin
  Result := (PaginaDatos <> nil) and PoliticaReemplazable and HayDatosPrevios
            and (PaginaDatos.SelectedValueIndex = 1);
end;

{ ------------------------------------------------------------- Diagnostico }

{ Con /VOLCADO=<archivo> el asistente ejecuta sus comprobaciones, las escribe
  en ese archivo y NO instala nada. Sirve para dos cosas:

    * que soporte pueda saber si un equipo del aula esta listo sin tocarlo;
    * que la compilacion pueda probar esta logica en un Windows de verdad
      (installer\build\PruebaAsistente.iss).

  Combinalo con /VERYSILENT para que no aparezca ninguna ventana. }
function RutaVolcado: String;
var
  i: Integer;
  Parametro: String;
begin
  Result := '';
  for i := 1 to ParamCount do
  begin
    Parametro := ParamStr(i);
    if CompareText(Copy(Parametro, 1, 9), '/VOLCADO=') = 0 then
    begin
      Result := Copy(Parametro, 10, Length(Parametro));
      Exit;
    end;
  end;
end;

procedure VolcarDiagnostico(const Archivo: String);
var
  Lineas: TArrayOfString;
  i: Integer;
begin
  EjecutarValidaciones;

  SetArrayLength(Lineas, NumeroChecks + 6);
  Lineas[0] := 'Diagnostico de AVACOM OPS Master ' + '{#VersionProducto}';
  Lineas[1] := 'Carpeta prevista: ' + WizardDirValue;
  for i := 0 to NumeroChecks - 1 do
    { El prefijo es ASCII a proposito: quien lea este archivo no deberia
      depender de acertar con la codificacion de una marca de verificacion. }
    Lineas[2 + i] := 'check: ' + EtiquetaCheck[i].Caption;
  Lineas[NumeroChecks + 2] := 'Politica de datos: {#PoliticaDatos}';
  Lineas[NumeroChecks + 3] := 'Version instalada: ' + VersionInstalada;
  if HayDatosPrevios then
    Lineas[NumeroChecks + 4] := 'Datos previos: si'
  else
    Lineas[NumeroChecks + 4] := 'Datos previos: no';
  Lineas[NumeroChecks + 5] := 'Resultado: ' + ResumenValidacion.Caption;

  SaveStringsToUTF8File(Archivo, Lineas, False);
end;

procedure InitializeWizard;
begin
  AjustarParaPantallaTactil;
  CrearBotonRutaRecomendada;
  CrearPaginaValidacion;
  CrearPaginaDatos;

  if RutaVolcado <> '' then
    VolcarDiagnostico(RutaVolcado);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PaginaDatos <> nil) and (PageID = PaginaDatos.ID) then
    Result := (not PoliticaReemplazable) or (not HayDatosPrevios);
end;

{ ------------------------------------------------------ Pantalla final (datos) }

function LeerArchivo(const Ruta: String): String;
var
  Contenido: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(Ruta, Contenido) then
    Result := Trim(String(Contenido));
end;

{ Lee la linea "clave=valor" del resumen que deja el host tras validar. Devuelve
  todas las coincidencias, una por linea, para "direccion". }
function ValoresDelResumen(const Resumen, Clave: String): String;
var
  Lineas: TArrayOfString;
  i: Integer;
  Prefijo: String;
begin
  Result := '';
  Prefijo := Clave + '=';
  Lineas := StringSplitEx(Resumen, [#10], #0, stExcludeEmpty);
  for i := 0 to GetArrayLength(Lineas) - 1 do
    if Copy(Trim(Lineas[i]), 1, Length(Prefijo)) = Prefijo then
    begin
      if Result <> '' then Result := Result + #13#10;
      Result := Result + Copy(Trim(Lineas[i]), Length(Prefijo) + 1, 500);
    end;
end;

{ Recorta un aviso largo para que la pantalla final no se desborde; el texto
  completo queda en los registros. }
function Recortado(const Texto: String; Maximo: Integer): String;
begin
  if Length(Texto) <= Maximo then
    Result := Texto
  else
    Result := Copy(Texto, 1, Maximo) + '… (el detalle está en los registros)';
end;

{ La pantalla final. De fabrica, su etiqueta mide lo que mide su texto corto: un
  texto mas largo (las direcciones para las tabletas, el estado de AVACOM
  Contenido, los avisos) se CORTA, y lo importante -la direccion que hay que
  escribir en las tabletas- no se ve. Aqui el contenido se reparte en tres
  bloques que se miden con su propia letra y se apilan: la cabecera, las
  direcciones en letra grande y las notas. La casilla de «Abrir ahora» baja con
  ellos y, si aun asi no cabe en la pagina, se baja la letra hasta que quepa. }
var
  EtiquetaDirecciones, EtiquetaNotas: TNewStaticText;

function NuevaEtiquetaFinal(Negrita: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(WizardForm);
  Result.Parent := WizardForm.FinishedPage;
  Result.Left := WizardForm.FinishedLabel.Left;
  Result.Width := WizardForm.FinishedLabel.Width;
  Result.AutoSize := False;
  Result.WordWrap := True;
  if Negrita then Result.Font.Style := [fsBold];
  Result.Caption := '';
end;

procedure Remedir(Etiqueta: TNewStaticText);
begin
  Etiqueta.AutoSize := False;
  Etiqueta.AutoSize := True;
end;

function DisponerPantallaFinal(const Cabecera, Direcciones, Notas: String; Minimo: Integer): Boolean;
var
  Tamano, Margen, Reservado, y: Integer;
begin
  if EtiquetaDirecciones = nil then EtiquetaDirecciones := NuevaEtiquetaFinal(True);
  if EtiquetaNotas = nil then EtiquetaNotas := NuevaEtiquetaFinal(False);

  WizardForm.FinishedLabel.WordWrap := True;
  WizardForm.FinishedLabel.Caption := Cabecera;
  EtiquetaDirecciones.Caption := Direcciones;
  EtiquetaNotas.Caption := Notas;
  EtiquetaDirecciones.Visible := Direcciones <> '';
  EtiquetaNotas.Visible := Notas <> '';

  Margen := ScaleY(10);
  Reservado := ScaleY(40);   { la casilla «Abrir ahora» y un respiro }
  Tamano := 11;
  repeat
    WizardForm.FinishedLabel.Font.Size := Tamano;
    EtiquetaNotas.Font.Size := Tamano;
    EtiquetaDirecciones.Font.Size := Tamano + 5;
    Remedir(WizardForm.FinishedLabel);
    Remedir(EtiquetaDirecciones);
    Remedir(EtiquetaNotas);

    y := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height;
    if Direcciones <> '' then
    begin
      EtiquetaDirecciones.Top := y + Margen div 2;
      y := EtiquetaDirecciones.Top + EtiquetaDirecciones.Height;
    end;
    if Notas <> '' then
    begin
      EtiquetaNotas.Top := y + Margen;
      y := EtiquetaNotas.Top + EtiquetaNotas.Height;
    end;
    Tamano := Tamano - 1;
  until (Tamano < Minimo) or (y + Margen + Reservado <= WizardForm.FinishedPage.ClientHeight);

  Result := (y + Margen + Reservado <= WizardForm.FinishedPage.ClientHeight);
  WizardForm.RunList.Top := y + Margen;
  WizardForm.RunList.Height := ScaleY(34);
end;

procedure ComponerPantallaFinal;
var
  Resumen, Direcciones, Organizacion, Registros, Biblioteca, Cursos, Cabecera, Notas: String;
begin
  Resumen := LeerArchivo(CarpetaDeEstado + '\Logs\resumen-nodo.txt');
  Direcciones := ValoresDelResumen(Resumen, 'direccion');
  Organizacion := ValoresDelResumen(Resumen, 'organizacion');
  Registros := ValoresDelResumen(Resumen, 'registros');
  Biblioteca := ValoresDelResumen(Resumen, 'biblioteca');
  Cursos := ValoresDelResumen(Resumen, 'biblioteca_cursos');

  if AvisoConfiguracion <> '' then
  begin
    if ActualizacionRevertida then
      Cabecera := AvisoConfiguracion
    else
      Cabecera := 'AVACOM OPS Master quedó instalado, pero la configuración de la API local no terminó:'
                  + #13#10 + #13#10 + AvisoConfiguracion
                  + #13#10 + #13#10 + 'El detalle está en la carpeta de registros del producto.';
    WizardForm.FinishedLabel.Font.Color := clMaroon;
    DisponerPantallaFinal(Cabecera, '', '', 8);
    Exit;
  end;

  Cabecera := 'AVACOM OPS Master quedó instalado y la API local responde. Arranca sola con Windows.';
  if Direcciones <> '' then
    Cabecera := Cabecera + #13#10 + #13#10 + 'En las tabletas de los estudiantes, escribe esta dirección del aula:'
  else
    Cabecera := Cabecera + #13#10 + #13#10 +
                'No se encontró una dirección de red para las tabletas. Conecta este equipo a la red del aula.';

  Notas := '';
  if Organizacion = 'no' then
    Notas := Notas + 'Falta crear la organización y el primer administrador. Ábrelos desde AVACOM OPS Master la primera vez.' + #13#10 + #13#10;

  { AVACOM Contenido es informativo: el aula funciona igual, solo que sin cursos
    hasta que la biblioteca este abierta. El instalador no la toca ni depende de ella. }
  if Biblioteca = 'conectada' then
  begin
    Notas := Notas + 'AVACOM Contenido conectado';
    if (Cursos <> '') and (Cursos <> '?') then
      Notas := Notas + ' (' + Cursos + ' cursos)';
    Notas := Notas + '.' + #13#10 + #13#10;
  end
  else if Biblioteca = 'no_disponible' then
    Notas := Notas + 'AVACOM Contenido no está abierto ahora: ábrelo para que el aula tenga cursos. ' +
             'Esta instalación no depende de él.' + #13#10 + #13#10;

  if Registros = 'sin_escritura' then
    Notas := Notas + 'Atención: el servicio no está guardando sus registros en la carpeta del nodo. ' +
             'Revisa los permisos de la carpeta Logs.' + #13#10 + #13#10;

  { Primero con los avisos de la configuracion (recortados); si asi la letra bajaria de 9,
    se dejan solo como un renglon que remite a los registros: lo importante es que se lea. }
  if AvisoInformativo = '' then
    DisponerPantallaFinal(Cabecera, Direcciones, Trim(Notas), 8)
  else if not DisponerPantallaFinal(Cabecera, Direcciones, Trim(Notas + Recortado(AvisoInformativo, 240)), 9) then
    DisponerPantallaFinal(Cabecera, Direcciones,
      Trim(Notas + 'Se corrigieron cosas de la configuración de este equipo: el detalle está en los registros del nodo.'), 8);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (PaginaValidacion <> nil) and (CurPageID = PaginaValidacion.ID) then
    EjecutarValidaciones
  else
    WizardForm.NextButton.Enabled := True;

  { Si la configuracion del backend no salio, o la actualizacion se revirtio,
    se dice en la propia pantalla final: dejar un producto instalado que no
    funciona sin explicacion es peor que cualquier mensaje. }
  if CurPageID = wpFinished then
    ComponerPantallaFinal;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (PaginaValidacion <> nil) and (CurPageID = PaginaValidacion.ID) then
    Result := ValidacionSuperada;
end;

function UpdateReadyMemo(const Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result :=
    'Se va a instalar en este equipo:' + NewLine +
    Space + 'AVACOM OPS Master (interfaz del profesor)' + NewLine +
    Space + 'AVACOM OPS Backend (API local del aula y tiempo real, puerto ' + IntToStr(PuertoApi) + ')' + NewLine +
    NewLine +
    MemoDirInfo + NewLine + NewLine +
    'Configuración que hará el asistente, sin intervención:' + NewLine +
    Space + 'Configuración local del nodo y base de datos' + NewLine +
    Space + 'Carpetas de datos, registros y auditoría con los permisos que el servicio necesita' + NewLine +
    Space + 'Servicio de Windows «{#NombreServicio}», con inicio automático' + NewLine +
    Space + 'Regla de Windows Defender Firewall para TCP ' + IntToStr(PuertoApi) +
            ' en redes privadas' + NewLine +
    Space + 'Icono de AVACOM OPS Master en el escritorio y en el menú Inicio' + NewLine +
    NewLine;

  if VersionInstalada <> '' then
  begin
    Result := Result + 'Actualización de la versión ' + VersionInstalada + ':' + NewLine;
    if EligioEmpezarDeCero then
      Result := Result + Space + 'Los datos actuales se guardan en una copia de seguridad y se empieza de cero.' + NewLine
    else if PoliticaReemplazable then
      Result := Result + Space + 'Se hace una copia de seguridad y se conservan los datos.' + NewLine
    else
      Result := Result + Space + 'Se hace una copia de seguridad y los datos se conservan siempre.' + NewLine;
    Result := Result + Space + 'Si algo falla, se vuelve a la versión anterior sin perder nada.' + NewLine + NewLine;
  end;

  Result := Result + 'No se modificará AVACOM Contenido ni ningún dato suyo.';
end;

{ -------------------------------------- Actualizar sin dejar restos ni a medias }

function EjecutarHostEn(const Carpeta, Parametros: String; Oculto: Boolean): Integer;
var
  Codigo: Integer;
  Modo: Integer;
begin
  if Oculto then Modo := SW_HIDE else Modo := SW_SHOWNORMAL;
  if not Exec(Carpeta + '\Runtime\{#EjecutableHost}', Parametros, '', Modo,
              ewWaitUntilTerminated, Codigo) then
    Codigo := -1;
  Result := Codigo;
end;

function EjecutarHost(const Parametros: String): Integer;
begin
  Result := EjecutarHostEn(ExpandConstant('{app}'), Parametros, True);
end;

function MoverCarpeta(const Origen, Destino: String): Boolean;
var
  Codigo, Intento: Integer;
begin
  Result := False;
  { Tras parar el servicio, Windows tarda un instante en soltar los archivos. }
  for Intento := 1 to 8 do
  begin
    Exec(ExpandConstant('{cmd}'), '/C move /Y "' + Origen + '" "' + Destino + '"', '',
         SW_HIDE, ewWaitUntilTerminated, Codigo);
    if (not DirExists(Origen)) and DirExists(Destino) then
    begin
      Result := True;
      Exit;
    end;
    Sleep(1500);
  end;
end;

procedure DetenerServicioPropio;
var
  Codigo: Integer;
begin
  if not ServicioRegistrado('{#NombreServicio}') then Exit;
  { El host detiene el servicio y ESPERA a que pare (el backend cierra el
    expediente antes de salir). Sin host, sc stop y una espera fija. }
  if FileExists(ExpandConstant('{app}\Runtime\{#EjecutableHost}')) then
    EjecutarHost('detener-servicio')
  else
  begin
    Exec(ExpandConstant('{sys}\sc.exe'), 'stop "{#NombreServicio}"', '', SW_HIDE,
         ewWaitUntilTerminated, Codigo);
    Sleep(8000);
  end;
end;

{ Aparta la version anterior (App, Backend, Runtime) a <app>\Anterior. Asi la
  nueva se copia sobre carpetas vacias -nada de mezclar runtimes, ni
  migraciones viejas, ni cachés- y, si falla, la anterior se puede volver a
  poner. Los datos no se tocan: viven en ProgramData. Devuelve '' si todo bien. }
function ApartarProgramaAnterior: String;
var
  Raiz, Aparte: String;
  Nombres: array[0..2] of String;
  i, j: Integer;
begin
  Result := '';
  HayProgramaApartado := False;
  Raiz := ExpandConstant('{app}');
  Aparte := Raiz + '\Anterior';
  Nombres[0] := 'App';
  Nombres[1] := 'Backend';
  Nombres[2] := 'Runtime';

  if not (DirExists(Raiz + '\App') or DirExists(Raiz + '\Backend') or DirExists(Raiz + '\Runtime')) then
  begin
    { Sin programa previo, pero puede haber restos de un intento fallido. }
    if DirExists(Aparte) then DelTree(Aparte, True, True, True);
    Exit;
  end;

  if DirExists(Aparte) then DelTree(Aparte, True, True, True);
  ForceDirectories(Aparte);

  for i := 0 to 2 do
  begin
    if DirExists(Raiz + '\' + Nombres[i]) then
    begin
      if not MoverCarpeta(Raiz + '\' + Nombres[i], Aparte + '\' + Nombres[i]) then
      begin
        { Se deshace lo ya apartado: la instalacion no puede quedar a medias. }
        for j := 0 to i - 1 do
          if DirExists(Aparte + '\' + Nombres[j]) then
            MoverCarpeta(Aparte + '\' + Nombres[j], Raiz + '\' + Nombres[j]);
        Result := 'No se pudo apartar la versión anterior (' + Nombres[i] + '): hay archivos en uso. ' +
                  'Cierra AVACOM OPS Master, espera un momento y vuelve a intentarlo.';
        Exit;
      end;
    end;
  end;
  HayProgramaApartado := True;
end;

{ Deja el equipo con la version anterior funcionando: datos restaurados desde
  la copia, programa devuelto a su sitio, servicio registrado de nuevo. }
procedure RevertirActualizacion(const Motivo: String);
var
  Raiz, Aparte: String;
  Nombres: array[0..2] of String;
  i, Codigo: Integer;
  Restaurado: Boolean;
begin
  Raiz := ExpandConstant('{app}');
  Aparte := Raiz + '\Anterior';
  Nombres[0] := 'App';
  Nombres[1] := 'Backend';
  Nombres[2] := 'Runtime';

  { 1. Parar lo nuevo (con el host nuevo, que todavia esta) y devolver los datos. }
  EjecutarHost('detener-servicio');
  Restaurado := True;
  if SeHizoRespaldo then
    Restaurado := (EjecutarHost('restaurar-datos') = 0);

  { 2. Retirar la version nueva y volver a poner la anterior. }
  for i := 0 to 2 do
  begin
    if DirExists(Raiz + '\' + Nombres[i]) then
      DelTree(Raiz + '\' + Nombres[i], True, True, True);
    if DirExists(Aparte + '\' + Nombres[i]) then
      MoverCarpeta(Aparte + '\' + Nombres[i], Raiz + '\' + Nombres[i]);
  end;
  DelTree(Aparte, True, True, True);

  { 3. Volver a registrar y arrancar la anterior con SU host: el servicio y la
    regla de firewall apuntan a un ejecutable que ha vuelto a su carpeta. }
  EjecutarHost('instalar-servicio');
  EjecutarHost('abrir-firewall');
  EjecutarHost('iniciar-servicio');
  Exec(ExpandConstant('{sys}\sc.exe'), 'query "{#NombreServicio}"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  if VersionAnterior <> '' then
    RegWriteStringValue(HKEY_LOCAL_MACHINE, ClaveDesinstalar, 'DisplayVersion', VersionAnterior);

  ActualizacionRevertida := True;
  AvisoConfiguracion := 'No se pudo actualizar: ' + Motivo + #13#10 + #13#10;
  if Restaurado then
    AvisoConfiguracion := AvisoConfiguracion +
      'Se volvió a la versión ' + VersionAnterior + ' y se restauraron sus datos. ' +
      'El aula sigue funcionando como antes.'
  else
    AvisoConfiguracion := AvisoConfiguracion +
      'Se volvió a la versión ' + VersionAnterior + ', pero no se pudieron restaurar los datos. ' +
      'La copia de seguridad está en la carpeta Respaldos de ' + CarpetaDeEstado + '.';
end;

{ Antes de copiar archivos: parar lo propio, cerrar la aplicacion propia y
  apartar la version anterior. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;
  ActualizacionRevertida := False;
  SeHizoRespaldo := False;
  AvisoConfiguracion := '';
  AvisoInformativo := '';

  { El modo diagnostico no instala: solo informa. }
  if RutaVolcado <> '' then
  begin
    Result := 'Modo diagnostico: las comprobaciones se escribieron en ' + RutaVolcado +
              ' y no se instalo nada.';
    Exit;
  end;

  InstalacionIniciada := True;
  VersionAnterior := VersionInstalada;

  DetenerServicioPropio;
  CerrarAplicacionPropia;
  Result := ApartarProgramaAnterior;
end;

{ Lo que el README del backend pide a mano, hecho aqui sin que nadie escriba un
  comando. En una actualizacion, ademas: copia de seguridad, y vuelta atras si
  algo falla entre preparar y validar. }
procedure ConfigurarBackend;
var
  Pagina: TOutputProgressWizardPage;
  Estado, Motivo: String;
  Codigo: Integer;
  Actualizando: Boolean;
begin
  AvisoConfiguracion := '';
  AvisoInformativo := '';
  Motivo := '';
  Actualizando := HayProgramaApartado;

  Pagina := CreateOutputProgressPage('Configuración del backend',
    'Se está preparando la API local de AVACOM OPS Master. No hace falta hacer nada.');
  Pagina.SetProgress(0, 100);
  Pagina.Show;
  try
    { --- Copia de seguridad de los datos (base + -wal + -shm + backend.env) --- }
    if HayDatosPrevios then
    begin
      Pagina.SetText('Guardando una copia de seguridad de los datos...', '');
      if EjecutarHost('respaldar ' + VersionAnterior) <> 0 then
      begin
        Motivo := 'no se pudo hacer la copia de seguridad de los datos.';
        if Actualizando then RevertirActualizacion(Motivo)
        else AvisoConfiguracion := 'No se pudo hacer la copia de seguridad de los datos.';
        Exit;
      end;
      SeHizoRespaldo := True;

      if EligioEmpezarDeCero then
      begin
        Pagina.SetText('Empezando de cero, como se pidió...', '');
        EjecutarHost('vaciar-datos');
      end;
    end;
    Pagina.SetProgress(15, 100);

    { --- Configuracion, claves y migraciones --- }
    Pagina.SetText('Creando la configuración de este equipo y preparando la base de datos...', '');
    Codigo := EjecutarHost('preparar');
    if Codigo <> 0 then
    begin
      Estado := LeerArchivo(CarpetaDeEstado + '\Logs\preparacion-estado.txt');
      if Estado = '' then
        Estado := 'La preparación del backend terminó con el código ' + IntToStr(Codigo) + '.';
      if Actualizando then RevertirActualizacion(Estado)
      else AvisoConfiguracion := Estado;
      Exit;
    end;
    AvisoInformativo := LeerArchivo(CarpetaDeEstado + '\Logs\preparacion-aviso.txt');
    Pagina.SetProgress(45, 100);

    { --- Servicio y firewall: el comando que ejecutan cambio (Daphne) --- }
    Pagina.SetText('Registrando el servicio de la API local...', '');
    if EjecutarHost('instalar-servicio') <> 0 then
    begin
      Motivo := 'no se pudo registrar el servicio {#NombreServicio}.';
      if Actualizando then RevertirActualizacion(Motivo)
      else AvisoConfiguracion := 'No se pudo registrar el servicio {#NombreServicio}.';
      Exit;
    end;
    Pagina.SetProgress(60, 100);

    Pagina.SetText('Autorizando el puerto ' + IntToStr(PuertoApi) +
                   ' para las tabletas del aula...', '');
    EjecutarHost('abrir-firewall');
    Pagina.SetProgress(70, 100);

    { --- Arrancar y validar: /health/ y el canal en tiempo real --- }
    Pagina.SetText('Iniciando la API local...', '');
    if EjecutarHost('iniciar-servicio') <> 0 then
    begin
      Motivo := 'el servicio {#NombreServicio} no arrancó.';
      if Actualizando then RevertirActualizacion(Motivo)
      else AvisoConfiguracion := 'El servicio {#NombreServicio} quedó instalado pero no arrancó. ' +
                                 'Se iniciará al reiniciar el equipo.';
      Exit;
    end;
    Pagina.SetProgress(80, 100);

    Pagina.SetText('Comprobando que la API local y el canal en tiempo real responden...', '');
    Codigo := EjecutarHost('validar 90');
    if Codigo <> 0 then
    begin
      if Codigo = 14 then
        Motivo := 'la API respondió, aunque el canal en tiempo real no acepta conexiones.'
      else if Codigo = 15 then
        Motivo := 'la API respondió, aunque no puede usar su base de datos (revisa los permisos de la carpeta Data).'
      else
        Motivo := 'la API local no respondió durante la instalación.';
      if Actualizando then RevertirActualizacion(Motivo)
      else AvisoConfiguracion := 'La instalación terminó, pero ' + Motivo + ' ' +
                                 'Revisa la carpeta de registros de AVACOM OPS Master.';
      Exit;
    end;
    Pagina.SetProgress(100, 100);

    { --- Todo bien: la version anterior ya no hace falta --- }
    if HayProgramaApartado then
      DelTree(ExpandConstant('{app}\Anterior'), True, True, True);
  finally
    Pagina.Hide;
  end;
end;

{ La bitacora de Inno Setup (SetupLogging=yes) queda en %TEMP% de quien instala,
  donde nadie la busca. Una copia en la carpeta de registros del nodo deja el
  detalle de cada instalacion junto a los demas registros (y el verificador la
  recoge). Se conservan la ultima y la anterior. Solo si la instalacion llego a
  empezar: abrir el asistente y cancelar no debe borrar el registro de la
  instalacion que si se hizo. }
procedure GuardarBitacoraDelInstalador;
var
  Origen, Carpeta, Ultima, Anterior: String;
begin
  if not InstalacionIniciada then Exit;
  Origen := ExpandConstant('{log}');
  if (Origen = '') or (not FileExists(Origen)) then Exit;
  Carpeta := CarpetaDeEstado + '\Logs';
  if not DirExists(Carpeta) then Exit;

  Ultima := Carpeta + '\instalador-ultimo.log';
  Anterior := Carpeta + '\instalador-anterior.log';
  if FileExists(Ultima) then
  begin
    DeleteFile(Anterior);
    RenameFile(Ultima, Anterior);
  end;
  CopyFile(Origen, Ultima, False);
end;

{ Si la instalacion se interrumpe despues de apartar la version anterior (falla
  la copia de archivos, se acaba el disco, alguien cancela), Inno Setup deshace
  lo que instalo pero no sabe de <app>\Anterior: sin esto el equipo se quedaria
  sin programa. Aqui, si la version anterior sigue apartada, se devuelve. }
procedure DeinitializeSetup;
begin
  if HayProgramaApartado then
    if DirExists(ExpandConstant('{app}\Anterior')) then
      RevertirActualizacion('la instalación se interrumpió antes de terminar.');
  GuardarBitacoraDelInstalador;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    ConfigurarBackend;
end;

{ ------------------------------------------------------------ Desinstalacion }

{ Cierra la aplicacion del profesor sola (solo la propia): pedirle a alguien que
  la cierre y vuelva a intentarlo es un paso mas en una pantalla sin teclado. }
function InitializeUninstall: Boolean;
begin
  Result := True;
  CerrarAplicacionPropia;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Estado: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;

  Estado := CarpetaDeEstado;
  if not DirExists(Estado) then Exit;

  { La base de datos y backend.env se conservan o se eliminan JUNTOS: sin las
    claves, las personas guardadas en la base no se pueden descifrar. La
    respuesta por defecto es conservar. %ProgramData%\AVACOM no se borra nunca:
    es de todos los productos de AVACOM. }
  if MsgBox('¿Eliminar también los datos de este equipo (organización, personas,' + #13#10 +
            'tabletas, clases, expediente) y su configuración?' + #13#10#13#10 +
            'Si vas a reinstalar AVACOM OPS Master, toca No para conservarlos.',
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    DelTree(Estado, True, True, True);
end;
