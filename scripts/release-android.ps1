<#
.SYNOPSIS
  Builds a new Android release and publishes it to the server, so every phone running the app is offered the update.

.DESCRIPTION
  1. raises the version in android\version.properties,
  2. builds the APK pointed at the server (restoring the old version if the build fails),
  3. asks for an ADMIN email and password (typed here, never stored), logs in, uploads the APK, logs out.
  Phones then show "Update available" the next time the app's home screen opens; tapping Update downloads the
  APK and opens Android's installer (one confirmation tap there). The new APK is checked by the app to be signed
  with the same key as the installed one, so always build on this laptop (same debug keystore).

.EXAMPLE
  .\scripts\release-android.ps1
  .\scripts\release-android.ps1 -VersionName "1.5"
  .\scripts\release-android.ps1 -SkipBuild        # publish the APK that is already built
#>
param(
    [string]$ServerUrl = "https://indev.eko.in/sbi-relationship-crm",
    [string]$Gradle = "C:\Android\gradle\gradle-8.9\bin\gradle.bat",
    [string]$VersionName = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ServerUrl = $ServerUrl.TrimEnd("/")
$root = Split-Path -Parent $PSScriptRoot
$androidDir = Join-Path $root "android"
$propsFile = Join-Path $androidDir "version.properties"
$apk = Join-Path $androidDir "app\build\outputs\apk\debug\app-debug.apk"

# ---- current version
$props = @{}
Get-Content $propsFile | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $props[$Matches[1]] = $Matches[2].Trim() } }
$oldCode = [int]$props["VERSION_CODE"]
$oldName = $props["VERSION_NAME"]
$code = $oldCode + 1
$name = if ($VersionName) { $VersionName } else { "1.$($code - 1)" }
Write-Host "Releasing version $name (code $code); the current one is $oldName (code $oldCode)."

# ---- build
if (-not $SkipBuild) {
    Set-Content -Path $propsFile -Value @("VERSION_CODE=$code", "VERSION_NAME=$name") -Encoding ASCII
    Push-Location $androidDir
    try {
        & $Gradle --offline :app:assembleDebug "-PrcrmApiBaseUrl=$ServerUrl/api/v1/"
        if ($LASTEXITCODE -ne 0) { throw "The build failed (exit code $LASTEXITCODE)." }
    } catch {
        Set-Content -Path $propsFile -Value @("VERSION_CODE=$oldCode", "VERSION_NAME=$oldName") -Encoding ASCII
        Write-Host "Version restored to $oldName (code $oldCode)." -ForegroundColor Yellow
        throw
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path $apk)) { throw "No APK at $apk" }
Write-Host ("APK ready: {0:N1} MB" -f ((Get-Item $apk).Length / 1MB))

# ---- upload (admin only)
$email = Read-Host "Admin email"
$secure = Read-Host "Admin password" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
$headerFile = $null
$token = $null
try {
    $login = Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/v1/auth/login" -ContentType "application/json" `
        -Body (@{ email = $email; password = $plain } | ConvertTo-Json)
    $token = $login.token
    if ($login.role -ne "admin") { throw "$email is not an admin (role: $($login.role))." }

    # The token goes to curl through a temp header file, not the command line.
    $headerFile = New-TemporaryFile
    Set-Content -Path $headerFile -Value "Authorization: Bearer $token" -Encoding ASCII
    $result = & curl.exe -sS --fail-with-body -X POST -H "@$headerFile" `
        -F "apk=@$apk" -F "version_code=$code" -F "version_name=$name" "$ServerUrl/api/v1/app/release"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed: $result" }
    Write-Host "Published: $result" -ForegroundColor Green
} finally {
    $plain = $null
    if ($token) {
        try { Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/v1/auth/logout" -Headers @{ Authorization = "Bearer $token" } | Out-Null } catch { }
    }
    if ($headerFile) { Remove-Item $headerFile -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "Done. Phones will offer the update when the app's home screen opens." -ForegroundColor Green
Write-Host "Commit the new version so it is not reused:  git add android/version.properties; git commit -m 'release: android $name'"
