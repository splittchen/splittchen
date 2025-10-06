# Multi-Architecture Docker Builds

Complete guide for building and deploying Splittchen Docker images across multiple CPU architectures (AMD64, ARM64).

## 🚀 Quick Start

### For Daily Development (Fast - 2-5 minutes)
```powershell
.\make.ps1 build-local
docker-compose up -d
```

### For Production Release (10-15 minutes)
```bash
# Let GitHub Actions handle it automatically
git tag v1.0.0
git push origin v1.0.0
```

### Manual Multi-Arch Build
```powershell
# Test without pushing
.\make.ps1 test-build

# Build and push
.\make.ps1 build-push
```

## 📋 Available Commands

| Command | Time | Description |
|---------|------|-------------|
| `.\make.ps1 build-local` | 2-5 min | Build for current platform only (development) |
| `.\make.ps1 test-build` | 10-15 min | Build multi-arch without pushing (testing) |
| `.\make.ps1 build-push` | 10-15 min | Build and push latest tag |
| `.\make.ps1 build-version` | 10-15 min | Build with version (set `$env:VERSION="1.0.0"` first) |
| `.\make.ps1 inspect` | instant | View multi-arch manifest |
| `.\make.ps1 clean` | instant | Clean builders and cache |
| `.\make.ps1 help` | instant | Show all commands |

## 🎯 Supported Platforms

| Platform | Architecture | Use Cases |
|----------|-------------|-----------|
| **linux/amd64** | x86_64 | Desktops, servers, cloud (99% of deployments) |
| **linux/arm64** | ARM 64-bit | Apple Silicon, Raspberry Pi 4/5, AWS Graviton |

**Note:** ARM v7 (32-bit) removed for performance. If needed, build manually:
```powershell
.\build-multiarch.ps1 -Platforms "linux/amd64,linux/arm64,linux/arm/v7"
```

## 🔧 Prerequisites

### Local Builds
- **Docker Desktop** (includes Buildx and QEMU)
- **PowerShell** (Windows) or **pwsh** (cross-platform)

### Pushing Images
```powershell
# GitHub Container Registry (recommended)
docker login ghcr.io -u YOUR_GITHUB_USERNAME
# Use Personal Access Token with write:packages scope
# Create at: https://github.com/settings/tokens
```

### GitHub Actions (CI/CD)
- ✅ Already configured in `.github/workflows/docker-multiarch.yml`
- ✅ Builds automatically on version tags
- ✅ **Free for public repos** (unlimited), free tier for private repos (2,000 min/month)

## 📖 Usage Guide

### Development Workflow

```powershell
# 1. Make code changes
# 2. Build locally (fast)
.\make.ps1 build-local

# 3. Test
docker-compose up -d

# 4. Commit and push
git add .
git commit -m "Your changes"
git push
```

### Release Workflow

```bash
# Option 1: Automated (Recommended)
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions builds automatically

# Option 2: Manual
$env:VERSION="1.0.0"
.\make.ps1 build-version
```

### Advanced Usage

```powershell
# Custom registry
$env:REGISTRY="ghcr.io/yourusername"
.\make.ps1 build-push

# Specific platforms
.\build-multiarch.ps1 -Platforms "linux/amd64"

# Build without pushing
.\build-multiarch.ps1 -NoPush -Version "1.0.0"

# Local only (fastest)
.\build-multiarch.ps1 -LocalOnly
```

## 🤖 GitHub Actions

### Automatic Builds
The workflow triggers on:
- **Version tags** (`v*.*.*`) → Builds and pushes versioned tags
- **Manual trigger** → Custom platform selection from Actions tab

### What Gets Created
When you push `v1.0.0`, these tags are created:
- `ghcr.io/splittchen/splittchen:v1.0.0`
- `ghcr.io/splittchen/splittchen:v1.0`
- `ghcr.io/splittchen/splittchen:v1`
- `ghcr.io/splittchen/splittchen:latest`

### Manual Trigger
1. Go to **Actions** → **Build Multi-Arch Docker Image**
2. Click **Run workflow**
3. (Optional) Customize platforms
4. Click **Run workflow**

### Cost & Performance
- **Public repos:** FREE unlimited builds
- **Private repos:** 2,000 free minutes/month, then $0.008/min
- **Typical usage:** 5-10 builds/month = FREE
- **Build time:** 10-15 minutes per build

## ⏱️ Performance

### Build Times

| Build Type | Time | When to Use |
|------------|------|-------------|
| Local (1 platform) | 2-5 min | ✅ Daily development |
| Multi-arch (2 platforms) | 10-15 min | ✅ Releases |
| First build (no cache) | 20-30 min | ⚠️ First time only |

### Why Multi-Arch is Slower
- Builds for multiple platforms simultaneously
- ARM builds use QEMU emulation (5-10x slower than native)
- Dependencies compile from source on ARM platforms

### Speed Optimizations Applied
1. ✅ **Use local builds for development** (single platform, native speed)
2. ✅ **Removed ARM v7** (saves 40% build time)
3. ✅ **Build caching enabled** (saves 50% on rebuilds)
4. ✅ **Only build on releases** (saves GitHub Actions minutes)

## ✅ Verification

### Check Multi-Arch Manifest
```powershell
.\make.ps1 inspect
```

Expected output:
```
Manifests:
  Platform:    linux/amd64
  Platform:    linux/arm64
```

### Test on Different Platforms
```bash
# Docker automatically pulls correct architecture
docker pull ghcr.io/splittchen/splittchen:latest

# Force specific platform
docker pull --platform linux/arm64 ghcr.io/splittchen/splittchen:latest

# Run locally
docker run -p 5000:5000 ghcr.io/splittchen/splittchen:latest
```

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "No builder found" | `docker buildx create --name splittchen-builder --use --bootstrap` |
| "multiple platforms not supported" | Create buildx builder (see above) |
| "exec format error" on ARM | Install QEMU: `docker run --privileged --rm tonistiigi/binfmt --install all` |
| Build very slow | Use `.\make.ps1 build-local` for development |
| "failed to push" permission denied | `docker login ghcr.io -u YOUR_USERNAME` |
| ARM v7 build fails "ffi.h not found" | ✅ Fixed in Dockerfile (includes `libffi-dev`) |

### Reset Everything
```powershell
# Clean up builders and cache
.\make.ps1 clean

# Remove local test images
docker rmi ghcr.io/splittchen/splittchen:latest

# Recreate builder
docker buildx create --name splittchen-builder --use --bootstrap
```

### Validation
```powershell
# Quick validation test
.\test-multiarch.ps1 -Quick

# Check builder status
docker buildx ls

# Check Docker is running
docker version
```

## 🛠️ Maintenance

### Clean Up
```powershell
# Clean builders and cache
.\make.ps1 clean

# Check disk usage
docker buildx du

# Prune old cache
docker buildx prune -af
```

### Update Builder
```powershell
docker buildx rm splittchen-builder
docker buildx create --name splittchen-builder --use --bootstrap
```

## 📚 Reference

### `build-multiarch.ps1` Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-Registry` | Container registry | `ghcr.io/splittchen` |
| `-Version` | Semantic version (creates multiple tags) | - |
| `-Tag` | Single tag | `latest` |
| `-Platforms` | Comma-separated platforms | `linux/amd64,linux/arm64` |
| `-LocalOnly` | Build for local platform only | `false` |
| `-NoPush` | Skip pushing to registry | `false` |

### `make.ps1` Targets

| Target | Description |
|--------|-------------|
| `build-local` | Fast single-platform build |
| `build-multiarch` | Multi-arch build without push |
| `build-push` | Build and push latest |
| `build-version` | Build and push with version (requires `$env:VERSION`) |
| `test-build` | Test multi-arch without push |
| `clean` | Clean builders and cache |
| `inspect` | Inspect multi-arch manifest |
| `help` | Show all commands |

### File Structure
```
build-multiarch.ps1          # Main multi-arch build script
make.ps1                     # Simplified build helper
test-multiarch.ps1           # Validation script
.github/workflows/
  docker-multiarch.yml       # GitHub Actions workflow (optimized)
  docker-multiarch-optimized.yml  # Alternative (releases only)
```

## 💡 Best Practices

### ✅ DO
- Use `.\make.ps1 build-local` for daily development (fast)
- Test multi-arch before releases with `.\make.ps1 test-build`
- Let GitHub Actions handle production builds
- Use semantic versioning for releases (`v1.2.3`)
- Use specific version tags in production deployments
- Verify manifest after building with `.\make.ps1 inspect`

### ❌ DON'T
- Build multi-arch for every code change (slow, unnecessary)
- Use `latest` tag in production (use specific versions)
- Skip authentication before pushing
- Forget to test locally before releasing

## 🔗 Resources

- **Main README:** [README.md](README.md)
- **Docker Buildx:** https://docs.docker.com/buildx/
- **Multi-platform Images:** https://docs.docker.com/build/building/multi-platform/
- **GitHub Actions:** https://docs.github.com/actions
- **GitHub Container Registry:** https://docs.github.com/packages

---

## Need Help?

1. **Run validation:** `.\test-multiarch.ps1 -Quick`
2. **Check this guide** for common issues
3. **View builder status:** `docker buildx ls`
4. **Check logs** in GitHub Actions for CI builds
5. **Open issue** with build logs if problems persist
