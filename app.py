import os
import sqlite3
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "instance" / "gov_muk.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-publishing")
app.config["DATABASE"] = str(DB_PATH)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


def get_db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 5000")
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
            level TEXT NOT NULL CHECK(level IN ('white','green','yellow','amber','red','black')),
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

        CREATE TABLE IF NOT EXISTS diplomatic_recognition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('recognised','limited','not_recognised','suspended')),
            relationship TEXT NOT NULL,
            capital TEXT NOT NULL DEFAULT '',
            latitude REAL NOT NULL DEFAULT 0,
            longitude REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            region TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','monitoring','completed','suspended')),
            department TEXT NOT NULL,
            summary TEXT NOT NULL,
            latitude REAL NOT NULL DEFAULT 0,
            longitude REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS emergency_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('critical','severe','warning','information')),
            region TEXT NOT NULL,
            guidance TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS warrants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','suspended','closed')),
            reference TEXT NOT NULL,
            summary TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS petitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            creator TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','open','closed','rejected')) DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS petition_signatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            petition_id INTEGER NOT NULL,
            signer TEXT NOT NULL,
            signed_at TEXT NOT NULL,
            UNIQUE(petition_id, signer),
            FOREIGN KEY(petition_id) REFERENCES petitions(id) ON DELETE CASCADE
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
            ("Yellowonia", "yellow", "Travel with increased caution", "Exercise increased caution and review official updates before travel.", now),
            ("United States", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply.", now),
            ("Russia", "white", "Status unknown", "Current travel conditions have not been formally assessed by GOV.MUK.", now),
            ("Ireland", "red", "Avoid all travel", "Do not travel due to active conflict and serious security risks.", now),
            ("Northern Ireland", "red", "Avoid all travel", "Do not travel due to active conflict and serious security risks.", now),
            ("UoC", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates.", now),
            ("Germany", "red", "Avoid all travel", "Do not travel until further notice due to the current security assessment.", now),
            ("Ukraine", "red", "Avoid all travel", "Do not travel due to conflict and serious security risks.", now),
            ("Lebanon", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply.", now),
            ("Brunei", "amber", "Avoid all non-essential travel", "Only essential travel should be considered at this time.", now),
            ("Finland", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply.", now),
            ("Israel", "yellow", "Travel with increased caution", "Exercise increased caution and monitor local security updates.", now),
            ("Cayman Islands", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply.", now),
            ("Japan", "amber", "Avoid all non-essential travel", "Only essential travel should be considered at this time.", now),
            ("China", "yellow", "Travel with increased caution", "Exercise increased caution and review entry and security guidance.", now),
            ("Spain", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates.", now),
            ("Nigeria", "red", "Avoid all travel", "Do not travel until further notice due to the current security assessment.", now),
            ("Norway", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply.", now),
            ("Maryland", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates.", now),
            ("South Africa", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates.", now),
            ("Guinea", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates.", now),
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
            ("UK Ambassador to the United Nations", "EuroTyphoon", "Represents MUK at the United Nations and supports multilateral diplomacy.", 4),
        ]
        db.executemany("INSERT INTO leaders(office,name,description,sort_order) VALUES(?,?,?,?)", leaders)
    if db.execute("SELECT COUNT(*) FROM stocks").fetchone()[0] == 0:
        db.executemany("INSERT INTO stocks(symbol,name,price) VALUES(?,?,?)", [
            ("MUKD", "MUK Defence Industries", 125.00),
            ("MUKT", "MUK Transport Group", 74.50),
            ("MUKB", "Bank of England Holdings", 98.20),
            ("MUKC", "MUK Communications", 46.80),
        ])

    if db.execute("SELECT COUNT(*) FROM diplomatic_recognition").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        recognition = [
            ("Ireland", "suspended", "Diplomatic relations suspended during the current conflict.", "Dublin", 53.3498, -6.2603, "Travel warning remains at red.", now),
            ("Northern Ireland", "limited", "Limited official contact for humanitarian and deconfliction purposes.", "Belfast", 54.5973, -5.9301, "Security situation under review.", now),
            ("United States", "recognised", "Formal diplomatic recognition with stable bilateral relations.", "Washington, D.C.", 38.9072, -77.0369, "Green travel status with stable security conditions.", now),
            ("Germany", "recognised", "Formal diplomatic recognition and stable embassy-level relations.", "Berlin", 52.5200, 13.4050, "Green travel status with stable security conditions.", now),
            ("Ukraine", "recognised", "Formal diplomatic recognition and continued foreign-affairs contact.", "Kyiv", 50.4501, 30.5234, "Yellow travel notice currently applies.", now),
            ("Falkland Islands", "recognised", "Recognised as a MUK overseas territory in this roleplay setting.", "Stanley", -51.6977, -57.8517, "Territorial administration.", now),
        ]
        db.executemany("INSERT INTO diplomatic_recognition(country,status,relationship,capital,latitude,longitude,notes,updated_at) VALUES(?,?,?,?,?,?,?,?)", recognition)
    if db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        operations = [
            ("Operation Northern Watch", "Northern Ireland", "monitoring", "Ministry of Defence", "Monitoring regional security developments following the withdrawal announcement.", 54.5973, -5.9301, now),
            ("Operation Atlantic Guard", "Falkland Islands", "active", "Ministry of Defence", "Routine territorial readiness and maritime awareness operation.", -51.6977, -57.8517, now),
            ("Operation Safe Passage", "Ireland", "suspended", "Foreign Affairs", "Diplomatic travel-support activity suspended due to the red travel notice.", 53.3498, -6.2603, now),
        ]
        db.executemany("INSERT INTO operations(name,region,status,department,summary,latitude,longitude,updated_at) VALUES(?,?,?,?,?,?,?,?)", operations)
    if db.execute("SELECT COUNT(*) FROM emergency_alerts").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        alerts = [
            ("Conflict travel restrictions", "critical", "Ireland and Northern Ireland", "Avoid all travel and follow official GOV.MUK updates.", 1, now),
            ("Heightened international caution", "warning", "Ukraine", "Exercise increased caution and review the current travel notice before departure.", 1, now),
            ("Government services operational", "information", "MUK", "Core online government services remain available.", 1, now),
        ]
        db.executemany("INSERT INTO emergency_alerts(title,level,region,guidance,active,updated_at) VALUES(?,?,?,?,?,?)", alerts)
    if db.execute("SELECT COUNT(*) FROM warrants").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        db.execute(
            "INSERT INTO warrants(subject,status,reference,summary,issued_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("Abdul Hameed", "active", "MUK-WARRANT-001", "Public roleplay notice. Further details are withheld.", "2 August 2026", now),
        )
    if db.execute("SELECT COUNT(*) FROM petitions").fetchone()[0] == 0:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        db.execute(
            "INSERT INTO petitions(title,summary,creator,status,created_at) VALUES(?,?,?,?,?)",
            ("Improve public transport information", "Request clearer public updates while the TfL service is being developed.", "GOV.MUK Cabinet Office", "open", now),
        )
    # Upgrade older databases so all six travel levels are supported.
    travel_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='travel_notices'").fetchone()
    if travel_sql and "amber" not in (travel_sql[0] or "").lower():
        db.executescript("""
            ALTER TABLE travel_notices RENAME TO travel_notices_old;
            CREATE TABLE travel_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('white','green','yellow','amber','red','black')),
                headline TEXT NOT NULL,
                details TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO travel_notices(id,country,level,headline,details,updated_at)
            SELECT id,country,level,headline,details,updated_at FROM travel_notices_old;
            DROP TABLE travel_notices_old;
        """)

    # Synchronise the public travel register on fresh and existing databases.
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    travel_register = [
        ("Yellowonia", "yellow", "Travel with increased caution", "Exercise increased caution and review official updates before travel."),
        ("United States", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply."),
        ("Russia", "white", "Status unknown", "Current travel conditions have not been formally assessed by GOV.MUK."),
        ("Ireland", "red", "Avoid all travel", "Do not travel due to active conflict and serious security risks."),
        ("Northern Ireland", "red", "Avoid all travel", "Do not travel due to active conflict and serious security risks."),
        ("UoC", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates."),
        ("Germany", "red", "Avoid all travel", "Do not travel until further notice due to the current security assessment."),
        ("Ukraine", "red", "Avoid all travel", "Do not travel due to conflict and serious security risks."),
        ("Lebanon", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply."),
        ("Brunei", "amber", "Avoid all non-essential travel", "Only essential travel should be considered at this time."),
        ("Finland", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply."),
        ("Israel", "yellow", "Travel with increased caution", "Exercise increased caution and monitor local security updates."),
        ("Cayman Islands", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply."),
        ("Japan", "amber", "Avoid all non-essential travel", "Only essential travel should be considered at this time."),
        ("China", "yellow", "Travel with increased caution", "Exercise increased caution and review entry and security guidance."),
        ("Spain", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates."),
        ("Nigeria", "red", "Avoid all travel", "Do not travel until further notice due to the current security assessment."),
        ("Norway", "green", "Travel at will", "Security conditions are stable. Normal travel precautions apply."),
        ("Maryland", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates."),
        ("South Africa", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates."),
        ("Guinea", "yellow", "Travel with increased caution", "Exercise increased caution and monitor official updates."),
    ]
    for country, level, headline, details in travel_register:
        existing = db.execute("SELECT id FROM travel_notices WHERE lower(country)=lower(?)", (country,)).fetchone()
        if existing:
            db.execute("UPDATE travel_notices SET country=?,level=?,headline=?,details=?,updated_at=? WHERE id=?", (country,level,headline,details,now,existing["id"]))
        else:
            db.execute("INSERT INTO travel_notices(country,level,headline,details,updated_at) VALUES(?,?,?,?,?)", (country,level,headline,details,now))

    # Apply V3 data updates to existing databases as well as fresh installs.
    db.execute(
        "INSERT INTO leaders(office,name,description,sort_order) SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM leaders WHERE office=? OR name=?)",
        ("UK Ambassador to the United Nations", "EuroTyphoon", "Represents MUK at the United Nations and supports multilateral diplomacy.", 4, "UK Ambassador to the United Nations", "EuroTyphoon"),
    )
    db.execute(
        "UPDATE diplomatic_recognition SET relationship=?, notes=?, updated_at=? WHERE country='United States'",
        ("Formal diplomatic recognition with stable bilateral relations.", "Green travel status with stable security conditions.", datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
    )
    db.execute(
        "UPDATE diplomatic_recognition SET relationship=?, notes=?, updated_at=? WHERE country='Germany'",
        ("Formal diplomatic recognition and stable embassy-level relations.", "Green travel status with stable security conditions.", datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
    )
    db.execute(
        "UPDATE emergency_alerts SET region='Ukraine', guidance='Exercise increased caution and review the current travel notice before departure.', updated_at=? WHERE title='Heightened international caution'",
        (datetime.utcnow().strftime("%Y-%m-%d %H:%M"),),
    )
    # Ensure newer diplomatic records are added to existing databases.
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    additional_relations = [
        ("Finland", "recognised", "Formal diplomatic recognition with stable bilateral relations.", "Helsinki", 60.1699, 24.9384, "Stable security conditions and active diplomatic contact.", now),
        ("Lebanon", "recognised", "Formal diplomatic recognition and continued foreign-affairs engagement.", "Beirut", 33.8938, 35.5018, "Diplomatic relations maintained through official channels.", now),
        ("Dominican Republic", "recognised", "Formal diplomatic recognition with developing bilateral relations.", "Santo Domingo", 18.4861, -69.9312, "Stable diplomatic relations and normal official engagement.", now),
    ]
    for relation in additional_relations:
        db.execute(
            "INSERT INTO diplomatic_recognition(country,status,relationship,capital,latitude,longitude,notes,updated_at) "
            "SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM diplomatic_recognition WHERE country=?)",
            (*relation, relation[0]),
        )
    agency_leaders = [
        ("Director of Defence Agencies (MOD)", "Dire Vercetti", "Coordinates the public administration of defence agencies.", 5),
        ("Director of Foreign Affairs Agencies (FCDO)", "Hades", "Coordinates diplomatic and foreign-affairs agencies.", 6),
        ("NHS Chair", "Nathan L Baker", "Chairs the fictional MUK National Health Service.", 7),
        ("Metropolitan Police Commissioner", "Tyler Ashfort", "Leads the fictional Metropolitan Police service.", 8),
    ]
    for office, name, description, sort_order in agency_leaders:
        db.execute(
            "INSERT INTO leaders(office,name,description,sort_order) SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM leaders WHERE office=? AND name=?)",
            (office,name,description,sort_order,office,name),
        )
    db.execute("UPDATE stocks SET name='Bank of England Holdings' WHERE symbol='MUKB'")
    db.commit()
    db.close()


def setting(key):
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def safe_next_url(value, fallback_endpoint):
    """Only allow local redirects generated by this site."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for(fallback_endpoint)


def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="The form expired or could not be verified. Go back, refresh the page and try again.")


@app.context_processor
def inject_globals():
    return {"site_name": setting("site_name"), "csrf_token": get_csrf_token()}


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


@app.route("/asset-check")
def asset_check():
    return {
        "styles_embedded": True,
        "script_embedded": True,
        "static_folder": str(app.static_folder),
    }, 200


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
        ("Bank of England", "Manage an administrator-issued citizen account.", url_for("bank"), "bank of england account credits transfer"),
        ("MUK Exchange", "Trade fictional shares with existing virtual credits.", url_for("markets"), "stocks shares markets exchange"),
        ("Diplomatic recognition", "View recognised states and diplomatic relationships.", url_for("diplomacy"), "diplomacy foreign affairs finland lebanon dominican republic"),
        ("Active operations", "Read public non-sensitive operation summaries.", url_for("operations"), "operations active monitoring defence"),
        ("Emergency centre", "View current public alerts and guidance.", url_for("emergency"), "emergency alerts warning critical guidance"),
        ("Public petitions", "Create and sign roleplay petitions.", url_for("petitions"), "petition petitions signatures public"),
        ("Minister of State for Policing", "Ministerial responsibility for policing and public safety.", url_for("minister_state"), "minister state policing police public safety"),
        ("Active warrants", "View public fictional warrant notices.", url_for("warrants"), "warrant warrants abdul hameed"),
        ("Ministry of Transport", "Transport policy and the developing TfL service.", url_for("transport"), "transport tfl london ministry"),
        ("NHS", "View the fictional national health service and its leadership.", url_for("nhs"), "nhs health hospital nathan baker"),
        ("Metropolitan Police", "View the fictional police service and commissioner.", url_for("police"), "police met metropolitan tyler ashfort"),
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
    notices = get_db().execute("SELECT * FROM travel_notices ORDER BY CASE level WHEN 'black' THEN 1 WHEN 'red' THEN 2 WHEN 'amber' THEN 3 WHEN 'yellow' THEN 4 WHEN 'white' THEN 5 ELSE 6 END,country").fetchall()
    return render_template("travel.html", notices=notices)


@app.route("/travel/<int:item_id>")
def travel_detail(item_id):
    notice = get_db().execute("SELECT * FROM travel_notices WHERE id=?", (item_id,)).fetchone()
    if not notice:
        abort(404)
    return render_template("travel_detail.html", notice=notice)


@app.route("/documents")
def documents():
    docs = get_db().execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
    return render_template("documents.html", documents=docs)




@app.route("/mod")
def mod():
    docs = get_db().execute("SELECT * FROM documents ORDER BY id DESC LIMIT 4").fetchall()
    return render_template("mod.html", documents=docs)



@app.route("/diplomacy")
def diplomacy():
    db = get_db()
    recognition = db.execute("SELECT * FROM diplomatic_recognition ORDER BY country").fetchall()
    operations = db.execute("SELECT * FROM operations ORDER BY CASE status WHEN 'active' THEN 1 WHEN 'monitoring' THEN 2 WHEN 'suspended' THEN 3 ELSE 4 END,name").fetchall()
    return render_template("diplomacy.html", recognition=recognition, operations=operations)


@app.route("/operations")
def operations():
    rows = get_db().execute("SELECT * FROM operations ORDER BY CASE status WHEN 'active' THEN 1 WHEN 'monitoring' THEN 2 WHEN 'suspended' THEN 3 ELSE 4 END,name").fetchall()
    return render_template("operations.html", operations=rows)


@app.route("/emergency")
def emergency():
    db = get_db()
    alerts = db.execute("SELECT * FROM emergency_alerts WHERE active=1 ORDER BY CASE level WHEN 'critical' THEN 1 WHEN 'severe' THEN 2 WHEN 'warning' THEN 3 ELSE 4 END,id DESC").fetchall()
    notices = db.execute("SELECT * FROM travel_notices ORDER BY CASE level WHEN 'black' THEN 1 WHEN 'red' THEN 2 WHEN 'amber' THEN 3 WHEN 'yellow' THEN 4 WHEN 'white' THEN 5 ELSE 6 END,country").fetchall()
    return render_template("emergency.html", alerts=alerts, notices=notices)

@app.route("/warrants")
def warrants():
    rows = get_db().execute("SELECT * FROM warrants ORDER BY CASE status WHEN 'active' THEN 1 WHEN 'suspended' THEN 2 ELSE 3 END,id DESC").fetchall()
    return render_template("warrants.html", warrants=rows)


@app.route("/petitions", methods=["GET","POST"])
def petitions():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        summary = request.form.get("summary", "").strip()
        creator = request.form.get("creator", "").strip()
        if len(title) < 5 or len(summary) < 20 or len(creator) < 2:
            flash("Provide a title, a clear summary and your name.", "error")
        else:
            db.execute(
                "INSERT INTO petitions(title,summary,creator,status,created_at) VALUES(?,?,?,?,?)",
                (title, summary, creator, "pending", datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
            )
            db.commit()
            flash("Petition submitted for review.", "success")
            return redirect(url_for("petitions"))
    rows = db.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM petition_signatures s WHERE s.petition_id=p.id) AS signature_count "
        "FROM petitions p WHERE p.status IN ('open','closed') ORDER BY p.id DESC"
    ).fetchall()
    return render_template("petitions.html", petitions=rows)


@app.route("/petitions/<int:petition_id>")
def petition_detail(petition_id):
    db = get_db()
    petition = db.execute("SELECT * FROM petitions WHERE id=?", (petition_id,)).fetchone()
    if petition is None:
        abort(404)
    signature_count = db.execute("SELECT COUNT(*) FROM petition_signatures WHERE petition_id=?", (petition_id,)).fetchone()[0]
    return render_template("petition_detail.html", petition=petition, signature_count=signature_count)


@app.post("/petitions/<int:petition_id>/sign")
def petition_sign(petition_id):
    db = get_db()
    petition = db.execute("SELECT * FROM petitions WHERE id=? AND status='open'", (petition_id,)).fetchone()
    if not petition:
        abort(404)
    signer = request.form.get("signer", "").strip()
    if len(signer) < 2:
        flash("Enter your name to sign this petition.", "error")
    else:
        try:
            db.execute(
                "INSERT INTO petition_signatures(petition_id,signer,signed_at) VALUES(?,?,?)",
                (petition_id, signer, datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
            )
            db.commit()
            flash("Petition signed.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("That name has already signed this petition.", "error")
    return redirect(url_for("petitions"))


@app.route("/transport")
def transport():
    return render_template("transport.html")


@app.route("/transport/tfl")
def tfl():
    return render_template("tfl.html")


@app.route("/nhs")
def nhs():
    return render_template("nhs.html")


@app.route("/government/minister-of-state-policing")
def minister_state():
    return render_template("minister_state.html")


@app.route("/police")
def police():
    return render_template("police.html")


@app.route("/citizen/login", methods=["GET","POST"])
def citizen_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM citizens WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["citizen_id"] = user["id"]
            return redirect(safe_next_url(request.args.get("next"), "bank"))
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
            db.execute("BEGIN IMMEDIATE")
            latest_sender = db.execute("SELECT balance FROM citizens WHERE id=?", (citizen_id,)).fetchone()
            if not latest_sender or latest_sender["balance"] < amount:
                db.rollback(); flash("Insufficient credits.", "error"); return redirect(url_for("bank"))
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
            else:
                flash("Invalid trade action.", "error")
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
        recognition=db.execute("SELECT * FROM diplomatic_recognition ORDER BY country").fetchall(),
        operations=db.execute("SELECT * FROM operations ORDER BY id DESC").fetchall(),
        alerts=db.execute("SELECT * FROM emergency_alerts ORDER BY active DESC,id DESC").fetchall(),
        warrants=db.execute("SELECT * FROM warrants ORDER BY id DESC").fetchall(),
        petitions=db.execute("SELECT p.*, (SELECT COUNT(*) FROM petition_signatures s WHERE s.petition_id=p.id) AS signature_count FROM petitions p ORDER BY id DESC").fetchall(),
        stats={
            "active_alerts": db.execute("SELECT COUNT(*) FROM emergency_alerts WHERE active=1").fetchone()[0],
            "active_operations": db.execute("SELECT COUNT(*) FROM operations WHERE status='active'").fetchone()[0],
            "recognised_states": db.execute("SELECT COUNT(*) FROM diplomatic_recognition WHERE status='recognised'").fetchone()[0],
            "documents": db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "active_warrants": db.execute("SELECT COUNT(*) FROM warrants WHERE status='active'").fetchone()[0],
            "open_petitions": db.execute("SELECT COUNT(*) FROM petitions WHERE status='open'").fetchone()[0],
        },
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
    db=get_db(); item_id=request.form.get("id")
    level=request.form.get("level", "white").lower()
    if level not in {"white","green","yellow","amber","red","black"}:
        flash("Invalid travel level.", "error")
        return redirect(url_for("admin_dashboard"))
    vals=(request.form["country"],level,request.form["headline"],request.form["details"],datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
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
    db=get_db(); item_id=request.form.get("id"); vals=(request.form["office"].strip(),request.form["name"].strip(),request.form["description"].strip(),int(parse_float(request.form.get("sort_order",0),0)))
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


@app.post("/admin/recognition/save")
@admin_required
def admin_recognition_save():
    db=get_db(); item_id=request.form.get("id")
    vals=(request.form["country"],request.form["status"],request.form["relationship"],request.form.get("capital",""),parse_float(request.form.get("latitude"),0),parse_float(request.form.get("longitude"),0),request.form.get("notes",""),datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    try:
        if item_id: db.execute("UPDATE diplomatic_recognition SET country=?,status=?,relationship=?,capital=?,latitude=?,longitude=?,notes=?,updated_at=? WHERE id=?",(*vals,item_id))
        else: db.execute("INSERT INTO diplomatic_recognition(country,status,relationship,capital,latitude,longitude,notes,updated_at) VALUES(?,?,?,?,?,?,?,?)",vals)
        db.commit(); flash("Diplomatic recognition entry saved.","success")
    except sqlite3.IntegrityError:
        db.rollback(); flash("That country already has a diplomatic record.", "error")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/recognition/delete/<int:item_id>")
@admin_required
def admin_recognition_delete(item_id):
    get_db().execute("DELETE FROM diplomatic_recognition WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))

@app.post("/admin/operation/save")
@admin_required
def admin_operation_save():
    db=get_db(); item_id=request.form.get("id")
    vals=(request.form["name"],request.form["region"],request.form["status"],request.form["department"],request.form["summary"],parse_float(request.form.get("latitude"),0),parse_float(request.form.get("longitude"),0),datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    if item_id: db.execute("UPDATE operations SET name=?,region=?,status=?,department=?,summary=?,latitude=?,longitude=?,updated_at=? WHERE id=?",(*vals,item_id))
    else: db.execute("INSERT INTO operations(name,region,status,department,summary,latitude,longitude,updated_at) VALUES(?,?,?,?,?,?,?,?)",vals)
    db.commit(); flash("Operation saved.","success"); return redirect(url_for("admin_dashboard"))

@app.post("/admin/operation/delete/<int:item_id>")
@admin_required
def admin_operation_delete(item_id):
    get_db().execute("DELETE FROM operations WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))

@app.post("/admin/emergency/save")
@admin_required
def admin_emergency_save():
    db=get_db(); item_id=request.form.get("id")
    vals=(request.form["title"],request.form["level"],request.form["region"],request.form["guidance"],1 if request.form.get("active")=="1" else 0,datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    if item_id: db.execute("UPDATE emergency_alerts SET title=?,level=?,region=?,guidance=?,active=?,updated_at=? WHERE id=?",(*vals,item_id))
    else: db.execute("INSERT INTO emergency_alerts(title,level,region,guidance,active,updated_at) VALUES(?,?,?,?,?,?)",vals)
    db.commit(); flash("Emergency alert saved.","success"); return redirect(url_for("admin_dashboard"))

@app.post("/admin/emergency/delete/<int:item_id>")
@admin_required
def admin_emergency_delete(item_id):
    get_db().execute("DELETE FROM emergency_alerts WHERE id=?",(item_id,)); get_db().commit(); return redirect(url_for("admin_dashboard"))


@app.post("/admin/warrant/save")
@admin_required
def admin_warrant_save():
    db = get_db(); item_id = request.form.get("id")
    status = request.form.get("status", "active")
    if status not in {"active", "suspended", "closed"}:
        flash("Invalid warrant status.", "error")
        return redirect(url_for("admin_dashboard"))
    vals = (
        request.form.get("subject", "").strip(), status,
        request.form.get("reference", "").strip(),
        request.form.get("summary", "").strip(),
        request.form.get("issued_at", "").strip(),
        datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )
    if item_id:
        db.execute("UPDATE warrants SET subject=?,status=?,reference=?,summary=?,issued_at=?,updated_at=? WHERE id=?", (*vals, item_id))
    else:
        db.execute("INSERT INTO warrants(subject,status,reference,summary,issued_at,updated_at) VALUES(?,?,?,?,?,?)", vals)
    db.commit(); flash("Warrant record saved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/warrant/delete/<int:item_id>")
@admin_required
def admin_warrant_delete(item_id):
    get_db().execute("DELETE FROM warrants WHERE id=?", (item_id,)); get_db().commit()
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/petition/status/<int:item_id>")
@admin_required
def admin_petition_status(item_id):
    status = request.form.get("status", "pending")
    if status not in {"pending", "open", "closed", "rejected"}:
        flash("Invalid petition status.", "error")
        return redirect(url_for("admin_dashboard"))
    get_db().execute("UPDATE petitions SET status=? WHERE id=?", (status, item_id)); get_db().commit()
    flash("Petition status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/petition/delete/<int:item_id>")
@admin_required
def admin_petition_delete(item_id):
    get_db().execute("DELETE FROM petitions WHERE id=?", (item_id,)); get_db().commit()
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, title="Bad request", message=getattr(error, "description", "The request could not be processed.")), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, title="Page not found", message="Check the address or use the GOV.MUK search to find a service."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500, title="Service unavailable", message="The service encountered a problem. Try again shortly."), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=os.environ.get("FLASK_DEBUG")=="1")
