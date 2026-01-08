from flask import Flask, render_template, session, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
from functools import wraps
import paramiko
import os
import secrets
import threading
import time
import select

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)

# Set your password here or use environment variable
ACCESS_PASSWORD = os.environ.get('TERMINAL_PASSWORD', 'admin123')

# Store SSH connections per session
ssh_clients = {}
ssh_channels = {}

def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_ssh_client(session_id):
    """Get or create SSH client for session"""
    if session_id not in ssh_clients:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect to localhost
        # Try to use current user's credentials
        username = os.environ.get('USER', os.getlogin())
        
        try:
            # Try SSH agent first
            client.connect('localhost', username=username, look_for_keys=True, allow_agent=True)
        except:
            try:
                # Try default SSH key
                key_path = os.path.expanduser('~/.ssh/id_rsa')
                if os.path.exists(key_path):
                    client.connect('localhost', username=username, key_filename=key_path)
                else:
                    # If no key, will need password - this will be handled by the connection attempt
                    raise Exception("No SSH keys found. Please set up SSH key authentication.")
            except Exception as e:
                raise Exception(f"Failed to connect via SSH: {str(e)}")
        
        ssh_clients[session_id] = client
    
    return ssh_clients[session_id]

def read_channel_output(channel, session_id):
    """Read output from SSH channel and emit to client"""
    try:
        while not channel.closed:
            # Use select for non-blocking I/O with timeout
            ready, _, _ = select.select([channel], [], [], 0.1)
            
            if ready:
                # Try to read stdout
                if channel.recv_ready():
                    try:
                        data = channel.recv(4096).decode('utf-8', errors='replace')
                        if data:
                            socketio.emit('output', {'data': data}, room=session_id)
                    except:
                        pass
                
                # Try to read stderr
                if channel.recv_stderr_ready():
                    try:
                        data = channel.recv_stderr(4096).decode('utf-8', errors='replace')
                        if data:
                            socketio.emit('output', {'data': data}, room=session_id)
                    except:
                        pass
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.01)
            
    except Exception as e:
        if not channel.closed:
            socketio.emit('output', {'data': f'\r\nError reading output: {str(e)}\r\n'}, room=session_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ACCESS_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Generate unique session ID
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)
    return render_template('terminal.html')

@socketio.on('connect')
def handle_connect():
    # Check authentication
    if not session.get('authenticated'):
        return False
    
    session_id = session.get('session_id')
    if not session_id:
        session['session_id'] = secrets.token_hex(16)
        session_id = session['session_id']
    
    # Join a room with the session ID
    join_room(session_id)
    
    try:
        # Get SSH client
        client = get_ssh_client(session_id)
        
        # Create interactive shell channel with proper terminal settings
        channel = client.invoke_shell(
            term='xterm-256color',  # Enable 256 color support
            width=120, 
            height=40,
            environment={
                'TERM': 'xterm-256color',
                'COLORTERM': 'truecolor',
                'LANG': 'en_US.UTF-8',
                'LC_ALL': 'en_US.UTF-8'
            }
        )
        ssh_channels[session_id] = channel
        
        # Start thread to read output
        thread = threading.Thread(target=read_channel_output, args=(channel, session_id))
        thread.daemon = True
        thread.start()
        
        emit('connected', {'status': 'success'})
    except Exception as e:
        emit('connected', {'status': 'error', 'message': str(e)})

@socketio.on('disconnect')
def handle_disconnect():
    session_id = session.get('session_id')
    if session_id:
        # Close channel and client
        if session_id in ssh_channels:
            try:
                ssh_channels[session_id].close()
            except:
                pass
            del ssh_channels[session_id]
        
        if session_id in ssh_clients:
            try:
                ssh_clients[session_id].close()
            except:
                pass
            del ssh_clients[session_id]

@socketio.on('input')
def handle_input(data):
    session_id = session.get('session_id')
    if session_id and session_id in ssh_channels:
        channel = ssh_channels[session_id]
        try:
            command = data.get('data', '')
            channel.send(command)
        except Exception as e:
            emit('output', {'data': f'\r\nError sending input: {str(e)}\r\n'})

@socketio.on('resize')
def handle_resize(data):
    session_id = session.get('session_id')
    if session_id and session_id in ssh_channels:
        channel = ssh_channels[session_id]
        try:
            width = data.get('width', 120)
            height = data.get('height', 40)
            channel.resize_pty(width=width, height=height)
        except Exception as e:
            pass

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
