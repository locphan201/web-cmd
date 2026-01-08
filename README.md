# web-cmd

A web-based terminal application with password protection.

## Features

- Web-based SSH terminal
- Password authentication
- Real-time terminal interaction
- Session management

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access the terminal at: `http://localhost:5000`

## Configuration

### Setting a Custom Password

By default, the password is `admin123`. You can change it in two ways:

1. **Environment Variable** (recommended):
```bash
export TERMINAL_PASSWORD="your_secure_password"
python app.py
```

2. **Edit the code**: Change the `ACCESS_PASSWORD` variable in `app.py`

## Security Note

For production use, make sure to:
- Use a strong password
- Enable HTTPS
- Consider additional security measures like rate limiting
