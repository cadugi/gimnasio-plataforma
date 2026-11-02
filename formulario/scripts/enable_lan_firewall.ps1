$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Haz clic derecho en Habilitar tablet Top Fitness.cmd y elige Ejecutar como administrador.'
    exit 1
}
$ruleName = 'TopFitness-Altas-LAN-8443'
$apache = Join-Path $env:USERPROFILE 'Documents\xampp\apache\bin\httpd.exe'
if (-not (Test-Path -LiteralPath $apache)) { throw 'No se encuentra el Apache configurado.' }
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Top Fitness - Altas HTTPS red local' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -LocalAddress 192.168.10.135,192.168.20.125 -RemoteAddress 192.168.10.0/24,192.168.20.0/24 -Program $apache -Profile Any | Out-Null
}
Write-Host 'Puerto 8443 habilitado solo para las redes locales del gimnasio.'
Write-Host 'Tablet en el mismo Wi-Fi: https://192.168.10.135:8443/'
Write-Host 'Instala y confia en el certificado local de Top Fitness en la tablet.'
