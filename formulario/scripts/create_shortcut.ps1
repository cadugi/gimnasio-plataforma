param([string]$ProjectDirectory='')
$ErrorActionPreference='Stop'
$projectRoot=if($ProjectDirectory){[IO.Path]::GetFullPath($ProjectDirectory)}else{Split-Path -Parent $PSScriptRoot}
$desktopPath=[Environment]::GetFolderPath('DesktopDirectory')
$pythonWindowless='C:\Users\User\CajaGimnasio-Pruebas\Runtime\pythonw.exe'
if(!(Test-Path -LiteralPath $pythonWindowless)){
    $pythonCommand=Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if(!$pythonCommand){throw 'Hace falta Python 3 con pythonw.exe para el acceso sin consola.'}
    $pythonWindowless=$pythonCommand.Source
}
$shortcutPath=Join-Path $desktopPath 'Top Fitness - Altas y contratos.lnk'
if(Test-Path -LiteralPath $shortcutPath){
    $existing=(New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    if($existing.Arguments -notlike ('*'+$projectRoot+'*')){throw 'Ya existe un acceso directo ajeno con ese nombre. No se ha sustituido.'}
}
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath=$pythonWindowless
$shortcut.Arguments='"'+(Join-Path $projectRoot 'scripts\open_demo.py')+'"'
$shortcut.WorkingDirectory=$projectRoot
$shortcut.Description='Abrir Top Fitness: altas, contratos y domiciliaciones. Inicia el servidor local cuando hace falta.'
$shortcut.WindowStyle=7
$chromeIcon='C:\Program Files\Google\Chrome\Application\chrome.exe'
if(Test-Path -LiteralPath $chromeIcon){$shortcut.IconLocation=$chromeIcon+',0'}
$shortcut.Save()
Write-Output $shortcutPath
