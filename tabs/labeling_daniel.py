from typing import List, Dict
import json
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

# 👇 HIER deine Folder-ID von "label-corpus-v1" einsetzen!
LABEL_CORPUS_DRIVE_FOLDER_ID = "1oOrVSlzR3sP7EYvIr5nzEgBF4KtJ2roJ"

# categories.json auf Google Drive (selbe ID wie im Categories-Tab)
CATEGORIES_DRIVE_FILE_ID = "1EmZHSfSwbEw4JYsyRYvVBSbY4g4FSOi5"

# Dateien für Labels & Skips im gleichen Ordner wie der Korpus
LABELS_FILENAME = "labels_daniel.csv"
SKIPPED_FILENAME = "skipped_daniel.csv"

ANNOTATOR_NAME = "daniel"  # fix für diesen Tab
CORPUS_NAME = "label_corpus_v1"  # nur für Anzeige


# --------------------------------------------------------------------
# Hilfsfunktionen: Kategorien
# --------------------------------------------------------------------

def _load_categories() -> Dict:
    """categories.json von Google Drive laden."""
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


def _list_labeling_plans() -> List[Dict]:
    """
    Listet alle CSV-Labeling-Pläne im Unterordner 'labelplan'.
    Rückgabe: Liste von Dicts mit 'id', 'name', 'mimeType'.
    """
    try:
        labelplan_folder_id = _get_labelplan_folder_id()
    except Exception as e:
        st.error(str(e))
        return []

    files = list_files_in_folder(labelplan_folder_id)
    csv_files = [f for f in files if f["name"].lower().endswith(".csv")]
    return csv_files


def _build_readme_index() -> Dict[str, str]:
    """
    Baut ein Mapping filename -> file_id für alle Dateien im
    Korpus-Ordner (ohne Unterordner).
    Erwartung: Spalte `filename` im Labelplan entspricht genau
    dem Dateinamen im Drive-Ordner `label-corpus-v1`.
    """
    files = list_files_in_folder(LABEL_CORPUS_DRIVE_FOLDER_ID)
    index: Dict[str, str] = {}
    for f in files:
        # Ordner ausklammern
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue
        index[f["name"]] = f["id"]
    return index


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
    # längere Keywords zuerst
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
# Laden / Speichern von Labels & Skips (Google Drive)
# --------------------------------------------------------------------

def _load_labels() -> pd.DataFrame:
    df = load_csv_from_drive_by_name(LABEL_CORPUS_DRIVE_FOLDER_ID, LABELS_FILENAME)
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["doc_id", "filename", "category", "label", "annotator"]
        )
    for col in ["doc_id", "filename", "category", "label", "annotator"]:
        if col not in df.columns:
            df[col] = ""
    return df


def _save_labels(df: pd.DataFrame):
    save_csv_to_drive_by_name(df, LABEL_CORPUS_DRIVE_FOLDER_ID, LABELS_FILENAME)


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
# Fortschritt
# --------------------------------------------------------------------

def _compute_progress(df_plan, df_labels, skipped_ids) -> Dict:
    if df_plan is None or df_plan.empty:
        return {"total_docs": 0, "done_docs": 0, "done_mask": []}

    doc_ids = df_plan["doc_id"].astype(str).tolist()
    total = len(doc_ids)
    labeled_ids = (
        set(df_labels["doc_id"].astype(str).unique())
        if not df_labels.empty
        else set()
    )
    skipped_set = set(skipped_ids)
    done_mask = [d in labeled_ids or d in skipped_set for d in doc_ids]
    done = sum(done_mask)
    return {"total_docs": total, "done_docs": done, "done_mask": done_mask}


def _find_next_doc_index(df_plan, done_mask) -> int:
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

    # ------------------------------------------------
    # 1) Labeling-Plan(e) aus Google Drive holen
    # ------------------------------------------------
    plans = _list_labeling_plans()
    if not plans:
        st.warning(
            "Kein Labeling-Plan gefunden. "
            "Lege im Drive-Korpus-Ordner (`label-corpus-v1`) einen Unterordner `labelplan` mit einer CSV (z. B. `label.csv`) an."
        )
        return

    # Es gibt bei dir aktuell nur eine Datei (label.csv) – aber wir lassen die Logik flexibel.
    if len(plans) == 1:
        selected_idx = 0
        st.caption(f"Labeling-Plan: **{plans[0]['name']}**")
    else:
        selected_idx = st.selectbox(
            "Labeling-Plan auswählen",
            options=list(range(len(plans))),
            format_func=lambda i: plans[i]["name"],
            key="dl_plan_select",
        )

    selected_plan = plans[selected_idx]
    plan_file_id = selected_plan["id"]

    try:
        df_plan = load_csv_from_drive(plan_file_id)
    except Exception as e:
        st.error(f"Labeling-Plan `{selected_plan['name']}` konnte nicht geladen werden: {e}")
        return

    # ------------------------------------------------
    # 2) Labels & Skips aus Google Drive
    # ------------------------------------------------
    df_labels = _load_labels()
    skipped = _load_skipped_ids()

    # ------------------------------------------------
    # 3) Kategorien laden & auf Labelplan mappen
    # ------------------------------------------------
    categories_cfg = _load_categories()
    if not categories_cfg:
        st.error("Es wurden keine Kategorien in `categories.json` (Google Drive) gefunden.")
        return

    # Kategorien, die im Labelplan für Daniel existieren (Spalten Daniel__...)
    daniel_cols = [c for c in df_plan.columns if c.startswith("Daniel__")]
    plan_categories = [c.split("Daniel__", 1)[1].lstrip("_") for c in daniel_cols]

    categories: List[str] = []
    for pc in plan_categories:
        if pc in categories_cfg:
            categories.append(pc)
        else:
            # Falls Kategorie nicht in categories.json konfiguriert ist:
            # trotzdem anzeigen, aber ohne Keywords.
            categories_cfg[pc] = {}
            categories.append(pc)

    if not categories:
        st.error(
            "Im Labeling-Plan wurden keine Spalten vom Typ `Daniel__<Kategorie>` gefunden. "
            "Bitte prüfe die Spaltennamen in `label.csv`."
        )
        return

    # ------------------------------------------------
    # 4) Fortschritt berechnen
    # ------------------------------------------------
    prog = _compute_progress(df_plan, df_labels, skipped)
    if prog["total_docs"] == 0:
        st.error("Der ausgewählte Labeling-Plan enthält keine Einträge.")
        return

    st.progress(prog["done_docs"] / prog["total_docs"])
    st.metric("Bearbeitet", f"{prog['done_docs']} / {prog['total_docs']}")

    # ------------------------------------------------
    # 5) README-Index (filename -> file_id) aufbauen
    # ------------------------------------------------
    readme_index = _build_readme_index()
    if not readme_index:
        st.error(
            "Im Korpus-Ordner auf Google Drive wurden keine README-Dateien gefunden. "
            "Lege die Datensatzbeschreibungen direkt in `label-corpus-v1` ab."
        )
        return

    # ------------------------------------------------
    # 6) Aktuelle README bestimmen
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

    text = ""
    try:
        text = load_text_from_drive(file_id)
    except Exception as e:
        st.error(f"README `{filename}` konnte nicht von Google Drive geladen werden: {e}")
        return

    st.markdown(
        f"**Aktuelles README:** `{filename}` "
        f"({current_index+1}/{prog['total_docs']})"
    )
    st.caption(
        f"doc_id: `{doc_id}` – Korpus: `{CORPUS_NAME}` – Plan: `{selected_plan['name']}`"
    )

    # ------------------------------------------------
    # 7) Keyword-Highlighting + Legende
    # ------------------------------------------------
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

    cat_to_keywords = _collect_positive_keywords_by_category(categories_cfg, categories)

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
    # 8) Labeling-UI
    # ------------------------------------------------
    st.markdown("### Labels vergeben")

    df_ann_doc = (
        df_labels[df_labels["doc_id"].astype(str) == str(doc_id)]
        if not df_labels.empty
        else pd.DataFrame()
    )
    label_widgets: Dict[str, str] = {}

    if len(categories) > 0:
        cols = st.columns(len(categories))
    else:
        cols = []

    for cat, col in zip(categories, cols):
        with col:
            existing = None
            if not df_ann_doc.empty and cat in df_ann_doc["category"].values:
                existing = int(
                    df_ann_doc[df_ann_doc["category"] == cat]["label"].iloc[-1]
                )
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
    # 9) Speichern oder Überspringen
    # ------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Label speichern & nächste README", key="dl_save_next"):
            rows_new = []
            for cat in categories:
                val = label_widgets.get(cat, "")
                if val == "":
                    continue
                label_value = 1 if "Ja (1)" in val else 0
                rows_new.append(
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "category": cat,
                        "label": label_value,
                        "annotator": ANNOTATOR_NAME,
                    }
                )

            if rows_new:
                df_new = pd.DataFrame(rows_new)

                # Alte Labels für diese doc_id & Annotator überschreiben
                if not df_labels.empty:
                    df_labels = df_labels[
                        ~(
                            (df_labels["annotator"] == ANNOTATOR_NAME)
                            & (df_labels["doc_id"].astype(str) == str(doc_id))
                        )
                    ]
                df_labels = pd.concat([df_labels, df_new], ignore_index=True)
                _save_labels(df_labels)

                # Labels zusätzlich im Labeling-Plan (Daniel-Spalten) speichern
                try:
                    df_plan_sheet = load_csv_from_drive(plan_file_id)
                    mask_doc = df_plan_sheet["doc_id"].astype(str) == str(doc_id)
                    if mask_doc.any():
                        for r in rows_new:
                            cat = r["category"]
                            label_val = r["label"]
                            col_name = f"Daniel__{cat}"
                            if col_name in df_plan_sheet.columns:
                                df_plan_sheet.loc[mask_doc, col_name] = label_val
                    save_csv_to_drive(df_plan_sheet, plan_file_id)
                except Exception as e:
                    st.warning(
                        f"Labels konnten nicht im Labeling-Plan `{selected_plan['name']}` gespeichert werden: {e}"
                    )

                if "dl_manual_doc_index" in st.session_state:
                    del st.session_state["dl_manual_doc_index"]

                st.success("Labels gespeichert! Nächstes README wird geladen …")
                if hasattr(st, "rerun"):
                    st.rerun()
                elif hasattr(st, "experimental_rerun"):
                    st.experimental_rerun()
            else:
                st.warning("Keine Labels vergeben.")

    with col2:
        if st.button("⏭ README überspringen", key="dl_skip_doc"):
            _append_skipped_id(doc_id, filename)
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
        row = df_plan[df_plan["doc_index"] == idx].iloc[0]
        pos = int(row["doc_index"]) + 1
        return f"{pos:03d} – {row['filename']} (doc_id={row['doc_id']})"

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


# optional, falls du in main.py sowas wie show_labeling_daniel() verwendest
def show_labeling_daniel():
    render()