"""
scraper.py — Autosphere
=========================
Adaptation de la logique du scraper Ayvens pour autosphere.fr.

HISTORIQUE DES CORRECTIONS
--------------------------
v1 (clic sur la case 'Marque' dans /recherche) : les marques 'Land-Rover'
   → 'Peugeot' ne se laissaient jamais cliquer (liste virtualisée).
v2 (navigation directe sur la page dédiée de chaque marque) : corrige le
   bug ci-dessus, mais le clic sur 'Electrique' échouait encore pour les
   marques sans aucun véhicule électrique en stock — logique, le site
   n'affiche même pas la case dans ce cas, donc il n'y a rien à cliquer.
v3 (celle-ci) : on arrête de cliquer sur 'Electrique' du tout. Le panneau
   'Énergies' affiche déjà le compte à côté de chaque case (ex.
   'Electrique (117)'), exactement comme 'Marques' affiche
   'Renault (4 309)'. On lit donc ce nombre directement dans le texte de
   la page, comme pour _get_brand_names — plus robuste (aucun clic
   nécessaire) et plus rapide (un seul chargement de page par marque).

USAGE
-----
    pip install playwright pandas --break-system-packages
    playwright install chromium
    python scraper.py

    SCRAPER_HEADLESS=0 python scraper.py   -> mode visible, debug
"""

import csv
import datetime as dt
import os
import re

from playwright.sync_api import sync_playwright

SEARCH_URL = "https://www.autosphere.fr/recherche"
BRAND_PAGE_URL = "https://www.autosphere.fr/voiture-occasion/{slug}.html"

CSV_PATH = "data/historique_marques.csv"
CSV_FIELDS = ["date_releve", "marque", "nb_total", "nb_electrique",
              "proportion_electrique"]

HEADLESS = os.environ.get("SCRAPER_HEADLESS", "1") != "0"

# Repère le total annoncé, ex: "16 314 annonces de véhicules d'occasion"
TOTAL_PATTERN = re.compile(r"([\d\s\u202f]+)\s*annonces?\s+de\s+véhicules")


def _slugify_brand(brand):
    """Convertit un nom de marque en slug d'URL, ex: 'Land-Rover' ->
    'land-rover', 'Alfa Romeo' -> 'alfa-romeo'. Confirmé en observant les
    liens réels de la page d'accueil du site pour toutes les 44 marques."""
    return brand.lower().replace(" ", "-")


def _dismiss_cookie_banner(page):
    """Le site utilise Didomi pour le consentement cookies (visible dans les
    logs : #didomi-popup). On cible d'abord son bouton dédié, avec repli sur
    une recherche textuelle générique si l'ID a changé."""
    try:
        btn = page.locator("#didomi-notice-agree-button")
        if btn.count() > 0:
            btn.first.click(timeout=3000)
            page.wait_for_timeout(600)
            return True
    except Exception:
        pass

    for label in ["Tout accepter", "Accepter", "J'accepte", "Accepter tout"]:
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=2000)
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    return False


def _read_total(page):
    """Lit le nombre d'annonces affiché après application des filtres.
    Les nombres du site utilisent une espace insécable fine (\\u202f, ex:
    '2\\u202f864'), donc on retire tout ce qui n'est pas un chiffre plutôt
    que de ne remplacer que l'espace normal."""
    text = page.inner_text("body")
    m = TOTAL_PATTERN.search(text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else None


def _get_brand_names(page):
    """Récupère dynamiquement la liste des marques ET leurs comptes depuis
    le panneau de filtres 'Marques', pour ne jamais coder une liste en dur
    (comme sur Ayvens : toujours à jour même si Autosphere ajoute une
    marque). Déplie 'Voir plus de marques' si présent pour tout récupérer.
    """
    _dismiss_cookie_banner(page)
    try:
        voir_plus = page.get_by_text("Voir plus de marques", exact=False)
        if voir_plus.count() > 0 and voir_plus.first.is_visible():
            _dismiss_cookie_banner(page)  # au cas où le bandeau soit réapparu
            try:
                voir_plus.first.click(timeout=5000)
            except Exception:
                _dismiss_cookie_banner(page)
                voir_plus.first.click(timeout=5000, force=True)
            page.wait_for_timeout(500)
    except Exception as e:
        print(f"    [ALERTE] 'Voir plus de marques' n'a pas pu être déplié : {e}")
        print(f"    -> seules les marques visibles par défaut seront scrapées.")

    text = page.inner_text("body")
    # Cherche le bloc "## Marques" ... "## Modèles" et en extrait les
    # libellés du type "Renault (4 309)"
    section = text.split("Marques", 1)[-1].split("Modèles", 1)[0]
    matches = re.findall(r"([A-Za-zÀ-ÿ\- ]+?)\s*\(([\d\s]+)\)", section)
    brands = []
    for name, _count in matches:
        name = name.strip()
        if name and name.lower() != "toutes les marques":
            brands.append(name)
    return brands


def _reset_and_goto_search(page):
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    _dismiss_cookie_banner(page)
    page.wait_for_timeout(500)


def _goto_brand_page(page, brand):
    """Va directement sur la page dédiée de la marque (ex:
    /voiture-occasion/land-rover.html) plutôt que de cliquer sur la case à
    cocher dans /recherche — évite le bug de liste virtualisée qui rendait
    Land-Rover→Peugeot injoignables au clic."""
    slug = _slugify_brand(brand)
    url = BRAND_PAGE_URL.format(slug=slug)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        _dismiss_cookie_banner(page)
        page.wait_for_timeout(500)
        return True
    except Exception as e:
        print(f"    [ALERTE] Impossible de charger la page de {brand} ({url}) : {e}")
        return False


def _read_electric_count(page):
    """Lit directement le compte à côté de 'Electrique' dans le panneau
    'Énergies' (ex: 'Electrique (117)'), sans cliquer sur rien. Si la case
    n'apparaît pas du tout, c'est que la marque n'a aucun véhicule
    électrique dans le contexte actuel -> 0, et ce n'est pas une erreur."""
    text = page.inner_text("body")
    if "Énergies" not in text:
        return 0
    section = text.split("Énergies", 1)[-1].split("Localisation", 1)[0]
    m = re.search(r"Electrique\s*\(([\d\s\u202f]+)\)", section)
    if not m:
        return 0
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else 0


def scrape():
    rows = []
    now = dt.datetime.now().isoformat(timespec="seconds")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=50 if not HEADLESS else 0)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            viewport={"width": 1400, "height": 1000},
        )
        page = context.new_page()

        try:
            print("Chargement de la page de recherche pour lister les marques...")
            _reset_and_goto_search(page)
            brands = _get_brand_names(page)
            print(f"{len(brands)} marques détectées : {brands}")

            for brand in brands:
                print(f"\n=== Marque : {brand} ===")

                try:
                    # Une seule page par marque : total ET électrique se
                    # lisent tous les deux directement dans le texte, sans
                    # clic ni rechargement.
                    if not _goto_brand_page(page, brand):
                        continue
                    total = _read_total(page)
                    if total is None:
                        print(f"    [ALERTE] Total introuvable pour {brand}, on passe.")
                        continue

                    electric = _read_electric_count(page)
                    if electric > total:
                        print(f"    [ALERTE] Lecture électrique ({electric}) > total ({total}) "
                              f"pour {brand} : probable erreur de parsing, valeur plafonnée au total.")
                        electric = total
                    print(f"    Total {brand} : {total}  (dont électrique : {electric})")
                except Exception as e:
                    print(f"    [ALERTE] Erreur inattendue sur {brand}, on passe : {e}")
                    continue

                proportion = round(electric / total, 4) if total else 0.0
                rows.append({
                    "date_releve": now,
                    "marque": brand,
                    "nb_total": total,
                    "nb_electrique": electric,
                    "proportion_electrique": proportion,
                })
        finally:
            browser.close()

    return rows


def save_to_csv(rows, csv_path=CSV_PATH):
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"\n{len(rows)} lignes ajoutées à {csv_path}")


if __name__ == "__main__":
    rows = scrape()
    save_to_csv(rows)

    print("\nRésumé :")
    for r in sorted(rows, key=lambda x: -x["nb_total"]):
        print(f"  {r['marque']:15s} total={r['nb_total']:5d}  "
              f"electrique={r['nb_electrique']:4d}  "
              f"({r['proportion_electrique']:.1%})")