import requests

URL = "https://www.schwarzfelder-hof.de/onlinebuchung/?arrival=2026-06-04&depart=2026-06-07&personen=2&kinder=1&kleinkinder=1#jumpBuchung"

KEYWORD_NOT_AVAILABLE = "keine passenden ergebnisse gefunden"

def check():
    response = requests.get(URL, headers={
        "User-Agent": "Mozilla/5.0"
    })

    content = response.text.lower()

    if KEYWORD_NOT_AVAILABLE not in content:
        print("✅ VERFÜGBAR!")
        return True
    else:
        print("❌ Noch nichts frei...")
        return False

if __name__ == "__main__":
    check()
``
