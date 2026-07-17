"""
dashboard.py — Autosphere
===========================
Dashboard Streamlit principal : proportion de véhicules électriques par
marque, à partir de data/historique_marques.csv produit par scraper.py.

USAGE
-----
    streamlit run dashboard.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Autosphere — proportion électrique",
    page_icon="🔋",
    layout="wide",
)

CSV_PATH = "data/historique_marques.csv"


@st.cache_data(ttl=600)
def load_data(path=CSV_PATH):
    df = pd.read_csv(path, parse_dates=["date_releve"])
    return df


st.title("🔋 Autosphere — proportion de véhicules électriques")

try:
    df = load_data(CSV_PATH)
except FileNotFoundError:
    st.error(
        f"Fichier introuvable : `{CSV_PATH}`. "
        "Lancez d'abord `python scraper.py` pour générer les données."
    )
    st.stop()

if df.empty:
    st.warning("Le fichier de données est vide pour l'instant.")
    st.stop()

derniere_date = df["date_releve"].max()
st.caption(f"Dernier relevé : {derniere_date.strftime('%d/%m/%Y %H:%M')}")

# --- Snapshot le plus récent ---
snapshot = df[df["date_releve"] == derniere_date].copy()

col1, col2, col3 = st.columns(3)
col1.metric("Véhicules (toutes marques)", f"{snapshot['nb_total'].sum():,}".replace(",", " "))
col2.metric("Dont électriques", f"{snapshot['nb_electrique'].sum():,}".replace(",", " "))
prop_globale = (
    snapshot["nb_electrique"].sum() / snapshot["nb_total"].sum()
    if snapshot["nb_total"].sum() else 0
)
col3.metric("Proportion électrique", f"{prop_globale:.1%}")

st.divider()

# --- Bar chart par marque (snapshot le plus récent) ---
st.subheader("Proportion électrique par marque")
snapshot_sorted = snapshot.sort_values("nb_total", ascending=False)
fig_bar = px.bar(
    snapshot_sorted,
    x="marque",
    y="proportion_electrique",
    text="nb_electrique",
    labels={"marque": "Marque", "proportion_electrique": "% électrique"},
)
fig_bar.update_traces(texttemplate="%{text}", textposition="outside")
fig_bar.update_layout(yaxis_tickformat=".0%")
st.plotly_chart(fig_bar, width='stretch')

st.divider()

# --- Évolution dans le temps ---
st.subheader("Évolution dans le temps")
toutes_marques = sorted(df["marque"].unique())
default_marques = toutes_marques[: min(5, len(toutes_marques))]
marques_choisies = st.multiselect(
    "Marques à afficher (évolution)", toutes_marques, default=default_marques
)

if marques_choisies:
    df_evo = df[df["marque"].isin(marques_choisies)]
    fig_evo = px.line(
        df_evo,
        x="date_releve",
        y="proportion_electrique",
        color="marque",
        markers=True,
        labels={"date_releve": "Date", "proportion_electrique": "Proportion électrique"},
    )
    fig_evo.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig_evo, width='stretch')
else:
    st.info("Sélectionnez au moins une marque pour afficher l'évolution.")

st.divider()
st.caption("💡 Les données sont mises à jour automatiquement une fois par jour (GitHub Actions).")
