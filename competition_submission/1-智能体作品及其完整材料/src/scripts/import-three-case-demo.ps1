param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [string]$DocsDir = "",
    [string]$Checkpoint = "",
    [switch]$RegisterAccount,
    [switch]$AdoptLegacy,
    [switch]$AllowPlaceholder
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "import_three_case_demo.py"
$pyArgs = @($script, "--base-url", $BaseUrl)
if ($DocsDir) {
    $pyArgs += @("--docs-dir", $DocsDir)
}
if ($Checkpoint) {
    $pyArgs += @("--checkpoint", $Checkpoint)
}
if ($RegisterAccount) {
    $pyArgs += "--register-account"
}
if ($AdoptLegacy) {
    $pyArgs += "--adopt-legacy"
}
if ($AllowPlaceholder) {
    $pyArgs += "--allow-placeholder"
}
python @pyArgs
