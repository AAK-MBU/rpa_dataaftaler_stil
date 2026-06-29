# Dataaftaler – STIL (desktop)

RPA-løsning til at danne overblik over og opdatere dataaftaler i STIL
([tilslutning.stil.dk](https://tilslutning.stil.dk)). Bygget på
[ATS-frameworket](https://github.com/AAK-MBU/ATS_Process_Framework) men startes
fra en **desktop** med et **Tkinter-feedbackvindue** i stedet for fra Automation
Server. Selve arbejdskøen ligger fortsat i Automation Server (over netværket).

Robotten er *attended*: den åbner en browser, hvor medarbejderen selv logger ind
i STIL (Aarhus Kommune Lokal IdP), hvorefter resten kører automatisk.

## Funktioner

Vinduet har to handlinger og lever op til fire feedback-krav:

1. **Dann overblik (Excel)** – logger ind i STIL, henter alle dataaftaler for alle
   institutioner og skriver `Output/dataaftaler_oversigt_<dato>.xlsx` med en
   `statusændring`-kolonne (dropdown: `GODKEND` / `SLET` / `VENT`). Medarbejderen
   redigerer arket manuelt og vælger, hvad der skal ændres.
2. **Indlæs ændringer & kør** – læser det reviderede Excel-ark, lægger de ønskede
   ændringer i Automation Server-køen, logger ind i STIL igen og gennemfører hver
   ændring (godkend / sæt til venter / slet), og viser til sidst et resultat.

Feedback i vinduet: **(1)** fremdriftslinje + fase, **(2)** historik der løbende
viser hvad der er sket (gemmes også i `Output/logs/`), **(3)** Pause/Fortsæt og
Stop, **(4)** en afsluttende opsummering (fx *"X aftaler godkendt, Y slettet,
Z sat til venter, …"*). Vinduet lukkes manuelt.

## Opsætning

Kræver Python 3.13, Google Chrome, og [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
cp .env.example .env   # udfyld ATS_TOKEN, ATS_URL, ATS_WORKQUEUE_OVERRIDE m.m.
```

Relevante `.env`-værdier:

| Variabel | Beskrivelse |
|---|---|
| `ATS_TOKEN` / `ATS_URL` | Adgang til Automation Server-API'et (arbejdskøen). |
| `ATS_WORKQUEUE_OVERRIDE` | ID på den arbejdskø der skal bruges (sættes manuelt ved desktop-kørsel). |
| `LOCAL_DEVELOPMENT` | `true` ved desktop-/lokal kørsel. |
| `BASE_DIR` | Mappe til input/output (default: repo-roden). Filer lægges i `BASE_DIR/Output`. |
| `SEND_ERROR_EMAILS` | `false` på desktop (fejl vises i historikken/loggen). |

## Kørsel

**Desktop-app (normal brug):**

```sh
uv run python -m gui.app
```

**Headless (samme faser, uden GUI – fx fra Automation Server):**

```sh
uv run python main.py --overview     # dan overblik (Excel)
uv run python main.py --queue        # læs Excel og fyld arbejdskøen
uv run python main.py --process      # gennemfør ændringerne i STIL
uv run python main.py --finalize     # opsummér resultatet
```

## Arkitektur

| Fil | Ansvar |
|---|---|
| `gui/app.py` | Tkinter-vindue, arbejdstråd, fremdrift/historik/pause/stop. |
| `main.py` | Faser (`populate_queue` / `process_workqueue` / `finalize`) + `--overview`. Headless-indgang. |
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
