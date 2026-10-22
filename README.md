# RPR1. Game of Phones – Studio-Dashboard

Web-Dienst für das Studio: startet die iPhone-KI (ElevenLabs-Agent „RPR1. Game of Phones – On-Air (Studio)“), schaltet das Mikro stumm und beendet das Gespräch. Vergibt pro Runde die nächste Region von Rheinland-Pfalz und merkt sich die zuletzt gespielten Lösungen, damit sich Fragen nicht wiederholen.

Nur aus dem ATSW-Netz erreichbar (IP-Sperre) und zusätzlich mit Zugangscode.

## Aufbau

```
app/main.py        FastAPI: Zugangsschutz, Dashboard, API
app/access.py      IP-Sperre (ALLOWED_IPS) + Zugangscode (ACCESS_CODE)
app/elevenlabs.py  Signierte URL / Token, Gesprächsdetails (API-Schlüssel nur hier)
app/store.py       Rundenspeicher im RAM, beim Start aus ElevenLabs aufgebaut
app/regions.py     Regionen + Gewichte
app/rotation.py    Auswahl der nächsten Region
app/static/        Dashboard (HTML/CSS/JS), ElevenLabs-Browser-Bibliothek 1.30.0, Key-Visual
tests/             pytest
render.yaml        Blueprint für Render (Docker, Frankfurt)
```

## Ablauf einer Runde

1. Moderator drückt **Start**. Der Browser holt von `/api/session` eine signierte Sitzung plus die dynamischen Variablen `region`, `gespielte_fragen`, `kandidat_name`, `kandidat_ort` und verbindet sich mit dem Agenten.
2. Die KI bestätigt off air den Kandidaten, wartet still, bis „Hey Siri, starte das RPR1 Game of Phones“ fällt, spielt die Runde und legt nach der Auflösung selbst auf.
3. Nach dem Ende ruft der Browser `/api/rounds/{id}/sync`. Der Server holt die Datenerfassung des Gesprächs bei ElevenLabs (Region, Kategorie, Lösung, Ergebnis) und zeigt die Runde unter „Letzte Runden“.
4. Die nächste Region ergibt sich aus Gewicht und Historie (`rotation.py`). Das Studio kann sie im Dashboard vorab ändern.

**Stumm** schaltet das Mikrofon zur KI ab (sie hört das Studio nicht mehr), die Verbindung bleibt. **Beenden** ist der Notausgang; normal legt die KI selbst auf.

## Umgebungsvariablen

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `ELEVENLABS_API_KEY` | ja | API-Schlüssel des ElevenLabs-Workspaces, in dem der Agent liegt. Nur auf dem Server. |
| `AGENT_ID` | ja | Standard: `agent_0901m4tq89w0eha9a8v0swg8770h` (Studio-Agent) |
| `ALLOWED_IPS` | empfohlen | Komma-Liste aus IPs/CIDR, z. B. `212.95.1.10, 212.95.1.0/24`. Leer = keine Sperre (Dashboard zeigt dann „IP-Sperre aus“). |
| `CLIENT_IP_SOURCE` | nein | `auto` (Standard: CF-Connecting-IP → True-Client-IP → erstes X-Forwarded-For → Peer), `cf`, `xff-first`, `xff-last`, `peer` |
| `ACCESS_CODE` | empfohlen | Zugangscode als zweites Schloss. Leer = aus. |
| `COOKIE_SECRET` | bei Code | Geheimnis für das Login-Cookie (Render erzeugt es per Blueprint). |
| `CONNECTION_TYPE` | nein | `websocket` (Standard) oder `webrtc` |
| `REGION_WEIGHTS` | nein | JSON, z. B. `{"Nahe": 1.5, "Hochwald": 1}` |
| `MOCK_ELEVENLABS` | nein | `1` = ohne ElevenLabs testen |

## IP-Sperre einrichten

1. Dienst deployen, `ALLOWED_IPS` erst einmal leer lassen.
2. Aus dem Studio-Netz `https://<dienst>/whoami` aufrufen. Das Feld `ip` ist die Adresse, die der Dienst sieht; `header` zeigt alle Kandidaten.
3. Diese IPs (oder das Netz der ATSW-IT) in `ALLOWED_IPS` eintragen, Deploy.
4. Gegenprobe von außen: `curl -H "X-Forwarded-For: <ATSW-IP>" https://<dienst>/` muss 403 liefern. Liefert es 200, steht `CLIENT_IP_SOURCE` falsch (dann `cf` setzen und erneut prüfen).

`/health` und `/whoami` sind absichtlich ohne Sperre erreichbar (Render-Healthcheck, Einrichtung). Sie verraten nichts außer der eigenen IP.

## Lokal

```
pip install -r requirements.txt
MOCK_ELEVENLABS=1 ACCESS_CODE=studio uvicorn app.main:app --reload --port 8765
python -m pytest tests
```

## Agent-Seite (ElevenLabs)

Der Studio-Agent braucht die dynamischen Variablen `region`, `gespielte_fragen`, `kandidat_name`, `kandidat_ort` (mit Platzhaltern, damit er auch ohne Dashboard startet) und in der Analyse die Datenerfassung `kandidat_name`, `kandidat_ort`, `kategorie`, `region`, `loesung`, `ergebnis`. Sobald das Dashboard läuft, im Agenten „Enable authentication“ einschalten – dann kann ihn niemand mehr an der Sperre vorbei starten.
