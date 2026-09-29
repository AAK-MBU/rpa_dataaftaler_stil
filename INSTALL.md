# Installation og kørsel (uden Python-kendskab)

Appen kører på Python, men slutbrugeren skal ikke kende til Python. En teknisk
person opsætter maskinen én gang; derefter starter medarbejderen blot programmet
med et dobbeltklik.

## Forudsætninger

- Windows.
- Google Chrome installeret.
- Internetadgang (første kørsel henter værktøjer og `chromedriver`).

`uv` (Python-værktøjet) installeres automatisk af launcheren første gang – det
skal ikke installeres manuelt.

## Opsætning (engang pr. maskine)

1. Pak projektmappen ud et fast sted, fx `C:\Programmer\Dataaftaler\`.
2. Kopiér `.env.example` til `.env` i samme mappe, og udfyld værdierne
   (`ATS_URL`, `ATS_TOKEN`, `ATS_WORKQUEUE_OVERRIDE`, og evt. `BASE_DIR`).
3. Dobbeltklik **`start-dataaftaler.bat`**. Første gang installeres `uv` og alle
   afhængigheder (det tager lidt tid og viser status i et konsolvindue).
   Bagefter åbner programvinduet.

Senere kørsler er hurtige, og konsolvinduet lukker af sig selv, så snart vinduet
er åbnet.

## Daglig brug

Dobbeltklik **`start-dataaftaler.bat`**.

### Arbejdsgang i programmet

1. **Dan overblik (Excel)** – programmet gemmer overbliks-arket i mappen
   `Output` (under `BASE_DIR`, ellers ved siden af programmet). Den fulde sti
   vises i historikken (*"Overblik gemt: …"*).
2. Åbn arket (knappen **Åbn regneark** eller direkte i `Output`-mappen), vælg
   `GODKEND` / `SLET` / `VENT` i kolonnen `statusændring`, og **gem filen samme
   sted** (overskriv – lad være med at omdøbe eller flytte den, og slet ikke
   kolonner).
3. **Indlæs ændringer & kør** – programmet læser det reviderede ark fra netop
   `Output`-mappen (stien vises også i historikken) og gennemfører ændringerne.

> Der må kun ligge **ét** Oversigt-ark i `Output`-mappen ad gangen. Slet gamle
> ark, ellers ved programmet ikke hvilket der skal bruges.

## Genvej på skrivebordet / Start-menu (anbefales)

Så medarbejderen kan starte programmet som enhver anden app:

**Nem måde:**
1. Højreklik `start-dataaftaler.bat` → **Send til** → **Skrivebord (opret genvej)**.
2. (Valgfrit) Højreklik genvejen → **Egenskaber** → **Skift ikon** og vælg et ikon.

**Helt uden konsolvindue:**
1. Højreklik på skrivebordet → **Ny** → **Genvej**.
2. Placering:
   `C:\Programmer\Dataaftaler\.venv\Scripts\pythonw.exe -m gui.app`
   (tilpas stien til hvor projektet ligger).
3. Åbn genvejens **Egenskaber** og sæt **Start i** til projektmappen
   (`C:\Programmer\Dataaftaler\`).
4. (Valgfrit) **Skift ikon** → vælg dit ikon.

> Denne genvej kræver, at `start-dataaftaler.bat` (eller `uv sync`) er kørt mindst
> én gang, så `.venv`-mappen findes.

### Ikon

Læg en `app.ico` i projektmappen og peg genvejens **Skift ikon** på den.
(Windows kan ikke bruge `.png` som genvejsikon – det skal være `.ico`.)

## Alternativ: kør fra kommandolinjen

Efter `uv sync` kan programmet også startes med:

```sh
uv run dataaftaler
```

## Sikkerhed: `.env`

`.env` indeholder `ATS_TOKEN` (en hemmelighed). Send den **ikke** på mail – distribuér
den via et beskyttet drev eller en administreret kanal, eller udfyld den lokalt på
maskinen. `BASE_DIR` styrer hvor `Output/` (overblik + logs) lægges; peg den evt.
mod en synkroniseret/delt mappe.
