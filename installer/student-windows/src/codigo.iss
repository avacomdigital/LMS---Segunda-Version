// Logica del asistente de AVACOM Student.
//
// Vive en su propio archivo para que build\PruebaAsistente.iss pueda ejecutarla tal cual, sin instalar
// nada, y comprobar que las ocho comprobaciones del equipo funcionan de verdad en un Windows real.
//
// Se incluye desde la seccion [Code]; aqui no va ninguna cabecera de seccion.


const
  NumeroChecks = 8;
  ClaveDesinstalar =
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#IdInstalacion}_is1';

var
  PaginaValidacion: TWizardPage;
  EtiquetaCheck: array[0..7] of TNewStaticText;
  ResumenValidacion: TNewStaticText;
  BotonRevalidar: TNewButton;
  BotonRutaRecomendada: TNewButton;
  ValidacionSuperada: Boolean;
  { La actualizacion aparta el programa anterior a <app>\Anterior mientras el nuevo se copia y se
    comprueba; si algo falla se vuelve a poner en su sitio. }
  VersionAnterior: String;
  HayProgramaApartado: Boolean;
  ActualizacionRevertida: Boolean;
  AvisoFinal: String;
  InstalacionIniciada: Boolean;

{ ------------------------------------------------------------------ Utiles }

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

function ProcesoActivo(const Imagen: String): Boolean;
var
  Salida: String;
begin
  Salida := EjecutarYLeer('tasklist /FI "IMAGENAME eq ' + Imagen + '" /NH');
  Result := Pos(LowerCase(Imagen), LowerCase(Salida)) > 0;
end;

{ El runtime de WebView2 (el de Edge) lo usan las lecciones para audio, video, PDF y laboratorios.
  Windows 11 lo trae; un Windows 10 limpio puede no traerlo. }
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

{ Otros productos de AVACOM en este equipo. Solo informativo: Student no los necesita ni los toca. }
function OpsMasterPresente: Boolean;
begin
  Result := DirExists(ExpandConstant('{autopf}\AVACOM\OPS Master'))
         or RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}_is1');
end;

function ContenidoPresente: Boolean;
begin
  Result := DirExists(ExpandConstant('{autopf}\AVACOM\Contenido'))
         or FileExists(ExpandConstant('{commonappdata}\AVACOM\content\link.json'));
end;

{ Cierra la aplicacion de Student, y solo esa: el asistente no toca procesos ajenos. Primero se le
  pide que cierre; si no lo hace, se fuerza. }
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

procedure DistribuirBotonesDeNavegacion(Ancho, Alto: Integer);
var
  Derecha, Hueco, Arriba: Integer;
begin
  { Los tres botones de navegacion crecen hacia la izquierda y hacia arriba para poder tocarlos con
    el dedo; se colocan desde el borde derecho, uno junto al otro, todos del mismo tamano. }
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

{ «Examinar...» se alinea con la caja de la ruta, a su derecha, y la caja cede el espacio. }
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

  { Los botones crecen hacia arriba; se le quita ese alto al area de las paginas para que no
    queden encima del contenido. }
  if Delta > 0 then
  begin
    WizardForm.Bevel.Top := WizardForm.Bevel.Top - Delta;
    WizardForm.OuterNotebook.Height := WizardForm.OuterNotebook.Height - Delta;
  end;

  DistribuirBotonesDeNavegacion(Ancho, Alto);

  WizardForm.RunList.Font.Size := 11;
  WizardForm.RunList.MinItemHeight := ScaleY(34);
  WizardForm.InfoBeforeMemo.Font.Size := 10;
  WizardForm.ReadyMemo.Font.Size := 10;

  { Una ruta escrita a mano es un riesgo en una tableta: la caja es de solo lectura y la carpeta se
    elige con Examinar o con el boton de al lado. }
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
  Bloqueo, Anterior: String;
  RequeridoMb: Integer;
begin
  Bloqueo := '';
  { Student publicado pesa unos 400 MB; una actualizacion guarda ademas la version anterior mientras
    la nueva se copia, por si hay que volver atras. }
  RequeridoMb := 1200;

  { 1. Version de Windows. La aplicacion lleva el Windows App SDK autocontenido, que pide
    Windows 10 version 1809 (compilacion 17763) o posterior. }
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
    Bloqueo := 'Este equipo tiene una versión de Windows demasiado antigua para AVACOM Student. ' +
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

  { 3. Espacio en disco }
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

  { 5. Instalacion previa }
  Anterior := VersionInstalada;
  if Anterior = '' then
    PonerCheck(4, True, True, 'Primera instalación de AVACOM Student en este equipo')
  else
    PonerCheck(4, True, False, 'Ya está instalada la versión ' + Anterior +
                               '; se actualizará y se conservan la dirección del aula y el trabajo pendiente');

  { 6. Aplicacion abierta: no bloquea; el asistente cierra solo la propia }
  if ProcesoActivo('{#EjecutableApp}') then
    PonerCheck(5, True, False, 'AVACOM Student está abierto; el asistente lo cerrará al instalar')
  else
    PonerCheck(5, True, True, 'Ninguna ventana de AVACOM Student está abierta');

  { 7. WebView2: no viaja en el instalador (lo pone Windows) }
  if WebView2Presente then
    PonerCheck(6, True, True, '.NET y el Windows App SDK van dentro del instalador; WebView2 presente (lecciones)')
  else
    PonerCheck(6, False, False, 'Falta el runtime de WebView2 de Microsoft: las lecciones con audio, video o PDF pueden cerrar la aplicación');

  { 8. Convivencia con otros productos de AVACOM (informativa) }
  if OpsMasterPresente then
    PonerCheck(7, True, True, 'AVACOM OPS Master está en este equipo: Student se instala aparte y no lo modifica')
  else if ContenidoPresente then
    PonerCheck(7, True, True, 'AVACOM Contenido está en este equipo: Student se instala aparte y no lo modifica')
  else
    PonerCheck(7, True, True, 'Equipo de estudiante: Student solo necesita llegar por la red a AVACOM OPS Master');

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
    'Antes de instalar nada, se revisa que este equipo pueda ejecutar AVACOM Student.');

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

{ ------------------------------------------------------------- Diagnostico }

{ Con /VOLCADO=<archivo> el asistente ejecuta sus comprobaciones, las escribe en ese archivo y NO
  instala nada. Sirve para que soporte sepa si un equipo esta listo sin tocarlo, y para que la
  compilacion pruebe esta logica en un Windows de verdad (build\PruebaAsistente.iss). Combinalo con
  /VERYSILENT para que no aparezca ninguna ventana. }
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

  SetArrayLength(Lineas, NumeroChecks + 4);
  Lineas[0] := 'Diagnostico de AVACOM Student ' + '{#VersionProducto}';
  Lineas[1] := 'Carpeta prevista: ' + WizardDirValue;
  for i := 0 to NumeroChecks - 1 do
    { El prefijo es ASCII a proposito: quien lea este archivo no deberia depender de acertar con la
      codificacion de una marca de verificacion. }
    Lineas[2 + i] := 'check: ' + EtiquetaCheck[i].Caption;
  Lineas[NumeroChecks + 2] := 'Version instalada: ' + VersionInstalada;
  Lineas[NumeroChecks + 3] := 'Resultado: ' + ResumenValidacion.Caption;

  SaveStringsToUTF8File(Archivo, Lineas, False);
end;

procedure InitializeWizard;
begin
  AjustarParaPantallaTactil;
  CrearBotonRutaRecomendada;
  CrearPaginaValidacion;

  if RutaVolcado <> '' then
    VolcarDiagnostico(RutaVolcado);
end;

{ ------------------------------------------------------ Pantalla final }

function LeerArchivo(const Ruta: String): String;
var
  Contenido: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(Ruta, Contenido) then
    Result := String(Contenido);
end;

procedure ComponerPantallaFinal;
begin
  if AvisoFinal <> '' then
  begin
    WizardForm.FinishedLabel.Font.Color := clMaroon;
    WizardForm.FinishedLabel.Caption := AvisoFinal;
  end
  else
    WizardForm.FinishedLabel.Caption :=
      'AVACOM Student quedó instalado en este equipo.' + #13#10 + #13#10 +
      'La primera vez que lo abras, escribe la dirección del aula que muestra AVACOM OPS Master ' +
      '(algo como http://192.168.0.55:8000). El equipo y la OPS deben estar en la misma red, y la OPS debe haber hecho su primer arranque.' + #13#10 + #13#10 +
      'Este equipo se registra solo en la OPS al conectarse. Si la lista de grupos sale vacía, el profesorado aún no creó grupos ni alumnos.' + #13#10 + #13#10 +
      'El icono quedó en el escritorio y en el menú Inicio.';
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (PaginaValidacion <> nil) and (CurPageID = PaginaValidacion.ID) then
    EjecutarValidaciones
  else
    WizardForm.NextButton.Enabled := True;

  { Si la comprobacion final no salio, o la actualizacion se revirtio, se dice en la propia pantalla
    final: dejar un producto instalado que no funciona sin explicacion es peor que cualquier mensaje. }
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
    Space + 'AVACOM Student (aplicación del estudiante)' + NewLine +
    Space + 'Lanzador, que le da a las lecciones un perfil de WebView2 propio de cada persona' + NewLine +
    NewLine +
    MemoDirInfo + NewLine + NewLine +
    'Configuración que hará el asistente, sin intervención:' + NewLine +
    Space + 'Permisos de la carpeta de WebView2 junto a la aplicación (la única que los usuarios pueden escribir)' + NewLine +
    Space + 'Icono de AVACOM Student en el escritorio y en el menú Inicio' + NewLine +
    NewLine +
    'No se instala ningún servicio, no se abre ningún puerto y no se cambia el firewall.' + NewLine;

  if VersionInstalada <> '' then
    Result := Result + NewLine + 'Actualización de la versión ' + VersionInstalada + ':' + NewLine +
      Space + 'Se conservan la dirección del aula y el trabajo del estudiante que aún no llegó a la OPS.' + NewLine +
      Space + 'Si algo falla, se vuelve a la versión anterior.' + NewLine;

  Result := Result + NewLine + 'No se modificará AVACOM OPS Master ni AVACOM Contenido.';
end;

{ -------------------------------------- Actualizar sin dejar restos ni a medias }

function MoverCarpeta(const Origen, Destino: String): Boolean;
var
  Codigo, Intento: Integer;
begin
  Result := False;
  { Tras cerrar la aplicacion, Windows tarda un instante en soltar los archivos. }
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

{ Aparta la version anterior (App y Lanzador) a <app>\Anterior. Asi la nueva se copia sobre carpetas
  vacias -nada de mezclar archivos de dos versiones- y, si falla, la anterior se puede volver a poner.
  Los datos del estudiante no se tocan: viven en el perfil de cada persona. Devuelve '' si todo bien. }
function ApartarProgramaAnterior: String;
var
  Raiz, Aparte: String;
  Nombres: array[0..1] of String;
  i, j: Integer;
begin
  Result := '';
  HayProgramaApartado := False;
  Raiz := ExpandConstant('{app}');
  Aparte := Raiz + '\Anterior';
  Nombres[0] := 'App';
  Nombres[1] := 'Lanzador';

  if not (DirExists(Raiz + '\App') or DirExists(Raiz + '\Lanzador')) then
  begin
    { Sin programa previo, pero puede haber restos de un intento fallido. }
    if DirExists(Aparte) then DelTree(Aparte, True, True, True);
    Exit;
  end;

  if DirExists(Aparte) then DelTree(Aparte, True, True, True);
  ForceDirectories(Aparte);

  for i := 0 to 1 do
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
                  'Cierra AVACOM Student, espera un momento y vuelve a intentarlo.';
        Exit;
      end;
    end;
  end;
  HayProgramaApartado := True;
end;

{ Deja el equipo con la version anterior funcionando. }
procedure RevertirActualizacion(const Motivo: String);
var
  Raiz, Aparte: String;
  Nombres: array[0..1] of String;
  i: Integer;
begin
  Raiz := ExpandConstant('{app}');
  Aparte := Raiz + '\Anterior';
  Nombres[0] := 'App';
  Nombres[1] := 'Lanzador';

  for i := 0 to 1 do
  begin
    if DirExists(Raiz + '\' + Nombres[i]) then
      DelTree(Raiz + '\' + Nombres[i], True, True, True);
    if DirExists(Aparte + '\' + Nombres[i]) then
      MoverCarpeta(Aparte + '\' + Nombres[i], Raiz + '\' + Nombres[i]);
  end;
  DelTree(Aparte, True, True, True);
  HayProgramaApartado := False;

  if VersionAnterior <> '' then
    RegWriteStringValue(HKEY_LOCAL_MACHINE, ClaveDesinstalar, 'DisplayVersion', VersionAnterior);

  ActualizacionRevertida := True;
  AvisoFinal := 'No se pudo actualizar: ' + Motivo + #13#10 + #13#10 +
                'Se volvió a la versión ' + VersionAnterior + '. AVACOM Student sigue funcionando como antes.';
end;

{ Antes de copiar archivos: cerrar la aplicacion propia y apartar la version anterior. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;
  ActualizacionRevertida := False;
  AvisoFinal := '';
  InstalacionIniciada := True;
  VersionAnterior := VersionInstalada;

  CerrarAplicacionPropia;
  Result := ApartarProgramaAnterior;
end;

{ Tras copiar: el lanzador comprueba que lo instalado puede abrirse (sin abrirlo). Una falla de las
  que bloquean (faltan archivos) con una version anterior apartada la devuelve; una falla sin version
  anterior se dice en la pantalla final. Los avisos (WebView2) no revierten nada. }
procedure ComprobarInstalacion;
var
  Salida, Detalle: String;
  Codigo: Integer;
  Lineas: TArrayOfString;
  i: Integer;
begin
  Salida := ExpandConstant('{tmp}\verificacion-student.txt');
  DeleteFile(Salida);
  if not Exec(ExpandConstant('{app}\Lanzador\{#EjecutableLanzador}'), 'verificar "' + Salida + '"', '',
              SW_HIDE, ewWaitUntilTerminated, Codigo) then
    Codigo := 1;

  Detalle := '';
  if LoadStringsFromFile(Salida, Lineas) then
    for i := 0 to GetArrayLength(Lineas) - 1 do
      if (Copy(Lineas[i], 1, 6) = 'falla:') or (Copy(Lineas[i], 1, 6) = 'aviso:') then
        Detalle := Detalle + Lineas[i] + #13#10;

  if Codigo = 1 then
  begin
    if HayProgramaApartado then
      RevertirActualizacion('la comprobación de lo instalado falló.' + #13#10 + Detalle)
    else
      AvisoFinal := 'AVACOM Student se copió, pero la comprobación final falló:' + #13#10 + #13#10 + Detalle + #13#10 +
                    'Vuelve a ejecutar el instalador. Si sigue igual, usa AVACOM-Verificar-Student.bat.';
  end;
  { Codigo 2 son solo avisos (p. ej. WebView2): la pantalla de comprobacion ya los mostro y quedan en el
    registro del lanzador; no revierten nada. }

  { Todo bien (o sin remedio): la copia anterior ya no hace falta. }
  if (not ActualizacionRevertida) and DirExists(ExpandConstant('{app}\Anterior')) then
    DelTree(ExpandConstant('{app}\Anterior'), True, True, True);
  HayProgramaApartado := False;
end;

{ La bitacora de Inno Setup (SetupLogging=yes) queda en %TEMP% de quien instala, donde nadie la
  busca. Una copia junto al registro del lanzador deja el detalle de cada instalacion a mano. }
procedure GuardarBitacoraDelInstalador;
var
  Origen, Carpeta: String;
begin
  if not InstalacionIniciada then Exit;
  Origen := ExpandConstant('{log}');
  if (Origen = '') or (not FileExists(Origen)) then Exit;
  Carpeta := ExpandConstant('{localappdata}\AVACOM\Student');
  if not ForceDirectories(Carpeta) then Exit;
  CopyFile(Origen, Carpeta + '\instalador-ultimo.log', False);
end;

{ Si la instalacion se interrumpe despues de apartar la version anterior (falla la copia, se acaba
  el disco, alguien cancela), Inno Setup deshace lo que instalo pero no sabe de <app>\Anterior:
  sin esto el equipo se quedaria sin programa. Aqui, si sigue apartada, se devuelve. }
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
    ComprobarInstalacion;
end;

{ ------------------------------------------------------------ Desinstalacion }

{ Cierra la aplicacion sola (solo la propia): pedirle a alguien que la cierre y vuelva a intentarlo
  es un paso mas en una pantalla tactil. }
function InitializeUninstall: Boolean;
begin
  Result := True;
  CerrarAplicacionPropia;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos, Perfil: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;

  { Datos de ESTA persona de Windows: la dirección del aula, la cola de respuestas que aun no llegaron
    a la OPS y el material de estudio descargado (MAUI los guarda por aplicacion en el perfil), mas
    el perfil de WebView2 del lanzador. Por defecto se CONSERVAN: puede haber respuestas del
    estudiante que todavia no llegaron al backend. %LOCALAPPDATA%\AVACOM\lms no se toca: es de OPS
    y de Student (registros). }
  Datos := ExpandConstant('{localappdata}\User Name\com.avacom.lms.student');
  Perfil := ExpandConstant('{localappdata}\AVACOM\Student');
  if (not DirExists(Datos)) and (not DirExists(Perfil)) then Exit;

  if MsgBox('¿Eliminar también los datos de AVACOM Student de esta cuenta de Windows?' + #13#10 +
            '(la dirección del aula, las respuestas que aún no se entregaron y el material de estudio descargado)' + #13#10#13#10 +
            'Si vas a reinstalar AVACOM Student, toca No para conservarlos.',
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
  begin
    if DirExists(Datos) then DelTree(Datos, True, True, True);
    if DirExists(Perfil) then DelTree(Perfil, True, True, True);
  end;
end;
