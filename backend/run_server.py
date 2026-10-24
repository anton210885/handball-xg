"""Startet den Server ohne Konsolenfenster (Aufruf mit pythonw.exe über start.vbs).

pythonw hat keine Konsole – alle Ausgaben gehen deshalb nach data/server.log.
Läuft der Server schon, beendet sich das Skript sofort wieder.
"""
import socket
import sys
from pathlib import Path

HOST, PORT = "127.0.0.1", 8010
BACKEND = Path(__file__).resolve().parent


def already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def main():
    if already_running():
        return
    log_dir = BACKEND / "data"
    log_dir.mkdir(exist_ok=True)
    log = open(log_dir / "server.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log

    sys.path.insert(0, str(BACKEND))
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
