# Werking en beheer

## Wat het dashboard doet

1. Haalt de laatste 100 trainingsactiviteiten van IJshal De Vliet op uit MYLAPS Speedhive.
2. Kiest de meest recente trainingsdag (in Nederlandse tijd).
3. Haalt per rijder de sessies en rondes op, tot tien rijders tegelijk.
4. Laat rondes onder 9,0 en boven 18,0 seconden weg. Daaruit komen de laatste drie rondes, de dag beste en de snelheid.
5. Toont de rijder met de meest recente passering bovenaan.

Het scherm ververst elke 3 seconden. Alleen de tabel ververst, de kop en het logo blijven staan. De opgehaalde data wordt 3 seconden gedeeld tussen alle kijkers. Meer schermen betekent dus niet meer verzoeken aan Speedhive.

## Kleine schermen (768 bij 512 pixels)

Voor een klein scherm langs de baan is er een compacte weergave. Die toont de kop in een smalle regel met kleine logo's, de vier kaarten in een rij en de twaalf rijders met de meest recente passering. In de gewone weergave staan alle rijders van de dag. Onderaan staat in de legenda hoeveel rijders er nog meer op het ijs zijn.

- **Automatisch:** de compacte weergave gaat aan zodra het venster lager is dan 600 pixels.
- **Geforceerd:** voeg `?scherm=klein` toe aan het adres, dus `https://rondetijden-ihcl.streamlit.app/?scherm=klein`. Gebruik dit adres op het kleine scherm. Dan werkt het ook als de browser zelf ruimte inneemt, bijvoorbeeld een adresbalk.
- De bovenbalk van Streamlit is dan verborgen. Dat is bedoeld voor een scherm dat alleen meekijkt.
- Op een iPad staand (768 bij 1024) is de gewone weergave iets kleiner gezet zodat de tabel zonder zijwaarts scrollen past.

## Instellingen

Bovenin `app.py` staan de instellingen:

| Instelling | Standaard | Betekenis |
|---|---|---|
| `REFRESH_SECONDS` | 3 | Verversing van het scherm |
| `MIN_LAP_SECONDS` | 9.0 | Snellere rondes tellen niet mee |
| `MAX_LAP_SECONDS` | 18.0 | Tragere rondes tellen niet mee |
| `ONLY_LATEST_DAY` | `True` | Alleen de laatste trainingsdag tonen |
| `LOCATION_ID` | `208259692` | Locatie in Speedhive |
| `ACTIVITIES_COUNT` | 100 | Aantal activiteiten dat uit Speedhive wordt opgehaald. Bepaalt hoeveel rijders van een dag maximaal meekomen |
| `COMPACT_ROWS` | 12 | Aantal rijders in de compacte weergave voor kleine schermen |

De omgevingsvariabele `VERIFY_SSL=0` zet de certificaatcontrole uit. Gebruik dat alleen lokaal als een Mac certificaatfouten geeft.

## Verschillen met de eerste versie

- Naam is nu Rondetijden IHCL en Shorttrack Academy.
- De oneindige `while True`-lus is vervangen door een Streamlit-fragment dat zichzelf ververst. De oude lus houdt de server bezet en past slecht bij hosting.
- SSL-controle staat aan.
- Tijden worden getoond in Nederlandse tijd. Op een server in de cloud staat de klok anders op UTC en liepen de tijden twee uur achter.
- Het aantal rondes telt nu alleen rondes binnen de grenzen, zodat het past bij de dag beste.
- Een fout bij een enkele rijder wordt in de statusregel getoond in plaats van stil overgeslagen.
- Optionele toegangscode via `ACCESS_CODE`.
- Foutafhandeling: twee herhaalpogingen bij een tijdelijke fout van Speedhive, onverwachte antwoorden worden afgevangen, en bij een storing blijven de laatste gelukte gegevens zichtbaar met een melding. Een foutmelding met traceback wordt niet meer getoond.
- De kolommen Transponder en Rondes zijn weggehaald. De kaart Rondes totaal is vervangen door Laatste passering.
- Laatste Passering toont het einde van de ronde in plaats van het begin.
- PR staat alleen bij de ronde die gelijk is aan de dag beste. Sneller en langzamer wordt berekend op de gefilterde rondes. De status van Speedhive rekende ook mee met foutmetingen, waardoor bij 2 van de 10 rijders de echte beste ronde geen PR kreeg.
- Logo van IHCL links en van de Academy rechts, lichte weergave zodat de zwarte logo's leesbaar blijven. De logo's worden bij het opstarten verkleind en in de pagina ingebed.
- Compacte weergave voor schermen van 768 bij 512 pixels.
- De kolommen Passering en Rijder zijn zo smal als hun inhoud. De ruimte die dat oplevert gaat naar de tijden, die in de compacte weergave groter zijn. Een lange naam wordt afgekapt met puntjes.

## Bij storing

| Melding | Mogelijke oorzaak | Aanpak |
|---|---|---|
| Gele melding met de laatste gelukte tijd | Speedhive geeft tijdelijk een fout (bijvoorbeeld foutcode 500) | Niets doen. Het script probeert het opnieuw en toont intussen de laatste gelukte gegevens, tot 10 minuten lang |
| Speedhive geeft foutcode of onverwacht antwoord, zonder tabel | De fout duurt langer dan 10 minuten of er waren nog geen gegevens | Even wachten. Blijft het zo, controleer in de browser of de Speedhive-pagina van de locatie nog werkt |
| Wachten op doorkomsten van rijders | Niemand op het ijs of alle rondes buiten de grenzen | Controleer de grenzen van 9,0 en 18,0 seconden |
| Rijder(s) niet ververst | Time-out bij een enkele rijder | De vorige waarde blijft staan en verdwijnt bij de volgende verversing |
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
- [Geverifieerd] De compacte weergave is getest met een echte browser op 768 bij 512, 768 bij 1024 en 1440 bij 900 pixels, met nagemaakte data van 12 rijders. Er was geen horizontale scroll en de legenda bleef zichtbaar met 31 pixels marge bij twaalf rijen, ook met een naam van 27 tekens.
- [Ongeverifieerd] Hoe het eruitziet op het echte scherm. Browserbalken, schaalinstellingen van het apparaat en de afstand tot het scherm kunnen anders uitpakken.
- [Algemene AI-kennis] Werking van `st.fragment` en `st.cache_data`.
