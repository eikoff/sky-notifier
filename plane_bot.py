import os
import requests
import math

# ─────────────────── KONFIGURATION ───────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

# Dein Zentrum (Oker/Goslar)
HARZ_CENTER = (51.8875, 10.45705) 
BUFFER_AREA = (50.8, 9.0, 53.0, 12.0)

# 1. MILITÄR & SPECIAL (Diese wollen wir sehen!)
# GAF: German Air Force, NATO, RCH: Reach (US Air Force), etc.
SPECIAL_PREFIXES = ("GAF", "NATO", "RCH", "DUKE", "TARTN", "BAF", "GAM", "FLG", "VADER", "BND")

# 2. LINIE & PRIVAT (Diese ignorieren wir, außer bei Notfällen)
IGNORE_PREFIXES = ("DLH", "EWG", "RYR", "BAW", "AFR", "KLM", "SWR", "BER", "WZZ", "LOT", "DE-", "CH-")

def get_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def calculate_bearing(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dLon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(dLon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def check_planes():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": BUFFER_AREA[0], "lomin": BUFFER_AREA[1], "lamax": BUFFER_AREA[2], "lomax": BUFFER_AREA[3]}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        states = r.json().get("states", [])
    except: return

    alerts = []
    if states:
        for s in states:
            callsign = (s[1] or "").strip()
            lat, lon, alt, heading, vel, squawk = s[6], s[5], s[7] or 0, s[10], (s[9] or 0) * 3.6, s[14] or ""

            if not lat or heading is None: continue

            # --- FILTER-LOGIK ---
            is_military = callsign.startswith(SPECIAL_PREFIXES)
            is_emergency = squawk in ["7700", "7600"]
            is_ignored = callsign.startswith(IGNORE_PREFIXES)
            
            # Nur weitermachen, wenn es Militär oder ein Notfall ist
            # ODER wenn es KEIN ignorierter Flieger ist UND sehr tief fliegt (z.B. Rettungshubschrauber)
            is_special = is_military or is_emergency or (not is_ignored and alt < 1500 and alt > 0)

            if not is_special:
                continue

            # Berechnung für Treffer
            dist = get_distance(lat, lon, HARZ_CENTER[0], HARZ_CENTER[1])
            bearing_to_me = calculate_bearing(lat, lon, HARZ_CENTER[0], HARZ_CENTER[1])
            angle_diff = abs((heading - bearing_to_me + 180) % 360 - 180)
            eta = (dist / vel) * 60 if vel > 0 else 99

            # Nur alarmieren, wenn im Anflug oder bereits nah
            if dist < 12 or (angle_diff < 25 and eta < 22):
                status = "🎖️ **MILITÄR / SPECIAL**" if is_military else "🚨 **NOTFALL**"
                if not is_military and not is_emergency:
                    status = "🚁 **UNGEWÖHNLICHER TIEFFLUG**"

                link = f"https://www.radarbox.com/flight/{callsign}"
                alerts.append(f"{status}\n✈️ `{callsign}` | {round(alt)}m | {round(dist, 1)}km entfernt\n🔗 [RadarBox]({link})")

    # Versand
    if alerts:
        msg = "✈️ **HARZ SPECIAL RADAR**\n\n" + "\n\n".join(alerts[:5])
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})
    elif GITHUB_EVENT_NAME == "workflow_dispatch":
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": "🧪 **TEST**: System aktiv. Keine 'Specials' im Anflug."})

if __name__ == "__main__":
    check_planes()
