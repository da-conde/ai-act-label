import streamlit as st
import graphviz
import pandas as pd


# ----------------------------------------------------
# Hardcodiertes Mapping (4 Kategorien + Erklärung)
# ----------------------------------------------------

def get_mapping_df() -> pd.DataFrame:
    """
    Liefert das feste Schema mit GENAU den vier Kernkategorien:
      1) Data Provenance (Origin)
      2) Data Composition (Real vs. Synthetic)
      3) Data Preparation & Processing
      4) Bias & Fairness Disclosure

    'detail' enthält jeweils den erklärenden Untertitel.
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
# Graphviz-Mindmap
# ----------------------------------------------------

def build_graph_from_df(df: pd.DataFrame) -> graphviz.Digraph:
    """
    Mindmap-Struktur:

      AI Act
        → Kategorie (4 Kern-Kategorien)
             → Detail (konkret labelbarer Aspekt)

    'pillar' wird nur als Info in der Kategorie-Beschriftung genutzt.
    """
    dot = graphviz.Digraph(comment="AI Act Transparency Mapping")
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
    for col in ["pillar", "category", "detail"]:
        df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()

    # Nur Zeilen mit mindestens einer Info
    df_clean = df_clean[
        df_clean[["pillar", "category", "detail"]].apply(
            lambda row: any(len(str(v)) > 0 for v in row), axis=1
        )
    ]

    if df_clean.empty:
        return dot  # dann bleibt nur der Root-Knoten

    # Kategorie → zugehörige Pillars
    cat_to_pillars = {}
    for _, row in df_clean.iterrows():
        cat = row["category"]
        pil = row["pillar"]
        if not cat:
            continue
        cat_to_pillars.setdefault(cat, set())
        if pil:
            cat_to_pillars[cat].add(pil)

    # 1) Kategorie-Knoten direkt unter AI Act
    category_nodes = {}
    for cat, pillar_set in cat_to_pillars.items():
        c_id = new_id()
        pillar_suffix = ""
        if pillar_set:
            first_pillar = list(pillar_set)[0]
            pillar_suffix = f"\n({first_pillar})"
        label = f"{cat}{pillar_suffix}"
        dot.node(c_id, label)
        dot.edge(root_id, c_id)
        category_nodes[cat] = c_id

    # 2) Detail-Knoten
    for _, row in df_clean.iterrows():
        cat = row["category"]
        detail = row["detail"]
        if not cat or not detail:
            continue
        c_id = category_nodes.get(cat)
        if not c_id:
            continue
        d_id = new_id()
        dot.node(d_id, detail, shape="note", fillcolor="#FFFFFF")
        dot.edge(c_id, d_id)

    return dot


# ----------------------------------------------------
# Render-Funktion
# ----------------------------------------------------

def render():
    st.subheader("📚 AI Act Mapping – Transparenzanforderungen")

    st.write(
        """
        Hier definierst du deine **operativen Transparenz-Kategorien** für die Analyse von Datensätzen
        im Lichte von **Art. 10 AI Act**.  
        
        Wir arbeiten mit vier festen Kernkategorien, die später im Labeling verwendet werden:

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

    # Mindmap aus dem hardcodierten Mapping
    df = get_mapping_df()

    st.markdown("### 🌳 AI Act Mindmap (4 Kern-Kategorien)")
    try:
        dot = build_graph_from_df(df)
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Mindmap-Fehler: {e}")