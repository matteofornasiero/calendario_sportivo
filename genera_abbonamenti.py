"""Pubblica abbonamenti iCalendar stabili usando solo i dati già raccolti da Sport OS.

Ogni calendario ha un URL statico GitHub Pages. Le date degli eventi con orario
sconosciuto vengono pubblicate come provvisorie (giornata intera) e si aggiornano
quando la fonte conferma l'orario. Nessun servizio esterno o chiave API aggiuntiva.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aggiorna_calendario import OUTPUT_FILE, ROOT, load_previous

OUTPUT_DIR = ROOT / "calendari"
COMPETITIONS = {
    "seriea": "Serie A",
    "champions": "Champions League",
    "nfl": "NFL",
    "f1": "Formula 1",
    "nazionale": "Nazionale italiana",
    "coppa": "Coppa Italia",
    "supercoppa": "Supercoppa italiana",
}
PLACEHOLDERS = {"", "tbd", "to be decided", "to be determined", "unknown", "home", "away", "da definire"}


def slug(value):
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_text = normalized.encode("ascii", errors="ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def competition(event):
    if event.get("sport") == "seriea":
        if event.get("loc") == "Coppa Italia":
            return "coppa"
        if event.get("loc") == "Supercoppa":
            return "supercoppa"
    return event.get("sport", "")


def calendar_teams(event):
    if event.get("sport") == "f1":
        return []
    return list({name.strip() for name in (event.get("home") or "", event.get("away") or "")
                 if name.strip() and name.strip().lower() not in PLACEHOLDERS})


def escape_ical(value):
    return (str(value).replace("\\", "\\\\").replace("\n", "\\n")
            .replace(",", "\\,").replace(";", "\\;"))


def fold_line(value):
    # RFC 5545: una riga fisica non deve eccedere 75 ottetti UTF-8.
    result, current, size = [], "", 0
    for char in value:
        char_size = len(char.encode("utf-8"))
        if current and size + char_size > 75:
            result.append(current)
            current, size = " ", 1  # il carattere di continuazione conta
        current += char
        size += char_size
    result.append(current)
    return "\r\n".join(result)


def moment(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stamp_utc(value):
    return value.strftime("%Y%m%dT%H%M%SZ")


def duration(event):
    if event.get("sport") == "nfl":
        return 210
    if event.get("sport") != "f1":
        return 120
    title = event.get("title", "").lower()
    if "prove libere" in title:
        return 90
    if "qualifiche" in title:
        return 75
    if "sprint" in title:
        return 60
    return 150


def uid(event):
    # Dipende solo dall'ID sorgente, non da data/orario (che possono cambiare).
    signature = hashlib.sha256(str(event["id"]).encode("utf-8")).hexdigest()[:24]
    return signature + "@sport-os.github.io"


def previous_events(text):
    """Per eventi invariati preserva DTSTAMP/SEQUENCE e non riscrive ogni due ore."""
    found = {}
    if not text:
        return found
    raw_lines = text.replace("\r\n", "\n").split("\n")
    lines = []
    for line in raw_lines:
        if (line.startswith(" ") or line.startswith("\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    block = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            block = {}
        elif line == "END:VEVENT":
            if block and block.get("UID"):
                found[block["UID"]] = block
            block = None
        elif block is not None and ":" in line:
            key, value = line.split(":", 1)
            if key in {"UID", "DTSTAMP", "LAST-MODIFIED", "SEQUENCE", "X-SPORT-OS-SIGNATURE"}:
                block[key] = value
    return found


def event_lines(event, previous, updated_at):
    identifier = uid(event)
    confirmed = bool(event.get("timeConfirmed") and event.get("startUtc"))
    if confirmed:
        start = moment(event["startUtc"])
        timing = [f"DTSTART:{stamp_utc(start)}",
                  f"DTEND:{stamp_utc(start + timedelta(minutes=duration(event)))}"]
    else:
        start = date.fromisoformat(event["date"])
        timing = [f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}"]

    title = event.get("title") or f"{event.get('home', '')} - {event.get('away', '')}"
    if not confirmed:
        title += " (orario da confermare)"
    state = event.get("status", "")
    if state == "CANCELLED":
        state_ical = "CANCELLED"
    elif state in ("POSTPONED", "SUSPENDED"):
        state_ical = "TENTATIVE"
    else:
        state_ical = "CONFIRMED"

    info = [COMPETITIONS.get(competition(event), "Sport"),
            event.get("loc") or ""]
    if not confirmed:
        info.append("Data/orario provvisori: verificare prima dell'evento.")
    if state in ("POSTPONED", "CANCELLED", "SUSPENDED"):
        info.append("Stato: " + state)
    if event.get("status") == "FINISHED" and event.get("homeScore") is not None and event.get("awayScore") is not None:
        info.append(f"Risultato: {event['homeScore']} - {event['awayScore']}")
    fields = [
        "UID:" + identifier,
        *timing,
        "SUMMARY:" + escape_ical(title),
        "DESCRIPTION:" + escape_ical(" · ".join(filter(None, info))),
        "LOCATION:" + escape_ical(event.get("venue") or ""),
        "STATUS:" + state_ical,
        "TRANSP:TRANSPARENT",
    ]
    signature = hashlib.sha256("\n".join(fields).encode("utf-8")).hexdigest()[:24]
    old = previous.get(identifier, {})
    if old.get("X-SPORT-OS-SIGNATURE") == signature and old.get("DTSTAMP"):
        created = old["DTSTAMP"]
        modified = old.get("LAST-MODIFIED", created)
        version = old.get("SEQUENCE", "0")
    else:
        created = old.get("DTSTAMP") or updated_at
        modified = updated_at
        version = str(int(old.get("SEQUENCE", "0")) + 1 if old else 0)
    return ["BEGIN:VEVENT",
            f"DTSTAMP:{created}", f"LAST-MODIFIED:{modified}", f"SEQUENCE:{version}",
            f"X-SPORT-OS-SIGNATURE:{signature}", *fields, "END:VEVENT"]


def serialize(name, events, old_text="", timestamp=None):
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    updated = stamp_utc(timestamp.astimezone(timezone.utc))
    previous = previous_events(old_text)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Sport OS//Calendario sportivo//IT", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", "X-WR-CALNAME:" + escape_ical("Sport OS · " + name),
        "X-WR-TIMEZONE:Europe/Rome", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
    ]
    for event in sorted(events, key=lambda e: (e["date"], e.get("time") or "", str(e["id"]))):
        lines.extend(event_lines(event, previous, updated))
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_line(line) for line in lines) + "\r\n"


def write_if_changed(path, content):
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)
    return True


def generate(data_path=OUTPUT_FILE, output_dir=OUTPUT_DIR, timestamp=None):
    events, _, _ = load_previous(data_path)
    if not events:
        raise ValueError("Impossibile creare abbonamenti: dati.js vuoto")
    output_dir = Path(output_dir)
    team_events = defaultdict(list)
    team_labels = {}
    league_events = defaultdict(list)
    for event in events:
        key = competition(event)
        if key in COMPETITIONS:
            league_events[key].append(event)
        for name in calendar_teams(event):
            code = slug(name)
            if not code:
                continue
            # Eventuali nomi omografi sono trattati come un'unica selezione.
            team_labels.setdefault(code, name)
            team_events[code].append(event)
    listing = {"schemaVersion": 1, "teams": [], "competitions": []}
    updated = 0
    for code in sorted(league_events):
        name = COMPETITIONS[code]
        relative = f"competizione/{code}.ics"
        path = output_dir / relative
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        ical = serialize(name, league_events[code], old, timestamp).encode("utf-8")
        updated += write_if_changed(path, ical)
        listing["competitions"].append({"name": name, "path": f"calendari/{relative}", "count": len(league_events[code])})
    for code in sorted(team_events):
        name = team_labels[code]
        relative = f"squadra/{code}.ics"
        path = output_dir / relative
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        ical = serialize(name, team_events[code], old, timestamp).encode("utf-8")
        updated += write_if_changed(path, ical)
        listing["teams"].append({"name": name, "path": f"calendari/{relative}", "count": len(team_events[code])})
    listing["teams"].sort(key=lambda row: row["name"].casefold())
    listing["competitions"].sort(key=lambda row: row["name"].casefold())
    catalog = (json.dumps(listing, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    updated += write_if_changed(output_dir / "catalogo.json", catalog)
    print(f"Abbonamenti: {len(listing['teams'])} squadre, {len(listing['competitions'])} competizioni, {updated} file cambiati.")
    return listing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera calendari iCalendar pubblici da dati.js")
    parser.add_argument("--data", type=Path, default=OUTPUT_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    generate(args.data, args.output_dir)
