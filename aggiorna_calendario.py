"""Aggiorna dati verificabili, conservando l'ultima copia valida di ogni fonte."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "dati.js"
ROME = ZoneInfo("Europe/Rome")
TIMEOUT = 30


def football_key():
    # Su GitHub arriva dai Secrets; .env serve soltanto alla copia locale.
    if "FOOTBALL_DATA_API_KEY" in os.environ:
        return os.environ["FOOTBALL_DATA_API_KEY"].strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("FOOTBALL_DATA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def get_json(url, authenticated=False):
    headers = {"User-Agent": "Sport-OS/2.0", "Accept": "application/json"}
    if authenticated:
        key = football_key()
        if not key:
            raise RuntimeError("Manca il Secret FOOTBALL_DATA_API_KEY")
        headers["X-Auth-Token"] = key
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"HTTP {exc.code} dalla fonte dati") from exc
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("Fonte dati non raggiungibile")
        time.sleep(2 ** attempt)


def parse_utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def event_clock(date_str, time_str=None, confirmed=True):
    if not time_str or not confirmed:
        return {"date": date_str[:10], "time": "", "timeConfirmed": False, "startUtc": None}
    utc = parse_utc(f"{date_str[:10]}T{time_str}")
    local = utc.astimezone(ROME)
    return {"date": local.strftime("%Y-%m-%d"), "time": local.strftime("%H:%M"),
            "timeConfirmed": True, "startUtc": utc.astimezone(timezone.utc).isoformat()}


def timestamp_clock(value, confirmed=True):
    date_str, time_str = value.split("T", 1)
    return event_clock(date_str, time_str, confirmed)


def is_top_match(sport, title, home="", away=""):
    text = f"{title} {home} {away}".lower()
    if sport == "seriea":
        return "torino" in text
    if sport == "nfl":
        return "broncos" in text or "denver" in text
    if sport == "f1":
        return title.startswith("GARA:")
    if sport == "champions":
        return any(team in text for team in ("inter", "milan", "juventus", "atalanta", "bologna", "roma", "lazio", "napoli", "fiorentina"))
    return sport == "nazionale"


def parse_football_matches(data, sport):
    events = []
    for match in data["matches"]:
        status = match.get("status", "SCHEDULED")
        home_data, away_data = match["homeTeam"], match["awayTeam"]
        home = home_data.get("shortName") or home_data.get("name", "Casa")
        away = away_data.get("shortName") or away_data.get("name", "Trasferta")
        title = f"{home} - {away}"
        score = (match.get("score") or {}).get("fullTime") or {}
        matchday = match.get("matchday")
        events.append({**timestamp_clock(match["utcDate"], status not in ("SCHEDULED", "POSTPONED", "CANCELLED")),
                       "id": f"football-{match['id']}", "title": title, "sport": sport,
                       "loc": f"Giornata {matchday}" if matchday else match.get("stage", "").replace("_", " ").title(),
                       "home": home, "away": away, "homeCrest": home_data.get("crest") or "",
                       "awayCrest": away_data.get("crest") or "", "venue": match.get("venue") or "",
                       "homeScore": score.get("home") if status == "FINISHED" else None,
                       "awayScore": score.get("away") if status == "FINISHED" else None,
                       "status": status, "matchday": matchday,
                       "isTop": is_top_match(sport, title, home, away)})
    if not events:
        raise ValueError("Calendario calcio vuoto")
    return events


def fetch_football_matches(code, sport):
    return parse_football_matches(get_json(f"https://api.football-data.org/v4/competitions/{code}/matches", True), sport)


def fetch_football_standings(code):
    data = get_json(f"https://api.football-data.org/v4/competitions/{code}/standings", True)
    tables = [group for group in data["standings"] if group.get("type") == "TOTAL"]
    rows = []
    for group in tables:
        for row in group["table"]:
            team = row["team"]
            rows.append({"pos": row["position"], "name": team.get("shortName") or team["name"],
                         "crest": team.get("crest") or "", "played": row["playedGames"],
                         "won": row["won"], "draw": row["draw"], "lost": row["lost"],
                         "points": row["points"], "diff": row["goalDifference"]})
    if not rows:
        raise ValueError("Classifica calcio non disponibile")
    return rows


def parse_f1_calendar(data):
    events = []
    sessions = [("FirstPractice", "Prove libere 1"), ("SecondPractice", "Prove libere 2"),
                ("ThirdPractice", "Prove libere 3"), ("SprintQualifying", "Qualifiche Sprint"),
                ("Sprint", "Sprint"), ("Qualifying", "Qualifiche"), (None, "GARA")]
    for race in data["MRData"]["RaceTable"]["Races"]:
        circuit = race.get("Circuit") or {}
        location = circuit.get("Location") or {}
        venue = ", ".join(filter(None, [circuit.get("circuitName"), location.get("locality"), location.get("country")]))
        for field, label in sessions:
            session = race if field is None else race.get(field)
            if not session or not session.get("date"):
                continue
            events.append({**event_clock(session["date"], session.get("time")),
                           "id": f"f1-{race['season']}-{race['round']}-{field or 'Race'}",
                           "title": f"{label}: {race['raceName']}", "sport": "f1",
                           "loc": location.get("country", "Formula 1"), "venue": venue,
                           "status": "SCHEDULED", "isTop": field is None})
    if not events:
        raise ValueError("Calendario F1 vuoto")
    return events


def fetch_f1_standings(year, constructors=False):
    field = "ConstructorStandings" if constructors else "DriverStandings"
    endpoint = "constructorStandings" if constructors else "driverStandings"
    data = get_json(f"https://api.jolpi.ca/ergast/f1/{year}/{endpoint}.json?limit=100")
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        raise ValueError("Classifica F1 non disponibile")
    rows = []
    for row in lists[0][field]:
        if constructors:
            name, team = row["Constructor"]["name"], ""
        else:
            driver = row["Driver"]
            name = f"{driver['givenName']} {driver['familyName']}"
            team = ", ".join(item["name"] for item in row.get("Constructors", []))
        rows.append({"pos": row["position"], "name": name, "team": team,
                     "points": row["points"], "wins": row["wins"]})
    if not rows:
        raise ValueError("Classifica F1 vuota")
    return rows


def parse_espn_events(data, sport, season, competition_name=None):
    events = []
    for event in data["events"]:
        if event.get("season", {}).get("year") != season:
            continue
        if sport == "nfl" and event.get("season", {}).get("type") == 1:
            continue
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        home_name, away_name = home["team"]["displayName"], away["team"]["displayName"]
        status_obj = (comp.get("status") or event.get("status") or {}).get("type") or {}
        raw = status_obj.get("name", "STATUS_SCHEDULED")
        finished = status_obj.get("completed", False)
        status = ("POSTPONED" if raw == "STATUS_POSTPONED" else "CANCELLED" if raw == "STATUS_CANCELED"
                  else "FINISHED" if finished else "IN_PLAY" if status_obj.get("state") == "in" else "SCHEDULED")
        confirmed = comp.get("timeValid", False) and status not in ("POSTPONED", "CANCELLED")
        venue_obj = comp.get("venue") or {}
        venue = ", ".join(filter(None, [venue_obj.get("fullName"), (venue_obj.get("address") or {}).get("city")]))
        title = f"{home_name} - {away_name}" if sport != "nfl" else event.get("shortName", f"{away_name} @ {home_name}")
        week = event.get("week", {}).get("number", "")
        loc = competition_name or f"{'Playoff' if event.get('season', {}).get('type') == 3 else 'Week'} {week}".strip()
        events.append({**timestamp_clock(comp.get("date") or event["date"], confirmed),
                       "id": f"espn-{sport}-{event['id']}", "title": title, "sport": sport, "loc": loc,
                       "home": home_name, "away": away_name, "homeCrest": home["team"].get("logo") or "",
                       "awayCrest": away["team"].get("logo") or "", "venue": venue,
                       "homeScore": home.get("score") if finished else None,
                       "awayScore": away.get("score") if finished else None,
                       "status": status, "isTop": is_top_match(sport, title, home_name, away_name)})
    return events


def fetch_espn_calendar(league, sport, season, competition_name=None):
    # ESPN non accetta l'intervallo lungo originario. Due anni includono gennaio/febbraio.
    events = {}
    for year in (season, season + 1):
        data = get_json(f"https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard?dates={year}&limit=1000")
        for event in parse_espn_events(data, sport, season, competition_name):
            events[event["id"]] = event
    if not events:
        raise ValueError("Calendario ESPN non disponibile")
    return list(events.values())


def parse_nfl_standings(data):
    result = {"divisions": {}, "conferences": {}, "playoffs": {}}
    for conference in data["children"]:
        conf = conference["abbreviation"]
        result["conferences"][conf] = []
        for division in conference["children"]:
            entries = []
            for row in division["standings"]["entries"]:
                stats = {stat["name"]: stat for stat in row["stats"]}
                def val(name):
                    return int(stats.get(name, {}).get("value") or 0)
                team = row["team"]
                logos = team.get("logos") or [{}]
                entries.append({"name": team["displayName"], "logo": logos[0].get("href", ""),
                                "wins": val("wins"), "losses": val("losses"), "ties": val("ties"),
                                "pct": stats.get("winPercent", {}).get("displayValue", "—"),
                                "diff": val("pointDifferential"), "seed": val("playoffSeed"),
                                "div": division["name"], "conf": conf})
            entries.sort(key=lambda row: row["seed"] or 99)
            for pos, row in enumerate(entries, 1):
                row["pos"] = pos
            result["divisions"][division["name"]] = entries
            result["conferences"][conf].extend(entries)
        result["conferences"][conf].sort(key=lambda row: row["seed"] or 99)
        result["playoffs"][conf] = [row for row in result["conferences"][conf] if 1 <= row["seed"] <= 7]
    if sum(map(len, result["divisions"].values())) != 32:
        raise ValueError("Classifica NFL incompleta")
    return result


def fetch_italy():
    events = []
    data = get_json("https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id=133910")
    for event in data["events"] or []:
        home = (event.get("strHomeTeam") or "").replace("Italy", "Italia")
        away = (event.get("strAwayTeam") or "").replace("Italy", "Italia")
        events.append({**event_clock(event["dateEvent"], event.get("strTime")),
                       "id": f"italy-{event['idEvent']}", "title": f"{home} - {away}", "sport": "nazionale",
                       "loc": event.get("strLeague") or "Internazionale", "home": home, "away": away,
                       "homeCrest": event.get("strHomeTeamBadge") or "", "awayCrest": event.get("strAwayTeamBadge") or "",
                       "venue": event.get("strVenue") or "", "status": "SCHEDULED", "isTop": True})
    return events


def load_previous(path):
    if not path.exists():
        return [], {}, {}
    source = path.read_text(encoding="utf-8")
    values = []
    for name, default in (("calendarData", []), ("standingsData", {}), ("calendarMeta", {})):
        match = re.search(r"window\." + name + r"\s*=\s*", source)
        values.append(json.JSONDecoder().raw_decode(source[match.end():])[0] if match else default)
    return tuple(values)


def write_data(path, events, standings, meta):
    for event in events:
        datetime.strptime(event["date"], "%Y-%m-%d")
        if event.get("time"):
            datetime.strptime(event["time"], "%H:%M")
    events.sort(key=lambda event: (event["date"], event.get("time") or "99:99", event["title"]))
    parts = []
    for name, value in (("calendarData", events), ("standingsData", standings), ("calendarMeta", meta)):
        encoded = json.dumps(value, ensure_ascii=False, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        parts.append(f"window.{name} = {encoded};\n")
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(parts), encoding="utf-8")
    temporary.replace(path)


def update(output=OUTPUT_FILE, now=None):
    now = now or datetime.now(ROME)
    year = now.year
    football_season = year if now.month >= 7 else year - 1
    nfl_season = year if now.month >= 3 else year - 1
    old_events, old_standings, old_meta = load_previous(output)
    stamp = now.astimezone(timezone.utc).isoformat()
    meta = {"schemaVersion": 2, "generatedAt": stamp, "timezone": "Europe/Rome",
            "footballSeason": f"{football_season}/{str(football_season + 1)[2:]}", "sources": {}}
    events, standings, failures = [], {}, []

    def source(key, fetch, fallback):
        previous = old_meta.get("sources", {}).get(key, {})
        try:
            value = fetch()
            meta["sources"][key] = {"status": "ok", "updatedAt": stamp}
            print(f"OK: {key}")
            return value
        except Exception as exc:
            message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
            print(f"ERRORE: {key}: {message}", file=sys.stderr)
            failures.append(key)
            meta["sources"][key] = {"status": "error", "updatedAt": previous.get("updatedAt"), "error": message}
            return fallback

    calendars = [
        ("seriea", lambda: fetch_football_matches("SA", "seriea"), lambda event: event["sport"] == "seriea" and event.get("loc") not in ("Coppa Italia", "Supercoppa")),
        ("champions", lambda: fetch_football_matches("CL", "champions"), lambda event: event["sport"] == "champions"),
        ("nfl", lambda: fetch_espn_calendar("football/nfl", "nfl", nfl_season), lambda event: event["sport"] == "nfl"),
        ("f1", lambda: parse_f1_calendar(get_json(f"https://api.jolpi.ca/ergast/f1/{year}.json?limit=100")), lambda event: event["sport"] == "f1"),
        ("nazionale", fetch_italy, lambda event: event["sport"] == "nazionale"),
        ("coppa", lambda: fetch_espn_calendar("soccer/ita.coppa_italia", "seriea", football_season, "Coppa Italia"), lambda event: event.get("loc") == "Coppa Italia"),
        ("supercoppa", lambda: fetch_espn_calendar("soccer/ita.super_cup", "seriea", football_season, "Supercoppa"), lambda event: event.get("loc") == "Supercoppa"),
    ]
    for key, fetch, belongs in calendars:
        # I dati v1 contenevano orari e coppe inventati: non sono un fallback affidabile.
        fallback = [event for event in old_events if belongs(event)] if old_meta.get("schemaVersion") == 2 else []
        events.extend(source(key, fetch, fallback))
    tables = {
        "seriea": lambda: fetch_football_standings("SA"),
        "champions": lambda: fetch_football_standings("CL"),
        "f1_drivers": lambda: fetch_f1_standings(year),
        "f1_constructors": lambda: fetch_f1_standings(year, True),
        "nfl": lambda: parse_nfl_standings(get_json(f"https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings?season={nfl_season}&type=0&level=3")),
    }
    for key, fetch in tables.items():
        fallback = old_standings.get(key, {} if key == "nfl" else []) if old_meta.get("schemaVersion") == 2 else ({} if key == "nfl" else [])
        standings[key] = source(f"standings_{key}", fetch, fallback)
    if not events:
        raise RuntimeError("Nessun calendario disponibile: dati.js non viene sovrascritto")
    meta["partial"] = bool(failures)
    write_data(output, events, standings, meta)
    print(f"Salvati {len(events)} eventi. Fonti non aggiornate: {len(failures)}.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(update())
