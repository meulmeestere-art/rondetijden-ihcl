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
- Laatste Passering toont het einde van de ronde in plaats van het begin.
- PR staat alleen bij de ronde die gelijk is aan de dag beste. Sneller en langzamer wordt berekend op de gefilterde rondes. De status van Speedhive rekende ook mee met foutmetingen, waardoor bij 2 van de 10 rijders de echte beste ronde geen PR kreeg.
- Logo van IHCL links en van de Academy rechts, lichte weergave zodat de zwarte logo's leesbaar blijven.

## Bij storing

| Melding | Mogelijke oorzaak | Aanpak |
|---|---|---|
| Geen verbinding met MYLAPS Speedhive | API tijdelijk niet bereikbaar of aangepast | Even wachten. Blijft het zo, controleer in de browser of de Speedhive-pagina van de locatie nog werkt |
| Wachten op doorkomsten van rijders | Niemand op het ijs of alle rondes buiten de grenzen | Controleer de grenzen van 9,0 en 18,0 seconden |
| Rijder(s) niet opgehaald | Time-out bij een enkele rijder | Verdwijnt meestal bij de volgende verversing |
| App slaapt | 12 uur zonder bezoek | Op de knop klikken om hem wakker te maken |

## Aandachtspunten voor het bestuur

- Het dashboard gebruikt een API van Speedhive die niet als officiele publieke dienst is gedocumenteerd. Die kan zonder aankondiging veranderen. [Ongeverifieerd]
- Speedhive levert van elke ronde het starttijdstip. De kolom Laatste Passering toont start plus rondetijd, dus het moment dat de rijder over de lijn ging. Dit is op 20 oktober 2026 gecontroleerd aan echte data: de start van een ronde valt samen met het einde van de vorige.
- Perspectieven: de trainer wil direct zien wie hoe rijdt, de rijder wil niet dat een slechte ronde publiek wordt uitgelicht, ouders willen weten wie de naam van hun kind ziet, en het bestuur is verantwoordelijk voor de privacy van minderjarigen. Dat spanningsveld is de reden voor de toegangsopties in `deploy-streamlit.md`.
- Risico dat onderbelicht blijft: een openbare link wordt gedeeld buiten de club. Een toegangscode of een besloten app voorkomt dat.

## Bronnen en Verantwoording

- [Logische deductie] De tijdzonefout volgt uit het gedrag van een cloudserver op UTC en het feit dat de oude code de tijdstippen zonder omrekening toonde.
- [Geverifieerd] Veldnamen en de betekenis van `dateTimeStart` zijn op 20 oktober 2026 gecontroleerd via een aanroep vanuit de browser op sporthive.com. Een directe aanroep zonder `Origin` en `Referer` geeft HTTP 401, daarom stuurt het script die headers mee.
- [Ongeverifieerd] Stabiliteit en gebruiksvoorwaarden van de Speedhive-API.
- [Algemene AI-kennis] Werking van `st.fragment` en `st.cache_data`.
