"""Server webhook WhatsApp Business Cloud API (Meta).

Endpoint:
  GET  /webhook  — verifikasi Meta (hub.mode=subscribe, hub.verify_token, hub.challenge)
  POST /webhook  — pesan masuk dari pelanggan -> agent.reply() -> kirim balasan

Jalankan:  python3 app.py   (port default 8000)
Atur dulu variabel di file .env (lihat .env.example):
  WHATSAPP_TOKEN    — token akses WhatsApp (dari Meta Developers)
  PHONE_NUMBER_ID   — ID nomor WhatsApp Business
  VERIFY_TOKEN      — token verifikasi webhook (kamu yang tentukan, mis. "rahasia123")
  OPENAI_API_KEY    — kunci API model (kosong = MOCK MODE, jawaban dari FAQ/produk)

Tanpa WHATSAPP_TOKEN, balasan hanya dicatat ke log (tidak dikirim) —
berguna untuk tes lokal.
"""

import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent import reply

PORT = int(os.environ.get("PORT", "8000"))
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")


def load_dotenv():
    path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_dotenv()
# baca ulang setelah .env dimuat
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", VERIFY_TOKEN)
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", PHONE_NUMBER_ID)


def send_whatsapp(to_wa_id, text):
    """Kirim pesan teks ke pelanggan lewat Graph API. Mengembalikan True/False."""
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"[DRY-RUN] balasan ke {to_wa_id}: {text}")
        return False
    body = json.dumps(
        {"messaging_product": "whatsapp", "to": to_wa_id, "type": "text", "text": {"body": text}}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("Terkirim:", resp.read().decode("utf-8")[:200])
        return True
    except Exception as e:
        print("GAGAL kirim:", e)
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # log ringkas
        print(fmt % args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/webhook":
            mode = qs.get("hub.mode", [""])[0]
            token = qs.get("hub.verify_token", [""])[0]
            challenge = qs.get("hub.challenge", [""])[0]
            if mode == "subscribe" and token == VERIFY_TOKEN:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(challenge.encode("utf-8"))
                print("Webhook terverifikasi oleh Meta.")
                return
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"verify_token salah")
            return
        if parsed.path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"WA Business Agent jalan. GET /webhook untuk verifikasi Meta.")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        # Meta mengirim event; ambil pesan teks pertama yang ada
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        if msg.get("type") != "text":
                            continue
                        wa_id = msg["from"]
                        text = msg["text"]["body"]
                        print(f"Pesan dari {wa_id}: {text}")
                        answer = reply(wa_id, text)
                        send_whatsapp(wa_id, answer)
        except Exception as e:
            print("Gagal proses pesan:", e)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


if __name__ == "__main__":
    print(f"WA Business Agent jalan di http://localhost:{PORT}")
    print("MOCK MODE (tanpa OPENAI_API_KEY):" , "YA" if not os.environ.get("OPENAI_API_KEY") else "TIDAK")
    print("WHATSAPP_TOKEN terpasang:", "YA" if WHATSAPP_TOKEN else "TIDAK (dry-run saja)")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
