# tabs/tab_ai_act_mapping.py  (ONLINE / Streamlit Cloud Variante – basiert auf deinem lokalen Code)

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

    # Check: sind alle benötigten Kategorien vorhanden?
    present = set(df["category"].dropna().unique().tolist())
    if not set(wanted_cats).issubset(present):
        df = default_mapping_df()
        df.to_csv(MAPPING_FILE, index=False)
        return df

    # REDUKTION: genau 1 Zeile pro Kategorie (erste sinnvolle Zeile gewinnt)
    reduced_rows = []
    for cat in wanted_cats:
        sub = df[df["category"] == cat].copy()

        # Priorität: Zeilen mit Detail > 0 Zeichen, sonst irgendwas
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

    # Datei aktualisieren (damit Mindmap künftig stabil 1 Pfeil/Kategorie ist)
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

    # nur Zeilen, die mindestens category haben
    cleaned = cleaned[cleaned["category"].astype(str).str.len() > 0]

    # genau 1 Zeile pro wanted category, in fester Reihenfolge
    reduced_rows = []
    for cat in wanted_cats:
        sub = cleaned[cleaned["category"] == cat]
        if sub.empty:
            # falls Nutzer Kategorie gelöscht hat -> Default-Zeile wieder herstellen
            default_row = default_mapping_df()
            d = default_row[default_row["category"] == cat].iloc[0].to_dict()
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

    # 1) Kategorie-Knoten
    category_nodes = {}
    for _, row in df_clean.iterrows():
        cat = row["category"]
        pil = row["pillar"]
        if not cat:
            continue
        if cat in category_nodes:
            continue  # Sicherheit: keine Duplikate im Graph
        c_id = new_id()
        suffix = f"\n({pil})" if pil else ""
        dot.node(c_id, f"{cat}{suffix}")
        dot.edge(root_id, c_id)
        category_nodes[cat] = c_id

    # 2) Genau EIN Detail-Knoten pro Kategorie
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

    # 1) Mapping laden (inkl. Reduktion auf 1 Row/Kategorie)
    df = load_mapping_df()

    # 2) Mindmap anzeigen
    st.markdown("### 🌳 Aktuelle AI Act Mindmap (1 Detail pro Kategorie)")
    try:
        dot = build_graph_from_df(df)
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Mindmap-Fehler: {e}")

    st.markdown("---")

    # 3) Editor: exakt 6 Zeilen (1 pro Kategorie) anzeigen/bearbeiten
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

    # 4) Kategorie-Guide (ausführlicher, wie im Online-Tab)
    st.markdown("### 📖 Kategorie-Guide für Labeling (ausführlicher)")

    st.caption(
        "Ziel: Die folgenden Hinweise erklären **was** die Kategorie abdeckt, **wie** die Labels zu vergeben sind "
        "(✅ ausreichend / ❓ unklar / ❌ unzureichend) und geben **Mini-Beispiele**. "
        "Die Icons entsprechen dem Selector in den Labeling-Tabs."
    )

    # ✅ NUR DIESER EXPANDER IST ANGEPASST (Data Provenance wie von dir beschrieben)
    with st.expander("1️⃣ Data Provenance (Art. 10(2)(b))", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
Nachvollziehbare **Herkunft/Quelle** der Daten: *Von wem / aus welcher Quelle stammen sie?*  
Wichtig: Es reicht **nicht**, einfach nur einen Datensatz **zu nennen** (z. B. *„based on the EDALT dataset“*).  
Auch ein berühmter Datensatz hat wiederum eine **eigene Quelle** – und genau diese Herkunft/Urheberschaft muss erkennbar sein.  
Bei abgeleiteten Datensätzen (Derived Datasets) zählt in eurer Logik insbesondere der **direkte Vorgänger-Datensatz** als Provenance-Stufe davor.

**✅ Ausreichend**  
- Die Herkunft/Quelle ist **explizit** genannt und die **Urheberschaft erkennbar** (wer hat die Daten erzeugt/erhoben/gesammelt?).  
- Eigene Urheberschaft wird klar benannt (*„wir haben … gesammelt/gescraped/erhoben“*).

**❓ Unklar**  
- Herkunft ist **angedeutet**, aber ohne Kontext nicht zweifelsfrei.  
  Beispiele: *„scraped from Wikipedia“*, *„sensor data“* (wer/wo/wie genau?).  
- Dazu zählt auch: Es wird **nur ein Link** genannt (z. B. zu einem Repository), ohne im Text klar zu machen, **was** dort genau die Quelle ist  
  bzw. ohne eindeutige Provenance-Aussage (Link allein ist nicht automatisch „explizite Herkunft“).

**❌ Unzureichend**  
- **Keine** Angabe zur Herkunft/Quelle.  
- Oder es steht **nur der Name** eines Datensatzes, auf den Bezug genommen wird (z. B. *„EDALT dataset“*),  
  aber man weiß danach immer noch nicht **woher** die Daten kommen oder **wie** man sie konkret findet/zuordnet.

**Mini-Beispiele**  
- ✅ *„We scraped Wikipedia pages between 2022–2023 …“*  
- ✅ *„Data was collected by our lab at … (institution) …“*  
- ❓ *„Wikipedia dataset“* / *„Sensor logs“* (ohne Betreiber/Setup)  
- ❓ *„See repository: <link>“* (nur Link, keine klare Provenance-Aussage)  
- ❌ *„Based on the EDALT dataset“* (nur Name, keine Quelle/Herkunft)  
- ❌ README ohne Herkunftsangaben
"""
        )

    # باقي Expander bleiben inhaltlich wie gehabt
    with st.expander("2️⃣ Data Composition (Art. 10(2))", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
Klarheit über den **Typ / die Zusammensetzung** der Daten – besonders wichtig für Datenqualität im Sinne von Art. 10:  
Sind es **Real-world** Daten, **Synthetic** Daten, oder **selbst erhobene** Daten?

**✅ Ausreichend**  
- Explizite Benennung wie: *„real-world“*, *„synthetic“* oder *„collected by us“ / „self-collected“*.

**❌ Unzureichend**  
- Keine (oder nur implizite) Information, ob real/synthetisch/selbst erhoben.

**Mini-Beispiele**  
- ✅ *„This dataset contains synthetic tabular records generated with …“*  
- ✅ *„We collected the data via surveys …“*  
- ❌ Nur technische Specs, aber kein Hinweis auf real vs. synthetic
"""
        )

    with st.expander("3️⃣ Obtained From (Annex IV 2(d) – „obtained and selected“)", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
**Wie** wurden die Daten **bezogen/erhoben/selektiert**? (Mechanismus/Quelle des Bezugs)  
Das ist nahe an Provenance, aber mit Fokus auf den **Beschaffungs-/Erhebungsweg** (Scraping, API, Sensor, Sampling, …).

**✅ Ausreichend**  
- Es wird benannt, **wie** die Daten bezogen wurden.  
  Beispiele: *„scraped from …“*, *„collected via API“*, *„measured with sensor …“*, *„sampled from …“*.

**❌ Unzureichend**  
- Keine Angabe zum Erhebungs-/Bezugsweg.

**Mini-Beispiele**  
- ✅ *„Collected via Twitter API (v2) using keywords …“*  
- ✅ *„Scraped from Wikipedia using …“*  
- ❌ *„Data from the web“* (zu vage, kein Mechanismus)
"""
        )

    with st.expander("4️⃣ Data Preparation and Processing (Art. 10(2)(c))", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
Alle **Verarbeitungsschritte ab Existenz der Rohdaten**: Cleaning, Filtering, Normalisierung, Deduplication, Labeling, etc.  
Wichtig ist nicht nur „dass“ etwas gemacht wurde, sondern **wie** – und **wie sich der resultierende Datensatz** vom Ausgangsdatensatz unterscheidet.

**✅ Ausreichend**  
- Konkrete Beschreibung der Verarbeitung **und/oder** der resultierenden Unterschiede zum Ausgangsdatensatz.  
- Oder explizit: *„no preprocessing was applied“*.

**❓ Unklar**  
- Verarbeitung wird nur als Schlagwort genannt, ohne Qualifizierung/Methode/Konfiguration.  
  Beispiel: *„outlier treatment“* ohne Methode (z. B. Tukey fences) und ohne Parameter.

**❌ Unzureichend**  
- Keine Angabe.

**Mini-Beispiele**  
- ✅ *„We removed duplicates by hashing rows; dropped records with missing target; normalized features with z-score …“*  
- ✅ *„No preprocessing was performed.“*  
- ❓ *„Data was cleaned and outliers were treated.“*  
- ❌ Keine Processing-Infos
"""
        )

    with st.expander("5️⃣ Bias and Fairness Disclosure (Art. 10(2)(f)(g))", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
Angaben zu **Bias**, **Fairness**, **Repräsentativität** und bekannten Verzerrungsrisiken – oder Hinweise auf entsprechende Analysen.

**✅ Ausreichend**  
- Benennung von Bias-/Fairness-relevanten Informationen (z. B. bekannte Verzerrungen, Unterrepräsentation, Sampling-Bias)  
  und/oder kurze Ergebnisse/Checks.

**❌ Unzureichend**  
- Keine Angabe (keine Hinweise auf Bias/Fairness/Representativität).

**Mini-Beispiele**  
- ✅ *„The dataset underrepresents age group 65+; results may not generalize.“*  
- ✅ *„We checked class imbalance and report distribution by gender/region …“*  
- ❌ Keine Bias-/Fairness-Infos
"""
        )

    with st.expander("6️⃣ Annahmen über den Datensatz (Art. 10(2)(d))", expanded=False):
        st.markdown(
            """
**Worum geht’s?**  
Beschreibung auf **Sachebene & Kontext**: *Was stellen die Daten dar? Was sollen sie messen/abbilden?*  
Das ist mehr als technische Spezifikationen – es geht um „meaning“ / intended measurement / intended use.

**✅ Ausreichend**  
- Es ist erklärt, welche Informationen in den Daten stecken bzw. was sie darstellen oder messen sollen  
  (Problem-/Domänenbezug, Ziel, Kontext, intended use).

**❌ Unzureichend**  
- Keine Angabe (z. B. leere README oder nur technische Specs ohne Bedeutung/ Kontext).

**Mini-Beispiele**  
- ✅ *„Each record represents a hospital visit; label indicates 30-day readmission risk …“*  
- ✅ *„Sensor measures vibration of machine X; goal is predictive maintenance …“*  
- ❌ *„Columns: col1, col2 … dtype …“* ohne Kontext
"""
        )


def show_ai_act_mapping():
    render()