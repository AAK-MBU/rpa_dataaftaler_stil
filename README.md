# Dataaftaler – STIL (desktop)

RPA-løsning til at danne overblik over og opdatere dataaftaler i STIL
([tilslutning.stil.dk](https://tilslutning.stil.dk)). Bygget på
[ATS-frameworket](https://github.com/AAK-MBU/ATS_Process_Framework) men startes
fra en **desktop** med et **Tkinter-feedbackvindue** i stedet for fra Automation
Server. Ændringerne køres enten via en arbejdskø i Automation Server (driftsform
**ATS**) eller direkte fra computeren uden kø (driftsform **Lokalt**).

Robotten er *attended*: den åbner en browser, hvor medarbejderen selv logger ind
i STIL via den lokale IdP, der er valgt under opsætningen, hvorefter resten kører automatisk.

## Funktioner

Vinduet har to handlinger og lever op til fire feedback-krav:

1. **Dann overblik (Excel)** – logger ind i STIL, henter alle dataaftaler for alle
   institutioner og skriver `Output/dataaftaler_oversigt_<dato>.xlsx` med en
   `statusændring`-kolonne (dropdown: `GODKEND` / `VENT` / `AFVIS` / `SLET`) og
   en `kommentar`-kolonne lige til højre for den. Medarbejderen redigerer arket
   manuelt og vælger, hvad der skal ændres.
2. **Indlæs ændringer & kør** – læser det reviderede Excel-ark (ligger der flere
   i `Output`, vælges arket i en dialog med det senest ændrede øverst), logger ind i STIL
   igen og gennemfører hver ændring, og viser til sidst et resultat. Godkend,
   venter og afvis sendes som statusændring (PUT) med kommentaren fra arket (tom
   hvis cellen er tom); slet sletter aftalen (DELETE), og kommentaren bruges ikke. Ved ATS lægges ændringerne først i Automation
   Server-køen og behandles derfra; ved Lokalt køres de direkte.

Knappen **Opsætning** åbner opsætningsdialogen (se nedenfor).

Feedback i vinduet: **(1)** fremdriftslinje + fase, **(2)** historik der løbende
viser hvad der er sket (gemmes også i `Output/logs/`), **(3)** Pause/Fortsæt og
Stop, **(4)** en afsluttende opsummering (fx *"X aftaler godkendt, Y slettet,
Z sat til venter, …"*). Vinduet lukkes manuelt.

## Opsætning

Kræver Python 3.13, Google Chrome, og [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
```

Første gang programmet startes (eller når `RUN_MODE` mangler i `.env`), vises en
opsætningsdialog før hovedvinduet. Den går igennem:

1. **Driftsform** – ATS eller Lokalt.
2. **Automation Server** – URL, token og workqueue-ID (kun ved ATS).
3. **Login** – IdP-organisationen der vælges på STIL's loginside, skrevet præcis
   som i listen dér (fx `Aarhus Kommune, 55133018, Aarhus Kommune`).
4. **Mappe til output** – gemmes som `BASE_DIR`; overblik og logs lægges i
   `<mappe>/Output`.
5. **Genvej (valgfrit, kun Windows)** – opretter `Dataaftaler - STIL.lnk` til
   `start-dataaftaler.bat` i den valgte mappe (standard: skrivebordet) med
   `app.ico` som ikon.

Værdierne skrives til `.env` i projektmappen; øvrige nøgler i filen bevares.
`.env` kan også udfyldes manuelt ud fra `.env.example`.

Relevante `.env`-værdier:

| Variabel | Beskrivelse |
|---|---|
| `RUN_MODE` | `ATS` (arbejdskø i Automation Server) eller `LOKAL` (ingen kø). |
| `ATS_TOKEN` / `ATS_URL` | Adgang til Automation Server-API'et (arbejdskøen). Kun ved `ATS`. |
| `ATS_WORKQUEUE_OVERRIDE` | ID på den arbejdskø der skal bruges. Kun ved `ATS`. |
| `LOCAL_DEVELOPMENT` | `true` ved desktop-/lokal kørsel. |
| `LOGIN_ORGANISATION` | Lokal IdP-organisation på STIL's loginside (standard: `Aarhus Kommune, 55133018, Aarhus Kommune`). |
| `BASE_DIR` | Mappe til input/output (default: repo-roden). Filer lægges i `BASE_DIR/Output`. |
| `SEND_ERROR_EMAILS` | `false` på desktop (fejl vises i historikken/loggen). |

## Kørsel

**Slutbruger (uden Python-kendskab):** hent zip-filen fra seneste release og dobbeltklik `Start Dataaftaler.bat`. Første
kørsel installerer `uv` og afhængigheder automatisk; derefter åbner vinduet uden
konsol. Se [`INSTALL.md`](INSTALL.md) for opsætning og hvordan man laver en genvej
på skrivebordet.

**Desktop-app (udvikling):**

```sh
uv run python -m gui.app    # eller, efter `uv sync`:  uv run dataaftaler
```

**Headless (samme faser, uden GUI – fx fra Automation Server):**

```sh
uv run python main.py --overview     # dan overblik (Excel)
uv run python main.py --queue        # læs Excel og fyld arbejdskøen
uv run python main.py --process      # gennemfør ændringerne i STIL
uv run python main.py --finalize     # opsummér resultatet
uv run python main.py --local        # læs Excel og gennemfør ændringerne uden kø
```

## Udgivelse

En ny version udgives som en zip-fil på GitHub Releases:

1. Hæv `version` i `pyproject.toml` (fx `2.1.0`) og merge til `main`.
2. Opret og push et tag med samme version: `git tag v2.1.0 && git push origin v2.1.0`.
3. `.github/workflows/release.yml` bygger `Dataaftaler-v2.1.0.zip` og lægger den på
   en release. Workflowet fejler, hvis tagget ikke matcher versionen.

Zip-filen indeholder `Start Dataaftaler.bat` og `LÆS MIG.txt` (fra `packaging/`)
i yderste mappe og koden i `app/` (et `git archive` af repoet; stier markeret
`export-ignore` i `.gitattributes` er udeladt). Når programmet kører fra en sådan
pakke, er standardmappen til output den yderste mappe (`config.INSTALL_DIR`);
`.env` og `.venv` ligger i `app/`.

## Arkitektur

| Fil | Ansvar |
|---|---|
| `gui/app.py` | Tkinter-vindue, arbejdstråd, fremdrift/historik/pause/stop. |
| `gui/setup_wizard.py` | Opsætningsdialog (driftsform, ATS, output-mappe, genvej). |
| `gui/overview_picker.py` | Dialog til at vælge overbliks-ark, når der er flere i `Output`. |
| `main.py` | Faser (`populate_queue` / `process_workqueue` / `finalize`), `run_local` + `--overview`. Headless-indgang. |
| `helpers/settings.py` | Læs/skriv opsætningen i `.env` og opret genvej. |
| `helpers/stil_api.py` | STIL login (Selenium) + REST-kald (requests). |
| `helpers/reporting.py` | `ProgressReporter` (Null/Gui) + `StopRequested` – fælles fremdrift/afbrydelse. |
| `helpers/config.py` | Konfiguration: endpoints, timeouts, status-mapping, stier. |
| `processes/application_handler.py` | `startup()`/`close()` – login og delt auth-kontekst (`AppContext`). |
| `processes/process_item.py` | Behandl ét kø-element (skift status / slet / spring over). |
| `processes/queue_handler.py` | Læs Excel → kø-elementer; samtidig upload til kø. |
| `processes/overview.py` | Dan overbliks-Excel med dropdown. |
| `processes/finalize_process.py` | Optæl resultat → opsummering. |

De samme faser bruges både af GUI'et (med `GuiReporter` på en arbejdstråd) og
headless (`NullReporter`).
