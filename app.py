import streamlit as st
from parser.parser import parse_debug_flow

st.title("FG Debug Analyzer")

uploaded_file = st.file_uploader("Upload debug flow", type=["txt"])

if uploaded_file:
    content = uploaded_file.read().decode("utf-8")

    st.subheader("Debug bruto")
    st.text(content)

    sessions = parse_debug_flow(content)

    st.subheader("Sessões encontradas")

    if sessions:
        for s in sessions:
            st.write(s)
    else:
        st.warning("Nenhuma sessão encontrada")
