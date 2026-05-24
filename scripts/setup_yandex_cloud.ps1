param(
    [Parameter(Mandatory = $true)]
    [string]$FolderId,

    [Parameter(Mandatory = $false)]
    [string]$ServiceAccountName = "hr-assessment-bot",

    [Parameter(Mandatory = $true)]
    [string]$BucketName
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = Join-Path $env:USERPROFILE "yandex-cloud\bin\$Name.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    if (-not $command) {
        throw "Command '$Name' was not found. Install Yandex Cloud CLI and run 'yc init'."
    }
}

$Yc = Require-Command "yc"

Write-Host "Using folder: $FolderId"
& $Yc config set folder-id $FolderId | Out-Null

Write-Host "Creating service account: $ServiceAccountName"
$saJson = & $Yc iam service-account create `
    --name $ServiceAccountName `
    --description "Telegram HR assessment bot: SpeechKit async + Object Storage" `
    --format json | ConvertFrom-Json

$saId = $saJson.id
Write-Host "Service account id: $saId"

Write-Host "Assigning roles..."
& $Yc resource-manager folder add-access-binding $FolderId `
    --role ai.speechkit-stt.user `
    --subject serviceAccount:$saId | Out-Null

& $Yc resource-manager folder add-access-binding $FolderId `
    --role ai.languageModels.user `
    --subject serviceAccount:$saId | Out-Null

& $Yc resource-manager folder add-access-binding $FolderId `
    --role storage.uploader `
    --subject serviceAccount:$saId | Out-Null

& $Yc resource-manager folder add-access-binding $FolderId `
    --role storage.editor `
    --subject serviceAccount:$saId | Out-Null

Write-Host "Creating private bucket: $BucketName"
& $Yc storage bucket create $BucketName `
    --default-storage-class STANDARD `
    --max-size 0 | Out-Null

Write-Host "Creating static Object Storage access key..."
$accessKeyJson = & $Yc iam access-key create `
    --service-account-name $ServiceAccountName `
    --description "Object Storage key for HR assessment bot" `
    --format json | ConvertFrom-Json

Write-Host "Creating SpeechKit API key..."
$apiKeyJson = & $Yc iam api-key create `
    --service-account-name $ServiceAccountName `
    --description "SpeechKit API key for HR assessment bot" `
    --format json | ConvertFrom-Json

Write-Host ""
Write-Host "Add these values to .env:"
Write-Host "YANDEX_SPEECHKIT_API_KEY=$($apiKeyJson.secret)"
Write-Host "YANDEX_GPT_API_KEY=$($apiKeyJson.secret)"
Write-Host "YANDEX_STORAGE_BUCKET=$BucketName"
Write-Host "YANDEX_STORAGE_ACCESS_KEY_ID=$($accessKeyJson.access_key.key_id)"
Write-Host "YANDEX_STORAGE_SECRET_ACCESS_KEY=$($accessKeyJson.secret)"
Write-Host "YANDEX_STORAGE_ENDPOINT=https://storage.yandexcloud.net"
Write-Host "YANDEX_STORAGE_PREFIX=interviews"
