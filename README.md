# vegeta-m3u 🇮🇹

Scraper per i server IPTV italiani del player **VEGETA TV** (`http://vegetatv.duckdns.org/`).

Legge `serveurs.txt` dal sito fonte, seleziona i soli server con **bandiera italiana** 🇮🇹,
scarica la playlist di ognuno e le unisce in un unico file `.m3u` — pubblicato su GitHub
e **aggiornato automaticamente ogni 24 ore** via GitHub Actions.

## File prodotti (a ogni run)

| File | Descrizione |
|---|---|
| `vegeta_italia.m3u` | **Playlist finale (canali LIVE)** — questo è il file pubblicato su GitHub |
| `vegeta_italia_full.m3u` | Playlist completa (live + VOD + altro) — **non** su GitHub (>100 MB) |
| `playlists/NN-host.m3u` | Copia della playlist per singolo server (fallback locale) |
| `report.json` | Esito del run: server vivi/morti, n° canali, timestamp |

I canali duplicati tra server **non vengono rimossi**: restano come fallback in caso
di malfunzionamento di un server. I nomi dei canali sono identici alle sorgenti.
Solo i file live (`*.m3u8`) finiscono in `vegeta_italia.m3u`; il file `full` resta
escluso dal repo perché supera il limite GitHub di 100 MB per file.

## Uso locale

```bash
python scraper.py
```

Richiede solo Python 3.11+ (nessuna dipendenza esterna).

## Deploy su GitHub (una tantum)

1. Crea una repo pubblica (es. `vegeta-m3u`):
   ```bash
   gh repo create vegeta-m3u --public --source . --push
   ```
   (oppure creala dal sito e fai `git push` manualmente)

2. Il workflow `.github/workflows/update.yml` parte da subito:
   - **ogni giorno alle 06:00 UTC** (cron `0 6 * * *`)
   - su richiesta manuale: tab *Actions* → *Update playlists* → *Run workflow*

3. Il link stabile del file unito è:
   ```
   https://raw.githubusercontent.com/<UTENTE>/vegeta-m3u/main/vegeta_italia.m3u
   ```

## Come aprire la playlist

- **VLC**: *Media → Apri flusso di rete* e incolla il link `raw.githubusercontent` (o apri il file locale).
- **Kodi / IPTV player mobile / Smart TV**: aggiungi il link alla lista IPTV.

## Disclaimer

Le playlist provengono da server pubblici elencati dal player fonte `vegetatv.duckdns.org`.
La disponibilità non è garantita; verifica i termini d'uso prima di qualunque utilizzo.