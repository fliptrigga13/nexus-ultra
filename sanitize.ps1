
$content = Get-Content "c:\Users\fyou1\Desktop\New folder\nexus-ultra\veilpiercer_proof.ps1" -Raw
# Replace any non-ASCII characters or weird quotes
$content = $content -replace '[^\x00-\x7F]', ''
Set-Content "c:\Users\fyou1\Desktop\New folder\nexus-ultra\veilpiercer_proof.ps1" $content -Encoding ASCII
