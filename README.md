# AI Agent WhatsApp Business

Agent AI untuk nomor WhatsApp Business kamu: membalas pelanggan otomatis,
menjawab soal produk, harga, ongkir, jam buka, mencatat pesanan, dan
meneruskan ke admin manusia kalau diminta.

**Tidak perlu install apa pun** — cukup Python 3.11+ (pustaka standar saja).

## File-file

| File | Fungsi |
|---|---|
| `app.py` | Server webhook: menerima pesan dari Meta, membalas via Graph API |
| `agent.py` | Otak agent: memori chat, tools, panggilan ke model AI |
| `config.json` | Profil usahamu — EDIT INI: nama toko, produk, harga, FAQ, jam buka |
| `test_webhook.py` | Tes end-to-end tanpa akun Meta |
| `.env.example` | Contoh pengaturan rahasia (salin jadi `.env`) |

## Cara kerja

```
Pelanggan chat nomor WA Business
        ↓  (webhook Meta)
   app.py menerima pesan
        ↓
   agent.py: model AI memutuskan
        ↓  (bila perlu)
   tools: lihat_produk / cek_jam_operasional / catat_pesanan / minta_manusia
        ↓
   balasan dikirim ke pelanggan via WhatsApp
```

Pesanan tercatat di `orders.jsonl`, permintaan bicara dengan manusia di
`handoffs.jsonl`, riwayat chat tersimpan di `chats.db`.

## 1. Tes di laptop dulu (tanpa akun Meta, gratis)

```bash
cd wa-business-agent
cp .env.example .env
python3 test_webhook.py
```

Kamu akan melihat balasan agent untuk 3 pesan contoh. Tanpa
`OPENAI_API_KEY`, agent jalan dalam **MOCK MODE**: menjawab dari FAQ dan
daftar produk di `config.json` — cukup untuk membuktikan webhook bekerja.

## 2. Sesuaikan dengan usahamu

Edit `config.json`: ganti `business_name`, `business_description`,
`products` (nama, harga, stok), `faqs`, dan `working_hours`. Tidak perlu
mengubah kode.

## 3. Sambungkan ke WhatsApp Business (resmi, dari Meta)

1. Buka [developers.facebook.com](https://developers.facebook.com) → buat
   aplikasi → tambah produk **WhatsApp**.
2. Di menu WhatsApp → API Setup: kamu dapat **nomor uji coba gratis** dan
   **token sementara**. Simpan `PHONE_NUMBER_ID` dan `WHATSAPP_TOKEN`.
   (Token sementara hanya berlaku 24 jam — untuk permanen, buat token
   permanen di Business Settings → System Users.)
3. Daftarkan nomor WhatsApp Business kamu sendiri kalau mau pakai nomor
   asli (perlu verifikasi bisnis Meta).

## 4. Buat server bisa diakses internet

Meta harus bisa memanggil webhook kamu, jadi server lokal saja tidak cukup.
Pilihan gampang:

- **Tes cepat:** [ngrok](https://ngrok.com) — `ngrok http 8000`, dapat URL
  `https://xxxx.ngrok-free.app`.
- **Produksi:** deploy ke VPS / Railway / Render / Fly.io, lalu jalankan
  `python3 app.py` di sana.
- **Paling gampang (gratis):** repo ini sudah siap deploy ke Render —
  buka [dashboard.render.com](https://dashboard.render.com) → New →
  Web Service → pilih repo ini → Render memakai `render.yaml` otomatis.
  Setelah deploy, isi environment variables di Render: `WHATSAPP_TOKEN`,
  `PHONE_NUMBER_ID`, `OPENAI_API_KEY` (dan `VERIFY_TOKEN` yang dibuat
  otomatis). URL webhook kamu: `https://NAMA-SERVICE.onrender.com/webhook`.

## 5. Pasang webhook di Meta

1. Jalankan server: `python3 app.py` (pastikan `.env` sudah diisi).
2. Di Meta Developers → WhatsApp → Configuration → Webhook → Edit:
   - **Callback URL:** `https://ALAMAT-SERVER-KAMU/webhook`
   - **Verify token:** isi sama dengan `VERIFY_TOKEN` di `.env` (mis. `rahasia123`)
   - Klik **Verify and save**.
3. Subscribe ke field **messages**.

## 6. Pasang kunci AI (supaya jawabannya pintar)

Tanpa kunci API, agent hanya menjawab dari FAQ/produk (mock mode). Untuk
jawaban AI penuh:

1. Daftar di [platform.openai.com](https://platform.openai.com) (atau
   provider lain yang kompatibel: Groq, OpenRouter) dan buat API key.
2. Isi di `.env`: `OPENAI_API_KEY=sk-...`
3. Restart server. (Biaya: model `gpt-4o-mini` sangat murah, umumnya
   Rp1.000–Rp5.000 per seribu pesan pelanggan.)

## Batas yang perlu kamu tahu

- Akun WhatsApp Business API **tidak bisa** dipakai bersama aplikasi
  WhatsApp Business di HP untuk nomor yang sama — pilih salah satu.
- Template message berbayar berlaku kalau kamu menghubungi pelanggan lebih
  dari 24 jam setelah pesan terakhir mereka (aturan Meta).
- Jangan pernah membagikan isi `.env` (token dan API key) ke siapa pun.
- Bot WhatsApp tidak resmi (mis. yang pakai WhatsApp Web / Baileys) bisa
  membuat nomor diblokir — proyek ini memakai jalur resmi Meta.

## Perintah berguna

```bash
python3 app.py            # jalankan server
python3 test_webhook.py   # tes webhook + agent
cat orders.jsonl          # lihat pesanan yang dicatat agent
cat handoffs.jsonl        # lihat pelanggan yang minta admin
```
