# trigger-n8n.ps1
$webhook = "http://localhost:5678/webhook/payment-confirmed"
$response = Invoke-RestMethod -Uri $webhook -Method Post -Body '{"event":"payment-confirmed", "email":"test@veilpiercer.com", "tier":"GTC Edition", "amount": 19500}' -ContentType "application/json"
Write-Output "n8n workflow triggered successfully!"
Write-Output $response