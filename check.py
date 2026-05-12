import os
import time
from datetime import datetime

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

URL = "https://www.schwarzfelder-hof.de/onlinebuchung/?arrival=2026-06-04&depart=2026-06-07&personen=2&kinder=1&kleinkinder=1#jumpBuchung"
KEYWORD_NOT_AVAILABLE = "Für den gewünschten Zeitraum konnten keine passenden Ergebnisse gefunden werden."

SCREENSHOT_FILE = "screenshot.png"
AVAILABLE_FILE = "AVAILABLE.txt"


# -----------------------------
# Browser / Selenium helpers
# -----------------------------
def make_driver() -> webdriver.Chrome:
    opts = Options()
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


def safe_click(driver, element, timeout=5) -> bool:
    """Versucht ein Element robust zu klicken (normal -> actions -> JS)."""
    try:
        WebDriverWait(driver, timeout).until(lambda d: element.is_displayed() and element.is_enabled())
    except Exception:
        pass

    try:
        element.click()
        return True
    except ElementClickInterceptedException:
        pass
    except Exception:
        pass

    # Actions click (manchmal zuverlässiger)
    try:
        ActionChains(driver).move_to_element(element).click().perform()
        return True
    except Exception:
        pass

    # JavaScript click als Fallback (wenn Selenium click 'klickbar' sagt, aber nichts auslöst) [4](https://www.uptimia.com/de)[5](https://turboutilkit.com/de/uberprufungderwebsiteverfugbarkeit/)
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def dismiss_cookie_banner(driver):
    """Versucht Consent/Cookie Banner zu akzeptieren oder Overlays zu entfernen."""
    time.sleep(1)

    text_variants = [
        "Alle akzeptieren", "Alles akzeptieren", "Akzeptieren",
        "Zustimmen", "Einverstanden", "OK", "Ok", "Accept all", "Accept"
    ]

    # Buttons / Links mit typischem Text
    for t in text_variants:
        try:
            btns = driver.find_elements(By.XPATH, f"//button[contains(., '{t}')]")
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    if safe_click(driver, b, timeout=2):
                        return True
        except Exception:
            pass
        try:
            links = driver.find_elements(By.XPATH, f"//a[contains(., '{t}')]")
            for a in links:
                if a.is_displayed() and a.is_enabled():
                    if safe_click(driver, a, timeout=2):
                        return True
        except Exception:
            pass

    # Häufige CMP IDs (optional)
    id_variants = [
        "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "CybotCookiebotDialogBodyButtonAccept",
        "onetrust-accept-btn-handler",
        "uc-accept-all-button",
    ]
    for cid in id_variants:
        try:
            el = driver.find_element(By.ID, cid)
            if el.is_displayed() and el.is_enabled():
                if safe_click(driver, el, timeout=2):
                    return True
        except Exception:
            pass

    # Letzter Ausweg: blockierende Overlays entfernen (best-effort)
    try:
        driver.execute_script("""
          const sels = [
            '[id*="cookie"]','[class*="cookie"]',
            '[id*="consent"]','[class*="consent"]',
            '[class*="overlay"]'
          ];
          sels.forEach(s => document.querySelectorAll(s).forEach(e => e.remove()));
        """)
    except Exception:
        pass

    return False


def scroll_to_booking_section(driver):
    """Scrollt zu #jumpBuchung (falls Element/Hash vorhanden)."""
    try:
        el = driver.find_element(By.ID, "jumpBuchung")
        driver.execute_script("arguments[0].scrollIntoView({block:'start'});", el)
        time.sleep(0.8)
        return
    except Exception:
        pass

    try:
        driver.execute_script("location.hash='jumpBuchung';")
        time.sleep(0.8)
    except Exception:
        pass


def click_search_button(driver) -> bool:
    """
    Klickt ROBUST auf den sichtbaren 'Suchen'-Button:
    - findet Kandidaten
    - scrollt in Viewport
    - normal click -> actions click -> JS click -> form.submit()
    """
    dismiss_cookie_banner(driver)
    scroll_to_booking_section(driver)
    time.sleep(0.5)

    # Kandidaten: Buttons mit Text "Suchen" (auch wenn Text in <span> steckt) oder submit inputs
    candidates = []
    try:
        candidates.extend(driver.find_elements(
            By.XPATH,
            "//button[.//span[contains(normalize-space(.),'Suchen')] or contains(normalize-space(.),'Suchen')]"
        ))
    except Exception:
        pass

    try:
        candidates.extend(driver.find_elements(
            By.XPATH,
            "//input[@type='submit' and (contains(@value,'Suchen') or contains(@aria-label,'Suchen'))]"
        ))
    except Exception:
        pass

    # Filter: sichtbar + enabled
    candidates = [c for c in candidates if c.is_displayed() and c.is_enabled()]

    if not candidates:
        return False

    # Häufig ist der relevante Button weiter unten -> letzten sichtbaren nehmen
    btn = candidates[-1]

    # In die Mitte scrollen (verhindert Sticky Header / Overlays)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.5)
    except Exception:
        pass

    # Versuche zu klicken
    if safe_click(driver, btn, timeout=5):
        return True

    # Fallback: Form submit (wenn ein echtes <form> vorhanden ist) [5](https://turboutilkit.com/de/uberprufungderwebsiteverfugbarkeit/)[6](https://dchatry.github.io/blog/2018/11/29/periodically-check-web-page-get-notified-changes.html)
    try:
        form = btn.find_element(By.XPATH, "ancestor::form")
        form.submit()
        return True
    except Exception:
        return False


def wait_for_results_loaded(driver, timeout=40):
    """
    Wartet, bis nach dem Klick der Ergebniszustand geladen ist.
    Explizites Warten reduziert Race-Conditions bei dynamischen Seiten. [1](https://learn.microsoft.com/en-us/microsoft-365/bookings/power-automate-integration?view=o365-worldwide)
    """
    def condition(d):
        try:
            txt = d.find_element(By.TAG_NAME, "body").text
        except Exception:
            return False

        # Wenn die "keine Ergebnisse"-Meldung erscheint => Suche hat reagiert
        if KEYWORD_NOT_AVAILABLE in txt:
            return True

        # Alternativ: irgendein Hinweis auf den Buchungs-/Ergebnisfluss (Heuristik)
        lowered = txt.lower()
        if ("verfügbarkeiten" in lowered) or ("warenkorb" in lowered) or ("buchung" in lowered):
            return True

        return False

    WebDriverWait(driver, timeout).until(condition)


# -----------------------------
# Telegram helpers
# -----------------------------
def telegram_send_photo(caption: str, photo_path: str):
    """
    Telegram Bot API: sendPhoto (chat_id + photo + caption). [2](https://www.naturgarten-kaiserstuhl.de/de/unterkunft-suchen)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("ℹ️ Telegram env fehlt (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID). Überspringe Telegram.")
        return

    endpoint = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        files = {"photo": f}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(endpoint, data=data, files=files, timeout=30)
        r.raise_for_status()


# -----------------------------
# Main
# -----------------------------
def main() -> int:
    driver = make_driver()
    status_line = "Status unbekannt"

    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        # Banner weg + scroll
        dismiss_cookie_banner(driver)
        scroll_to_booking_section(driver)

        # Suche auslösen (mit Retry)
        clicked = click_search_button(driver)

        if not clicked:
            status_line = "⚠️ Konnte 'Suchen' nicht eindeutig klicken (Screenshot zur Diagnose)."
        else:
            # Nach Klick warten, bis Ergebniszustand da ist
            try:
                wait_for_results_loaded(driver, timeout=20)
            except TimeoutException:
                # einmal retry (manchmal verschluckt JS den ersten Click)
                click_search_button(driver)
                try:
                    wait_for_results_loaded(driver, timeout=40)
                except TimeoutException:
                    status_line = "⚠️ 'Suchen' geklickt, aber Ergebniszustand nicht innerhalb Timeout sichtbar."

        # ✅ Screenshot IMMER (auch bei Fehlern)
        try:
            driver.save_screenshot(SCREENSHOT_FILE)
            print(f"📸 Screenshot gespeichert: {SCREENSHOT_FILE}")
        except Exception as e:
            print(f"⚠️ Screenshot konnte nicht gespeichert werden: {e}")

        # Text prüfen
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_text = ""

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Verfügbarkeit: Wenn der "keine Ergebnisse"-Text NICHT vorkommt, ist es ein möglicher Treffer
        if body_text and (KEYWORD_NOT_AVAILABLE not in body_text):
            status_line = "✅ MÖGLICHER TREFFER: 'keine Ergebnisse' Text NICHT gefunden (evtl. frei)."
            try:
                with open(AVAILABLE_FILE, "w", encoding="utf-8") as f:
                    f.write(f"Availability suspected at {ts}\n{URL}\n")
            except Exception:
                pass
        elif "keine Ergebnisse" in body_text.lower():
            status_line = "❌ Noch nichts frei (Hinweistext gefunden)."

        # Telegram: immer Screenshot + Status senden
        caption = f"{status_line}\n{ts}\n{URL}"
        try:
            telegram_send_photo(caption=caption, photo_path=SCREENSHOT_FILE)
        except Exception as e:
            print(f"⚠️ Telegram Versand fehlgeschlagen: {e}")

        return 0

    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
