import os
import requests
import pytz
import time
from datetime import datetime

# ─────────────────── KONFIGURATION ───────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
KP_THRESHOLD = 6
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")
GERMAN_TZ = pytz.timezone("Europe/Berlin")

# NOAA API Endpunkte
URL_KP_FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
URL_KP_LIVE = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
URL_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"
URL_OVATION_MAP = "https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg"

# Globaler Session-Header
session = requests.Session()
session.headers.update({"User-Agent": "AuroraBot_Goslar_V3"})

# ─────────────────── HILFSFUNKTIONEN ───────────────────

def utc_to_local(utc_dt_string):
    """Konvertiert NOAA-Zeitstempel in deutsche Lokalzeit."""
    try:
        utc_dt = datetime.strptime(utc_dt_string, "%Y-%m-%d %H:%M:%S")
        utc_dt = pytz.utc.localize(utc_dt)
        return utc_dt.astimezone(GERMAN_TZ)
    except Exception as e:
        print(f"Fehler bei Zeitumrechnung: {e}")
        return None

def get_kp_symbol(kp):
    """Gibt ein Emoji basierend auf dem Kp-Wert zurück."""
    if kp >= 7: 
        return "🚨"
    if kp >= 6: 
        return "🟠"
    return "📈"

def is_dark_in_germany():
    """Prüft, ob es in DE aktuell zwischen 20:00 und 05:00 Uhr ist."""
    now_de = datetime.now(GERMAN_TZ)
    return now_de.hour >= 20 or now_de.hour <= 5

# ─────────────────── KERN-MODULE ──────────────────────

def check_solar_flares():
    """Sucht nach starken Solar Flares (M/X Klasse)."""
    try:
        r = session.get(URL_ALERTS, timeout=10)
        r.raise_for_status()
        alerts = r.json()
        for alert in alerts:
            msg = alert.get("message", "")
            if "Space Weather Message Code: ALTTPX" in msg:
                if "Class M" in msg or "Class X" in msg:
                    return "💥 **SOLAR FLARE ALARM!**\nStarker Ausbruch registriert. Polarlichter in 1-3 Tagen möglich!\n\n"
    except Exception as e:
        print(f"Fehler im Flare-Check: {e}")
    return ""

def get_forecast_data():
    """Holt Kp-Vorhersage und filtert nach zukünftigen deutschen Nachtstunden."""
    forecast_text = ""
    try:
        r = session.get(URL_KP_FORECAST, timeout=10)
        r.raise_for_status()
        forecast = r.json() # Format: [ ["time", "kp", ...], [...] ]
        
        # Aktuelle Zeit in deutscher Zeitzone
        now_de = datetime.now(GERMAN_TZ)
        
        found_intervals = []
        # Wir starten bei Index 2, um prev_val aus Index 1 zu haben
        prev_val = float(forecast[1][1]) 

        for entry in forecast[2:]:
            curr_val = float(entry[1])
            local_dt = utc_to_local(entry[0])
            
            if local_dt and curr_val >= KP_THRESHOLD:
                # FILTER: Nur zukünftige Zeiten
                if local_dt > now_de:
                    # FILTER: Nur wenn das Vorhersage-Fenster in der deutschen Nacht liegt
                    if local_dt.hour >= 20 or local_dt.hour <= 5:
                        trend = "↗️" if curr_val > prev_val else "↘️" if curr_val < prev_val else "➡️"
                        symbol = get_kp_symbol(curr_val)
                        time_str = local_dt.strftime("%d.%m. %H:%M Uhr")
                        found_intervals.append(f"{symbol} Kp {curr_val} {trend} ({time_str})")
            
            prev_val = curr_val

        if found_intervals:
            forecast_text = "**Vorhersage für die Nacht:**\n" + "\n".join(found_intervals[:4]) + "\n\n"
    except Exception as e:
        print(f"Fehler im Forecast-Check: {e}")
    return forecast_text

def get_live_data():
    """Prüft den aktuellen Echtzeit-Kp-Wert."""
    try:
        r = session.get(URL_KP_LIVE, timeout=10)
        r.raise_for_status()
        live_data = r.json()
        latest_kp = float(live_data[-1]['kp_index'])
        if latest_kp >= KP_THRESHOLD:
            return f"🔴 **LIVE-ALARM: Kp {latest_kp}** (Gerade eben gemessen!)\n\n"
    except Exception as e:
        print(f"Fehler im Live-Check: {e}")
    return ""

# ─────────────────── HAUPTFUNKTION ────────────────────

def run_bot():
    is_test = (GITHUB_EVENT_NAME == "workflow_dispatch")
    is_dark = is_dark_in_germany()
    
    flare_alert = check_solar_flares()
    live_alert = get_live_data() if is_dark else ""
    forecast_alert = get_forecast_data()
    
    # Logik: Wann senden wir?
    # 1. Solar Flare gefunden (immer)
    # 2. Es ist Nacht UND (Live-Alarm ODER Forecast-Alarm)
    # 3. Es ist ein manueller Testlauf
    
    has_aurora_data = (live_alert != "" or forecast_alert != "")
    should_send = flare_alert != "" or (is_dark and has_aurora_data) or is_test

    if should_send:
        # Nachricht zusammenbauen
        caption = "🧪 **BOT TESTLAUF**\n\n" if is_test else "🌌 **AURORA UPDATE** 🌌\n\n"
        
        if flare_alert: 
            caption += flare_alert
        
        if is_dark or is_test:
            if has_aurora_data:
                caption += live_alert + forecast_alert
            else:
                caption += "Aktuell keine erhöhten Kp-Werte für die Nachtstunden."
        else:
            caption += "Tagsüber werden keine Kp-Alarme gesendet (Warten auf die Nacht)."

        caption += f"\n🕒 Stand: {datetime.now(GERMAN_TZ).strftime('%H:%M')} Uhr (DE)"

        # Telegram Versand mit Cache-Busting
        busted_url = f"{URL_OVATION_MAP}?t={int(time.time())}"
        try:
            r = session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                json={
                    "chat_id": CHAT_ID,
                    "photo": busted_url,
                    "caption": caption,
                    "parse_mode": "Markdown"
                },
                timeout=20
            )
            r.raise_for_status()
            print("Erfolgreich an Telegram gesendet.")
        except Exception as e:
            print(f"Telegram Sende-Fehler: {e}")
    else:
        print("Keine relevanten Ereignisse. Bot bleibt stumm.")

if __name__ == "__main__":
    run_bot()
