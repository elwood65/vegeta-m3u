# Design — Scraper Vegeta IPTV (canali italiani 🇮🇹)

Data: 2026-08-09

## Scopo

Un tool che interroga il file `serveurs.txt` del sito `http://vegetatv.duckdns.org/`, seleziona i soli server contrassegnati con bandiera italiana 🇮🇹, scarica la playlist di ognuno, le unisce in un unico file `.m3u` e pubblica il risultato su una repo GitHub pubblica, auto-aggiornata ogni 24 ore tramite GitHub Actions.

## Contesto verificato (ricerche fatte)

- Il sito è un player IPTV a pagina singola (VEGETA TV) che carica i server con:
  `fetch('serveurs.txt?v=' + Date.now(), { cache: 'no-store' })`
- `serveurs.txt` è un file **statico** su nginx (`Server: nginx/1.24.0 (Ubuntu)`), `Last-Modified: Sun, 12 Jul 2026` — **NON si autoaggiorna/autoIgenera**: cambia solo quando il gestore lo ricarica manualmente. L'aggiornamento periodico deve essere garantito dal nostro workflow.
- Formato file: una riga per server, `<URL xtream> <emoji bandiere>`; righe vuote o `#...` ignorate.
- Attualmente: 60 server, di cui **7 con bandiera italiana** (emoji 🇮🇹 = codepoint `U+1F1EE U+1F1F9`).
- Il filtro bandiera deve confrontare i codepoint esatti (evita falsi positivi dal testo "IT" nei domini).
- **Nota encoding**: il file inizia con BOM UTF-8 (`\uFEFF`) — da rimuovere. Emoji, su alcuni terminal, possono apparire come `??` ma sono valide.

## Comportamento richiesto dal committente

- Ogni link viene invocato; l'output (m3u/m3u8) viene salvato in una cartella di output.
- Tutti i file vengono uniti in uno unico.
- I canali duplicati tra server **restano** (fallback in caso di malfunzionamento di uno) — niente dedup dei canali.
- I nomi dei canali restano **identici** a quelli delle singole playlist (nessun prefisso "S1:" o simile).
- La lista deve vivere su una repo GitHub pubblica accessibile da internet, aggiornata ogni **24 ore**.

## Struttura del progetto

```
vegeta-m3u/
├── scraper.py            # script principale (solo std lib Python 3, zero dipendenze)
├── README.md             # istruzioni: uso locale, creazione repo, link file finale
├── .github/workflows/
│   └── update.yml        # GitHub Action: esecuzione programmata ogni 24h + manual dispatch
├── playlists/            # una copia m3u per server (commitate)
│   └── <01-07>-<host>.m3u
├── report.json           # report dell'ultimo run: esito per server, n. canali, timestamp
└── vegeta_italia.m3u     # FILE FINALE: playlist unita (ciò che userai / link da raw.githubusercontent)
```

## scraper.py — specifica

Solo **libreria standard** Python (`urllib.request`, `re`, `json`, `pathlib`, `datetime`): nessuna dipendenza da installare in Actions.

Flusso:

1. **Fetch di `serveurs.txt`** con cache-buster: `http://vegetatv.duckdns.org/serveurs.txt?v=<unix>`:
   - timeout 30s
   - decode `utf-8` dopo rimozione BOM
2. **Parse righe**: trim, ignora vuote e righe che iniziano con `#`. Per ogni riga: primo token = URL, resto = bandiere (emoji).
3. **Filtro bandiera 🇮🇹**: il token bandiera deve contenere i codepoint `U+1F1EE` e `U+1F1F9` contigui (esattamente `\u{1F1EE}\u{1F1F9}`). Criterio: presenza dell'emoji IT nella riga (es. potrebbe essere combinata: `🇮🇹🌐` — in quel caso il server è comunque classificato IT). Log delle righe scartate con motivo.
4. Per ogni server IT (in ordine di apparizione):
   - `GET` dell'URL con timeout 30s e header User-Agent descrittivo
   - Se risposta `2xx`: salva il testo in `playlists/<NN>-<host>.m3u` (host = dominio senza porta, sanitizzato)
   - Se errore rete/HTTP/timeout: segnala nel report, **non bloccare** gli altri
   - Rilevazione del formato: il contenuto inizia con `#EXTM3U` di norma; se no, registra come `unknown` nel report ma salva comunque
5. **Unisci**: concatena tutte le playlist salvate in ordine server, interponendo un commento `# ===== Server <NN> (<host>) =====` tra una e l'altra, e header globale `#EXTM3U` in cima al file unito. Nessuna dedup, nomi originali intatti.
6. **Output**: scrive `vegeta_italia.m3u` (UTF-8, BOM opzionale — meglio senza) + `report.json` con:
   - `timestamp` ISO
   - `total_servers` = n. server IT trovati
   - `ok_servers` / `failed_servers` (lista nome + motivo)
   - `playlist_count` per server
   - `total_channels` (righe `#EXTINF` nel file unito)
7. Exit code: 0 anche con qualche server fallito; fail solo per errori fatali (serveurs.txt irraggiungibile o nessun server IT).

Robustezza:
- Timeout globali per ogni HTTP call (30 s lettura).
- URL "uncrackable": tollera righe con più spazi, url aventi `&` nella query (importante: non richiede escaping).
- Nome file sicuro da host.

## GitHub Action (.github/workflows/update.yml)

- **Trigger**:
  - `schedule: cron 0 6 * * *` (ogni giorno 06:00 UTC) — equivalgo app di 24h
  - `workflow_dispatch` (manuale)
- **Job `update`** su `ubuntu-latest`:
  1. `actions/checkout@v4`
  2. `python scraper.py` (Python 3.11+ preinstallato)
  3. `git status --porcelain` per rilevare modifiche
  4. Se modificate: `git add -A`, commit con messaggio `chore: update playlists (timestamp)` con `git commitor` di default, push back su `main`
  5. Se nessun cambiamento: termina senza commit (evita commit vuoti)
- **Permissions**: `contents: write` per il push nel run.

## GitHub Action — dettagli

```yaml
name: Update playlists
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run scraper
        run: python scraper.py
      - name: Commit changes if any
        run: |
          if [ -n "$(git status --porcelain)" ]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add -A
            git commit -m "chore: update playlists ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
            git push
          else
            echo "No changes"
          fi
```

## URL finali

- File unito: `https://raw.githubusercontent.com/<USER>/vegeta-m3u/main/vegeta_italia.m3u`
- (il `USER` verrà deciso alla creazione della repo dal proprietario)

## README.md — contenuto previsto

- Descrizione breve del tool
- Prerequisiti: Python 3.11+, git; opzionale `gh` CLI
- Uso locale: `python scraper.py`
- Come creare la repo: `gh repo create vegeta-m3u --public --source . --push` oppure dal sito web
- Attivare Actions: il workflow parte da subito; il cron è in approccio `0 6 * * *`
- Come aprire la playlist: link raw + player qualsiasi (V LC, IPTV, Kodi, ecc.)
- Disclaimer: le playlist sono pubbliche/gratuite indicate dal sito fonte; l'utente verifica i termini d'uso prima dell'utilizzo.

## Aggiornamento (dopo test locale)

- `vegeta_italia.m3u` (162 MB) supera il limite GitHub di 100 MB per file → il push fallirebbe.
- **Decisione:** split live/VOD.
  - `vegeta_italia.m3u` — SOLO canali live (URL contenente `.m3u8`): file piccolo, pubblicato su GitHub.
  - `vegeta_italia_full.m3u` — tutto (live + VOD + altro): grande, **escluso da git** (`.gitignore`), resta locale.
  - `report.json`: aggiunti `total_live_channels` e `total_vod_channels`.
- Identificazione live: la riga URL contiene `.m3u8`. Tutto il resto (`.mp4`, `out.mp4`, ecc.) = VOD.
- Nomi canali identici, niente dedup, separatori server `# ===== Server NN (host) =====` in entrambi i file.

## Rischio e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Server IT morto/lento | Timeout per ogni GET; salta e continua; report lo segnala |
| `serveurs.txt` cambia formato | Parser difensivo (trim, ignora `#`, token-based); report chiaro |
| Repository senza push permission | `permissions: contents: write`; workflow gestito |
| Emoji non visualizzabili | Codepoint `U+1F1EE U+1F1F9` confrontati al livello di stringa, indipendenti da font |
| Commit vuoti inutili | Solo commit se `git status --porcelain` non vuoto |