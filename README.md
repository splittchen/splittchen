# Splittchen - Expense Splitting Made Simple

A privacy-first expense splitting app built with Flask. Create groups, split expenses, and settle debts without registration. Perfect for roommates, travel groups, and recurring bills.

Hosted Version: **https://splittchen.com**

## ✨ Features

- **🔐 No Registration**: Token-based access, no accounts needed
- **📱 Mobile Optimized**: Touch-friendly dark theme interface with native mobile experience
- **⚡ Real-Time Updates**: WebSocket-powered live collaboration with browser notifications
- **🔗 Personal Access Links**: Unique participant URLs for seamless group access
- **💸 Smart Settlements**: Optimized payment suggestions
- **📧 Enhanced Invitations**: Pre-created participants with personalized email invitations
- **🔄 Recurring Groups**: Monthly auto-settlement for bills
- **🌍 Multi-Currency**: Real-time conversion support
- **⏰ Auto-Expiration**: Set group expiry dates
- **📊 Settlement History**: Track expense periods
- **🔔 Browser Notifications**: Get notified of group updates even when tab is closed

## 🚀 Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/splittchen/splittchen.git
cd splittchen
cp .env.example .env
# Edit .env with your settings (all options documented inside)

docker-compose up -d
```

Access at: **http://localhost:5000**

> **Multi-Architecture:** Docker images support `linux/amd64` and `linux/arm64`. Docker automatically pulls the correct architecture.

#### Docker User Permissions

Set `DOCKER_USER` and `DOCKER_GROUP` in `.env` to your uid:gid (`id $(whoami)`).

### Local Development

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## ⚙️ Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` — every option is documented inline.

**Key settings:**

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Secure random key (32+ chars). Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | PostgreSQL connection string |
| `BASE_URL` | Your public URL (e.g. `https://splittchen.com`) |
| `SMTP_*` | Email server settings for invitations and reports |
| `SECURE_COOKIES` | Set `true` for HTTPS deployments |
| `TZ` | Container timezone (e.g. `Europe/Vienna`) |

## 🚀 Production Deployment

### Docker with Reverse Proxy (Recommended)

```bash
docker-compose up -d
# Configure reverse proxy (Traefik/Nginx) for HTTPS → http://localhost:5000
```

### Manual with Gunicorn

```bash
pip install -r requirements.txt
gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:5000 wsgi:application
```

> **Note:** WebSocket support requires gevent workers with a single worker process.

## 🔒 Security

- Token-based authentication (no user accounts)
- Security headers: CSP, X-Frame-Options, HSTS, Permissions-Policy
- CSRF protection, input validation, SQL injection prevention
- Non-root Docker container, minimal attack surface
- Email rate limiting with configurable thresholds
- Environment-based secrets, no hardcoded credentials

See [SECURITY.md](SECURITY.md) for vulnerability reporting and security policy.

## 🔧 CLI Commands

```bash
docker-compose exec web flask check-settlements   # Manual settlement check
docker-compose exec web flask scheduler-status     # View scheduled jobs
```

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Docker build fails | `docker system prune -f && docker-compose up --build` |
| Database connection error | Check PostgreSQL container: `docker-compose logs db` |
| Email not working | Verify SMTP credentials in `.env` |
| Port 5000 in use | Stop other services or change port in `docker-compose.yml` |
| Permission denied | Check `DOCKER_USER`/`DOCKER_GROUP` in `.env` |

```bash
# Reset database (removes all data)
docker-compose down -v && docker-compose up -d

# View logs
docker-compose logs -f web
```

## 🏗️ Architecture

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0 + SQLAlchemy ORM |
| Real-Time | Flask-SocketIO with gevent |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Scheduler | APScheduler for background jobs |
| Frontend | Jinja2 + Bootstrap 5 + Socket.IO |
| Deployment | Docker Compose + Gunicorn |

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and how to submit changes.

## 📄 License

**MIT License with Commercial Use Restriction**

✅ Personal use: freely use, modify, and distribute  
❌ Commercial use: requires explicit written permission

See [LICENSE](LICENSE) for full terms.

See [LICENSE](LICENSE) file for complete terms.

For commercial licensing inquiries, please contact the project maintainer.

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- 🐛 **Bug Reports**: Use GitHub Issues
- ✨ **Feature Requests**: Use GitHub Issues  
- 🔧 **Pull Requests**: Follow the contribution guidelines
- 💬 **Discussions**: For questions and general discussion

## 🌟 Recent Updates

### ✅ Implemented in v1.0
- **Real-Time WebSocket Updates**: Live collaboration without page refresh
- **Browser Notifications**: Desktop notifications for group updates
- **Unique Participant Access**: Personal access links for seamless group access
- **Pre-Created Participants**: Enhanced invitation system with personalized onboarding
- **Enhanced Admin Panel**: Participant management with personal link viewing
- **Mobile WebSocket Support**: Real-time updates optimized for mobile devices
- **Comprehensive Email System**: Rate-limited, professional email templates

### 🚀 Planned Features
- **Export Functionality**: CSV/PDF expense reports
- **Native App Support**: Native Android/IOS Apps

## 🙏 Built With

- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/) - Real-time WebSocket support
- [Bootstrap](https://getbootstrap.com/) - Frontend styling with WebSocket integration
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM with participant tokens
- [APScheduler](https://apscheduler.readthedocs.io/) - Background scheduling
- [Socket.IO](https://socket.io/) - Real-time client-server communication
- [Gevent](http://www.gevent.org/) - Concurrent networking for WebSocket support
