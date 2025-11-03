from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
import sqlite3
from threading import Thread
import time
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# --- PATHS ---
UPLOAD_FOLDER = os.path.join('static', 'uploads')
DB_FILE = 'contacts.db'   # kept same as your project
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DATABASE SETUP ---
def init_db():
    """Create visitors table (and keep a messages table if templates expect it)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # visitors table for analytics
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            source TEXT,
            page TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # optional messages table (kept for compatibility if any template uses it)
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            text TEXT,
            filename TEXT,
            seen INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# --- VISITOR LOGGING ---
def log_visit(source=None):
    """Record a visitor row. Use ?from=facebook etc. or pass source argument."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        page = request.path
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        ref = source or request.args.get('from', 'direct')
        c.execute('INSERT INTO visitors (ip, source, page) VALUES (?, ?, ?)', (ip, ref, page))
        conn.commit()
        conn.close()
    except Exception as e:
        # don't crash the app for logging issues
        print(f"⚠️ log_visit error: {e}")

# --- HOME PAGE ---
@app.route('/')
@app.route('/home')
@app.route('/index.html')
def home():
    log_visit()
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

# --- GALLERY PAGE ---
@app.route('/gallery')
def gallery():
    log_visit()
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

# --- PROGRAMS PAGE ---
@app.route("/programs")
def programs():
    log_visit()
    return render_template("programs.html",
                           title="Programs",
                           description="Programs offered at Jevicarn Christian Kindergarten & School",
                           keywords="daycare, kindergarten, primary school, nightcare, Jevicarn, Juja")

# --- CONTACT PAGE (simple buttons; no chat POST) ---
@app.route('/contact')
def contact():
    log_visit()
    # Keep a contact.html that shows Call / SMS / WhatsApp buttons (no form submission)
    return render_template('contact.html')

# --- ADMIN ANALYTICS DASHBOARD ---
@app.route('/admin')
def admin():
    auth = request.args.get('auth')
    if auth != os.getenv('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # total visits
    c.execute('SELECT COUNT(*) FROM visitors')
    total_visits = c.fetchone()[0]

    # top sources
    c.execute('SELECT source, COUNT(*) as count FROM visitors GROUP BY source ORDER BY count DESC LIMIT 10')
    sources = c.fetchall()

    # top pages
    c.execute('SELECT page, COUNT(*) as count FROM visitors GROUP BY page ORDER BY count DESC LIMIT 10')
    pages = c.fetchall()

    # recent visitors
    c.execute('SELECT ip, source, page, timestamp FROM visitors ORDER BY id DESC LIMIT 50')
    recent = c.fetchall()

    conn.close()

    return render_template('admin.html',
                           total_visits=total_visits,
                           sources=sources,
                           pages=pages,
                           recent=recent)

# --- FILE DOWNLOAD / VIEW ROUTE ---
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

# --- KEEP-ALIVE ENDPOINT ---
@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong"

# --- KEEP-ALIVE THREAD (prevents Render/Fly.io sleeping) ---
def keep_alive():
    url = os.getenv('KEEP_ALIVE_URL')
    if not url:
        print("⚠️ No KEEP_ALIVE_URL set; skipping keep-alive thread.")
        return

    print("🟢 Keep-alive service started, pinging every 25 seconds.")
    while True:
        try:
            requests.get(url + '/keepalive-ping', timeout=10)
            print("✅ Ping sent successfully.")
        except Exception as e:
            print(f"⚠️ Keep-alive error: {e}")
        time.sleep(25)

# --- MAIN APP ENTRY ---
if __name__ == '__main__':
    init_db()
    if os.getenv('ENABLE_KEEP_ALIVE', '1') == '1':
        Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
