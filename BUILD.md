# Byg en Windows `.exe`

Appen pakkes til en enkelt `.exe` med [PyInstaller](https://pyinstaller.org/).

> **Vigtigt:** PyInstaller kan ikke krydskompilere. En Windows-`.exe` skal bygges
> **på en Windows-maskine** med samme Python-version (3.13).

## Forudsætninger

- Windows med Python 3.13 og [`uv`](https://docs.astral.sh/uv/).
- Projektet hentet/udpakket, og afhængigheder installeret:

  ```sh
  uv sync
  ```

## Byg

Fra projektmappen:

```sh
uv run --with pyinstaller pyinstaller dataaftaler.spec
```

(`--with pyinstaller` henter PyInstaller midlertidigt, så det ikke skal tilføjes
som projektafhængighed.)

Resultatet ligger i:

```
dist\Dataaftaler-STIL.exe
```

## Kør den byggede app

1. Læg en `.env` **i samme mappe som `.exe`'en** (kopiér `.env.example` og udfyld
   `ATS_URL`, `ATS_TOKEN`, `ATS_WORKQUEUE_OVERRIDE`, evt. `BASE_DIR`). Appen læser
   `.env` fra den mappe, den startes i.
2. Google Chrome skal være installeret. Selenium henter selv den matchende
   `chromedriver` første gang (kræver internetadgang).
3. Dobbeltklik `Dataaftaler-STIL.exe` (eller kør den fra en mappe der indeholder
   `.env`).

Output (overbliks-Excel og `logs/`) lægges under `BASE_DIR\Output` hvis `BASE_DIR`
er sat – ellers ved siden af `.exe`'en.

## Noter / fejlfinding

- **Konsolvindue:** Specfilen bygger med `console=True`, så fejl ved opstart er
  synlige i et terminalvindue. Når du er sikker på at den starter, kan du sætte
  `console=False` i `dataaftaler.spec` og bygge igen for en ren GUI uden terminal.
- **Langsom første opstart:** Én-fils-`.exe`'en pakker sig selv ud i en temp-mappe
  ved hver start. Vil du have hurtigere opstart, kan specfilen ændres til en
  mappe-build (`COLLECT`) i stedet for én fil.
- **Antivirus:** En selvudpakkende PyInstaller-`.exe` kan udløse en falsk positiv.
  Byg fra en kendt/ren kilde, og overvej at signere `.exe`'en til udrulning.
- **Slankere build:** Fejl-e-mails er slået fra som standard på desktop, så
  `mbu_dev_shared_components` (og `pyodbc`) er reelt ikke nødvendig. Hvis buildet
  fejler på den pakke, kan du fjerne den fra listen i `dataaftaler.spec` og lægge
  den i `excludes` i stedet.
