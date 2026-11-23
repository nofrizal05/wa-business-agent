"""Tes end-to-end server webhook tanpa perlu akun Meta.

Menjalankan server di port 8123, lalu mengirim:
  1. GET verifikasi webhook (seperti yang dilakukan Meta)
  2. POST pesan pelanggan palsu "Halo, ada produk apa saja?"
  3. POST pesan "jam buka jam berapa?"
Lalu mencetak balasan agent dari log server.

Jalankan:  python3 test_webhook.py
Tanpa OPENAI_API_KEY, agent menjawab dalam MOCK MODE (dari FAQ/produk).
"""

import json
import subprocess
import sys
import time
import urllib.request

PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def fake_incoming(text, wa_id="6281234567890"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "12345",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": "wamid.test",
                                    "timestamp": "1234567890",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PORT"] = str(PORT)
    env.pop("OPENAI_API_KEY", None)  # paksa mock mode untuk tes
    env.pop("WHATSAPP_TOKEN", None)
    server = subprocess.Popen(
        [sys.executable, "-u", "app.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        time.sleep(1.5)
        status, body = get("/webhook?hub.mode=subscribe&hub.verify_token=rahasia123&hub.challenge=CHALLENGE_OK")
        print(f"[1] Verifikasi webhook: HTTP {status}, balasan: {body!r}")
        assert status == 200 and body == "CHALLENGE_OK", "verifikasi gagal — cek VERIFY_TOKEN di .env (default tes: rahasia123)"

        for i, teks in enumerate(
            ["Halo, ada produk apa saja?", "Jam buka jam berapa?", "Saya mau pesan 2 Kopi Gula Aren"], start=2
        ):
            status, _ = post("/webhook", fake_incoming(teks))
            print(f"[{i}] Kirim '{teks}' -> HTTP {status}")
            time.sleep(0.3)
        time.sleep(1.0)
        print("\n--- log server (balasan agent) ---")
        server.terminate()
        out, _ = server.communicate(timeout=5)
        for line in out.splitlines():
            if "DRY-RUN" in line or "Pesan dari" in line or "terverifikasi" in line:
                print(line)
        print("\nTES SELESAI. Kalau balasan muncul di atas, webhook + agent bekerja.")
    finally:
        if server.poll() is None:
            server.kill()
