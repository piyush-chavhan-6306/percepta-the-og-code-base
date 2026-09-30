# Setup Online, Offline, Shared, Docs directory structure and perform initial copy

$ErrorActionPreference = 'Stop'
Write-Host "Creating target folder structure..."

$dirs = @(
  "online/frontend", "online/backend", "online/services", "online/copilot", "online/sync", "online/storage", "online/database", "online/auth", "online/config", "online/deployment",
  "offline/frontend", "offline/backend", "offline/services", "offline/copilot", "offline/storage", "offline/database", "offline/camera", "offline/desktop", "offline/config", "offline/deployment",
  "shared/types", "shared/models", "shared/incident", "shared/tracking", "shared/evidence", "shared/severity", "shared/camera", "shared/copilot", "shared/utilities",
  "docs"
)

foreach ($d in $dirs) {
  if (-not (Test-Path $d)) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    Write-Host "Created directory: $d"
  }
}

Write-Host "Copying backend to online/backend and offline/backend..."
Copy-Item -Path "backend/*" -Destination "online/backend/" -Recurse -Force -Exclude "__pycache__"
Copy-Item -Path "backend/*" -Destination "offline/backend/" -Recurse -Force -Exclude "__pycache__"

Write-Host "Copying frontend code (excluding node_modules and dist)..."
$frontendItems = Get-ChildItem -Path "frontend" -Exclude "node_modules", "dist", ".git"
foreach ($item in $frontendItems) {
  Copy-Item -Path $item.FullName -Destination "online/frontend/" -Recurse -Force
  Copy-Item -Path $item.FullName -Destination "offline/frontend/" -Recurse -Force
}

Write-Host "Copying configs..."
Copy-Item -Path "configs/*" -Destination "online/config/" -Recurse -Force
Copy-Item -Path "configs/*" -Destination "offline/config/" -Recurse -Force

Write-Host "Initial structure established successfully."
