
# Camping-Checker (Schwarzfelder Hof) – Selenium + Telegram + GitHub Actions

Dieses Repo prüft die Verfügbarkeit auf der Onlinebuchungsseite (JavaScript-Rendering via Selenium) und sendet bei jedem Lauf einen Screenshot per Telegram.

## Was passiert bei jedem Run?
- Öffnet die Buchungsseite mit Selenium (Headless Chrome)
- Klickt auf **„Suchen“** (`#btn-search`)
- Wartet, bis der Lade-Spinner **`.tf_spinner`** wieder verschwindet
- Erstellt immer `screenshot.png`
- Sendet den Screenshot per Telegram (Bot API `sendPhoto`)
- Wenn die typische „keine Ergebnisse“-Meldung **nicht** gefunden wird, wird zusätzlich `AVAILABLE.txt` erzeugt

## Voraussetzungen
- GitHub Repository mit Actions aktiviert
- Telegram Bot Token + Chat ID als GitHub Secrets

## Secrets einrichten (GitHub)
Repo → **Settings → Secrets and variables → Actions** → **New repository secret**
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Workflow-Zeitplan (Berlin)
Der Workflow läuft automatisch:
- **09:00** und **16:00** Uhr (Europe/Berlin)

Beispiel im Workflow (`.github/workflows/…yml`):

```yaml
on:
  schedule:
    - cron: '0 9 * * *'
      timezone: 'Europe/Berlin'
    - cron: '0 16 * * *'
      timezone: 'Europe/Berlin'
  workflow_dispatch:
```

<img width="563" height="1218" alt="screenshot-bot-message" src="https://github.com/user-attachments/assets/00811c23-ddfb-4c3b-a762-ad45ba8ecaeb" />

---
*Erstellt mit M365 Copilot, GPT‑5 (Reasoning/“Thinking”)*
