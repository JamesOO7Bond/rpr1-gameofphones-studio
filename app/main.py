"""RPR1. Game of Phones – Studio-Dashboard.

Ein Web-Dienst, der im Studio die iPhone-KI startet, stummschaltet und
beendet. Nur aus dem ATSW-Netz erreichbar (IP-Sperre) und zusätzlich mit
Zugangscode. Vergibt pro Runde die nächste Region und merkt sich, welche
Lösungen zuletzt gespielt wurden.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import elevenlabs
from .access import COOKIE_MAX_AGE, COOKIE_NAME, CodePolicy, IpPolicy
from .questions import CATEGORIES, QuestionPool
from .store import RoundStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("gop")

AGENT_ID = os.environ.get("AGENT_ID", "agent_0901m4tq89w0eha9a8v0swg8770h").strip()
CONNECTION_TYPE = os.environ.get("CONNECTION_TYPE", "websocket").strip().lower()
MOCK = os.environ.get("MOCK_ELEVENLABS", "").strip() == "1"
VERSION = (os.environ.get("RENDER_GIT_COMMIT") or "dev")[:7]

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RPR1. Game of Phones Studio", docs_url=None, redoc_url=None, openapi_url=None)
ip_policy = IpPolicy()
code_policy = CodePolicy()
pool = QuestionPool()
store = RoundStore(AGENT_ID)

# Pfade, die ohne IP-Sperre und Code erreichbar sind
OPEN_PATHS = {"/health", "/whoami"}
CODE_FREE_PATHS = {"/login", "/static/style.css", "/static/keyvisual.jpg", "/favicon.ico"}


# ----- Zugangsschutz ------------------------------------------------------
@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path in OPEN_PATHS:
        return await call_next(request)
    ip = ip_policy.client_ip(request)
    if not ip_policy.allows(ip):
        log.warning("Zugriff abgelehnt von %s auf %s", ip, path)
        return JSONResponse({"fehler": "Zugriff nur aus dem ATSW-Netz."}, status_code=403)
    if code_policy.active and path not in CODE_FREE_PATHS:
        if not code_policy.check_token(request.cookies.get(COOKIE_NAME)):
            if path.startswith("/api/"):
                return JSONResponse({"fehler": "Zugangscode fehlt."}, status_code=401)
            return RedirectResponse("/login", status_code=302)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.on_event("startup")
async def _startup() -> None:
    if MOCK:
        log.warning("MOCK_ELEVENLABS=1: keine echten ElevenLabs-Aufrufe")
        return
    try:
        await pool.load()
    except Exception as exc:  # noqa: BLE001
        log.warning("Fragenpool konnte nicht geladen werden: %s", exc)
    try:
        await store.refresh(force=True)
        log.info("Rundenspeicher aufgebaut: %d Gespräche", len(store.rounds))
    except Exception as exc:  # noqa: BLE001
        log.warning("Rundenspeicher konnte nicht aufgebaut werden: %s", exc)


# ----- Offene Endpunkte ---------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "ip_filter": ip_policy.active,
        "code": code_policy.active,
        "fragen": len(pool.questions),
        "aktiv": pool.summary()["aktiv"],
        "stufe": pool.summary()["stufe"],
        "pool_fehler": pool.error,
    }


@app.get("/whoami")
async def whoami(request: Request) -> dict:
    """Zeigt, welche IP der Dienst für den Aufrufer sieht. Für die Einrichtung der Sperre."""
    ip = ip_policy.client_ip(request)
    return {
        "ip": ip,
        "erlaubt": ip_policy.allows(ip),
        "quelle": ip_policy.source,
        "header": ip_policy.candidates(request),
    }


# ----- Login (Zugangscode) ------------------------------------------------
LOGIN_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Game of Phones · Zugang</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body class="login"><form method="post" action="/login" class="login-box">
<div class="wordmark">RPR1<span class="dot">.</span></div>
<h1>Game of Phones · Studio</h1>
<p>Zugangscode eingeben.</p>
<input name="code" type="password" autocomplete="current-password" autofocus required>
<button type="submit">Weiter</button>{fehler}
</form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_form() -> HTMLResponse:
    if not code_policy.active:
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(LOGIN_HTML.replace("{fehler}", ""))


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    if code_policy.check_code(str(form.get("code", ""))):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(
            COOKIE_NAME,
            code_policy.token(),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
        return resp
    return HTMLResponse(LOGIN_HTML.replace("{fehler}", '<p class="fehler">Code falsch.</p>'), status_code=401)


# ----- Dashboard ----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
async def state() -> dict:
    if not MOCK:
        await store.refresh()
    return {
        "agent_id": AGENT_ID,
        "version": VERSION,
        "connection_type": CONNECTION_TYPE,
        "ip_filter": ip_policy.active,
        "code": code_policy.active,
        "pool": pool.summary(),
        "rounds": [r.to_public() for r in store.ordered()[:12]],
    }


@app.post("/api/pool/reload")
async def reload_pool() -> dict:
    await pool.load()
    return pool.summary()


class SessionRequest(BaseModel):
    name: str = ""
    ort: str = ""


@app.post("/api/session")
async def create_session(body: SessionRequest) -> dict:
    if not MOCK:
        if not pool.ready:
            await pool.load()
        if not pool.ready:
            raise HTTPException(status_code=503, detail="Fragenpool nicht geladen (" + (pool.error or "unbekannt") + "). Bitte Seite neu laden oder Armin Bescheid geben.")
        await store.refresh(max_age=60)
    picks = pool.pick_round(store.recent_numbers(), store.recent_solutions(), store.region_history())
    dynamic_variables = {
        "kandidat_name": body.name.strip()[:60],
        "kandidat_ort": body.ort.strip()[:60],
    }
    for key in CATEGORIES:
        q = picks.get(key)
        dynamic_variables[f"frage_{key}"] = q.as_line() if q else "keine"
    planned = [q.nr for q in picks.values()]
    if MOCK:
        return {"mock": True, "connection_type": CONNECTION_TYPE, "planned": planned, "dynamic_variables": dynamic_variables}
    try:
        if CONNECTION_TYPE == "webrtc":
            auth = {"conversation_token": await elevenlabs.get_conversation_token(AGENT_ID)}
        else:
            auth = {"signed_url": await elevenlabs.get_signed_url(AGENT_ID)}
    except elevenlabs.ElevenLabsError as exc:
        log.error("Session: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"connection_type": CONNECTION_TYPE, "planned": planned, "dynamic_variables": dynamic_variables, **auth}


class RegisterRequest(BaseModel):
    conversation_id: str
    planned: list[int] = []
    name: str = ""
    ort: str = ""


@app.post("/api/rounds/register")
async def register_round(body: RegisterRequest) -> dict:
    rnd = store.register(body.conversation_id, body.planned, body.name.strip(), body.ort.strip())
    return rnd.to_public()


@app.post("/api/rounds/{conversation_id}/sync")
async def sync_round(conversation_id: str) -> dict:
    if MOCK:
        rnd = store.rounds.get(conversation_id)
        if rnd:
            rnd.status = "fertig"
            rnd.frage_nr = str(rnd.planned_numbers[0]) if rnd.planned_numbers else None
            rnd.loesung = "Testlösung"
            rnd.ergebnis = "richtig"
            return rnd.to_public()
        raise HTTPException(status_code=404, detail="unbekannt")
    rnd = await store.sync(conversation_id)
    _match_question(rnd)
    return rnd.to_public()


def _match_question(rnd) -> None:
    """Die KI kennt die Fragennummer im Nachhinein nicht; über die Lösung zuordnen."""
    if rnd.frage_nr or not rnd.loesung:
        return
    sol = rnd.loesung.strip().lower()
    for nr in rnd.planned_numbers:
        q = pool.questions.get(nr)
        if not q:
            continue
        variants = [q.antwort] + [v for v in q.gilt_auch.split(",") if v.strip()]
        if any(v.strip().lower() in sol or sol in v.strip().lower() for v in variants if len(v.strip()) > 2):
            rnd.frage_nr = str(nr)
            return


@app.get("/api/rounds")
async def rounds() -> list[dict]:
    return [r.to_public() for r in store.ordered()[:50]]


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
