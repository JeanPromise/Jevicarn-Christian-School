#!/usr/bin/env python3
"""
app.py - Jevicarn site with admin auth using hithere.db

Creates hithere.db and an `admins` table on first run.
Default admin user created if none exists:
  - username: admin
  - password: admin123

You can override default credentials by setting environment variables:
  ADMIN_USER and ADMIN_PASS

Uses werkzeug.security for password hashing.
"""
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, session, jsonify
)
import os
import sqlite3
from threading import Thread
import time
import requests
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIG ---
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret")
UPLOAD_FOLDER = os.path.join('static', 'uploads')
CONTACTS_DB = 'contacts.db'   # existing site DB for messages, contacts
ADMIN_DB = 'hithere.db'       # new DB to store admin credentials
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DB INITIALIZATION ---
def init_contacts_db():
    conn = sqlite3.connect(CONTACTS_DB)
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
    # Also ensure the older contacts table exists for contact form
    c.execute('CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT)')
    conn.commit()
    conn.close()

def init_admin_db():
    """Create hithere.db and a default admin if none exists."""
    conn = sqlite3.connect(ADMIN_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # insert default admin if none
    c.execute('SELECT COUNT(*) FROM admins')
    if c.fetchone()[0] == 0:
        admin_user = os.getenv('ADMIN_USER', 'admin')
        admin_pass = os.getenv('ADMIN_PASS', 'admin123')
        pwd_hash = generate_password_hash(admin_pass)
        c.execute('INSERT INTO admins (username, password_hash) VALUES (?, ?)', (admin_user, pwd_hash))
        conn.commit()
        print(f"[INIT] Created default admin -> user: {admin_user} (change it ASAP)")
    conn.close()

# run initializers
init_contacts_db()
init_admin_db()

# --- ROUTES: PUBLIC SITE ---
@app.route('/')
@app.route('/home')
@app.route('/index.html')
def home():
    images = []
    if os.path.exists(UPLOAD_FOLDER):
        images = [img for img in os.listdir(UPLOAD_FOLDER)
                  if img.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]

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
    image_folder = os.path.join(app.static_folder, 'gallery')
    images = []
    if os.path.exists(image_folder):
        images = [f'gallery/{img}' for img in os.listdir(image_folder)
                  if img.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]

    return render_template(
        'gallery.html',
        images=images,
        title='Our Gallery | Jevicarn Christian Daycare & School'
    )

@app.route("/programs")
def programs():
    return render_template("programs.html", title="Programs", description="Programs offered at Jevicarn Christian Kindergarten & School", keywords="daycare, kindergarten, primary school, nightcare, Jevicarn, Juja")

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    conn = sqlite3.connect(CONTACTS_DB)
    c = conn.cursor()
    # messages table created in init_contacts_db()

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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong", 200

# --- ADMIN AUTH HELPERS ---
def get_admin_by_username(username):
    conn = sqlite3.connect(ADMIN_DB)
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

# --- ADMIN ROUTES ---
@app.route('/admin', methods=['GET'])
def admin():
    """
    If admin_logged_in in session -> show dashboard
    Otherwise -> show login form (same template)
    """
    logged_in = session.get('admin_logged_in', False)
    if not logged_in:
        # show login form inside admin.html
        return render_template('admin.html', logged_in=False)

    # prepare dashboard data from contacts DB
    conn = sqlite3.connect(CONTACTS_DB)
    c = conn.cursor()
    # ensure columns present
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

    # recent visitors: pick last 10 messages
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
        visitors=visitors
    )

@app.route('/admin/login', methods=['POST'])
def admin_login():
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

# --- KEEP-ALIVE THREAD (optional) ---
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
