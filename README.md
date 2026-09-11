# Jarvis

Jarvis ist ein lokaler Windows-Sprachassistent mit zwei getrennten
Erkennungspfaden: Ein kleines deutsches Vosk-Modell hört schnell nur auf
„Jarvis“ und Beenden-Sätze; Whisper `small` versteht danach vollständige
deutsche Fragen. Mikrofon-Audio wird ausschließlich im Arbeitsspeicher
verarbeitet und nie dauerhaft gespeichert.

Conrad (`de-DE-ConradNeural`) ist die Online-Stimme. Bei einem Ausfall bleibt
Microsoft Stefan der automatische lokale Ersatz. Wetteranfragen nutzen dauerhaft
**Berlin, 10115**.

## Installation

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts\download_whisper_model.py
python scripts\download_vosk_model.py
```

Whisper `small` benötigt etwa 462 MB und liefert die vollständige deutsche
Satz-Erkennung. Das kleine deutsche Vosk-Modell benötigt etwa 45 MB und dient
nur der schnellen Aktivierung sowie dem Abbruch. Beide Modelle liegen lokal in
`models` und werden nicht in Git aufgenommen.

## Einmalige Audioeinrichtung

```powershell
python -m jarvis --setup-audio
```

Der Befehl listet alle Mikrofone mit Nummer, Name und Kennzeichnung des
Windows-Standardmikrofons. Nach der Auswahl zeigt ein Live-Pegel, ob das
gewählte Headset-Mikrofon tatsächlich Ton empfängt. Jarvis prüft die verwendete
Sample-Rate direkt am Gerät (bevorzugt 16 kHz, falls unterstützt). Gerätenummer
und tatsächlich unterstützte Sample-Rate werden ausschließlich lokal in
`jarvis.local.json` gespeichert; diese Datei ist per `.gitignore` ausgeschlossen.
Jarvis verwendet anschließend genau dieses Mikrofon.

## Persönliches Profil

Persönliche Antworten werden ausschließlich aus der lokalen Datei
`jarvis.profile.json` im Projektordner gelesen. Sie ist per `.gitignore`
ausgeschlossen und wird nie an die Websuche oder andere Online-Dienste gesendet.
Du kannst die Werte später direkt in dieser JSON-Datei ändern; die Feldnamen
lauten `first_name`, `last_name`, `full_name`, `birth_date`, `birth_place`,
`residence` und `interests`.

## Start

```powershell
python -m jarvis --check
python -m jarvis
```

Im Wartemodus steht im Terminal `Warte auf Jarvis`. Sagen Sie einmal
**„Jarvis“**; auch „Jarwis“ und „Jervis“ werden akzeptiert. Danach folgt eine
kurze Begrüßung und Jarvis hört auf eine vollständige Frage.

Whisper wird erst nach dieser Aktivierung genau einmal pro Frage gestartet. Die
Aufnahme endet nach etwa 0,45 Sekunden echter Sprechpause und ist auf ungefähr
acht Sekunden begrenzt. Das Terminal zeigt `Erkannt:`, `Aufnahmezeit:`,
`Whisper-Verarbeitung:`, `Internetsuche:` und `Sprachausgabe:` an.

## Befehle

- Uhrzeit: „Wie spät ist es?“, „Wie viel Uhr ist es?“, „Uhrzeit“
- Datum: „Welches Datum haben wir?“, „Welcher Tag ist heute?“, „Datum“
- Speicher: „Wie viel Speicher habe ich noch?“, „Freier Speicher“, „Speicherplatz“
- Wetter: „Wie ist das Wetter heute?“, „Wetter morgen“, „Temperatur morgen“
- Hilfe: „Hilfe“ oder „Was kannst du?“
- KI-Identität: „Welches KI-Modell bist du?“, „Läufst du lokal?“ oder „Läufst du über ChatGPT?“
- Smalltalk: „Hallo“, „Wie geht es dir?“, „Danke“ oder „Was machst du?“
- Beenden: „Beenden“, „Stopp“, „Ende“, „Tschüss Jarvis“, „Auf Wiedersehen“ oder „Das war's“

Nach jeder Antwort bleibt Jarvis im Gespräch. Während Sprachwiedergabe oder
einer Internetsuche überwacht die kleine Vosk-Grammatik weiter die Beenden-Sätze.
Bei Treffer stoppt Jarvis die Ausgabe, ignoriert eine laufende Suche, verabschiedet
sich kurz und wechselt zurück zu `Warte auf Jarvis`.

Während Jarvis spricht, bleibt der zentrale Mikrofonablauf aktiv. Sobald zwei
aufeinanderfolgende kurze Audioblöcke echte Sprache erkennen, stoppt Jarvis die
alte Antwort sofort, verwirft sie und nimmt die neue Frage vollständig bis zur
Sprechpause auf. Whisper verarbeitet diese neue Frage genau einmal. Kurze
Hintergrundgeräusche werden dabei ignoriert; Beenden-Sätze stoppen das Gespräch
sofort. Das ausgewählte Headset-Mikrofon aus `--setup-audio` wird unverändert
weiterverwendet.

Unbekannte Wissensfragen werden als Text über öffentliche Quellen beantwortet:
zuerst deutschsprachige Wikipedia, danach eine kostenlose Instant-Answer-Suche.
Die Quelle erscheint im Terminal; Audio wird niemals übertragen. Internetantworten
bleiben kurz. Bei fehlender Verbindung erklärt Jarvis das ehrlich.

Normale Gespräche, Erklärungen und Fragen ohne passende lokale oder recherchierte
Antwort gehen an das lokal laufende Ollama-Modell `gemma4:latest` unter
`http://127.0.0.1:11434/api/chat`. Es wird kein API-Schlüssel verwendet und keine
andere Ollama-Adresse angesprochen. Nur wenige Gesprächsrunden bleiben während
des laufenden Prozesses im Arbeitsspeicher; beim Neustart sind sie gelöscht.
Bei Fragen nach seiner KI-Identität nennt JARVIS verlässlich das konfigurierte
Modell `gemma4:latest`, Ollama und die lokale Ausführung. Er stellt außerdem klar,
dass dafür aktuell keine OpenAI- oder ChatGPT-Cloud-API verwendet wird. Diese
Fakten stammen zentral aus `jarvis/ollama_client.py` und stehen auch im
Ollama-System-Prompt.

Die Kommandozeilenausgabe wird ausdrücklich als UTF-8 konfiguriert. Dadurch
bleiben deutsche Umlaute, `ß` und Gedankenstriche auch dann unverändert, wenn
das getrennte Dashboard JARVIS über eine Windows-Pipe beobachtet.

Zum manuellen Prüfen zuerst Ollama und das Modell starten und dann Jarvis wie
gewohnt ausführen:

```powershell
ollama run gemma4:latest
python -m jarvis
```

Nach „Jarvis“ eignen sich nacheinander etwa „Wie spät ist es?“, „Erkläre mir
Rekursion einfach“, „Kannst du dafür ein Beispiel geben?“ und „Beenden“. So
werden ein fester Befehl, Ollama, dessen kurzer Folgekontext und der unveränderte
Beenden-Befehl geprüft. Bei gestopptem Ollama meldet Jarvis den lokalen
Modellausfall kurz; Uhrzeit, Datum, Wetter und andere feste Befehle bleiben aktiv.

## Fehlerbehebung

- **Vosk-Modell fehlt:** `python scripts\download_vosk_model.py`
- **Whisper-Modell fehlt:** `python scripts\download_whisper_model.py`
- **Kein Pegel im Setup:** anderes Mikrofon wählen und dessen Berechtigung in
  Windows prüfen.
- **Conrad nicht hörbar:** Jarvis verwendet automatisch Stefan; Internet und
  Windows-Standardausgang prüfen.
- **Strg + C:** beendet Jarvis jederzeit manuell.

Temporäre MP3- und WAV-Dateien werden nach jeder Ausgabe gelöscht. Es gibt keine
API-Schlüssel und keine kostenpflichtigen Dienste.
