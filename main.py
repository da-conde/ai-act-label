import streamlit as st

from tabs.ai_act_mapping import show_ai_act_mapping
from tabs.labeling_daniel import show_labeling_daniel
from tabs.labeling_marie import show_labeling_marie
import tabs.categories as categories_tab  # <-- wichtig für render()


def main():
    st.set_page_config(page_title="AI Act Labeling Tool", layout="wide")

    st.title("AI Act Labeling – Main App")

    tabs = [
        "AI Act Mapping",
        "Categories",
        "Labeling Daniel",
        "Labeling Marie",
    ]

    st_tabs = st.tabs(tabs)

    with st_tabs[0]:
        show_ai_act_mapping()

    with st_tabs[1]:
        # nutzt deine render()-Funktion aus tabs/categories.py
        categories_tab.render()

    with st_tabs[2]:
        show_labeling_daniel()

    with st_tabs[3]:
        show_labeling_marie()


if __name__ == "__main__":
    main()