"""Agent WhatsApp Business — otak agentnya.

Cara kerja (pola ReAct sederhana):
  pesan masuk -> model AI memutuskan: jawab langsung, atau panggil tool dulu
  -> hasil tool dikirim balik ke model -> model menyusun jawaban akhir.

Tool yang dimiliki agent:
  - lihat_produk: daftar produk + harga + stok
  - cek_jam_operasional: jam buka toko
  - catat_pesanan: mencatat pesanan pelanggan ke orders.jsonl
  - minta_manusia: meneruskan ke admin (dicatat ke handoffs.jsonl)

LLM: API OpenAI (atau yang kompatibel, mis. Groq/OpenRouter) lewat
endpoint /chat/completions, dipanggil dengan urllib (stdlib saja).
Tanpa OPENAI_API_KEY, agent jalan dalam MOCK MODE: menjawab dari FAQ dan
daftar produk di config.json (cocok untuk tes webhook tanpa biaya).
"""

import json
import os
import sqlite3
import urllib.request

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "chats.db")
ORDERS_PATH = os.path.join(os.path.dirname(__file__), "orders.jsonl")
HANDOFFS_PATH = os.path.join(os.path.dirname(__file__), "handoffs.jsonl")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------- memori percakapan (sqlite, stdlib) ----------------

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages "
        "(wa_id TEXT, role TEXT, content TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    return conn


def load_history(wa_id, limit=20):
    conn = _db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE wa_id=? "
        "ORDER BY rowid DESC LIMIT ?",
        (wa_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def save_message(wa_id, role, content):
    conn = _db()
    conn.execute(
        "INSERT INTO messages (wa_id, role, content) VALUES (?,?,?)",
        (wa_id, role, content),
    )
    conn.commit()
    conn.close()


# ---------------- tools ----------------

def tool_lihat_produk(cfg):
    lines = []
    for p in cfg["products"]:
        lines.append(
            f"- {p['name']}: Rp{p['price']:,} (stok {p['stock']}) — {p['description']}"
        )
    return "\n".join(lines)


def tool_cek_jam_operasional(cfg):
    return f"Jam operasional: {cfg['working_hours']}. Alamat: {cfg['address']}."


def tool_catat_pesanan(cfg, produk, jumlah, nama=""):
    record = {"produk": produk, "jumlah": jumlah, "nama": nama}
    with open(ORDERS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return f"Pesanan dicatat: {jumlah}x {produk} (atas nama {nama or 'pelanggan'})."


def tool_minta_manusia(cfg, wa_id, alasan=""):
    with open(HANDOFFS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"wa_id": wa_id, "alasan": alasan}, ensure_ascii=False) + "\n")
    return cfg["human_handoff_message"].format(business_name=cfg["business_name"])


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "lihat_produk",
            "description": "Melihat daftar produk, harga, dan stok toko.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cek_jam_operasional",
            "description": "Mengecek jam buka dan alamat toko.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "catat_pesanan",
            "description": "Mencatat pesanan pelanggan. Pakai hanya kalau pelanggan jelas menyebut produk dan jumlah.",
            "parameters": {
                "type": "object",
                "properties": {
                    "produk": {"type": "string"},
                    "jumlah": {"type": "integer"},
                    "nama": {"type": "string"},
                },
                "required": ["produk", "jumlah"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "minta_manusia",
            "description": "Meneruskan percakapan ke admin manusia. Pakai kalau pelanggan minta bicara dengan manusia/admin, atau pertanyaannya di luar kemampuan agent.",
            "parameters": {
                "type": "object",
                "properties": {"alasan": {"type": "string"}},
            },
        },
    },
]


def run_tool(cfg, wa_id, name, args):
    if name == "lihat_produk":
        return tool_lihat_produk(cfg)
    if name == "cek_jam_operasional":
        return tool_cek_jam_operasional(cfg)
    if name == "catat_pesanan":
        return tool_catat_pesanan(cfg, args.get("produk", ""), int(args.get("jumlah", 1)), args.get("nama", ""))
    if name == "minta_manusia":
        return tool_minta_manusia(cfg, wa_id, args.get("alasan", ""))
    return "Tool tidak dikenal."


# ---------------- LLM ----------------

def _call_llm(messages):
    """Satu panggilan chat-completions. Mengembalikan dict pesan assistant."""
    body = json.dumps(
        {"model": OPENAI_MODEL, "messages": messages, "tools": TOOLS_SPEC, "temperature": 0.7}
    ).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]


def _mock_reply(cfg, text):
    """Jawaban tanpa API key: cocokkan kata kunci FAQ/produk, sisanya default."""
    low = text.lower()
    for faq in cfg["faqs"]:
        if faq["q"] in low:
            return faq["a"]
    if any(k in low for k in ("produk", "harga", "jual", "menu", "katalog")):
        return "Ini daftar produk kami kak:\n" + tool_lihat_produk(cfg)
    for p in cfg["products"]:
        keywords = p["name"].lower().replace(" 250g", "").replace(" 1 liter", "").replace(" 200g", "").split()
        if any(k in low for k in keywords if len(k) > 3):
            return (
                f"{p['name']} — Rp{p['price']:,} (stok {p['stock']}) kak. {p['description']} "
                "Mau pesan berapa? Sebut jumlahnya ya, contoh: 'pesan 2'."
            )
    if any(k in low for k in ("jam", "buka", "tutup", "alamat", "lokasi")):
        return tool_cek_jam_operasional(cfg)
    if any(k in low for k in ("manusia", "admin", "orang", "cs")):
        return cfg["human_handoff_message"].format(business_name=cfg["business_name"])
    if any(k in low for k in ("halo", "hai", "hi", "pagi", "siang", "sore", "malam", "assalamualaikum")):
        return (
            f"Halo kak, selamat datang di {cfg['business_name']}! "
            f"{cfg['business_description']} Ada yang bisa saya bantu? "
            "Ketik 'produk' untuk lihat katalog, atau tanya soal ongkir dan pembayaran."
        )
    return (
        "Maaf kak, saya belum paham. Bisa tanya soal produk, harga, ongkir, jam buka, "
        "atau ketik 'admin' untuk bicara dengan manusia."
    )


# ---------------- titik masuk utama ----------------

def reply(wa_id, text):
    """Terima pesan pelanggan (wa_id + teks), kembalikan teks balasan agent."""
    cfg = load_config()
    save_message(wa_id, "user", text)

    if not OPENAI_API_KEY:
        answer = _mock_reply(cfg, text)
        save_message(wa_id, "assistant", answer)
        return answer

    system = (
        f"Kamu adalah asisten AI WhatsApp Business untuk {cfg['business_name']}. "
        f"{cfg['business_description']} Gaya bicara: {cfg['tone']} "
        "Jawab singkat, maksimal 3 kalimat pendek kecuali pelanggan minta daftar. "
        "Jangan mengarang harga atau stok — selalu cek lewat tool lihat_produk. "
        "Jangan menjanjikan diskon, pengiriman, atau hal lain di luar info yang ada. "
        "Kalau pelanggan mau pesan, pastikan produk dan jumlahnya jelas, "
        "lalu catat dengan tool catat_pesanan dan sebutkan total harganya."
    )
    messages = [{"role": "system", "content": system}] + load_history(wa_id)

    for _ in range(5):  # maksimal 5 giliran tool
        msg = _call_llm(messages)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            answer = msg.get("content", "").strip()
            break
        messages.append(msg)
        for call in tool_calls:
            fn = call["function"]["name"]
            args = json.loads(call["function"].get("arguments") or "{}")
            result = run_tool(cfg, wa_id, fn, args)
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result}
            )
    else:
        answer = "Maaf kak, saya sedang kesulitan memprosesnya. Ketik 'admin' untuk dibantu manusia."

    save_message(wa_id, "assistant", answer)
    return answer
