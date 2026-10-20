# Online zetten op Streamlit

Doel: het dashboard draait zonder dat een laptop aan hoeft te staan. Elke wijziging die je op GitHub zet is daarna binnen een minuut live.

## Wat je nodig hebt

- Een GitHub-account met een repository voor dit project (bijvoorbeeld `rondetijden-ihcl`)
- Een gratis account op Streamlit Community Cloud, ingelogd via GitHub
- De logo's in de map `assets` (zitten al in de repository)

## Stap 1: code op GitHub zetten

```bash
cd rondetijden-ihcl
git init
git add .
git commit -m "Eerste versie rondetijden dashboard"
git branch -M main
git remote add origin https://github.com/<jouw-account>/rondetijden-ihcl.git
git push -u origin main
```

Controleer dat `.streamlit/secrets.toml` niet is meegekomen. Die staat in `.gitignore` en hoort daar te blijven.

## Stap 2: app koppelen

1. Ga naar Streamlit Community Cloud en kies **Create app**.
2. Kies de repository en de branch `main`.
3. Vul als hoofdbestand `app.py` in.
4. Kies bij geavanceerde instellingen een recente Python-versie (3.11 of hoger).
5. Kies **Deploy**.

Streamlit installeert de pakketten uit `requirements.txt` en start de app. Daarna deployt elke push naar `main` automatisch opnieuw.

## Stap 3: toegang regelen

Op het dashboard staan namen van rijders, en een deel daarvan is minderjarig. Een openbare link is dan een keuze die het bestuur bewust moet maken.

| Optie | Voordeel | Nadeel |
|---|---|---|
| App privat maken en kijkers uitnodigen | Alleen genodigden kijken mee | Een TV langs de baan moet ingelogd zijn |
| `ACCESS_CODE` instellen in de secrets | Werkt met een gedeelde code | De code moet per sessie worden ingevoerd |
| Openbaar laten | Geen gedoe aan de baan | Iedereen met de link ziet namen en tijden |

Een toegangscode instellen:

1. Open de app in Streamlit Community Cloud en ga naar **Settings** en dan **Secrets**.
2. Plak de inhoud van `.streamlit/secrets.toml.example` en kies zelf een code.
3. Sla op. De app vraagt daarna om de code.

De zichtbaarheidsinstellingen van de app staan bij de deelopties van de app zelf. Controleer daar de actuele mogelijkheden.

## Wat te weten over Streamlit Community Cloud

- Apps die 12 uur lang niemand bezoekt gaan slapen. Een bezoeker kan de app wakker maken met de knop "Yes, get this app back up!". Een TV die tijdens trainingen openstaat houdt de app waarschijnlijk wakker.
- Pin de Streamlit-versie in `requirements.txt`. Dat staat er al. Verhoog die bewust en test eerst lokaal.
- Wijzigingen aan `requirements.txt` zorgen voor een nieuwe installatie van de pakketten.

## Lokaal testen voor je pusht

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Bronnen en Verantwoording

- Streamlit Docs. (z.d.). *Manage your app*. Geraadpleegd op 20 oktober 2026, van https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app. Gebruikt voor: slaapstand na 12 uur, wakker maken, `requirements.txt`, automatisch opnieuw installeren en het pinnen van de Streamlit-versie.
- [Afleiding] Een TV die openstaat houdt de app wakker. De bron zegt dat bezoeken de app wakker houdt.
- [Ongeverifieerd] Exacte plek en opties van de zichtbaarheidsinstelling en de keuze van de Python-versie in de deploy-schermen. De bron beschrijft dit niet. Controleer het in de interface.
- [Algemene AI-kennis] De git-commando's en de opzet van de stappen.
