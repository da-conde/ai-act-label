import streamlit as st

import tabs.ai_act_mapping as ai_act_mapping_tab
import tabs.categories as categories_tab
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

    st_tabs = st.tabs(tabs)

    # 1) AI Act Mapping Tab
    with st_tabs[0]:
        ai_act_mapping_tab.render()

    # 2) Categories Tab
    with st_tabs[1]:
        categories_tab.render()

    # 3) Labeling Daniel Tab
    with st_tabs[2]:
        show_labeling_daniel()

    # 4) Labeling Marie Tab
    with st_tabs[3]:
        show_labeling_marie()


if __name__ == "__main__":
    main()