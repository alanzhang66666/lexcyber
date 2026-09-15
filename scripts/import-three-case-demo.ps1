param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [string]$DocsDir = ""
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "import_three_case_demo.py"
$pyArgs = @($script, "--base-url", $BaseUrl)
if ($DocsDir) {
    $pyArgs += @("--docs-dir", $DocsDir)
}
python @pyArgs
