# trigger-n8n.ps1
$webhook = "http://localhost:5678/webhook-test/8c467412-7e02-4445-9d0e-09988f08197b"
$response = Invoke-RestMethod -Uri $webhook -Method Post -Body '{"source":"NEXUS"}' -ContentType "application/json"
Write-Output "n8n workflow triggered successfully!"
Write-Output $response