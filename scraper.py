#!/usr/bin/env python3
"""Scraper per i server IPTV italiani (bandiera 🇮🇹) del player Vegeta TV.

Flusso:
1. Scarica serveurs.txt da vegetatv.duckdns.org
2. Filtra i soli server con bandiera italiana (emoji U+1F1EE U+1F1F9)
3. Per ogni server IT scarica la playlist m3u_plus e la salva in playlists/
4. Unisce tutte le playlist in vegeta_italia.m3u (senza dedup, nomi originali)
5. Scrive report.json con l'esito del run

Solo libreria standard: nessuna dipendenza esterna.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "http://vegetatv.duckdns.org"
SERVEURS_URL = BASE_URL + "/serveurs.txt"
IT_FLAG = "\U0001F1EE\U0001F1F9"  # 🇮🇹 Regional Indicator I + T

BASE_DIR = Path(__file__).resolve().parent
PLAYLISTS_DIR = BASE_DIR / "playlists"
OUTPUT_FILE = BASE_DIR / "vegeta_italia.m3u"
FULL_OUTPUT_FILE = BASE_DIR / "vegeta_italia_full.m3u"
REPORT_FILE = BASE_DIR / "report.json"

TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; vegeta-m3u-scraper/1.0)"


def http_get(url: str, timeout: int = TIMEOUT) -> tuple[int, bytes]:
    """GET e ritorna (status, body)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def safe_host(url: str, index: int) -> str:
    """Estrae l'host dall'URL per il nome file, con fallback sicuro."""
    m = re.match(r"https?://([^/:#]+)", url)
    if m:
        host = m.group(1).replace(".", "_")
        return f"{index:02d}-{host}"
    return f"{index:02d}-unknown"


def parse_serveurs(text: str) -> list[dict]:
    """Ritorna [{url, flags, line}] dalle righe non vuote di serveurs.txt."""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        url = parts[0]
        flags = "".join(parts[1:])
        entries.append({"url": url, "flags": flags, "line": line})
    return entries


def is_italian(entry: dict) -> bool:
    """True se la bandiera italiana è presente (emoji o codice IT)."""
    flag_part = entry["flags"]
    if IT_FLAG in flag_part:
        return True
    # Permette codici a 2 lettere tipo "IT" o "IT 🇮🇹" se il sito cambiasse formato
    plain = re.sub(r"[^A-Za-z]", "", flag_part).upper()
    return "IT" in plain


def channel_count(playlist_body: str) -> int:
    return sum(1 for line in playlist_body.splitlines() if line.strip().startswith("#EXTINF"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # console Windows
    except Exception:
        pass
    server_stats = []
    total_channels = 0

    print(f"[1/4] Scarico {SERVEURS_URL} ...")
    try:
        status, data = http_get(SERVEURS_URL + "?v=" + str(int(time.time())))
        if status != 200:
            print(f"  ERRORE: serveurs.txt ha risposto HTTP {status}")
            return 1
    except Exception as exc:
        print(f"  ERRORE: impossibile scaricare serveurs.txt: {exc}")
        return 1

    text = data.decode("utf-8-sig")  # rimuove il BOM
    entries = parse_serveurs(text)
    italian = [e for e in entries if is_italian(e)]
    print(f"  {len(entries)} server totali, {len(italian)} con bandiera italiana 🇮🇹")

    if not italian:
        print("  Nessun server italiano trovato: niente da fare.")
        return 1

    # Salva ogni playlist
    PLAYLISTS_DIR.mkdir(exist_ok=True)
    saved_paths = []
    for i, entry in enumerate(italian, start=1):
        url = entry["url"]
        name = safe_host(url, i)
        print(f"[2/4] ({i}/{len(italian)}) {url}")
        try:
            status, body = http_get(url)
            if status != 200:
                print(f"  HTTP {status} — saltato")
                server_stats.append({"url": url, "ok": False, "reason": f"HTTP {status}"})
                continue
            out_path = PLAYLISTS_DIR / f"{name}.m3u"
            out_path.write_bytes(body)
            saved_paths.append(out_path)
            n = channel_count(body.decode("utf-8", errors="replace"))
            total_channels += n
            server_stats.append({"url": url, "ok": True, "playlist": out_path.name, "channels": n})
            print(f"  OK: {n} canali → {out_path.name}")
        except Exception as exc:
            print(f"  ERRORE: {exc} — saltato")
            server_stats.append({"url": url, "ok": False, "reason": str(exc)})

    if not saved_paths:
        print("  Nessuna playlist scaricata con successo.")
        return 1

    # Unisci le playlist in un unico file (live) e in uno full (live+VOD+altro)
    print("[3/4] Creo i file uniti (live e full) ...")
    full_channels = 0
    live_channels = 0
    with open(FULL_OUTPUT_FILE, "w", encoding="utf-8") as out_full, open(OUTPUT_FILE, "w", encoding="utf-8") as out_live:
        out_full.write("#EXTM3U\n")
        out_live.write("#EXTM3U\n")
        for idx, path in enumerate(saved_paths, start=1):
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            lines = [ln for ln in content.splitlines() if not ln.strip().startswith("#EXTM3U")]
            # raggruppa righe (#EXTINF + url successivo)
            full_chunk, live_chunk = [], []
            pending = None
            block = []
            for ln in lines:
                block.append(ln)
                if ln.strip().startswith("#EXTINF"):
                    pending = ln
                    continue
                if pending is None and not ln.strip():
                    continue
                url_line = ln
                if pending is not None and url_line.strip().startswith("http"):
                    if ".m3u8" in url_line:
                        live_chunk.extend(block)
                        live_channels += 1
                    full_chunk.extend(block)
                    full_channels += 1
                    pending, block = None, []
            header = f"# ===== Server {idx:02d} ({path.stem}) =====\n"
            if full_chunk:
                out_full.write(header)
                out_full.write("\n".join(full_chunk).strip())
                out_full.write("\n\n")
            if live_chunk:
                out_live.write(header)
                out_live.write("\n".join(live_chunk).strip())
                out_live.write("\n\n")
    print(f"  Salvato {OUTPUT_FILE} — {live_channels} canali live")
    print(f"  Salvato {FULL_OUTPUT_FILE} — {full_channels} canali totali")

    # Report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": SERVEURS_URL,
        "total_servers_in_file": len(entries),
        "italian_servers": len(italian),
        "ok_servers": sum(1 for s in server_stats if s["ok"]),
        "failed_servers": [s for s in server_stats if not s["ok"]],
        "total_channels": full_channels,
        "live_channels": live_channels,
        "vod_channels": full_channels - live_channels,
        "servers": server_stats,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[4/4] Report scritto in {REPORT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())