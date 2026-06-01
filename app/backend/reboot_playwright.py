from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time

def reboot_tplink(ip: str, user: str, password: str, timeout: int = 60) -> tuple[bool, str]:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)
            page.goto(f"http://{ip}/")
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            if page.locator('input[type="password"]').count() > 0:
                page.fill('input[type="password"]', password)
                page.press('input[type="password"]', 'Enter')
            elif page.locator('#local-password').count() > 0:
                page.fill('#local-password', password)
                page.click('button:has-text("LOG IN")')
            time.sleep(3)
            if page.locator('text=System Tools').count() > 0:
                page.click('text=System Tools'); time.sleep(1)
            if page.locator('text=Reboot').count() > 0:
                page.click('text=Reboot'); time.sleep(2)
            if page.locator('button:has-text("Reboot")').count() > 0:
                page.click('button:has-text("Reboot")')
            elif page.locator('button:has-text("Restart")').count() > 0:
                page.click('button:has-text("Restart")')
            else:
                browser.close()
                return False, "reboot_button_not_found"
            time.sleep(1)
            if page.locator('button:has-text("OK")').count() > 0:
                page.click('button:has-text("OK")')
            elif page.locator('button:has-text("Confirm")').count() > 0:
                page.click('button:has-text("Confirm")')
            time.sleep(2)
            browser.close()
            return True, "reboot_command_sent"
    except PlaywrightTimeout:
        return False, "timeout"
    except Exception as e:
        return False, f"error:{type(e).__name__}"

def reboot_netgear(ip: str, user: str, password: str, timeout: int = 60) -> tuple[bool, str]:
    """
    Netgear R6000/AC1000 (UI español):
    - Evitar clics ambiguos; usar POST directo con page.request heredando auth/cookies.
    - Intentar variantes conocidas y detectar caída de la UI (~inicio de reinicio) como confirmación.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(
                ignore_https_errors=True,
                http_credentials={"username": user, "password": password}
            )
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)

            # 1) Login (Basic) y tocar home para iniciar sesión/crear cookie de sesión
            page.goto(f"http://{ip}/")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # 2) Variantes de solicitud de reboot (POST internos)
            attempts = [
                # Variante clásica Netgear (form español)
                {"url": f"http://{ip}/setup.cgi", "data": {"todo": "reboot", "Reboot": "Reiniciar"}, "label": "setup_todo_reboot"},
                # Variante con submit_button
                {"url": f"http://{ip}/apply.cgi", "data": {"submit_button": "reboot"}, "label": "apply_submit_reboot"},
                # Variante con query y sin cuerpo
                {"url": f"http://{ip}/setup.cgi?todo=reboot", "data": {}, "label": "setup_query_reboot"},
            ]

            sent = False
            detail = ""
            for att in attempts:
                try:
                    resp = page.request.post(att["url"], form=att["data"])
                    status = resp.status
                    text = ""
                    try:
                        text = resp.text()
                    except Exception:
                        pass
                    # Considerar 200/302 como válidos (algunos devuelven HTTP/0.9-like pero aquí viene via Playwright)
                    if status in (200, 302) or "reboot" in (text or "").lower():
                        sent = True
                        detail = f"reboot_via_{att['label']}_status_{status}"
                        break
                except Exception:
                    continue

            if not sent:
                browser.close()
                return False, "reboot_http_post_failed"

            # 3) Confirmar que el router inicia reinicio: esperar caída de la UI
            # Poll a /top.html: en cuanto falle (no 200), asumimos que entró en reboot
            start = time.time()
            gone = False
            while time.time() - start < 15:  # ventana corta para detectar inicio del reboot
                try:
                    r = page.request.get(f"http://{ip}/top.html")
                    if r.status != 200:
                        gone = True
                        break
                except Exception:
                    gone = True
                    break
                time.sleep(1)

            browser.close()
            if gone:
                return True, detail + "_ui_down_detected"
            else:
                # Algunos firmwares no cortan inmediatamente; igualmente reportamos envío OK
                return True, detail + "_ui_still_up"
    except PlaywrightTimeout:
        return False, "timeout"
    except Exception as e:
        return False, f"error:{type(e).__name__}"
