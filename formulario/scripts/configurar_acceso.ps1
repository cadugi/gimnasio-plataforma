$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$adminName=Read-Host 'Usuario administrador'
$securePassword=Read-Host 'Contraseña nueva (12 o más caracteres, letras y números)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $payload=@{username=$adminName;password=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)} | ConvertTo-Json -Compress
    $php=if($env:TF_PHP_BINARY){$env:TF_PHP_BINARY}else{'C:/Users/User/Documents/xampp/php/php.exe'}
    $payload | & $php (Join-Path $PSScriptRoot 'reset_admin.php')
} finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer);$payload=$null}
