import os
import requests
from datetime import datetime
import pytz
import time

# ─────────────────── KONFIGURATION ───────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
KP_THRESHOLD = 6
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

GERMAN_TZ = pytz.timezone("Europe/Berlin")

# ───────────────────── QUELLEN ───────────────────────
URL_KP_FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
URL_KP_LIVE = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
URL_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"
URL_OVATION_MAP = "https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg"

session = requests.Session()
session.headers.update({"User-Agent": "AuroraBot/1.2"})

# ─────────────────── TELEGRAM ────────────────────────
def send_telegram_photo(photo_url: str, caption: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Fehler: Konfiguration unvollständig.")
        return

    # Cache-Busting: Zeitstempel an URL hängen, damit Telegram das Bild neu lädt
    busted_url = f"{photo_url}?t={int(time.time())}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": CHAT_ID,
        "photo": busted_url,
        "caption": caption,
        "parse_mode": "Markdown",
    }

    try:
        r = session.post(url, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"Telegram Fehler: {e}")

# ─────────────────── LOGIK-FUNKTIONEN ────────────────
def utc_to_local(utc_dt_string: str) -> str:
    try:
        utc_dt = datetime.strptime(utc_dt_string, "%Y-%m-%d %H:%M:%S")
        utc_dt = pytz.utc.localize(utc_dt)
        return utc_dt.astimezone(GERMAN_TZ).strftime("%d.%m. %H:%M Uhr")
    except:
        return utc_dt_string

def get_kp_symbol(kp: float) -> str:
    if kp >= 7: return "🚨"
    if kp >= 6: return "🟠"
    return "📈"

def check_solar_flares() -> str:
    try:
        r = session.get(URL_ALERTS, timeout=10)
        alerts = r.json()
        for alert in alerts:
            msg = alert.get("message", "")
            if "Space Weather Message Code: ALTTPX" in msg and ("Class M" in msg or "Class X" in msg):
                return "💥 **SOLAR FLARE ALARM!**\nStarker Flare (M/X) registriert. Chance in 1-3 Tagen!\n\n"
    except:
        pass
    return ""

# ───────────────── AURORA CHECK ──────────────────────
def check_aurora() -> None:
    now_de = datetime.now(GERMAN_TZ)
    is_test = GITHUB_EVENT_NAME == "workflow_dispatch"
    alert_text = ""

    #  Solar Flares
    alert_text += check_solar_flares()

    # 2️⃣ Live-Check (Nur nachts zwischen 22:00 und 03:00 Uhr)
    if 22 <= now_de.hour or now_de.hour < 3:
        try:
            live_data = session.get(URL_KP_LIVE, timeout=10).json()
            latest_kp = float(live_data[-1]['kp_index'])
            if latest_kp >= KP_THRESHOLD:
                alert_text += f"🔴 **LIVE-ALARM: Kp {latest_kp}** (Gerade eben!)\n\n"
        except:
            pass

    #  Kp-Forecast mit korrekter Trend-Logik
    try:
        forecast = session.get(URL_KP_FORECAST, timeout=10).json()
        found_kp = []
        # Wir tracken den Trend über alle Intervalle
        prev_val = float(forecast[1][1]) 

        for entry in forecast[2:]: # Start ab dem zweiten Datenpunkt
            curr_val = float(entry[1])
            if curr_val >= KP_THRESHOLD:
                local_time = utc_to_local(entry[0])
                
                # Trend-Symbol
                if curr_val > prev_val: trend = "↗️"
                elif curr_val < prev_val: trend = "↘️"
                else: trend = "➡️"
                
                symbol = get_kp_symbol(curr_val)
                found_kp.append(f"{symbol} Kp {curr_val} {trend} ({local_time})")
            
            prev_val = curr_val # Update für den nächsten Schleifendurchlauf

        if found_kp:
            alert_text += "**Vorhersage (nächste Stunden):**\n" + "\n".join(found_kp[:3])
    except:
        pass

    #  Senden
    if alert_text or is_test:
        caption = "**BOT TESTLAUF**\n\n" if is_test else "**AURORA UPDATE**\n\n"
        
        if alert_text:
            caption += alert_text
        else:
            caption += "Aktuell keine erhöhten Werte (Kp < 6)."
        
        caption += f"\n\n Stand: {now_de.strftime('%H:%M')} Uhr (DE)"
        
        send_telegram_photo(URL_OVATION_MAP, caption)

if __name__ == "__main__":
    check_aurora()
