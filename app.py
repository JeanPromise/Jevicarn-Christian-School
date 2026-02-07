#!/usr/bin/env python3
"""
app.py - Jevicarn site with one-time admin registration then login using hithere.db
Admin dashboard now includes gallery management controls in the single admin.html template.
Improved safe deletion of uploaded images (works on hosting where static/uploads is writable).
"""
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, session, jsonify, send_file
)
import os
import sqlite3
from threading import Thread
import time
import requests
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import csv
import io

# --- CONFIG ---
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret")
# uploads directory inside static
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
CONTACTS_DB = 'contacts.db'   # site DB (messages + gallery)
ADMIN_DB = 'hithere.db'       # admins DB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff'}

# --- DB helpers & initialization ---
def get_conn(db_file):
    return sqlite3.connect(db_file)

def init_contacts_db():
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        text TEXT,
        filename TEXT,
        seen INTEGER DEFAULT 0,
        location TEXT,
        platform TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS gallery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        caption TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def init_admin_db():
    conn = get_conn(ADMIN_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def admin_count():
    conn = get_conn(ADMIN_DB)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM admins')
    n = c.fetchone()[0]
    conn.close()
    return n

def create_admin(username, password):
    pwd_hash = generate_password_hash(password)
    conn = get_conn(ADMIN_DB)
    c = conn.cursor()
    c.execute('INSERT INTO admins (username, password_hash) VALUES (?, ?)', (username, pwd_hash))
    conn.commit()
    conn.close()

def get_admin_by_username(username):
    conn = get_conn(ADMIN_DB)
    c = conn.cursor()
    c.execute('SELECT id, username, password_hash FROM admins WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    return row

def verify_admin_credentials(username, password):
    row = get_admin_by_username(username)
    if not row:
        return False
    _, db_user, db_hash = row
    return check_password_hash(db_hash, password)

# init DBs
init_contacts_db()
init_admin_db()

# auto create admin from env if none exists
if admin_count() == 0:
    env_user = os.getenv('ADMIN_USER')
    env_pass = os.getenv('ADMIN_PASS')
    if env_user and env_pass:
        create_admin(env_user, env_pass)
        print(f"[INIT] Admin created from env: {env_user}")

# --- helpers: admin protection ---
def require_admin():
    return bool(session.get('admin_logged_in'))

# --- Public site routes ---
@app.route('/')
@app.route('/home')
@app.route('/index.html')
def home():
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT filename FROM gallery ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    if rows:
        images = [f'uploads/{r[0]}' for r in rows]
    else:
        images = []
        if os.path.exists(UPLOAD_FOLDER):
            images = [f'uploads/{img}' for img in os.listdir(UPLOAD_FOLDER)
                      if Path(img).suffix.lower() in ALLOWED_IMG_EXTS]
    seo_keywords = (
        "Jevicarn Christian School, Day and Night Daycare, Kindergarten in Ruiru, "
        "Preschool in Kiambu, Childcare, Early Learning Centre, Babycare, "
        "Christian Education Kenya, Safe learning for children, Nursery School Ruiru"
    )
    return render_template(
        'home.html',
        images=images,
        title='Jevicarn Christian School | Day & Night Daycare Ruiru Kiambu',
        description='Join Jevicarn Christian Kindergarten & Daycare in Ruiru, Kiambu. Offering day and night care, nurturing learning, and Christian values for your child.',
        keywords=seo_keywords,
        location='Ebenezer, Ruiru – Kiambu County'
    )

@app.route('/gallery')
def gallery():
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT filename FROM gallery ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    if rows:
        images = [f'uploads/{r[0]}' for r in rows]
    else:
        images = [f'gallery/{img}' for img in os.listdir(os.path.join(app.static_folder, 'gallery'))
                  if Path(img).suffix.lower() in ALLOWED_IMG_EXTS] \
                 if os.path.exists(os.path.join(app.static_folder, 'gallery')) else []
    return render_template('gallery.html', images=images)

@app.route("/programs")
def programs():
    return render_template("programs.html", title="Programs", description="Programs offered at Jevicarn Christian Kindergarten & School", keywords="daycare, kindergarten, primary school, nightcare, Jevicarn, Juja")

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        file = request.files.get('file')
        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
        if text or filename:
            c.execute('INSERT INTO messages (sender, text, filename) VALUES (?, ?, ?)',
                      ('user', text, filename))
            conn.commit()
        conn.close()
        return redirect(url_for('contact'))
    c.execute('SELECT sender, text, filename, seen, timestamp FROM messages ORDER BY id ASC')
    messages_list = [{'sender': row[0], 'text': row[1], 'filename': row[2], 'seen': bool(row[3]), 'timestamp': row[4]} for row in c.fetchall()]
    conn.close()
    return render_template('contact.html', messages_list=messages_list)

# serve uploaded images from static/uploads
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # send_from_directory will take care of safe path handling
    uploads_dir = os.path.join(app.static_folder, 'uploads')
    return send_from_directory(uploads_dir, filename)

@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong", 200

# --- ADMIN / AUTH ROUTES ---
@app.route('/admin', methods=['GET'])
def admin():
    num = admin_count()
    logged_in = session.get('admin_logged_in', False)

    if num == 0:
        return render_template('admin.html', register_mode=True, logged_in=False)

    if not logged_in:
        return render_template('admin.html', logged_in=False)

    # prepare dashboard + gallery items
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('PRAGMA table_info(messages)')
    cols = [col[1] for col in c.fetchall()]
    for missing in ['receiver', 'location', 'platform']:
        if missing not in cols:
            try:
                c.execute(f'ALTER TABLE messages ADD COLUMN {missing} TEXT;')
            except Exception:
                pass

    c.execute('SELECT COUNT(*) FROM messages')
    total_msgs = c.fetchone()[0] or 0

    c.execute('SELECT COUNT(DISTINCT sender) FROM messages WHERE sender != "admin"')
    total_users = c.fetchone()[0] or 0

    c.execute('SELECT location, COUNT(*) FROM messages WHERE location IS NOT NULL GROUP BY location')
    location_data = c.fetchall()

    c.execute('SELECT platform, COUNT(*) FROM messages WHERE platform IS NOT NULL GROUP BY platform')
    platform_data = c.fetchall()

    c.execute('SELECT sender, COUNT(*) as count FROM messages WHERE sender != "admin" GROUP BY sender ORDER BY count DESC LIMIT 5')
    top_senders = c.fetchall()

    c.execute('SELECT sender, platform, location, timestamp, text FROM messages ORDER BY id DESC LIMIT 10')
    recent = c.fetchall()
    visitors = []
    for r in recent:
        visitors.append({
            'name': r[0],
            'platform': r[1] or 'Unknown',
            'location': r[2] or 'Unknown',
            'timestamp': r[3],
            'text': r[4]
        })

    # gallery items
    c.execute('SELECT id, filename, caption, created_at FROM gallery ORDER BY created_at DESC')
    gallery_rows = c.fetchall()
    gallery_items = [{'id': row[0], 'filename': row[1], 'caption': row[2], 'created_at': row[3]} for row in gallery_rows]

    conn.close()

    locations = [row[0] for row in location_data if row[0]]
    location_counts = [row[1] for row in location_data if row[0]]
    platforms = [row[0] for row in platform_data if row[0]]
    platform_counts = [row[1] for row in platform_data if row[0]]

    return render_template(
        'admin.html',
        logged_in=True,
        total_msgs=total_msgs,
        total_users=total_users,
        top_senders=top_senders,
        locations=locations,
        location_counts=location_counts,
        platforms=platforms,
        platform_counts=platform_counts,
        visitors=visitors,
        gallery_items=gallery_items
    )

@app.route('/!0pl', methods=['GET'])
def admin_alias():
    return admin()

@app.route('/admin/register', methods=['POST'])
def admin_register():
    if admin_count() > 0:
        flash("Registration not allowed. An admin already exists.", "error")
        return redirect(url_for('admin'))

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    password2 = request.form.get('password2', '').strip()

    if not username or not password:
        flash("Provide username and password", "error")
        return redirect(url_for('admin'))

    if password != password2:
        flash("Passwords do not match", "error")
        return redirect(url_for('admin'))

    try:
        create_admin(username, password)
    except sqlite3.IntegrityError:
        flash("Username already exists", "error")
        return redirect(url_for('admin'))

    session['admin_logged_in'] = True
    session['admin_user'] = username
    flash("Admin account created and logged in", "success")
    return redirect(url_for('admin'))

@app.route('/admin/login', methods=['POST'])
def admin_login():
    if admin_count() == 0:
        flash("No admin exists. Please register first.", "error")
        return redirect(url_for('admin'))

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        flash("Enter username and password", "error")
        return redirect(url_for('admin'))

    if verify_admin_credentials(username, password):
        session['admin_logged_in'] = True
        session['admin_user'] = username
        flash("Logged in successfully", "success")
        return redirect(url_for('admin'))
    else:
        flash("Invalid credentials", "error")
        return redirect(url_for('admin'))

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_user', None)
    flash("Logged out", "info")
    return redirect(url_for('admin'))

# --- ADMIN: gallery upload/delete (called from admin.html) ---
@app.route('/admin/gallery/upload', methods=['POST'])
def admin_gallery_upload():
    if not require_admin():
        flash("Please log in to upload images", "error")
        return redirect(url_for('admin'))

    file = request.files.get('file')
    caption = request.form.get('caption', '').strip()
    if not file or file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for('admin'))

    filename_orig = secure_filename(file.filename)
    ext = Path(filename_orig).suffix.lower()
    if ext not in ALLOWED_IMG_EXTS:
        flash("Unsupported image type", "error")
        return redirect(url_for('admin'))

    unique = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, unique)
    file.save(save_path)

    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('INSERT INTO gallery (filename, caption) VALUES (?, ?)', (unique, caption))
    conn.commit()
    conn.close()

    flash("Image uploaded", "success")
    return redirect(url_for('admin'))

@app.route('/admin/gallery/replace_ajax', methods=['POST'])
def admin_gallery_replace_ajax():
    if not require_admin():
        return jsonify({'success': False, 'error': 'not_logged_in'}), 401

    item_id = request.form.get('id')
    file = request.files.get('file')
    if not item_id or not file or file.filename == '':
        return jsonify({'success': False, 'error': 'missing_params'}), 400

    filename_orig = secure_filename(file.filename)
    ext = Path(filename_orig).suffix.lower()
    if ext not in ALLOWED_IMG_EXTS:
        return jsonify({'success': False, 'error': 'bad_type'}), 400

    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT filename FROM gallery WHERE id = ?', (item_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'not_found'}), 404

    old_filename = row[0]
    # save new file
    new_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, new_name)
    file.save(save_path)

    # delete old file safely
    uploads_dir = os.path.abspath(UPLOAD_FOLDER)
    old_path = os.path.abspath(os.path.join(uploads_dir, old_filename))
    try:
        if old_path.startswith(uploads_dir) and os.path.exists(old_path):
            os.remove(old_path)
    except Exception as e:
        print("Warning deleting old file:", e)

    # update DB
    c.execute('UPDATE gallery SET filename = ? WHERE id = ?', (new_name, item_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': item_id, 'filename': new_name})

@app.route('/admin/gallery/delete', methods=['POST'])
def admin_gallery_delete():
    """
    Traditional form POST (non-AJAX) delete. Keeps original behavior but with safer path checks.
    """
    if not require_admin():
        flash("Please log in to delete images", "error")
        return redirect(url_for('admin'))

    item_id = request.form.get('id')
    if not item_id:
        flash("Missing image id", "error")
        return redirect(url_for('admin'))

    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT filename FROM gallery WHERE id = ?', (item_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash("Image not found", "error")
        return redirect(url_for('admin'))

    filename = row[0]
    # safe removal: ensure the path is inside UPLOAD_FOLDER
    uploads_dir = os.path.abspath(UPLOAD_FOLDER)
    file_path = os.path.abspath(os.path.join(uploads_dir, filename))
    try:
        if file_path.startswith(uploads_dir) and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print("Warning: failed to remove file:", e)

    c.execute('DELETE FROM gallery WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

    flash("Image deleted", "success")
    return redirect(url_for('admin'))

@app.route('/admin/gallery/delete_ajax', methods=['POST'])
def admin_gallery_delete_ajax():
    """
    AJAX delete endpoint returning JSON. Body should be JSON: {"id": <id>}
    """
    if not require_admin():
        return jsonify({'success': False, 'error': 'not_logged_in'}), 401

    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'error': 'missing_id'}), 400

    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT filename FROM gallery WHERE id = ?', (item_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'not_found'}), 404

    filename = row[0]
    uploads_dir = os.path.abspath(UPLOAD_FOLDER)
    file_path = os.path.abspath(os.path.join(uploads_dir, filename))
    try:
        if file_path.startswith(uploads_dir) and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print("Warning: failed to remove file:", e)

    c.execute('DELETE FROM gallery WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': item_id})

# --- ADMIN: messages delete/export ---
@app.route('/admin/messages/delete', methods=['POST'])
def admin_message_delete():
    if not require_admin():
        flash("Please log in to manage messages", "error")
        return redirect(url_for('admin'))
    msg_id = request.form.get('id')
    if not msg_id:
        flash("Missing message id", "error")
        return redirect(url_for('admin'))
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()
    flash("Message deleted", "success")
    return redirect(url_for('admin'))

@app.route('/admin/messages/export', methods=['GET'])
def admin_messages_export():
    if not require_admin():
        flash("Please log in to export messages", "error")
        return redirect(url_for('admin'))
    conn = get_conn(CONTACTS_DB)
    c = conn.cursor()
    c.execute('SELECT id, sender, text, filename, location, platform, timestamp FROM messages ORDER BY id ASC')
    rows = c.fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['id','sender','text','filename','location','platform','timestamp'])
    cw.writerows(rows)
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, download_name='messages_export.csv', as_attachment=True)

# --- KEEP-ALIVE thread ---
def keep_alive():
    url = os.getenv('KEEP_ALIVE_URL', 'https://jevicarn-christian-school.onrender.com')
    while True:
        try:
            requests.get(f"{url}/keepalive-ping", timeout=10)
        except Exception:
            pass
        time.sleep(25)

# --- MAIN ---
if __name__ == '__main__':
    if os.getenv('ENABLE_KEEP_ALIVE', '0') == '1':
        Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
