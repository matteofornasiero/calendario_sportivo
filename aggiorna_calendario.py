import json
import os
import urllib.request
from datetime import datetime, timedelta

# ==========================================
# CONFIGURAZIONE API (FOOTBALL-DATA.ORG)
# ==========================================
FOOTBALL_DATA_API_KEY = "6538d15985a7467f9213779686609cbf"

# File di output
OUTPUT_FILE = "dati.js"

def get_dt_str(dt):
    return dt.strftime("%Y-%m-%d")

def fetch_api_matches(competition_code, sport_tag):
    """Scarica i match reali dall'API di football-data.org (senza arbitri, risultati solo post-partita)."""
    if not FOOTBALL_DATA_API_KEY:
        return []
        
    url = f"http://api.football-data.org/v4/competitions/{competition_code}/matches"
    req = urllib.request.Request(url, headers={'X-Auth-Token': FOOTBALL_DATA_API_KEY})
    events = []
    try:
        print(f"Scaricamento match reali per {competition_code}...")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for match in data.get('matches', []):
                utc_date = match['utcDate']
                dt = datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ")
                dt = dt + timedelta(hours=2) # Ora italiana estiva/solare
                
                home_data = match.get('homeTeam', {})
                away_data = match.get('awayTeam', {})
                
                home = home_data.get('shortName') or home_data.get('name', 'Casa')
                away = away_data.get('shortName') or away_data.get('name', 'Trasferta')
                home_crest = home_data.get('crest', '')
                away_crest = away_data.get('crest', '')
                
                matchday = match.get('matchday')
                raw_status = match.get('status', 'SCHEDULED')
                
                # Consideriamo FINISHED solo se la partita è terminata
                is_finished = (raw_status == 'FINISHED')
                score_data = match.get('score', {}).get('fullTime', {})
                
                home_score = score_data.get('home') if is_finished else None
                away_score = score_data.get('away') if is_finished else None
                status = "FINISHED" if is_finished else "SCHEDULED"
                
                stage = match.get('stage', 'REGULAR_SEASON')
                loc = f"Giornata {matchday}" if matchday else stage.replace('_', ' ').title()
                
                events.append({
                    "date": get_dt_str(dt),
                    "time": dt.strftime("%H:%M"),
                    "title": f"{home} - {away}",
                    "sport": sport_tag,
                    "loc": loc,
                    "home": home,
                    "away": away,
                    "homeCrest": home_crest,
                    "awayCrest": away_crest,
                    "homeScore": home_score,
                    "awayScore": away_score,
                    "status": status,
                    "matchday": matchday,
                    "stage": stage
                })
        print(f"  Trovati {len(events)} match per {competition_code}.")
    except Exception as e:
        print(f"  Errore API per {competition_code}: {e}")
    return events

def fetch_f1_matches():
    """Scarica il calendario F1 con circuito e paese tramite Ergast / Jolpi API."""
    url = "http://api.jolpi.ca/ergast/f1/2026.json"
    events = []
    try:
        print("Scaricamento gare per Formula 1...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            for r in races:
                date_str = r['date']
                title = r['raceName']
                circuit = r.get('Circuit', {})
                circuit_name = circuit.get('circuitName', 'Circuito')
                locality = circuit.get('Location', {}).get('locality', '')
                country = circuit.get('Location', {}).get('country', '')
                venue_str = f"{circuit_name}, {locality} ({country})" if locality else circuit_name
                race_time = r.get('time', '15:00:00Z')[:5]
                
                # Gara (Domenica)
                events.append({
                    "date": date_str,
                    "time": race_time or "15:00",
                    "title": f"GARA: {title}",
                    "sport": "f1",
                    "loc": country or "Formula 1",
                    "venue": venue_str,
                    "status": "SCHEDULED"
                })
                
                # Qualifiche (Sabato)
                q_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                events.append({
                    "date": q_date,
                    "time": "16:00",
                    "title": f"Qualifiche: {title}",
                    "sport": "f1",
                    "loc": country or "Formula 1",
                    "venue": venue_str,
                    "status": "SCHEDULED"
                })
        print(f"  Trovate {len(events)} sessioni per F1.")
    except Exception as e:
        print(f"  Errore API per F1: {e}")
    return events

def fetch_espn_nfl_matches():
    """Scarica il calendario NFL da ESPN API."""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20260901-20270228&limit=1000"
    events = []
    try:
        print("Scaricamento match reali NFL da ESPN...")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for ev in data.get("events", []):
                utc_date = ev['date']
                dt = datetime.strptime(utc_date, "%Y-%m-%dT%H:%MZ")
                dt = dt + timedelta(hours=2)
                
                comp = ev.get("competitions", [{}])[0]
                competitors = comp.get("competitors", [])
                
                home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0] if competitors else {})
                away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
                
                home_name = home_c.get("team", {}).get("displayName", "Home")
                away_name = away_c.get("team", {}).get("displayName", "Away")
                home_crest = home_c.get("team", {}).get("logo", "")
                away_crest = away_c.get("team", {}).get("logo", "")
                
                venue_obj = comp.get("venue", {})
                venue_name = venue_obj.get("fullName", "")
                city = venue_obj.get("address", {}).get("city", "")
                venue_str = f"{venue_name}, {city}" if city else venue_name
                
                week = ev.get("week", {}).get("number", "X")
                loc = f"Week {week}"
                
                raw_status = ev.get("status", {}).get("type", {}).get("name", "")
                is_finished = (raw_status == "STATUS_FINAL")
                
                home_score = home_c.get("score") if is_finished else None
                away_score = away_c.get("score") if is_finished else None
                status = "FINISHED" if is_finished else "SCHEDULED"
                
                title = ev.get("shortName", f"{away_name} @ {home_name}")
                if 'TBD' in title:
                    if dt.month == 1:
                        if dt.day <= 18:
                            title = "NFL Wild Card"
                        elif dt.day <= 25:
                            title = "NFL Divisional"
                        else:
                            title = "NFL Conference Championship"
                        loc = "Playoff"
                    elif dt.month == 2:
                        title = "🏆 SUPER BOWL LXI"
                        loc = "Super Bowl"
                
                events.append({
                    "date": get_dt_str(dt),
                    "time": dt.strftime("%H:%M"),
                    "title": title,
                    "sport": "nfl",
                    "loc": loc,
                    "home": home_name,
                    "away": away_name,
                    "homeCrest": home_crest,
                    "awayCrest": away_crest,
                    "homeScore": home_score,
                    "awayScore": away_score,
                    "venue": venue_str,
                    "status": status
                })
        print(f"  Trovati {len(events)} match per NFL.")
    except Exception as e:
        print(f"  Errore API per NFL: {e}")
    return events

def generate_mock_real_data():
    """Genera calendari per Nazionale e Coppe Italiane."""
    events = []
    # 1. NAZIONALE ITALIANA
    try:
        url_italy = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id=133910"
        req_italy = urllib.request.Request(url_italy, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_italy) as r:
            data = json.loads(r.read().decode())
            nazionale_events = data.get('events', []) or []
            for e in nazionale_events:
                time_str = e.get('strTime', '20:45:00')[:5]
                try:
                    h, m = map(int, time_str.split(':'))
                    h = (h + 2) % 24
                    time_str = f"{h:02d}:{m:02d}"
                except:
                    pass
                home = e.get('strHomeTeam', '').replace('Italy', 'Italia')
                away = e.get('strAwayTeam', '').replace('Italy', 'Italia')
                events.append({
                    "date": e.get('dateEvent'),
                    "time": time_str,
                    "title": f"{home} - {away}",
                    "sport": "nazionale",
                    "loc": e.get('strLeague', 'Internazionale'),
                    "home": home,
                    "away": away,
                    "venue": e.get('strVenue', ''),
                    "status": "SCHEDULED"
                })
    except Exception as e:
        print(f"Errore Nazionale: {e}")

    # 2. COPPA ITALIA
    coppa = [
        ("2026-12-02", "Ottavi di Finale - Andata"),
        ("2026-12-16", "Ottavi di Finale - Ritorno"),
        ("2027-01-20", "Quarti di Finale - Andata"),
        ("2027-02-03", "Quarti di Finale - Ritorno"),
        ("2027-03-03", "Semifinali - Andata"),
        ("2027-04-21", "Semifinali - Ritorno"),
        ("2027-05-19", "🏆 Finale Coppa Italia (Roma)")
    ]
    for d, t in coppa:
        events.append({"date": d, "time": "21:00", "title": t, "sport": "seriea", "loc": "Coppa Italia", "venue": "Stadio Olimpico, Roma", "status": "SCHEDULED"})

    # 3. SUPERCOPPA ITALIANA
    supercoppa = [
        ("2027-01-07", "Semifinale 1 (Supercoppa)"),
        ("2027-01-08", "Semifinale 2 (Supercoppa)"),
        ("2027-01-11", "🏆 Finale Supercoppa Italiana")
    ]
    for d, t in supercoppa:
        events.append({"date": d, "time": "20:00", "title": t, "sport": "seriea", "loc": "Supercoppa", "venue": "Al-Awwal Park, Riyadh", "status": "SCHEDULED"})

    return events

# ==========================================
# SCARICAMENTO CLASSIFICHE REALI
# ==========================================
def fetch_all_standings():
    """Scarica le classifiche ufficiali per Serie A, Champions League, F1 e NFL."""
    standings = {
        "seriea": [],
        "champions": [],
        "f1_drivers": [],
        "f1_constructors": [],
        "nfl": []
    }
    
    # 1. CLASSIFICA SERIE A
    if FOOTBALL_DATA_API_KEY:
        try:
            print("Scaricamento Classifica Serie A...")
            url = "http://api.football-data.org/v4/competitions/SA/standings"
            req = urllib.request.Request(url, headers={'X-Auth-Token': FOOTBALL_DATA_API_KEY})
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read().decode())
                table = data.get('standings', [{}])[0].get('table', [])
                for x in table:
                    standings['seriea'].append({
                        "pos": x.get('position'),
                        "name": x.get('team', {}).get('shortName') or x.get('team', {}).get('name'),
                        "crest": x.get('team', {}).get('crest', ''),
                        "played": x.get('playedGames', 0),
                        "won": x.get('won', 0),
                        "draw": x.get('draw', 0),
                        "lost": x.get('lost', 0),
                        "points": x.get('points', 0),
                        "diff": x.get('goalDifference', 0)
                    })
            print(f"  Classifica Serie A caricata: {len(standings['seriea'])} squadre.")
        except Exception as e:
            print(f"  Errore Classifica Serie A: {e}")

    # 2. CLASSIFICA CHAMPIONS LEAGUE
    if FOOTBALL_DATA_API_KEY:
        try:
            print("Scaricamento Classifica Champions League...")
            url = "http://api.football-data.org/v4/competitions/CL/standings?season=2024"
            req = urllib.request.Request(url, headers={'X-Auth-Token': FOOTBALL_DATA_API_KEY})
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read().decode())
                for grp in data.get('standings', []):
                    grp_name = grp.get('group', 'Girone Unico')
                    for x in grp.get('table', []):
                        standings['champions'].append({
                            "pos": x.get('position'),
                            "name": x.get('team', {}).get('shortName') or x.get('team', {}).get('name'),
                            "crest": x.get('team', {}).get('crest', ''),
                            "played": x.get('playedGames', 0),
                            "won": x.get('won', 0),
                            "draw": x.get('draw', 0),
                            "lost": x.get('lost', 0),
                            "points": x.get('points', 0),
                            "diff": x.get('goalDifference', 0),
                            "group": grp_name
                        })
            print(f"  Classifica Champions League caricata: {len(standings['champions'])} squadre.")
        except Exception as e:
            print(f"  Errore Classifica Champions: {e}")

    # 3. F1 PILOTI
    try:
        print("Scaricamento Classifica F1 Piloti...")
        url = "http://api.jolpi.ca/ergast/f1/current/driverStandings.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            d_list = data['MRData']['StandingsTable']['StandingsLists'][0]['DriverStandings']
            for d in d_list:
                driver = d.get('Driver', {})
                constructors = d.get('Constructors', [{}])
                team_name = constructors[0].get('name', '') if constructors else ''
                standings['f1_drivers'].append({
                    "pos": d.get('position'),
                    "name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}",
                    "team": team_name,
                    "points": d.get('points', '0'),
                    "wins": d.get('wins', '0')
                })
        print(f"  Classifica F1 Piloti caricata: {len(standings['f1_drivers'])} piloti.")
    except Exception as e:
        print(f"  Errore F1 Piloti: {e}")

    # 4. F1 COSTRUTTORI
    try:
        print("Scaricamento Classifica F1 Costruttori...")
        url = "http://api.jolpi.ca/ergast/f1/current/constructorStandings.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            c_list = data['MRData']['StandingsTable']['StandingsLists'][0]['ConstructorStandings']
            for c in c_list:
                team = c.get('Constructor', {})
                standings['f1_constructors'].append({
                    "pos": c.get('position'),
                    "name": team.get('name', ''),
                    "points": c.get('points', '0'),
                    "wins": c.get('wins', '0')
                })
        print(f"  Classifica F1 Costruttori caricata: {len(standings['f1_constructors'])} scuderie.")
    except Exception as e:
        print(f"  Errore F1 Costruttori: {e}")

    # 5. NFL STANDINGS
    try:
        print("Scaricamento Classifica NFL da ESPN...")
        url = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            for conf in data.get('children', []):
                conf_name = "AFC" if "American" in conf.get('name', '') else "NFC"
                for entry in conf.get('standings', {}).get('entries', []):
                    stats = {s['name']: s['displayValue'] for s in entry.get('stats', [])}
                    logos = entry.get('team', {}).get('logos', [{}])
                    standings['nfl'].append({
                        "conf": conf_name,
                        "name": entry.get('team', {}).get('displayName', ''),
                        "logo": logos[0].get('href', '') if logos else '',
                        "record": stats.get('overall', ''),
                        "wins": stats.get('wins', '0'),
                        "losses": stats.get('losses', '0'),
                        "diff": stats.get('pointDifferential', '0'),
                        "streak": stats.get('streak', '')
                    })
        print(f"  Classifica NFL caricata: {len(standings['nfl'])} squadre.")
    except Exception as e:
        print(f"  Errore NFL Standings: {e}")

    return standings

def main():
    print("--- Sport OS Data & Standings Fetcher ---")
    all_events = []
    
    # 1. SERIE A & CHAMPIONS LEAGUE
    if FOOTBALL_DATA_API_KEY:
        all_events.extend(fetch_api_matches("SA", "seriea"))
        all_events.extend(fetch_api_matches("CL", "champions"))

    # 2. NFL
    all_events.extend(fetch_espn_nfl_matches())

    # 3. FORMULA 1
    all_events.extend(fetch_f1_matches())

    # 4. NAZIONALE E COPPE
    all_events.extend(generate_mock_real_data())
    
    all_events.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
    
    # 5. CLASSIFICHE UFFICIALI
    standings = fetch_all_standings()

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("window.calendarData = ")
        json.dump(all_events, f, indent=4, ensure_ascii=False)
        f.write(";\n\n")
        f.write("window.standingsData = ")
        json.dump(standings, f, indent=4, ensure_ascii=False)
        f.write(";\n")
        
    print(f"\nSalvataggio completato! {len(all_events)} partite ed eventi + classifiche salvate in {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
