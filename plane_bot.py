import os
import requests
import math
from datetime import datetime

# ─────────────────── KONFIGURATION ───────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

# Dein spezifisches Zentrum (Oker/Goslar)
HARZ_CENTER = (51.8875, 10.45705) 

# Pufferzone für Vorhersage (ca. 120km Radius)
BUFFER_AREA = (50.8, 9.0, 53.0, 12.0)

# Nahbereich (Wann gilt ein Flugzeug als "über dir"?)
# ca. 10km Radius um dein Zentrum
PROXIMITY_RANGE = 0.1 

def calculate_bearing(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dLon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(dLon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def get_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def check_planes():
    # Wir nutzen die OpenSky API
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": BUFFER_AREA[0], "lomin": BUFFER_AREA[1], "lamax": BUFFER_AREA[2], "lomax": BUFFER_AREA[3]}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        states = r.json().get("states", [])
    except Exception as e:
        print(f"API Fehler: {e}")
        return

    alerts = []
    if states:
        for s in states:
            callsign = (s[1] or "UNKN").strip()
            lat, lon = s[6], s[5]
            heading = s[10]
            velocity = (s[9] or 0) * 3.6
            altitude = s[7] or 0
            squawk = s[14] or ""

            if not lat or heading is None or velocity < 150: continue

            # Distanz zum Zentrum berechnen
            dist = get_distance(lat, lon, HARZ_CENTER[0], HARZ_CENTER[1])
            
            # Kurs-Analyse: Zeigt die Nase in deine Richtung?
            bearing_to_me = calculate_bearing(lat, lon, HARZ_CENTER[0], HARZ_CENTER[1])
            angle_diff = abs((heading - bearing_to_me + 180) % 360 - 180)
            
            # ETA berechnen
            eta = (dist / velocity) * 60 

            status = ""
            # Logik: Im Nahbereich (10km) oder im Anflug (Kurs stimmt & ETA < 20 Min)
            if dist < 10:
                status = "🔴 **DIREKT ÜBER DIR / NAHBEREICH**"
            elif angle_diff < 25 and eta < 22:
                status = f"🟡 **ANFLUG AUF DEINEN STANDORT** (ETA: {round(eta)} Min)"
            
            # Sonder-Filter: Notfall oder Militär (GAF = German Air Force)
            if squawk in ["7700", "7600"] or callsign.startswith(("GAF", "NATO", "DUKE")):
                status = "🚨 **SONDERFLUG / MILITÄR** " + (status if status else f"(Dist: {round(dist)}km)")

            if status:
                link = f"https://www.radarbox.com/flight/{callsign}"
                alerts.append(f"{status}\n✈️ `{callsign}` | {round(altitude)}m | {round(velocity)}km/h\n📍 Distanz: {round(dist, 1)}km\n🔗 [RadarBox]({link})")

    # Senden der Nachricht
    if alerts or GITHUB_EVENT_NAME == "workflow_dispatch":
        msg = "✈️ **HARZ RADAR (GOSLAR/OKER)**\n\n"
        if alerts:
            msg += "\n\n".join(alerts[:5])
        else:
            msg += "Aktuell kein relevanter Anflug im Zeitfenster."
            
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

if __name__ == "__main__":
    check_planes()
