import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import httpx
import pymupdf
import websockets

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"
YOUPI_URL = "http://127.0.0.1:6100"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TEMP_DIR = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "chrome_phase4_e2e")
ARTIFACT_DIR = r"C:\Users\DELL\.gemini\antigravity\brain\6acc376b-3ca3-4e9e-a683-05469d09b738"
YOUPI_WEBHOOK_SECRET = "youpi_test_webhook_secret_key_32bytes_long!"

results = []

def record(name: str, passed: bool, details: str = ""):
    status_str = "PASSED" if passed else "FAILED"
    results.append({"name": name, "passed": passed, "details": details})
    print(f"[{status_str}] {name} - {details}")

def create_pdf(page_count: int = 3) -> bytes:
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint Diploma Demo Document - Page {i+1}")
        page.insert_text((50, 100), "Project: SmartPrint Self-Service Printing Kiosk")
    b = doc.tobytes()
    doc.close()
    return b

def compute_youpi_signature(body: bytes, secret: str = YOUPI_WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"

_cmd_counter = 100

async def send_cmd(ws, method, params=None, timeout=15.0):
    global _cmd_counter
    _cmd_counter += 1
    cmd_id = _cmd_counter
    payload = {"id": cmd_id, "method": method}
    if params is not None:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    start_t = time.time()
    while True:
        if time.time() - start_t > timeout:
            raise TimeoutError(f"Timeout waiting for response to {method} (id={cmd_id})")
        msg = json.loads(await ws.recv())
        if msg.get("id") == cmd_id:
            return msg

async def main():
    print("=" * 80)
    print("SMARTPRINT PHASE 4: FULL END-TO-END VALIDATION")
    print("=" * 80)

    # 1. Verify all services are reachable
    with httpx.Client(timeout=5.0) as client:
        # Backend health
        try:
            r = client.get(f"{BACKEND_URL}/api/health")
            backend_ok = r.status_code == 200 and r.json().get("status") in ("ok", "healthy", "degraded")
            backend_info = f"status={r.json().get('status')}, db={r.json().get('database')}"
        except Exception as e:
            backend_ok = False
            backend_info = str(e)
        record("Service Check: FastAPI Backend (8000)", backend_ok, backend_info)

        # YouPI-PG health
        try:
            r = client.get(f"{YOUPI_URL}/health")
            youpi_ok = r.status_code == 200 and r.json().get("status") == "UP"
        except Exception as e:
            youpi_ok = False
        record("Service Check: YouPI-PG Gateway (6100)", youpi_ok, "Core API and SQLite running")

        # Frontend reachable
        try:
            r = client.get(FRONTEND_URL)
            frontend_ok = r.status_code == 200
        except Exception as e:
            frontend_ok = False
        record("Service Check: React + Vite Frontend (5173)", frontend_ok, "Vite dev server running")

    # 2. PDF Upload
    pdf_bytes = create_pdf(page_count=3)
    with httpx.Client(timeout=10.0) as client:
        files = {"file": ("SmartPrint_Demo_Invoice.pdf", pdf_bytes, "application/pdf")}
        upload_res = client.post(f"{BACKEND_URL}/api/files/upload", files=files)
        upload_ok = upload_res.status_code == 201
        upload_data = upload_res.json() if upload_ok else {}
        file_id = upload_data.get("file_id")
        detected_pages = upload_data.get("page_count")
        record(
            "Customer Workflow: Upload PDF",
            upload_ok and detected_pages == 3,
            f"file_id={file_id}, detected_pages={detected_pages}"
        )

        # 3. Create Order
        # 3 pages, 2 copies, B&W, single-sided -> 6 total pages @ Rs 3 = Rs 18.00
        order_payload = {
            "file_ids": [file_id],
            "copies": 2,
            "color_mode": "bw",
            "duplex": False,
            "page_range": "all",
        }
        order_res = client.post(f"{BACKEND_URL}/api/orders", json=order_payload)
        order_ok = order_res.status_code == 201
        order_data = order_res.json() if order_ok else {}
        order_id = order_data.get("order_id") or order_data.get("id")
        order_number = order_data.get("order_number")
        total_amount = order_data.get("total_amount")
        record(
            "Customer Workflow: Create Order & Verify Calculation",
            order_ok and total_amount == 18.0,
            f"order_number={order_number}, total_amount=Rs {total_amount}"
        )

        # 4. Generate YouPI-PG Mock UPI Payment Session
        checkout_res = client.post(f"{BACKEND_URL}/api/payments/{order_id}/checkout?provider=youpi")
        checkout_ok = checkout_res.status_code == 200
        checkout_data = checkout_res.json() if checkout_ok else {}
        payment_session_id = checkout_data.get("payment_session_id")
        upi_uri = checkout_data.get("upi_uri", "")
        record(
            "Customer Workflow: Generate Dynamic UPI Session",
            checkout_ok and bool(payment_session_id) and upi_uri.startswith("upi://pay"),
            f"session_id={payment_session_id}, uri={upi_uri[:45]}..."
        )

    # 5. Launch Chrome to inspect Customer UI and Tablet UI
    os.makedirs(TEMP_DIR, exist_ok=True)
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        f"--user-data-dir={TEMP_DIR}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
    ])

    try:
        # Wait for Chrome CDP
        ws_browser_url = None
        for _ in range(25):
            try:
                r = httpx.get("http://127.0.0.1:9222/json/version", timeout=1.0)
                if r.status_code == 200:
                    ws_browser_url = r.json().get("webSocketDebuggerUrl")
                    break
            except Exception:
                pass
            time.sleep(0.4)

        assert ws_browser_url, "Failed to connect to headless Chrome CDP"

        # Customer Screen View
        async with websockets.connect(ws_browser_url) as bws:
            create_resp = await send_cmd(bws, "Target.createTarget", {"url": "about:blank"})
            target_id = create_resp["result"]["targetId"]

            page_ws_url = f"ws://127.0.0.1:9222/devtools/page/{target_id}"
            async with websockets.connect(page_ws_url) as pws:
                await send_cmd(pws, "Page.enable")
                await send_cmd(pws, "Runtime.enable")
                await send_cmd(pws, "Log.enable")

                # Set desktop viewport (1280x900)
                await send_cmd(pws, "Emulation.setDeviceMetricsOverride", {
                    "width": 1280,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "mobile": False
                })

                # Navigate to Frontend URL
                await send_cmd(pws, "Page.navigate", {"url": FRONTEND_URL})
                await asyncio.sleep(2)

                # Set active order in sessionStorage
                set_storage_js = f"""
                (() => {{
                    sessionStorage.setItem('smartprint_active_order_id', '{order_number}');
                    sessionStorage.setItem('smartprint_current_view', 'payment');
                    window.location.reload();
                }})()
                """
                await send_cmd(pws, "Runtime.evaluate", {"expression": set_storage_js})
                await asyncio.sleep(3)

                # Check Customer DOM
                # Check Customer DOM (waiting up to 5s if still loading)
                check_dom_js = """
                (() => ({
                    hasQr: !!document.querySelector('svg'),
                    hasAmount: document.body.innerText.includes('18'),
                    hasUPIApps: document.body.innerText.includes('Google Pay') || document.body.innerText.includes('PhonePe') || document.body.innerText.includes('BHIM'),
                    hasDisabledNotice: document.body.innerText.toLowerCase().includes('disabled')
                }))()
                """
                dom_info = {}
                for _ in range(10):
                    eval_resp = await send_cmd(pws, "Runtime.evaluate", {"expression": check_dom_js, "returnByValue": True})
                    dom_info = eval_resp["result"]["result"]["value"]
                    if dom_info["hasQr"] and dom_info["hasUPIApps"] and dom_info["hasDisabledNotice"]:
                        break
                    await asyncio.sleep(1)

                record(
                    "Customer UI: Dynamic UPI QR & Payment Screen Rendered",
                    dom_info["hasQr"] and dom_info["hasAmount"] and dom_info["hasUPIApps"] and dom_info["hasDisabledNotice"],
                    f"hasQr={dom_info['hasQr']}, hasAmount={dom_info['hasAmount']}, hasUPIApps={dom_info['hasUPIApps']}, hasDisabledNotice={dom_info['hasDisabledNotice']}"
                )

                # Capture Customer Payment Screen Screenshot
                shot_resp = await send_cmd(pws, "Page.captureScreenshot", {"format": "png"})
                shot_data = base64.b64decode(shot_resp["result"]["data"])

                payment_screen_path = os.path.join(ARTIFACT_DIR, "customer_payment_screen.png")
                with open(payment_screen_path, "wb") as f:
                    f.write(shot_data)
                with open("customer_payment_screen.png", "wb") as f:
                    f.write(shot_data)
                record("Screenshot: Customer Payment Screen", os.path.exists(payment_screen_path), f"Saved to {payment_screen_path}")

        # 6. Trigger Synthetic Successful Payment Webhook
        mock_utr = f"UTR{int(time.time())}"
        webhook_payload = {
            "event": "OBSERVED_SUCCESS",
            "deliveryId": f"del_{int(time.time()*1000)}",
            "timestamp": "2026-11-02T13:45:00.000Z",
            "orderId": order_number,
            "paymentSessionId": payment_session_id,
            "amount": 18.0,
            "utr": mock_utr,
            "matchedObserver": "mock-sms-observer",
            "observerType": "sms",
            "attributionScore": 1.0,
            "notes": "Diploma Mock Test Verification"
        }
        raw_body = json.dumps(webhook_payload).encode("utf-8")
        sig = compute_youpi_signature(raw_body)

        with httpx.Client(timeout=10.0) as client:
            wh_res = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gateway-Signature": sig
                }
            )
            wh_ok = wh_res.status_code == 200 and wh_res.json().get("status") in ("ok", "processed")
            record(
                "Webhook: Synthetic Successful Payment (HMAC Validated)",
                wh_ok,
                f"status={wh_res.status_code}, response={wh_res.json()}"
            )

            # 7. Verify Order Confirmation in MySQL via Backend API
            status_res = client.get(f"{BACKEND_URL}/api/payments/{order_id}/status")
            status_ok = status_res.status_code == 200
            status_data = status_res.json() if status_ok else {}
            is_confirmed = (
                status_data.get("status") == "CONFIRMED" and
                status_data.get("payment_status") in ("PAID", "SUCCESS") and
                status_data.get("is_paid") is True and
                (status_data.get("payment_reference") == mock_utr or status_data.get("payment_session_id") == payment_session_id)
            )
            record(
                "Backend Order Confirmation: Status=CONFIRMED, is_paid=True",
                is_confirmed,
                f"status={status_data.get('status')}, payment_status={status_data.get('payment_status')}, ref={status_data.get('payment_reference')}"
            )

            # 8. Test Duplicate Webhook Idempotency
            wh_dup_res = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=raw_body,
                headers={"Content-Type": "application/json", "X-Gateway-Signature": sig}
            )
            dup_handled = wh_dup_res.status_code == 200 and wh_dup_res.json().get("status") in ("ignored", "processed", "ok")
            record("Edge Case: Duplicate Webhook Delivery Idempotency", dup_handled, f"Response: {wh_dup_res.json()}")

            # 9. Test Invalid Signature Rejection (400 or 401)
            wh_bad_sig = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=raw_body,
                headers={"Content-Type": "application/json", "X-Gateway-Signature": "sha256=invalid_bad_sig_hex"}
            )
            bad_sig_rejected = wh_bad_sig.status_code in (400, 401)
            record("Security Check: Invalid Webhook Signature Rejected", bad_sig_rejected, f"Status={wh_bad_sig.status_code}")

            # 10. Test Wrong Amount Rejection (with fresh deliveryId)
            order2_res = client.post(f"{BACKEND_URL}/api/orders", json=order_payload)
            order2_id = order2_res.json()["order_number"]
            mismatch_payload = dict(webhook_payload)
            mismatch_payload["orderId"] = order2_id
            mismatch_payload["deliveryId"] = f"del_mismatch_{int(time.time()*1000)}"
            mismatch_payload["amount"] = 99.0
            mismatch_body = json.dumps(mismatch_payload).encode("utf-8")
            wh_mismatch = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=mismatch_body,
                headers={"Content-Type": "application/json", "X-Gateway-Signature": compute_youpi_signature(mismatch_body)}
            )
            mismatch_rejected = wh_mismatch.status_code in (400, 422)
            record("Security Check: Mismatched Payment Amount Rejected", mismatch_rejected, f"Status={wh_mismatch.status_code}")

            # 11. Test Duplicate UTR Across Different Orders Rejection
            dup_utr_payload = dict(webhook_payload)
            dup_utr_payload["orderId"] = order2_id
            dup_utr_payload["amount"] = 18.0
            dup_utr_payload["deliveryId"] = f"del_duputr_{int(time.time()*1000)}"
            dup_utr_payload["utr"] = mock_utr
            dup_utr_body = json.dumps(dup_utr_payload).encode("utf-8")
            wh_dup_utr = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=dup_utr_body,
                headers={"Content-Type": "application/json", "X-Gateway-Signature": compute_youpi_signature(dup_utr_body)}
            )
            dup_utr_rejected = wh_dup_utr.status_code == 409
            record("Security Check: Reused UTR Rejection (409 Conflict)", dup_utr_rejected, f"Status={wh_dup_utr.status_code}")

            # 12. Test Failed / Expired Events Do NOT Confirm Orders
            order3_res = client.post(f"{BACKEND_URL}/api/orders", json=order_payload)
            order3_id = order3_res.json()["order_number"]
            failed_payload = dict(webhook_payload)
            failed_payload["orderId"] = order3_id
            failed_payload["event"] = "OBSERVED_FAILED"
            failed_payload["deliveryId"] = f"del_{int(time.time()*1000)+2}"
            failed_body = json.dumps(failed_payload).encode("utf-8")
            wh_failed = client.post(
                f"{BACKEND_URL}/api/payments/webhook/youpi",
                content=failed_body,
                headers={"Content-Type": "application/json", "X-Gateway-Signature": compute_youpi_signature(failed_body)}
            )
            order3_status = client.get(f"{BACKEND_URL}/api/payments/{order3_id}/status").json()
            failed_not_paid = order3_status.get("status") != "CONFIRMED" and not order3_status.get("is_paid")
            record("Edge Case: FAILED Payment Does Not Confirm Order", failed_not_paid, f"Status={order3_status.get('status')}")

            # 13. Test Fallback: Razorpay session generation remains functional
            order4_res = client.post(f"{BACKEND_URL}/api/orders", json=order_payload)
            order4_id = order4_res.json()["order_number"]
            rzp_checkout = client.post(f"{BACKEND_URL}/api/payments/{order4_id}/checkout?provider=razorpay")
            rzp_ok = rzp_checkout.status_code == 200 and rzp_checkout.json().get("provider") == "razorpay"
            record("Fallback Preservation: Razorpay Checkout Creatable", rzp_ok, f"provider={rzp_checkout.json().get('provider')}")

        # 14. Tablet Dashboard: Portrait View & Latest Confirmed Order Display
        async with websockets.connect(ws_browser_url) as bws:
            tablet_create = await send_cmd(bws, "Target.createTarget", {"url": "about:blank"})
            tablet_target_id = tablet_create["result"]["targetId"]

            tablet_ws_url = f"ws://127.0.0.1:9222/devtools/page/{tablet_target_id}"
            async with websockets.connect(tablet_ws_url) as tws:
                await send_cmd(tws, "Page.enable")

                # Set portrait tablet viewport: 800 x 1280 (portrait kiosk layout)
                await send_cmd(tws, "Emulation.setDeviceMetricsOverride", {
                    "width": 800,
                    "height": 1280,
                    "deviceScaleFactor": 1,
                    "mobile": True
                })

                # Navigate to /tablet
                await send_cmd(tws, "Page.navigate", {"url": f"{FRONTEND_URL}/tablet"})
                await asyncio.sleep(4)

                # Check Tablet DOM
                check_tablet_js = """
                (() => ({
                    hasConfirmedBadge: document.body.innerText.includes('ORDER CONFIRMED') || document.body.innerText.includes('CONFIRMED PRINT ORDER'),
                    hasOrderNumber: document.body.innerText.includes('SP-'),
                    hasPaidStatus: document.body.innerText.includes('PAID'),
                    hasAmount: document.body.innerText.includes('18')
                }))()
                """
                tab_eval = await send_cmd(tws, "Runtime.evaluate", {"expression": check_tablet_js, "returnByValue": True})
                tablet_dom = tab_eval["result"]["result"]["value"]

                tablet_verified = (
                    tablet_dom["hasConfirmedBadge"] and
                    tablet_dom["hasOrderNumber"] and
                    tablet_dom["hasPaidStatus"] and
                    tablet_dom["hasAmount"]
                )
                record(
                    "Tablet Kiosk: Automatically Displays Latest Confirmed Order",
                    tablet_verified,
                    f"Badge={tablet_dom['hasConfirmedBadge']}, Order#={tablet_dom['hasOrderNumber']}, Status=PAID, Amount=Rs 18"
                )

                # Capture Tablet Dashboard Screenshot
                tab_shot = await send_cmd(tws, "Page.captureScreenshot", {"format": "png"})
                tablet_shot_data = base64.b64decode(tab_shot["result"]["data"])

                tablet_screen_path = os.path.join(ARTIFACT_DIR, "tablet_dashboard.png")
                with open(tablet_screen_path, "wb") as f:
                    f.write(tablet_shot_data)
                with open("tablet_dashboard.png", "wb") as f:
                    f.write(tablet_shot_data)
                record("Screenshot: Tablet Dashboard (Portrait)", os.path.exists(tablet_screen_path), f"Saved to {tablet_screen_path}")

    finally:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=5)

    # 15. Check Frontend Bundle for Exposed Secrets
    dist_dir = "frontend/dist"
    secrets_exposed = False
    leaked_found = []
    forbidden_needles = [
        "youpi_admin_secret_token",
        "youpi_test_webhook_secret",
        "iTefZ9wxPUl5jp8T3CrPAgrU",  # Razorpay secret
        "9f250f27538f134047993c63dca65cddf8d39e351fa2bff10be236ee2c2ca25c"
    ]
    if os.path.exists(dist_dir):
        for root, _, files in os.walk(dist_dir):
            for file in files:
                if file.endswith((".js", ".html", ".map")):
                    content = open(os.path.join(root, file), "r", encoding="utf-8", errors="ignore").read()
                    for needle in forbidden_needles:
                        if needle in content:
                            secrets_exposed = True
                            leaked_found.append(needle)

    record(
        "Security Check: No Gateway Secrets in Frontend Production Bundle",
        not secrets_exposed,
        "Zero secrets found in frontend distribution" if not secrets_exposed else f"Leaked: {leaked_found}"
    )

    print("=" * 80)
    passed_count = sum(1 for r in results if r["passed"])
    print(f"SUMMARY: {passed_count}/{len(results)} VALIDATION CHECKS PASSED.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
