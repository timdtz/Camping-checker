import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://www.schwarzfelder-hof.de/onlinebuchung/?arrival=2026-06-04&depart=2026-06-07&personen=2&kinder=1&kleinkinder=1#jumpBuchung"
KEYWORD_NOT_AVAILABLE = "Für den gewünschten Zeitraum konnten keine passenden Ergebnisse gefunden werden."

def make_driver() -> webdriver.Chrome:
    opts = Options()
    # Stabil in GitHub Actions / CI [1](https://www.monicheck.com/de)
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1100")
    opts.add_argument("--lang=de-DE")
    return webdriver.Chrome(options=opts)

def page_ready(driver, timeout=40):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
    )

def safe_click(driver, by, selector, timeout=2):
    """Versucht kurz, ein Element zu klicken. Gibt True/False zurück."""
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
        el.click()
        return True
    except Exception:
        return False

def dismiss_cookie_banner(driver):
    """
    Versucht verschiedene typische Consent-Buttons zu klicken.
    Kein harter Fehler, wenn nichts gefunden wird.
    """
    # Kurzer Moment, damit Banner überhaupt gerendert ist
    time.sleep(1)

    # 1) Häufige Button-Texte (Deutsch) – via XPath "contains"
    text_variants = [
        "Alle akzeptieren", "Alles akzeptieren", "Akzeptieren",
        "Zustimmen", "Einverstanden", "OK", "Ok", "I agree", "Accept all", "Accept"
    ]

    for t in text_variants:
        # Button
        if safe_click(driver, By.XPATH, f"//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), '{t.lower()}')]", timeout=2):
            return True
        # Link/Anchor als Button
        if safe_click(driver, By.XPATH, f"//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'), '{t.lower()}')]", timeout=2):
            return True

    # 2) Häufige "Accept all"-IDs (falls eine bekannte CMP verwendet wird) – harmlose Fallbacks
    id_variants = [
        "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "CybotCookiebotDialogBodyButtonAccept",
        "onetrust-accept-btn-handler",
        "uc-accept-all-button",
    ]
    for cid in id_variants:
        if safe_click(driver, By.ID, cid, timeout=2):
            return True

    # 3) Letzter Ausweg: Overlay entfernen, falls es nur blockiert (best effort)
    # (Wenn nichts gefunden wurde, versuchen wir die typischen Overlay-Klassen zu entfernen)
    try:
        driver.execute_script("""
            const selectors = [
              '[id*="cookie"][class*="banner"]',
              '[class*="cookie"][class*="banner"]',
              '[id*="consent"]',
              '[class*="consent"]',
              '[class*="overlay"]'
            ];
            for (const sel of selectors) {
              document.querySelectorAll(sel).forEach(el => el.remove());
            }
        """)
    except Exception:
        pass

    return False

def scroll_to_booking_section(driver):
    """
    Scrollt zur Stelle, die durch #jumpBuchung adressiert wird.
    Versucht erst ID, sonst nutzt es den Hash.
    """
    # Versuch: Element mit ID jumpBuchung
    try:
        el = driver.find_element(By.ID, "jumpBuchung")
        driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", el)
        time.sleep(1)
        return
    except Exception:
        pass

    # Fallback: Hash setzen + scroll
    try:
        driver.execute_script("location.hash = 'jumpBuchung';")
        time.sleep(1)
    except Exception:
        pass

def main() -> int:
    driver = make_driver()
    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        # Cookie-Banner wegklicken (damit Screenshot nicht verdeckt ist)
        dismiss_cookie_banner(driver)

        # Zur relevanten Stelle scrollen
        scroll_to_booking_section(driver)

        # kleine Wartezeit für Layout nach Banner-Entfernung
        time.sleep(1)

        body_text = driver.find_element(By.TAG_NAME, "body").text

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Immer einen Screenshot zur Kontrolle erzeugen (optional, aber praktisch)
        screenshot = f"screenshot-{ts}.png"
        driver.save_screenshot(screenshot)
        print(f"📸 Screenshot gespeichert: {screenshot}")

        if KEYWORD_NOT_AVAILABLE not in body_text:
            print("✅ MÖGLICHER TREFFER: Hinweistext NICHT gefunden.")
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
``
