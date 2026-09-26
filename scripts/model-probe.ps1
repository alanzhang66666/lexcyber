param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [string]$OutFile = "",
    [string]$Username = $env:LEXCYBER_USERNAME,
    [string]$Password = $env:LEXCYBER_PASSWORD
)

$ErrorActionPreference = "Stop"
if (-not $OutFile) {
    $OutFile = Join-Path $PSScriptRoot "..\docs\archive\model-probe-record.md"
}

if (-not $env:MODEL_PROVIDER -or $env:MODEL_PROVIDER -eq "stub") {
    throw "Set MODEL_PROVIDER to a real provider (not stub) and MODEL_API_KEY before recording a real call."
}
if (-not $env:MODEL_API_KEY) {
    throw "MODEL_API_KEY is required. The script will not write a stub result as a real call."
}
if (-not $Username -or -not $Password) {
    throw "LEXCYBER_USERNAME and LEXCYBER_PASSWORD are required. Reserved tasks (model.probe) now require auth; set the env vars or pass -Username/-Password. Do not hardcode credentials."
}

$loginBody = @{
    username = $Username
    password = $Password
} | ConvertTo-Json -Compress

try {
    $session = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/auth/login" -ContentType "application/json" -Body $loginBody
} catch {
    throw "Login failed. Reserved tasks (model.probe) require a valid session. Check LEXCYBER_USERNAME / LEXCYBER_PASSWORD."
}
$token = $session.token
if (-not $token) {
    throw "Login did not return a token. Reserved tasks now require auth."
}
$authHeaders = @{ Authorization = "Bearer $token" }

$body = @{
    query = "model probe"
    metadata = @{ taskType = "model.probe" }
} | ConvertTo-Json -Compress

try {
    $created = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/tasks" -Headers $authHeaders -ContentType "application/json" -Body $body
} catch {
    throw "Failed to create model.probe. Reserved tasks require Authorization: Bearer after login."
}
$taskId = $created.id
$status = $created.status
$task = $created
for ($i = 0; $i -lt 60; $i++) {
    $task = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tasks/$taskId" -Headers $authHeaders
    $status = $task.status
    if ($status -in @("completed", "failed", "timed_out", "rejected")) { break }
    Start-Sleep -Seconds 2
}

if ($status -ne "completed") {
    throw "model.probe ended with status=$status errorCode=$($task.errorCode) error=$($task.error)"
}

$result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tasks/$taskId/result" -Headers $authHeaders
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
