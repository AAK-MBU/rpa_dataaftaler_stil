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

## Opsætning (en gang pr. maskine)

1. Pak projektmappen ud et fast sted, fx `C:\Programmer\Dataaftaler\`.
2. Dobbeltklik **`start-dataaftaler.bat`**. Første gang installeres `uv` og alle
   afhængigheder (det tager lidt tid og viser status i et konsolvindue).
3. Programmet åbner en opsætningsdialog:
   1. Vælg **ATS** (ændringer køres via arbejdskø i Automation Server) eller
      **Lokalt** (ændringer køres direkte uden arbejdskø).
   2. Ved ATS: indtast URL, token og workqueue-ID.
   3. Vælg mappen til output. Overblik og logs gemmes i undermappen `Output`.
   4. Vælg om der skal oprettes en genvej, og hvor (standard: skrivebordet).
      Genvejen får programmets ikon (`app.ico`).
4. Tryk **Gem**. Hovedvinduet åbner.

Opsætningen gemmes i `.env` i projektmappen og kan ændres senere med knappen
**Opsætning** i programmet.

Senere kørsler er hurtige, og konsolvinduet lukker af sig selv, så snart vinduet
er åbnet.

## Daglig brug

Dobbeltklik **`start-dataaftaler.bat`**.

### Arbejdsgang i programmet

1. **Dan overblik (Excel)** – programmet gemmer overbliks-arket i mappen
   `Output` i den mappe, der er valgt under Opsætning. Den fulde sti
   vises i historikken (*"Overblik gemt: …"*).
2. Åbn arket (knappen **Åbn regneark** eller direkte i `Output`-mappen), vælg
   `GODKEND` / `SLET` / `VENT` i kolonnen `statusændring`, og **gem filen samme
   sted** (overskriv – lad være med at omdøbe eller flytte den, og slet ikke
   kolonner).
3. **Indlæs ændringer & kør** – programmet læser det reviderede ark fra netop
   `Output`-mappen (stien vises også i historikken) og gennemfører ændringerne.

> Der må kun ligge **ét** Oversigt-ark i `Output`-mappen ad gangen. Slet gamle
> ark, ellers ved programmet ikke hvilket der skal bruges.

## Genvej

Opsætningsdialogen kan oprette genvejen automatisk. Vil du lave den manuelt:

1. Højreklik `start-dataaftaler.bat` → **Send til** → **Skrivebord (opret genvej)**.
2. (Valgfrit) Højreklik genvejen → **Egenskaber** → **Skift ikon** og vælg
   `app.ico` i projektmappen.

## Alternativ: kør fra kommandolinjen

Efter `uv sync` kan programmet også startes med:

```sh
uv run dataaftaler
```

## Sikkerhed: `.env`

`.env` indeholder `ATS_TOKEN` (en hemmelighed), når driftsformen er ATS. Send den
**ikke** på mail – udfyld den lokalt på maskinen via opsætningsdialogen.
`BASE_DIR` styrer hvor `Output/` (overblik + logs) lægges; peg den evt.
mod en synkroniseret/delt mappe.
