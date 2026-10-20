# Rondetijden IHCL en Shorttrack Academy

Live dashboard met rondetijden van IJshal De Vliet in Leiden, voor een TV of tablet langs de ijsbaan. De data komt uit MYLAPS Speedhive.

## Snel starten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

De logo's staan in de map `assets`: `logo_ihcl.png` links en `logo_academy.png` rechts in de kop. Zonder logobestanden werkt het dashboard ook.

## Documentatie

Alle documentatie staat in de map [`docs`](docs):

- [Online zetten op Streamlit](docs/deploy-streamlit.md): GitHub koppelen en automatisch laten draaien
- [Werking en beheer](docs/werking-en-beheer.md): wat het script doet, instellingen en wat te doen bij storing
