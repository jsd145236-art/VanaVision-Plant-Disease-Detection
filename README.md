# VanaVision — Herbal Plant Disease Identification

A Flask application that wraps the supplied MobileNetV3-Small checkpoint and disease reference dataset in a responsive botanical research interface.

## Preserved model assets
- `model/mobilenet_v3_small_best.pth` — copied byte-for-byte from the uploaded checkpoint.
- `model_loader.py` — supplied MobileNetV3-Small architecture, 31 output classes and checkpoint loading.
- `app.py` — supplied class order, 224×224 resize, RGB conversion, ImageNet normalization, softmax and top-5 inference.
- `data/disease_info_database.json` — supplied disease reference content, copied without edits.

No retraining or model replacement is performed. Predictions are produced by the trained checkpoint, not hardcoded.

## Features
- Responsive botanical landing page and plant library derived from the supplied dataset.
- Registration, login, password hashing, session-protected workspace and profile/password update.
- Image upload and browser-camera capture (camera requires HTTPS or localhost).
- Real model inference, top-5 scores, result report and print option.
- User-scoped prediction history and dashboard counts.
- Search across supported plant and disease classes.
- MongoDB Atlas support when `MONGO_URI` is configured. A local SQLite fallback is used when it is blank.

## Run locally (VS Code / PowerShell)

1. Install Python 3.10 or 3.11 (recommended), then:

   ```powershell
   cd Vanavision
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set a strong `SECRET_KEY`. For Atlas, set `MONGO_URI` and `MONGO_DB_NAME`. Keep credentials private.
3. Run `python app.py`.
4. Open `http://127.0.0.1:5000`.

PyTorch loads the supplied checkpoint from `model/mobilenet_v3_small_best.pth`. The original loader configures CPU inference.

## MongoDB Atlas
1. Create an Atlas cluster and database user.
2. Add your development IP to Atlas Network Access.
3. Put the Python connection string in `.env` as `MONGO_URI`.
4. Set `MONGO_DB_NAME=vanavision` and restart.

When `MONGO_URI` is empty, local SQLite storage is used at `instance/vanavision.sqlite3`. Existing SQLite records are not automatically migrated to MongoDB.

## Deployment
This is a conventional Flask/PyTorch server and needs a Python host with persistent model files and sufficient memory (for example, Render, Railway, a VM or another container/Python host). Vercel alone is not suitable for this full PyTorch/Flask inference backend. A separately deployed frontend can call a Flask API hosted on a compatible Python service.

Production command:

```bash
gunicorn --workers 1 --threads 4 --timeout 120 app:app
```

Set `SECRET_KEY`, `MONGO_URI`, `MONGO_DB_NAME`, and `COOKIE_SECURE=1` behind HTTPS. Disable debug mode. For multi-instance deployments, move uploaded images from local `static/uploads` to durable object storage and serve them through authenticated URLs.

## Folder structure

```text
Vanavision/
├── app.py
├── model_loader.py
├── model/mobilenet_v3_small_best.pth
├── data/disease_info_database.json
├── templates/
│   ├── base.html, index.html, auth.html
│   ├── dashboard.html, detect.html, result.html
│   └── plants.html, history.html, profile.html
├── static/
│   ├── css/style.css
│   ├── js/main.js, detect.js
│   ├── images/botanical-hero.png
│   └── uploads/
├── instance/                 # SQLite fallback, created at runtime
├── .env.example
├── requirements.txt
└── README.md
```

## Verification status and limitations
Python source syntax was checked during packaging. This execution environment did not have Flask or PyMongo installed, so a live Flask server, browser camera, Atlas connection, registration/login flow and end-to-end web inference could not be run here. Install the requirements and test locally before treating the deployment as production-verified.

The uploaded video is a short filmed screen recording; this implementation follows its dark editorial visual direction together with the botanical screenshot. The generated hero image is decorative artwork. Plant library tiles use botanical-inspired CSS artwork, not verified photographs of each individual species.
