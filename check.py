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

    try:
        ActionChains(driver).move_to_element(element).click().perform()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def dismiss_cookie_banner(driver):
    time.sleep(1)
    text_variants = [
        "Alle akzeptieren", "Alles akzeptieren", "Akzeptieren",
        "Zustimmen", "Einverstanden", "OK", "Ok", "Accept all", "Accept"
    ]

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
    """
    dismiss_cookie_banner(driver)
    scroll_to_booking_section(driver)
    time.sleep(0.5)

    try:
        btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btn-search")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.3)

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

    except Exception:
        return False


# -----------------------------
# Spinner wait (NEW)
# -----------------------------
def wait_for_spinner_to_finish(driver, timeout_visible=2, timeout_gone=10):
    """
    Wartet auf das Verschwinden der Ladeanimation:
      - Spinner hat Klasse: .tf_spinner
      - während Laden:  style="display: block;"
      - nach Laden:     style="display: none;"
    Wir warten zuerst kurz (optional), ob er sichtbar wird, und dann bis er unsichtbar ist. [1](https://www.tutorialspoint.com/article/python-script-to-monitor-website-changes)
    Wichtig: implicit waits können invisibility-Waits ausbremsen, daher temporär auf 0. [4](https://pyquesthub.com/automated-url-monitoring-with-python-a-practical-case-study)[2](https://jessbudd.com/blog/automate-ticket-availability-scraping/)
    """
    spinner = (By.CSS_SELECTOR, ".tf_spinner")

    # implicit wait temporär deaktivieren (falls irgendwann gesetzt)
    driver.implicitly_wait(0)

    wait_short = WebDriverWait(driver, timeout_visible)
    wait_long = WebDriverWait(driver, timeout_gone)

    # optional: kurz warten, ob er sichtbar wird
    try:
        wait_short.until(EC.visibility_of_element_located(spinner))
    except Exception:
        pass

    # dann: warten bis unsichtbar (display:none) oder nicht vorhanden
    wait_long.until(EC.invisibility_of_element_located(spinner))  # [1](https://www.tutorialspoint.com/article/python-script-to-monitor-website-changes)


def wait_for_results_loaded(driver, before_text: str, timeout=10):
    """
    Sicherheitsnetz: Nach Spinner weg noch kurz warten, bis sich der Inhalt wirklich geändert hat
    oder die "keine Ergebnisse"-Meldung auftaucht. [2](https://jessbudd.com/blog/automate-ticket-availability-scraping/)[3](https://www.geeksforgeeks.org/python/python-script-to-monitor-website-changes/)
    """
    def condition(d):
        try:
            txt = d.find_element(By.TAG_NAME, "body").text
        except Exception:
            return False

        if KEYWORD_NOT_AVAILABLE in txt:
            return True

        return txt != before_text

    WebDriverWait(driver, timeout).until(condition)


# -----------------------------
# Telegram helpers
# -----------------------------
def telegram_send_photo(caption: str, photo_path: str):
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
    spinner_info = "spinner=?"

    try:
        driver.get(URL)
        page_ready(driver, timeout=40)

        dismiss_cookie_banner(driver)
        scroll_to_booking_section(driver)

        # Vorher-Text merken (für echte Änderung)
        try:
            before_text = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            before_text = ""

        clicked = click_search_button(driver)
        clicked_info = "click=OK" if clicked else "click=FAIL"

        if clicked:
            # 1) Warte bis Spinner weg ist (typisch ~2s, max 10s)
            try:
                wait_for_spinner_to_finish(driver, timeout_visible=2, timeout_gone=10)
                spinner_info = "spinner=OK"
            except TimeoutException:
                spinner_info = "spinner=TIMEOUT"

            # 2) Danach (kurz) auf echte Inhaltsänderung warten
            try:
                wait_for_results_loaded(driver, before_text=before_text, timeout=10)
            except TimeoutException:
                # wenn es keine erkennbare Änderung gibt, trotzdem weitermachen (Screenshot hilft)
                pass
        else:
            status_line = "⚠️ Konnte 'btn-search' nicht klicken."

        # Screenshot IMMER
        try:
            driver.save_screenshot(SCREENSHOT_FILE)
        except Exception as e:
            print(f"⚠️ Screenshot konnte nicht gespeichert werden: {e}")

        # Text prüfen (für AVAILABLE.txt)
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

        caption = f"{status_line} [{clicked_info},{spinner_info}]\n{ts}\n{URL}"
        try:
            telegram_send_photo(caption=caption, photo_path=SCREENSHOT_FILE)
        except Exception as e:
            print(f"⚠️ Telegram Versand fehlgeschlagen: {e}")

        return 0

    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
