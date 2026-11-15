"""Datenbank vom Server auf den PC holen: gleicher Stand wie online (Spiele, Würfe, Quoten, Verifikator-Tipps).

Die lokale Datenbank wird vorher nach backend/data/backups/ gesichert (die letzten 3 bleiben).
Der lokale Server wird dafür kurz gestoppt und danach wieder gestartet.

Aufruf: Doppelklick auf ``daten_vom_server.bat`` im Projektordner, oder
    backend\\.venv\\Scripts\\python deploy\\pull_db.py [--no-start]
Anderer Server/Schlüssel: Umgebungsvariablen HXG_SERVER (z. B. ubuntu@1.2.3.4) und HXG_KEY.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
DB = DATA / "handball.db"
SERVER = os.getenv("HXG_SERVER", "ubuntu@141.144.248.91")
KEY = os.getenv("HXG_KEY", str(Path.home() / ".ssh" / "oracle-handball.key"))
REMOTE_DB = "/opt/handball-xg/backend/data/handball.db"
REMOTE_TMP = "/tmp/hxg-pull.db"
KEEP = 3
# konsistente Kopie auch während der Server schreibt (SQLite-Backup-API), dann gepackt
REMOTE_SNAPSHOT = (
    f"python3 -c \"import sqlite3; s=sqlite3.connect('{REMOTE_DB}'); d=sqlite3.connect('{REMOTE_TMP}'); "
    f"s.backup(d); d.close(); s.close()\" && gzip -f {REMOTE_TMP}"
)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ssh_base() -> list[str]:
    return ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]


def local_server_pids() -> list[int]:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -match 'run_server' } | ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def main() -> int:
    start_after = "--no-start" not in sys.argv
    download = DATA / "handball.download.db"
    packed = DATA / "handball.download.db.gz"

    print(f"1/4 Kopie auf dem Server anlegen ({SERVER}) …")
    run(["ssh", *ssh_base(), SERVER, REMOTE_SNAPSHOT])

    print("2/4 Herunterladen …")
    run(["scp", "-q", *ssh_base(), f"{SERVER}:{REMOTE_TMP}.gz", str(packed)])
    run(["ssh", *ssh_base(), SERVER, f"rm -f {REMOTE_TMP}.gz"])
    with gzip.open(packed, "rb") as src, open(download, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    packed.unlink()
    con = sqlite3.connect(download)
    ok = con.execute("PRAGMA quick_check").fetchone()[0]
    games, shots = con.execute("select (select count(*) from games), (select count(*) from shots)").fetchone()
    con.close()
    if ok != "ok":
        download.unlink()
        print(f"Die heruntergeladene Datenbank ist beschädigt ({ok}). Lokal wurde nichts geändert.")
        return 1
    print(f"    {download.stat().st_size / 1e6:.0f} MB, {games} Spiele, {shots} Würfe")

    print("3/4 Lokalen Server stoppen und alte Datenbank sichern …")
    was_running = bool(local_server_pids())
    for pid in local_server_pids():
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    for _ in range(20):
        if not local_server_pids():
            break
        time.sleep(0.5)
    backups = DATA / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        # Sicherung per Backup-API, damit auch noch nicht übernommene WAL-Änderungen drin sind
        s, d = sqlite3.connect(DB), sqlite3.connect(backups / f"handball.vor-serverkopie-{datetime.now():%Y%m%d-%H%M}.db")
        s.backup(d)
        d.close()
        s.close()
        for old in sorted(backups.glob("handball.vor-serverkopie-*.db"))[:-KEEP]:
            old.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(DB) + suffix).unlink(missing_ok=True)
    os.replace(download, DB)

    print("4/4 Fertig: der PC hat jetzt den Stand vom Server.")
    if start_after and was_running:
        subprocess.Popen(["wscript.exe", str(ROOT / "start.vbs")], cwd=ROOT)
        print("    Lokaler Server wird neu gestartet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
