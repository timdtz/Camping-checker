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
    """
    Robuster Klick: normal -> Actions -> JS click.
    Hintergrund: Elemente können als "klickbar" gelten, aber Click wird blockiert/verschluckt;
    JS-click ist ein gängiger Fallback. [1](https://turboutilkit.com/de/uberprufungderwebsiteverfugbarkeit/)[2](https://www.uptimia.com/de)
    """
    try:
        WebDriverWait(driver, timeout).until(lambda d: element.is_displayed() and element.is_enabled())
    except Exception:
        pass

    # 1) normaler click
    try:
        element.click()
        return True
    except ElementClickInterceptedException:
        pass
    except Exception:
        pass

    # 2) Actions click
    try:
        ActionChains(driver).move_to_element(element).click().perform()
        return True
    except Exception:
        pass

    # 3) JS click
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def dismiss_cookie_banner(driver):
    """Versucht Consent/Cookie Banner zu akzeptieren oder Overlays zu entfernen (best effort)."""
    time.sleep(1)

    text_variants = [
        "Alle akzeptieren", "Alles akzeptieren", "Akzeptieren",
        "Zustimmen", "Einverstanden", "OK", "Ok", "Accept all", "Accept"
    ]

    for t in text_variants:
        # Buttons
        try:
            btns = driver.find_elements(By.XPATH, f"//button[contains(., '{t}')]")
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    if safe_click(driver, b, timeout=2):
                        return True
        except Exception:
            pass
        # Links
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

    # Last resort: Overlays entfernen
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
    Klickt gezielt auf: <input id="btn-search" type="submit" value="Suchen">
    Falls nicht vorhanden: Fallback auf andere Kandidaten.
    """
    dismiss_cookie_banner(driver)
    scroll_to_booking_section(driver)
    time.sleep(0.5)

    # 1) Primär: ID btn-search
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "btn-search"))
        )
        # in die Mitte scrollen (gegen Sticky Header/Overlays)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.5)

        # clickable wait + robust click
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btn-search")))
        except Exception:
            pass

        if safe_click(driver, btn, timeout=5):
            return True

        # Fallback: form.submit()
        try:
            form = btn.find_element(By.XPATH, "ancestor::form")
            form.submit()
            return True
        except Exception:
            return False

    except TimeoutException:
        pass
    except Exception:
        pass

    # 2) Fallback: Input submit mit value=Suchen
    try:
        candidates = driver.find_elements(By.XPATH, "//input[@type='submit' and contains(@value,'Suchen')]")
        candidates = [c for c in candidates if c.is_displayed() and c.is_enabled()]
        if candidates:
            btn = candidates[-1]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            if safe_click(driver, btn, timeout=5):
                return True
            try:
                form = btn.find_element(By.XPATH, "ancestor::form")
                form.submit()
                return True
            except Exception:
                return False
    except Exception:
        pass

    return False


def wait_for_results_loaded(driver, timeout=40):
    """
    Wartet nach dem Klick, bis der Ergebniszustand geladen ist.
    Explizite Waits reduzieren Flakiness bei dynamischen Seiten. [3](https://learn.microsoft.com/en-us/microsoft-365/bookings/power-automate-integration?view=o365-worldwide)
    """
    def condition(d):
        try:
            txt = d.find_element(By.TAG_NAME, "body").text
        except Exception:
            return False

        # "keine Ergebnisse" Meldung => Suche wurde ausgeführt
        if KEYWORD_NOT_AVAILABLE in txt:
            return True

        # Heuristik: Begriffe aus dem Buchungsfluss
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
    Telegram Bot API: sendPhoto (chat_id + photo + caption). [4](https://www.naturgarten-kaiserstuhl.de/de/unterkunft-suchen)[5](https://www.campingplatz.de/campingplaetze/deutschland/schwarzfelder-hof/)
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
    clicked_info = "click=?"

    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        dismiss_cookie_banner(driver)
        scroll_to_booking_section(driver)

        # Suche auslösen (mit Retry)
        clicked = click_search_button(driver)
        clicked_info = "click=OK" if clicked else "click=FAIL"

        if clicked:
            try:
                wait_for_results_loaded(driver, timeout=20)
            except TimeoutException:
                # Retry (manchmal verschluckt JS den ersten Click)
                clicked2 = click_search_button(driver)
                clicked_info = "click=OK(retry)" if clicked2 else clicked_info
                try:
                    wait_for_results_loaded(driver, timeout=40)
                except TimeoutException:
                    status_line = "⚠️ 'Suchen' geklickt, aber Ergebniszustand nicht innerhalb Timeout sichtbar."
        else:
            status_line = "⚠️ Konnte 'btn-search' nicht klicken (Screenshot zur Diagnose)."

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

        if body_text and (KEYWORD_NOT_AVAILABLE not in body_text):
            status_line = "✅ MÖGLICHER TREFFER: 'keine Ergebnisse' Text NICHT gefunden (evtl. frei)."
            try:
                with open(AVAILABLE_FILE, "w", encoding="utf-8") as f:
                    f.write(f"Availability suspected at {ts}\n{URL}\n")
            except Exception:
                pass
        elif "keine passenden ergebnisse" in body_text.lower():
            status_line = "❌ Noch nichts frei (Hinweistext gefunden)."

        # Telegram: immer Screenshot + Status senden
        caption = f"{status_line} [{clicked_info}]\n{ts}\n{URL}"
        try:
            telegram_send_photo(caption=caption, photo_path=SCREENSHOT_FILE)
        except Exception as e:
            print(f"⚠️ Telegram Versand fehlgeschlagen: {e}")

        return 0

    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
