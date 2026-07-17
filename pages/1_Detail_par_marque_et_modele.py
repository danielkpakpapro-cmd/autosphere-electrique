"""
dashboard_modeles.py — Autosphere
===================================
Dashboard Streamlit détaillé : table marque/modèle avec proportion
électrique, à partir de data/historique_modeles.csv produit par
scraper_modeles.py.

USAGE
-----
    streamlit run dashboard_modeles.py
"""

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Autosphere — détail par modèle",
    page_icon="🚗",
    layout="wide",
)

CSV_PATH = "data/historique_modeles.csv"


@st.cache_data(ttl=600)
def load_data(path=CSV_PATH):
    df = pd.read_csv(path, parse_dates=["date_releve"])
    return df


st.title("🚗 Détail par marque et modèle")

try:
    df = load_data(CSV_PATH)
except FileNotFoundError:
    st.error(
        f"Fichier introuvable : `{CSV_PATH}`. "
        "Lancez d'abord `python scraper_modeles.py` pour générer les données."
    )
    st.stop()

if df.empty:
    st.warning("Le fichier de données est vide pour l'instant.")
    st.stop()

derniere_date = df["date_releve"].max()
st.caption(f"Dernier relevé : {derniere_date.strftime('%d/%m/%Y %H:%M')}")

snapshot = df[df["date_releve"] == derniere_date].copy()

col_filtre, col_case = st.columns([3, 1])

with col_filtre:
    toutes_marques = sorted(snapshot["marque"].unique())
    marques_choisies = st.multiselect(
        "Filtrer par marque", toutes_marques, placeholder="Choose options"
    )

with col_case:
    st.write("")
    st.write("")
    only_electric = st.checkbox("Uniquement modèles avec ≥1 électrique")

table = snapshot.copy()
if marques_choisies:
    table = table[table["marque"].isin(marques_choisies)]
if only_electric:
    table = table[table["nb_electrique"] >= 1]

table = table.sort_values(["marque", "nb_total"], ascending=[True, False])
table_display = table.rename(
    columns={
        "marque": "Marque",
        "modele": "Modèle",
        "nb_total": "Total",
        "nb_electrique": "Électrique",
        "proportion_electrique": "% Électrique",
    }
)[["Marque", "Modèle", "Total", "Électrique", "% Électrique"]]
table_display["% Électrique"] = table_display["% Électrique"] * 100

st.dataframe(
    table_display,
    width='stretch',
    hide_index=True,
    column_config={
        "% Électrique": st.column_config.NumberColumn(format="%.1f%%"),
    },
)

st.caption(f"{len(table_display)} ligne(s) affichée(s) sur {len(snapshot)} au total.")
