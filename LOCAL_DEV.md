# Local Development Guide

## Quick Start - Local Testing with Docker

### Using the Local Docker Compose

The `docker-compose.local.yml` file is specifically for **local testing** and will build from your current branch instead of pulling the latest production image.

```bash
# Build and start local development environment
docker-compose -f docker-compose.local.yml up --build

# View logs
docker-compose -f docker-compose.local.yml logs -f web

# Stop services
docker-compose -f docker-compose.local.yml down

# Clean rebuild (removes old containers and volumes)
docker-compose -f docker-compose.local.yml down -v
docker-compose -f docker-compose.local.yml up --build
```

### Accessing the Application

- **Web Interface**: http://localhost:5000
- **Debug Mode**: Add `?debug=1` to any group URL to see debug information
  - Example: http://localhost:5000/group/ABC123DEF456?debug=1

### Testing Exit Group Feature

1. **Create a Test Group**:
   - Go to http://localhost:5000
   - Click "Create Group"
   - Fill in group details

2. **Join as a Participant** (Important!):
   - Use the share link to join
   - Enter your name and email
   - Click "Join Group"
   - You MUST be a real participant, not just viewing

3. **Verify Participant Status**:
   - Add `?debug=1` to the group URL
   - Check "Participant ID Type" - should be `True`
   - Check "Exit Button Should Show" - should be `True`

4. **Find the Exit Button**:
   - **Header** (desktop): Orange icon button next to admin panel
   - **Participants Tab**: Warning card at bottom
   - **Bottom Section**: Warning card before mobile navigation

### Troubleshooting

**Exit button not showing?**
- Use `?debug=1` to see why
- Check if you're a real participant (ID should be a number, not 'viewer' or 'admin')
- Make sure group is not settled or expired
- Make sure you joined the group, not just viewing

**Container not building?**
- Use `docker-compose -f docker-compose.local.yml build --no-cache web`
- Check for errors in build output

**Database issues?**
- Clean volumes: `docker-compose -f docker-compose.local.yml down -v`
- Restart: `docker-compose -f docker-compose.local.yml up --build`

## File Differences

### docker-compose.yml (Production)
- Uses `ghcr.io/splittchen/splittchen:latest` image
- Production-ready configuration
- Use for deployment

### docker-compose.local.yml (Development)
- Builds from local Dockerfile
- Uses current git branch code
- Debug mode enabled
- Use for testing features

## Testing the Exit Group Feature

### Requirements to Exit
- ✅ You are a real participant (not viewer/admin)
- ✅ Your balance is exactly 0.00
- ✅ Group is not settled
- ✅ Group is not expired
- ✅ You're not the last participant
- ✅ If you're admin, there must be another admin

### Test Scenarios

**Scenario 1: Successful Exit**
1. Create group with 2+ participants
2. Add some expenses that balance to zero for you
3. Click exit button
4. Confirm in modal
5. You should be redirected to homepage

**Scenario 2: Cannot Exit - Outstanding Balance**
1. Create group with 2+ participants
2. Add expense where you owe money
3. Exit button should show
4. Clicking exit should show error message

**Scenario 3: Cannot Exit - Only Admin**
1. Create group as admin (you're the only admin)
2. Add another participant (not admin)
3. Try to exit
4. Should show error: "Cannot exit - you are the only admin"

**Scenario 4: Cannot Exit - Last Participant**
1. Create group with just yourself
2. Exit button should not show
3. If you try the route directly, should show error

## Development Workflow

1. Make code changes in your branch
2. Rebuild: `docker-compose -f docker-compose.local.yml up --build`
3. Test the feature
4. Check logs: `docker-compose -f docker-compose.local.yml logs -f web`
5. Debug with `?debug=1` parameter
6. Iterate until working

## Environment Variables

Create a `.env` file with:

```env
# Database
DATABASE_URL=postgresql://splittchen:password@db:5432/splittchen
POSTGRES_DB=splittchen
POSTGRES_USER=splittchen
POSTGRES_PASSWORD=password

# App
FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production
BASE_URL=http://localhost:5000
DEFAULT_CURRENCY=EUR
TZ=Europe/Vienna

# Email (optional for local testing)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=noreply@yourdomain.com

# Scheduler
SCHEDULER_SETTLEMENT_TIME=23:30
SCHEDULER_REMINDER_TIME=09:00

# WebSockets
ENABLE_WEBSOCKETS=true
WEBSOCKET_CORS_ORIGINS=*

# Security
SECURE_COOKIES=false
LOG_LEVEL=DEBUG

# Email Rate Limiting
EMAIL_RATE_LIMITING_ENABLED=true
```

## Quick Commands

```bash
# Start local dev environment
docker-compose -f docker-compose.local.yml up --build

# View live logs
docker-compose -f docker-compose.local.yml logs -f

# Exec into container
docker-compose -f docker-compose.local.yml exec web bash

# Check database
docker-compose -f docker-compose.local.yml exec db psql -U splittchen -d splittchen

# Clean restart
docker-compose -f docker-compose.local.yml down -v && docker-compose -f docker-compose.local.yml up --build

# Stop everything
docker-compose -f docker-compose.local.yml down
```
