from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import sqlite3
from threading import Thread
import time
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'

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
def home():
    images = os.listdir(UPLOAD_FOLDER)
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
@app.route("/gallery")
def gallery():
    image_folder = os.path.join(app.static_folder, 'gallery')
    images = []

    if os.path.exists(image_folder):
        images = [
            f'gallery/{img}'
            for img in os.listdir(image_folder)
            if img.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
        ]

    return render_template(
        "gallery.html",
        images=images,
        title="Our Gallery | Jevicarn Christian Daycare & School"
    )

# --- CONTACT PAGE ---
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        conn = sqlite3.connect(DB_FILE)
        conn.execute('INSERT INTO contacts (name, email, message) VALUES (?, ?, ?)', (name, email, message))
        conn.commit()
        conn.close()
        flash('Message sent successfully!', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html', title='Contact Us | Jevicarn Christian School')

# --- ADMIN PAGE ---
@app.route('/admin')
def admin():
    auth = request.args.get('auth')
    if auth != os.getenv('ADMIN_PASS', 'admin123'):
        return "Unauthorized", 403
    conn = sqlite3.connect(DB_FILE)
    contacts = conn.execute('SELECT * FROM contacts').fetchall()
    conn.close()
    return render_template('admin.html', contacts=contacts, title='Admin Panel')

# --- KEEP-ALIVE ENDPOINT ---
@app.route('/keepalive-ping')
def keepalive_ping():
    return "pong"

# --- KEEP-ALIVE THREAD (Prevents Render/Fly from sleeping) ---
def keep_alive():
    url = os.getenv('KEEP_ALIVE_URL')
    if not url:
        return
    print("🟢 Keep-alive service started, pinging every 25 seconds.")
    while True:
        try:
            requests.get(url + '/keepalive-ping')
            print("Ping sent successfully.")
        except Exception as e:
            print(f"⚠️ Keep-alive error: {e}")
        time.sleep(25)  # shorter intervals improve uptime consistency

# --- MAIN APP ENTRY ---
if __name__ == '__main__':
    init_db()
    if os.getenv('ENABLE_KEEP_ALIVE', '1') == '1':  # Default enabled
        Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True)
