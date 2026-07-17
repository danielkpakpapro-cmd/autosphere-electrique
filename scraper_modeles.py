"""
scraper_modeles.py — Autosphere
=================================
Version détaillée de scraper.py : au lieu de s'arrêter au total par marque,
on descend au niveau marque+modèle, pour alimenter le tableau "Détail par
marque et modèle" du dashboard (comme sur le projet Ayvens).

LOGIQUE
-------
Pour chaque marque :
  1. On applique le filtre marque dans le panneau 'Marques'.
  2. On déplie 'Voir tous les modèles' dans le panneau 'Modèles' : à ce
     stade, ce panneau n'affiche QUE les modèles de la marque filtrée,
     avec leur compte total (ex: "3008 (440)" pour Peugeot).
  3. On ajoute le filtre 'Electrique' (cumul avec la marque) et on relit
     le même panneau 'Modèles' : les comptes affichés sont maintenant
     ceux des modèles électriques uniquement.
  4. On combine les deux lectures par nom de modèle pour obtenir
     total / électrique / proportion.

⚠️ Comme pour scraper.py, les sélecteurs du panneau 'Modèles' (id
probable `model_{Nom}`) n'ont pas pu être vérifiés en conditions réelles
depuis mon environnement — testez en SCRAPER_HEADLESS=0 et signalez-moi
tout sélecteur qui ne matche pas.

USAGE
-----
    python scraper_modeles.py
    SCRAPER_HEADLESS=0 python scraper_modeles.py   -> mode visible, debug
"""

import csv
import datetime as dt
import os
import re

from playwright.sync_api import sync_playwright

SEARCH_URL = "https://www.autosphere.fr/recherche"
BRAND_PAGE_URL = "https://www.autosphere.fr/voiture-occasion/{slug}.html"

CSV_PATH = "data/historique_modeles.csv"
CSV_FIELDS = ["date_releve", "marque", "modele", "nb_total", "nb_electrique",
              "proportion_electrique"]

HEADLESS = os.environ.get("SCRAPER_HEADLESS", "1") != "0"


def _slugify_brand(brand):
    """Ex: 'Land-Rover' -> 'land-rover', 'Alfa Romeo' -> 'alfa-romeo'."""
    return brand.lower().replace(" ", "-")


def _dismiss_cookie_banner(page):
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


def _reset_and_goto_search(page):
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    _dismiss_cookie_banner(page)
    page.wait_for_timeout(500)


def _get_brand_names(page):
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

    text = page.inner_text("body")
    section = text.split("Marques", 1)[-1].split("Modèles", 1)[0]
    matches = re.findall(r"([A-Za-zÀ-ÿ\- ]+?)\s*\(([\d\s\u202f]+)\)", section)
    brands = []
    for name, _count in matches:
        name = name.strip()
        if name and name.lower() != "toutes les marques":
            brands.append(name)
    return brands


def _goto_brand_page(page, brand):
    """Va directement sur la page dédiée de la marque, comme dans
    scraper.py — évite le bug de liste virtualisée qui rendait certaines
    marques injoignables au clic dans le panneau 'Marques'."""
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


def _apply_electric_filter(page):
    """Coche 'Electrique' dans le panneau 'Énergies'. Contrairement à
    scraper.py (qui se contente de LIRE le compte facette sans cliquer),
    on a ici besoin du détail par modèle une fois réellement filtré, donc
    le clic est nécessaire. On scope la recherche à la zone qui suit le
    titre 'Énergies' pour ne pas risquer de cliquer un lien 'Electrique'
    ailleurs sur la page (bannière promo, etc.), et on re-vérifie le
    bandeau cookie juste avant de cliquer (il peut réapparaître après une
    navigation)."""
    _dismiss_cookie_banner(page)
    try:
        heading = page.get_by_text("Énergies", exact=True)
        if heading.count() > 0:
            chk = heading.first.locator(
                "xpath=following::label[contains(normalize-space(.), 'Electrique')][1]"
            )
            if chk.count() > 0:
                try:
                    chk.first.click(timeout=5000)
                except Exception:
                    _dismiss_cookie_banner(page)
                    chk.first.click(timeout=5000, force=True)
                page.wait_for_timeout(1500)
                return True

        # Si la case n'existe pas du tout : la marque n'a aucun véhicule
        # électrique dans ce contexte, ce n'est pas une erreur.
        return False
    except Exception as e:
        print(f"    [ALERTE] Impossible de cliquer sur le filtre Electrique : {e}")
        return False


def _expand_all_models(page):
    """Déplie 'Voir tous les modèles (+N)' pour avoir la liste complète
    des modèles de la marque actuellement filtrée, pas seulement les 8
    premiers affichés par défaut."""
    _dismiss_cookie_banner(page)
    try:
        voir_tous = page.get_by_text("Voir tous les modèles", exact=False)
        if voir_tous.count() > 0 and voir_tous.first.is_visible():
            try:
                voir_tous.first.click(timeout=3000)
            except Exception:
                _dismiss_cookie_banner(page)
                voir_tous.first.click(timeout=3000, force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass


def _get_model_counts(page):
    """Lit le panneau 'Modèles' (déjà filtré sur une seule marque à ce
    stade) et retourne {nom_modele: compte}."""
    _expand_all_models(page)
    text = page.inner_text("body")
    section = text.split("Modèles", 1)[-1].split("Énergies", 1)[0]
    matches = re.findall(r"([A-Za-zÀ-ÿ0-9\- ]+?)\s*\(([\d\s\u202f]+)\)", section)
    counts = {}
    for name, count in matches:
        name = name.strip()
        digits = re.sub(r"\D", "", count)
        if name and digits:
            counts[name] = int(digits)
    return counts


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
                    if not _goto_brand_page(page, brand):
                        continue
                    total_counts = _get_model_counts(page)
                    print(f"    {len(total_counts)} modèles trouvés (total).")

                    if not _apply_electric_filter(page):
                        electric_counts = {}
                    else:
                        electric_counts = _get_model_counts(page)
                    print(f"    {len(electric_counts)} modèles avec au moins 1 électrique.")
                except Exception as e:
                    print(f"    [ALERTE] Erreur inattendue sur {brand}, on passe : {e}")
                    continue

                all_models = set(total_counts) | set(electric_counts)
                for model in sorted(all_models):
                    total = total_counts.get(model, 0)
                    electric = electric_counts.get(model, 0)
                    proportion = round(electric / total, 4) if total else 0.0
                    rows.append({
                        "date_releve": now,
                        "marque": brand,
                        "modele": model,
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
    print(f"\nTerminé : {len(rows)} couples marque/modèle enregistrés.")
