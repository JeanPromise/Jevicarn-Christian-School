from flask import Flask, render_template, request, redirect, url_for, flash
from flask import send_from_directory
import os
import sqlite3
from threading import Thread
import time
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# --- PATHS ---
UPLOAD_FOLDER = os.path.join('static', 'uploads')
DB_FILE = 'contacts.db'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            source TEXT,
            page TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_visit(source=None):
    conn = sqlite3.connect(DB_FILE)
    page = request.path
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ref = source or request.args.get('from', 'direct')
    conn.execute('INSERT INTO visitors (ip, source, page) VALUES (?, ?, ?)', (ip, ref, page))
    conn.commit()
    conn.close()

# --- HOME PAGE ---
@app.route('/')
@app.route('/home')
@app.route('/index.html')
def home():
    log_visit('home')
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
    log_visit('gallery')
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
    log_visit('programs')
    return render_template("programs.html", title="Programs", description="Programs offered at Jevicarn Christian Kindergarten & School", keywords="daycare, kindergarten, primary school, nightcare, Jevicarn, Juja")

# --- CONTACT PAGE ---
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    conn = sqlite3.connect('contacts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sender TEXT,
                  text TEXT,
                  filename TEXT,
                  seen INTEGER DEFAULT 0,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        file = request.files.get('file')
        filename = None
        if file and file.filename:
            filename = file.filename
            file.save(os.path.join('static/uploads', filename))
        if text or filename:
            c.execute('INSERT INTO messages (sender, text, filename) VALUES (?, ?, ?)',
                      ('user', text, filename))
            conn.commit()
        return redirect(url_for('contact'))

    c.execute('SELECT sender, text, filename, seen FROM messages ORDER BY id ASC')
    messages_list = [{'sender': row[0], 'text': row[1], 'filename': row[2], 'seen': bool(row[3])} for row in c.fetchall()]
    conn.close()
    return render_template('contact.html', messages_list=messages_list)

# --- ADMIN PAGE ---
@app.route('/admin', methods=['GET'])
def admin():
    auth = request.args.get('auth')
    if auth != os.getenv('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403

    sender = request.args.get('sender')
    conn = sqlite3.connect('contacts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        text TEXT,
        filename TEXT,
        seen INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Distinct senders
    c.execute('SELECT DISTINCT sender FROM messages WHERE sender != "admin"')
    senders = [row[0] for row in c.fetchall()]

    # View visitor details (new)
    c.execute('SELECT ip, source, page, timestamp FROM visitors ORDER BY id DESC LIMIT 20')
    visitors = [{'ip': r[0], 'source': r[1], 'page': r[2], 'timestamp': r[3]} for r in c.fetchall()]

    chat_messages = []
    if sender:
        c.execute('UPDATE messages SET seen=1 WHERE sender=?', (sender,))
        conn.commit()
        c.execute('''
            SELECT sender, text, filename, seen, timestamp
            FROM messages
            WHERE (sender=? AND receiver="admin") OR (sender="admin" AND receiver=?)
            ORDER BY id ASC
        ''', (sender, sender))
        chat_messages = [
            {'sender': r[0], 'text': r[1], 'filename': r[2], 'seen': bool(r[3]), 'timestamp': r[4]}
            for r in c.fetchall()
        ]
    conn.close()

    return render_template('admin.html', senders=senders, chat_messages=chat_messages,
                           active_sender=sender, visitors=visitors, auth=auth)

# --- FILE DOWNLOAD ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

# --- ADMIN REPLY ---
@app.route('/admin/reply/<sender>', methods=['POST'])
def admin_reply(sender):
    auth = request.args.get('auth')
    if auth != os.getenv('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403

    text = request.form.get('text', '').strip()
    if text:
        conn = sqlite3.connect('contacts.db')
        c = conn.cursor()
        c.execute('INSERT INTO messages (sender, receiver, text, seen) VALUES (?, ?, ?, ?)',
                  ('admin', sender, text, 1))
        conn.commit()
        conn.close()
    return redirect(url_for('admin', sender=sender, auth=auth))

# --- KEEP ALIVE ---
@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong"

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

if __name__ == '__main__':
    init_db()
    if os.getenv('ENABLE_KEEP_ALIVE', '1') == '1':
        Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
