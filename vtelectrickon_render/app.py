import os
import sqlite3
import json
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="statistcs")
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
UPI_ID = os.environ.get("UPI_ID", "vtelectrickon@upi")

def is_postgres():
    return bool(os.environ.get("DATABASE_URL"))

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        import psycopg2
        return psycopg2.connect(db_url, sslmode='require')
    else:
        return sqlite3.connect("database.db")

# ---------------- DATABASE ----------------
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    
    if pg:
        c.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT,
            brand TEXT,
            price REAL,
            stock INTEGER,
            image TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            address TEXT,
            items TEXT,
            total REAL,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending',
            transaction_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_status TEXT DEFAULT 'pending'
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            id SERIAL PRIMARY KEY,
            key TEXT UNIQUE,
            value TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
    else:
        c.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            brand TEXT,
            price REAL,
            stock INTEGER,
            image TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            address TEXT,
            items TEXT,
            total REAL,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending',
            transaction_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_status TEXT DEFAULT 'pending'
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
    try:
        c.execute("ALTER TABLE orders ADD COLUMN delivery_status TEXT DEFAULT 'pending'")
        if pg: conn.commit()
    except Exception:
        if pg: conn.rollback()
        
    try:
        c.execute("ALTER TABLE orders ADD COLUMN transaction_ref TEXT")
        if pg: conn.commit()
    except Exception:
        if pg: conn.rollback()
        
    try:
        c.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'Uncategorized'")
        if pg: conn.commit()
    except Exception:
        if pg: conn.rollback()
        
    try:
        c.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER")
        if pg: conn.commit()
    except Exception:
        if pg: conn.rollback()
        
    c.execute("SELECT COUNT(*) FROM products")
    count = c.fetchone()[0]
    if count == 0:
        c.execute("""
        INSERT INTO products (name,brand,price,stock,image)
        VALUES
        ('Multispan Digital Timer','Multispan',1200,5,'multispan_timer.jpg'),
        ('Sibass MCB','Sibass',850,2,'sibass_mcb.jpg')
        """)
        
    # Seed default settings
    c.execute("SELECT COUNT(*) FROM settings")
    s_count = c.fetchone()[0]
    if s_count == 0:
        query = "INSERT INTO settings (key, value) VALUES (%s, %s)" if pg else "INSERT INTO settings (key, value) VALUES (?, ?)"
        c.execute(query, ('upi_id', UPI_ID))
        c.execute(query, ('card_details', 'Bank Name: State Bank of India\nAccount Number: 123456789\nIFSC Code: SBIN0001234\nAccount Name: VT Electrickon'))
        
    conn.commit()
    c.close()
    conn.close()

init_db()

# ---------------- HELPERS ----------------
def get_cart_products():
    cart_ids = session.get("cart", [])
    if not cart_ids:
        return [], 0
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    
    products = []
    for pid in cart_ids:
        query = "SELECT * FROM products WHERE id=%s" if pg else "SELECT * FROM products WHERE id=?"
        c.execute(query, (pid,))
        p = c.fetchone()
        if p:
            products.append(p)
    c.close()
    conn.close()
    total = sum(p[3] for p in products)
    return products, total

def get_setting(key, default=""):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query = "SELECT value FROM settings WHERE key=%s" if pg else "SELECT value FROM settings WHERE key=?"
    c.execute(query, (key,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row[0] if row else default

def update_setting(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query_check = "SELECT id FROM settings WHERE key=%s" if pg else "SELECT id FROM settings WHERE key=?"
    c.execute(query_check, (key,))
    if c.fetchone():
        query = "UPDATE settings SET value=%s WHERE key=%s" if pg else "UPDATE settings SET value=? WHERE key=?"
        c.execute(query, (value, key))
    else:
        query = "INSERT INTO settings (key, value) VALUES (%s, %s)" if pg else "INSERT INTO settings (key, value) VALUES (?, ?)"
        c.execute(query, (key, value))
    conn.commit()
    c.close()
    conn.close()

# ---------------- ADMIN AUTH ----------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "Incorrect password."
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

# ---------------- CUSTOMER AUTH ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username and password:
            conn = get_db_connection()
            c = conn.cursor()
            pg = is_postgres()
            try:
                query = "INSERT INTO users (username, password) VALUES (%s, %s)" if pg else "INSERT INTO users (username, password) VALUES (?, ?)"
                c.execute(query, (username, password))
                conn.commit()
                c.execute("SELECT id FROM users WHERE username=%s" if pg else "SELECT id FROM users WHERE username=?", (username,))
                user_id = c.fetchone()[0]
                session["user_id"] = user_id
                session["username"] = username
                c.close()
                conn.close()
                return redirect(url_for("home"))
            except Exception:
                error = "Username already exists."
            finally:
                if c: c.close()
                if conn: conn.close()
        else:
            error = "Both fields are required."
    return render_template("signup.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db_connection()
        c = conn.cursor()
        pg = is_postgres()
        query = "SELECT id, password FROM users WHERE username=%s" if pg else "SELECT id, password FROM users WHERE username=?"
        c.execute(query, (username,))
        user = c.fetchone()
        c.close()
        conn.close()
        if user and user[1] == password:
            session["user_id"] = user[0]
            session["username"] = username
            return redirect(url_for("home"))
        else:
            error = "Invalid credentials."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("home"))

@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query = "SELECT id, total, payment_method, payment_status, delivery_status, created_at, items FROM orders WHERE user_id=%s ORDER BY created_at DESC" if pg else "SELECT id, total, payment_method, payment_status, delivery_status, created_at, items FROM orders WHERE user_id=? ORDER BY created_at DESC"
    c.execute(query, (user_id,))
    orders = c.fetchall()
    c.close()
    conn.close()
    return render_template("profile.html", orders=orders)

# ---------------- HOME ----------------
@app.route("/", methods=["GET", "HEAD"])
def home():
    search = request.args.get("q", "")
    category = request.args.get("category", "")
    
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if search:
        query += " AND name ILIKE %s" if pg else " AND name LIKE ?"
        params.append(f"%{search}%")
    if category:
        query += " AND category = %s" if pg else " AND category = ?"
        params.append(category)
        
    c.execute(query, tuple(params))
    products = c.fetchall()
    
    try:
        c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != 'Uncategorized'")
        categories = [r[0] for r in c.fetchall()]
    except Exception:
        categories = []
    
    c.close()
    conn.close()
    return render_template("index.html", products=products, categories=categories, current_search=search, current_category=category)

# ---------------- ADD TO CART ----------------
@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    cart = session.get("cart", [])
    cart.append(product_id)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))

# ---------------- CART PAGE ----------------
@app.route("/cart")
def cart():
    products, total = get_cart_products()
    return render_template("cart.html", products=products, total=total)

# ---------------- REMOVE FROM CART ----------------
@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):
    cart = session.get("cart", [])
    if 0 <= index < len(cart):
        cart.pop(index)
        session["cart"] = cart
        session.modified = True
    return redirect(url_for("cart"))

# ---------------- BUY PRODUCT ----------------
@app.route("/buy/<int:product_id>")
def buy(product_id):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    
    query = "SELECT stock FROM products WHERE id=%s" if pg else "SELECT stock FROM products WHERE id=?"
    c.execute(query, (product_id,))
    stock = c.fetchone()
    if stock and stock[0] > 0:
        upd_query = "UPDATE products SET stock = stock - 1 WHERE id=%s" if pg else "UPDATE products SET stock = stock - 1 WHERE id=?"
        c.execute(upd_query, (product_id,))
        conn.commit()
    c.close()
    conn.close()
    return redirect(url_for("home"))

# ---------------- CHECKOUT ----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    products, total = get_cart_products()
    if not products:
        return redirect(url_for("cart"))

    upi_id = get_setting("upi_id", UPI_ID)
    card_details = get_setting("card_details", "")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        method = request.form.get("payment_method", "cod")
        transaction_ref = request.form.get("transaction_ref", "").strip()
        items_json = json.dumps([{"name": p[1], "price": p[3]} for p in products])

        if method in ["upi", "card"] and not transaction_ref:
            return render_template("checkout.html", products=products, total=total,
                                   upi_id=upi_id, card_details=card_details,
                                   error="Please enter your payment transaction reference number after paying.")

        pay_status = "pending" if method in ["upi", "card"] else "confirmed"
        conn = get_db_connection()
        c = conn.cursor()
        pg = is_postgres()
        
        if pg:
            query = """INSERT INTO orders (name, phone, address, items, total, payment_method, payment_status, transaction_ref, delivery_status, user_id)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s) RETURNING id"""
            c.execute(query, (name, phone, address, items_json, total, method, pay_status, transaction_ref or None, session.get("user_id")))
            order_id = c.fetchone()[0]
        else:
            query = """INSERT INTO orders (name, phone, address, items, total, payment_method, payment_status, transaction_ref, delivery_status, user_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)"""
            c.execute(query, (name, phone, address, items_json, total, method, pay_status, transaction_ref or None, session.get("user_id")))
            order_id = c.lastrowid
            
        conn.commit()
        c.close()
        conn.close()
        session["cart"] = []
        session.modified = True
        return render_template("order_confirmed.html", name=name, total=total,
                               method="UPI" if method == "upi" else ("Bank/Card" if method == "card" else "Cash on Delivery"),
                               order_id=order_id)

    return render_template("checkout.html", products=products, total=total, upi_id=upi_id, card_details=card_details)

# ---------------- ORDER STATUS (for customers) ----------------
@app.route("/order/status/<int:order_id>")
def order_status(order_id):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query = "SELECT id, name, total, payment_method, delivery_status, created_at FROM orders WHERE id=%s" if pg else "SELECT id, name, total, payment_method, delivery_status, created_at FROM orders WHERE id=?"
    c.execute(query, (order_id,))
    order = c.fetchone()
    c.close()
    conn.close()
    return render_template("order_status.html", order=order, order_id=order_id)

# ---------------- ADMIN PANEL ----------------
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        action = request.form.get("action", "add_product")
        if action == "save_settings":
            upi_id = request.form.get("upi_id", "").strip()
            card_details = request.form.get("card_details", "").strip()
            update_setting("upi_id", upi_id)
            update_setting("card_details", card_details)
            return redirect(url_for("admin"))
        elif action == "add_product":
            name = request.form.get("name", "").strip()
            brand = request.form.get("brand", "").strip()
            category = request.form.get("category", "Uncategorized").strip()
            price = request.form.get("price", "0").strip()
            stock = request.form.get("stock", "0").strip()
            
            file = request.files.get("image_file")
            image_filename = ""
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_folder = os.path.join(app.root_path, "statistcs", "images")
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                image_filename = filename
            else:
                image_filename = request.form.get("image", "").strip()

            if name:
                try:
                    price = float(price)
                    stock = int(stock)
                except ValueError:
                    price = 0.0
                    stock = 0
                conn = get_db_connection()
                c = conn.cursor()
                pg = is_postgres()
                query = "INSERT INTO products (name, brand, price, stock, image, category) VALUES (%s, %s, %s, %s, %s, %s)" if pg else "INSERT INTO products (name, brand, price, stock, image, category) VALUES (?, ?, ?, ?, ?, ?)"
                c.execute(query, (name, brand, price, stock, image_filename, category))
                conn.commit()
                c.close()
                conn.close()
            return redirect(url_for("admin"))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    c.execute("""SELECT id, name, phone, address, total, payment_method, payment_status,
                        transaction_ref, delivery_status, created_at, user_id
                 FROM orders ORDER BY created_at DESC LIMIT 50""")
    orders = c.fetchall()
    c.close()
    conn.close()
    
    current_upi = get_setting("upi_id", UPI_ID)
    current_card = get_setting("card_details", "")
    
    return render_template("admin.html", products=products, orders=orders, upi_id=current_upi, card_details=current_card)

# ---------------- MARK ORDER DONE ----------------
@app.route("/admin/order/<int:order_id>/done")
@admin_required
def order_done(order_id):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query = "UPDATE orders SET delivery_status='done' WHERE id=%s" if pg else "UPDATE orders SET delivery_status='done' WHERE id=?"
    c.execute(query, (order_id,))
    conn.commit()
    c.close()
    conn.close()
    return redirect(url_for("admin"))

# ---------------- DELETE PRODUCT ----------------
@app.route("/admin/delete/<int:product_id>")
@admin_required
def delete_product(product_id):
    conn = get_db_connection()
    c = conn.cursor()
    pg = is_postgres()
    query = "DELETE FROM products WHERE id=%s" if pg else "DELETE FROM products WHERE id=?"
    c.execute(query, (product_id,))
    conn.commit()
    c.close()
    conn.close()
    return redirect(url_for("admin"))

# ---------------- STARTUP ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
