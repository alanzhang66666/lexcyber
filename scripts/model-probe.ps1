param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
if (-not $OutFile) {
    $OutFile = Join-Path $PSScriptRoot "..\docs\model-probe-record.md"
}

if (-not $env:MODEL_PROVIDER -or $env:MODEL_PROVIDER -eq "stub") {
    throw "Set MODEL_PROVIDER to a real provider (not stub) and MODEL_API_KEY before recording a real call."
}
if (-not $env:MODEL_API_KEY) {
    throw "MODEL_API_KEY is required. The script will not write a stub result as a real call."
}

$body = @{
    query = "model probe"
    metadata = @{ taskType = "model.probe" }
} | ConvertTo-Json -Compress

$created = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/tasks" -ContentType "application/json" -Body $body
$taskId = $created.id
$status = $created.status
for ($i = 0; $i -lt 60; $i++) {
    $task = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tasks/$taskId"
    $status = $task.status
    if ($status -in @("completed", "failed", "timed_out", "rejected")) { break }
    Start-Sleep -Seconds 2
}

if ($status -ne "completed") {
    throw "model.probe ended with status=$status errorCode=$($task.errorCode) error=$($task.error)"
}

$result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tasks/$taskId/result"
$content = $result.content
if ($content.provider -eq "stub") {
    throw "Result provider is stub. This is not a real model call."
}

$recordedAt = [DateTime]::UtcNow.ToString("o")
$markdown = @"
# Model probe record

- recordedAt: $recordedAt
- taskId: $taskId
- resultId: $($result.resultId)
- provider: $($content.provider)
- model: $($content.model)
- latencyMs: $($content.latencyMs)
- schemaVersion: $($content.schemaVersion)

Do not store API keys in this file.
"@

Set-Content -Path $OutFile -Value $markdown -Encoding utf8
Write-Output "Wrote $OutFile"
