# Handball xG auf Oracle Cloud (gratis) betreiben

Am Ende läuft Handball xG rund um die Uhr unter einer Adresse wie `https://130-61-12-34.sslip.io`:
mit HTTPS und Passwort-Login. Verifikator, Import und Quoten-Abgleich laufen auch, wenn dein PC aus ist.

Zeitbedarf: etwa eine Stunde. Kosten: 0 € im Rahmen von „Always Free“.

---

## 1. Oracle-Konto anlegen (machst du selbst)

1. Auf <https://www.oracle.com/cloud/free/> „Start for free“ wählen.
2. Die **Home Region** gut wählen, sie lässt sich später nicht ändern. Nimm eine in deiner Nähe, z. B. *Switzerland North (Zurich)* oder *Germany Central (Frankfurt)*.
3. Die Kreditkarte dient nur zur Prüfung. Im Always-Free-Rahmen wird nichts abgebucht.

---

## 2. Server anlegen

In der Oracle-Konsole: **☰ → Compute → Instances → Create instance**.

| Feld | Wert |
|---|---|
| Name | `handball-xg` |
| Image | **Canonical Ubuntu 24.04** (auf „Change image“ klicken) |
| Shape | **Ampere → VM.Standard.A1.Flex**, **2 OCPU, 12 GB RAM** (gratis bis 4 OCPU / 24 GB) |
| Networking | neues VCN mit öffentlichem Subnetz, **„Assign a public IPv4 address“ an** |
| SSH keys | **„Generate a key pair for me“ → „Save private key“** |

Den privaten Schlüssel speichern unter `C:\Users\anton\.ssh\oracle-handball.key`.

**„Out of capacity“?** Gratis-Server sind in beliebten Regionen oft knapp.
- Später noch einmal versuchen, oder eine andere *Availability Domain* wählen.
- Oder das Konto auf **Pay As You Go** umstellen. Always-Free-Server bleiben dann trotzdem gratis, und es gibt kaum noch Engpässe.
- Lege dafür unter *Billing → Budgets* ein Budget von 1 € mit E-Mail-Warnung an.

Nach dem Anlegen die **Public IP address** notieren, z. B. `130.61.12.34`.

### Ports 80 und 443 öffnen

1. Auf der Seite der Instanz auf das Subnetz klicken, dann auf die **Default Security List**.
2. **Add Ingress Rules** wählen und zwei Regeln anlegen:
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `80`;
   - dasselbe noch einmal mit Port `443`.

Die Firewall auf dem Server selbst öffnet später das Einrichtungsskript.

---

## 3. Auf dem PC: Paket bauen

In PowerShell im Projektordner:

```powershell
cd C:\Users\anton\Projects\handball-xg\frontend
npm run build
cd ..
backend\.venv\Scripts\python deploy\pack.py
```

Danach liegen in `deploy\out\` die Dateien `handball-xg-app.tar.gz` und `handball.db`.

Windows verlangt, dass nur du den Schlüssel lesen darfst. Einmalig ausführen:

```powershell
icacls C:\Users\anton\.ssh\oracle-handball.key /inheritance:r /grant:r "$($env:USERNAME):R"
```

---

## 4. Hochladen

IP durch deine ersetzen:

```powershell
scp -i C:\Users\anton\.ssh\oracle-handball.key deploy\out\handball-xg-app.tar.gz deploy\out\handball.db backend\.env ubuntu@130.61.12.34:~
```

`backend\.env` enthält deine API-Schlüssel. Es geht verschlüsselt direkt auf deinen eigenen Server.

---

## 5. Auf dem Server einrichten

```powershell
ssh -i C:\Users\anton\.ssh\oracle-handball.key ubuntu@130.61.12.34
```

Dann auf dem Server:

```bash
tar -xzf handball-xg-app.tar.gz deploy/setup.sh && bash deploy/setup.sh
```

Das Skript erledigt Folgendes:
- installiert Python und Caddy (für HTTPS);
- legt das Programm nach `/opt/handball-xg` und übernimmt Datenbank und `.env`;
- **fragt nach dem Passwort für die Webseite** (mindestens 10 Zeichen) und trägt es als `APP_PASSWORD` ein;
- richtet den Dienst ein, der automatisch startet, auch nach einem Neustart des Servers;
- öffnet die Ports 80 und 443 und holt das HTTPS-Zertifikat;
- sichert die Datenbank jeden Tag um 03:30 nach `backend/data/backups` (14 Tage).

Am Ende steht die Adresse da, z. B. `https://130-61-12-34.sslip.io`. Der erste Aufruf kann 1–2 Minuten dauern.

Eigene Domain? Bei der Domain einen A-Eintrag auf die Server-IP setzen und das Skript mit der Domain starten: `bash deploy/setup.sh handball.meinedomain.ch`.

---

## 6. Wichtig: der PC und der Server nebeneinander

Ab jetzt ist der **Server die Hauptversion**: Dort laufen Verifikator, Import und Quoten-Abgleich.

Damit der PC nicht dasselbe tut und das OddsPapi-Gratis-Kontingent (250 Abfragen/Monat) doppelt verbraucht, auf dem PC in `backend\.env` eintragen:

```
ODDSPAPI_SYNC_HOURS=0
AUTO_IMPORT_HOURS=0
VERIFY_MINUTES=0
```

Neue Strategien und Tipps entstehen dann nur noch auf dem Server.

**Datenbank vom Server auf den PC holen:** Doppelklick auf `daten_vom_server.bat` im Projektordner.

- Danach hat der PC denselben Stand wie online: neue Spiele mit Würfen, Quoten und Verifikator-Tipps.
- Die lokale Datenbank wird vorher nach `backend\data\backups\handball.vor-serverkopie-….db` gesichert. Die letzten drei Sicherungen bleiben erhalten.
- Was du nur auf dem PC geändert hast, etwa eine neue Strategie, ist danach überschrieben. Lege Strategien deshalb auf der Webseite an.
- Anderer Server: die Umgebungsvariablen `HXG_SERVER` (z. B. `ubuntu@1.2.3.4`) und `HXG_KEY` setzen.

Der Server holt neue Spiele **stündlich** (`AUTO_IMPORT_HOURS=1` in seiner `.env`). Die Würfe übernimmt er 3 Stunden nach Anpfiff, weil der Spielverlauf direkt nach dem Spiel oft noch unvollständig ist.

---

## 7. Neue Version einspielen

Auf dem PC:

```powershell
cd C:\Users\anton\Projects\handball-xg\frontend; npm run build; cd ..
backend\.venv\Scripts\python deploy\pack.py --no-db
scp -i C:\Users\anton\.ssh\oracle-handball.key deploy\out\handball-xg-app.tar.gz ubuntu@130.61.12.34:~
ssh -i C:\Users\anton\.ssh\oracle-handball.key ubuntu@130.61.12.34 "bash /opt/handball-xg/deploy/update.sh"
```

Das Update sichert zuerst die Datenbank. Daten, `.env` und Passwort bleiben erhalten.

---

## Wenn etwas nicht geht

| Problem | Prüfen |
|---|---|
| Seite lädt nicht | `sudo systemctl status handball-xg` und `tail -50 /opt/handball-xg/backend/data/server.log` |
| Kein HTTPS / Zertifikatfehler | Ports 80/443 in der Security List offen? `sudo journalctl -u caddy -n 50` |
| Passwort ändern | `nano /opt/handball-xg/backend/.env` → Zeile `APP_PASSWORD=…` ändern, dann `sudo systemctl restart handball-xg`. Alle Geräte müssen sich neu anmelden. |
| Ein Import klappt dort nicht, auf dem PC schon | Manche Datenquellen sperren Rechenzentrums-Adressen. Diesen Import auf dem PC machen, `deploy\pack.py` ausführen und nur `handball.db` hochladen (wie in Abschnitt 4), dann auf dem Server: `bash /opt/handball-xg/deploy/replace_db.sh` |
| Zu viele Fehlversuche beim Login | 15 Minuten warten, die Sperre gilt nur für diese Adresse. |
