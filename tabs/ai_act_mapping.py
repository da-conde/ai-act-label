# tabs/tab_ai_act_mapping.py  (ONLINE / Streamlit Cloud Variante)

import streamlit as st
import graphviz
import pandas as pd
from pathlib import Path


# ----------------------------------------------------
# Storage (ONLINE)
# ----------------------------------------------------
# Streamlit Cloud: nutze persistentes Volume, falls vorhanden.
# Fallback: lokales Projektverzeichnis.
try:
    _BASE_DIR = Path(st.secrets.get("STORAGE_DIR", "."))
except Exception:
    _BASE_DIR = Path(".")

DATA_DIR = _BASE_DIR / "data"
MAPPING_FILE = DATA_DIR / "ai_act_mapping.csv"


# ----------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def default_mapping_df() -> pd.DataFrame:
    """
    Default-Schema: EXACTLY ONE ROW PER CATEGORY (für Mindmap: 1 Pfeil pro Kategorie)

    Kategorien (online, v2):
      1) Data Provenance
      2) Data Composition
      3) Obtained From
      4) Data Preparation and Processing
      5) Bias and Fairness Disclosure
      6) Annahmen über den Datensatz
    """
    rows = [
        {
            "pillar": "Art. 10(2)(b)",
            "category": "Data Provenance",
            "detail": "Quelle/Herkunft des Datensatzes (inkl. direkter Vorgänger bei Derived Datasets).",
        },
        {
            "pillar": "Art. 10(2)",
            "category": "Data Composition",
            "detail": "Zusammensetzung/Typ der Daten (z. B. real-world vs. synthetic; selbst erhoben).",
        },
        {
            "pillar": "Annex IV 2(d)",
            "category": "Obtained From",
            "detail": "Wie die Daten bezogen/erhoben/selektiert wurden (z. B. Scraping, Sensor, API, Sampling).",
        },
        {
            "pillar": "Art. 10(2)(c)",
            "category": "Data Preparation and Processing",
            "detail": "Welche Verarbeitungsschritte ab Rohdaten erfolgt sind (oder explizit: keine).",
        },
        {
            "pillar": "Art. 10(2)(f)(g)",
            "category": "Bias and Fairness Disclosure",
            "detail": "Bias/Fairness/Representativität: bekannte Risiken oder durchgeführte Analysen.",
        },
        {
            "pillar": "Art. 10(2)(d)",
            "category": "Annahmen über den Datensatz",
            "detail": "Sachebene & Kontext: was die Daten darstellen/messen sollen (nicht nur technische Specs).",
        },
    ]
    return pd.DataFrame(rows, columns=["pillar", "category", "detail"])


def load_mapping_df() -> pd.DataFrame:
    """
    Lädt die Mapping-Tabelle.

    Zielzustand:
      - EXACTLY ONE ROW PER CATEGORY
      - Falls Datei fehlt oder Kategorien nicht passen -> Reset auf Default.
      - Falls Datei existiert, aber Kategorien mehrfach vorkommen -> auf 1 Row pro Kategorie reduzieren
        (erste nicht-leere Detail-Zeile wird genommen).
    """
    ensure_data_dir()

    wanted_cats = [
        "Data Provenance",
        "Data Composition",
        "Obtained From",
        "Data Preparation and Processing",
        "Bias and Fairness Disclosure",
        "Annahmen über den Datensatz",
    ]

    if MAPPING_FILE.exists():
        try:
            df = pd.read_csv(MAPPING_FILE)
        except Exception:
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()

    # Wenn leer/inkonsistent -> Default
    if df.empty or "category" not in df.columns:
        df = default_mapping_df()
        df.to_csv(MAPPING_FILE, index=False)
        return df

    # Spalten absichern
    for col in ["pillar", "category", "detail"]:
        if col not in df.columns:
            df[col] = ""

    # trim
    df = df[["pillar", "category", "detail"]].copy()
    for col in ["pillar", "category", "detail"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    present = set(df["category"].dropna().unique().tolist())
    if not set(wanted_cats).issubset(present):
        df = default_mapping_df()
        df.to_csv(MAPPING_FILE, index=False)
        return df

    # REDUKTION: genau 1 Zeile pro Kategorie
    reduced_rows = []
    for cat in wanted_cats:
        sub = df[df["category"] == cat].copy()
        sub_non_empty = sub[sub["detail"].astype(str).str.len() > 0]
        pick = sub_non_empty.iloc[0] if not sub_non_empty.empty else sub.iloc[0]
        reduced_rows.append(
            {
                "pillar": pick.get("pillar", "").strip(),
                "category": cat,
                "detail": pick.get("detail", "").strip(),
            }
        )

    df_reduced = pd.DataFrame(reduced_rows, columns=["pillar", "category", "detail"])
    df_reduced.to_csv(MAPPING_FILE, index=False)
    return df_reduced


def save_mapping_df(df: pd.DataFrame):
    """
    Speichert NUR 1 Zeile pro Kategorie (erste gewinnt), damit die Mindmap
    pro Kategorie genau einen Detail-Knoten hat.
    """
    ensure_data_dir()

    wanted_cats = [
        "Data Provenance",
        "Data Composition",
        "Obtained From",
        "Data Preparation and Processing",
        "Bias and Fairness Disclosure",
        "Annahmen über den Datensatz",
    ]

    cleaned = df.copy()
    for col in ["pillar", "category", "detail"]:
        if col not in cleaned.columns:
            cleaned[col] = ""
        cleaned[col] = cleaned[col].fillna("").astype(str).str.strip()

    cleaned = cleaned[cleaned["category"].astype(str).str.len() > 0]

    reduced_rows = []
    defaults = default_mapping_df()
    for cat in wanted_cats:
        sub = cleaned[cleaned["category"] == cat]
        if sub.empty:
            d = defaults[defaults["category"] == cat].iloc[0].to_dict()
            reduced_rows.append(d)
            continue

        sub_non_empty = sub[sub["detail"].astype(str).str.len() > 0]
        pick = sub_non_empty.iloc[0] if not sub_non_empty.empty else sub.iloc[0]
        reduced_rows.append(
            {
                "pillar": pick.get("pillar", "").strip(),
                "category": cat,
                "detail": pick.get("detail", "").strip(),
            }
        )

    out = pd.DataFrame(reduced_rows, columns=["pillar", "category", "detail"])
    out.to_csv(MAPPING_FILE, index=False)


def build_graph_from_df(df: pd.DataFrame) -> graphviz.Digraph:
    """
    Mindmap: pro Kategorie genau ein Detail-Knoten.

      AI Act
        → Kategorie (mit Pillar-Suffix)
             → Detail (1 kurzer Kasten)
    """
    dot = graphviz.Digraph(comment="AI Act Transparency Mapping")
    dot.attr(rankdir="TB")
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#F5F5F5")

    root_id = "root"
    root_label = "AI Act\n(Transparenz- & Datenpflichten)"
    dot.node(root_id, root_label)

    node_counter = 0

    def new_id():
        nonlocal node_counter
        node_counter += 1
        return f"n{node_counter}"

    df_clean = df.copy()
    for col in ["pillar", "category", "detail"]:
        df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()

    if df_clean.empty:
        return dot

    category_nodes = {}
    for _, row in df_clean.iterrows():
        cat = row["category"]
        pil = row["pillar"]
        if not cat or cat in category_nodes:
            continue
        c_id = new_id()
        suffix = f"\n({pil})" if pil else ""
        dot.node(c_id, f"{cat}{suffix}")
        dot.edge(root_id, c_id)
        category_nodes[cat] = c_id

    for _, row in df_clean.iterrows():
        cat = row["category"]
        detail = row["detail"]
        if not cat or cat not in category_nodes:
            continue
        c_id = category_nodes[cat]
        d_id = new_id()
        dot.node(d_id, detail, shape="note", fillcolor="#FFFFFF")
        dot.edge(c_id, d_id)

    return dot


# ----------------------------------------------------
# Render-Funktion
# ----------------------------------------------------

def render():
    st.subheader("📚 AI Act Mapping – Transparenzanforderungen (Online)")

    st.write(
        """
        Hier strukturierst du die **transparenzrelevanten Pflichten des AI Act**
        und leitest daraus deine operativen Kategorien ab.

        **Visualisierung:**
        *AI Act → Kategorie → 1 kurzer Detail-Kasten*

        Kategorien (online, v2):
        1. **Data Provenance**
        2. **Data Composition**
        3. **Obtained From**
        4. **Data Preparation and Processing**
        5. **Bias and Fairness Disclosure**
        6. **Annahmen über den Datensatz**
        """
    )

    df = load_mapping_df()

    st.markdown("### 🌳 Aktuelle AI Act Mindmap (1 Detail pro Kategorie)")
    try:
        dot = build_graph_from_df(df)
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Mindmap-Fehler: {e}")

    st.markdown("---")

    st.markdown("### ✏️ AI Act Mapping Tabelle bearbeiten (1 Zeile pro Kategorie)")
    st.caption(
        "Hier bearbeitest du pro Kategorie genau **eine** kurze Erklärung (Detail). "
        "Beim Speichern werden ggf. Duplikate wieder auf 1 Zeile pro Kategorie reduziert."
    )

    edited_df = st.data_editor(
        df,
        num_rows="fixed",
        use_container_width=True,
        key="ai_act_mapping_editor_one_row_per_cat_online",
    )

    if st.button("💾 Speichern & Mindmap aktualisieren", key="ai_act_mapping_save_online"):
        save_mapping_df(edited_df)
        st.success("Mapping gespeichert – Mindmap wird aktualisiert.")
        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()

    st.markdown("---")
    st.markdown("### 📖 Kleine AI-Act-Auszüge (ausführlicher)")

    with st.expander("1️⃣ Data Provenance", expanded=False):
        st.write(
            "- **Art. 10(2)(b)**: Nachvollziehbarkeit der Datenbasis (Herkunft/Quelle).\n"
            "- In eurer Logik zählt bei Derived Datasets der **direkte Vorgänger-Datensatz** als Provenance-Stufe davor."
        )

    with st.expander("2️⃣ Data Composition", expanded=False):
        st.write(
            "- Art. 10 knüpft Datenqualität an den Zweck.\n"
            "- Dafür braucht es Klarheit über **real-world vs. synthetic** (oder selbst erhoben)."
        )

    with st.expander("3️⃣ Obtained From", expanded=False):
        st.write(
            "- **Annex IV 2(d)**: Daten müssen als „**obtained and selected**“ dokumentiert sein.\n"
            "- Operationalisierung: **Wie** wurden Daten bezogen/erhoben/selektiert (Scraping, Sensor, API, Sampling)."
        )

    with st.expander("4️⃣ Data Preparation and Processing", expanded=False):
        st.write(
            "- **Art. 10(2)(c)**: Verarbeitungsschritte ab Rohdaten.\n"
            "- Erwartet: **was** gemacht wurde (oder explizit: nichts) und ggf. Abweichung vom Ausgangsdatensatz."
        )

    with st.expander("5️⃣ Bias and Fairness Disclosure", expanded=False):
        st.write(
            "- **Art. 10(2)(f)(g)**: Risiko systematischer Verzerrungen.\n"
            "- Operationalisierung: Bias/Fairness/Representativität + ggf. Analysen."
        )

    with st.expander("6️⃣ Annahmen über den Datensatz", expanded=False):
        st.write(
            "- **Art. 10(2)(d)** (eure Zuordnung): Sachebene & Kontext.\n"
            "- Operationalisierung: Was stellen die Daten dar / Ziel / intended use (nicht nur technische Specs)."
        )


def show_ai_act_mapping():
    render()