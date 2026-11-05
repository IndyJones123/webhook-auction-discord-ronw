# Discord Auction Gateway

Backend FastAPI + PostgreSQL untuk bot Discord berbasis **Interactions Endpoint** (webhook HTTP, tanpa gateway websocket).
Bot tidak perlu "online" seperti bot biasa: Discord mengirim setiap slash command ke `POST /interactions`
di server kamu, lalu server membalas dalam waktu maksimal 3 detik.

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

---

## 1. Setup aplikasi di Discord Developer Portal

1. Buka <https://discord.com/developers/applications> → **New Application** → beri nama → Create.
2. Halaman **General Information**, catat:
   - **Application ID** → `DISCORD_APPLICATION_ID`
   - **Public Key** → `DISCORD_PUBLIC_KEY`
3. Menu **Bot** → **Reset Token** → salin token → `DISCORD_BOT_TOKEN`.
   Token hanya tampil sekali. Simpan baik-baik dan jangan di-commit.
   Token ini hanya dipakai untuk mendaftarkan slash command; app tidak login sebagai bot.
   Privileged Gateway Intents tidak perlu diaktifkan.
4. **ID server** (opsional, untuk `DISCORD_GUILD_ID`): di Discord, aktifkan
   *User Settings → Advanced → Developer Mode*, lalu klik kanan nama server → **Copy Server ID**.
5. **Invite bot ke server**: menu **Installation** (atau **OAuth2 → URL Generator**), centang scope
   `applications.commands` (dan `bot` kalau mau bot tampil di daftar member), lalu buka URL yang dihasilkan
   dan pilih server. Bentuk URL-nya kurang lebih:
   ```
   https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=applications.commands+bot
   ```

**Interactions Endpoint URL** baru diisi setelah server jalan dan bisa diakses lewat HTTPS (langkah 3.6).

---

## 2. Menjalankan di lokal (development)

1. **Database**: `docker compose up -d` (Postgres di `localhost:5432`, user/password `postgres`),
   atau pakai Postgres yang sudah ada dan buat database `discord_auction`.
   Tabel dibuat otomatis saat app start (`schema.sql`).
2. **Env**: `copy .env.example .env` lalu isi nilai dari langkah 1.
   Isi `DISCORD_GUILD_ID` supaya command langsung muncul di server kamu.
3. **Install** (Windows):
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Daftarkan command**: `python -m scripts.register_commands`
5. **Jalankan**: `uvicorn app.main:app --reload --port 8000`
6. **Expose ke internet** (Discord butuh HTTPS publik):
   `cloudflared tunnel --url http://localhost:8000` atau `ngrok http 8000`.
7. Isi **Interactions Endpoint URL** di Developer Portal dengan `https://<url-tunnel>/interactions` lalu Save.

URL tunnel gratis berubah setiap kali dijalankan ulang, jadi cara ini hanya untuk testing.

---

## 3. Deploy ke production (VPS Ubuntu)

Contoh di bawah memakai Ubuntu 22.04/24.04, Python 3.12, PostgreSQL, systemd, dan Nginx + Let's Encrypt.
Yang dibutuhkan: VPS dengan IP publik dan sebuah domain/subdomain (misal `auction.domainkamu.com`)
yang record **A**-nya sudah mengarah ke IP VPS.

Pilih region VPS yang dekat dengan server Discord (misal Singapore atau US). Discord membatalkan
interaction yang tidak dibalas dalam 3 detik.

### 3.1 Install paket

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv postgresql nginx certbot python3-certbot-nginx git
```

Kalau `python3.12` tidak tersedia di repo Ubuntu kamu, tambahkan PPA `deadsnakes` atau jalankan via Docker.

### 3.2 Siapkan database

```bash
sudo -u postgres psql
```
```sql
CREATE USER auction WITH PASSWORD 'ganti_password_kuat';
CREATE DATABASE discord_auction OWNER auction;
\q
```

Postgres cukup listen di `localhost` (default). Jangan buka port 5432 ke internet.

> Kalau mau pakai `docker-compose.yml` di production, **ganti** `POSTGRES_PASSWORD` dan ubah
> `ports` menjadi `"127.0.0.1:5432:5432"` supaya database tidak terekspos ke publik.

### 3.3 Upload kode dan install dependency

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin auction
sudo mkdir -p /opt/discord-auction
sudo chown auction:auction /opt/discord-auction

# clone repo (atau upload via scp/rsync, tanpa folder .venv dan .env)
sudo -u auction git clone <url-repo> /opt/discord-auction
cd /opt/discord-auction

sudo -u auction python3.12 -m venv .venv
sudo -u auction .venv/bin/pip install -r requirements.txt
```

### 3.4 Isi `.env`

```bash
sudo -u auction cp .env.example .env
sudo -u auction nano .env
sudo chmod 600 .env
```

```env
DISCORD_APPLICATION_ID=123456789012345678
DISCORD_PUBLIC_KEY=abcdef...
DISCORD_BOT_TOKEN=MTIz...
DISCORD_GUILD_ID=
DATABASE_URL=postgresql://auction:ganti_password_kuat@localhost:5432/discord_auction
```

- Kosongkan `DISCORD_GUILD_ID` untuk mendaftarkan command secara **global** (berlaku di semua server
  tempat bot di-invite; propagasi bisa sampai 1 jam).
- Isi `DISCORD_GUILD_ID` kalau bot hanya untuk satu server; command langsung muncul.

Lalu daftarkan command:

```bash
sudo -u auction .venv/bin/python -m scripts.register_commands
```

Ulangi perintah ini setiap kali `DEFINITIONS` di `app/commands.py` berubah.

### 3.5 Jalankan sebagai service (systemd)

Buat `/etc/systemd/system/discord-auction.service`:

```ini
[Unit]
Description=Discord Auction Gateway
After=network.target postgresql.service

[Service]
User=auction
Group=auction
WorkingDirectory=/opt/discord-auction
ExecStart=/opt/discord-auction/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-auction
sudo systemctl status discord-auction
curl http://127.0.0.1:8000/health     # harus {"status":"ok"}
```

App hanya listen di `127.0.0.1`; akses dari luar lewat Nginx. Semua state ada di Postgres, jadi aman
memakai lebih dari satu worker.

### 3.6 Nginx + HTTPS

Buat `/etc/nginx/sites-available/discord-auction`:

```nginx
server {
    listen 80;
    server_name auction.domainkamu.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/discord-auction /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d auction.domainkamu.com   # pasang SSL + auto-renew

sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Cek dari luar: `curl https://auction.domainkamu.com/health`.

**Alternatif tanpa domain/port terbuka:** pakai [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
dengan *named tunnel* (bukan quick tunnel) yang mengarah ke `http://localhost:8000`, lalu lewati bagian Nginx/certbot.

### 3.7 Hubungkan ke Discord

1. Developer Portal → aplikasi kamu → **General Information**.
2. Isi **Interactions Endpoint URL**: `https://auction.domainkamu.com/interactions` → **Save Changes**.
3. Discord akan mengirim PING bertanda tangan dan request dengan signature palsu. Save hanya berhasil
   kalau server membalas PONG dan menolak signature yang salah (401). Kalau gagal, lihat bagian Troubleshooting.
4. Pastikan bot sudah di-invite ke server (langkah 1.5), lalu ketik `/` di channel. Command bot akan muncul.

Selesai. Coba `/add-item` (sebagai admin) lalu `/bid-item` dan `/status`.

---

## Seeder item

Untuk mengisi banyak item sekaligus (tanpa `/add-item` satu per satu), isi `scripts/data/items.json`:

```json
[
  {"name": "Nama Item", "description": "Deskripsi opsional"},
  {"name": "Item Lain"}
]
```

lalu jalankan:

```
python -m scripts.seed_items                    # pakai scripts/data/items.json
python -m scripts.seed_items path/lain.json     # atau file lain
```

Item yang namanya sudah ada (tidak peduli huruf besar/kecil) dilewati, jadi aman dijalankan berulang.
Nama maksimal 100 karakter.

---

## 4. Operasional

**Lihat log**
```bash
sudo journalctl -u discord-auction -f
```

**Update kode**
```bash
cd /opt/discord-auction
sudo -u auction git pull
sudo -u auction .venv/bin/pip install -r requirements.txt
sudo -u auction .venv/bin/python -m scripts.register_commands   # kalau ada perubahan command
sudo systemctl restart discord-auction
```

**Backup database**
```bash
sudo -u postgres pg_dump discord_auction > backup_$(date +%F).sql
# restore: sudo -u postgres psql discord_auction < backup_YYYY-MM-DD.sql
```

**Health check**: `GET /health` mengecek koneksi ke database. Bisa dipakai untuk uptime monitor.

**Keamanan**
- Jangan commit `.env` (sudah ada di `.gitignore`). Kalau token bocor, segera **Reset Token** di menu Bot.
- Endpoint `/interactions` memverifikasi signature Ed25519 dari Discord, jadi request palsu ditolak dengan 401.
- Postgres jangan diekspos ke internet; pakai password yang kuat.

---

## 5. Troubleshooting

| Gejala | Penyebab / solusi |
|---|---|
| Save Interactions Endpoint URL gagal ("could not be verified") | Server tidak bisa diakses lewat HTTPS, `DISCORD_PUBLIC_KEY` salah (atau milik aplikasi lain), atau service mati. Cek `curl https://domain/health` dan `journalctl`. |
| Command tidak muncul saat ketik `/` | Belum menjalankan `register_commands`, bot belum di-invite dengan scope `applications.commands`, atau command global masih propagasi (tunggu hingga 1 jam / pakai `DISCORD_GUILD_ID`). Coba juga restart aplikasi Discord (Ctrl+R). |
| Command admin tidak terlihat oleh member | Disengaja: command admin memakai `default_member_permissions` Manage Server. Bisa diubah di *Server Settings → Integrations*. |
| "The application did not respond" | Server telat membalas (>3 detik) atau error. Cek log dan koneksi ke database. |
| App gagal start: `Environment variable ... belum diisi` | `.env` tidak ada di `WorkingDirectory` atau variabelnya kosong. |
| `register_commands` gagal 401 | `DISCORD_BOT_TOKEN` salah atau sudah di-reset. |

---

## Struktur

```
app/main.py        endpoint /interactions (verifikasi signature + routing) dan /health
app/commands.py    definisi slash command + handler command & dropdown
app/db.py          query PostgreSQL (asyncpg)
app/discord.py     helper Interactions API (signature, response, followup)
app/config.py      baca konfigurasi dari .env
schema.sql         tabel items & bids (antrian = urutan id bid)
scripts/register_commands.py   daftarkan slash command ke Discord
```
