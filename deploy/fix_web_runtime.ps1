param(
    [string]$ComposeWeb = "lexcyber-v03-web-1"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$index = Join-Path "web\dist" "index.html"
if (-not (Test-Path $index)) {
    throw "web/dist/index.html missing; run: npm --prefix web run build"
}

docker cp "web\dist\." "${ComposeWeb}:/usr/share/nginx/html/"
docker exec $ComposeWeb nginx -s reload
if ($LASTEXITCODE -ne 0) {
    docker restart $ComposeWeb
}
Write-Host "web runtime patched"
