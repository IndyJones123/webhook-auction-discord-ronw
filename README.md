# Discord Auction Gateway

Backend FastAPI + PostgreSQL untuk bot Discord berbasis **Interactions Endpoint** (webhook HTTP, tanpa gateway websocket).

## Command

| Command | Siapa | Fungsi |
|---|---|---|
| `/add-item nama [deskripsi]` | Admin | List barang baru |
| `/bid-item` | Semua | Pilih barang lewat dropdown, masuk antrian |
| `/cancel-bid` | Semua | Pilih bid milik sendiri untuk dibatalkan |
| `/delete-item` | Admin | Unlist barang (bid-nya ikut terhapus) |
| `/status` | Semua | Semua barang + antrian bid, termasuk yang belum di-bid |
| `/delete-bid` | Admin | Pilih barang, hapus bidder **paling depan** (pemenang) |

"Admin" = member dengan permission **Manage Server** atau **Administrator**.
Dropdown Discord maksimal 25 opsi, jadi kalau barang lebih dari 25 hanya 25 pertama yang tampil.

## Setup

1. **Database**: pakai Postgres yang sudah ada (buat database `discord_auction`), atau `docker compose up -d`.
   Tabel dibuat otomatis saat app start (`schema.sql`).
2. **Env**: `copy .env.example .env` lalu isi `DISCORD_APPLICATION_ID`, `DISCORD_PUBLIC_KEY`,
   `DISCORD_BOT_TOKEN`, `DATABASE_URL` (dan `DISCORD_GUILD_ID` supaya command langsung muncul di server kamu).
3. **Install**:
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Daftarkan command** ke Discord: `python -m scripts.register_commands`
5. **Jalankan server**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
6. **Expose ke internet** (Discord butuh HTTPS publik), misal `cloudflared tunnel --url http://localhost:8000` atau ngrok.
7. Di Developer Portal > General Information, isi **Interactions Endpoint URL** dengan `https://<domain-kamu>/interactions`
   lalu Save (Discord akan mengirim PING untuk verifikasi).
8. Invite bot ke server dengan scope `applications.commands` (dan `bot`).

Health check: `GET /health`.

## Struktur

```
app/main.py        endpoint /interactions (verifikasi signature + routing)
app/commands.py    definisi slash command + handler command & dropdown
app/db.py          query PostgreSQL (asyncpg)
app/discord.py     helper Interactions API (signature, response, followup)
schema.sql         tabel items & bids (antrian = urutan id bid)
scripts/register_commands.py
```
