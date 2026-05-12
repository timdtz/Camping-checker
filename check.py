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
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")                 # CI stabil [1](https://github.com/actions/checkout/issues/2240)
    opts.add_argument("--disable-dev-shm-usage")      # CI stabil [1](https://github.com/actions/checkout/issues/2240)
    opts.add_argument("--window-size=1400,1100")
    opts.add_argument("--lang=de-DE")
    return webdriver.Chrome(options=opts)             # Driver-Handling typischerweise via Selenium Manager [2](https://gitea.com/gitea/act_runner/issues/729)

def page_ready(driver, timeout=40):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
    )

def safe_click(driver, by, selector, timeout=2):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
        el.click()
        return True
    except Exception:
        return False

def dismiss_cookie_banner(driver):
    time.sleep(1)
    text_variants = [
        "Alle akzeptieren", "Alles akzeptieren", "Akzeptieren",
        "Zustimmen", "Einverstanden", "OK", "Accept all", "Accept"
    ]
    for t in text_variants:
        if safe_click(driver, By.XPATH, f"//button[contains(., '{t}')]", timeout=2):
            return True
        if safe_click(driver, By.XPATH, f"//a[contains(., '{t}')]", timeout=2):
            return True

    # Fallback IDs (harmlos, wenn nicht vorhanden)
    id_variants = [
        "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "CybotCookiebotDialogBodyButtonAccept",
        "onetrust-accept-btn-handler",
        "uc-accept-all-button",
    ]
    for cid in id_variants:
        if safe_click(driver, By.ID, cid, timeout=2):
            return True

    # Letzter Ausweg: blockierende Overlays entfernen
    try:
        driver.execute_script("""
          const sels = ['[id*="cookie"]','[class*="cookie"]','[id*="consent"]','[class*="consent"]','[class*="overlay"]'];
          sels.forEach(s => document.querySelectorAll(s).forEach(e => e.remove()));
        """)
    except Exception:
        pass
    return False

def scroll_to_booking_section(driver):
    # Ziel: #jumpBuchung
    try:
        el = driver.find_element(By.ID, "jumpBuchung")
        driver.execute_script("arguments[0].scrollIntoView({block:'start'});", el)
        time.sleep(1)
        return
    except Exception:
        pass
    try:
        driver.execute_script("location.hash='jumpBuchung';")
        time.sleep(1)
    except Exception:
        pass

def click_search_button(driver) -> bool:
    """
    Klickt auf 'Suchen' (oder ähnliche) – robust über mehrere Selektoren.
    """
    # Erstmal sicherstellen, dass wir nicht von einem Banner blockiert werden
    dismiss_cookie_banner(driver)

    # Häufigste Variante: Button mit Text "Suchen"
    xpaths = [
        "//button[normalize-space()='Suchen']",
        "//button[contains(normalize-space(.), 'Suchen')]",
        "//input[@type='submit' and (contains(@value,'Suchen') or contains(@aria-label,'Suchen'))]",
        "//button[contains(@class,'search') or contains(@id,'search')]",
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, timeout=4):
            return True

    # Fallback: irgendein Button in der Buchungssektion, der "Suchen" enthält
    try:
        btns = driver.find_elements(By.XPATH, "//button")
        for b in btns:
            try:
                if "suchen" in (b.text or "").lower():
                    b.click()
                    return True
            except Exception:
                continue
    except Exception:
        pass

    return False

def wait_for_results_loaded(driver, timeout=30):
    """
    Wartet nach dem Klick, bis sich die Seite aktualisiert hat:
    - entweder erscheint der "keine Ergebnisse"-Text
    - oder es tauchen andere Ergebnis-Hinweise/Elemente auf
    """
    def condition(d):
        txt = d.find_element(By.TAG_NAME, "body").text
        if KEYWORD_NOT_AVAILABLE in txt:
            return True
        # Wenn verfügbar, könnte statt der Fehlmeldung ein anderer Inhalt erscheinen.
        # Heuristik: irgendein Hinweis auf "Warenkorb" / "Verfügbarkeiten" / "Buchung" ist vorhanden
        # (das ist nur ein "loaded"-Signal, nicht die Verfügbarkeitslogik!)
        lowered = txt.lower()
        return ("verfügbarkeiten" in lowered) or ("warenkorb" in lowered) or ("buchung" in lowered)
    WebDriverWait(driver, timeout).until(condition)

def main() -> int:
    driver = make_driver()
    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        dismiss_cookie_banner(driver)
        scroll_to_booking_section(driver)

        # ✅ WICHTIG: Suche auslösen
        clicked = click_search_button(driver)
        if not clicked:
            print("⚠️ Konnte den 'Suchen'-Button nicht eindeutig finden/klicken. Screenshot zur Diagnose wird erstellt.")

        # ✅ warten, bis Ergebnisse/Status da sind
        wait_for_results_loaded(driver, timeout=40)
        time.sleep(1)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        screenshot = f"screenshot-{ts}.png"
        driver.save_screenshot(screenshot)
        print(f"📸 Screenshot gespeichert: {screenshot}")

        body_text = driver.find_element(By.TAG_NAME, "body").text

        if KEYWORD_NOT_AVAILABLE not in body_text:
            print("✅ MÖGLICHER TREFFER: Hinweistext NICHT gefunden.")
            with open("AVAILABLE.txt", "w", encoding="utf-8") as f:
                f.write(f"Availability suspected at {ts}\n{URL}\n")
        else:
            print("❌ Noch nichts frei (Hinweistext gefunden).")

        return 0
    finally:
        driver.quit()

if __name__ == "__main__":
    raise SystemExit(main())
