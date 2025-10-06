#!/usr/bin/env pwsh
# Build script for Splittchen Docker image
# Usage:
#   ./build.ps1                           # Build latest
#   ./build.ps1 -Tag "v1.2.3"           # Build with version
#   ./build.ps1 -Version "1.2.3"        # Build with semantic versioning (creates multiple tags)
#
# NOTE: Default registry is set for the maintainer's builds.
#       For your own builds, either:
#       1. Change the Registry parameter below to your registry
#       2. Or use: ./build.ps1 -Registry "ghcr.io/yourusername"

param(
    [string]$Registry = "ghcr.io/splittchen",  # Maintainer's registry - change for your builds
    [string]$Tag = "latest",
    [string]$Version = "",
    [switch]$NoPush = $false
)

# Determine tags to create
$Tags = @()
if ($Version) {
    # Semantic versioning - create multiple tags
    $v = $Version.TrimStart('v')
    $parts = $v.Split('.')
    if ($parts.Length -ne 3) {
        Write-Host "❌ Version must be in format X.Y.Z (e.g., 1.2.3)" -ForegroundColor Red
        exit 1
    }
    $major, $minor, $patch = $parts
    
    $Tags += "v$v"           # v1.2.3
    $Tags += "v$major.$minor" # v1.2  
    $Tags += "v$major"       # v1
    $Tags += "latest"        # latest
    
    Write-Host "🏷️  Creating tags for version $v`: $($Tags -join ', ')" -ForegroundColor Cyan
} else {
    $Tags += $Tag
}

$LocalTag = "splittchen:$($Tags[0])"
Write-Host "Building Splittchen Docker image..." -ForegroundColor Green

# Build the Docker image
docker build -t $LocalTag -f Dockerfile .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Build successful: $LocalTag" -ForegroundColor Green

# Tag all versions for registry
$RegistryTags = @()
foreach ($tag in $Tags) {
    $registryTag = "$Registry/splittchen:$tag"
    $RegistryTags += $registryTag
    
    Write-Host "Tagging for registry: $registryTag" -ForegroundColor Yellow
    docker tag $LocalTag $registryTag
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Tagging failed for $registryTag" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ All tags created successfully" -ForegroundColor Green

# Push to registry (unless -NoPush is specified)
if (-not $NoPush) {
    Write-Host "Pushing all tags to registry..." -ForegroundColor Yellow
    
    foreach ($registryTag in $RegistryTags) {
        Write-Host "  Pushing: $registryTag" -ForegroundColor Cyan
        docker push $registryTag
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Push failed for $registryTag" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "✅ All pushes successful!" -ForegroundColor Green
    Write-Host "🚀 Images available:" -ForegroundColor Cyan
    foreach ($registryTag in $RegistryTags) {
        Write-Host "   $registryTag" -ForegroundColor White
    }
} else {
    Write-Host "⏸️  Skipping push (use without -NoPush to push)" -ForegroundColor Yellow
    Write-Host "📋 Would push these tags:" -ForegroundColor Yellow
    foreach ($registryTag in $RegistryTags) {
        Write-Host "   $registryTag" -ForegroundColor Gray
    }
}