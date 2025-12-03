import json
from typing import Dict, Any, List

import streamlit as st

from utils.gdrive import load_json_from_drive, save_json_to_drive

# ----------------------------------------------------
# Google Drive Konfiguration
# ----------------------------------------------------

# File-ID deiner categories.json auf Google Drive
CATEGORIES_DRIVE_FILE_ID = "1EmZHSfSwbEw4JYsyRYvVBSbY4g4FSOi5"


# ----------------------------------------------------
# Hilfsfunktionen: Laden / Speichern
# ----------------------------------------------------

def _load_categories() -> Dict[str, Any]:
    """
    Lädt die Kategorien aus der JSON-Datei auf Google Drive.
    Erwartet eine Struktur wie:
    {
      "Data_Source": { ... },
      "Synthetic_Disclosure": { ... },
      ...
    }
    """
    try:
        data = load_json_from_drive(CATEGORIES_DRIVE_FILE_ID)

        if isinstance(data, dict):
            return data
        else:
            st.warning(
                "Die Datei `categories.json` auf Google Drive enthält kein Dict auf oberster Ebene."
            )
            return {}
    except Exception as e:
        st.error(f"Fehler beim Laden von Kategorien aus Google Drive: {e}")
        return {}


def _save_categories(categories: Dict[str, Any]) -> None:
    """
    Speichert die Kategorien zurück in die JSON-Datei auf Google Drive.
    """
    try:
        save_json_to_drive(categories, CATEGORIES_DRIVE_FILE_ID)
    except Exception as e:
        st.error(f"Fehler beim Speichern von Kategorien nach Google Drive: {e}")


# ----------------------------------------------------
# Hilfsfunktionen: List <-> Multiline-String
# ----------------------------------------------------

def _list_to_multiline(values: List[str]) -> str:
    if not values:
        return ""
    return "\n".join(v for v in values if v is not None)


def _multiline_to_list(text: str) -> List[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


# ----------------------------------------------------
# Render-Funktion für den Tab
# ----------------------------------------------------

def render():
    st.subheader("🏷️ Kategorien & Keywords")

    st.caption(
        """
        Hier verwaltest du deine **Labeling-Kategorien** und die zugehörigen
        **Such-Queries** und **Satz-Keywords**.
        
        - Die Daten werden in einer `categories.json` Datei auf **Google Drive** gespeichert.
        - Du kannst **neue Kategorien anlegen** oder **bestehende bearbeiten / löschen**.
        """
    )

    # Kategorien aus Google Drive laden
    categories = _load_categories()

    # ------------------------------------------------
    # Übersicht vorhandener Kategorien
    # ------------------------------------------------
    with st.expander("📚 Überblick: vorhandene Kategorien", expanded=True):
        if not categories:
            st.info(
                "Es sind aktuell noch keine Kategorien in `categories.json` auf Google Drive definiert."
            )
        else:
            st.write(f"**Anzahl Kategorien:** {len(categories)}")
            st.write(", ".join(sorted(categories.keys())))

    st.markdown("---")

    # Zwei Spalten: links neue Kategorie, rechts vorhandene bearbeiten
    col_new, col_edit = st.columns(2)

    # ================================================================
    # 1) Neue Kategorie anlegen
    # ================================================================
    with col_new:
        st.markdown("### ➕ Neue Kategorie anlegen")

        new_name = st.text_input(
            "Kategoriename (Key in JSON)",
            value="",
            key="new_cat_name",
            placeholder="z. B. Synthetic_Ethics",
        )

        label_unit_options = ["sentence", "paragraph", "document", "other"]
        new_label_unit = st.selectbox(
            "Label-Einheit (label_unit)",
            options=label_unit_options,
            index=0,
            key="new_cat_label_unit",
        )

        new_description = st.text_area(
            "Beschreibung",
            value="",
            key="new_cat_description",
            height=100,
            placeholder="Kurzbeschreibung der Kategorie (wird im Labeling angezeigt)",
        )

        st.caption(
            "**Dataset-Suchqueries (positiv / negativ)** – jeweils eine Zeile pro Eintrag"
        )
        new_ds_pos = st.text_area(
            "Dataset-Suchqueries (positiv)",
            value="",
            key="new_cat_ds_pos",
            height=120,
            placeholder="z. B.\nsynthetic dataset\nsimulation-based dataset",
        )

        new_ds_neg = st.text_area(
            "Dataset-Suchqueries (negativ)",
            value="",
            key="new_cat_ds_neg",
            height=120,
            placeholder="z. B.\nreal-world dataset\nreal data only",
        )

        st.caption(
            "**Satz-Keywords (positiv / negativ)** – jeweils eine Zeile pro Phrase"
        )
        new_sent_pos = st.text_area(
            "Satz-Keywords (positiv)",
            value="",
            key="new_cat_sent_pos",
            height=150,
            placeholder="z. B.\nthis dataset is synthetic\ncontains synthetic samples",
        )

        new_sent_neg = st.text_area(
            "Satz-Keywords (negativ)",
            value="",
            key="new_cat_sent_neg",
            height=150,
            placeholder="z. B.\nreal-world data only\nno synthetic data",
        )

        if st.button("💾 Neue Kategorie speichern", key="save_new_category"):
            name = new_name.strip()
            if not name:
                st.error("Bitte einen Kategorienamen angeben.")
            elif name in categories:
                st.error(f"Eine Kategorie mit dem Namen **{name}** existiert bereits.")
            else:
                categories[name] = {
                    "label_unit": new_label_unit,
                    "description": new_description.strip(),
                    "dataset_search_queries_positive": _multiline_to_list(new_ds_pos),
                    "dataset_search_queries_negative": _multiline_to_list(new_ds_neg),
                    "sentence_keywords_positive": _multiline_to_list(new_sent_pos),
                    "sentence_keywords_negative": _multiline_to_list(new_sent_neg),
                }
                _save_categories(categories)
                st.success(f"Neue Kategorie **{name}** gespeichert.")
                st.rerun()

    # ================================================================
    # 2) Existierende Kategorie bearbeiten
    # ================================================================
    with col_edit:
        st.markdown("### ✏️ Existierende Kategorie bearbeiten")

        if not categories:
            st.info("Noch keine Kategorien vorhanden, die bearbeitet werden könnten.")
            return

        # Auswahl der Kategorie
        category_names = sorted(categories.keys())
        selected_name = st.selectbox(
            "Kategorie auswählen",
            options=category_names,
            index=0,
            key="edit_cat_select",
        )

        selected_data = categories.get(selected_name, {})

        # Felder der ausgewählten Kategorie vorbefüllen
        edit_name = st.text_input(
            "Kategoriename (Key in JSON)",
            value=selected_name,
            key=f"edit_cat_name_{selected_name}",
        )

        label_unit_options = ["sentence", "paragraph", "document", "other"]
        current_label_unit = selected_data.get("label_unit", "sentence")
        if current_label_unit not in label_unit_options:
            current_label_unit = "sentence"

        edit_label_unit = st.selectbox(
            "Label-Einheit (label_unit)",
            options=label_unit_options,
            index=label_unit_options.index(current_label_unit),
            key=f"edit_cat_label_unit_{selected_name}",
        )

        edit_description = st.text_area(
            "Beschreibung",
            value=selected_data.get("description", ""),
            key=f"edit_cat_description_{selected_name}",
            height=100,
        )

        st.caption(
            "**Dataset-Suchqueries (positiv / negativ)** – jeweils eine Zeile pro Eintrag"
        )

        edit_ds_pos = st.text_area(
            "Dataset-Suchqueries (positiv)",
            value=_list_to_multiline(
                selected_data.get("dataset_search_queries_positive", [])
            ),
            key=f"edit_cat_ds_pos_{selected_name}",
            height=120,
        )

        edit_ds_neg = st.text_area(
            "Dataset-Suchqueries (negativ)",
            value=_list_to_multiline(
                selected_data.get("dataset_search_queries_negative", [])
            ),
            key=f"edit_cat_ds_neg_{selected_name}",
            height=120,
        )

        st.caption(
            "**Satz-Keywords (positiv / negativ)** – jeweils eine Zeile pro Phrase"
        )

        edit_sent_pos = st.text_area(
            "Satz-Keywords (positiv)",
            value=_list_to_multiline(
                selected_data.get("sentence_keywords_positive", [])
            ),
            key=f"edit_cat_sent_pos_{selected_name}",
            height=150,
        )

        edit_sent_neg = st.text_area(
            "Satz-Keywords (negativ)",
            value=_list_to_multiline(
                selected_data.get("sentence_keywords_negative", [])
            ),
            key=f"edit_cat_sent_neg_{selected_name}",
            height=150,
        )

        col_save, col_delete = st.columns(2)

        # --------------------- Speichern / Update ---------------------
        with col_save:
            if st.button("💾 Kategorie aktualisieren", key="update_category_button"):
                new_name = edit_name.strip()
                if not new_name:
                    st.error("Bitte einen Kategorienamen angeben.")
                else:
                    # Name-Kollision prüfen (falls umbenannt)
                    if new_name != selected_name and new_name in categories:
                        st.error(
                            f"Eine andere Kategorie mit dem Namen **{new_name}** existiert bereits."
                        )
                    else:
                        # Neues Payload bauen
                        new_payload = {
                            "label_unit": edit_label_unit,
                            "description": edit_description.strip(),
                            "dataset_search_queries_positive": _multiline_to_list(
                                edit_ds_pos
                            ),
                            "dataset_search_queries_negative": _multiline_to_list(
                                edit_ds_neg
                            ),
                            "sentence_keywords_positive": _multiline_to_list(
                                edit_sent_pos
                            ),
                            "sentence_keywords_negative": _multiline_to_list(
                                edit_sent_neg
                            ),
                        }

                        # Falls der Name geändert wurde: alten Key entfernen
                        if new_name != selected_name:
                            categories.pop(selected_name, None)

                        categories[new_name] = new_payload
                        _save_categories(categories)
                        st.success(f"Kategorie **{new_name}** aktualisiert.")
                        st.rerun()

        # --------------------- Löschen ---------------------
        with col_delete:
            if st.button("🗑 Kategorie löschen", key="delete_category_button"):
                categories.pop(selected_name, None)
                _save_categories(categories)
                st.warning(f"Kategorie **{selected_name}** gelöscht.")
                st.rerun()

    st.markdown("---")

    # Optional: Roh-JSON anzeigen
    with st.expander("🧾 Rohansicht Kategorien (Google Drive JSON)"):
        st.code(
            json.dumps(categories, indent=2, ensure_ascii=False, sort_keys=True),
            language="json",
        )