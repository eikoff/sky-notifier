import os
import requests
from datetime import datetime
import pytz

# ─────────────────── KONFIGURATION ───────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

# Bounding Box Harz (Süd, West, Nord, Ost)
HARZ_AREA = (51.4, 10.0, 52.0, 11.2)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True})

def check_planes():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": HARZ_AREA[0], "lomin": HARZ_AREA[1], "lamax": HARZ_AREA[2], "lomax": HARZ_AREA[3]}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        states = r.json().get("states", [])
    except Exception as e:
        print(f"Fehler: {e}")
        return

    is_test = GITHUB_EVENT_NAME == "workflow_dispatch"
    special_flights = []

    if states:
        for s in states:
            callsign = (s[1] or "UNKN").strip()
            altitude = s[7] or 0 # Meter
            velocity = round(s[9] * 3.6) if s[9] else 0 # km/h
            squawk = s[14] or "0000"
            
            is_special = False
            tags = []

            # FILTER 1: Notfälle (Squawk 7700, 7600)
            if squawk in ["7700", "7600"]:
                is_special = True
                tags.append("🚨 NOTFALL/SQUAWK")

            # FILTER 2: Militär (Anhand bekannter Rufzeichen-Kürzel)
            mil_prefixes = ["GAF", "NATO", "IAM", "BAF", "AME", "RCH", "DUKE", "TARTN"]
            if any(callsign.startswith(p) for p in mil_prefixes):
                is_special = True
                tags.append("🎖️ MILITÄR")

            # FILTER 3: Tiefflug (unter 2000m)
            if 0 < altitude < 2000:
                is_special = True
                tags.append("⬇️ TIEFFLUG")

            if is_special or is_test:
                tag_str = " ".join(tags)
                link = f"https://www.radarbox.com/flight/{callsign}"
                special_flights.append(
                    f"{tag_str}\n✈️ **{callsign}**\nHöhe: {round(altitude)}m | Tempo: {velocity}km/h\n🔗 [RadarBox]({link})"
                )

    # Nachricht senden
    if special_flights:
        header = "✈️ **HARZ RADAR: BESONDERHEITEN**\n\n"
        send_telegram(header + "\n\n".join(special_flights[:5]))
    elif is_test:
        send_telegram("🧪 **PLANE-BOT TEST**\nKeine speziellen Flüge im Harz-Sektor.")

if __name__ == "__main__":
    check_planes()
