$ErrorActionPreference = "Stop"

$workspace = (Get-Location).Path
$port = 8765
$baseUrl = "http://127.0.0.1:$port"
$healthUrl = "$baseUrl/health"
$processOutput = [Environment]::GetEnvironmentVariable(
    "CITRUSCARE_MODEL_PROVIDER", "Process"
)
$modelOutput = [Environment]::GetEnvironmentVariable(
    "CITRUSCARE_MODEL", "Process"
)
$keyOutput = [Environment]::GetEnvironmentVariable("GROQ_API_KEY", "Process")

if ($processOutput -and $processOutput -ne "groq") {
    throw "CITRUSCARE_MODEL_PROVIDER is already set to a non-Groq provider."
}

$model = Read-Host "Enter the Groq model ID"
if ([string]::IsNullOrWhiteSpace($model)) {
    throw "A Groq model ID is required."
}

$secureKey = Read-Host "Enter the rotated Groq API key (input is hidden)" -AsSecureString
if ($null -eq $secureKey -or $secureKey.Length -eq 0) {
    throw "A Groq API key is required."
}

$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$apiKey = $null
$server = $null
$stdoutPath = Join-Path ([IO.Path]::GetTempPath()) "citruscare-groq-$PID.out"
$stderrPath = Join-Path ([IO.Path]::GetTempPath()) "citruscare-groq-$PID.err"

try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "A Groq API key is required."
    }

    $env:CITRUSCARE_MODEL_PROVIDER = "groq"
    $env:CITRUSCARE_MODEL = $model
    $env:GROQ_API_KEY = $apiKey

    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 `
        -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $port is already in use; no existing process was stopped."
    }

    $server = Start-Process -FilePath "python" `
        -ArgumentList @(
            "-m", "uvicorn", "citruscare.api.app:app",
            "--host", "127.0.0.1", "--port", "$port"
        ) `
        -WorkingDirectory $workspace `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($server.HasExited) {
            throw "FastAPI exited during startup; inspect its local startup error."
        }
        try {
            $null = Invoke-WebRequest -Uri $healthUrl `
                -Headers @{ Accept = "application/json" } `
                -TimeoutSec 2 -UseBasicParsing
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        throw "FastAPI did not become ready on port $port."
    }

    $healthResponse = Invoke-WebRequest -Uri $healthUrl `
        -Headers @{ Accept = "application/json" } `
        -TimeoutSec 10 -UseBasicParsing
    $providersResponse = Invoke-WebRequest -Uri "$baseUrl/v1/providers" `
        -TimeoutSec 10 -UseBasicParsing
    $modelsResponse = Invoke-WebRequest -Uri "$baseUrl/v1/models" `
        -TimeoutSec 10 -UseBasicParsing

    $health = $healthResponse.Content | ConvertFrom-Json
    $providers = $providersResponse.Content | ConvertFrom-Json
    $models = $modelsResponse.Content | ConvertFrom-Json
    if ($health.model_provider -ne "groq") {
        throw "Health endpoint does not report Groq as the active provider."
    }
    if (-not ($providers.providers | Where-Object { $_.name -eq "groq" })) {
        throw "Provider listing does not include Groq."
    }

    $query = "Explain hypertension in simple terms and identify the main clinical risk factors."
    $payload = @{ query = $query } | ConvertTo-Json -Compress
    $response = Invoke-WebRequest -Uri "$baseUrl/v1/intelligence/query" `
        -Method Post -ContentType "application/json" -Body $payload `
        -TimeoutSec 90 -UseBasicParsing
    $bodyText = $response.Content
    $body = $bodyText | ConvertFrom-Json

    $routes = $models.routes.PSObject.Properties.Value
    $configuredModel = ($routes | Where-Object { $_.provider -eq "groq" } |
        Select-Object -First 1).model
    $expectedModel = if ($configuredModel) { $configuredModel } else { $model }
    if ($body.provider -ne "groq" -or $body.model -ne $expectedModel) {
        throw "The query response did not identify the configured Groq provider and model."
    }
    if ([string]::IsNullOrWhiteSpace($body.request_id)) {
        throw "The query response has no request ID."
    }

    $responses = @(
        $healthResponse.Content,
        $providersResponse.Content,
        $modelsResponse.Content,
        $bodyText
    )
    foreach ($content in $responses) {
        if ($content.Contains($apiKey) -or $content -match "(?i)bearer\s+\S+") {
            throw "A response appears to contain credential material."
        }
    }

    Write-Output "REAL_GROQ_REQUEST=PASS"
    Write-Output "PROVIDER=$($body.provider)"
    Write-Output "MODEL=$($body.model)"
    Write-Output "HTTP_STATUS=$([int]$response.StatusCode)"
    Write-Output "REQUEST_ID=$($body.request_id)"
    Write-Output "LATENCY_MS=$($body.latency_ms)"
    Write-Output "SAFETY_METADATA_PRESENT=$($null -ne $body.safety_decision)"
    Write-Output "EVIDENCE_METADATA_PRESENT=$($null -ne $body.evidence)"
    Write-Output "TRACE_METADATA_PRESENT=$($null -ne $body.agent_trace)"
    Write-Output "RESPONSE_CREDENTIAL_SCAN=PASS"
    Write-Output "API_HEALTH_STATUS=$([int]$healthResponse.StatusCode)"
    Write-Output "API_PROVIDERS_STATUS=$([int]$providersResponse.StatusCode)"
    Write-Output "API_MODELS_STATUS=$([int]$modelsResponse.StatusCode)"
} catch {
    $statusCode = $null
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    if ($statusCode) {
        Write-Output "REAL_GROQ_REQUEST=FAIL"
        Write-Output "HTTP_STATUS=$statusCode"
        Write-Output "ERROR_CATEGORY=Provider or API rejected the request"
    } else {
        Write-Output "REAL_GROQ_REQUEST=BLOCKED"
        Write-Output "ERROR_CATEGORY=$($_.Exception.GetType().Name)"
    }
} finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id
        $server.WaitForExit(10000) | Out-Null
    }

    foreach ($logPath in @($stdoutPath, $stderrPath)) {
        if (Test-Path -LiteralPath $logPath) {
            $logText = [IO.File]::ReadAllText($logPath)
            if ($apiKey -and $logText.Contains($apiKey)) {
                Write-Output "SERVER_LOG_CREDENTIAL_SCAN=FAIL"
            }
            Remove-Item -LiteralPath $logPath -Force
        }
    }

    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $apiKey = $null
    Remove-Variable secureKey -ErrorAction SilentlyContinue

    if ($processOutput) {
        $env:CITRUSCARE_MODEL_PROVIDER = $processOutput
    } else {
        Remove-Item Env:CITRUSCARE_MODEL_PROVIDER -ErrorAction SilentlyContinue
    }
    if ($modelOutput) {
        $env:CITRUSCARE_MODEL = $modelOutput
    } else {
        Remove-Item Env:CITRUSCARE_MODEL -ErrorAction SilentlyContinue
    }
    if ($keyOutput) {
        $env:GROQ_API_KEY = $keyOutput
    } else {
        Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
    }
}
