"""Verifica la copia da pubblicare senza accedere alla rete."""
from datetime import datetime
from aggiorna_calendario import OUTPUT_FILE, load_previous


def verify(path=OUTPUT_FILE):
    events, standings, meta = load_previous(path)
    assert events, "Calendario vuoto"
    assert meta.get("schemaVersion") == 2, "Dati privi di informazioni sull'aggiornamento"
    datetime.fromisoformat(meta["generatedAt"])
    ids = [event["id"] for event in events]
    assert len(ids) == len(set(ids)), "Eventi duplicati"
    for event in events:
        datetime.strptime(event["date"], "%Y-%m-%d")
        if event["timeConfirmed"]:
            datetime.strptime(event["time"], "%H:%M")
            assert event["startUtc"], "Manca l'orario UTC"
        else:
            assert not event["time"] and not event["startUtc"], "Orario fittizio"
    assert set(standings) == {"seriea", "champions", "nfl", "f1_drivers", "f1_constructors"}
    print(f"Dati validi: {len(events)} eventi, {len(meta['sources'])} fonti.")


if __name__ == "__main__":
    verify()
