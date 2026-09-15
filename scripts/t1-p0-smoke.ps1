param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
if (-not $OutFile) {
    $OutFile = Join-Path $PSScriptRoot "..\.t1-smoke-responses.md"
}

$script:Lines = New-Object System.Collections.Generic.List[string]
function Add-Section([string]$Title, [string]$Status, $Body) {
    $json = if ($null -eq $Body) { "" } elseif ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 12 }
    $script:Lines.Add("## $Title")
    $script:Lines.Add("")
    $script:Lines.Add("status: $Status")
    $script:Lines.Add("")
    if ($json) {
        $script:Lines.Add('```json')
        $script:Lines.Add($json)
        $script:Lines.Add('```')
        $script:Lines.Add("")
    }
}

function Invoke-Json {
    param(
        [string]$Method,
        [string]$Path,
        [hashtable]$Headers = @{},
        $Body,
        [string]$ContentType = "application/json"
    )
    $uri = "$BaseUrl$Path"
    $params = @{ Method = $Method; Uri = $uri; Headers = $Headers }
    if ($null -ne $Body) {
        $params.ContentType = $ContentType
        $params.Body = $Body
    }
    try {
        $resp = Invoke-WebRequest @params
        return @{ Status = [int]$resp.StatusCode; Body = ($resp.Content | ConvertFrom-Json) }
    } catch {
        $ex = $_.Exception.Response
        if (-not $ex) { throw }
        $reader = New-Object System.IO.StreamReader($ex.GetResponseStream())
        $text = $reader.ReadToEnd()
        $parsed = $null
        try { $parsed = $text | ConvertFrom-Json } catch { $parsed = $text }
        return @{ Status = [int]$ex.StatusCode; Body = $parsed }
    }
}

$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "$BaseUrl/healthz" -TimeoutSec 3
        if ($health.status -eq "ok") { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw "service not ready at $BaseUrl" }

$suffix = Get-Random -Minimum 1000 -Maximum 9999
$userA = "t1smoke$suffix"
$userB = "t1smokeb$suffix"
$pass = "SmokePass123"

$regA = Invoke-Json -Method Post -Path "/v1/auth/register" -Body (@{ username = $userA; password = $pass; displayName = "T1 Smoke A" } | ConvertTo-Json)
if ($regA.Status -ne 201) { throw "register A failed $($regA.Status)" }
$tokenA = $regA.Body.token
$authA = @{ Authorization = "Bearer $tokenA" }
Add-Section "POST /v1/auth/register (A)" $regA.Status @{ username = $regA.Body.username; displayName = $regA.Body.displayName }

$regB = Invoke-Json -Method Post -Path "/v1/auth/register" -Body (@{ username = $userB; password = $pass; displayName = "T1 Smoke B" } | ConvertTo-Json)
$tokenB = $regB.Body.token
$authB = @{ Authorization = "Bearer $tokenB" }

$unauth = Invoke-Json -Method Post -Path "/v1/cases" -Body (@{ title = "no auth" } | ConvertTo-Json)
Add-Section "POST /v1/cases without bearer" $unauth.Status $unauth.Body
if ($unauth.Status -ne 401) { throw "expected 401 without bearer" }

$created = Invoke-Json -Method Post -Path "/v1/cases" -Headers $authA -Body (@{
    title = "测试案例 001"
    jurisdiction = "CN"
    asOfDate = "2026-09-06"
    metadata = @{
        datasetCaseId = "001"
        isDevelopmentSample = $true
        relations = @{ events = @(@{ eventId = "evt-smoke-001"; stage = "help"; documentId = "doc-pending-upload" }) }
    }
} | ConvertTo-Json)
Add-Section "POST /v1/cases" $created.Status $created.Body
if ($created.Status -ne 201) { throw "create case failed $($created.Status)" }
$caseId = $created.Body.id

$listed = Invoke-Json -Method Get -Path "/v1/cases?page=0&size=20" -Headers $authA
Add-Section "GET /v1/cases" $listed.Status $listed.Body

$got = Invoke-Json -Method Get -Path "/v1/cases/$caseId" -Headers $authA
Add-Section "GET /v1/cases/{caseId}" $got.Status $got.Body

$cross = Invoke-Json -Method Get -Path "/v1/cases/$caseId" -Headers $authB
Add-Section "GET /v1/cases/{caseId} cross-user" $cross.Status $cross.Body
if ($cross.Status -ne 404) { throw "expected 404 cross-user case" }

$docx = Join-Path $PSScriptRoot "..\.t1-smoke-input.docx"
if (-not (Test-Path $docx)) { throw "missing $docx" }

function Upload-Doc {
    param([string]$File, [string]$Role, [string]$Idem, [hashtable]$Headers)
    $uri = "$BaseUrl/v1/cases/$caseId/documents"
    $curl = @("curl.exe", "-s", "-D", "-", "-o", "-")
    # Use Invoke-RestMethod multipart
    $form = @{
        role = $Role
        file = Get-Item $File
    }
    $headerArgs = @{}
    foreach ($k in $Headers.Keys) { $headerArgs[$k] = $Headers[$k] }
    if ($Idem) { $headerArgs["Idempotency-Key"] = $Idem }
    try {
        $resp = Invoke-WebRequest -Method Post -Uri $uri -Headers $headerArgs -Form $form
        return @{ Status = [int]$resp.StatusCode; Body = ($resp.Content | ConvertFrom-Json) }
    } catch {
        $ex = $_.Exception.Response
        if (-not $ex) { throw }
        $reader = New-Object System.IO.StreamReader($ex.GetResponseStream())
        $text = $reader.ReadToEnd()
        $parsed = $null
        try { $parsed = $text | ConvertFrom-Json } catch { $parsed = $text }
        return @{ Status = [int]$ex.StatusCode; Body = $parsed }
    }
}

$upload = Upload-Doc -File $docx -Role "input" -Idem "upload-demo-$suffix" -Headers $authA
Add-Section "POST /v1/cases/{caseId}/documents input" $upload.Status $upload.Body
if ($upload.Status -ne 201) { throw "upload failed $($upload.Status)" }
$docId = $upload.Body.id
$parseTaskId = $upload.Body.parseTaskId
if (-not $parseTaskId) { throw "parseTaskId missing" }

$bound = Invoke-Json -Method Patch -Path "/v1/cases/$caseId/metadata/relations/events/evt-smoke-001/document" -Headers $authA -Body (@{
    documentId = $docId
    locator = "paragraph:1"
} | ConvertTo-Json)
Add-Section "PATCH event document binding" $bound.Status $bound.Body
if ($bound.Status -ne 200 -or $bound.Body.metadata.relations.events[0].documentId -ne $docId) {
    throw "event document binding failed"
}

$replay = Upload-Doc -File $docx -Role "input" -Idem "upload-demo-$suffix" -Headers $authA
Add-Section "POST upload idempotent replay" $replay.Status $replay.Body
if ($replay.Body.id -ne $docId) { throw "idempotent replay should return same document" }

$other = Join-Path $env:TEMP "t1-smoke-other.docx"
Copy-Item $docx $other
Add-Content -Path $other -Value "different" -Encoding Byte
$conflict = Upload-Doc -File $other -Role "input" -Idem "upload-demo-$suffix" -Headers $authA
Add-Section "POST upload idempotent conflict" $conflict.Status $conflict.Body
if ($conflict.Status -ne 409) { throw "expected 409 idempotency conflict" }

$txt = Join-Path $env:TEMP "t1-smoke-notes.txt"
Set-Content -Path $txt -Value "plain text" -Encoding utf8
$badType = Upload-Doc -File $txt -Role "input" -Idem $null -Headers $authA
Add-Section "POST upload unsupported type" $badType.Status $badType.Body
if ($badType.Status -ne 415) { throw "expected 415" }

$ann = Upload-Doc -File $docx -Role "annotation" -Idem "ann-$suffix" -Headers $authA
Add-Section "POST upload annotation" $ann.Status $ann.Body
if ($ann.Status -ne 201) { throw "annotation upload failed" }
if ($ann.Body.role -ne "annotation") { throw "annotation role not stored" }

$docs = Invoke-Json -Method Get -Path "/v1/cases/$caseId/documents?role=input&page=0&size=20" -Headers $authA
Add-Section "GET /v1/cases/{caseId}/documents?role=input" $docs.Status $docs.Body

$docGet = Invoke-Json -Method Get -Path "/v1/documents/$docId" -Headers $authA
Add-Section "GET /v1/documents/{documentId} refresh" $docGet.Status $docGet.Body

$hidden = Invoke-Json -Method Get -Path "/v1/documents/$docId" -Headers $authB
Add-Section "GET /v1/documents/{documentId} cross-user" $hidden.Status $hidden.Body
if ($hidden.Status -ne 404) { throw "expected 404 cross-user document" }

$task = $null
for ($i = 0; $i -lt 60; $i++) {
    $task = Invoke-Json -Method Get -Path "/v1/tasks/$parseTaskId" -Headers $authA
    if ($task.Body.status -in @("completed", "failed", "timed_out", "rejected")) { break }
    Start-Sleep -Seconds 2
}
Add-Section "GET /v1/tasks/{parseTaskId}" $task.Status $task.Body
if ($task.Body.status -ne "completed") { throw "parse did not complete: $($task.Body.status) $($task.Body.errorCode) $($task.Body.error)" }

$result = Invoke-Json -Method Get -Path "/v1/tasks/$parseTaskId/result" -Headers $authA
Add-Section "GET /v1/tasks/{id}/result" $result.Status $result.Body
if ($result.Body.content.schemaVersion -ne "document.parse.v1") { throw "unexpected schemaVersion" }

$taskCross = Invoke-Json -Method Get -Path "/v1/tasks/$parseTaskId" -Headers $authB
Add-Section "GET /v1/tasks/{id} cross-user" $taskCross.Status $taskCross.Body
if ($taskCross.Status -ne 404) { throw "expected 404 cross-user task" }

$broken = Join-Path $PSScriptRoot "..\.t1-smoke-broken.pdf"
if (Test-Path $broken) {
    $failUpload = Upload-Doc -File $broken -Role "input" -Idem "broken-$suffix" -Headers $authA
    $failTaskId = $failUpload.Body.parseTaskId
    $failTask = $null
    for ($i = 0; $i -lt 60; $i++) {
        $failTask = Invoke-Json -Method Get -Path "/v1/tasks/$failTaskId" -Headers $authA
        if ($failTask.Body.status -in @("completed", "failed", "timed_out", "rejected")) { break }
        Start-Sleep -Seconds 2
    }
    Add-Section "GET failed parse task" $failTask.Status $failTask.Body
    if ($failTask.Body.status -in @("failed", "timed_out")) {
        $retried = Invoke-Json -Method Post -Path "/v1/tasks/$failTaskId/retry" -Headers $authA
        Add-Section "POST /v1/tasks/{id}/retry" $retried.Status $retried.Body
    }
}

$script:Lines.Insert(0, "")
$script:Lines.Insert(0, "BaseUrl: $BaseUrl")
$script:Lines.Insert(0, "caseId: $caseId")
$script:Lines.Insert(0, "documentId: $docId")
$script:Lines.Insert(0, "parseTaskId: $parseTaskId")
$script:Lines.Insert(0, "# T1 P0 smoke responses")
$script:Lines | Set-Content -Path $OutFile -Encoding utf8
Write-Output "SMOKE_OK wrote $OutFile"
Write-Output "caseId=$caseId parseTaskId=$parseTaskId status=$($task.Body.status)"
