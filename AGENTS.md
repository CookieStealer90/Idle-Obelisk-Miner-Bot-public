# Arbeitsregeln für Codex

Diese Anweisungen gelten für das gesamte Projekt und die laufende Zusammenarbeit.

## Orientierung und Dokumentation

- Lies vor Änderungen die zur Aufgabe passenden Abschnitte von [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). Dort stehen Architektur, Funktionsumfang, Modulabhängigkeiten, Einschränkungen und Prüfhinweise.
- Prüfe betroffene Quelldateien und bei Bedarf lokale Konfigurationen. Gleiche Dokumentationsaussagen mit dem aktuellen Code ab; benenne Abweichungen, Annahmen und ungeprüftes Verhalten.
- Ergänzende Dokumentation:
  - [README.md](README.md): Einrichtung und Betrieb; bekannte Unstimmigkeiten sind im Projektkontext vermerkt.
  - [docs/RELIABILITY.md](docs/RELIABILITY.md): Aktionsergebnisse, Konfigurationsvalidierung, Workflow-Neuladen und LAN-Zugriff.
  - [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md): Screenshot-Pipeline und Cache.
  - [docs/STATISTICS.md](docs/STATISTICS.md): Statistik, Laufzeiten und Migration.
- Halte relevante Dokumentation bei Verhaltens- oder Architekturänderungen aktuell. Diese Datei enthält Arbeitsregeln; technische Details gehören nach `docs/`.

## Vorgehen und Änderungsumfang

- Erhalte bestehende Funktionen und gespeicherte Benutzereinstellungen. Verhaltensänderungen müssen zur Aufgabe gehören und ausdrücklich benannt werden.
- Erstelle vor größeren Änderungen einen konkreten Plan mit betroffenen Komponenten, vorgesehenem Verhalten und Prüfungen. Stimme grundlegende Architekturänderungen mit dem Nutzer ab.
- Halte Änderungen klein, nachvollziehbar und testbar. Vermeide sachfremde Umstrukturierungen, Formatierungen und zusätzliche Abhängigkeiten.
- Prüfe vor Änderungen den Arbeitsstand. Überschreibe oder verwirf keine vorhandenen Änderungen und führe keine unbeauftragten Bereinigungen durch.
- Antworte dem Nutzer auf Deutsch. Diese Arbeitsanweisung bleibt auf Deutsch; Quellcode, Kommentare, Protokollmeldungen, Oberflächentexte, Tests und technische Projektdokumentation bleiben gemäß Projektkonvention auf Englisch.

## Architekturregeln

- `main.py` und `tray_runner.py` sind die Einstiegspunkte. `web/` stellt Flask/Socket.IO und das Dashboard bereit; `bot_app.py` verarbeitet die Befehlswarteschlange und steuert die Hintergrundarbeit.
- Nutze bestehende Helfer in `core/` für ADB, Bilderkennung, Screenshots, Klicks und Scrollen. Feature-Logik gehört nach `features/`, zentrale Vorgaben nach `config/`.
- Beachte die Konfigurationsreihenfolge: `config/settings.py`, anschließend lokale Überschreibungen aus `config/user_settings.json` durch `config/user_overrides.py`. Importiere das Settings-Modul, statt überschreibbare Einzelwerte vorzeitig zu kopieren.
- Neue Einstellungen müssen auch über die WebUI konfigurierbar sein. Prüfe Standardwerte, Validierung, Migration, Speicherung und Oberfläche gemeinsam. Allgemeine Einstellungen benötigen einen Prozessneustart; Workflow-Neuladen übernimmt ausschließlich Workflow-Definitionen an Ausführungsgrenzen.
- Koordiniere Spielaktionen über `state.ingame_action_lock`. Erhalte dokumentierte Ausnahmen sowie Sperr- und Abbruchregeln der Workflows. Halte Metadatensperren nicht während ADB-Aufrufen oder Wartezeiten.
- Erhalte isolierte Screenshot-Slots, atomare Veröffentlichung, Bildvalidierung, Gerätebindung und Altersprüfungen. Ein fehlgeschlagenes frisches Bild darf nicht unbemerkt durch ein altes ersetzt werden.
- ROIs verwenden `(x1, y1, x2, y2)` in Bildschirm-Pixeln. Prüfe Auflösung, Spielsprache und Bildvorlagen zusammen; eine automatische Anpassung an beliebige Auflösungen ist nicht vorhanden.
- Ein erfolgreicher ADB-Klick bestätigt keine Spielbelohnung. Erhalte die Fehlerweitergabe und erhöhe Aktionszähler nicht nach fehlgeschlagenen Aktionen.
- Bewahre Konfigurationsmigrationen, atomare JSON-Speicherung und bestehende LAN-/Origin-Prüfungen. Veröffentliche keine lokalen Geheimnisse oder benutzerspezifischen Konfigurationen.

## Prüfung und Abschluss

- Führe passende Regressionstests aus `tests/` aus. Befehle für die vorhandenen Python- und JavaScript-Tests:

  ```text
  python -B -m unittest discover -s tests -v
  node --test tests/test_dashboard_connection.cjs tests/test_dashboard_editors.cjs tests/test_dashboard_gem_stats.cjs
  ```

- Wähle Prüfungen nach dem Änderungsumfang. Bei reinen Dokumentationsänderungen genügen Inhalts-, Verweis- und Änderungsprüfung. Die Windows-Prüfkonfiguration steht in `.github/workflows/tests.yml`.
- Starte den Bot und echte Spielaktionen nicht beiläufig zur Prüfung. Bereits der Import von `bot_app.py` kann ADB verbinden; lokale Startvorgaben können Spielaktionen aktivieren. Kläre vor Funktionstests Zielgerät, Auflösung, Spielsprache und die vom Auftrag gedeckten Abläufe.
- `TEST-ENVIRONMENT.bat` schreibt temporäre Dateien; `INSTALL-ENVIRONMENT.bat` installiert Pakete; `tools/sync_workflows.py` verändert Quellcode. Nutze diese Werkzeuge nur, wenn ihre Wirkung zur Aufgabe gehört.
- Berichte zum Abschluss, was geändert wurde, welche Prüfungen tatsächlich erfolgten und welche Einschränkungen oder offenen Punkte verbleiben. Simulierte Tests ersetzen keine Bestätigung des Verhaltens im echten Spiel.
