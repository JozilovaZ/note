# Eslatma bot (@eslatmaStudent_bot)

SamDU talabalari uchun Telegram bot. HEMIS'dan olingan ma'lumotlar asosida ishlaydi:

- 🗓 haftalik dars jadvali (xona, vaqt, o'qituvchi)
- 📚 fan resurslari: topshiriqlar va muddatlari
- 📊 davomat, 📈 GPA va akademik qarzdorlik, 👤 profil
- 🔔 eslatmalar: ertalabki jadval, darsdan oldin, yangi NB, sababsiz NB chegarasiga yaqinlashish, topshiriq muddati, yangi topshiriq, GPA o'zgarishi

Parol saqlanmaydi: bazada faqat shifrlangan HEMIS tokeni turadi.

## Sozlamalar (`.env`)

`.env.example` dan nusxa olib to'ldiring:

| O'zgaruvchi | Ma'nosi |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `HEMIS_URL` | `https://student.samdu.uz` |
| `SECRET_KEY` | tokenlarni shifrlash kaliti (pastda qanday yaratish yozilgan) |
| `REMIND_BEFORE` | darsdan necha daqiqa oldin eslatish (standart 5) |
| `MORNING_TIME` | ertalabki xabar vaqti (standart 07:30) |
| `ABSENCE_LIMIT` | semestrda ruxsat etilgan sababsiz NB, soat (standart 74; 50%, 75%, 90% va 100% da ogohlantiriladi; `0` — o'chirish) |

> ⚠️ `SECRET_KEY` yo'qolsa yoki o'zgarsa, barcha foydalanuvchilar qayta kirishi kerak bo'ladi.
> `.env` faylini hech qachon GitHub'ga yoki chatga yubormang.

## Serverga o'rnatish (Docker — tavsiya etiladi)

Kerak: Ubuntu 22.04/24.04 VPS, 512 MB RAM yetarli.

**0. Server HEMIS'ga ulana olishini tekshiring** (ba'zi davlat saytlari chet el IP'larini bloklaydi):

```bash
curl -sI https://student.samdu.uz | head -1     # "HTTP/... 200" yoki 302 chiqishi kerak
```

**1. Docker o'rnatish:**

```bash
curl -fsSL https://get.docker.com | sudo sh
```

**2. Loyihani serverga ko'chirish** (kompyuterdan, loyiha papkasida):

```bash
ssh root@SERVER_IP "mkdir -p /opt/eslatma_bot"
scp -r bot db hemis services deploy config.py main.py requirements.txt \
    Dockerfile .dockerignore docker-compose.yml .env.example \
    root@SERVER_IP:/opt/eslatma_bot/
```

**3. `.env` yaratish** (serverda):

```bash
cd /opt/eslatma_bot
cp .env.example .env
nano .env          # BOT_TOKEN, HEMIS_URL, SECRET_KEY ni yozing
```

Yangi `SECRET_KEY` yaratish:

```bash
docker run --rm python:3.11-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

**4. Kompyuterdagi botni to'xtating.** Bitta token bilan faqat bitta bot ishlashi mumkin, aks holda Telegram `Conflict` xatosini beradi.

**5. Ishga tushirish:**

```bash
docker compose up -d --build
docker compose logs -f        # "Run polling for bot @eslatmaStudent_bot" chiqsa — tayyor
```

Bot server qayta yoqilganda ham o'zi ishga tushadi (`restart: unless-stopped`).

### Kerakli buyruqlar

```bash
docker compose logs -f --tail 100     # loglar
docker compose restart                # qayta ishga tushirish
docker compose up -d --build          # kod yangilangandan keyin
docker compose down                   # to'xtatish (baza saqlanib qoladi)
```

Bazaning zaxira nusxasi:

```bash
docker compose cp bot:/app/data/bot.db ./bot-backup-$(date +%F).db
```

### Mavjud foydalanuvchilarni ko'chirish (ixtiyoriy)

Kompyuterdagi `bot.db` ni ko'chirsangiz, foydalanuvchilar qayta kirishi shart bo'lmaydi.
Buning uchun serverdagi `.env` da **kompyuterdagi bilan bir xil** `SECRET_KEY` bo'lishi kerak:

```bash
scp bot.db root@SERVER_IP:/opt/eslatma_bot/
cd /opt/eslatma_bot
docker compose up -d --build
docker compose cp bot.db bot:/app/data/bot.db && docker compose restart
```

## Docker'siz o'rnatish (systemd)

```bash
sudo apt install -y python3.11 python3.11-venv
sudo useradd --system --home /opt/eslatma_bot eslatma
cd /opt/eslatma_bot
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env
sudo chown -R eslatma /opt/eslatma_bot
sudo cp deploy/eslatma-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now eslatma-bot
journalctl -u eslatma-bot -f          # loglar
```

## Kompyuterda ishga tushirish

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```
