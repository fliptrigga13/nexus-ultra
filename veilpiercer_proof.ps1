
# 
#  VEILPIERCER  LIVE PROOF SCRIPT
#  Hits every component end-to-end. Expects 11/11 green.
# 

$BASE = "http://127.0.0.1:3000"
$AUTH = @{"x-api-key" = "Burton" }
$TOKEN = "386d770395a7b7bb7d700e00a9bdfb2badd94c00cdaaa790b941ea2e32369e83"  # Pro test token

$pass = 0; $fail = 0; $results = @()

function Check($num, $name, $ok, $detail = "") {
    if ($ok) {
        Write-Host "   [$num/11] $name" -ForegroundColor Green
        if ($detail) { Write-Host "          $detail" -ForegroundColor DarkGreen }
        $script:pass++
    }
    else {
        Write-Host "   [$num/11] $name" -ForegroundColor Red
        if ($detail) { Write-Host "          $detail" -ForegroundColor DarkRed }
        $script:fail++
    }
}

Write-Host ""
Write-Host "  " -ForegroundColor Cyan
Write-Host "     VEILPIERCER  LIVE PROOF SCRIPT        " -ForegroundColor Cyan
Write-Host "     11 Components  End-to-End             " -ForegroundColor Cyan
Write-Host "  " -ForegroundColor Cyan
Write-Host ""

#  [1] Server Health 
try {
    $s = Invoke-RestMethod "$BASE/status" -ErrorAction Stop
    Check 1 "Server Health" ($s.status -eq "NEXUS ULTRA ONLINE") "Status: $($s.status)"
}
catch {
    Check 1 "Server Health" $false "Error: $_"
}

#  [2] Admin Auth 
try {
    $a = Invoke-RestMethod "$BASE/access/list" -Headers $AUTH -ErrorAction Stop
    Check 2 "Admin Auth" ($a.count -gt 0) "Tokens in DB: $($a.count)"
}
catch {
    Check 2 "Admin Auth" $false "Error: $_"
}

#  [3] Token Creation 
try {
    $rnd = [System.Guid]::NewGuid().ToString("N").Substring(0, 8)
    $email = "proof_$rnd@test.veilpiercer.com"
    $body = @{ email = $email; tier = "Starter"; amount = 4700; sendEmail = $false } | ConvertTo-Json
    $cr = Invoke-RestMethod "$BASE/access/create" -Method POST -Headers $AUTH -Body $body -ContentType "application/json" -ErrorAction Stop
    $newTok = $cr.token
    $preview = if ($newTok.Length -gt 12) { $newTok.Substring(0, 12) } else { $newTok }
    Check 3 "Token Creation" ($cr.ok -eq $true -and $newTok.Length -gt 20) "New token for $email ($preview...)"
}
catch {
    Check 3 "Token Creation" $false "Error: $_"
    $newTok = $TOKEN
}

#  [4] Buyer Portal (Token Verify) 
try {
    $v = Invoke-RestMethod "$BASE/access/verify?token=$TOKEN" -ErrorAction Stop
    Check 4 "Buyer Portal  Token Verify" ($v.ok -eq $true) "Email: $($v.email) | Tier: $($v.tier)"
}
catch {
    Check 4 "Buyer Portal  Token Verify" $false "Error: $_"
}

#  [5] Command Hub Accessible 
try {
    $hub = Invoke-WebRequest "$BASE/veilpiercer-command.html" -UseBasicParsing -ErrorAction Stop
    $hasGate = $hub.Content -match 'verifyAndUnlock'
    $hasTiers = $hub.Content -match 'TIER_FEATURES'
    $hasOrbits = $hub.Content -match 'masterR'
    Check 5 "Command Hub" ($hub.StatusCode -eq 200 -and $hasGate -and $hasTiers) "Size: $([math]::Round($hub.Content.Length/1024,1))KB | Gate: $hasGate | Orbits: $hasOrbits"
}
catch {
    Check 5 "Command Hub" $false "Error: $_"
}

#  [6] Ollama AI Command (Pro tier) 
try {
    $body = @{
        token    = $TOKEN
        command  = "Run a quick visibility scan on all active nodes"
        protocol = "NOMINAL"
        scores   = @{ vis = 78.5; saf = 82.1; priv = 91.0 }
        useCase  = "proof test"
    } | ConvertTo-Json
    $ai = Invoke-RestMethod "$BASE/veilpiercer/command" -Method POST -Body $body -ContentType "application/json" -ErrorAction Stop -TimeoutSec 35
    $words = if ($ai.response) { ($ai.response -split '\s+').Count } else { 0 }
    $preview = if ($ai.response.Length -gt 0) { $ai.response.Substring(0, [Math]::Min(60, $ai.response.Length)) } else { '(empty)' }
    Check 6 "Ollama AI Command (Pro)" ($ai.ok -eq $true -and $ai.response.Length -gt 20) "Model: $($ai.model) | Response: $words words | Preview: $preview..."
}
catch {
    Check 6 "Ollama AI Command (Pro)" $false "Error: $_ (Is Ollama running? Run: ollama serve)"
}

#  [7] ZIP Download 
try {
    $tmpZip = "$env:TEMP\vp_test.zip"
    $dl = Invoke-WebRequest "$BASE/download?token=$TOKEN" -OutFile $tmpZip -ErrorAction Stop
    $isZip = (Get-Item $tmpZip).Length -gt 100
    $sizeKB = [math]::Round((Get-Item $tmpZip).Length / 1024, 1)
    Remove-Item $tmpZip
    Check 7 "ZIP Download" ($isZip) "Size: ${sizeKB}KB | Token: $($TOKEN.Substring(0,8))..."
}
catch {
    Check 7 "ZIP Download" $false "Error: $_"
}

#  [8] Feedback Submission 
try {
    $fb = Invoke-RestMethod "$BASE/feedback" -Method POST -ContentType "application/json" `
        -Body '{"token":"386d770395a7b7bb7d700e00a9bdfb2badd94c00cdaaa790b941ea2e32369e83","rating":"10","worked":"yes","recommend":"10","useCase":"proof script","suggestion":"ship it"}' `
        -ErrorAction Stop
    Check 8 "Feedback Submission" ($fb.ok -eq $true) "Response: $($fb.message)"
}
catch {
    Check 8 "Feedback Submission" $false "Error: $_"
}

#  [9] Feedback Insights (Admin View) 
try {
    $ins = Invoke-RestMethod "$BASE/feedback/all" -Headers $AUTH -ErrorAction Stop
    Check 9 "Feedback Insights Panel" ($ins.count -gt 0) "Responses: $($ins.count) | Avg Rating: $($ins.avgRating)/10 | Worked: $($ins.workedCount)"
}
catch {
    Check 9 "Feedback Insights Panel" $false "Error: $_"
}

#  [10] Signal / Access Flow 
try {
    $list = Invoke-RestMethod "$BASE/access/list" -Headers $AUTH -ErrorAction Stop
    $shortToken = $TOKEN.Substring(0, 8)
    $tok = $list.tokens | Where-Object { $_.token -like "$shortToken*" } | Select-Object -First 1
    $downloads = if ($tok.downloads -gt 0) { $tok.downloads } else { '0 (not yet tracked)' }
    $lastDl = if ($tok.lastDownload) { $tok.lastDownload } else { 'n/a' }
    Check 10 "Signal / Access Flow" ($tok -ne $null -and $tok.downloads -gt 0) "Downloads on this token: $downloads | Last: $lastDl"
}
catch {
    Check 10 "Signal / Access Flow" $false "Error: $_"
}

#  [11] Sales Page 
try {
    $sp = Invoke-WebRequest "$BASE/veilpiercer.html" -UseBasicParsing -ErrorAction Stop
    $hasStripe = $sp.Content -match 'buy\.stripe\.com'
    $hasBrand = $sp.Content -match 'VEILPIERCER'
    $sizeKB = [math]::Round($sp.Content.Length / 1024, 1)
    Check 11 "Sales Page" ($sp.StatusCode -eq 200 -and $hasStripe -and $hasBrand) "Size: ${sizeKB}KB | Stripe links: $hasStripe | Brand: $hasBrand"
}
catch {
    Check 11 "Sales Page" $false "Error: $_"
}

#  RESULTS 
Write-Host ""
if ($fail -eq 0) {
    Write-Host "   ALL $pass/11 CHECKS PASSED  VEILPIERCER IS LIVE" -ForegroundColor Cyan
}
else {
    Write-Host "   $pass PASSED  $fail FAILED" -ForegroundColor Yellow
    Write-Host "  Fix the red items above before going live." -ForegroundColor DarkYellow
}
Write-Host ""

