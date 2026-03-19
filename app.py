import streamlit as st
import pandas as pd
from parser.parser import parse_debug_sessions

st.set_page_config(page_title="FortiGate Debug Analyzer", layout="wide")

st.title("🔥 FortiGate Debug Analyzer")
st.caption("Cole abaixo um output de diagnose debug flow para análise fim a fim.")

debug_text = st.text_area("Debug Flow", height=260)

if st.button("Analisar"):
    if not debug_text.strip():
        st.warning("Cole um debug válido.")
        st.stop()

    sessions = parse_debug_sessions(debug_text)

    if not sessions:
        st.error("Nenhuma sessão identificada no debug.")
        st.stop()

    df = pd.DataFrame(sessions)

    ordered_cols = [
        "sessionId",
        "traceIds",
        "sourceIP",
        "sourcePort",
        "protocolType",
        "destinationIP",
        "destinationPort",
        "sourceInterface",
        "destinationInterface",
        "policyIdFinal",
        "policyRouteId",
        "gateway",
        "finalRoute",
        "natType",
        "snatIP",
        "actionFinal",
        "vdom",
        "npuOffload",
        "tcpFlags",
        "diagnosis",
    ]
    df = df[[c for c in ordered_cols if c in df.columns]]

    st.subheader("📋 Sessões encontradas")

    c1, c2, c3, c4 = st.columns(4)

    src_options = sorted([x for x in df["sourceIP"].dropna().unique().tolist()]) if "sourceIP" in df else []
    dst_options = sorted([x for x in df["destinationIP"].dropna().unique().tolist()]) if "destinationIP" in df else []
    proto_options = sorted([x for x in df["protocolType"].dropna().unique().tolist()]) if "protocolType" in df else []
    action_options = sorted([x for x in df["actionFinal"].dropna().unique().tolist()]) if "actionFinal" in df else []

    src_filter = c1.selectbox("Filtrar por Source IP", options=["Todos"] + src_options)
    dst_filter = c2.selectbox("Filtrar por Destination IP", options=["Todos"] + dst_options)
    proto_filter = c3.selectbox("Filtrar por Protocolo", options=["Todos"] + proto_options)
    action_filter = c4.selectbox("Filtrar por Ação", options=["Todos"] + action_options)

    if src_filter != "Todos":
        df = df[df["sourceIP"] == src_filter]
    if dst_filter != "Todos":
        df = df[df["destinationIP"] == dst_filter]
    if proto_filter != "Todos":
        df = df[df["protocolType"] == proto_filter]
    if action_filter != "Todos":
        df = df[df["actionFinal"] == action_filter]

    st.dataframe(df, use_container_width=True, hide_index=True)

    if df.empty:
        st.warning("Nenhuma sessão corresponde aos filtros selecionados.")
        st.stop()

    df = df.copy()
    df["sessionLabel"] = df.apply(
        lambda row: f'{row.get("sourceIP", "?")}:{row.get("sourcePort", "?")} -> '
                    f'{row.get("destinationIP", "?")}:{row.get("destinationPort", "?")} | '
                    f'Policy {row.get("policyIdFinal", "-")} | {row.get("actionFinal", "-")}',
        axis=1
    )

    selected_label = st.selectbox("Selecione uma sessão para detalhar", df["sessionLabel"].tolist())
    selected = df[df["sessionLabel"] == selected_label].iloc[0].to_dict()

    st.subheader("📊 Resumo da Sessão")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Source IP", selected.get("sourceIP", "-"))
    r1.metric("Source Port", str(selected.get("sourcePort", "-")))
    r1.metric("Protocol", selected.get("protocolType", "-"))

    r2.metric("Destination IP", selected.get("destinationIP", "-"))
    r2.metric("Destination Port", str(selected.get("destinationPort", "-")))
    r2.metric("Action", selected.get("actionFinal", "-"))

    r3.metric("Source Interface", selected.get("sourceInterface", "-"))
    r3.metric("Destination Interface", selected.get("destinationInterface", "-"))
    r3.metric("Policy ID Final", str(selected.get("policyIdFinal", "-")))

    r4.metric("Gateway", selected.get("gateway", "-"))
    r4.metric("NAT Type", selected.get("natType", "-"))
    r4.metric("NPU Offload", selected.get("npuOffload", "-"))

    st.subheader("🧠 Diagnóstico")
    st.info(selected.get("diagnosis", "Sem diagnóstico"))

    st.subheader("🧾 Detalhes Técnicos da Sessão")
    detail_df = pd.DataFrame(
        [{"Campo": k, "Valor": v} for k, v in selected.items() if k != "sessionLabel"]
    )
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

    with st.expander("📜 Ver debug bruto colado"):
        st.code(debug_text, language="text")
