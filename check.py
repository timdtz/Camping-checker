import os
import sys
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://www.schwarzfelder-hof.de/onlinebuchung/?arrival=2026-06-04&depart=2026-06-07&personen=2&kinder=1&kleinkinder=1#jumpBuchung"
KEYWORD_NOT_AVAILABLE = "Für den gewünschten Zeitraum konnten keine passenden Ergebnisse gefunden werden."

def make_driver() -> webdriver.Chrome:
    opts = Options()
    # Headless + Stabilitäts-Flags (typisch für CI/Actions)
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--lang=de-DE")

    # Optional: PageLoadStrategy kann helfen, wenn Seiten sehr "schwer" sind
    # opts.page_load_strategy = "eager"

    return webdriver.Chrome(options=opts)

def page_ready(driver: webdriver.Chrome, timeout: int = 30):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

def main() -> int:
    driver = make_driver()
    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        # Kleine zusätzliche Wartezeit für JS-Rendering
        time.sleep(2)

        body_text = driver.find_element(By.TAG_NAME, "body").text

        if KEYWORD_NOT_AVAILABLE not in body_text:
            print("✅ MÖGLICHER TREFFER: Hinweistext 'keine Ergebnisse' NICHT gefunden.")
            # Screenshot zur späteren Kontrolle
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            screenshot = f"screenshot-available-{ts}.png"
            driver.save_screenshot(screenshot)
            print(f"📸 Screenshot gespeichert: {screenshot}")

            # Marker-Datei für Workflow (damit du in Actions darauf reagieren kannst)
            with open("AVAILABLE.txt", "w", encoding="utf-8") as f:
                f.write(f"Availability suspected at {ts}\n{URL}\n")
            print("📝 AVAILABLE.txt geschrieben")

        else:
            print("❌ Noch nichts frei (Hinweistext gefunden).")

        return 0

    finally:
        driver.quit()

if __name__ == "__main__":
    raise SystemExit(main())
