param(
    [string]$BaseUrl = "http://127.0.0.1:18080",
    [int]$Attempts = 30
)

for ($index = 1; $index -le $Attempts; $index++) {
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/healthz" -TimeoutSec 3
        if ($response.status -eq "ok") {
            Write-Output "LexCyber v0.3 is ready at $BaseUrl"
            exit 0
        }
    } catch {
        # Compose services may still be applying migrations; retry below.
    }
    Start-Sleep -Seconds 2
}

throw "LexCyber did not become ready within $($Attempts * 2) seconds"
