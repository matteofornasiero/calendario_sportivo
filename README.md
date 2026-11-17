# Sport OS – Calendario Sportivo

Calendario sportivo statico pubblicato tramite GitHub Pages. **Non richiede compilazioni periodiche manuali:** il workflow GitHub Actions aggiorna `dati.js` e pubblica il sito automaticamente.

## Aggiornamento automatico

- [Aggiorna e pubblica Sport OS](.github/workflows/aggiorna_dati.yml): avvio ogni **2 ore** (minuto 23 UTC), oltre che su push su `main` e avvio manuale. I risultati non sono in diretta: i fornitori gratuiti possono pubblicarli in ritardo.
- Il programma `aggiorna_calendario.py` raccoglie eventi e classifiche, conserva l'ultima copia valida se una singola fonte fallisce, e salva data ed esito per ciascuna fonte.
- I calendari F1 includono automaticamente l'anno successivo quando disponibile e quello precedente nei primi mesi dell'anno. Durante le pause F1 e NFL le classifiche dell'ultima stagione conclusa rimangono consultabili con l'indicazione della stagione nei metadati.
- Prima di sostituire un calendario fondamentale vengono controllati numero minimo di eventi e presenza di incontri futuri durante la stagione attiva. Un feed vuoto o incompleto non deve cancellare i dati buoni.
- Il file `dati.js` viene committato anche quando cambia soltanto il timestamp del controllo: questo consente di sapere quando il sistema ha effettivamente verificato le fonti. Le modifiche a `main` vengono pubblicate automaticamente dal workflow.

## Controllo guasti e autoripristino

- [Controllo automatico salute](.github/workflows/salute.yml): una volta al giorno verifica che il dataset sia stato rigenerato entro **16 ore**, che le 12 fonti previste siano presenti e che non ci siano guasti persistenti (**oltre 48 ore**). Le indisponibilità temporanee non causano un incidente.
- Se un controllo fallisce, apre o aggiorna una **issue GitHub** dedicata; al ripristino la chiude. Per ricevere avvisi, attivare le notifiche di GitHub per le issue del repository.
- Se una fonte fallisce, il sito resta accessibile e conserva i dati validi precedenti; l'interfaccia visualizza la data dell'ultimo aggiornamento e lo stato delle fonti.

## Cosa puo' ancora richiedere un intervento

Il sistema non puo' correggere automaticamente la revoca di `FOOTBALL_DATA_API_KEY`, la chiusura di un servizio API, una modifica incompatibile al suo formato, o lo spegnimento delle GitHub Actions da parte di GitHub. I workflow programmati in repository pubblici possono essere disattivati da GitHub dopo 60 giorni senza attivita' nel repository; gli aggiornamenti periodici del dataset creano normalmente attivita', ma non sono una garanzia assoluta. Consultare [GitHub Actions](https://github.com/matteofornasiero/calendario_sportivo/actions) e le issue in caso di avviso.

## Verifiche locali

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node tests/test_app.cjs
python verifica_dati.py
python monitor_salute.py
```

La chiave personale `FOOTBALL_DATA_API_KEY` deve restare nei Secrets di GitHub Actions, mai nel repository.
