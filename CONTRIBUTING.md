# Contributing to Splittchen

Thank you for your interest in contributing to Splittchen! This document provides guidelines and information for contributors.

## 🚀 Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Set up the development environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your development settings
   pip install -r requirements.txt
   ```
4. **Run the application**:
   ```bash
   python app.py
   ```

## 📋 Development Guidelines

### Code Style

We follow the **Google Python Style Guide** with these specifics:

- **Function and variable names**: `snake_case`
- **Class names**: `PascalCase` 
- **Constants**: `UPPER_CASE`
- **Line length**: 88 characters (Black formatter compatible)
- **Docstrings**: Google-style docstrings for all public functions
- **Type hints**: Required for all function parameters and return values

### Documentation

- All public functions must have docstrings
- Use type hints consistently
- Update CLAUDE.md for significant architectural changes
- Keep README.md updated for user-facing changes

### Testing

- Test your changes locally before submitting
- Ensure the development server starts without errors
- Verify email functionality (if making email-related changes)
- Test responsive design on mobile devices

## 🔒 Security Guidelines

**Critical Security Requirements:**

- **Never commit secrets**: Use environment variables for all sensitive data
- **Validate all input**: Especially email addresses and user-provided data  
- **Follow Flask security best practices**: CSRF protection, secure headers, etc.
- **Use parameterized queries**: SQLAlchemy ORM prevents SQL injection
- **Email validation**: Always validate and sanitize email addresses

### Security Checklist

Before submitting your PR, verify:

- [ ] No hardcoded credentials or API keys
- [ ] Input validation on all user forms
- [ ] Proper error handling without information leakage
- [ ] CSRF tokens on all forms
- [ ] Secure email sending (no injection vulnerabilities)

## 🐛 Bug Reports

When reporting bugs, please include:

- **Environment details**: Python version, OS, browser (if applicable)
- **Steps to reproduce**: Clear, numbered steps
- **Expected vs actual behavior**
- **Error messages**: Complete error output/logs
- **Screenshots**: For UI-related issues

## ✨ Feature Requests

For new features:

- **Search existing issues** first to avoid duplicates
- **Describe the use case**: Why is this feature needed?
- **Provide examples**: How would users interact with this feature?
- **Consider scope**: Keep features focused and well-defined

## 🔄 Pull Request Process

### Before Submitting

1. **Create a focused branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding guidelines

3. **Test thoroughly**:
   - Development server starts correctly
   - No Python errors or warnings
   - UI works on desktop and mobile
   - Email functionality (if applicable)

4. **Update documentation** as needed

### PR Requirements

- **Clear title**: Describe what the PR does
- **Detailed description**: Explain the changes and reasoning
- **Link related issues**: Use "Fixes #123" or "Addresses #456"
- **Screenshots**: For UI changes
- **Testing notes**: How you tested the changes

### Review Process

- Maintainers will review PRs as time permits
- Feedback will be provided for improvements
- Once approved, maintainers will merge your PR
- Please be patient - this is a personal project maintained in spare time

## 🏗️ Development Environment

### Local Setup

```bash
# Clone your fork
git clone https://github.com/splittchen/splittchen.git
cd splittchen

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run development server
python app.py
```

### Docker Development

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access application at http://localhost:5000
```

### Database Operations

```bash
# Initialize database (first time - automatic on startup)
python app.py

# Manual database initialization if needed
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

## 📁 Project Structure

```
splittchen/
├── app/                    # Main application package
│   ├── __init__.py        # Application factory
│   ├── models.py          # Database models
│   ├── routes.py          # URL routes and views
│   ├── forms.py           # WTForms definitions
│   ├── utils.py           # Utility functions
│   ├── scheduler.py       # Background task scheduler
│   ├── currency.py        # Currency conversion service
│   └── templates/         # Jinja2 templates
├── instance/              # Instance-specific files (created by Docker)
├── app.py                 # Application entry point
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # Multi-service deployment
├── Dockerfile            # Container definition
└── .env.example          # Environment template
```

## 🎯 Areas for Contribution

### High Priority

- **Additional split types**: Implement EXACT and PERCENTAGE split methods (currently only EQUAL)
- **Mobile UX**: Improve responsive design and mobile interactions
- **Performance**: Optimize database queries and page load times
- **Accessibility**: Add ARIA labels and keyboard navigation
- **Tests**: Add comprehensive test suite

### Medium Priority

- **Currency improvements**: Add more currencies, better rate caching
- **Email templates**: Improve email design and accessibility
- **Group features**: Categories, tags, expense search/filtering
- **Export functionality**: CSV/PDF expense reports
- **Internationalization**: Multi-language support

### Documentation

- **Tutorial videos**: Screen recordings for common workflows
- **API documentation**: If we add an API in the future
- **Deployment guides**: More hosting platform options
- **Troubleshooting**: Common issues and solutions

## 🤝 Code of Conduct

### Our Standards

- **Be respectful**: Treat all contributors with respect
- **Be inclusive**: Welcome people of all backgrounds and skill levels
- **Be collaborative**: Work together constructively
- **Be patient**: This is a volunteer-driven project

### Unacceptable Behavior

- Harassment, discrimination, or inappropriate comments
- Personal attacks or inflammatory language
- Spam or off-topic contributions
- Violation of others' privacy

## 📄 License

By contributing to Splittchen, you agree that your contributions will be licensed under the project's MIT License with Commercial Use Restriction. See the [LICENSE](LICENSE) file for details.

**Important**: This project allows personal use only. Commercial use requires explicit permission from the maintainer.

## 📞 Getting Help

- **Issues**: For bugs and feature requests
- **Discussions**: For questions and general discussion
- **Email**: For sensitive security issues or licensing questions

## 🙏 Recognition

Contributors will be acknowledged in:

- GitHub contributors list
- Release notes for significant contributions
- Project documentation

Thank you for helping make Splittchen better! 🎉