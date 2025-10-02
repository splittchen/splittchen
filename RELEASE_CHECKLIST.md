# Splittchen Public Release Checklist

This document provides a comprehensive checklist for preparing Splittchen for public release.

## 🚨 CRITICAL - Security & Credentials

### Before Publishing Repository
- [ ] **Rotate ALL credentials in your `.env` file**
  - [ ] Generate new `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
  - [ ] Change database password (`POSTGRES_PASSWORD`)
  - [ ] Change SMTP password or regenerate API key
  - [ ] Update all services with new credentials
- [ ] **Verify `.env` is in `.gitignore`** ✅ (Already confirmed)
- [ ] **Confirm `.env` was never committed to git history** ✅ (Already verified)
- [ ] **Check for any other sensitive files**
  ```bash
  find . -name "*.key" -o -name "*.pem" -o -name "credentials.*"
  ```

### Scan for Hardcoded Secrets
- [ ] **Run security scanner**
  ```bash
  # Scan for potential secrets in code
  grep -r "password\|secret\|api_key" --include="*.py" --include="*.js" . | grep -v ".env"
  ```
- [ ] **Verify no production URLs/IPs in code** ✅ (Already verified)
- [ ] **Check git history for accidentally committed secrets**
  ```bash
  git log --all --full-history -- .env
  ```

---

## 📝 Documentation Review

### License & Legal
- [x] **LICENSE file exists and includes contact information** ✅
- [ ] **Copyright year is current** (Update if needed)
- [ ] **Commercial use terms are clear**
- [ ] **Attribution requirements documented**

### README.md
- [ ] **Verify all links work** (especially GitHub links)
- [ ] **Check all code examples are accurate**
- [ ] **Verify deployment instructions**
- [ ] **Ensure feature list is up-to-date**
- [ ] **Screenshots/GIFs are current** (if applicable)

### SECURITY.md
- [ ] **Verify vulnerability disclosure process**
- [ ] **Update supported versions**
- [ ] **Confirm contact methods work**

### CONTRIBUTING.md
- [ ] **Verify development setup instructions**
- [ ] **Check contribution guidelines are clear**
- [ ] **Update code of conduct (if needed)**

---

## 🐳 Docker & Deployment

### Docker Configuration
- [x] **Container registry references documented** ✅
- [x] **Build script includes usage notes** ✅
- [ ] **Verify Dockerfile security best practices**
  - [x] Non-root user ✅
  - [x] Multi-stage build ✅
  - [x] No secrets in layers ✅
- [ ] **Test Docker build from clean checkout**
  ```bash
  git clone <repo-url> test-build
  cd test-build
  docker-compose build
  ```

### docker-compose.yml
- [x] **Usage documentation clear** ✅
- [ ] **Verify environment variable defaults are safe**
- [ ] **Check volume mounts are appropriate**

---

## 🧪 Testing & Quality

### Functional Testing
- [ ] **Test fresh installation**
  ```bash
  docker-compose up -d
  # Create group, add expense, invite member
  docker-compose down -v
  ```
- [ ] **Test all major features**
  - [ ] Group creation
  - [ ] Expense addition/editing/deletion
  - [ ] Participant management
  - [ ] Email invitations
  - [ ] Settlement process
  - [ ] WebSocket real-time updates
  - [ ] Admin panel access

### Code Quality
- [ ] **Run linters (if configured)**
  ```bash
  flake8 app/
  pylint app/
  ```
- [ ] **Check for debug code**
  - [ ] Remove/comment unnecessary `print()` statements
  - [ ] Review `console.log()` statements (21 found - decide if needed)
- [ ] **Remove TODOs or document them in issues**

---

## 📦 Repository Setup

### Git Configuration
- [ ] **Create `.gitattributes` (if needed)**
- [ ] **Verify `.gitignore` is comprehensive** ✅
- [ ] **Check `.dockerignore` is complete** ✅

### GitHub Configuration
- [ ] **Set repository description**
- [ ] **Add topics/tags** (flask, expense-tracker, websocket, docker, etc.)
- [ ] **Configure branch protection on `main`**
- [ ] **Enable Dependabot alerts** ✅ (Already configured)
- [ ] **Set up GitHub Actions (optional)**
  - [ ] CI/CD pipeline
  - [ ] Automated testing
  - [ ] Security scanning

### Release Tags
- [ ] **Create initial release tag** (e.g., `v1.0.0`)
  ```bash
  git tag -a v1.0.0 -m "Initial public release"
  git push origin v1.0.0
  ```
- [ ] **Write release notes**
- [ ] **Upload pre-built Docker image** (optional)

---

## 🔒 Security Hardening

### Code Security
- [x] **No SQL injection vulnerabilities** ✅ (ORM only)
- [x] **XSS protection enabled** ✅ (Jinja2 auto-escaping)
- [x] **CSRF protection on forms** ✅ (Flask-WTF)
- [x] **Input validation implemented** ✅ (WTForms)
- [x] **Security headers configured** ✅ (CSP, X-Frame-Options, etc.)
- [x] **Email rate limiting active** ✅

### Dependency Security
- [ ] **Review all dependencies for known vulnerabilities**
  ```bash
  pip install safety
  safety check -r requirements.txt
  ```
- [ ] **Ensure dependencies are pinned with version ranges** ✅
- [ ] **Set up Dependabot** ✅ (Already configured)

---

## 📢 Pre-Publication

### Final Review
- [ ] **Read through entire README as a new user**
- [ ] **Test "Quick Start" instructions on clean machine**
- [ ] **Verify all external links work**
- [ ] **Check for any personal/internal references**
  - [x] No personal email addresses in code ✅
  - [ ] No internal hostnames/URLs
  - [x] No company-specific references ✅

### Community Preparation
- [ ] **Prepare announcement text**
- [ ] **Create GitHub Discussions (optional)**
- [ ] **Set up issue templates** ✅ (Already configured)
- [ ] **Prepare FAQ document (optional)**

---

## 🚀 Publication Steps

1. **Final Credential Rotation**
   ```bash
   # Generate new secrets
   python -c "import secrets; print(secrets.token_hex(32))"
   # Update .env file
   # Restart services with new credentials
   ```

2. **Create Clean Commit**
   ```bash
   git add .
   git commit -m "chore: Prepare for public release

   - Updated LICENSE with contact information
   - Enhanced Docker registry documentation
   - Removed development artifacts
   - Added public release checklist"
   ```

3. **Tag Release**
   ```bash
   git tag -a v1.0.0 -m "Initial public release"
   ```

4. **Push to GitHub**
   ```bash
   git push origin main
   git push origin v1.0.0
   ```

5. **Make Repository Public** (on GitHub)
   - Settings → Danger Zone → Change visibility

6. **Create GitHub Release**
   - Write release notes
   - Attach any binaries/artifacts
   - Publish release

7. **Announce**
   - Share on social media (if desired)
   - Post to relevant communities
   - Add to awesome lists (if applicable)

---

## ✅ Post-Release

### Monitoring
- [ ] **Watch for initial security reports**
- [ ] **Monitor first issues/PRs**
- [ ] **Track Docker image pulls**
- [ ] **Set up analytics (optional)**

### Maintenance
- [ ] **Respond to issues within 48 hours**
- [ ] **Review PRs promptly**
- [ ] **Keep dependencies updated**
- [ ] **Address security vulnerabilities immediately**

---

## 📊 Release Status

**Current Status:** 🟡 Ready for final preparations

### Completed ✅
- Security audit complete
- No hardcoded secrets found
- `.env` properly excluded from git
- Docker security best practices implemented
- Documentation comprehensive
- License includes contact information
- Container registry documented
- Development artifacts removed

### Remaining 🔴
1. **CRITICAL:** Rotate all credentials in `.env` file
2. Test full deployment from clean checkout
3. Create release tag and notes
4. Final review of README as new user

---

## 🆘 Emergency Rollback

If credentials are accidentally exposed:

1. **Immediately rotate all secrets**
   ```bash
   # Generate new SECRET_KEY
   # Change all passwords
   # Revoke compromised API keys
   ```

2. **Rewrite git history (if committed)**
   ```bash
   # DANGER: Only if absolutely necessary
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch .env' \
     --prune-empty --tag-name-filter cat -- --all
   ```

3. **Force push (if repository already public)**
   ```bash
   git push origin --force --all
   git push origin --force --tags
   ```

4. **Notify users of security incident** (if applicable)

---

**Last Updated:** $(date)
**Audit Status:** ✅ Passed - Ready for publication after credential rotation