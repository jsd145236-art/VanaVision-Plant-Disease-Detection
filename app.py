import os, json, uuid, sqlite3, secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "change-this-secret-before-deployment"),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,

    UPLOAD_FOLDER=str(Path(os.getenv("DATA_DIR", str(BASE_DIR / "instance"))) / "uploads"),

    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1"
)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "instance")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vanavision.sqlite3"


DB_PATH.parent.mkdir(exist_ok=True)
MONGO_URI = os.getenv("MONGO_URI", "").strip()
_mongo = None

CLASS_NAMES = [
    "Aloevera_Anthracnose", "Aloevera_Healthy", "Aloevera_Leaf_Spot",
    "Brahmi_Healthy", "Brahmi_Leaf_Spot", "Camphor_Healthy", "Camphor_Leaf_Spot",
    "Harad_Healthy", "Harad_Leaf_Spot", "Hibiscus_ Wrinkled_Leaf", "Hibiscus_Healthy",
    "Hibiscus_Leaf_Spot", "Moringa_Bacterial_Leaf_Spot", "Moringa_Cercospora_Leaf_Spot",
    "Moringa_Healthy", "Moringa_Yellow_Leaf", "Neem_Healthy", "Neem_Leaf_Spot",
    "Patharchatta_Healthy", "Patharchatta_Leaf_Blight", "Piper_Betal_Healthy",
    "Piper_Betal_Leaf_Spot", "Piper_Betal_Yellow_Leaf", "Tamarind_Healthy",
    "Tamarind_Leaf_Spot", "Tamarind_Powdery_Mildew", "Tulsi_Downy_Mildew",
    "Tulsi_Healthy", "Tulsi_Leaf_Spot", "Turmeric_Healthy", "Turmeric_leaf_spot"
]
with open(BASE_DIR / "data" / "disease_info_database.json", encoding="utf-8-sig") as f:
    DISEASE_INFO = json.load(f)

def db_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db_conn() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS predictions (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, image_path TEXT NOT NULL,
            predicted_class TEXT NOT NULL, confidence REAL NOT NULL, top5 TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""")
init_db()

def mongo_db():
    global _mongo
    if not MONGO_URI:
        return None
    if _mongo is None:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
        client.admin.command("ping")
        _mongo = client[os.getenv("MONGO_DB_NAME", "vanavision")]
    return _mongo

def store_user(name, email, password_hash):
    db = mongo_db()
    created = datetime.now(timezone.utc).isoformat()
    if db is not None:
        if db.users.find_one({"email": email}):
            return None
        result = db.users.insert_one({"name": name, "email": email, "password_hash": password_hash, "created_at": created})
        return str(result.inserted_id)
    try:
        with db_conn() as con:
            cur = con.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                              (name,email,password_hash,created))
            return str(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None

def get_user_by_email(email):
    db = mongo_db()
    if db is not None:
        return db.users.find_one({"email": email})
    with db_conn() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

def get_user(user_id):
    db = mongo_db()
    if db is not None:
        from bson import ObjectId
        try: return db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
        except Exception: return None
    with db_conn() as con:
        row = con.execute("SELECT id,name,email,created_at FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

def update_user(user_id, name, password_hash=None):
    db = mongo_db()
    if db is not None:
        from bson import ObjectId
        oid = ObjectId(user_id)
        payload = {"name": name}
        if password_hash: payload["password_hash"] = password_hash
        db.users.update_one({"_id": oid}, {"$set": payload})
        return
    with db_conn() as con:
        if password_hash:
            con.execute("UPDATE users SET name=?, password_hash=? WHERE id=?", (name,password_hash,user_id))
        else:
            con.execute("UPDATE users SET name=? WHERE id=?", (name,user_id))

def save_prediction(user_id, image_path, predicted_class, confidence, top5):
    db = mongo_db()
    record = {"id": uuid.uuid4().hex, "user_id": user_id, "image_path": image_path,
              "predicted_class": predicted_class, "confidence": float(confidence),
              "top5": top5, "created_at": datetime.now(timezone.utc).isoformat()}
    if db is not None:
        db.predictions.insert_one(record)
    else:
        with db_conn() as con:
            con.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?,?)",
                        (record["id"], user_id, image_path, predicted_class, confidence,
                         json.dumps(top5), record["created_at"]))
    return record

def user_predictions(user_id, limit=100, offset=0):
    db = mongo_db()
    if db is not None:
        return list(db.predictions.find({"user_id": user_id}).sort("created_at", -1).skip(offset).limit(limit))
    with db_conn() as con:
        rows = con.execute("SELECT * FROM predictions WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                           (user_id,limit,offset)).fetchall()
        items=[]
        for r in rows:
            x=dict(r); x["top5"]=json.loads(x["top5"]); items.append(x)
        return items

def user_stats(user_id):
    records = user_predictions(user_id, limit=10000)
    healthy = sum(1 for r in records if DISEASE_INFO.get(r["predicted_class"],{}).get("status") == "Healthy")
    return {"total":len(records), "healthy":healthy, "diseased":len(records)-healthy}

def get_prediction(user_id, prediction_id):
    db = mongo_db()
    if db is not None:
        return db.predictions.find_one({"id":prediction_id,"user_id":user_id})
    with db_conn() as con:
        row=con.execute("SELECT * FROM predictions WHERE id=? AND user_id=?", (prediction_id,user_id)).fetchone()
        if not row: return None
        x=dict(row); x["top5"]=json.loads(x["top5"]); return x

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def current_user():
    return get_user(session["user_id"]) if session.get("user_id") else None

def model_predict(image):
    # Keep the original MobileNetV3-Small architecture and preprocessing unchanged.
    import torch
    from torchvision import transforms
    from model_loader import model, DEVICE
    transform = transforms.Compose([
        transforms.Resize((224, 224)), transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
    ])
    tensor = transform(image.convert("RGB")).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        probs = torch.softmax(model(tensor), dim=1)
        count = min(5, probs.shape[1])
        values, indices = torch.topk(probs, count, dim=1)
    top = [{"class_name": CLASS_NAMES[int(indices[0][i])],
            "confidence": round(float(values[0][i]) * 100, 2)} for i in range(count)]
    return top[0]["class_name"], top[0]["confidence"], top

def plant_catalog():
    grouped={}
    for key, info in DISEASE_INFO.items():
        plant=info.get("plant") or key.split("_")[0]
        grouped.setdefault(plant, {"name":plant,"classes":[],"diseases":[]})
        grouped[plant]["classes"].append(key)
        disease=info.get("disease")
        if disease and disease != "None" and disease not in grouped[plant]["diseases"]:
            grouped[plant]["diseases"].append(disease)
    return list(grouped.values())

@app.context_processor
def inject_globals():
    return {"current_user": current_user(), "year": datetime.now().year}

@app.route("/")
def home():
    return render_template("index.html", plants=plant_catalog()[:8], plant_count=len(plant_catalog()), class_count=len(CLASS_NAMES))


@app.route("/sitemap.xml")
def sitemap():
    pages = [
        url_for("home", _external=True),
    ]

    xml = render_template("sitemap.xml", pages=pages)
    return app.response_class(xml, mimetype="application/xml")


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        confirm=request.form.get("confirm_password","")
        if not name or len(name)>80 or "@" not in email or len(password)<8:
            flash("Enter a valid name and email. Password must be at least 8 characters.", "danger")
        elif password != confirm:
            flash("Your passwords do not match.", "danger")
        else:
            uid=store_user(name,email,generate_password_hash(password))
            if uid:
                session.clear(); session["user_id"]=uid
                flash("Your VanaVision account is ready.", "success")
                return redirect(url_for("dashboard"))
            flash("An account with that email already exists.", "danger")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        user=get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], request.form.get("password","")):
            session.clear(); session["user_id"]=str(user.get("_id") or user.get("id"))
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "danger")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear(); flash("You have been signed out.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    stats=user_stats(session["user_id"])
    recent=user_predictions(session["user_id"], limit=5)
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/detect", methods=["GET","POST"])
@login_required
def detect():
    if request.method=="POST":
        file=request.files.get("image")
        if not file or not file.filename:
            flash("Choose a plant image first.", "danger"); return redirect(url_for("detect"))
        ext=secure_filename(file.filename).rsplit(".",1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            flash("Please upload a JPG, PNG or WEBP image.", "danger"); return redirect(url_for("detect"))
        try:
            image=Image.open(file.stream)
            image.verify()
            file.stream.seek(0)
            image=Image.open(file.stream).convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError):
            flash("That file is not a valid image. Please try another photograph.", "danger")
            return redirect(url_for("detect"))
        filename=f"{uuid.uuid4().hex}.{ext}"
        target=Path(app.config["UPLOAD_FOLDER"])/filename
        image.save(target, format="JPEG" if ext in {"jpg","jpeg"} else ("PNG" if ext=="png" else "WEBP"))
        try:
            predicted, confidence, top5=model_predict(image)
        except Exception as exc:
            app.logger.exception("Model inference failed")
            target.unlink(missing_ok=True)
            flash("The prediction model could not process this image. Check model setup and server logs.", "danger")
            return redirect(url_for("detect"))
        record=save_prediction(session["user_id"], f"uploads/{filename}", predicted, confidence, top5)
        return redirect(url_for("result", prediction_id=record["id"]))
    return render_template("detect.html")

@app.route("/result/<prediction_id>")
@login_required
def result(prediction_id):
    record=get_prediction(session["user_id"], prediction_id)
    if not record: abort(404)
    info=DISEASE_INFO.get(record["predicted_class"], {})
    return render_template("result.html", record=record, info=info)

@app.route("/plants")
@login_required
def plants():
    q=request.args.get("q","").strip().lower()
    catalog=plant_catalog()
    if q:
        catalog=[p for p in catalog if q in p["name"].lower() or any(q in c.lower() for c in p["classes"]+p["diseases"])]
    return render_template("plants.html", plants=catalog, query=q)

@app.route("/api/search")
@login_required
def search_api():
    q=request.args.get("q","").strip().lower()
    if len(q)<2: return jsonify([])
    out=[]
    for key, info in DISEASE_INFO.items():
        plant=info.get("plant","")
        disease=info.get("disease","")
        hay=" ".join([key,plant,disease,info.get("symptoms","")]).lower()
        if q in hay:
            out.append({"class_name":key,"plant":plant,"disease":disease,"status":info.get("status")})
    return jsonify(out[:12])

@app.route("/history")
@login_required
def history():
    q=request.args.get("q","").strip().lower()
    records=user_predictions(session["user_id"], limit=200)
    if q:
        records=[r for r in records if q in r["predicted_class"].lower() or q in DISEASE_INFO.get(r["predicted_class"],{}).get("plant","").lower()]
    return render_template("history.html", records=records, query=q)

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    user=current_user()
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if not name:
            flash("Name cannot be empty.", "danger")
        else:
            pwd_hash=None
            new_password=request.form.get("new_password","")
            if new_password:
                if len(new_password)<8 or not check_password_hash(get_user_by_email(user["email"])["password_hash"],request.form.get("current_password","")):
                    flash("Enter your current password and a new password of at least 8 characters.", "danger")
                    return redirect(url_for("profile"))
                pwd_hash=generate_password_hash(new_password)
            update_user(session["user_id"],name,pwd_hash)
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", user=user, stats=user_stats(session["user_id"]))

@app.errorhandler(413)
def too_large(_):
    flash("Image is too large. Maximum upload size is 10 MB.", "danger")
    return redirect(url_for("detect"))

print(app.url_map)

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG","0")=="1")
