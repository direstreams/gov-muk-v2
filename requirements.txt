import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "gov_muk.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-publishing")
app.config["DATABASE"] = str(DB_PATH)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


def get_db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS travel_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('red','yellow','green')),
            headline TEXT NOT NULL,
            details TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            url TEXT NOT NULL,
            published_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            office TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS citizens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0 CHECK(balance >= 0),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(citizen_id) REFERENCES citizens(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL CHECK(price > 0)
        );
        CREATE TABLE IF NOT EXISTS holdings (
            citizen_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            PRIMARY KEY(citizen_id, symbol),
            FOREIGN KEY(citizen_id) REFERENCES citizens(id) ON DELETE CASCADE,
            FOREIGN KEY(symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
        );
        """
    )
    admin_user = os.environ.get("ADMIN_USERNAME", "MUKADMIN")
    admin_password = os.environ.get("ADMIN_PASSWORD", "modernuk")
    db.execute(
        "INSERT OR IGNORE INTO admins(username,password_hash) VALUES(?,?)",
        (admin_user, generate_password_hash(admin_password)),
    )
    settings = {
        "site_name": "GOV.MUK",
        "announcement_title": "MOD withdraws from Northern Ireland war against Ireland",
        "announcement_text": "The Ministry of Defence has confirmed the withdrawal following an operational and strategic review.",
    }
    for key, value in settings.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
    if db.execute("SELECT COUNT(*) FROM travel_notices").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        notices = [
            ("Ireland", "red", "War — avoid all travel", "Do not travel due to active conflict and serious security risks.", now),
            ("Northern Ireland", "red", "War — avoid all travel", "Do not travel due to active conflict and serious security risks.", now),
            ("United States", "yellow", "Increased caution", "Exercise increased caution due to participation in the war.", now),
            ("Germany", "yellow", "Increased caution", "Exercise increased caution due to participation in the war.", now),
            ("Ukraine", "yellow", "Increased caution", "Exercise increased caution due to participation in the war.", now),
        ]
        db.executemany("INSERT INTO travel_notices(country,level,headline,details,updated_at) VALUES(?,?,?,?,?)", notices)
    if db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
        now = "1 August 2026"
        docs = [
            ("MOD Document 01", "Ministry of Defence", "Official Ministry of Defence document.", "https://docs.google.com/document/d/1ITQAUw-hpAxzQ-UC1Gd-MY9HabISmEhEL3rczlWA6NY/edit?tab=t.0", now),
            ("MOD Document 02", "Ministry of Defence", "Official Ministry of Defence document.", "https://docs.google.com/document/d/1FzShO1NqsMkfamcrNDn0v2KHEz3kZLvTPdxXidRkRH4/edit?tab=t.0", now),
            ("MOD Document 03", "Ministry of Defence", "Official Ministry of Defence document.", "https://docs.google.com/document/d/1TswyE4qKpaMHxfTDlS3Gn-KFDxquaqxIqhZcblRhzAY/edit?tab=t.0", now),
            ("MOD Document 04", "Ministry of Defence", "Official Ministry of Defence document.", "https://docs.google.com/document/d/1BYzuE-SHhbZQrmCYGVgiuema-2sHyYf40B08LSseL9k/edit?tab=t.0", now),
        ]
        db.executemany("INSERT INTO documents(title,category,description,url,published_at) VALUES(?,?,?,?,?)", docs)
    if db.execute("SELECT COUNT(*) FROM leaders").fetchone()[0] == 0:
        leaders = [
            ("Prime Minister", "Carter McGrant", "Head of Government and chair of the national cabinet.", 1),
            ("Minister of Defence", "Dire Vercetti", "Responsible for defence policy, armed forces and national security.", 2),
            ("Minister of Foreign Affairs", "Hades", "Responsible for diplomacy, international relations and foreign policy.", 3),
        ]
        db.executemany("INSERT INTO leaders(office,name,description,sort_order) VALUES(?,?,?,?)", leaders)
    if db.execute("SELECT COUNT(*) FROM stocks").fetchone()[0] == 0:
        db.executemany("INSERT INTO stocks(symbol,name,price) VALUES(?,?,?)", [
            ("MUKD", "MUK Defence Industries", 125.00),
            ("MUKT", "MUK Transport Group", 74.50),
            ("MUKB", "Bank of MUK Holdings", 98.20),
            ("MUKC", "MUK Communications", 46.80),
        ])
    db.commit()
    db.close()


def setting(key):
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


@app.context_processor
def inject_globals():
    return {"site_name": setting("site_name")}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def citizen_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("citizen_id"):
            return redirect(url_for("citizen_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/")
def home():
    leaders = get_db().execute("SELECT * FROM leaders ORDER BY sort_order,id").fetchall()
    return render_template("index.html", leaders=leaders, announcement_title=setting("announcement_title"), announcement_text=setting("announcement_text"))


@app.route("/services")
def services(): return render_template("services.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    catalogue = [
        ("Services and information", "Browse government services and departments.", url_for("services"), "services government information"),
        ("Foreign travel advice", "View fictional security and conflict notices by country.", url_for("travel"), "travel ireland northern ireland usa germany ukraine war"),
        ("Government and leadership", "View the Prime Minister and senior ministers.", url_for("leadership"), "leadership prime minister carter mcgrant dire vercetti hades"),
        ("Government documents", "Open the Ministry of Defence publication archive.", url_for("documents"), "documents archive ministry defence publications"),
        ("Ministry of Defence", "Recruitment, statements and defence information.", url_for("mod"), "mod defence 42 commando 856 support unit royal marines"),
        ("Bank of MUK", "Manage an administrator-issued citizen account.", url_for("bank"), "bank account credits transfer"),
        ("MUK Exchange", "Trade fictional shares with existing virtual credits.", url_for("markets"), "stocks shares markets exchange"),
    ]
    terms = [t for t in query.lower().split() if t]
    results = []
    for title, description, target, keywords in catalogue:
        haystack = f"{title} {description} {keywords}".lower()
        if query and all(term in haystack for term in terms):
            results.append({"title": title, "description": description, "url": target})
    return render_template("search.html", query=query, results=results)


@app.route("/leadership")
def leadership():
    leaders = get_db().execute("SELECT * FROM leaders ORDER BY sort_order,id").fetchall()
    return render_template("leadership.html", leaders=leaders)


@app.route("/travel")
def travel():
    notices = get_db().execute("SELECT * FROM travel_notices ORDER BY CASE level WHEN 'red' THEN 1 WHEN 'yellow' THEN 2 ELSE 3 END,country").fetchall()
    return render_template("travel.html", notices=notices)


@app.route("/documents")
def documents():
    docs = get_db().execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
    return render_template("documents.html", documents=docs)




@app.route("/mod")
def mod():
    docs = get_db().execute("SELECT * FROM documents ORDER BY id DESC LIMIT 4").fetchall()
    return render_template("mod.html", documents=docs)


@app.route("/citizen/login", methods=["GET","POST"])
def citizen_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM citizens WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["citizen_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("bank"))
        flash("Invalid citizen username or password.", "error")
    return render_template("citizen_login.html")


@app.route("/citizen/logout")
def citizen_logout(): session.clear(); return redirect(url_for("home"))


@app.route("/bank", methods=["GET","POST"])
@citizen_required
def bank():
    db = get_db(); citizen_id = session["citizen_id"]
    if request.method == "POST":
        recipient_name = request.form.get("recipient", "").strip()
        try: amount = round(float(request.form.get("amount", "0")), 2)
        except ValueError: amount = 0
        sender = db.execute("SELECT * FROM citizens WHERE id=?", (citizen_id,)).fetchone()
        recipient = db.execute("SELECT * FROM citizens WHERE username=?", (recipient_name,)).fetchone()
        if amount <= 0: flash("Enter a valid transfer amount.", "error")
        elif not recipient: flash("Recipient account was not found.", "error")
        elif recipient["id"] == citizen_id: flash("You cannot transfer credits to your own account.", "error")
        elif sender["balance"] < amount: flash("Insufficient credits.", "error")
        else:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            db.execute("UPDATE citizens SET balance=balance-? WHERE id=?", (amount,citizen_id))
            db.execute("UPDATE citizens SET balance=balance+? WHERE id=?", (amount,recipient["id"]))
            db.execute("INSERT INTO transactions(citizen_id,kind,description,amount,created_at) VALUES(?,?,?,?,?)", (citizen_id,"debit",f"Transfer to {recipient_name}",-amount,now))
            db.execute("INSERT INTO transactions(citizen_id,kind,description,amount,created_at) VALUES(?,?,?,?,?)", (recipient["id"],"credit",f"Transfer from {sender['username']}",amount,now))
            db.commit(); flash("Virtual credits transferred.", "success")
            return redirect(url_for("bank"))
    citizen = db.execute("SELECT * FROM citizens WHERE id=?", (citizen_id,)).fetchone()
    tx = db.execute("SELECT * FROM transactions WHERE citizen_id=? ORDER BY id DESC LIMIT 30", (citizen_id,)).fetchall()
    return render_template("bank.html", citizen=citizen, transactions=tx)


@app.route("/markets", methods=["GET","POST"])
@citizen_required
def markets():
    db=get_db(); citizen_id=session["citizen_id"]
    if request.method == "POST":
        symbol=request.form.get("symbol",""); action=request.form.get("action","")
        try: qty=int(request.form.get("quantity","0"))
        except ValueError: qty=0
        stock=db.execute("SELECT * FROM stocks WHERE symbol=?",(symbol,)).fetchone()
        citizen=db.execute("SELECT * FROM citizens WHERE id=?",(citizen_id,)).fetchone()
        holding=db.execute("SELECT quantity FROM holdings WHERE citizen_id=? AND symbol=?",(citizen_id,symbol)).fetchone()
        owned=holding["quantity"] if holding else 0
        if not stock or qty <= 0: flash("Invalid trade.","error")
        else:
            total=round(stock["price"]*qty,2); now=datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            if action=="buy":
                if citizen["balance"] < total: flash("Insufficient credits.","error")
                else:
                    db.execute("UPDATE citizens SET balance=balance-? WHERE id=?",(total,citizen_id))
                    db.execute("INSERT INTO holdings(citizen_id,symbol,quantity) VALUES(?,?,?) ON CONFLICT(citizen_id,symbol) DO UPDATE SET quantity=quantity+excluded.quantity",(citizen_id,symbol,qty))
                    db.execute("INSERT INTO transactions(citizen_id,kind,description,amount,created_at) VALUES(?,?,?,?,?)",(citizen_id,"debit",f"Bought {qty} {symbol}",-total,now)); db.commit(); flash("Shares purchased.","success")
            elif action=="sell":
                if owned < qty: flash("You do not own enough shares.","error")
                else:
                    db.execute("UPDATE holdings SET quantity=quantity-? WHERE citizen_id=? AND symbol=?",(qty,citizen_id,symbol))
                    db.execute("UPDATE citizens SET balance=balance+? WHERE id=?",(total,citizen_id))
                    db.execute("INSERT INTO transactions(citizen_id,kind,description,amount,created_at) VALUES(?,?,?,?,?)",(citizen_id,"credit",f"Sold {qty} {symbol}",total,now)); db.commit(); flash("Shares sold.","success")
            return redirect(url_for("markets"))
    citizen=db.execute("SELECT * FROM citizens WHERE id=?",(citizen_id,)).fetchone()
    stocks=db.execute("SELECT * FROM stocks ORDER BY symbol").fetchall()
    holdings={r["symbol"]:r["quantity"] for r in db.execute("SELECT * FROM holdings WHERE citizen_id=?",(citizen_id,)).fetchall()}
    return render_template("markets.html", citizen=citizen, stocks=stocks, holdings=holdings)


@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username=request.form.get("username","").strip(); password=request.form.get("password","")
        admin=get_db().execute("SELECT * FROM admins WHERE username=?",(username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"],password):
            session.clear(); session["admin_id"]=admin["id"]
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.","error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout(): session.clear(); return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db=get_db()
    return render_template("admin.html",
        notices=db.execute("SELECT * FROM travel_notices ORDER BY id").fetchall(),
        documents=db.execute("SELECT * FROM documents ORDER BY id").fetchall(),
        leaders=db.execute("SELECT * FROM leaders ORDER BY sort_order,id").fetchall(),
        citizens=db.execute("SELECT id,username,balance,created_at FROM citizens ORDER BY username").fetchall(),
        stocks=db.execute("SELECT * FROM stocks ORDER BY symbol").fetchall(),
        announcement_title=setting("announcement_title"), announcement_text=setting("announcement_text"))


@app.post("/admin/settings")
@admin_required
def admin_settings():
    db=get_db()
    for key in ("announcement_title","announcement_text"):
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,request.form.get(key,"")))
    db.commit(); flash("Homepage announcement updated.","success"); return redirect(url_for("admin_dashboard"))


@app.post("/admin/travel/save")
@admin_required
def admin_travel_save():
    db=get_db(); item_id=request.form.get("id"); vals=(request.form["country"],request.form["level"],request.form["headline"],request.form["details"],datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    if item_id: db.execute("UPDATE travel_notices SET country=?,level=?,headline=?,details=?,updated_at=? WHERE id=?",(*vals,item_id))
    else: db.execute("INSERT INTO travel_notices(country,level,headline,details,updated_at) VALUES(?,?,?,?,?)",vals)
    db.commit(); flash("Travel notice saved.","success"); return redirect(url_for("admin_dashboard"))


@app.post("/admin/travel/delete/<int:item_id>")
@admin_required
def admin_travel_delete(item_id):
    get_db().execute("DELETE FROM travel_notices WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))


@app.post("/admin/document/save")
@admin_required
def admin_document_save():
    db=get_db(); item_id=request.form.get("id"); vals=(request.form["title"],request.form["category"],request.form["description"],request.form["url"],request.form["published_at"])
    if item_id: db.execute("UPDATE documents SET title=?,category=?,description=?,url=?,published_at=? WHERE id=?",(*vals,item_id))
    else: db.execute("INSERT INTO documents(title,category,description,url,published_at) VALUES(?,?,?,?,?)",vals)
    db.commit(); flash("Document saved.","success"); return redirect(url_for("admin_dashboard"))


@app.post("/admin/document/delete/<int:item_id>")
@admin_required
def admin_document_delete(item_id):
    get_db().execute("DELETE FROM documents WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))


@app.post("/admin/leader/save")
@admin_required
def admin_leader_save():
    db=get_db(); item_id=request.form.get("id"); vals=(request.form["office"],request.form["name"],request.form["description"],int(request.form.get("sort_order",0)))
    if item_id: db.execute("UPDATE leaders SET office=?,name=?,description=?,sort_order=? WHERE id=?",(*vals,item_id))
    else: db.execute("INSERT INTO leaders(office,name,description,sort_order) VALUES(?,?,?,?)",vals)
    db.commit(); flash("Leadership entry saved.","success"); return redirect(url_for("admin_dashboard"))


@app.post("/admin/leader/delete/<int:item_id>")
@admin_required
def admin_leader_delete(item_id):
    get_db().execute("DELETE FROM leaders WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))


@app.post("/admin/citizen/create")
@admin_required
def admin_citizen_create():
    username=request.form["username"].strip(); password=request.form["password"]
    try: balance=max(0,round(float(request.form.get("balance","0")),2))
    except ValueError: balance=0
    try:
        get_db().execute("INSERT INTO citizens(username,password_hash,balance,created_at) VALUES(?,?,?,?)",(username,generate_password_hash(password),balance,datetime.utcnow().strftime("%Y-%m-%d %H:%M"))); get_db().commit(); flash("Citizen account created.","success")
    except sqlite3.IntegrityError: flash("That username already exists.","error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/citizen/balance/<int:citizen_id>")
@admin_required
def admin_citizen_balance(citizen_id):
    try: balance=max(0,round(float(request.form["balance"]),2))
    except ValueError: flash("Invalid balance.","error"); return redirect(url_for("admin_dashboard"))
    get_db().execute("UPDATE citizens SET balance=? WHERE id=?",(balance,citizen_id)); get_db().commit(); flash("Balance updated by administrator.","success"); return redirect(url_for("admin_dashboard"))


@app.post("/admin/stock/<symbol>")
@admin_required
def admin_stock(symbol):
    try: price=round(float(request.form["price"]),2)
    except ValueError: price=0
    if price>0:
        get_db().execute("UPDATE stocks SET price=? WHERE symbol=?",(price,symbol)); get_db().commit(); flash("Stock price updated.","success")
    return redirect(url_for("admin_dashboard"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=os.environ.get("FLASK_DEBUG")=="1")
