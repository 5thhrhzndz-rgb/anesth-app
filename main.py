from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from pathlib import Path
from pypdf import PdfReader
from urllib.parse import quote
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends
import secrets
import sqlite3
from datetime import date
from fastapi import Form



security = HTTPBasic()

app = FastAPI(title="Anesth-App", dependencies=[Depends(check_auth)])


def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "HPPS")
    correct_password = secrets.compare_digest(credentials.password, "HPPS*")

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Accès refusé",
            headers={"WWW-Authenticate": "Basic"},
        )


# Servir les fichiers statiques (image de fond)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Helpers ---
def inline_file(path: Path, media_type: str):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier introuvable: {path}")
    return FileResponse(
        str(path),
        media_type=media_type,
        headers={"Content-Disposition": "inline"},
    )


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
        text += "\n"
    return text


# --- Modèles / Données en mémoire ---
class Protocol(BaseModel):
    title: str
    content: str


protocols: List[Protocol] = []


# --- Routes de base ---
@app.get("/")
def root():
    return {"status": "Anesth-App opérationnelle"}


@app.get("/home", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body {
                margin: 0;
                min-height: 100vh;
                background: #111;
                font-family: Arial, sans-serif;
                color: white;
            }
            .bg {
                position: fixed;
                inset: 0;
                background-image: url('/static/hpps.png');
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                opacity: 0.35;
                z-index: -1;
            }
            .content { padding: 24px; }
            .card {
                background: rgba(0,0,0,0.55);
                padding: 16px;
                border-radius: 12px;
                max-width: 720px;
            }
            a { color: #fff; }
        </style>
    </head>
    <body>
        <div class="bg"></div>
        <div class="content">
            <div class="card">
                <h1>HPPS – Anesthésie</h1>
                <p><a href="/documents">📚 Ouvrir la bibliothèque de PDFs</a></p>
            </div>
        </div>
    </body>
    </html>
    """


# --- Protocoles texte ---
@app.get("/protocols", response_model=List[Protocol])
def get_protocols():
    return protocols


@app.post("/protocols")
def add_protocol(protocol: Protocol):
    protocols.append(protocol)
    return {"message": "Protocole ajouté"}


# --- PDFs spécifiques ---
@app.get("/pdf/kt")
def get_pdf_kt():
    file_path = Path(__file__).parent / "docs" / "KT.pdf"
    return inline_file(file_path, "application/pdf")


@app.get("/antibioprophylaxie/sfar")
def get_antibio_sfar():
    file_path = (
        Path(__file__).parent
        / "Recommandations"
        / "antibioprophylaxie"
        / "antibioprophylaxieSFAR.pdf"
    )
    return inline_file(file_path, "application/pdf")


@app.get("/hemostase/gihp")
def get_hemostase_gihp():
    file_path = (
        Path(__file__).parent
        / "Recommandations"
        / "hemostase-coagulation"
        / "thromboprophylaxieGIHP.pdf"
    )
    return inline_file(file_path, "application/pdf")


# --- Planning Excel (souvent téléchargé par le navigateur, normal) ---
@app.get("/planning/xlsx")
def get_planning_xlsx():
    file_path = Path(__file__).parent / "planning" / "planning.xlsx"
    return inline_file(
        file_path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Recherche simple dans le PDF SFAR antibio ---
@app.get("/search/simple")
def search_simple(query: str):
    pdf_path = (
        Path(__file__).parent
        / "Recommandations"
        / "antibioprophylaxie"
        / "antibioprophylaxieSFAR.pdf"
    )

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF introuvable: {pdf_path}")

    text = read_pdf_text(pdf_path)
    results = [line for line in text.split("\n") if query.lower() in line.lower()]
    return {"results": results[:10]}


# --- Bibliothèque générique ---
@app.get("/list")
def list_pdfs():
    base = Path(__file__).parent
    pdfs = sorted([str(p.relative_to(base)) for p in base.rglob("*.pdf")])
    return {"pdfs": pdfs}


@app.get("/open")
def open_pdf(path: str):
    file_path = Path(__file__).parent / path
    return inline_file(file_path, "application/pdf")


@app.get("/documents", response_class=HTMLResponse)
def documents():
    base = Path(__file__).parent
    pdfs = sorted([p.relative_to(base) for p in base.rglob("*.pdf")])

    html = """
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body { font-family: Arial, sans-serif; padding: 16px; }
        input { width: 100%; padding: 10px; font-size: 16px; margin: 12px 0; }
        ul { list-style: none; padding: 0; }
        li { padding: 8px 0; border-bottom: 1px solid #eee; }
        a { text-decoration: none; }
      </style>
    </head>
    <body>
      <h1>Documents</h1>
      <p><a href="/home">🏠 Accueil</a></p>
      <input id="q" placeholder="Rechercher un PDF..." oninput="filter()"/>
      <ul id="list">
    """

    for p in pdfs:
        html += f'<li><a href="/open?path={quote(str(p))}">{p}</a></li>'

    html += """
      </ul>
      <script>
        function filter() {
          const q = document.getElementById('q').value.toLowerCase();
          const items = document.querySelectorAll('#list li');
          items.forEach(li => {
            li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
          });
        }
      </script>
    </body>
    </html>
    """
    return html
# =========================
# DB (badgeuse + messagerie)
# =========================
DB_PATH = Path(__file__).parent / "app.db"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    # Badgeuse : 1 ligne par (employee, day)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS badge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT NOT NULL,
            day TEXT NOT NULL,                 -- YYYY-MM-DD
            start_time TEXT,                   -- HH:MM
            end_time TEXT,                     -- HH:MM
            UNIQUE(employee, day)
        )
    """)
    # Chat
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

IADE_NAMES = [
    "Romain", "Amel", "Philippe", "Fabrice", "Catherine",
    "Florent", "Patricia P", "Patricia L", "Helena"
]

# =========
# BADGEUSE
# =========
@app.get("/badge", response_class=HTMLResponse)
def badge_page():
    today = date.today().isoformat()
    options = "\n".join([f'<option value="{n}">{n}</option>' for n in IADE_NAMES])

    return f"""
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body {{ font-family: Arial, sans-serif; padding: 16px; max-width: 520px; margin: 0 auto; }}
        label {{ display:block; margin-top: 14px; font-weight: 600; }}
        select, input, button {{ width: 100%; padding: 14px; font-size: 16px; margin-top: 8px; }}
        button {{ cursor: pointer; }}
        .row {{ display:flex; gap:12px; }}
        .row > div {{ flex:1; }}
        .hint {{ color:#555; font-size: 14px; }}
        .card {{ border:1px solid #eee; border-radius:12px; padding:14px; margin-top:14px; }}
      </style>
    </head>
    <body>
      <h1>Badgeuse IADE</h1>
      <p class="hint">Choisis ton nom une fois : il sera mémorisé sur ton appareil.</p>

      <div class="card">
        <label>Nom</label>
        <select id="employee">
          <option value="">— Choisir —</option>
          {options}
        </select>

        <label>Date</label>
        <input id="day" type="date" value="{today}" />

        <div class="row">
          <div>
            <label>Heure début</label>
            <input id="start_time" type="time" />
          </div>
          <div>
            <label>Heure fin</label>
            <input id="end_time" type="time" />
          </div>
        </div>

        <button onclick="submitEntry()">💾 Enregistrer</button>
        <p class="hint" id="msg"></p>
      </div>

      <p><a href="/badge/day?day={today}">Voir la journée (JSON)</a></p>

      <script>
        const employeeEl = document.getElementById('employee');
        const saved = localStorage.getItem('badge_employee');
        if(saved) employeeEl.value = saved;

        employeeEl.addEventListener('change', () => {{
          if(employeeEl.value) localStorage.setItem('badge_employee', employeeEl.value);
        }});

        async function submitEntry() {{
          const employee = employeeEl.value;
          const day = document.getElementById('day').value;
          const start_time = document.getElementById('start_time').value;
          const end_time = document.getElementById('end_time').value;

          if(!employee) return show("Choisis ton nom.");
          if(!day) return show("Choisis une date.");
          if(!start_time && !end_time) return show("Renseigne au moins une heure.");

          const form = new URLSearchParams();
          form.append("employee", employee);
          form.append("day", day);
          form.append("start_time", start_time);
          form.append("end_time", end_time);

          const res = await fetch("/badge/entry", {{
            method: "POST",
            headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
            body: form.toString()
          }});

          const data = await res.json();
          if(!res.ok) return show(data.detail || "Erreur.");
          show("Enregistré ✅");
        }}

        function show(t) {{
          document.getElementById('msg').textContent = t;
        }}
      </script>
    </body>
    </html>
    """

@app.post("/badge/entry")
def badge_upsert(
    employee: str = Form(...),
    day: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form("")
):
    if employee not in IADE_NAMES:
        raise HTTPException(status_code=400, detail="Employé inconnu")

    conn = db()
    conn.execute("""
        INSERT INTO badge_entries (employee, day, start_time, end_time)
        VALUES (?, ?, NULLIF(?, ''), NULLIF(?, ''))
        ON CONFLICT(employee, day) DO UPDATE SET
            start_time = COALESCE(NULLIF(excluded.start_time, ''), badge_entries.start_time),
            end_time   = COALESCE(NULLIF(excluded.end_time, ''), badge_entries.end_time)
    """, (employee, day, start_time, end_time))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/badge/day")
def badge_day(day: str):
    conn = db()
    rows = conn.execute("""
        SELECT employee, day, start_time, end_time
        FROM badge_entries
        WHERE day = ?
        ORDER BY employee ASC
    """, (day,)).fetchall()
    conn.close()
    return {"day": day, "entries": [dict(r) for r in rows]}

# ===========
# MESSAGERIE
# ===========
@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    options = "\n".join([f'<option value="{n}">{n}</option>' for n in IADE_NAMES])
    return f"""
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body {{ font-family: Arial, sans-serif; padding: 16px; max-width: 720px; margin: 0 auto; }}
        select, textarea, button {{ width: 100%; padding: 12px; font-size: 16px; margin: 8px 0; }}
        textarea {{ height: 110px; }}
        .msg {{ border: 1px solid #eee; border-radius: 12px; padding: 10px 12px; margin: 10px 0; }}
        .meta {{ color: #666; font-size: 13px; margin-bottom: 6px; }}
        .row {{ display:flex; gap: 10px; }}
        .row > * {{ flex: 1; }}
      </style>
    </head>
    <body>
      <h1>Messagerie équipe</h1>
      <p><a href="/home">🏠 Accueil</a></p>

      <div class="row">
        <select id="sender">
          <option value="">— Qui es-tu ? —</option>
          {options}
        </select>
        <button onclick="refresh()">🔄 Rafraîchir</button>
      </div>

      <textarea id="content" placeholder="Écris un message (pas de données patient)"></textarea>
      <button onclick="send()">📨 Envoyer</button>
      <p id="status"></p>

      <h2>Derniers messages</h2>
      <div id="feed"></div>

      <script>
        const senderEl = document.getElementById('sender');
        const saved = localStorage.getItem('chat_sender');
        if(saved) senderEl.value = saved;
        senderEl.addEventListener('change', () => {{
          if(senderEl.value) localStorage.setItem('chat_sender', senderEl.value);
        }});

        async function refresh() {{
          const res = await fetch('/chat/messages');
          const data = await res.json();
          const feed = document.getElementById('feed');
          feed.innerHTML = '';
          (data.messages || []).forEach(m => {{
            const div = document.createElement('div');
            div.className = 'msg';
            div.innerHTML = `<div class="meta"><b>${{m.sender}}</b> — ${{m.created_at}}</div><div>${{escapeHtml(m.content)}}</div>`;
            feed.appendChild(div);
          }});
        }}

        async function send() {{
          const sender = senderEl.value;
          const content = document.getElementById('content').value.trim();
          if(!sender) return setStatus("Choisis ton nom.");
          if(!content) return setStatus("Écris un message.");
          if(content.length > 1000) return setStatus("Message trop long (max 1000).");

          const form = new URLSearchParams();
          form.append('sender', sender);
          form.append('content', content);

          const res = await fetch('/chat/send', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
            body: form.toString()
          }});

          const data = await res.json();
          if(!res.ok) return setStatus(data.detail || "Erreur");
          document.getElementById('content').value = '';
          setStatus("Envoyé ✅");
          refresh();
        }}

        function setStatus(t) {{
          document.getElementById('status').textContent = t;
        }}

        function escapeHtml(s) {{
          return s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
        }}

        refresh();
        setInterval(refresh, 8000);
      </script>
    </body>
    </html>
    """

from datetime import datetime

@app.post("/chat/send")
def chat_send(sender: str = Form(...), content: str = Form(...)):
    if sender not in IADE_NAMES:
        raise HTTPException(status_code=400, detail="Expéditeur invalide")
    content = content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message vide")
    if len(content) > 1000:
        raise HTTPException(status_code=400, detail="Message trop long")

    conn = db()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO chat_messages (sender, created_at, content) VALUES (?, ?, ?)",
        (sender, now, content),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/chat/messages")
def chat_messages(limit: int = 50):
    limit = max(1, min(limit, 200))
    conn = db()
    rows = conn.execute(
        "SELECT sender, created_at, content FROM chat_messages ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    messages = [dict(r) for r in rows][::-1]
    return {"messages": messages}
    