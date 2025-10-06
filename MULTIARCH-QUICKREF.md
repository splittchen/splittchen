# Multi-Arch Build - Quick Reference

## ⚡ Quick Commands

```powershell
# Daily development (2-5 min)
.\make.ps1 build-local

# Test multi-arch (10-15 min)
.\make.ps1 test-build

# Release (10-15 min)
$env:VERSION="1.0.0"
.\make.ps1 build-version

# Or use Git (automatic CI)
git tag v1.0.0 && git push origin v1.0.0

# Verify
.\make.ps1 inspect

# Clean up
.\make.ps1 clean

# Help
.\make.ps1 help
```

## 📋 Command Reference

| Command | Time | Use For |
|---------|------|---------|
| `.\make.ps1 build-local` | 2-5 min | Daily development |
| `.\make.ps1 test-build` | 10-15 min | Pre-release testing |
| `.\make.ps1 build-push` | 10-15 min | Manual release |
| `.\make.ps1 build-version` | 10-15 min | Versioned release |
| `.\make.ps1 inspect` | instant | Check platforms |
| `.\make.ps1 clean` | instant | Reset builders |

## 🔧 Advanced Usage

```powershell
# Custom registry
$env:REGISTRY="ghcr.io/myuser"
.\make.ps1 build-push

# Specific platforms
.\build-multiarch.ps1 -Platforms "linux/amd64"

# Build without push
.\build-multiarch.ps1 -NoPush

# Include ARM v7
.\build-multiarch.ps1 -Platforms "linux/amd64,linux/arm64,linux/arm/v7"
```

## 🎯 Workflows

### Development
```powershell
# Edit code → Build locally → Test → Push
.\make.ps1 build-local
docker-compose up -d
git add . && git commit -m "..." && git push
```

### Release
```bash
# Tag → Push → CI builds automatically
git tag v1.0.0
git push origin v1.0.0
```

## 🔍 Verification

```powershell
# Check manifest
docker buildx imagetools inspect ghcr.io/splittchen/splittchen:latest

# Pull and test
docker pull ghcr.io/splittchen/splittchen:latest
docker run -p 5000:5000 ghcr.io/splittchen/splittchen:latest
```

## 🆘 Troubleshooting

```powershell
# Validate setup
.\test-multiarch.ps1 -Quick

# Reset builder
.\make.ps1 clean
docker buildx create --name splittchen-builder --use --bootstrap

# Login
docker login ghcr.io -u YOUR_USERNAME

# Check status
docker buildx ls
docker version
```

## 💡 Tips

- ✅ Use `build-local` for daily work (fast)
- ✅ Let CI handle releases (automatic)
- ✅ Test multi-arch before releasing
- ❌ Don't build multi-arch for every change (slow)

## 📖 Full Documentation

See [MULTIARCH.md](MULTIARCH.md) for complete guide.
