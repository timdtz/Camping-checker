import os
import time
from datetime import datetime

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://www.schwarzfelder-hof.de/onlinebuchung/?arrival=2026-06-04&depart=2026-06-07&personen=2&kinder=1&kleinkinder=1#jumpBuchung"
KEYWORD_NOT_AVAILABLE = "Für den gewünschten Zeitraum konnten keine passenden Ergebnisse gefunden werden."

SCREENSHOT_FILE = "screenshot.png"
AVAILABLE_FILE = "AVAILABLE.txt"

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

def safe_click(driver, by, selector, timeout=3):
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

    id_variants = [
        "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "CybotCookiebotDialogBodyButtonAccept",
        "onetrust-accept-btn-handler",
        "uc-accept-all-button",
    ]
    for cid in id_variants:
        if safe_click(driver, By.ID, cid, timeout=2):
            return True

    # Last resort: Overlays entfernen (best effort)
    try:
        driver.execute_script("""
          const sels = ['[id*="cookie"]','[class*="cookie"]','[id*="consent"]','[class*="consent"]','[class*="overlay"]'];
          sels.forEach(s => document.querySelectorAll(s).forEach(e => e.remove()));
        """)
    except Exception:
        pass
    return False

def scroll_to_booking_section(driver):
    try:
        el = driver.find_element(By.ID, "jumpBuchung")
        driver.execute_script("arguments[0].scrollIntoView({block:'start'});", el)
        time.sleep(1)
    except Exception:
        try:
            driver.execute_script("location.hash='jumpBuchung';")
            time.sleep(1)
        except Exception:
            pass

def click_search_button(driver) -> bool:
    dismiss_cookie_banner(driver)

    xpaths = [
        "//button[normalize-space()='Suchen']",
        "//button[contains(normalize-space(.), 'Suchen')]",
        "//input[@type='submit' and (contains(@value,'Suchen') or contains(@aria-label,'Suchen'))]",
    ]
    for xp in xpaths:
        if safe_click(driver, By.XPATH, xp, timeout=5):
            return True

    # Fallback: irgendein Button mit Text "suchen"
    try:
        for b in driver.find_elements(By.XPATH, "//button"):
            if "suchen" in (b.text or "").lower():
                b.click()
                return True
    except Exception:
        pass

    return False

def wait_for_results_loaded(driver, timeout=40):
    def condition(d):
        txt = d.find_element(By.TAG_NAME, "body").text
        if KEYWORD_NOT_AVAILABLE in txt:
            return True
        # "Loaded"-Heuristik
        lowered = txt.lower()
        return ("verfügbarkeiten" in lowered) or ("warenkorb" in lowered) or ("buchung" in lowered)
    WebDriverWait(driver, timeout).until(condition)

def telegram_send_photo(caption: str, photo_path: str):
    """
    Sendet Foto via Telegram Bot API: POST /sendPhoto mit chat_id + photo. [1](https://core.telegram.org/bots/api)[2](https://tg-bot-sdk.website/api/methods/send-photo/)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("ℹ️ Telegram Secrets nicht gesetzt (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID). Überspringe Telegram Versand.")
        return

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        files = {"photo": f}
        data = {"chat_id": chat_id, "caption": caption}
        r = requests.post(url, data=data, files=files, timeout=30)
        r.raise_for_status()

def main() -> int:
    driver = make_driver()
    status_line = "Status unbekannt"
    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        dismiss_cookie_banner(driver)
        scroll_to_booking_section(driver)

        clicked = click_search_button(driver)
        if not clicked:
            status_line = "⚠️ 'Suchen' Button nicht sicher gefunden – Screenshot zur Diagnose."
        else:
            wait_for_results_loaded(driver, timeout=40)

        time.sleep(1)

        # ✅ Screenshot IMMER erzeugen
        driver.save_screenshot(SCREENSHOT_FILE)
        print(f"📸 Screenshot gespeichert: {SCREENSHOT_FILE}")

        body_text = driver.find_element(By.TAG_NAME, "body").text
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        if KEYWORD_NOT_AVAILABLE not in body_text:
            status_line = "✅ MÖGLICHER TREFFER: Hinweistext NICHT gefunden (evtl. frei)."
            with open(AVAILABLE_FILE, "w", encoding="utf-8") as f:
                f.write(f"Availability suspected at {ts}\n{URL}\n")
        else:
            status_line = "❌ Noch nichts frei (Hinweistext gefunden)."

        # ✅ Telegram: immer Screenshot + Status senden
        caption = f"{status_line}\n{ts}\n{URL}"
        telegram_send_photo(caption=caption, photo_path=SCREENSHOT_FILE)

        return 0

    finally:
        driver.quit()

if __name__ == "__main__":
    raise SystemExit(main())
