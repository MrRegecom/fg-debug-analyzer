import re
from collections import defaultdict


PROTO_MAP = {
    "6": "TCP",
    "17": "UDP",
    "1": "ICMP",
}


def clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().strip(' ."[]')


def proto_name(proto_num: str) -> str:
    return PROTO_MAP.get(str(proto_num), f"PROTO-{proto_num}")


def normalize_debug_text(text: str) -> list[str]:
    """
    Normaliza logs colados em uma única linha, quebrando antes de cada bloco id=... trace_id=...
    """
    text = text.replace("\r", " ")
    text = re.sub(r"\s+(?=id=\d+\s+trace_id=\d+\s+func=)", "\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def build_empty_record() -> dict:
    return {
        "sessionId": None,
        "traceIds": set(),
        "sourceIP": None,
        "sourcePort": None,
        "destinationIP": None,
        "destinationPort": None,
        "protocolType": None,
        "sourceInterface": None,
        "destinationInterface": None,
        "gateway": None,
        "finalRoute": None,
        "policyIdFinal": None,
        "policyRouteId": None,
        "natType": "NONE",
        "snatIP": None,
        "dnatMatched": False,
        "actionFinal": None,
        "vdom": None,
        "npuOffload": "No",
        "tcpFlags": None,
        "diagnosis": "Análise incompleta",
    }


def get_or_create_record(trace_id: str, trace_map: dict, session_map: dict) -> dict:
    if trace_id in trace_map:
        return trace_map[trace_id]

    rec = build_empty_record()
    trace_map[trace_id] = rec
    return rec


def finalize_record(rec: dict) -> dict:
    rec["traceIds"] = ", ".join(sorted(rec["traceIds"], key=lambda x: int(x))) if rec["traceIds"] else None

    # Final route amigável
    if rec.get("gateway") and rec.get("destinationInterface"):
        rec["finalRoute"] = f'{rec["gateway"]} via {rec["destinationInterface"]}'
    elif rec.get("gateway"):
        rec["finalRoute"] = rec["gateway"]
    elif rec.get("destinationInterface"):
        rec["finalRoute"] = rec["destinationInterface"]

    # NAT type
    if rec.get("snatIP") and rec.get("dnatMatched"):
        rec["natType"] = "SNAT+DNAT"
    elif rec.get("snatIP"):
        rec["natType"] = "SNAT"
    elif rec.get("dnatMatched"):
        rec["natType"] = "DNAT"
    else:
        rec["natType"] = "NONE"

    # Diagnosis
    if rec["actionFinal"] == "DENY":
        rec["diagnosis"] = "Bloqueado por firewall policy"
    elif rec["actionFinal"] == "ACCEPT":
        rec["diagnosis"] = "Tráfego permitido pelo firewall; se falhar, investigar Security Logs, DNS ou aplicação"
    elif rec["sourceIP"] and not rec["destinationInterface"]:
        rec["diagnosis"] = "Tráfego chegou ao firewall, mas não foi encontrada rota/interface de saída"
    elif rec["sourceIP"] and not rec["policyIdFinal"]:
        rec["diagnosis"] = "Tráfego chegou ao firewall, mas nenhuma policy final foi identificada"
    else:
        rec["diagnosis"] = "Análise incompleta"

    return rec


def parse_debug_sessions(text: str) -> list[dict]:
    lines = normalize_debug_text(text)

    trace_map: dict[str, dict] = {}
    session_map: dict[str, dict] = {}

    for line in lines:
        trace_m = re.search(r"trace_id=(\d+)", line)
        if not trace_m:
            continue

        trace_id = trace_m.group(1)
        rec = get_or_create_record(trace_id, trace_map, session_map)
        rec["traceIds"].add(trace_id)

        # VDOM / pacote inicial / interfaces / flags / protocolo / IPs / portas
        pkt = re.search(
            r'received a packet\(proto=(\d+),\s*'
            r'(\d+\.\d+\.\d+\.\d+):(\d+)->(\d+\.\d+\.\d+\.\d+):(\d+)'
            r'.*?from\s+([A-Za-z0-9_\-\.]+)\.\s*flag\s+\[([^\]]+)\]',
            line
        )
        if pkt:
            rec["protocolType"] = proto_name(pkt.group(1))
            rec["sourceIP"] = pkt.group(2)
            rec["sourcePort"] = pkt.group(3)
            rec["destinationIP"] = pkt.group(4)
            rec["destinationPort"] = pkt.group(5)
            rec["sourceInterface"] = clean_value(pkt.group(6))
            rec["tcpFlags"] = pkt.group(7)

        # VDOM
        vdom_m = re.search(r'vd-([A-Za-z0-9_\-]+):', line)
        if vdom_m:
            rec["vdom"] = clean_value(vdom_m.group(1))

        # Session allocation
        sess_new = re.search(r'allocate a new session-([A-Za-z0-9]+)', line)
        if sess_new:
            sid = sess_new.group(1)
            rec["sessionId"] = sid
            session_map[sid] = rec

        # Existing session association
        sess_existing = re.search(r'Find an existing session,\s*id-([A-Za-z0-9]+)', line)
        if sess_existing:
            sid = sess_existing.group(1)
            if sid in session_map:
                # reaponta este trace_id para o mesmo registro
                trace_map[trace_id] = session_map[sid]
                rec = session_map[sid]
                rec["traceIds"].add(trace_id)
                rec["sessionId"] = sid

        # Policy route
        policy_route = re.search(r'Match policy routing id=(\d+):.*?via\s+([A-Za-z0-9_\-\.]+)', line)
        if policy_route:
            rec["policyRouteId"] = policy_route.group(1)
            candidate = clean_value(policy_route.group(2))
            # Não usar ifindex como interface final amigável
            if candidate and not candidate.startswith("ifindex-"):
                rec["destinationInterface"] = candidate

        # Final route + gateway
        route = re.search(r'find a route:.*?gw-(\d+\.\d+\.\d+\.\d+)\s+via\s+([A-Za-z0-9_\-\.]+)', line)
        if route:
            rec["gateway"] = route.group(1)
            candidate = clean_value(route.group(2))
            if candidate and not candidate.startswith("ifindex-"):
                rec["destinationInterface"] = candidate

        # Preferir out-[INTERFACE]
        out_if = re.search(r'out-\[([^\]]+)\]', line)
        if out_if:
            rec["destinationInterface"] = clean_value(out_if.group(1))

        # DNAT detection
        if "iprope_dnat_check" in line and "ret-matched" in line:
            rec["dnatMatched"] = True
        if "DNAT" in line:
            rec["dnatMatched"] = True

        # Policy matched final
        allowed = re.search(r'Allowed by Policy-(\d+)', line)
        if allowed:
            rec["policyIdFinal"] = allowed.group(1)
            rec["actionFinal"] = "ACCEPT"

        deny = re.search(r'Denied by forward policy check', line)
        if deny:
            rec["actionFinal"] = "DENY"

        # Fallback: pega policy matched se ainda não tiver a final
        if rec["policyIdFinal"] is None:
            pol_match = re.search(r'policy-(\d+)\s+is matched,\s*act-accept', line)
            if pol_match:
                rec["policyIdFinal"] = pol_match.group(1)

        # SNAT
        snat = re.search(r'SNAT\s+\d+\.\d+\.\d+\.\d+->(\d+\.\d+\.\d+\.\d+):(\d+)', line)
        if snat:
            rec["snatIP"] = snat.group(1)

        # NPU
        if "npu session installation succeeded" in line:
            rec["npuOffload"] = "Yes"

    # Deduplicar por object id do registro
    unique_records = []
    seen_ids = set()
    for rec in trace_map.values():
        oid = id(rec)
        if oid not in seen_ids:
            seen_ids.add(oid)
            unique_records.append(finalize_record(rec))

    return unique_records
