$body = @{
    name         = "Zoho Test"
    location     = "-"
    phone        = "9788394394"
    email        = "resig44458@rapplo.com"
    signup_type  = "listing_school_signup"
    website      = "-"
} | ConvertTo-Json

Write-Host "Testing POST /users/ ..."
try {
    $response = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/users/" -ContentType "application/json" -Body $body
    Write-Host "[OK]"
    $response | ConvertTo-Json -Depth 5
} catch {
    $errorBody = $_.ErrorDetails.Message
    Write-Host "[FAIL] $errorBody"
}
