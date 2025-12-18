# tabs/tab_labeling_daniel.py  (ONLINE / Streamlit Cloud Variante – Daniel)

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

# Kategorien mit 3 Ausprägungen (A/K/N)
TERNARY_CATEGORIES = {
    "Data Provenance",
    "Data Preparation and Processing",
    "Data Preparation & Processing",
    "Data Preparation and Processing (alle Verarbeitungsschritte ab Existenz der Rohdaten)",
    "Data Preparation and Processing (all processing steps after raw data exists)",
}


# --------------------------------------------------------------------
# Hilfsfunktionen: Kategorien (Drive + Session-Cache)
# --------------------------------------------------------------------

def _load_categories_raw() -> Dict:
    """categories.json von Google Drive laden (einmalig, dann in Session-Cache)."""
    try:
        data = load_json_from_drive(CATEGORIES_DRIVE_FILE_ID)
        if isinstance(data, dict):
            return data
        st.error("`categories.json` auf Google Drive hat keine Dict-Struktur.")
        return {}
    except Exception as e:
        st.error(f"Fehler beim Laden von Kategorien aus Google Drive: {e}")
        return {}


def _get_categories_cached() -> Dict:
    """Kategorien einmal pro Session von Drive laden und dann aus st.session_state holen."""
    key = "daniel_categories_cache"
    if key not in st.session_state:
        st.session_state[key] = _load_categories_raw()
    return st.session_state[key]


def _reload_categories():
    """Manuelles Neuladen aus Drive (falls im Categories-Tab etwas geändert wurde)."""
    st.session_state["daniel_categories_cache"] = _load_categories_raw()


# --------------------------------------------------------------------
# Hilfsfunktionen: Korpus-Struktur auf Drive
# --------------------------------------------------------------------

def _get_labelplan_folder_id() -> str:
    """Sucht im Korpus-Ordner einen Unterordner mit Namen 'labelplan'."""
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
    """Liefert die fileId von label.csv in labelplan/."""
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

    raise RuntimeError("In `labelplan/` wurde keine `label.csv` (oder sonstige CSV) gefunden.")


@st.cache_data(show_spinner=False)
def _cached_readme_index(folder_id: str, version: int) -> Dict[str, str]:
    """Gecachtes Mapping filename -> file_id für alle Dateien im Korpus-Ordner (ohne Unterordner)."""
    files = list_files_in_folder(folder_id)
    index: Dict[str, str] = {}
    for f in files:
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue
        index[f["name"]] = f["id"]
    return index


@st.cache_data(ttl=120, show_spinner=False)
def _cached_load_labelplan(plan_file_id: str, version: int) -> pd.DataFrame:
    """Gecachter Loader für label.csv."""
    return load_csv_from_drive(plan_file_id)


@st.cache_data(show_spinner=False)
def _cached_load_readme_text(file_id: str) -> str:
    """README-Text pro Datei cachen."""
    return load_text_from_drive(file_id)


# --------------------------------------------------------------------
# YAML-Frontmatter entfernen & Sanitizer (ONLINE: wie local – mit html.escape)
# --------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Entfernt optionales YAML-Frontmatter am Anfang (HuggingFace-Style)."""
    lines = text.splitlines()
    if not lines:
        return text

    first_non_empty_idx = None
    for i, line in enumerate(lines):
        if line.strip():
            first_non_empty_idx = i
            break

    if first_non_empty_idx is None:
        return text

    if lines[first_non_empty_idx].strip() != "---":
        return text

    for j in range(first_non_empty_idx + 1, len(lines)):
        if lines[j].strip() == "---":
            return "\n".join(lines[j + 1:])

    return text


def _sanitize_text_for_html(text: str) -> str:
    """
    Entfernt problematische Unicode-Zeichen und escaped HTML (stabil für unsafe HTML-Markup).
    """
    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        if code < 32 and ch not in ("\t", "\n", "\r"):
            continue
        if 0xD800 <= code <= 0xDFFF:
            continue
        cleaned_chars.append(ch)
    safe = "".join(cleaned_chars)
    return html.escape(safe)


# --------------------------------------------------------------------
# HTML-README: Erkennen, Decoden, Sanitizen, Rendern (ONLINE)
# --------------------------------------------------------------------

_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "u",
    "a", "ul", "ol", "li",
    "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "td", "th",
    "sup", "sub",
}


def _looks_like_html(text: str) -> bool:
    """
    Heuristik: True wenn der Text vermutlich HTML enthält (oder HTML-escaped Tags).
    """
    if not text:
        return False
    t = text.strip()

    # echte HTML-Tags
    if re.search(r"(?i)<\s*(p|div|span|br|a|strong|em|ul|ol|li|table|tr|td|th|h[1-6])\b", t):
        return True

    # HTML-escaped Tags (&lt;p&gt; etc.)
    if "&lt;" in t and re.search(r"(?i)&lt;\s*(p|div|span|br|a|strong|em|ul|ol|li|table|tr|td|th|h[1-6])\b", t):
        return True

    return False


def _decode_html_maybe_twice(text: str) -> str:
    """
    Viele Quellen liefern (teilweise) HTML-escaped HTML. Wir unescapen max. 2x.
    """
    out = text or ""
    for _ in range(2):
        new = html.unescape(out)
        if new == out:
            break
        out = new
    return out


def _sanitize_html_basic(raw_html: str) -> str:
    """
    Einfache Sanitization:
    - entfernt <script>/<style>
    - entfernt on* Event-Handler Attribute
    - neutralisiert javascript: URLs
    - lässt nur eine begrenzte Tag-Liste durch
    - entfernt Attribute überall, außer bei <a href="...">
    """
    s = raw_html or ""

    # 1) script/style entfernen
    s = re.sub(r"(?is)<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", "", s)

    # 2) on* handler entfernen (onclick=..., onload=..., etc.)
    s = re.sub(r"(?i)\s+on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s)

    # 3) javascript: in href/src neutralisieren
    s = re.sub(r"(?i)\b(href|src)\s*=\s*(['\"])javascript:[^'\"]*\2", r"\1=\2#\2", s)

    # 4) Nur erlaubte Tags zulassen – nicht erlaubte Tags escapen
    def _filter_tag(m: re.Match) -> str:
        tag = m.group(0)
        mname = re.match(r"(?is)<\s*/?\s*([a-z0-9]+)", tag)
        if not mname:
            return html.escape(tag)
        name = mname.group(1).lower()
        if name in _ALLOWED_TAGS:
            return tag
        return html.escape(tag)

    s = re.sub(r"(?is)<[^>]+>", _filter_tag, s)

    # 5) Attribute entfernen (außer <a href="...">)
    def _strip_attrs(m: re.Match) -> str:
        full = m.group(0)  # z.B. <p class="x">
        name = m.group(1).lower()
        closing = full.startswith("</")
        if closing:
            return full  # </p> bleibt

        if name == "a":
            href_m = re.search(r'(?i)\bhref\s*=\s*(".*?"|\'.*?\')', full)
            title_m = re.search(r'(?i)\btitle\s*=\s*(".*?"|\'.*?\')', full)
            href = f" href={href_m.group(1)}" if href_m else ""
            title = f" title={title_m.group(1)}" if title_m else ""
            rel = ' rel="noopener noreferrer"'
            target = ' target="_blank"'
            return f"<a{href}{title}{target}{rel}>"

        return f"<{name}>"

    s = re.sub(r"(?is)<\s*([a-z0-9]+)\b[^>]*>", _strip_attrs, s)

    # 6) Kontrollzeichen entfernen (wie im Text-Sanitizer)
    cleaned_chars = []
    for ch in s:
        code = ord(ch)
        if code < 32 and ch not in ("\t", "\n", "\r"):
            continue
        if 0xD800 <= code <= 0xDFFF:
            continue
        cleaned_chars.append(ch)

    return "".join(cleaned_chars)


def _render_readme_box(text: str, kw_color_pairs: List[Dict[str, str]]) -> None:
    """
    Rendert README im Scroll-Container.
    - Wenn HTML: decoded + sanitized HTML anzeigen (ohne Keyword-Highlighting, um HTML nicht zu zerbrechen)
    - Sonst: bisheriges Keyword-Highlighting (escaped + <mark>)
    """
    if _looks_like_html(text):
        decoded = _decode_html_maybe_twice(text)
        safe_html = _sanitize_html_basic(decoded)
        st.markdown(
            f"""
            <div style="max-height:500px;overflow-y:auto;padding:0.75rem;
            border:1px solid #ddd;border-radius:0.5rem;background-color:#fafafa;">
            {safe_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Hinweis: README wurde als HTML erkannt und gerendert (Keyword-Highlighting ist für HTML deaktiviert).")
        return

    marked_text = _highlight_keywords_multi(text, kw_color_pairs) if kw_color_pairs else _sanitize_text_for_html(text)
    st.markdown(
        f"""
        <div style="max-height:500px;overflow-y:auto;padding:0.75rem;
        border:1px solid #ddd;border-radius:0.5rem;background-color:#fafafa;">
        {marked_text}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------
# Label-Optionen (2 oder 3 Ausprägungen) – mit Icons ✅ ❓ ❌
# --------------------------------------------------------------------

def _normalize_cat_name(cat: str) -> str:
    return (cat or "").strip()


def _is_ternary_category(category_name: str) -> bool:
    """
    Entscheidet, ob eine Kategorie 3 Ausprägungen hat (A/K/N).
    Robust: entweder exakter Name oder per Heuristik.
    """
    c = _normalize_cat_name(category_name)

    if c in TERNARY_CATEGORIES:
        return True

    c_low = c.lower()
    if "provenance" in c_low:
        return True
    if "preparation" in c_low or "processing" in c_low:
        return True

    return False


def _label_options_for_category(category_name: str) -> List[str]:
    if _is_ternary_category(category_name):
        return ["—", "✅", "❓", "❌"]  # A, K, N
    return ["—", "✅", "❌"]          # A, N


def _parse_label_choice(category_name: str, choice: str):
    """
    Rückgabe:
      - ternär: ✅=2, ❓=1, ❌=0
      - binär: ✅=1, ❌=0
      - None wenn nicht gesetzt
    """
    if not choice or str(choice).strip() in ("", "—"):
        return None

    c = str(choice).strip()
    ternary = _is_ternary_category(category_name)

    if ternary:
        return {"✅": 2, "❓": 1, "❌": 0}.get(c, None)

    return {"✅": 1, "❌": 0}.get(c, None)


def _format_existing_label_for_ui(category_name: str, existing_val) -> str:
    """
    Wandelt gespeicherten Labelwert zurück in UI-Default:
      - ternär: 2→✅, 1→❓, 0→❌
      - binär: 1→✅, 0→❌
      - sonst → —
    """
    if existing_val is None or (isinstance(existing_val, float) and pd.isna(existing_val)):
        return "—"
    try:
        v = int(existing_val)
    except Exception:
        return "—"

    if _is_ternary_category(category_name):
        return {2: "✅", 1: "❓", 0: "❌"}.get(v, "—")

    return {1: "✅", 0: "❌"}.get(v, "—")


# --------------------------------------------------------------------
# Keyword-Highlighting
# --------------------------------------------------------------------

def _collect_positive_keywords_by_category(
    categories_cfg: Dict,
    categories_to_label: List[str],
) -> Dict[str, List[str]]:
    """Liefert pro Kategorie die POS-Keywords."""
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
    """Mehrfarbiges Keyword-Highlighting (input wird HTML-escaped erwartet)."""
    safe_text = _sanitize_text_for_html(text)
    if not kw_color_pairs:
        return safe_text

    highlighted = safe_text
    sorted_pairs = sorted(kw_color_pairs, key=lambda x: len(x["keyword"]), reverse=True)

    for pair in sorted_pairs:
        kw = pair["keyword"]
        color = pair["color"]
        if not kw:
            continue
        pattern = re.compile(re.escape(html.escape(kw)), re.IGNORECASE)

        def repl(match):
            return (
                f"<mark style='background-color:{color}; padding:0 2px;'>"
                f"{match.group(0)}</mark>"
            )

        highlighted = pattern.sub(repl, highlighted)

    return highlighted


# --------------------------------------------------------------------
# Skipped-Tracking (Drive + Session-Cache)
# --------------------------------------------------------------------

def _load_skipped_ids_raw() -> List[str]:
    """Direkt von Drive laden (danach Cache)."""
    try:
        labelplan_folder_id = _get_labelplan_folder_id()
    except Exception as e:
        st.warning(f"Skip-Dateien konnten nicht geladen werden: {e}")
        return []

    df = load_csv_from_drive_by_name(labelplan_folder_id, SKIPPED_FILENAME)
    if df is None or df.empty:
        return []
    if "doc_id" not in df.columns:
        return []
    return df["doc_id"].astype(str).tolist()


def _get_skipped_ids_cached() -> List[str]:
    key = "daniel_skipped_cache"
    if key not in st.session_state:
        st.session_state[key] = _load_skipped_ids_raw()
    return st.session_state[key]


def _append_skipped_id(corpus_doc_id: str, filename: str):
    """doc_id + filename in skipped_daniel.csv ergänzen (Drive + Cache)."""
    try:
        labelplan_folder_id = _get_labelplan_folder_id()
    except Exception as e:
        st.error(f"Skip-Datei konnte nicht aktualisiert werden (labelplan-Ordner fehlt?): {e}")
        return

    df = load_csv_from_drive_by_name(labelplan_folder_id, SKIPPED_FILENAME)
    if df is None or df.empty:
        df = pd.DataFrame(columns=["doc_id", "filename"])

    if "doc_id" not in df.columns:
        df["doc_id"] = []
    if "filename" not in df.columns:
        df["filename"] = []

    if str(corpus_doc_id) not in df["doc_id"].astype(str).values:
        df = pd.concat(
            [df, pd.DataFrame([{"doc_id": str(corpus_doc_id), "filename": filename}])],
            ignore_index=True,
        )
        save_csv_to_drive_by_name(df, labelplan_folder_id, SKIPPED_FILENAME)

    key = "daniel_skipped_cache"
    skipped = st.session_state.get(key, [])
    if str(corpus_doc_id) not in skipped:
        skipped.append(str(corpus_doc_id))
    st.session_state[key] = skipped


# --------------------------------------------------------------------
# Fortschritt – direkt aus label.csv (Daniel-Spalten)
# --------------------------------------------------------------------

def _get_daniel_columns(df_plan: pd.DataFrame) -> List[str]:
    return [c for c in df_plan.columns if c.startswith("Daniel__")]


def _compute_progress(df_plan: pd.DataFrame, daniel_cols: List[str], skipped_ids: List[str]) -> Dict:
    """
    Eine README gilt als "done", wenn mindestens eine Daniel__-Spalte gesetzt ist
    (0/1/2/...) ODER wenn sie in skipped_daniel.csv steht.
    """
    if df_plan is None or df_plan.empty:
        return {"total_docs": 0, "done_docs": 0, "done_mask": []}

    skipped_set = set(str(s) for s in skipped_ids)
    done_mask: List[bool] = []

    for _, row in df_plan.iterrows():
        doc_id = str(row["doc_id"])

        if doc_id in skipped_set:
            done_mask.append(True)
            continue

        any_label = False
        for col in daniel_cols:
            val = row.get(col, None)
            if pd.isna(val):
                continue
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
    st.subheader("🧩 Labeling – Daniel (Online)")

    # Session-State-Init
    if "labelplan_version" not in st.session_state:
        st.session_state["labelplan_version"] = 0
    if "readme_index_version" not in st.session_state:
        st.session_state["readme_index_version"] = 0

    # Optionen / Reloads
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
                try:
                    _cached_load_labelplan.clear()
                except Exception:
                    pass

                st.session_state["labelplan_version"] += 1

                if "df_plan_daniel" in st.session_state:
                    del st.session_state["df_plan_daniel"]
                st.session_state["df_dirty_daniel"] = False

                st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.info("Labelplan neu von Google Drive geladen.")
                st.rerun()

    # 1) label.csv laden
    try:
        plan_file_id = _get_labelplan_file_id()
    except Exception as e:
        st.error(str(e))
        return

    try:
        df_plan_remote = _cached_load_labelplan(plan_file_id, st.session_state["labelplan_version"])
    except Exception as e:
        st.error(f"Labeling-Plan konnte nicht geladen werden: {e}")
        return

    # 1a) Session-Kopie initialisieren
    if "df_plan_daniel" not in st.session_state:
        st.session_state["df_plan_daniel"] = df_plan_remote.copy()
        st.session_state["df_dirty_daniel"] = False
        st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df_plan = st.session_state["df_plan_daniel"]

    # 2) Daniel-Spalten
    daniel_cols = _get_daniel_columns(df_plan)
    if not daniel_cols:
        st.error("Im Labeling-Plan wurden keine Spalten vom Typ `Daniel__<Kategorie>` gefunden.")
        return

    # Mapping cat -> col
    cat_to_col: Dict[str, str] = {}
    for col in daniel_cols:
        cat_name = col.split("Daniel__", 1)[1].lstrip("_")
        cat_to_col[cat_name] = col

    # Kategorien-Konfiguration
    categories_cfg = _get_categories_cached()

    categories: List[str] = []
    for cat in cat_to_col.keys():
        if cat not in categories_cfg:
            categories_cfg[cat] = {}
        categories.append(cat)

    # 3) Progress + Skips
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

    # 4) README Index
    readme_index = _cached_readme_index(LABEL_CORPUS_DRIVE_FOLDER_ID, st.session_state["readme_index_version"])
    if not readme_index:
        st.error("Im Korpus-Ordner auf Google Drive wurden keine README-Dateien gefunden.")
        return

    # 5) Aktuelles README bestimmen
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
            "Nutze in ⚙️ den Button **„Korpus-Dateiliste neu laden“**, falls du gerade Dateien kopiert hast."
        )
        return

    try:
        raw_text = _cached_load_readme_text(file_id)
    except Exception as e:
        st.error(f"README `{filename}` konnte nicht von Google Drive geladen werden: {e}")
        return

    # Frontmatter entfernen (optional)
    text = _strip_frontmatter(raw_text)

    st.markdown(f"**Aktuelles README:** `{filename}` ({current_index+1}/{prog['total_docs']})")
    st.caption(f"doc_id: `{doc_id}` – Korpus: `{CORPUS_NAME}` – Plan: `label.csv`")

    # 6) Keyword highlighting
    color_palette = [
        "#ffe58a", "#ffcccc", "#cce5ff", "#d5f5e3",
        "#f9e79f", "#f5cba7", "#d7bde2", "#aed6f1",
    ]
    cat_to_color: Dict[str, str] = {}
    for i, cat in enumerate(categories):
        cat_to_color[cat] = color_palette[i % len(color_palette)]

    cat_to_keywords = _collect_positive_keywords_by_category(categories_cfg, categories)

    kw_color_pairs: List[Dict[str, str]] = []
    for cat, kws in cat_to_keywords.items():
        color = cat_to_color.get(cat, "#ffe58a")
        for kw in kws:
            kw_color_pairs.append({"keyword": kw, "color": color})

    st.markdown("#### README-Inhalt (mit Keyword-Highlighting)")
    _render_readme_box(text, kw_color_pairs)

    # Legende
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
                            display:inline-block;width:14px;height:14px;border-radius:3px;
                            background-color:{color};border:1px solid #999;"></span>
                        <span>{html.escape(cat)}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("_Hinweis: Wörter werden je nach Kategorie verschieden eingefärbt. Labels trotzdem immer manuell vergeben._")

    # 7) Labeling UI (✅/❓/❌ oder ✅/❌) – Icons nicht im Titel
    st.markdown("### Labels vergeben")

    with st.expander("ℹ️ Abkürzungen (Labels)", expanded=False):
        st.markdown(
            "- **✅** = Ausreichend\n"
            "- **❓** = Unklar (nur bei *Data Provenance* und *Data Preparation & Processing*)\n"
            "- **❌** = Unzureichend\n"
            "- **—** = nicht gesetzt\n\n"
            "**Speicherwerte (in label.csv):**\n"
            "- ternär: ✅=2, ❓=1, ❌=0\n"
            "- binär: ✅=1, ❌=0"
        )

    label_widgets: Dict[str, str] = {}

    # kompakt wie local: 3 pro Reihe
    per_row = 3
    for start in range(0, len(categories), per_row):
        row_cats = categories[start:start + per_row]
        cols = st.columns(len(row_cats))

        for cat, col in zip(row_cats, cols):
            with col:
                plan_col = cat_to_col[cat]
                existing = row.get(plan_col, None)

                options = _label_options_for_category(cat)
                default_choice = _format_existing_label_for_ui(cat, existing)
                if default_choice not in options:
                    default_choice = "—"

                ui_label = f"{cat}"

                label_widgets[cat] = st.segmented_control(
                    label=ui_label,
                    options=options,
                    default=default_choice,
                    key=f"{doc_id}__{cat}__daniel_v2",
                )

    # 8) Save local + next / skip
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Label lokal speichern & nächste README", key="dl_save_next"):
            mask_doc = df_plan["doc_id"].astype(str) == str(doc_id)
            if not mask_doc.any():
                st.error("Aktuelle doc_id wurde im Labelplan nicht gefunden.")
            else:
                any_changed = False
                for cat in categories:
                    choice = label_widgets.get(cat, "—")
                    parsed = _parse_label_choice(cat, choice)
                    if parsed is None:
                        continue  # nicht gesetzt -> nichts ändern
                    plan_col = cat_to_col[cat]
                    df_plan.loc[mask_doc, plan_col] = int(parsed)
                    any_changed = True

                st.session_state["df_plan_daniel"] = df_plan
                if any_changed:
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

    # 9) Sync to Drive (nur Daniel-Spalten)
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
                    df_remote = load_csv_from_drive(plan_file_id)
                    if "doc_id" not in df_remote.columns:
                        st.error("In der Labelplan-Datei auf Drive fehlt die Spalte `doc_id`.")
                    else:
                        daniel_cols_remote = _get_daniel_columns(df_local)

                        df_remote = df_remote.copy()
                        df_remote.set_index("doc_id", inplace=True)
                        df_local_idx = df_local.set_index("doc_id")

                        # Update nur Daniel-Spalten
                        df_remote.update(df_local_idx[daniel_cols_remote])
                        df_remote.reset_index(inplace=True)

                        save_csv_to_drive(df_remote, plan_file_id)

                        st.session_state["df_dirty_daniel"] = False
                        st.session_state["labelplan_version"] += 1
                        st.session_state["daniel_labelplan_last_loaded"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        try:
                            _cached_load_labelplan.clear()
                        except Exception:
                            pass

                        st.success("Daniel-Labels erfolgreich nach Google Drive hochgeladen (nur Daniel-Spalten).")
                        st.rerun()

                except Exception as e:
                    st.error(f"Fehler beim Hochladen nach Drive: {e}")

    # 10) Jump
    st.markdown("---")
    st.markdown("### Zu bestimmter README springen")

    doc_options = df_plan.sort_values("doc_index")[["doc_index", "filename", "doc_id"]].values.tolist()

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