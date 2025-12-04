from typing import List, Dict
import re
import html
import pandas as pd
import streamlit as st

from utils.gdrive import (
    load_json_from_drive,
    load_text_from_drive,
    load_csv_from_drive,
    save_csv_to_drive,
    list_files_in_folder,
    load_csv_from_drive_by_name,
    save_csv_to_drive_by_name,
)

# --------------------------------------------------------------------
# Konfiguration: Google Drive
# --------------------------------------------------------------------

# Google-Drive-Ordner: label-corpus-v1
LABEL_CORPUS_DRIVE_FOLDER_ID = "1oOrVSlzR3sP7EYvIr5nzEgBF4KtJ2roJ"

# categories.json auf Google Drive (selbe ID wie im Categories-Tab)
CATEGORIES_DRIVE_FILE_ID = "1EmZHSfSwbEw4JYsyRYvVBSbY4g4FSOi5"

# Datei für Skips im gleichen Ordner wie der Korpus (kein Label-File!)
SKIPPED_FILENAME = "skipped_daniel.csv"

ANNOTATOR_NAME = "daniel"  # fix für diesen Tab
CORPUS_NAME = "label-corpus-v1"  # nur für Anzeige


# --------------------------------------------------------------------
# Hilfsfunktionen: Kategorien (OHNE Cache, immer aktuelle JSON)
# --------------------------------------------------------------------

def _load_categories_raw() -> Dict:
    """categories.json von Google Drive laden (immer aktuell, kein Cache)."""
    try:
        data = load_json_from_drive(CATEGORIES_DRIVE_FILE_ID)
        if isinstance(data, dict):
            return data
        else:
            st.error("`categories.json` auf Google Drive hat keine Dict-Struktur.")
            return {}
    except Exception as e:
        st.error(f"Fehler beim Laden von Kategorien aus Google Drive: {e}")
        return {}


# --------------------------------------------------------------------
# Hilfsfunktionen: Korpus-Struktur auf Drive
# --------------------------------------------------------------------

def _get_labelplan_folder_id() -> str:
    """
    Sucht im Korpus-Ordner einen Unterordner mit Namen 'labelplan'.
    """
    folders = list_files_in_folder(
        LABEL_CORPUS_DRIVE_FOLDER_ID,
        mime_type="application/vnd.google-apps.folder",
    )
    for f in folders:
        if f["name"].lower() == "labelplan":
            return f["id"]
    raise RuntimeError(
        "Kein Unterordner 'labelplan' im Korpus-Ordner gefunden. "
        "Bitte im Drive-Ordner `label-corpus-v1` einen Unterordner `labelplan` anlegen."
    )


def _get_labelplan_file_id() -> str:
    """
    Liefert die fileId von label.csv in labelplan/.
    """
    labelplan_folder_id = _get_labelplan_folder_id()
    files = list_files_in_folder(labelplan_folder_id)

    # Bevorzugt explizit label.csv
    for f in files:
        if f["name"].lower() == "label.csv":
            return f["id"]

    # Fallback: erste CSV-Datei im Ordner
    for f in files:
        if f["name"].lower().endswith(".csv"):
            return f["id"]

    raise RuntimeError(
        "In `labelplan/` wurde keine `label.csv` (oder sonstige CSV) gefunden."
    )


@st.cache_data(show_spinner=False)
def _cached_readme_index(folder_id: str) -> Dict[str, str]:
    """
    Gecachtes Mapping filename -> file_id für alle Dateien im
    Korpus-Ordner (ohne Unterordner).
    """
    files = list_files_in_folder(folder_id)
    index: Dict[str, str] = {}
    for f in files:
        # Ordner ausklammern
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue
        index[f["name"]] = f["id"]
    return index


@st.cache_data(show_spinner=False)
def _cached_load_labelplan(plan_file_id: str, version: int) -> pd.DataFrame:
    """
    Gecachter Loader für label.csv. Der Parameter `version` sorgt dafür,
    dass nach jedem Speichern eine neue Version in den Cache geschrieben wird.
    """
    return load_csv_from_drive(plan_file_id)


@st.cache_data(show_spinner=False)
def _cached_load_readme_text(file_id: str) -> str:
    """README-Text pro Datei cachen."""
    return load_text_from_drive(file_id)


# --------------------------------------------------------------------
# Keyword-Highlighting
# --------------------------------------------------------------------

def _sanitize_text_for_html(text: str) -> str:
    """
    Entfernt problematische Unicode-Zeichen und escaped HTML.
    """
    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        # Steuerzeichen 0x00–0x1F (außer \t, \n, \r) entfernen
        if code < 32 and ch not in ("\t", "\n", "\r"):
            continue
        # Surrogates entfernen
        if 0xD800 <= code <= 0xDFFF:
            continue
        cleaned_chars.append(ch)
    safe = "".join(cleaned_chars)
    return html.escape(safe)


def _collect_positive_keywords_by_category(
    categories_cfg: Dict,
    categories_to_label: List[str],
) -> Dict[str, List[str]]:
    """
    Liefert pro Kategorie die POS-Keywords:
      {category_name: [kw1, kw2, ...]}

    Nutzt bevorzugt "sentence_keywords_positive" aus categories.json.
    """
    result: Dict[str, List[str]] = {}
    for cat in categories_to_label:
        cfg = categories_cfg.get(cat, {})
        kws = (
            cfg.get("sentence_keywords_positive")
            or cfg.get("sentence_positive_keywords")
            or cfg.get("sentence_keywords")
            or []
        )
        if isinstance(kws, list):
            kw_list = [str(k).strip().lower() for k in kws if str(k).strip()]
        elif isinstance(kws, str):
            kw_list = [p.strip().lower() for p in kws.split(",") if p.strip()]
        else:
            kw_list = []
        result[cat] = kw_list
    return result


def _highlight_keywords_multi(text: str, kw_color_pairs: List[Dict[str, str]]) -> str:
    """
    Mehrfarbiges Keyword-Highlighting:
    kw_color_pairs: Liste von Dicts mit {'keyword': ..., 'color': ...}
    """
    safe_text = _sanitize_text_for_html(text)
    if not kw_color_pairs:
        return safe_text

    highlighted = safe_text
    # längere Keywords zuerst → stabileres Matching
    sorted_pairs = sorted(
        kw_color_pairs,
        key=lambda x: len(x["keyword"]),
        reverse=True,
    )

    for pair in sorted_pairs:
        kw = pair["keyword"]
        color = pair["color"]
        if not kw:
            continue
        pattern = re.compile(re.escape(kw), re.IGNORECASE)

        def repl(match):
            return (
                f"<mark style='background-color:{color}; "
                f"padding:0 2px;'>{match.group(0)}</mark>"
            )

        highlighted = pattern.sub(repl, highlighted)

    return highlighted


# --------------------------------------------------------------------
# Skipped-Tracking (kleine Extra-CSV, aber KEIN Label-File)
# --------------------------------------------------------------------

def _load_skipped_ids() -> List[str]:
    df = load_csv_from_drive_by_name(LABEL_CORPUS_DRIVE_FOLDER_ID, SKIPPED_FILENAME)
    if df is None or df.empty:
        return []
    if "doc_id" not in df.columns:
        return []
    return df["doc_id"].astype(str).tolist()


def _append_skipped_id(doc_id: str, filename: str):
    df = load_csv_from_drive_by_name(LABEL_CORPUS_DRIVE_FOLDER_ID, SKIPPED_FILENAME)
    if df is None or df.empty:
        df = pd.DataFrame(columns=["doc_id", "filename"])
    if "doc_id" not in df.columns:
        df["doc_id"] = []
    if "filename" not in df.columns:
        df["filename"] = []

    if doc_id not in df["doc_id"].astype(str).values:
        df = pd.concat(
            [df, pd.DataFrame([{"doc_id": doc_id, "filename": filename}])],
            ignore_index=True,
        )
        save_csv_to_drive_by_name(df, LABEL_CORPUS_DRIVE_FOLDER_ID, SKIPPED_FILENAME)


# --------------------------------------------------------------------
# Fortschritt – direkt aus label.csv (Daniel-Spalten)
# --------------------------------------------------------------------

def _get_daniel_columns(df_plan: pd.DataFrame) -> List[str]:
    """Alle Spalten vom Typ Daniel__<Kategorie>."""
    return [c for c in df_plan.columns if c.startswith("Daniel__")]


def _compute_progress(df_plan: pd.DataFrame, daniel_cols: List[str], skipped_ids: List[str]) -> Dict:
    """
    Fortschritt basierend auf label.csv:

    - Eine README gilt als "done", wenn mindestens eine Daniel__-Spalte (0 oder 1) gesetzt ist
      ODER wenn sie in skipped_daniel.csv steht.
    """
    if df_plan is None or df_plan.empty:
        return {"total_docs": 0, "done_docs": 0, "done_mask": []}

    skipped_set = set(str(s) for s in skipped_ids)

    done_mask: List[bool] = []
    for _, row in df_plan.iterrows():
        doc_id = str(row["doc_id"])

        # Falls geskippt → fertig
        if doc_id in skipped_set:
            done_mask.append(True)
            continue

        # Fertig, wenn mindestens eine Daniel-Spalte gesetzt ist (0 oder 1)
        any_label = False
        for col in daniel_cols:
            val = row.get(col, None)
            if pd.isna(val):
                continue
            # Leere Strings wie "" ignorieren
            if isinstance(val, str) and val.strip() == "":
                continue
            any_label = True
            break

        done_mask.append(any_label)

    total = len(done_mask)
    done = sum(done_mask)

    return {"total_docs": total, "done_docs": done, "done_mask": done_mask}


def _find_next_doc_index(df_plan: pd.DataFrame, done_mask: List[bool]) -> int:
    if df_plan is None or df_plan.empty:
        return -1
    for i, done in enumerate(done_mask):
        if not done:
            return int(df_plan.iloc[i]["doc_index"])
    return -1


# --------------------------------------------------------------------
# Render
# --------------------------------------------------------------------

def render():
    st.subheader("🧩 Labeling – Daniel")

    # Session-State-Init (damit labelplan_version immer existiert)
    if "labelplan_version" not in st.session_state:
        st.session_state["labelplan_version"] = 0

    # ------------------------------------------------
    # 1) label.csv aus Google Drive holen (gecached)
    # ------------------------------------------------
    try:
        plan_file_id = _get_labelplan_file_id()
    except Exception as e:
        st.error(str(e))
        return

    try:
        df_plan = _cached_load_labelplan(plan_file_id, st.session_state["labelplan_version"])
    except Exception as e:
        st.error(f"Labeling-Plan konnte nicht geladen werden: {e}")
        return

    # ------------------------------------------------
    # 2) Daniel-Spalten & Kategorien aus dem Plan bestimmen
    # ------------------------------------------------
    daniel_cols = _get_daniel_columns(df_plan)
    if not daniel_cols:
        st.error(
            "Im Labeling-Plan wurden keine Spalten vom Typ `Daniel__<Kategorie>` gefunden. "
            "Bitte prüfe die Spaltennamen in `label.csv`."
        )
        return

    # Mapping: Kategorie-Name <-> Daniel-Spalte
    cat_to_col: Dict[str, str] = {}
    for col in daniel_cols:
        cat_name = col.split("Daniel__", 1)[1].lstrip("_")
        cat_to_col[cat_name] = col

    # Kategorien-Konfiguration IMMER FRISCH von Google Drive laden
    categories_cfg = _load_categories_raw()

    categories: List[str] = []
    for cat in cat_to_col.keys():
        if cat not in categories_cfg:
            # Wenn es die Kategorie im JSON (noch) nicht gibt:
            # leeres Dict -> keine Keywords, aber trotzdem Kategorie im UI
            categories_cfg[cat] = {}
        categories.append(cat)

    # ------------------------------------------------
    # 3) Skips laden & Fortschritt berechnen
    # ------------------------------------------------
    skipped = _load_skipped_ids()
    prog = _compute_progress(df_plan, daniel_cols, skipped)
    if prog["total_docs"] == 0:
        st.error("Der ausgewählte Labeling-Plan enthält keine Einträge.")
        return

    st.progress(prog["done_docs"] / prog["total_docs"])
    st.metric("Bearbeitet", f"{prog['done_docs']} / {prog['total_docs']}")

    # ------------------------------------------------
    # 4) README-Index (filename -> file_id) aufbauen (gecached)
    # ------------------------------------------------
    readme_index = _cached_readme_index(LABEL_CORPUS_DRIVE_FOLDER_ID)
    if not readme_index:
        st.error(
            "Im Korpus-Ordner auf Google Drive wurden keine README-Dateien gefunden. "
            "Lege die Datensatzbeschreibungen direkt in `label-corpus-v1` ab."
        )
        return

    # ------------------------------------------------
    # 5) Aktuelle README bestimmen (Auto + Jump)
    # ------------------------------------------------
    manual_idx = st.session_state.get("dl_manual_doc_index", None)
    available_indices = set(df_plan["doc_index"].tolist())

    if manual_idx is not None and int(manual_idx) in available_indices:
        current_index = int(manual_idx)
    else:
        current_index = _find_next_doc_index(df_plan, prog["done_mask"])

    if current_index == -1:
        st.success("🎉 Alle Readmes in diesem Labeling-Plan sind fertig!")
        return

    row = df_plan[df_plan["doc_index"] == current_index].iloc[0]
    doc_id, filename = row["doc_id"], row["filename"]

    file_id = readme_index.get(filename)
    if not file_id:
        st.error(
            f"Die Datei `{filename}` wurde im Korpus-Ordner auf Google Drive nicht gefunden.\n\n"
            "Bitte sicherstellen, dass der Dateiname im Labeling-Plan (Spalte `filename`) "
            "exakt mit der Datei im Ordner `label-corpus-v1` übereinstimmt."
        )
        return

    try:
        text = _cached_load_readme_text(file_id)
    except Exception as e:
        st.error(f"README `{filename}` konnte nicht von Google Drive geladen werden: {e}")
        return

    st.markdown(
        f"**Aktuelles README:** `{filename}` "
        f"({current_index+1}/{prog['total_docs']})"
    )
    st.caption(
        f"doc_id: `{doc_id}` – Korpus: `{CORPUS_NAME}` – Plan: `label.csv`"
    )

    # ------------------------------------------------
    # 6) Keyword-Highlighting + Legende (aus sentence_keywords_positive)
    # ------------------------------------------------
    # Farben pro Kategorie (einfaches Set – wird zyklisch genutzt)
    color_palette = [
        "#ffe58a",  # gelb
        "#ffcccc",  # rosa
        "#cce5ff",  # hellblau
        "#d5f5e3",  # hellgrün
        "#f9e79f",  # gold
        "#f5cba7",  # orange
        "#d7bde2",  # lila
        "#aed6f1",  # blau
    ]
    cat_to_color: Dict[str, str] = {}
    for i, cat in enumerate(categories):
        cat_to_color[cat] = color_palette[i % len(color_palette)]

    # Positive Satz-Keywords pro Kategorie aus categories.json holen
    cat_to_keywords = _collect_positive_keywords_by_category(categories_cfg, categories)

    # Keyword-Color-Paare bauen (für das eigentliche Highlighting)
    kw_color_pairs = []
    for cat, kws in cat_to_keywords.items():
        color = cat_to_color.get(cat, "#ffe58a")
        for kw in kws:
            kw_color_pairs.append({"keyword": kw, "color": color})

    st.markdown("#### README-Inhalt (mit Keyword-Highlighting)")
    if kw_color_pairs:
        highlighted_html = _highlight_keywords_multi(text, kw_color_pairs)
    else:
        highlighted_html = _sanitize_text_for_html(text)

    st.markdown(
        f"""
        <div style="max-height:500px;overflow-y:auto;padding:0.75rem;
        border:1px solid #ddd;border-radius:0.5rem;background-color:#fafafa;">
        {highlighted_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Legende horizontal mit Farben pro Kategorie
    st.markdown("##### Legende für Highlights")
    max_per_row = 4
    cats = categories
    for start in range(0, len(cats), max_per_row):
        row_cats = cats[start:start + max_per_row]
        cols_legend = st.columns(len(row_cats))
        for cat, col in zip(row_cats, cols_legend):
            color = cat_to_color.get(cat, "#ffe58a")
            with col:
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;gap:0.4rem;">
                        <span style="
                            display:inline-block;
                            width:14px;
                            height:14px;
                            border-radius:3px;
                            background-color:{color};
                            border:1px solid #999;
                        "></span>
                        <span>{html.escape(cat)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown(
        "_Hinweis: Wörter werden je nach Kategorie verschieden eingefärbt. "
        "Labels trotzdem immer manuell vergeben._"
    )

    # ------------------------------------------------
    # 7) Labeling-UI – direkt auf Basis von label.csv (Daniel-Spalten)
    # ------------------------------------------------
    st.markdown("### Labels vergeben")

    label_widgets: Dict[str, str] = {}

    if len(categories) > 0:
        cols = st.columns(len(categories))
    else:
        cols = []

    for cat, col in zip(categories, cols):
        with col:
            plan_col = cat_to_col[cat]
            val = row.get(plan_col, None)
            existing = None
            if not pd.isna(val):
                try:
                    existing = int(val)
                except Exception:
                    existing = None

            default_val = (
                ""
                if existing is None
                else ("Ja (1)" if existing == 1 else "Nein (0)")
            )

            label_widgets[cat] = st.segmented_control(
                label=cat,
                options=["", "Ja (1)", "Nein (0)"],
                default=default_val,
                key=f"{doc_id}_{cat}",
            )

    # ------------------------------------------------
    # 8) Speichern oder Überspringen
    # ------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Label speichern & nächste README", key="dl_save_next"):
            mask_doc = df_plan["doc_id"].astype(str) == str(doc_id)
            if not mask_doc.any():
                st.error("Aktuelle doc_id wurde im Labelplan nicht gefunden.")
            else:
                # Nur Daniel__-Spalten aktualisieren
                for cat in categories:
                    val = label_widgets.get(cat, "")
                    plan_col = cat_to_col[cat]
                    if val == "":
                        # nichts ändern → bisherigen Wert beibehalten
                        continue
                    label_value = 1 if "Ja (1)" in val else 0
                    df_plan.loc[mask_doc, plan_col] = label_value

                # Plan nach Google Drive zurückschreiben (überschreibt label.csv)
                try:
                    save_csv_to_drive(df_plan, plan_file_id)
                except Exception as e:
                    st.error(f"Labeling-Plan `label.csv` konnte nicht gespeichert werden: {e}")
                    return

                # Cache invalidieren, indem wir die Version erhöhen
                st.session_state["labelplan_version"] += 1

                if "dl_manual_doc_index" in st.session_state:
                    del st.session_state["dl_manual_doc_index"]

                st.success("Labels gespeichert! Nächstes README wird geladen …")
                if hasattr(st, "rerun"):
                    st.rerun()
                elif hasattr(st, "experimental_rerun"):
                    st.experimental_rerun()

    with col2:
        if st.button("⏭ README überspringen", key="dl_skip_doc"):
            _append_skipped_id(str(doc_id), filename)
            if "dl_manual_doc_index" in st.session_state:
                del st.session_state["dl_manual_doc_index"]
            st.info("README übersprungen. Nächstes README wird geladen …")
            if hasattr(st, "rerun"):
                st.rerun()
            elif hasattr(st, "experimental_rerun"):
                st.experimental_rerun()

    st.markdown("---")
    st.markdown("### Zu bestimmter README springen")

    doc_options = (
        df_plan.sort_values("doc_index")[["doc_index", "filename", "doc_id"]]
        .values
        .tolist()
    )

    def _format_doc_option(idx: int) -> str:
        row2 = df_plan[df_plan["doc_index"] == idx].iloc[0]
        pos = int(row2["doc_index"]) + 1
        return f"{pos:03d} – {row2['filename']} (doc_id={row2['doc_id']})"

    selected_jump_idx = st.selectbox(
        "README auswählen",
        options=[int(r[0]) for r in doc_options],
        format_func=_format_doc_option,
        key="dl_jump_select",
    )

    if st.button("🔁 Zu dieser README springen", key="dl_jump_button"):
        st.session_state["dl_manual_doc_index"] = int(selected_jump_idx)
        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()


def show_labeling_daniel():
    render()