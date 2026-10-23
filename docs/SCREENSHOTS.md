# Screenshot-Aufnahme und Fehlerdiagnose

Stand: 23.10.2026.

## Aufnahmewege

Alle Aufnahmen sind vollständige Emulator-Screenshots. ROIs werden erst bei
der Bilderkennung ausgewertet. Es gibt keine Aufnahme nur eines ROI-Ausschnitts.

| Verwendung | Lokaler Slot |
| --- | --- |
| Run Detection | `game_scr` |
| Freebies, Claim-Suche und Menüschließen | `freebie_scr` |
| Lootbug-Erkennung und Buybox-Wiederholungen | `lootbug_scr` |
| Founders | `founders_scr` |
| Levelerkennung | `level_scr` |
| Workflow-Template, Rotation, Rainbow und If-Bedingungen | `wf_scr` |
| Kompatibilitätshelfer `screenshot_gray()` | `manual_scr`, Zielpfad wie bisher über `LOCAL_SCREEN` oder Argument |

Die Slot-Einstellungen im Code bleiben maßgeblich. Jeder Aufnahmeversuch erzeugt
auf Android `<Verzeichnis>/__obelisk_<slot>_<uuid>.png`. Das Verzeichnis wird
aus `REMOTE_SCREEN` abgeleitet, standardmäßig `/sdcard`. Die alte gemeinsame
Datei `/sdcard/__scr.png` wird nicht mehr beschrieben. Eine neue UUID pro Versuch
verhindert auch Kollisionen zwischen Aufnahmen desselben Slots und verschiedener
Botprozesse auf Android.

Die Aufnahme läuft über `core/screen_cache.py`:

1. Zielpfad sperren; unterschiedliche Slots können parallel arbeiten.
2. Aktives ADB-Gerät für diesen Versuch festhalten.
3. Screenshot auf eigenem Android-Pfad aufnehmen.
4. In eine eigene lokale `.part`-Datei neben dem Ziel herunterladen.
5. PNG-Signatur, abschließenden IEND-Chunk, Dekodierbarkeit und Bildmaße prüfen.
6. Geräte-ID prüfen, Zeitstempel aktualisieren und Ziel atomar ersetzen.
7. Eigene Android- und Zwischendateien im `finally`-Block bereinigen.

Eine nicht löschbare Android-Datei wird protokolliert, macht aber eine bereits
erfolgreiche Aufnahme nicht ungültig. Es werden niemals Dateien anderer
Aufnahmeversuche pauschal gelöscht. Bei Prozessabbruch können Reste bleiben.

Die Sperren sind pro Prozess und normalisiertem lokalem Zielpfad organisiert.
Zwei gleichzeitig betriebene Botprozesse benötigen getrennte lokale
Tempverzeichnisse. Ein bereits laufender alter Bot verwendet bis zu seinem
Neustart weiterhin seine alte Implementierung.

## Cache-Vertrag und Fehlerverhalten

- `get_screen(slot, max_age, force=False, color=False)` darf aufnehmen. Ein
  frisches, gültiges Cache-Bild wird wiederverwendet, sofern `force=False`.
- `force=True` verlangt eine erfolgreiche neue Aufnahme. Nach erschöpften
  Versuchen ist das Ergebnis `(None, 0, 0)`, niemals ein altes Bild.
- `get_cached_screen()` liest ausschließlich einen frischen lokalen Slot.
- `get_latest_cached_screen()` liest die erlaubten Slots nach Aktualität und
  überspringt fehlende, alte oder beschädigte Bilder. Es nimmt niemals auf.
- Lootbug und Founders lesen zunächst nur `game_scr` aus dem Cache. Falls
  ungeeignet, nehmen sie in ihrem eigenen Slot auf.
- `color=True` liefert das Farbbild aus demselben geprüften Zugriff. Insbesondere
  der Rainbow-Check liest nach einer fehlgeschlagenen Aufnahme keine alte Datei.
- Der Viewer erhält über `latest_cached_png()` unveränderliche PNG-Bytes ohne
  dauerhaft offenen Dateihandle. Er darf das letzte gültige Bild unabhängig
  vom Alter anzeigen; er ist kein Beleg für eine erfolgreiche aktuelle Aufnahme.
- Die Run Detection prüft unter einer eigenen Sperre. Scheitern sämtliche
  Aufnahmeversuche, setzt sie wie bisher `game_running=False`. Die Meldung
  unterscheidet den Aufnahmefehler von einem bestätigten Bild-Miss. Ein neuer
  UI-Zustand „UNKNOWN“ wurde nicht eingeführt.

ADB kann nach Verbindungsfehlern neu verbinden. Bei explizit gebundener Geräte-ID
wird ein Befehl niemals auf einem anderen Emulator wiederholt. Wählt Reconnect
ein anderes Gerät, beginnt der nächste vollständige Aufnahmeversuch dort neu.
Andere ADB-Aufrufer ohne Gerätebindung behalten ihr bisheriges Verhalten.

## Einstellungen

WebUI → Settings → `screenshot_capture`; Änderung benötigt einen Prozessneustart.
Alte `user_settings.json`-Dateien funktionieren ohne Migration oder neue Einträge.

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `SCREENSHOT_CAPTURE_ATTEMPTS` | `2` | Vollständige Aufnahmeversuche, zulässig 1–5 |
| `SCREENSHOT_RETRY_DELAY_S` | `0.2` | Pause zwischen Versuchen, zulässig 0–10 Sekunden |
| `SCREENSHOT_LOG_LEVEL` | `TXT` | `TXT`: Datei; `FULL`: Datei + WebUI; `UI`: nur WebUI |
| `SCREENSHOT_LOG_CACHE_HITS` | `False` | Zusätzliche Meldung bei erfolgreicher Cache-Wiederverwendung |

Die Aufnahmeversuche kommen zusätzlich zu den bestehenden ADB-Befehlsversuchen.
ADB verwendet weiter bis zu 30 Sekunden Timeout pro Befehl; Reconnect und
Portsuche können zusätzlich dauern. Die Retry-Pause ist keine Gesamtdauergrenze.

## Logging lesen

Alle Aufnahme-Meldungen beginnen mit `[SCREENSHOT]`. Normale Aufnahmen melden
Beginn und erfolgreichen Abschluss. Fehler, Wiederholungen, Wiederverbindungen,
Bereinigungsprobleme und erschöpfte Versuche werden ebenfalls protokolliert.
Cache-Treffer sind standardmäßig ausgeschaltet, um das Log nicht mit jedem
Watchdog-Aufruf zu füllen.

Beispiel, IDs gekürzt:

```text
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 phase=capture begin remote=/sdcard/__obelisk_game_scr_def.png thread=bot-main
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 phase=pull failed: RuntimeError: ... elapsed=0.300s
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 retry_in=0.200s (new full screenshot)
[SCREENSHOT] slot=game_scr request=abc capture=ghi device=127.0.0.1:16416 attempt=2/2 phase=complete size=900x1600 bytes=120000 elapsed=0.700s recovered=True
```

- `request`: verbindet sämtliche Versuche derselben Anforderung.
- `capture`: identifiziert einen einzelnen Versuch und seinen Android-Dateipfad.
- `phase`: `prepare`, `capture`, `pull`, `decode`, `device_check`, `publish`,
  `remote_cleanup`, `local_cleanup`, `cache_read`, `cache_stat`, `viewer_read`
  oder `complete`.
- `adb_attempt` und `adb_reconnect`: zeigen Wiederverbindungen innerhalb eines
  einzelnen ADB-Befehls, einschließlich aktiver und gebundener Geräte-ID.
- `elapsed`: Zeit seit Beginn der Aufnahmefunktion, einschließlich ihrer
  dortigen Sperrwartezeit; die erfolgreiche Abschlussmeldung erfolgt vor
  der Bereinigung. `recovered=True` bedeutet Erfolg nach erneutem Aufnahmeversuch.
- `exhausted`: alle vollständigen Aufnahmeversuche sind fehlgeschlagen.

Bei `[RUNNING] ... marking STOPPED (game stop unconfirmed; ...)` zuerst nach
dem benachbarten `slot=game_scr`-Fehler und dessen `request` suchen. Ein
normaler Statuswechsel mit Match-Score nennt außerdem die Bildquelle
(`cache:<slot>` mit Alter oder `fresh:game_scr`).

## Prüfung

```powershell
python -B -m unittest discover -s tests -v
```

`tests/test_screen_cache.py` verwendet echte PNGs, temporäre lokale Verzeichnisse
und simuliertes ADB. Abgedeckt sind Cache-Alter, kaputte Bilder, Teilübertragungen,
Wiederholungen, atomarer Austausch, Gerätesprünge, parallele Slots, derselbe Slot,
Dashboard-Snapshots, Legacy-Helfer und Fehlerdiagnostik.
`tests/test_screenshot_consumers.py` prüft Run Detection, ihre Serialisierung,
Workflow-Farbbilder, weitere Verbraucher, Konfiguration und HTTP-Auslieferung.
Die bestehenden Founders-/Lootbug-Tests prüfen weiterhin die Feature-Abläufe.

Zusätzlich am 23.10.2026 auf dem lokal konfigurierten MuMu-Gerät geprüft:
sechs gleichzeitige Slots, zwei konkurrierende Aufnahmen von `game_scr`, gültige
900 × 1600-PNGs, Cache-/Viewer-Zugriff, keine verbliebenen lokalen `.part`-Dateien
und Run-Template-Match mit Score 1,000. Dafür wurde ein eigenes temporäres
Verzeichnis verwendet. Keine Klicks, Swipes oder Botstarts; dies ersetzt keinen
längeren Betriebstest mit allen aktiven Features.
