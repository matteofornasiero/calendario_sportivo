"""Controllo quotidiano della salute delle fonti senza richiedere servizi esterni."""
import sys
from datetime import datetime, timedelta, timezone

from aggiorna_calendario import OUTPUT_FILE, load_previous

MAX_DATA_AGE = timedelta(hours=16)
MAX_SOURCE_ERROR_AGE = timedelta(hours=48)
EXPECTED_SOURCES = {
    "seriea", "champions", "nfl", "f1", "nazionale", "coppa", "supercoppa",
    "standings_seriea", "standings_champions", "standings_f1_drivers",
    "standings_f1_constructors", "standings_nfl",
}


def parse_time(value):
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def diagnose(meta, now=None):
    """Nessun allarme per errori transitori: una singola fonte ha 48 ore per riprendersi."""
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    problems = []
    generated = parse_time(meta.get("generatedAt"))
    if generated is None:
        problems.append("Data dell'ultimo aggiornamento assente o non valida.")
    elif generated > now + timedelta(minutes=10) or now - generated > MAX_DATA_AGE:
        problems.append(f"Dati non rigenerati da oltre 16 ore (ultimo: {generated.isoformat()}).")

    sources = meta.get("sources") or {}
    missing = EXPECTED_SOURCES.difference(sources)
    if missing:
        problems.append("Fonti assenti: " + ", ".join(sorted(missing)))

    for name in sorted(EXPECTED_SOURCES.intersection(sources)):
        item = sources[name]
        if item.get("status") == "ok":
            continue
        last_good = parse_time(item.get("updatedAt"))
        # Coppe estive: non e' detto che il nuovo calendario sia gia' pubblicato.
        if name in {"coppa", "supercoppa"} and now.month in {6, 7, 8}:
            continue
        if last_good is None or now - last_good > MAX_SOURCE_ERROR_AGE:
            problems.append(f"{name}: fonte non recuperata da oltre 48 ore ({item.get('error', 'errore sconosciuto')}).")
    return problems


def main():
    events, standings, meta = load_previous(OUTPUT_FILE)
    problems = diagnose(meta)
    if not events or not standings:
        problems.append("Calendario o classifiche assenti.")
    if problems:
        print("SPORT OS: NECESSARIO CONTROLLO AUTOMATICO\n" + "\n".join("- " + p for p in problems))
        return 1
    print(f"SPORT OS: OK - {len(events)} eventi, {len(meta['sources'])} fonti, ultima verifica {meta['generatedAt']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
