import streamlit as st
import pandas as pd
from parser.parser import analyze_debug

st.set_page_config(page_title="FG Debug Analyzer", layout="wide")

st.title("🔥 FortiGate Debug Analyzer")

st.markdown("Cole o debug flow abaixo para análise completa:")

debug_text = st.text_area("Debug Flow", height=300)

if st.button("Analisar"):

    if not debug_text.strip():
        st.warning("Cole um debug válido.")
    else:
        result = analyze_debug(debug_text)

        # 🔹 RESUMO
        st.subheader("📊 Resumo da Sessão")

        col1, col2, col3 = st.columns(3)

        col1.metric("Origem", result.get("src_ip"))
        col1.metric("Destino", result.get("dst_ip"))
        col1.metric("Porta", result.get("dst_port"))

        col2.metric("Entrada", result.get("in_intf"))
        col2.metric("Saída", result.get("out_intf"))
        col2.metric("Policy", result.get("policy"))

        col3.metric("NAT", result.get("snat"))
        col3.metric("Ação", result.get("action"))
        col3.metric("NPU Offload", result.get("npu"))

        # 🔹 DIAGNÓSTICO
        st.subheader("🧠 Diagnóstico")

        st.info(result.get("diagnosis"))

        # 🔹 DETALHES
        st.subheader("📋 Detalhes Técnicos")

        df = pd.DataFrame(result.items(), columns=["Campo", "Valor"])
        st.dataframe(df)

        # 🔹 DEBUG BRUTO
        st.subheader("📜 Debug Bruto")
        st.text(debug_text)
