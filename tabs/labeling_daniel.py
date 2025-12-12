from typing import List, Dict
import re
import html
from datetime import datetime

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

# Datei für Skips im labelplan-Unterordner
SKIPPED_FILENAME = "skipped_daniel.csv"

ANNOTATOR_NAME = "daniel"  # fix für diesen Tab
CORPUS_NAME = "label-corpus-v1"  # nur für Anzeige


# --------------------------------------------------------------------
# Hilfsfunktionen: Kategorien (Drive + Session-Cache)
# --------------------------------------------------------------------

def _load_categories_raw() -> Dict:
    """categories.json von Google Drive laden (einmalig, dann in Session-Cache)."""
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


def _get_categories_cached() -> Dict:
    """
    Kategorien einmal pro Session von Drive laden und dann aus st.session_state holen.
    So vermeiden wir Drive-Requests bei jedem Klick.
    """
    key = "daniel_categories_cache"
    if key not in st.session_state:
        st.session_state[key] = _load_categories_raw()
    return st.session_state[key]


def _reload_categories():
    """Manuelles Neuladen aus Drive (falls du im Categories-Tab etwas geändert hast)."""
    st.session_state["daniel_categories_cache"] = _load_categories_raw()


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
def _cached_readme_index(folder_id: str, version: int) -> Dict[str, str]:
    """
    Gecachtes Mapping filename -> file_id für alle Dateien im
    Korpus-Ordner (ohne Unterordner).

    Der Parameter `version` sorgt dafür, dass wir den Cache manuell
    invalidieren können (z. B. nach dem Kopieren eines neuen Korpus
    nach Google Drive).
    """
    files = list_files_in_folder(folder_id)
    index: Dict[str, str] = {}
    for f in files:
        # Ordner ausklammern
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue
        index[f["name"]] = f["id"]
    return index


@st.cache_data(ttl=120, show_spinner=False)
def _cached_load_labelplan(plan_file_id: str, version: int) -> pd.DataFrame:
    """
    Gecachter Loader für label.csv.
    TTL verhindert veraltete Drive-Stände bei längeren Pausen.
    """
    return load_csv_from_drive(plan_file_id)


@st.cache_data(show_spinner=False)
def _cached_load_readme_text(file_id: str) -> str:
    """README-Text pro Datei cachen."""
    return load_text_from_drive(file_id)


# --------------------------------------------------------------------
# YAML-Frontmatter entfernen & Sanitizer
# --------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """
    Entfernt optionales YAML-Frontmatter am Anfang (HuggingFace-Style):

    ---
    license: ...
    configs:
      - ...
    ---
    # Überschrift

    Alles zwischen den beiden '---'-Linien am Anfang wird entfernt.
    """
    lines = text.splitlines()
    if not lines:
        return text

    # erste nicht-leere Zeile suchen
    first_non_empty_idx = None
    for i, line in enumerate(lines):
        if line.strip():
            first_non_empty_idx = i
            break

    if first_non_empty_idx is None:
        return text

    if lines[first_non_empty_idx].strip() != "---":
        # kein Frontmatter
        return text

    # zweite '---'-Zeile suchen
    for j in range(first_non_empty_idx + 1, len(lines)):
        if lines[j].strip() == "---":
            # alles danach behalten
            return "\n".join(lines[j + 1:])

    # falls keine zweite --- gefunden → Text unverändert lassen
    return text


def _sanitize_text_for_html(text: str) -> str:
    """
    Entfernt problematische Unicode-Zeichen, aber KEIN html.escape mehr,
    damit Markdown / Sonderzeichen erhalten bleiben.
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
    return safe


# --------------------------------------------------------------------
# Keyword-Highlighting
# --------------------------------------------------------------------

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
# Skipped-Tracking (Drive + Session-Cache)
# --------------------------------------------------------------------

def _load_skipped_ids_raw() -> List[str]:
    """
    Direkt von Drive laden (wird dann in Session-Cache gelegt).
    Sucht die Datei `skipped_daniel.csv` im labelplan-Unterordner.
    """
    try:
        labelplan_folder_id = _get_labelplan_folder_id()
    except Exception as e:
        # Wenn es den labelplan-Ordner nicht gibt, einfach keine Skips
        st.warning(f"Skip-Dateien konnten nicht geladen werden: {e}")
        return []

    df = load_csv_from_drive_by_name(labelplan_folder_id, SKIPPED_FILENAME)
    if df is None or df.empty:
        return []
    if "doc_id" not in df.columns:
        return []
    return df["doc_id"].astype(str).tolist()


def _get_skipped_ids_cached() -> List[str]:
    """
    Skipped-IDs einmal pro Session von Drive holen und dann in
    st.session_state vorhalten.
    """
    key = "daniel_skipped_cache"
    if key not in st.session_state:
        st.session_state[key] = _load_skipped_ids_raw()
    return st.session_state[key]


def _append_skipped_id(doc_id: str, filename: str):
    """
    doc_id + filename in skipped_daniel.csv im labelplan-Ordner ergänzen
    und Session-Cache aktualisieren.
    """
    # Zielordner jetzt: labelplan-Unterordner
    try:
        labelplan_folder_id = _get_labelplan_folder_id()
    except Exception as e:
        st.error(f"Skip-Datei konnte nicht aktualisiert werden (labelplan-Ordner fehlt?): {e}")
        return

    # 1) Auf Drive schreiben
    df = load_csv_from_drive_by_name(labelplan_folder_id, SKIPPED_FILENAME)
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
        # ⬇️ Speichern jetzt im labelplan-Ordner
        save_csv_to_drive_by_name(df, labelplan_folder_id, SKIPPED_FILENAME)

    # 2) Session-Cache aktualisieren
    key = "daniel_skipped_cache"
    skipped = st.session_state.get(key, [])
    if doc_id not in skipped:
        skipped.append(doc_id)
    st.session_state[key] = skipped


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

    # Session-State-Init (damit labelplan_version & readme_index_version immer existieren)
    if "labelplan_version" not in st.session_state:
        st.session_state["labelplan_version"] = 0
    if "readme_index_version" not in st.session_state:
        st.session_state["readme_index_version"] = 0

    # Optional: Button zum manuellen Reload der Kategorien & der Dateiliste & Labelplan
    with st.expander("⚙️ Optionen", expanded=False):
        col_opt1, col_opt2, col_opt3 = st.columns(3)

        with col_opt1:
            if st.button("🔄 Kategorien aus Drive neu laden", key="reload_categories_btn_daniel"):
                _reload_categories()
                st.info("Kategorien neu geladen.")
                st.rerun()

        with col_opt2:
            if st.button("🔄 Korpus-Dateiliste neu laden", key="reload_readme_index_btn_daniel"):
                st.session_state["readme_index_version"] += 1
                st.info("Korpus-Dateiliste neu geladen.")
                st.rerun()

        with col_opt3:
            if st.button("🔄 Labelplan von Drive neu laden", key="reload_labelplan_btn_daniel"):
                # Cache für label.csv invalidieren (falls verfügbar)
                try:
                    _cached_load_labelplan.clear()
                except Exception:
                    pass

                # Version erhöhen (Cache-Key) + Session-Kopie resetten
                st.session_state["labelplan_version"] += 1

                if "df_plan_daniel" in st.session_state:
                    del st.session_state["df_plan_daniel"]
                st.session_state["df_dirty_daniel"] = False

                st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                st.info("Labelplan neu von Google Drive geladen.")
                st.rerun()

    # ------------------------------------------------
    # 1) label.csv aus Google Drive holen (gecached)
    # ------------------------------------------------
    try:
        plan_file_id = _get_labelplan_file_id()
    except Exception as e:
        st.error(str(e))
        return

    try:
        df_plan_remote = _cached_load_labelplan(
            plan_file_id, st.session_state["labelplan_version"]
        )
    except Exception as e:
        st.error(f"Labeling-Plan konnte nicht geladen werden: {e}")
        return

    # ------------------------------------------------
    # 1a) Lokale Session-Kopie initialisieren (Batch-Editing)
    # ------------------------------------------------
    if "df_plan_daniel" not in st.session_state:
        st.session_state["df_plan_daniel"] = df_plan_remote.copy()
        st.session_state["df_dirty_daniel"] = False
        # Zeitstempel "zuletzt von Drive geladen"
        st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    # Ab hier IMMER mit der Session-Kopie arbeiten
    df_plan = st.session_state["df_plan_daniel"]

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

    # Kategorien-Konfiguration aus Session-Cache holen (einmal pro Session von Drive)
    categories_cfg = _get_categories_cached()

    categories: List[str] = []
    for cat in cat_to_col.keys():
        if cat not in categories_cfg:
            # Wenn es die Kategorie im JSON (noch) nicht gibt:
            # leeres Dict -> keine Keywords, aber trotzdem Kategorie im UI
            categories_cfg[cat] = {}
        categories.append(cat)

    # ------------------------------------------------
    # 3) Skips laden & Fortschritt berechnen (Skips aus Session-Cache)
    # ------------------------------------------------
    skipped = _get_skipped_ids_cached()
    prog = _compute_progress(df_plan, daniel_cols, skipped)
    if prog["total_docs"] == 0:
        st.error("Der ausgewählte Labeling-Plan enthält keine Einträge.")
        return

    st.progress(prog["done_docs"] / prog["total_docs"])
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Bearbeitet", f"{prog['done_docs']} / {prog['total_docs']}")
    with c2:
        ts = st.session_state.get("daniel_labelplan_last_loaded", "unbekannt")
        st.caption(f"Zuletzt von Drive geladen: {ts}")

    # ------------------------------------------------
    # 4) README-Index (filename -> file_id) aufbauen (gecached)
    # ------------------------------------------------
    readme_index = _cached_readme_index(
        LABEL_CORPUS_DRIVE_FOLDER_ID,
        st.session_state["readme_index_version"],
    )
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
            "exakt mit der Datei im Ordner `label-corpus-v1` übereinstimmt.\n\n"
            "Falls du den Final-Korpus gerade neu nach Google Drive kopiert hast, "
            "nutze im ⚙️-Menü den Button **„Korpus-Dateiliste neu laden“**."
        )
        return

    try:
        raw_text = _cached_load_readme_text(file_id)
    except Exception as e:
        st.error(f"README `{filename}` konnte nicht von Google Drive geladen werden: {e}")
        return

    # YAML-Frontmatter entfernen und Text „säubern“
    text = _strip_frontmatter(raw_text)
    text = _sanitize_text_for_html(text)

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
    kw_color_pairs: List[Dict[str, str]] = []
    for cat, kws in cat_to_keywords.items():
        color = cat_to_color.get(cat, "#ffe58a")
        for kw in kws:
            kw_color_pairs.append({"keyword": kw, "color": color})

    st.markdown("#### README-Inhalt (mit Keyword-Highlighting)")

    if kw_color_pairs:
        marked_text = _highlight_keywords_multi(text, kw_color_pairs)
    else:
        marked_text = text

    # 👉 Scrollbarer Kasten mit dem Readme-Inhalt
    st.markdown(
        f"""
        <div style="max-height:500px;overflow-y:auto;padding:0.75rem;
        border:1px solid #ddd;border-radius:0.5rem;background-color:#fafafa;">
        {marked_text}
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
    # 7) Labeling-UI – direkt auf Basis der Session-Kopie (Daniel-Spalten)
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
                key=f"{doc_id}_{cat}_daniel",
            )

    # ------------------------------------------------
    # 8) Speichern oder Überspringen (nur lokal in Session-Kopie)
    # ------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Label lokal speichern & nächste README", key="dl_save_next"):
            mask_doc = df_plan["doc_id"].astype(str) == str(doc_id)
            if not mask_doc.any():
                st.error("Aktuelle doc_id wurde im Labelplan nicht gefunden.")
            else:
                # Nur Daniel__-Spalten in der Session-Kopie aktualisieren
                for cat in categories:
                    val = label_widgets.get(cat, "")
                    plan_col = cat_to_col[cat]
                    if val == "":
                        # nichts ändern → bisherigen Wert beibehalten
                        continue
                    label_value = 1 if "Ja (1)" in val else 0
                    df_plan.loc[mask_doc, plan_col] = label_value

                # Session-Kopie & Dirty-Flag aktualisieren
                st.session_state["df_plan_daniel"] = df_plan
                st.session_state["df_dirty_daniel"] = True

                if "dl_manual_doc_index" in st.session_state:
                    del st.session_state["dl_manual_doc_index"]

                st.success("Labels lokal gespeichert! Nächstes README wird geladen …")
                st.rerun()

    with col2:
        if st.button("⏭ README überspringen", key="dl_skip_doc"):
            _append_skipped_id(str(doc_id), filename)
            if "dl_manual_doc_index" in st.session_state:
                del st.session_state["dl_manual_doc_index"]
            st.info("README übersprungen. Nächstes README wird geladen …")
            st.rerun()

    # ------------------------------------------------
    # 9) Synchronisation mit Google Drive (Batch-Upload, nur Daniel-Spalten mergen)
    # ------------------------------------------------
    st.markdown("---")
    st.markdown("### Synchronisation mit Google Drive")

    col_sync1, col_sync2 = st.columns(2)
    with col_sync1:
        dirty = st.session_state.get("df_dirty_daniel", False)
        status_text = "🟡 nicht hochgeladene Änderungen" if dirty else "🟢 alle Änderungen auf Drive"
        st.write(f"Status: {status_text}")

    with col_sync2:
        if st.button("⬆️ Labels nach Drive hochladen", key="dl_upload_drive"):
            df_local = st.session_state.get("df_plan_daniel", None)
            if df_local is None:
                st.warning("Keine lokalen Labels zum Hochladen gefunden.")
            else:
                try:
                    # 1) Aktuelle Version von Drive laden
                    df_remote = load_csv_from_drive(plan_file_id)

                    if "doc_id" not in df_remote.columns:
                        st.error("In der Labelplan-Datei auf Drive fehlt die Spalte `doc_id`.")
                    else:
                        # 2) Nur Daniel-Spalten aktualisieren
                        daniel_cols_remote = _get_daniel_columns(df_local)

                        df_remote = df_remote.copy()
                        df_remote.set_index("doc_id", inplace=True)
                        df_local_idx = df_local.set_index("doc_id")

                        # Nur die Daniel-Spalten aus der lokalen Kopie übernehmen
                        df_remote.update(df_local_idx[daniel_cols_remote])

                        df_remote.reset_index(inplace=True)

                        # 3) Gemergte Version zurück nach Drive schreiben
                        save_csv_to_drive(df_remote, plan_file_id)

                        # 4) Dirty-Flag & Version aktualisieren
                        st.session_state["df_dirty_daniel"] = False
                        st.session_state["labelplan_version"] += 1
                        st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                        # Optional: Cache leeren, damit direkt frischer Stand gezogen wird
                        try:
                            _cached_load_labelplan.clear()
                        except Exception:
                            pass

                        st.success(
                            "Daniel-Labels erfolgreich nach Google Drive hochgeladen "
                            "(nur Daniel-Spalten aktualisiert)."
                        )
                        st.rerun()

                except Exception as e:
                    st.error(f"Fehler beim Hochladen nach Drive: {e}")

    # ------------------------------------------------
    # 10) Jump zu bestimmter README
    # ------------------------------------------------
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
        st.rerun()


def show_labeling_daniel():
    render()