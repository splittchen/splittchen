# Splittchen - Expense Splitting Made Simple

A privacy-first expense splitting app built with Flask. Create groups, split expenses, and settle debts without registration. Perfect for roommates, travel groups, and recurring bills.

## ✨ Features

- **🔐 No Registration**: Token-based access, no accounts needed
- **📱 Mobile Optimized**: Touch-friendly dark theme interface with native mobile experience
- **⚡ Real-Time Updates**: WebSocket-powered live collaboration with browser notifications
- **� Personal Access Links**: Unique participant URLs for seamless group access
- **�💸 Smart Settlements**: Optimized payment suggestions
- **📧 Enhanced Invitations**: Pre-created participants with personalized email invitations
- **🔄 Recurring Groups**: Monthly auto-settlement for bills
- **🌍 Multi-Currency**: Real-time conversion support
- **⏰ Auto-Expiration**: Set group expiry dates
- **📊 Settlement History**: Track expense periods
- **🔔 Browser Notifications**: Get notified of group updates even when tab is closed

## 🚀 Quick Start

### Production Deployment (Docker)
```bash
# Clone and configure
git clone <your-repository-url>
cd splittchen
cp .env.example .env
# Edit .env with your settings (see Configuration section)

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f web
```

Access your application at: **http://localhost:5000**

### Docker User Configuration

Configure user permissions in your `.env` file:

```bash
# Find your user ID:
id $(whoami)
# Set DOCKER_USER and DOCKER_GROUP to your uid:gid
```

```env
DOCKER_USER=1000
DOCKER_GROUP=1000
DATA_PATH=./data
```

### Local Development
```bash
# Setup virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: Configure required environment variables

# Start development server
python app.py
```

Access at: **http://localhost:5000**

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure these required settings:

```env
# Application
SECRET_KEY=your-secure-secret-key-32-characters-minimum
BASE_URL=https://yourdomain.com
DEFAULT_CURRENCY=USD

# Database
DATABASE_URL=postgresql://splittchen:password@db:5432/splittchen
POSTGRES_DB=splittchen
POSTGRES_USER=splittchen
POSTGRES_PASSWORD=secure-password

# Email (for invitations and reports)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=noreply@yourdomain.com

# Security Configuration
SECURE_COOKIES=true              # Enable for HTTPS (disable for development)
LOG_LEVEL=INFO                   # DEBUG|INFO|WARNING|ERROR

# Scheduling & Timezone
TZ=UTC                           # Your local timezone (entire container)
SCHEDULER_SETTLEMENT_TIME=23:30   # When to run settlements (24h format)
SCHEDULER_REMINDER_TIME=09:00     # When to send reminders (24h format)

# Email Rate Limiting
EMAIL_RATE_LIMITING_ENABLED=true
EMAIL_LIMIT_REMINDER=1               # Settlement reminders per group per day
EMAIL_LIMIT_SETTLEMENT=5             # Settlement reports per group per day
EMAIL_LIMIT_INVITATION=25            # Group invitations per group per day
EMAIL_LIMIT_PRECREATED_INVITATION=25 # Pre-created participant invitations per group per day
EMAIL_LIMIT_GROUP_CREATED=19         # Group creation confirmations per day
EMAIL_LIMIT_TOTAL_DAILY=50           # Total emails per group per day

# Real-Time Features
ENABLE_WEBSOCKETS=true               # Enable real-time WebSocket updates (production default: true)
WEBSOCKET_CORS_ORIGINS=*             # WebSocket CORS origins (configure for production)

# Docker
DOCKER_USER=1000
DOCKER_GROUP=1000
DATA_PATH=./data
```

## Production Deployment

### Security Features
✅ **Enterprise-grade security implemented:**
- **Authentication**: Token-based access without user accounts
- **Security Headers**: CSP, X-Frame-Options, X-XSS-Protection, Permissions-Policy
- **HTTPS Support**: Configurable secure cookies for production deployments
- **Input Validation**: Email validation, CSRF protection, input sanitization
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- **Container Security**: Non-root execution, minimal attack surface
- **Email Rate Limiting**: Anti-abuse protection with configurable thresholds
- **Comprehensive Logging**: Security event tracking with configurable verbosity
- **Secret Management**: Environment-based configuration, no hardcoded credentials

### Environment Configuration
```bash
# Generate secure secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Example production .env
SECRET_KEY=your-64-character-secret-key-here
DATABASE_URL=postgresql://splittchen:secure_password@db:5432/splittchen
SMTP_HOST=smtp2go.com
SMTP_USERNAME=your-smtp2go-username
SMTP_PASSWORD=your-smtp2go-password
BASE_URL=https://yourdomain.com

# Security Configuration for Production
SECURE_COOKIES=true    # Enable for HTTPS deployments
LOG_LEVEL=INFO         # INFO for ops monitoring, WARNING for security focus
```

### Deployment Options

**Option 1: Docker with Reverse Proxy (Recommended)**
```bash
# Start services
docker-compose up -d

# Configure reverse proxy (Traefik/Nginx) for HTTPS
# Point to http://localhost:5000
```

**Option 2: Manual with Gunicorn**
```bash
# Install dependencies
pip install -r requirements.txt gunicorn

# Run with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 2 wsgi:application
```

## Advanced Features

### Real-Time Collaboration 🔄
Modern WebSocket-powered live updates and notifications:
- **Instant Updates**: See expenses and participants added in real-time (no page refresh)
- **Browser Notifications**: Get notified of group changes even when tab is closed
- **Live Collaboration**: Multiple users can work on the same group simultaneously
- **Connection Management**: Automatic reconnection handling and offline resilience
- **Mobile Optimized**: Reduced battery drain compared to traditional polling

### Unique Participant Access 🔗
Enhanced user experience with personalized group access:
- **Personal Access Links**: Each participant gets a unique URL (`/p/{token}`) for direct group access
- **Pre-Created Participants**: Admins can create participants and send personalized invitations
- **Seamless Onboarding**: Click personal link to access group without entering details
- **Cross-Device Access**: Access your participant account from any device using personal link
- **Admin Management**: View and manage participant personal links from admin panel

### Enhanced Invitation System 📧
Streamlined group joining with intelligent participant management:
- **Personalized Invitations**: Automatic participant creation when sending invitations
- **Direct Access Links**: Invitations contain unique participant links for immediate access
- **Smart Email Templates**: Professional emails with group branding and personal touches
- **Invitation Analytics**: Track who has been invited and when they last accessed

### Recurring Groups & Auto-Settlement
Create groups with monthly auto-settlement for regular expenses:
- **Monthly Billing**: Perfect for shared apartments, office expenses
- **Automatic Processing**: Settlement emails sent automatically on last day of month
- **Expense Archiving**: Previous months moved to history tab
- **Background Scheduler**: Uses APScheduler for reliable automation
- **Timezone Support**: Configure scheduler timezone and settlement times

### Timezone & Scheduler Configuration
The application allows customizing timezone and scheduler times:

```env
# Set container timezone (affects entire application)
TZ=Europe/Vienna                  # Your local timezone
SCHEDULER_SETTLEMENT_TIME=23:30   # Process settlements (24-hour format)
SCHEDULER_REMINDER_TIME=09:00     # Send reminders (24-hour format)
```

### Group Management
- **Settle Without Closing**: Process payments but keep group active
- **Settle and Close**: Final settlement and group deactivation  
- **Group History**: View past settlement periods and archived expenses
- **Auto-Expiration**: Groups automatically close on set expiration dates
- **Group Deletion**: Admin-only complete group removal with cascade cleanup
- **Settlement Reminders**: Email notifications 3 days before monthly settlement

### Real-Time Features Configuration

#### WebSocket Settings
```env
# Enable/disable real-time features (default: true in production)
ENABLE_WEBSOCKETS=true

# WebSocket CORS configuration (configure for production security)
WEBSOCKET_CORS_ORIGINS=*  # Development: *, Production: https://yourdomain.com
```

#### Browser Notifications
The application includes progressive browser notification support:
- **Automatic Permission Request**: Requested on first user interaction
- **Smart Notifications**: Only when tab is not active
- **Notification Types**: New expenses, participants joining, settlements
- **Privacy-First**: Notifications stored locally, no external services

#### Real-Time Events
Users receive instant updates for:
- ✅ **Expense Changes**: New, edited, or deleted expenses
- ✅ **Participant Updates**: Members joining or leaving
- ✅ **Balance Updates**: Recalculated balances and settlements
- ✅ **Admin Actions**: Group settlements, closures, and management changes

### Personal Access Links

#### Participant Experience
Each participant automatically receives:
- **Unique Access URL**: `https://yourdomain.com/p/{access-token}` 
- **Cross-Device Access**: Use the same link on phone, tablet, computer
- **No Login Required**: Direct access to your group view
- **Session Persistence**: 90-day automatic login

#### Admin Management
Group administrators can:
- **View Personal Links**: See all participant access URLs in admin panel
- **Resend Invitations**: Send new invitation emails with personal links
- **Pre-Create Participants**: Add members before they join, send personalized invites
- **Manage Access**: Monitor participant activity and last access times

### CLI Commands
```bash
# Check for due settlements manually
docker-compose exec web flask check-settlements

# View scheduler status and jobs
docker-compose exec web flask scheduler-status
```

## Troubleshooting

### Common Issues
| Issue | Solution |
|-------|----------|
| Docker build fails | `docker system prune -f && docker-compose up --build` |
| Database connection error | Check PostgreSQL container: `docker-compose logs db` |
| Email not working | Verify SMTP credentials in .env file |
| Port 5000 in use | Stop other services or change port in docker-compose.yml |
| Permission denied | Check DOCKER_USER/DOCKER_GROUP settings in .env |

### Reset Database
```bash
# Clear Docker volumes and restart (removes all data)
docker-compose down -v
docker-compose up -d
```

### Production Troubleshooting
- Ensure SECRET_KEY is properly set (32+ characters)
- Use strong PostgreSQL passwords
- Configure proper SMTP settings for email notifications
- Use HTTPS in production environments
- Monitor logs: `docker-compose logs -f`

### Security Monitoring
```bash
# Monitor security events
docker-compose logs web | grep WARNING

# Track unauthorized access attempts
docker-compose logs web | grep "Unauthorized"

# Monitor group deletions
docker-compose logs web | grep "permanently deleted"

# Check email rate limiting
docker-compose logs web | grep "rate limit"

# Monitor admin panel access
docker-compose logs web | grep "Admin panel accessed"
```

**Log Level Configuration:**
- `LOG_LEVEL=DEBUG`: Development debugging
- `LOG_LEVEL=INFO`: Production operational monitoring (recommended)
- `LOG_LEVEL=WARNING`: Security-focused monitoring only
- `LOG_LEVEL=ERROR`: Critical errors only

## Architecture

- **Backend**: Flask 3.0 with SQLAlchemy ORM + Flask-SocketIO for real-time features
- **Database**: PostgreSQL with automatic schema initialization
- **Real-Time**: WebSocket connections with room-based messaging and automatic fallbacks
- **Task Queue**: APScheduler for background jobs (settlements, reminders)
- **Sessions**: Flask server-side sessions with 90-day persistence
- **Participant Access**: Unique token-based authentication with personal access links
- **Frontend**: Server-side rendered Jinja2 templates with Bootstrap 5 + Socket.IO client
- **Notifications**: Browser push notifications with permission management
- **Mobile**: Responsive design with touch-optimized interface and WebSocket support
- **Security**: Token-based access, CSRF protection, input validation, rate limiting
- **Deployment**: Docker Compose with multi-container setup + gevent WSGI server

## 📄 License

This project is licensed under a **MIT License with Commercial Use Restriction**.

**Personal Use**: ✅ Freely use, modify, and distribute for personal projects  
**Commercial Use**: ❌ Requires explicit written permission

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