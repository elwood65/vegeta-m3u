#!/usr/bin/env python3
"""Scraper per i server IPTV italiani (bandiera 🇮🇹) del player Vegeta TV.

Flusso:
1. Scarica serveurs.txt da vegetatv.duckdns.org
2. Filtra i soli server con bandiera italiana (emoji U+1F1EE U+1F1F9)
3. Per ogni server IT scarica la playlist m3u_plus e la salva in playlists/
Flusso:
1. Scarica serveurs.txt da vegetatv.duckdns.org
2. Filtra i soli server con bandiera italiana (emoji U+1F1EE U+1F1F9)
3. Per ogni server IT scarica la playlist m3u_plus e la salva in playlists/
4. Unisce le playlist (senza dedup, nomi originali) in due file:
   vegeta_italia.m3u (solo canali LIVE .m3u8) e vegeta_italia_vod.m3u (solo VOD)
5. Scarta i canali marcati come sicuramente NON italiani (bandiere estere,
   prefissi paese, parole nazione nel group-title)
6. Scrive report.json con l'esito del run

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
OUTPUT_FILE = BASE_DIR / "vegeta_italia.m3u"        # canali LIVE (.m3u8)
VOD_OUTPUT_FILE = BASE_DIR / "vegeta_italia_vod.m3u" # soli canali VOD
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


# --- Filtro canali NON italiani ---
FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF][\U0001F1E6-\U0001F1FF]")
FOREIGN_GROUP_WORDS = [
    "GERMAN", "FRANCE", "FRANCIA", "SPAIN", "ESPANA", "PORTUGAL", "HUNGARY", "BULGARIA",
    "ROMANIA", "RUMENIA", "ALBANIA", "TURKEY", "TURCHIA", "RUSSIA", "POLAND", "POLONIA",
    "BRAZIL", "BRASIL", "ARGENTINA", "MEXICO", "COLOMBIA", "CHILE", "PERU", "VENEZUELA",
    "BOLIVIA", "PARAGUAY", "URUGUAY", "ECUADOR", "COSTA RICA", "PANAMA", "GUATEMALA",
    "CUBA", "HAITI", "INDIA", "INDIANI", "CHINA", "KOREA", "JAPAN", "THAILAND", "VIETNAM",
    "PHILIPPINES", "INDONESIA", "MALAYSIA", "SINGAPORE", "TAIWAN", "HONG", "PAKISTAN",
    "BANGLADESH", "SRI LANKA", "NEPAL", "AFGHAN", "IRAN", "IRAQ", "ISRAEL", "ISRAELE",
    "JORDAN", "KUWAIT", "QATAR", "SAUDI", "EMIRATI", "DUBAI", "BAHRAIN", "OMAN", "LEBAN",
    "SYRIA", "YEMEN", "EGYPT", "ALGERIA", "TUNISIA", "MOROCCO", "LIBYA", "SUDAN", "NIGERIA",
    "GHANA", "KENYA", "ETHIOPIA", "SOUTH AFRICA", "ANGOLA", "MOZAMB", "AUSTRALIA", "CANADA",
    "ENGLAND", "USA ", "UNITED STATES", "ENGLISH", "DANIMARCA", "NORVEG", "SVEZIA",
    "FINLAND", "FINLANDIA", "IRLANDA", "SCOZIA", "GALLES", "SVIZZERA", "AUSTRI", "BELGIO",
    "NEDERLAN", "PAESI BASSI", "UNGHERIA", "CZECH", "SLOVACCHIA", "SLOVENIA", "CROATIA",
    "CROAZIA", "SERBIA", "BOSNIA", "MONTENEGRO", "MACEDONIA", "MOLDAVIA", "UCRAINA",
    "BIELORUSSIA", "KAZAKH", "AZERBAIJAN", "GEORGIA", "ARMENIA", "GRECIA", "GREECE",
    "MESSICO", "DOMINICANA", "ISLANDA", "ISRAELI", "PALESTIN", "ARABIA",
    "SPORTDEUTSCHLAND",
]
COUNTRY_PREFIXES = {
    "BG", "FR", "DE", "PT", "ES", "RU", "BR", "AL", "RO", "GR", "IN", "MX", "CN", "PL",
    "CZ", "HU", "SE", "NO", "DK", "FI", "AT", "UA", "AU", "CA", "IL", "EG", "SA", "QA",
    "JO", "PK", "BD", "TH", "VN", "MY", "PH", "ID", "KR", "JP", "TW", "SG", "HK", "ZA",
    "NG", "KE", "RS", "SI", "HR", "SK", "LT", "LV", "EE", "MK", "IR", "IQ", "SY", "LB",
    "TN", "MA", "DZ", "LY", "CL", "CO", "PE", "EC", "UY", "VE", "BO", "PY", "DO", "CR",
    "PA", "CU", "ME", "AZ", "GE", "AM", "KZ", "IS", "IE", "GB", "UK", "USA", "ARG",
    "MEX", "PER", "ALB", "KURD", "EX", "MGRE", "ESP", "BIH", "MNE", "SRB", "HRV", "JPN",
}
PREFIX_NAME_RE = re.compile(r"^\s*\[([A-Za-z]{2,4})\]\s*|^\s*([A-Za-z]{2,4}):\s*")


def _flag_country(text: str) -> str | None:
    for fl in FLAG_RE.findall(text):
        return chr(65 + ord(fl[0]) - 0x1F1E6) + chr(65 + ord(fl[1]) - 0x1F1E6)
    return None


def is_foreign_channel(name: str, group: str) -> tuple[bool, str]:
    """True se il canale è marcatamente NON italiano (flag/parole/prefissi)."""
    up_g = (group or "").upper()
    cc = _flag_country(group or "") or _flag_country(name or "")
    if cc and cc != "IT":
        return True, f"flag {cc}"
    for w in FOREIGN_GROUP_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", up_g):
            return True, f"parola {w}"
    m = PREFIX_NAME_RE.match(name or "")
    if m:
        code = (m.group(1) or m.group(2)).upper()
        if code in COUNTRY_PREFIXES:
            return True, f"prefisso {code}"
    return False, ""


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

    # Unisci le playlist: canali LIVE (vivo, .m3u8) e canali VOD, entrambi filtrati
    print("[3/4] Creo i file uniti (live IT e VOD) ...")
    live_channels = 0
    vod_channels = 0
    filtered_non_it = 0
    filter_reasons = {}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_live, open(VOD_OUTPUT_FILE, "w", encoding="utf-8") as out_vod:
        out_live.write("#EXTM3U\n")
        out_vod.write("#EXTM3U\n")
        for idx, path in enumerate(saved_paths, start=1):
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            lines = [ln for ln in content.splitlines() if not ln.strip().startswith("#EXTM3U")]
            live_chunk, vod_chunk = [], []
            for i in range(len(lines)):
                ln = lines[i]
                if not ln.strip().startswith("#EXTINF"):
                    continue
                name = ""
                m = re.search(r'tvg-name="([^"]*)"', ln)
                if m:
                    name = m.group(1)
                g = re.search(r'group-title="([^"]*)"', ln)
                group = g.group(1) if g else ""
                next_url = ""
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        next_url = lines[j].strip()
                        break
                if not next_url.startswith("http"):
                    continue
                foreign, why = is_foreign_channel(name, group)
                if foreign:
                    filtered_non_it += 1
                    filter_reasons[why] = filter_reasons.get(why, 0) + 1
                    continue
                if ".m3u8" in next_url:
                    live_chunk.extend([ln, next_url])
                    live_channels += 1
                else:
                    vod_chunk.extend([ln, next_url])
                    vod_channels += 1
            header = f"# ===== Server {idx:02d} ({path.stem}) =====\n"
            if live_chunk:
                out_live.write(header)
                out_live.write("\n".join(live_chunk))
                out_live.write("\n\n")
            if vod_chunk:
                out_vod.write(header)
                out_vod.write("\n".join(vod_chunk))
                out_vod.write("\n\n")
    print(f"  Salvato {OUTPUT_FILE} — {live_channels} canali live italiani (scartati {filtered_non_it} non-IT in totale)")
    print(f"  Salvato {VOD_OUTPUT_FILE} — {vod_channels} canali VOD italiani")

    # Report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": SERVEURS_URL,
        "total_servers_in_file": len(entries),
        "italian_servers": len(italian),
        "ok_servers": sum(1 for s in server_stats if s["ok"]),
        "failed_servers": [s for s in server_stats if not s["ok"]],
        "total_channels": live_channels + vod_channels,
        "live_channels": live_channels,
        "vod_channels": vod_channels,
        "filtered_non_italian": filtered_non_it,
        "filter_reasons": filter_reasons,
        "servers": server_stats,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[4/4] Report scritto in {REPORT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())