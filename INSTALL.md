# Installation og kørsel (uden Python-kendskab)

Appen kører på Python, men slutbrugeren skal ikke kende til Python. En teknisk
person opsætter maskinen én gang; derefter starter medarbejderen blot programmet
med et dobbeltklik.

## Forudsætninger

- Windows.
- Google Chrome installeret.
- Git installeret (bruges til at hente en af programmets afhængigheder).
- Internetadgang (første kørsel henter værktøjer og `chromedriver`).

`uv` (Python-værktøjet) installeres automatisk af launcheren første gang – det
skal ikke installeres manuelt.

## Opsætning (en gang pr. maskine)

1. Hent `Dataaftaler-v<version>.zip` fra den
   [seneste release](https://github.com/AAK-MBU/rpa_dataaftaler_stil/releases/latest).
2. Pak zip-filen ud et sted, hvor brugeren selv kan skrive, fx
   `C:\Users\<bruger>\Dataaftaler\` (ikke under `C:\Program Files`). Mappen ser
   sådan ud:

   ```
   Dataaftaler\
   ├─ Start Dataaftaler.bat   ← start programmet her
   ├─ LÆS MIG.txt
   └─ app\                   ← selve programmet, .venv og .env
   ```
3. Dobbeltklik **`Start Dataaftaler.bat`**. Første gang installeres `uv` og alle
   afhængigheder (det tager lidt tid og viser status i et konsolvindue).
4. Programmet åbner en opsætningsdialog:
   1. Vælg **ATS** (ændringer køres via arbejdskø i Automation Server) eller
      **Lokalt** (ændringer køres direkte uden arbejdskø).
   2. Ved ATS: indtast URL, token og workqueue-ID.
   3. Skriv IdP-organisationen, der vælges ved login i STIL, præcis som den står
      i listen på loginsiden (fx `Aarhus Kommune, 55133018, Aarhus Kommune`).
   4. Vælg mappen til output (standard: den yderste `Dataaftaler`-mappe).
      Overblik og logs gemmes i undermappen `Output`.
   5. Vælg om der skal oprettes en genvej, og hvor (standard: skrivebordet).
      Genvejen får programmets ikon (`app.ico`).
5. Tryk **Gem**. Hovedvinduet åbner.

Opsætningen gemmes i `app\.env` og kan ændres senere med knappen
**Opsætning** i programmet.

Når opsætningen er gemt, og afhængighederne er installeret, åbner senere starter
programvinduet direkte uden konsolvinduet med trinnene. Er programmet opdateret
(ændret `uv.lock` eller `pyproject.toml`), vises konsolvinduet igen, mens
afhængighederne opdateres.

## Opdatering

Når programmet starter, tjekker det, om der er en nyere version på GitHub. Er
der det, spørger programmet, om det skal opdatere. Ved **Ja** hentes den nye
version, programfilerne i `app` udskiftes, og programmet genstarter. Opsætningen
(`.env`), `.venv` og `Output` bevares. Har den nye version ændrede afhængigheder,
vises konsolvinduet med trinnene, mens de installeres.

Går opdateringen galt, lægges de gamle filer tilbage, og den nuværende version
bruges fortsat. Tjekket kan slås fra med `DATAAFTALER_NO_UPDATE=true` i `.env`.

## Daglig brug

Dobbeltklik **`Start Dataaftaler.bat`** (eller genvejen).

### Arbejdsgang i programmet

1. **Dan overblik (Excel)** – programmet gemmer overbliks-arket i mappen
   `Output` i den mappe, der er valgt under Opsætning. Den fulde sti
   vises i historikken (*"Overblik gemt: …"*).
2. Åbn arket (knappen **Åbn regneark** eller direkte i `Output`-mappen), vælg
   `GODKEND` / `VENT` / `AFVIS` / `SLET` i kolonnen `statusændring`, skriv evt.
   en kommentar i kolonnen `kommentar` lige til højre (bruges ikke ved `SLET`),
   og **gem filen samme
   sted** (overskriv – lad være med at omdøbe eller flytte den, og slet ikke
   kolonner).
3. **Indlæs ændringer & kør** – programmet læser det reviderede ark fra netop
   `Output`-mappen (stien vises også i historikken) og gennemfører ændringerne.
   Ligger der flere ark i mappen, vælger du arket i en dialog.

> Ligger der flere Oversigt-ark i `Output`-mappen, spørger programmet, hvilket
> der skal bruges. Arkene vises med det senest ændrede øverst, markeret
> **★ Senest ændret**.

## Genvej

Opsætningsdialogen kan oprette genvejen automatisk. Vil du lave den manuelt:

1. Højreklik `Start Dataaftaler.bat` → **Send til** → **Skrivebord (opret genvej)**.
2. (Valgfrit) Højreklik genvejen → **Egenskaber** → **Skift ikon** og vælg
   `app.ico` i mappen `app`.

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
