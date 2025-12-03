import streamlit as st

# Tabs importieren
from tabs.ai_act_mapping import show_ai_act_mapping
from tabs.categories import show_categories
from tabs.labeling_daniel import show_labeling_daniel
from tabs.labeling_marie import show_labeling_marie

def main():
    st.set_page_config(page_title="AI Act Labeling Tool", layout="wide")

    st.title("AI Act Labeling – Main App")

    tabs = [
        "AI Act Mapping",
        "Categories",
        "Labeling Daniel",
        "Labeling Marie",
    ]

    selected_tab = st.tabs(tabs)

    # Jede Tab-Funktion einem Tab zuordnen
    with selected_tab[0]:
        show_ai_act_mapping()

    with selected_tab[1]:
        show_categories()

    with selected_tab[2]:
        show_labeling_daniel()

    with selected_tab[3]:
        show_labeling_marie()


if __name__ == "__main__":
    main()