import streamlit as st
import graphviz
import pandas as pd


# ----------------------------------------------------
# Hardcodiertes Mapping (4 Kategorien + "formale" Erklärung)
# ----------------------------------------------------

def get_mapping_df() -> pd.DataFrame:
    """
    Liefert das feste Schema mit GENAU den vier Kernkategorien:
      1) Data Provenance (Origin)
      2) Data Composition (Real vs. Synthetic)
      3) Data Preparation & Processing
      4) Bias & Fairness Disclosure

    'detail' enthält eine eher formale Beschreibung (oben im Text genutzt),
    wird aber NICHT mehr für die Mindmap verwendet.
    """
    rows = [
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Data Provenance (Origin)",
            "detail": (
                "Beschreibt die Herkunft der Daten: Wie, wo und durch wen sie erhoben wurden, "
                "welche Quellen genutzt wurden und unter welchen Bedingungen die Datenerfassung stattfand."
            ),
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Data Composition (Real vs. Synthetic)",
            "detail": (
                "Gibt an, ob der Datensatz aus realweltlichen Beobachtungen, synthetisch generierten Daten "
                "oder einer Kombination beider besteht – einschließlich Hinweise auf generative Verfahren "
                "oder künstliche Ergänzungen."
            ),
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Data Preparation & Processing",
            "detail": (
                "Dokumentiert alle Schritte der Datenaufbereitung, z. B. Cleaning, Filtering, Normalisierung, "
                "Labeling, Splits oder andere Transformationen, die die Datenform oder -qualität beeinflussen."
            ),
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Bias & Fairness Disclosure",
            "detail": (
                "Beschreibt potenzielle Verzerrungen, Repräsentationsprobleme oder fairness-relevante Risiken "
                "im Datensatz sowie Maßnahmen, die zur Identifikation, Bewertung oder Mitigation von Bias "
                "ergriffen wurden."
            ),
        },
    ]
    return pd.DataFrame(rows, columns=["pillar", "category", "detail"])


# ----------------------------------------------------
# Graphviz-Mindmap (nur 2 Ebenen)
# ----------------------------------------------------

def build_two_level_graph(df: pd.DataFrame) -> graphviz.Digraph:
    """
    Mindmap-Struktur (2 Ebenen):

      AI Act
        → Kategorie (4 Kern-Kategorien)

    'pillar' wird nur zur Info in der Beschriftung genutzt.
    Es gibt KEINE Detail-Knoten mehr.
    """
    dot = graphviz.Digraph(comment="AI Act Transparency Mapping – 2-Level")
    dot.attr(rankdir="TB")
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#F5F5F5")

    # Root Node
    root_id = "root"
    root_label = "AI Act\n(Transparenz- & Datenpflichten)"
    dot.node(root_id, root_label)

    node_counter = 0

    def new_id():
        nonlocal node_counter
        node_counter += 1
        return f"n{node_counter}"

    # DataFrame bereinigen
    df_clean = df.copy()
    for col in ["pillar", "category"]:
        df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()

    # Nur Zeilen mit Kategorie
    df_clean = df_clean[df_clean["category"] != ""]
    if df_clean.empty:
        return dot  # nur Root

    # Kategorie → Pillars (nur für Anzeige)
    cat_to_pillars = {}
    for _, row in df_clean.iterrows():
        cat = row["category"]
        pil = row["pillar"]
        if not cat:
            continue
        cat_to_pillars.setdefault(cat, set())
        if pil:
            cat_to_pillars[cat].add(pil)

    # Kategorie-Knoten direkt unter AI Act
    for cat, pillar_set in cat_to_pillars.items():
        c_id = new_id()
        pillar_suffix = ""
        if pillar_set:
            first_pillar = list(pillar_set)[0]
            pillar_suffix = f"\n({first_pillar})"
        label = f"{cat}{pillar_suffix}"
        dot.node(c_id, label)
        dot.edge(root_id, c_id)

    return dot


# ----------------------------------------------------
# Einfache Anleitungs-Texte für das Labeling
# (für Readmes / Dataset-Beschreibungen)
# ----------------------------------------------------

def get_simple_guidance() -> dict:
    """
    Sehr einfache, kurze Erklärungen für Labeler:innen –
    direkt darauf ausgerichtet, was in README / Datensatzbeschreibung
    gesucht werden soll.
    """
    return {
        "Data Provenance (Origin)": (
            "Schau nach, ob beschrieben wird, **woher** die Daten kommen.\n\n"
            "- Werden Datenquellen genannt (z. B. Sensoren, Nutzer:innen, Logs, Web-Scraping)?\n"
            "- Wird erklärt, wie die Daten erhoben wurden (z. B. Studie, Umfrage, Plattform)?\n"
            "- Ziel: Man versteht grob, aus welchem Kontext die Daten stammen."
        ),
        "Data Composition (Real vs. Synthetic)": (
            "Prüfe, ob erwähnt wird, ob die Daten **real**, **synthetisch** oder eine Mischung sind.\n\n"
            "- Steht irgendwo, dass Daten generiert, simuliert oder synthetisch erstellt wurden?\n"
            "- Oder wird klar gesagt, dass es echte Beobachtungsdaten sind?\n"
            "- Ziel: Klarheit darüber, ob wir es mit Real-World-Daten, Synthetic Data oder einem Mix zu tun haben."
        ),
        "Data Preparation & Processing": (
            "Achte darauf, ob Aufbereitungsschritte beschrieben werden.\n\n"
            "- Werden Schritte wie Cleaning, Filtering, Aggregation, Anonymisierung, Normalisierung genannt?\n"
            "- Gibt es Infos zu Train/Dev/Test-Splits oder Labeling-Prozessen?\n"
            "- Ziel: Man bekommt ein Gefühl, was mit den Rohdaten gemacht wurde, bevor sie im Datensatz gelandet sind."
        ),
        "Bias & Fairness Disclosure": (
            "Suche nach Hinweisen auf mögliche Verzerrungen oder Fairness-Themen.\n\n"
            "- Werden Limitierungen der Repräsentativität erwähnt (z. B. bestimmte Gruppen fehlen)?\n"
            "- Gibt es Aussagen zu Bias, Fairness-Analysen oder bekannten Schwächen des Datensatzes?\n"
            "- Ziel: Transparenz darüber, wo der Datensatz unfair, unvollständig oder potenziell problematisch sein könnte."
        ),
    }


# ----------------------------------------------------
# Render-Funktion
# ----------------------------------------------------

def render():
    st.subheader("📚 AI Act Mapping – Transparenzanforderungen")

    st.write(
        """
        Hier definierst du deine **operativen Transparenz-Kategorien** für die Analyse von Datensätzen
        im Lichte von **Art. 10 AI Act**.  
        
        Wir arbeiten mit vier festen Kernkategorien, die später im Labeling für README- und
        Datensatzbeschreibungen verwendet werden:

        1. **Data Provenance (Origin)**  
           Beschreibt die Herkunft der Daten: Wie, wo und durch wen sie erhoben wurden,
           welche Quellen genutzt wurden und unter welchen Bedingungen die Datenerfassung stattfand.

        2. **Data Composition (Real vs. Synthetic)**  
           Gibt an, ob der Datensatz aus realweltlichen Beobachtungen, synthetisch generierten Daten
           oder einer Kombination beider besteht – einschließlich Hinweise auf generative Verfahren
           oder künstliche Ergänzungen.

        3. **Data Preparation & Processing**  
           Dokumentiert alle Schritte der Datenaufbereitung, z. B. Cleaning, Filtering, Normalisierung,
           Labeling, Splits oder andere Transformationen, die die Datenform oder -qualität beeinflussen.

        4. **Bias & Fairness Disclosure**  
           Beschreibt potenzielle Verzerrungen, Repräsentationsprobleme oder fairness-relevante Risiken
           im Datensatz sowie Maßnahmen, die zur Identifikation, Bewertung oder Mitigation von Bias
           ergriffen wurden.
        """
    )

    # Mindmap (2 Ebenen)
    df = get_mapping_df()

    st.markdown("### 🌳 AI Act Mindmap (2 Ebenen)")
    try:
        dot = build_two_level_graph(df)
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Mindmap-Fehler: {e}")

    st.markdown("---")

    # Anleitung / Erklärung für das Labeling
    st.markdown("### 📝 Anleitung für das Labeling von Readmes & Dataset-Beschreibungen")

    st.write(
        """
        Unten findest du für jede Kategorie eine kurze, praktische Erklärung,  
        **worum es beim Labeling geht** und **wonach du im Text suchen sollst**.
        """
    )

    simple_guidance = get_simple_guidance()

    for cat, text in simple_guidance.items():
        with st.expander(cat, expanded=False):
            st.write(text)