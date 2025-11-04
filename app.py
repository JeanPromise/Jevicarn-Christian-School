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
    conn.execute('CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT)')
    conn.commit()
    conn.close()

# --- HOME PAGE ---
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

# --- GALLERY PAGE ---
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
#---PROGRAMS PAGE ---
@app.route("/programs")
def programs():
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

    # Fetch all messages (user + admin)
    c.execute('SELECT sender, text, filename, seen FROM messages ORDER BY id ASC')
    messages_list = [{'sender': row[0], 'text': row[1], 'filename': row[2], 'seen': bool(row[3])} for row in c.fetchall()]
    conn.close()
    return render_template('contact.html', messages_list=messages_list)

# --- ADMIN ANALYTICS DASHBOARD (NEW CLEAN VERSION) ---
@app.route('/admin', methods=['GET'])
def admin():
    auth = request.args.get('auth')
    if auth != os.getenv('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403

    conn = sqlite3.connect('contacts.db')
    c = conn.cursor()

    # Ensure messages table exists and has required columns
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

    # Patch missing columns if any
    c.execute('PRAGMA table_info(messages)')
    cols = [col[1] for col in c.fetchall()]
    for missing in ['receiver', 'location', 'platform']:
        if missing not in cols:
            try:
                c.execute(f'ALTER TABLE messages ADD COLUMN {missing} TEXT;')
                conn.commit()
            except:
                pass

    # Fetch summarized analytics
    c.execute('SELECT COUNT(*) FROM messages')
    total_msgs = c.fetchone()[0] or 0

    c.execute('SELECT COUNT(DISTINCT sender) FROM messages WHERE sender != "admin"')
    total_users = c.fetchone()[0] or 0

    # Group by location
    c.execute('SELECT location, COUNT(*) FROM messages WHERE location IS NOT NULL GROUP BY location')
    location_data = c.fetchall()

    # Group by platform
    c.execute('SELECT platform, COUNT(*) FROM messages WHERE platform IS NOT NULL GROUP BY platform')
    platform_data = c.fetchall()

    # Top 5 most active senders
    c.execute('SELECT sender, COUNT(*) as count FROM messages WHERE sender != "admin" GROUP BY sender ORDER BY count DESC LIMIT 5')
    top_senders = c.fetchall()

    conn.close()

    # Prepare data for charts
    locations = [row[0] for row in location_data if row[0]]
    location_counts = [row[1] for row in location_data if row[0]]
    platforms = [row[0] for row in platform_data if row[0]]
    platform_counts = [row[1] for row in platform_data if row[0]]

    return render_template(
        'admin.html',
        total_msgs=total_msgs,
        total_users=total_users,
        top_senders=top_senders,
        locations=locations,
        location_counts=location_counts,
        platforms=platforms,
        platform_counts=platform_counts
    )


# --- FILE DOWNLOAD / VIEW ROUTE ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

# --- KEEP-ALIVE ENDPOINT ---
@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong"

# --- KEEP-ALIVE ENDPOINT ---
@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong", 200


# --- KEEP-ALIVE THREAD (optional internal pinger, every 25 sec) ---
def keep_alive():
    url = os.getenv('KEEP_ALIVE_URL', 'https://jevicarn-christian-school.onrender.com')
    print("🟢 Internal keep-alive started (pinging every 25 seconds).")

    while True:
        try:
            requests.get(f"{url}/keepalive-ping", timeout=10)
            print("✅  Keep-alive ping sent.")
        except Exception as e:
            print(f"⚠️  Keep-alive error: {e}")
        time.sleep(25)


# --- MAIN APP ENTRY ---
if __name__ == '__main__':
    init_db()
    # Internal keep-alive runs only if enabled via env var
    if os.getenv('ENABLE_KEEP_ALIVE', '1') == '1':
        Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
