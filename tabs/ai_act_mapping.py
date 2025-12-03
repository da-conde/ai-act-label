import streamlit as st
import graphviz
import pandas as pd

from utils.gdrive import load_csv_from_drive, save_csv_to_drive


# ----------------------------------------------------
# Google Drive Konfiguration
# ----------------------------------------------------

# File-ID deiner ai_act_mapping.csv auf Google Drive
AI_ACT_MAPPING_DRIVE_FILE_ID = "1pjoV4AnJxxIy3nK4fG1htB3mcvqWk0Qp"


# ----------------------------------------------------
# Hilfsfunktionen: Default-Schema
# ----------------------------------------------------

def default_mapping_df() -> pd.DataFrame:
    """
    Liefert das neue, feste Default-Schema mit GENAU den vier Kernkategorien:
      - Data Source / Provenance
      - Synthetic Data Disclosure
      - Fairness / Bias Disclosure
      - Limitations & Suitability
    """
    rows = [
        # 1) Data Source / Provenance
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Data Source / Provenance",
            "detail": "Herkunft / Erzeugung der Trainingsdaten (z. B. Logs, Sensoren, Web-Scraping).",
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Data Source / Provenance",
            "detail": "Dokumentation der Datenerhebungsprozesse und Vorverarbeitungsschritte.",
        },

        # 2) Synthetic Data Disclosure
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Synthetic Data Disclosure",
            "detail": "Offenlegung, ob und wo synthetische Daten im Trainingsdatensatz verwendet werden.",
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Synthetic Data Disclosure",
            "detail": "Begründung, warum synthetische Daten eingesetzt werden (z. B. Privacy, Class-Balancing).",
        },

        # 3) Fairness / Bias Disclosure
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Fairness / Bias Disclosure",
            "detail": "Hinweise auf bekannte Verzerrungen oder eingeschränkte Repräsentativität des Datensatzes.",
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Fairness / Bias Disclosure",
            "detail": "Beschreibung von Bias-Analysen oder Fairness-Evaluierungen.",
        },

        # 4) Limitations & Suitability
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Limitations & Suitability",
            "detail": "Angaben zu intended / non-intended use und Grenzen der Datennutzung.",
        },
        {
            "pillar": "Art. 10 – Data Governance & Data Quality",
            "category": "Limitations & Suitability",
            "detail": "Warnhinweise zu möglichen Fehlinterpretationen oder Missbrauch des Datensatzes.",
        },
    ]
    return pd.DataFrame(rows, columns=["pillar", "category", "detail"])


# ----------------------------------------------------
# Hilfsfunktionen: Laden / Speichern über Google Drive
# ----------------------------------------------------

def load_mapping_df() -> pd.DataFrame:
    """
    Lädt die Mapping-Tabelle von Google Drive.
    Falls die Datei fehlt, leer ist oder nicht das erwartete Schema enthält,
    wird das Default-Schema erzeugt und wieder nach Drive geschrieben.
    """
    wanted_cats = {
        "Data Source / Provenance",
        "Synthetic Data Disclosure",
        "Fairness / Bias Disclosure",
        "Limitations & Suitability",
    }

    # 1) Versuchen, CSV von Google Drive zu laden
    try:
        df = load_csv_from_drive(AI_ACT_MAPPING_DRIVE_FILE_ID)
    except Exception as e:
        st.error(f"Fehler beim Laden der AI Act Mapping CSV von Google Drive: {e}")
        df = pd.DataFrame()

    # 2) Prüfen, ob die Datei brauchbar ist
    if (
        df.empty
        or "category" not in df.columns
        or not set(df["category"].dropna().unique()).issuperset(wanted_cats)
    ):
        # → auf das neue Schema umstellen
        df = default_mapping_df()
        try:
            save_csv_to_drive(df, AI_ACT_MAPPING_DRIVE_FILE_ID)
            st.info("AI Act Mapping CSV auf Google Drive wurde auf das Default-Schema zurückgesetzt.")
        except Exception as e:
            st.error(f"Fehler beim Speichern des Default-Mappings nach Google Drive: {e}")

    # 3) Sicherstellen, dass alle benötigten Spalten da sind
    for col in ["pillar", "category", "detail"]:
        if col not in df.columns:
            df[col] = ""

    df = df[["pillar", "category", "detail"]]

    return df


def save_mapping_df(df: pd.DataFrame):
    """
    Speichert das Mapping-DataFrame zurück nach Google Drive.
    """
    try:
        save_csv_to_drive(df, AI_ACT_MAPPING_DRIVE_FILE_ID)
    except Exception as e:
        st.error(f"Fehler beim Speichern der AI Act Mapping CSV nach Google Drive: {e}")


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
        Hier strukturierst du die **transparenzrelevanten Pflichten des AI Act** 
        und leitest daraus deine operativen Kategorien ab.

        **Visualisierung:**  
        *AI Act → Kategorie → Detail*

        Derzeit sind fest hinterlegt (kannst du unten aber erweitern/ändern):

        1. **Data Source / Provenance**  
        2. **Synthetic Data Disclosure**  
        3. **Fairness / Bias Disclosure**  
        4. **Limitations & Suitability**
        """
    )

    # 1) Mapping laden (inkl. ggf. Reset auf Default-Schema)
    df = load_mapping_df()

    # 2) Mindmap anzeigen
    st.markdown("### 🌳 Aktuelle AI Act Mindmap (4 Kern-Kategorien)")
    try:
        dot = build_graph_from_df(df)
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Mindmap-Fehler: {e}")

    st.markdown("---")

    # 3) Editor für die Tabelle
    st.markdown("### ✏️ AI Act Mapping Tabelle bearbeiten")

    st.caption(
        "Du kannst Pillars (Art. 10 etc.), Kategorien und Details anpassen oder neue Zeilen hinzufügen. "
        "Die vier Kern-Kategorien sind das Start-Setup."
    )

    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        key="ai_act_mapping_editor_four_core_cats",
    )

    if st.button("💾 Speichern & Mindmap aktualisieren"):
        cleaned = edited_df.copy()
        for col in ["pillar", "category", "detail"]:
            cleaned[col] = cleaned[col].fillna("").astype(str).str.strip()

        cleaned = cleaned[
            cleaned[["pillar", "category", "detail"]].apply(
                lambda row: any(len(str(v)) > 0 for v in row), axis=1
            )
        ]

        save_mapping_df(cleaned)
        st.success("Mapping gespeichert – Mindmap wird aktualisiert.")

        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()

    st.markdown("---")

    # 4) Kleine AI-Act-Auszüge zu den 4 Kategorien
    st.markdown("### 📖 Kleine AI-Act-Auszüge zu den 4 Kern-Kategorien")

    with st.expander("1️⃣ Data Source / Provenance"):
        st.write(
            "- Art. 10(2) verlangt Transparenz über Herkunft & Erhebung der Trainingsdaten.\n"
            "  ⇒ Operationalisiert als *Data Source / Provenance*."
        )

    with st.expander("2️⃣ Synthetic Data Disclosure"):
        st.write(
            "- Art. 10(5) erwähnt synthetische Daten direkt.\n"
            "  ⇒ Offenlegung erforderlich (*Synthetic Data Disclosure*)."
        )

    with st.expander("3️⃣ Fairness / Bias Disclosure"):
        st.write(
            "- Art. 10(2) knüpft Datenqualität an Fairness.\n"
            "  ⇒ Dokumentation von Bias & Fairness-Analysen."
        )

    with st.expander("4️⃣ Limitations & Suitability"):
        st.write(
            "- Art. 10(3) / 10(5): Zweckgebundenheit + Grenzen der Eignung.\n"
            "  ⇒ Transparenz über intended / non-intended use."
        )