# Werking en beheer

## Wat het dashboard doet

1. Haalt de laatste 30 trainingsactiviteiten van IJshal De Vliet op uit MYLAPS Speedhive.
2. Kiest de meest recente trainingsdag (in Nederlandse tijd).
3. Haalt per rijder de sessies en rondes op, tot tien rijders tegelijk.
4. Laat rondes onder 9,0 en boven 18,0 seconden weg. Daaruit komen de laatste drie rondes, de dag beste, de snelheid en het aantal rondes.
5. Toont de rijder met de meest recente passering bovenaan.

Het scherm ververst elke 3 seconden. Alleen de tabel ververst, de kop en het logo blijven staan. De opgehaalde data wordt 3 seconden gedeeld tussen alle kijkers. Meer schermen betekent dus niet meer verzoeken aan Speedhive.

## Instellingen

Bovenin `app.py` staan de instellingen:

| Instelling | Standaard | Betekenis |
|---|---|---|
| `REFRESH_SECONDS` | 3 | Verversing van het scherm |
| `MIN_LAP_SECONDS` | 9.0 | Snellere rondes tellen niet mee |
| `MAX_LAP_SECONDS` | 18.0 | Tragere rondes tellen niet mee |
| `ONLY_LATEST_DAY` | `True` | Alleen de laatste trainingsdag tonen |
| `LOCATION_ID` | `208259692` | Locatie in Speedhive |

De omgevingsvariabele `VERIFY_SSL=0` zet de certificaatcontrole uit. Gebruik dat alleen lokaal als een Mac certificaatfouten geeft.

## Verschillen met de eerste versie

- Naam is nu Rondetijden IHCL en Shorttrack Academy.
- De oneindige `while True`-lus is vervangen door een Streamlit-fragment dat zichzelf ververst. De oude lus houdt de server bezet en past slecht bij hosting.
- SSL-controle staat aan.
- Tijden worden getoond in Nederlandse tijd. Op een server in de cloud staat de klok anders op UTC en liepen de tijden twee uur achter.
- Het aantal rondes telt nu alleen rondes binnen de grenzen, zodat het past bij de dag beste.
- Een fout bij een enkele rijder wordt in de statusregel getoond in plaats van stil overgeslagen.
- Optionele toegangscode via `ACCESS_CODE`.

## Bij storing

| Melding | Mogelijke oorzaak | Aanpak |
|---|---|---|
| Geen verbinding met MYLAPS Speedhive | API tijdelijk niet bereikbaar of aangepast | Even wachten. Blijft het zo, controleer in de browser of de Speedhive-pagina van de locatie nog werkt |
| Wachten op doorkomsten van rijders | Niemand op het ijs of alle rondes buiten de grenzen | Controleer de grenzen van 9,0 en 18,0 seconden |
| Rijder(s) niet opgehaald | Time-out bij een enkele rijder | Verdwijnt meestal bij de volgende verversing |
| App slaapt | 12 uur zonder bezoek | Op de knop klikken om hem wakker te maken |

## Aandachtspunten voor het bestuur

- Het dashboard gebruikt een API van Speedhive die niet als officiele publieke dienst is gedocumenteerd. Die kan zonder aankondiging veranderen. [Ongeverifieerd]
- De kolom Laatste Passering toont het starttijdstip van de laatste ronde zoals Speedhive dat levert. Controleer bij een echte training of dat overeenkomt met het moment dat de rijder over de lijn ging.
- Perspectieven: de trainer wil direct zien wie hoe rijdt, de rijder wil niet dat een slechte ronde publiek wordt uitgelicht, ouders willen weten wie de naam van hun kind ziet, en het bestuur is verantwoordelijk voor de privacy van minderjarigen. Dat spanningsveld is de reden voor de toegangsopties in `deploy-streamlit.md`.
- Risico dat onderbelicht blijft: een openbare link wordt gedeeld buiten de club. Een toegangscode of een besloten app voorkomt dat.

## Bronnen en Verantwoording

- [Logische deductie] De tijdzonefout volgt uit het gedrag van een cloudserver op UTC en het feit dat de oude code de tijdstippen zonder omrekening toonde.
- [Ongeverifieerd] Stabiliteit en gebruiksvoorwaarden van de Speedhive-API en de betekenis van `dateTimeStart`. Er is geen toegang tot de API geweest. Het script is getest met nagemaakte data.
- [Algemene AI-kennis] Werking van `st.fragment` en `st.cache_data`.
