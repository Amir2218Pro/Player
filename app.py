from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
import os
import json
import sqlite3
import subprocess
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import mimetypes
import base64
from datetime import datetime
import hashlib
from datetime import time

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Default admin credentials
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'

# Configuration
UPLOAD_FOLDER = 'static/videos'
THUMBNAILS_FOLDER = 'static/thumbnails'
SUBTITLES_FOLDER = 'static/subtitles'
DATABASE_FILE = 'xplayer.db'

# Extended list of supported media formats
ALLOWED_EXTENSIONS = {
    # Video formats
    'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'ogv',
    'm4v', 'mpg', 'mpeg', 'mp2', 'mpe', 'mpv', 'm2v', '3gp', '3g2',
    'mxf', 'roq', 'nsv', 'f4v', 'f4p', 'f4a', 'f4b', 'asf', 'rm',
    'rmvb', 'vob', 'ts', 'mts', 'm2ts', 'divx', 'xvid',
    # Audio formats
    'mp3', 'wav', 'flac', 'aac', 'oga', 'wma', 'm4a', 'opus',
    'aiff', 'au', 'ra', 'amr', 'ac3', 'dts', 'ape', 'mka'
}

SUBTITLE_EXTENSIONS = {'srt', 'vtt', 'ass', 'ssa'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAILS_FOLDER'] = THUMBNAILS_FOLDER
app.config['SUBTITLES_FOLDER'] = SUBTITLES_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure directories exist
for folder in [UPLOAD_FOLDER, THUMBNAILS_FOLDER, SUBTITLES_FOLDER]:
    os.makedirs(folder, exist_ok=True)

def init_database():
    """Initialize SQLite database for users and playlists"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            can_use_playlists BOOLEAN DEFAULT TRUE,
            can_download BOOLEAN DEFAULT TRUE,
            can_use_subtitles BOOLEAN DEFAULT TRUE,
            access_start_time TEXT DEFAULT '00:00',
            access_end_time TEXT DEFAULT '23:59',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Playlists table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            videos TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Video metadata table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            thumbnail_path TEXT,
            duration REAL,
            resolution TEXT,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create default admin user if not exists
    cursor.execute('SELECT id FROM users WHERE username = ?', (DEFAULT_ADMIN_USERNAME,))
    if not cursor.fetchone():
        admin_password_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, is_admin, can_use_playlists, can_download, can_use_subtitles)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (DEFAULT_ADMIN_USERNAME, admin_password_hash, 'admin@xplayer.com', True, True, True, True))
        print(f"✅ Default admin user created: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")
    
    conn.commit()
    conn.close()

def check_user_permissions(user_id, permission_type):
    """Check if user has specific permission"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute(f'SELECT {permission_type}, is_active FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return False
    
    return bool(result[0]) and bool(result[1])

def check_time_access(user_id):
    """Check if user can access during current time"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT access_start_time, access_end_time, is_active FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[2]:  # User not found or inactive
        return False
    
    start_time_str, end_time_str = result[0], result[1]
    
    try:
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        current_time = datetime.now().time()
        
        if start_time <= end_time:
            # Same day range
            return start_time <= current_time <= end_time
        else:
            # Overnight range (e.g., 22:00 to 06:00)
            return current_time >= start_time or current_time <= end_time
    except:
        return True  # If time parsing fails, allow access

def allowed_file(filename):
    """Check if file is allowed (video or audio)"""
    if not filename or '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS

def allowed_subtitle(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in SUBTITLE_EXTENSIONS

def is_video_file(filename):
    return is_video_file_detailed(filename)

def is_audio_file(filename):
    return is_audio_file_detailed(filename)

def get_file_type(filename):
    if is_video_file(filename):
        return 'video'
    elif is_audio_file(filename):
        return 'audio'
    else:
        return 'unknown'

def generate_thumbnail(video_path, thumbnail_path):
    """Generate thumbnail for video at 55 seconds using ffmpeg (if available)"""
    try:
        full_video_path = os.path.join(UPLOAD_FOLDER, video_path)
        
        if not os.path.exists(full_video_path):
            print(f"Video file not found: {full_video_path}")
            return create_placeholder_thumbnail(thumbnail_path)
        
        thumbnail_dir = os.path.dirname(thumbnail_path)
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        print(f"Generating thumbnail for: {full_video_path}")
        
        try:
            # Get video duration first
            duration_cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', full_video_path
            ]
            
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=15)
            
            if duration_result.returncode == 0:
                try:
                    duration = float(duration_result.stdout.strip())
                    print(f"Video duration: {duration} seconds")
                    
                    # Choose appropriate time for thumbnail (prefer 55 seconds)
                    if duration > 55:
                        seek_time = '00:00:55'
                    elif duration > 10:
                        seek_time = '00:00:10'
                    elif duration > 5:
                        seek_time = '00:00:05'
                    else:
                        seek_time = '00:00:01'
                except ValueError:
                    print("Could not parse duration, using default")
                    seek_time = '00:00:10'
            else:
                print("Could not get duration, using default seek time")
                seek_time = '00:00:10'
            
            print(f"Using seek time: {seek_time}")
            
            # FFmpeg command to extract frame at specified time
            cmd = [
                'ffmpeg', '-i', full_video_path,
                '-ss', seek_time,
                '-vframes', '1',
                '-q:v', '2',
                '-vf', 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
                '-y',
                thumbnail_path
            ]
            
            print(f"Running ffmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                print(f"Thumbnail generated successfully: {thumbnail_path}")
                return f"/static/thumbnails/{os.path.basename(thumbnail_path)}"
            else:
                print(f"FFmpeg failed with return code: {result.returncode}")
                print(f"FFmpeg stderr: {result.stderr}")
                
                # Try with a different seek time if first attempt failed
                if seek_time != '00:00:01':
                    print("Retrying with 1 second seek time")
                    cmd[3] = '00:00:01'
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0 and os.path.exists(thumbnail_path):
                        print("Thumbnail generated on retry")
                        return f"/static/thumbnails/{os.path.basename(thumbnail_path)}"
                
                return create_placeholder_thumbnail(thumbnail_path)
                
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"FFmpeg error: {e}")
            return create_placeholder_thumbnail(thumbnail_path)
            
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return create_placeholder_thumbnail(thumbnail_path)

def create_placeholder_thumbnail(thumbnail_path):
    """Create a simple placeholder thumbnail"""
    print("Creating placeholder thumbnail")
    try:
        # Create a simple SVG placeholder
        svg_content = '''
        <svg width="320" height="180" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#333"/>
            <text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="white" font-family="Arial" font-size="24">
                🎬
            </text>
        </svg>
        '''
        
        # Convert SVG to base64 data URL
        svg_b64 = base64.b64encode(svg_content.encode()).decode()
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception as e:
        print(f"Error creating placeholder: {e}")
        return None

def is_video_file_detailed(filename):
    """More comprehensive video file detection"""
    video_extensions = {
        'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'ogv',
        'm4v', 'mpg', 'mpeg', 'mp2', 'mpe', 'mpv', 'm2v', '3gp', '3g2',
        'mxf', 'roq', 'nsv', 'f4v', 'f4p', 'f4a', 'f4b', 'asf', 'rm',
        'rmvb', 'vob', 'ts', 'mts', 'm2ts', 'divx', 'xvid'
    }
    
    if not filename or '.' not in filename:
        return False
        
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in video_extensions

def is_audio_file_detailed(filename):
    """More comprehensive audio file detection"""
    audio_extensions = {
        'mp3', 'wav', 'flac', 'aac', 'ogg', 'oga', 'wma', 'm4a', 'opus',
        'aiff', 'au', 'ra', 'amr', 'ac3', 'dts', 'ape', 'mka'
    }
    
    if not filename or '.' not in filename:
        return False
        
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in audio_extensions

def get_video_duration(file_path):
    """Get video duration using ffprobe"""
    try:
        full_path = os.path.join(UPLOAD_FOLDER, file_path)
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', full_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            print(f"Duration for {file_path}: {duration} seconds")
            return duration
    except Exception as e:
        print(f"Error getting duration for {file_path}: {e}")
        pass
    return None

def get_video_metadata(file_path):
    """Get video metadata including thumbnail"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM video_metadata WHERE file_path = ?', (file_path,))
    metadata = cursor.fetchone()
    
    if not metadata:
        # Generate new metadata
        thumbnail_filename = hashlib.md5(file_path.encode()).hexdigest() + '.jpg'
        thumbnail_path = os.path.join(THUMBNAILS_FOLDER, thumbnail_filename)
        
        print(f"Processing metadata for: {file_path}")
        
        # Generate thumbnail
        thumbnail_url = generate_thumbnail(file_path, thumbnail_path)
        
        # Get file size and duration
        try:
            full_path = os.path.join(UPLOAD_FOLDER, file_path)
            file_size = os.path.getsize(full_path)
            duration = get_video_duration(file_path)
        except:
            file_size = 0
            duration = None
        
        print(f"Metadata - Size: {file_size}, Duration: {duration}, Thumbnail: {thumbnail_url}")
        
        # Insert metadata
        cursor.execute('''
            INSERT INTO video_metadata (file_path, thumbnail_path, file_size, duration)
            VALUES (?, ?, ?, ?)
        ''', (file_path, thumbnail_url, file_size, duration))
        
        conn.commit()
        metadata = (cursor.lastrowid, file_path, thumbnail_url, duration, None, file_size, datetime.now())
    
    conn.close()
    return metadata

def scan_directory_recursive(directory_path, base_path='', sort_by='name', sort_order='asc'):
    """Recursively scan directory for media files with metadata and sorting"""
    items = []
    
    try:
        if not os.path.exists(directory_path):
            return items
            
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            relative_path = os.path.join(base_path, item) if base_path else item
            
            if os.path.isdir(item_path):
                # It's a directory
                folder_info = {
                    'name': item,
                    'type': 'folder',
                    'path': relative_path,
                    'full_path': item_path,
                    'size': 0,
                    'modified': os.path.getmtime(item_path),
                    'children': scan_directory_recursive(item_path, relative_path, sort_by, sort_order)
                }
                items.append(folder_info)
            elif allowed_file(item):
                # It's a media file
                print(f"Found media file: {item}")
                file_size = os.path.getsize(item_path)
                file_modified = os.path.getmtime(item_path)
                metadata = get_video_metadata(relative_path)
                
                file_info = {
                    'name': item,
                    'type': get_file_type(item),
                    'path': relative_path,
                    'full_path': item_path,
                    'url': f'/static/videos/{relative_path.replace(os.sep, "/").replace(chr(92), "/")}',
                    'size': file_size,
                    'modified': file_modified,
                    'thumbnail': metadata[2] if metadata else None,
                    'duration': metadata[3] if metadata else None,
                    'resolution': metadata[4] if metadata else None
                }
                print(f"Added file info: {file_info['name']} - Type: {file_info['type']}")
                items.append(file_info)
            else:
                print(f"File not allowed: {item}")
    except PermissionError:
        print(f"Permission denied for directory: {directory_path}")
        pass
    except Exception as e:
        print(f"Error scanning directory {directory_path}: {e}")
    
    # Sort items
    return sort_items(items, sort_by, sort_order)

def sort_items(items, sort_by='name', sort_order='asc'):
    """Sort items based on criteria"""
    reverse = sort_order == 'desc'
    
    if sort_by == 'name':
        items.sort(key=lambda x: x['name'].lower(), reverse=reverse)
    elif sort_by == 'size':
        items.sort(key=lambda x: x.get('size', 0), reverse=reverse)
    elif sort_by == 'modified':
        items.sort(key=lambda x: x.get('modified', 0), reverse=reverse)
    elif sort_by == 'duration':
        items.sort(key=lambda x: x.get('duration', 0) or 0, reverse=reverse)
    elif sort_by == 'type':
        # Sort by type: folders first, then by file type
        items.sort(key=lambda x: (x['type'] != 'folder', x['type'], x['name'].lower()), reverse=reverse)
    
    return items

def search_files_recursive(directory_path, query, search_type='file', base_path=''):
    """Recursively search for files or folders matching query"""
    results = []
    query_lower = query.lower()
    
    try:
        if not os.path.exists(directory_path):
            return results
            
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            relative_path = os.path.join(base_path, item) if base_path else item
            
            if os.path.isdir(item_path):
                # Check if folder matches search (for folder search)
                if search_type == 'folder' and query_lower in item.lower():
                    folder_info = {
                        'name': item,
                        'type': 'folder',
                        'path': relative_path,
                        'full_path': item_path,
                        'folder': os.path.dirname(relative_path) if os.path.dirname(relative_path) else 'Root'
                    }
                    results.append(folder_info)
                
                # Search in subdirectory
                results.extend(search_files_recursive(item_path, query, search_type, relative_path))
                
            elif search_type == 'file' and allowed_file(item) and query_lower in item.lower():
                # File matches search query
                file_size = os.path.getsize(item_path)
                metadata = get_video_metadata(relative_path)
                
                file_info = {
                    'name': item,
                    'type': get_file_type(item),
                    'path': relative_path,
                    'full_path': item_path,
                    'url': f'/static/videos/{relative_path.replace(os.sep, "/").replace(chr(92), "/")}',
                    'size': file_size,
                    'folder': os.path.dirname(relative_path) if os.path.dirname(relative_path) else 'Root',
                    'thumbnail': metadata[2] if metadata else None
                }
                results.append(file_info)
    except PermissionError:
        pass
    
    return results

# Authentication routes
@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, password_hash, is_admin, can_use_playlists, can_download, 
               can_use_subtitles, access_start_time, access_end_time, is_active 
        FROM users WHERE username = ?
    ''', (username,))
    user = cursor.fetchone()
    
    if user and check_password_hash(user[1], password):
        # Check if user is active
        if not user[8]:
            conn.close()
            return jsonify({'error': 'Account is deactivated'}), 401
        
        # Check time access
        if not check_time_access(user[0]):
            conn.close()
            return jsonify({'error': 'Access denied at this time'}), 401
        
        session['user_id'] = user[0]
        session['username'] = username
        session['is_admin'] = bool(user[2])
        session['permissions'] = {
            'can_use_playlists': bool(user[3]),
            'can_download': bool(user[4]),
            'can_use_subtitles': bool(user[5])
        }
        conn.close()
        return jsonify({
            'success': True, 
            'message': 'Login successful',
            'is_admin': bool(user[2]),
            'permissions': session['permissions']
        })
    
    conn.close()
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400
    
    # Create user
    password_hash = generate_password_hash(password)
    cursor.execute('''
        INSERT INTO users (username, password_hash, email, is_admin, can_use_playlists, can_download, can_use_subtitles)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (username, password_hash, email, False, True, True, True))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    session['user_id'] = user_id
    session['username'] = username
    session['is_admin'] = False
    session['permissions'] = {
        'can_use_playlists': True,
        'can_download': True,
        'can_use_subtitles': True
    }
    
    return jsonify({'success': True, 'message': 'Registration successful'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# Admin routes
@app.route('/admin')
def admin_panel():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login_page'))
    return render_template('admin.html', username=session.get('username'))

@app.route('/api/admin/users')
def get_all_users():
    """Get all users (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, username, email, is_admin, can_use_playlists, can_download, 
               can_use_subtitles, access_start_time, access_end_time, is_active, created_at
        FROM users
        ORDER BY created_at DESC
    ''')
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'is_admin': bool(row[3]),
            'can_use_playlists': bool(row[4]),
            'can_download': bool(row[5]),
            'can_use_subtitles': bool(row[6]),
            'access_start_time': row[7],
            'access_end_time': row[8],
            'is_active': bool(row[9]),
            'created_at': row[10]
        })
    
    conn.close()
    return jsonify({'users': users})

@app.route('/api/admin/create-user', methods=['POST'])
def admin_create_user():
    """Create new user (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email', '')
    is_admin = data.get('is_admin', False)
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400
    
    # Create user
    password_hash = generate_password_hash(password)
    cursor.execute('''
        INSERT INTO users (username, password_hash, email, is_admin, can_use_playlists, can_download, can_use_subtitles)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (username, password_hash, email, is_admin, True, True, True))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'User created successfully'})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete user (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    # Prevent admin from deleting themselves
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Delete user's playlists first
    cursor.execute('DELETE FROM playlists WHERE user_id = ?', (user_id,))
    
    # Delete user
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'User deleted successfully'})

@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
def toggle_admin_status(user_id):
    """Toggle admin status (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    # Prevent admin from removing their own admin status
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot modify your own admin status'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Get current admin status
    cursor.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Toggle admin status
    new_admin_status = not bool(user[0])
    cursor.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_admin_status, user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True, 
        'message': f'User admin status {"enabled" if new_admin_status else "disabled"}',
        'is_admin': new_admin_status
    })

@app.route('/api/admin/users/<int:user_id>/permissions', methods=['POST'])
def update_user_permissions(user_id):
    """Update user permissions (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Update permissions
    cursor.execute('''
        UPDATE users SET 
            can_use_playlists = ?,
            can_download = ?,
            can_use_subtitles = ?,
            access_start_time = ?,
            access_end_time = ?,
            is_active = ?
        WHERE id = ?
    ''', (
        data.get('can_use_playlists', True),
        data.get('can_download', True),
        data.get('can_use_subtitles', True),
        data.get('access_start_time', '00:00'),
        data.get('access_end_time', '23:59'),
        data.get('is_active', True),
        user_id
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Permissions updated successfully'})

@app.route('/api/admin/stats')
def get_admin_stats():
    """Get system statistics (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Get user count
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Get active users count
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
    active_users = cursor.fetchone()[0]
    
    # Get admin count
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    total_admins = cursor.fetchone()[0]
    
    # Get playlist count
    cursor.execute('SELECT COUNT(*) FROM playlists')
    total_playlists = cursor.fetchone()[0]
    
    # Get video count
    cursor.execute('SELECT COUNT(*) FROM video_metadata')
    total_videos = cursor.fetchone()[0]
    
    # Get storage usage
    cursor.execute('SELECT SUM(file_size) FROM video_metadata')
    storage_used = cursor.fetchone()[0] or 0
    
    # Get recent activity (users created in last 7 days)
    cursor.execute('''
        SELECT COUNT(*) FROM users 
        WHERE created_at > datetime('now', '-7 days')
    ''')
    recent_users = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_users': total_users,
        'active_users': active_users,
        'total_admins': total_admins,
        'total_playlists': total_playlists,
        'total_videos': total_videos,
        'storage_used': storage_used,
        'recent_users': recent_users
    })

@app.route('/api/admin/system-info')
def get_system_info():
    """Get system information (admin only)"""
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        import psutil
        import platform
        
        # System info
        system_info = {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'used': psutil.disk_usage('/').used,
                'free': psutil.disk_usage('/').free,
                'percent': psutil.disk_usage('/').percent
            }
        }
        
        return jsonify({'system_info': system_info})
    except ImportError:
        return jsonify({'error': 'System monitoring not available'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Main routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    # Check time access
    if not check_time_access(session['user_id']):
        session.clear()
        return redirect(url_for('login_page'))
    
    return render_template('index.html', 
                         username=session.get('username'),
                         is_admin=session.get('is_admin', False),
                         permissions=session.get('permissions', {}))

@app.route('/api/user/permissions')
def get_user_permissions():
    """Get current user permissions"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    return jsonify({
        'permissions': session.get('permissions', {}),
        'is_admin': session.get('is_admin', False)
    })

@app.route('/api/browse')
def browse_files():
    """Browse files and folders with sorting"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        path = request.args.get('path', '')
        sort_by = request.args.get('sort', 'name')  # name, size, modified, duration, type
        sort_order = request.args.get('order', 'asc')  # asc, desc
        
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], path) if path else app.config['UPLOAD_FOLDER']
        
        # Security check
        if not os.path.abspath(full_path).startswith(os.path.abspath(app.config['UPLOAD_FOLDER'])):
            return jsonify({'error': 'Invalid path'}), 400
        
        items = scan_directory_recursive(full_path, path, sort_by, sort_order)
        
        return jsonify({
            'items': items,
            'current_path': path,
            'parent_path': os.path.dirname(path) if path else None,
            'sort_by': sort_by,
            'sort_order': sort_order
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search')
def search_files():
    """Search files or folders recursively"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        query = request.args.get('q', '').strip()
        search_type = request.args.get('type', 'file')  # 'file' or 'folder'
        
        if not query:
            return jsonify({'results': []})
        
        results = search_files_recursive(app.config['UPLOAD_FOLDER'], query, search_type)
        
        return jsonify({
            'results': results,
            'query': query,
            'search_type': search_type,
            'count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/videos')
def get_videos():
    """Get list of all videos recursively"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        all_items = scan_directory_recursive(app.config['UPLOAD_FOLDER'])
        videos = []
        
        def extract_videos(items):
            for item in items:
                if item['type'] == 'video':
                    videos.append(item)
                elif item['type'] == 'folder':
                    extract_videos(item['children'])
        
        extract_videos(all_items)
        
        return jsonify({'videos': videos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Playlist routes
@app.route('/api/playlists')
def get_playlists():
    """Get user's playlists"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check playlist permission
    if not check_user_permissions(session['user_id'], 'can_use_playlists'):
        return jsonify({'error': 'Playlist access denied'}), 403
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, description, videos, created_at, updated_at
        FROM playlists WHERE user_id = ?
        ORDER BY updated_at DESC
    ''', (session['user_id'],))
    
    playlists = []
    for row in cursor.fetchall():
        playlist = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'videos': json.loads(row[3]) if row[3] else [],
            'created_at': row[4],
            'updated_at': row[5]
        }
        playlists.append(playlist)
    
    conn.close()
    return jsonify({'playlists': playlists})

@app.route('/api/playlists', methods=['POST'])
def create_playlist():
    """Create new playlist"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check playlist permission
    if not check_user_permissions(session['user_id'], 'can_use_playlists'):
        return jsonify({'error': 'Playlist access denied'}), 403
    
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    
    if not name:
        return jsonify({'error': 'Playlist name required'}), 400
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO playlists (user_id, name, description, videos)
        VALUES (?, ?, ?, ?)
    ''', (session['user_id'], name, description, '[]'))
    
    playlist_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'playlist_id': playlist_id})

@app.route('/api/playlists/<int:playlist_id>', methods=['PUT'])
def update_playlist(playlist_id):
    """Update playlist"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check playlist permission
    if not check_user_permissions(session['user_id'], 'can_use_playlists'):
        return jsonify({'error': 'Playlist access denied'}), 403
    
    data = request.get_json()
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Handle different update types
    if 'videos' in data:
        # Update video list
        videos = data.get('videos', [])
        cursor.execute('''
            UPDATE playlists SET videos = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        ''', (json.dumps(videos), playlist_id, session['user_id']))
    
    if 'name' in data or 'description' in data:
        # Update playlist info
        name = data.get('name')
        description = data.get('description')
        
        if name:
            cursor.execute('''
                UPDATE playlists SET name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (name, playlist_id, session['user_id']))
        
        if description is not None:
            cursor.execute('''
                UPDATE playlists SET description = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (description, playlist_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/playlists/<int:playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    """Delete playlist"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check playlist permission
    if not check_user_permissions(session['user_id'], 'can_use_playlists'):
        return jsonify({'error': 'Playlist access denied'}), 403
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM playlists WHERE id = ? AND user_id = ?', 
                  (playlist_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/playlists/<int:playlist_id>/play')
def get_playlist_for_playing(playlist_id):
    """Get playlist with full video details for playing"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    if not check_user_permissions(session['user_id'], 'can_use_playlists'):
        return jsonify({'error': 'Playlist access denied'}), 403
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, description, videos
        FROM playlists WHERE id = ? AND user_id = ?
    ''', (playlist_id, session['user_id']))
    
    playlist = cursor.fetchone()
    conn.close()
    
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404
    
    video_paths = json.loads(playlist[3]) if playlist[3] else []
    detailed_videos = []
    
    for video_path in video_paths:
        try:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], video_path)
            if os.path.exists(full_path):
                file_size = os.path.getsize(full_path)
                metadata = get_video_metadata(video_path)
                
                video_info = {
                    'name': os.path.basename(video_path),
                    'path': video_path,
                    'url': f'/static/videos/{video_path.replace(os.sep, "/").replace(chr(92), "/")}',
                    'size': file_size,
                    'thumbnail': metadata[2] if metadata else None,
                    'duration': metadata[3] if metadata else None,
                    'type': get_file_type(video_path)
                }
                detailed_videos.append(video_info)
        except:
            continue
    
    return jsonify({
        'playlist': {
            'id': playlist[0],
            'name': playlist[1],
            'description': playlist[2],
            'videos': detailed_videos
        }
    })

# Subtitle routes
@app.route('/api/subtitles/<path:video_path>')
def get_subtitles(video_path):
    """Get available subtitles for a video"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check subtitle permission
    if not check_user_permissions(session['user_id'], 'can_use_subtitles'):
        return jsonify({'error': 'Subtitle access denied'}), 403
    
    # Look for subtitle files with same name as video
    video_name = os.path.splitext(video_path)[0]
    subtitles = []
    
    # Check in subtitles folder
    subtitle_dir = os.path.join(app.config['SUBTITLES_FOLDER'])
    if os.path.exists(subtitle_dir):
        for file in os.listdir(subtitle_dir):
            if file.startswith(os.path.basename(video_name)) and allowed_subtitle(file):
                subtitles.append({
                    'name': file,
                    'url': f'/static/subtitles/{file}',
                    'language': 'en'  # Default, could be parsed from filename
                })
    
    return jsonify({'subtitles': subtitles})

@app.route('/api/download/<path:video_path>')
def download_video(video_path):
    """Download video file"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check download permission
    if not check_user_permissions(session['user_id'], 'can_download'):
        return jsonify({'error': 'Download access denied'}), 403
    
    try:
        # Normalize path separators
        normalized_path = video_path.replace('/', os.sep).replace('\\', os.sep)
        print(f"Download request for: {normalized_path}")
        
        # Check if file exists
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], normalized_path)
        if not os.path.exists(full_path):
            print(f"File not found: {full_path}")
            return jsonify({'error': 'File not found'}), 404
            
        return send_from_directory(app.config['UPLOAD_FOLDER'], normalized_path, as_attachment=True)
    except FileNotFoundError:
        print(f"FileNotFoundError for: {video_path}")
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500

# Add route to serve video files directly
@app.route('/static/videos/<path:filename>')
def serve_video(filename):
    """Serve video files with proper headers"""
    try:
        # Normalize path separators
        normalized_path = filename.replace('/', os.sep).replace('\\', os.sep)
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], normalized_path)
        
        print(f"Serving video: {normalized_path}")
        print(f"Full path: {full_path}")
        print(f"File exists: {os.path.exists(full_path)}")
        
        if not os.path.exists(full_path):
            print(f"Video file not found: {full_path}")
            return "File not found", 404
        
        # Get file directory and name
        directory = os.path.dirname(full_path)
        file_name = os.path.basename(full_path)
        
        return send_from_directory(directory, file_name)
    except Exception as e:
        print(f"Error serving video {filename}: {e}")
        return "Error serving file", 500
if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)