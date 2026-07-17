# Autosphere — suivi de la proportion de véhicules électriques

Scrape le catalogue de voitures d'occasion [autosphere.fr](https://www.autosphere.fr)
et suit dans le temps la proportion de véhicules électriques, par marque et
par modèle.

## Structure du projet

```
autosphere/
├── .github/workflows/scrape.yml   # scraping automatique quotidien
├── data/
│   ├── historique_marques.csv     # historique par marque (scraper.py)
│   └── historique_modeles.csv     # historique par marque+modèle (scraper_modeles.py)
├── scraper.py                     # scrape le total / électrique par marque
├── scraper_modeles.py             # scrape le total / électrique par marque+modèle
├── dashboard.py                   # dashboard Streamlit — vue par marque
├── dashboard_modeles.py           # dashboard Streamlit — détail par modèle
├── requirements.txt               # dépendances du dashboard
└── requirements-scraping.txt      # dépendances du scraping (Playwright)
```

## Comment ça marche

Le site autosphere.fr affiche, dans son panneau de filtres, le nombre
d'annonces correspondant à chaque combinaison de filtres cochés (ex:
`Renault` seul → 4 309 véhicules ; `Renault` + `Electrique` → un sous-total).
Plutôt que de parcourir les milliers de fiches une par une, les scripts
appliquent ces filtres et lisent directement ce total affiché.

- `scraper.py` : pour chaque marque, lit le total et le total électrique →
  `data/historique_marques.csv`.
- `scraper_modeles.py` : pour chaque marque, déplie la liste complète des
  modèles et lit le total / électrique de chacun → `data/historique_modeles.csv`.

Chaque exécution **ajoute** une ligne par marque (ou par modèle) avec la date
du relevé, ce qui permet de suivre l'évolution dans le temps.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows

pip install -r requirements-scraping.txt
playwright install chromium
```

## Lancer le scraping

```bash
python scraper.py
python scraper_modeles.py

# Mode visible pour déboguer un sélecteur :
SCRAPER_HEADLESS=0 python scraper.py
```

## Lancer les dashboards

```bash
pip install -r requirements.txt
streamlit run dashboard.py
streamlit run dashboard_modeles.py
```

## Automatisation

Le workflow `.github/workflows/scrape.yml` relance les deux scrapers tous
les jours à 9h UTC et committe les nouvelles lignes dans `data/`. Il peut
aussi être déclenché manuellement depuis l'onglet Actions du dépôt.

## ⚠️ Points à vérifier

Certains sélecteurs (panneau "Modèles", format exact des identifiants de
case à cocher) ont été déduits de l'inspection du site plutôt que d'un
test interactif complet. En cas d'erreur, relancez avec
`SCRAPER_HEADLESS=0` pour observer ce qui bloque.