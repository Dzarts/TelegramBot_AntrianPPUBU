from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread
import csv
import os

# ===================== KONFIGURASI =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [6031464259, 354099742, 5305004129, 5168706730, 1303024958, 92375879]

# ===================== DATA =====================
antrian = []
riwayat_lengkap = []
state_meminta_nama = {}
state_pilihan_kendala = {}
export_confirmation = {}
TAHUN_SAAT_INI = datetime.now().year
TANGGAL_SAAT_INI = datetime.now().date()

CSV_DATA_FILE = "riwayat_data.csv"

def simpan_data_csv():
    with open(CSV_DATA_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Nama", "Kendala", "Waktu"])
        for r in riwayat_lengkap:
            writer.writerow([r['nama'], r['kendala'], r['waktu'].strftime('%Y-%m-%d %H:%M')])

def muat_data_csv():
    global riwayat_lengkap
    if os.path.exists(CSV_DATA_FILE):
        with open(CSV_DATA_FILE, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            riwayat_lengkap = [
                {
                    'nama': row['Nama'],
                    'kendala': row['Kendala'],
                    'waktu': datetime.strptime(row['Waktu'], '%Y-%m-%d %H:%M'),
                    'dipanggil': False
                }
                for row in reader
            ]

# ===================== KEYBOARD =====================
menu_keyboard = ReplyKeyboardMarkup(
    [["Ambil Antrian", "Lihat Antrian", "Next"], ["Reset", "Rekapan"]], resize_keyboard=True
)

kendala_keyboard = ReplyKeyboardMarkup(
    [["Registrasi BU", "Sertifikat", "Pengaduan"], ["Batal"]], resize_keyboard=True
)

export_keyboard = ReplyKeyboardMarkup(
    [["Export Harian", "Export Bulanan"], ["Export Tahunan", "Batal"]], resize_keyboard=True
)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selamat datang. Pilih menu:", reply_markup=menu_keyboard)

async def ambil_antrian_awal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state_pilihan_kendala[user_id] = None
    await update.message.reply_text("\U0001F6E0️ Kendala apa yang dimiliki oleh BU?", reply_markup=kendala_keyboard)

async def proses_nama_antrian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TAHUN_SAAT_INI, TANGGAL_SAAT_INI, antrian

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()
    waktu_sekarang = datetime.now(timezone(timedelta(hours=8)))

    if export_confirmation.get(user_id):
        if text.lower().startswith("export"):
            tipe = text.split()[1].lower()
            await export_csv_tipe(update, context, tipe)
        else:
            await update.message.reply_text("❌ Batal export.", reply_markup=menu_keyboard)
        export_confirmation.pop(user_id, None)
        return

    if text.lower() == "batal":
        state_meminta_nama.pop(user_id, None)
        state_pilihan_kendala.pop(user_id, None)
        await update.message.reply_text("❌ Proses dibatalkan.", reply_markup=menu_keyboard)
        return

    if user_id in state_meminta_nama:
        nama_badan_usaha = text

        if not nama_badan_usaha:
            await update.message.reply_text("❗ Nama tidak boleh kosong. Masukkan lagi.")
            return

        if waktu_sekarang.date() != TANGGAL_SAAT_INI:
            antrian.clear()
            TANGGAL_SAAT_INI = waktu_sekarang.date()
            await update.message.reply_text("🔁 Hari baru dimulai. Antrian aktif telah direset.")

        kendala = state_pilihan_kendala.get(user_id, "Tidak diketahui")
        nomor = len(antrian) + 1

        data_antrian = {
            "user_id": user_id,
            "nama": nama_badan_usaha,
            "kendala": kendala,
            "waktu": waktu_sekarang,
            "dipanggil": False
        }

        antrian.append(data_antrian)
        riwayat_lengkap.append(data_antrian)
        simpan_data_csv()

        state_meminta_nama.pop(user_id, None)
        state_pilihan_kendala.pop(user_id, None)

        await update.message.reply_text(
            f"✅ Antrian berhasil!\n"
            f"Nama: {nama_badan_usaha}\n"
            f"Kendala: {kendala}\n"
            f"Nomor antrian: {nomor}\n"
            f"Total antrian aktif: {len(antrian)}",
            reply_markup=menu_keyboard
        )
        return

    if user_id in state_pilihan_kendala and state_pilihan_kendala[user_id] is None:
        if text in ["Registrasi BU", "Sertifikat", "Pengaduan"]:
            state_pilihan_kendala[user_id] = text
            state_meminta_nama[user_id] = True
            await update.message.reply_text("📝 Masukkan Nama Badan Usaha:", reply_markup=menu_keyboard)
        else:
            await update.message.reply_text("⚠️ Pilih kendala yang tersedia.", reply_markup=kendala_keyboard)
        return

    if text == "Ambil Antrian":
        await ambil_antrian_awal(update, context)
    elif text == "Lihat Antrian":
        await lihat_antrian(update)
    elif text == "Next":
        await next_antrian(update)
    elif text == "Reset":
        antrian.clear()
        await update.message.reply_text("✅ Antrian aktif hari ini telah di-reset.", reply_markup=menu_keyboard)
    elif text == "Rekapan":
        await tampilkan_rekapan(update)
    else:
        await update.message.reply_text("❓ Gunakan menu tombol.", reply_markup=menu_keyboard)

async def lihat_antrian(update: Update):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin.", reply_markup=menu_keyboard)
        return

    if not antrian:
        await update.message.reply_text("📭 Antrian kosong.", reply_markup=menu_keyboard)
        return

    teks = "📋 Daftar Antrian:\n"
    for idx, o in enumerate(antrian, start=1):
        status = "✅" if o.get("dipanggil") else "⬜"
        teks += f"{idx}. {status} {o['nama']}\n   🛠️ {o['kendala']}\n   ⏰ {o['waktu'].strftime('%H:%M')}\n"

    await update.message.reply_text(teks, reply_markup=menu_keyboard)

async def next_antrian(update: Update):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Hanya admin.", reply_markup=menu_keyboard)
        return

    berikutnya = next((a for a in antrian if not a.get("dipanggil")), None)
    if not berikutnya:
        await update.message.reply_text("✅ Semua antrian telah dipanggil.", reply_markup=menu_keyboard)
        return

    nomor = antrian.index(berikutnya) + 1
    berikutnya["dipanggil"] = True

    await update.message.reply_text(
        f"📢 Memanggil antrian #{nomor}:\n👤 {berikutnya['nama']}\n🛠️ {berikutnya['kendala']}",
        reply_markup=menu_keyboard
    )

async def tampilkan_rekapan(update: Update):
    now = datetime.now(timezone(timedelta(hours=8)))

    hari_ini = [r for r in riwayat_lengkap if r['waktu'].date() == now.date()]
    bulan_ini = [r for r in riwayat_lengkap if r['waktu'].month == now.month and r['waktu'].year == now.year]
    tahun_ini = [r for r in riwayat_lengkap if r['waktu'].year == now.year]

    def hitung(data):
        return {
            "Registrasi BU": len([d for d in data if d['kendala'] == "Registrasi BU"]),
            "Sertifikat": len([d for d in data if d['kendala'] == "Sertifikat"]),
            "Pengaduan": len([d for d in data if d['kendala'] == "Pengaduan"])
        }

    h = hitung(hari_ini)
    b = hitung(bulan_ini)
    t = hitung(tahun_ini)

    pesan = (
        f"📊 Statistik Antrian {now.strftime('%d %B %Y')}\n\n"
        f"📆 Hari Ini: {len(hari_ini)} antrian\n"
        f"   📌 Registrasi BU: {h['Registrasi BU']}\n"
        f"   📄 Sertifikat: {h['Sertifikat']}\n"
        f"   📢 Pengaduan: {h['Pengaduan']}\n\n"
        f"🗓️ Bulan Ini: {len(bulan_ini)} antrian\n"
        f"   📌 Registrasi BU: {b['Registrasi BU']}\n"
        f"   📄 Sertifikat: {b['Sertifikat']}\n"
        f"   📢 Pengaduan: {b['Pengaduan']}\n\n"
        f"📅 Tahun Ini: {len(tahun_ini)} antrian\n"
        f"   📌 Registrasi BU: {t['Registrasi BU']}\n"
        f"   📄 Sertifikat: {t['Sertifikat']}\n"
        f"   📢 Pengaduan: {t['Pengaduan']}"
    )

    await update.message.reply_text(pesan, reply_markup=export_keyboard)
    export_confirmation[update.effective_user.id] = True

async def export_csv_tipe(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):
    now = datetime.now(timezone(timedelta(hours=8)))
    if tipe == "harian":
        data = [r for r in riwayat_lengkap if r['waktu'].date() == now.date()]
    elif tipe == "bulanan":
        data = [r for r in riwayat_lengkap if r['waktu'].month == now.month and r['waktu'].year == now.year]
    elif tipe == "tahunan":
        data = [r for r in riwayat_lengkap if r['waktu'].year == now.year]
    else:
        await update.message.reply_text("❌ Format tidak dikenal.", reply_markup=menu_keyboard)
        return

    if not data:
        await update.message.reply_text("📭 Tidak ada data untuk export.", reply_markup=menu_keyboard)
        return

    nama_file = f"rekap_{tipe}_{now.strftime('%Y%m%d%H%M%S')}.csv"
    with open(nama_file, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Nama", "Kendala", "Waktu"])
        for r in data:
            writer.writerow([r['nama'], r['kendala'], r['waktu'].strftime('%Y-%m-%d %H:%M')])

    await update.message.reply_document(document=InputFile(nama_file, filename=nama_file))
    os.remove(nama_file)

# ===================== FLASK KEEP ALIVE =====================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "✅ Bot aktif"

def run():
    app_web.run(host='0.0.0.0', port=10000)

Thread(target=run).start()

# ===================== JALANKAN BOT =====================
muat_data_csv()

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), proses_nama_antrian))
app.run_polling()
