import re

PROTO_MAP = {
    "6": "TCP",
    "17": "UDP",
    "1": "ICMP",
}


def clean_value(value):
    if value is None:
        return None
    return value.strip().strip(' ."[]')


def proto_name(proto_num):
    return PROTO_MAP.get(str(proto_num), f"PROTO-{proto_num}")


def normalize_debug_text(text):
    text = text.replace("\r", " ")
    text = re.sub(r"\s+(?=id=\d+\s+trace_id=\d+\s+func=)", "\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def build_empty_record():
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


def finalize_record(rec):
    rec["traceIds"] = ", ".join(sorted(rec["traceIds"], key=lambda x: int(x))) if rec["traceIds"] else None

    if rec.get("gateway") and rec.get("destinationInterface"):
        rec["finalRoute"] = f'{rec["gateway"]} via {rec["destinationInterface"]}'
    elif rec.get("gateway"):
        rec["finalRoute"] = rec["gateway"]
    elif rec.get("destinationInterface"):
        rec["finalRoute"] = rec["destinationInterface"]

    if rec.get("snatIP") and rec.get("dnatMatched"):
        rec["natType"] = "SNAT+DNAT"
    elif rec.get("snatIP"):
        rec["natType"] = "SNAT"
    elif rec.get("dnatMatched"):
        rec["natType"] = "DNAT"
    else:
        rec["natType"] = "NONE"

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


def parse_debug_sessions(text):
    lines = normalize_debug_text(text)

    trace_map = {}
    session_map = {}

    for line in lines:
        trace_m = re.search(r"trace_id=(\d+)", line)
        if not trace_m:
            continue

        trace_id = trace_m.group(1)

        if trace_id in trace_map:
            rec = trace_map[trace_id]
        else:
            rec = build_empty_record()
            trace_map[trace_id] = rec

        rec["traceIds"].add(trace_id)

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

        vdom_m = re.search(r'vd-([A-Za-z0-9_\-]+):', line)
        if vdom_m:
            rec["vdom"] = clean_value(vdom_m.group(1))

        sess_new = re.search(r'allocate a new session-([A-Za-z0-9]+)', line)
        if sess_new:
            sid = sess_new.group(1)
            rec["sessionId"] = sid
            session_map[sid] = rec

        sess_existing = re.search(r'Find an existing session,\s*id-([A-Za-z0-9]+)', line)
        if sess_existing:
            sid = sess_existing.group(1)
            if sid in session_map:
                trace_map[trace_id] = session_map[sid]
                rec = session_map[sid]
                rec["traceIds"].add(trace_id)
                rec["sessionId"] = sid

        policy_route = re.search(r'Match policy routing id=(\d+):.*?via\s+([A-Za-z0-9_\-\.]+)', line)
        if policy_route:
            rec["policyRouteId"] = policy_route.group(1)
            candidate = clean_value(policy_route.group(2))
            if candidate and not candidate.startswith("ifindex-"):
                rec["destinationInterface"] = candidate

        route = re.search(r'find a route:.*?gw-(\d+\.\d+\.\d+\.\d+)\s+via\s+([A-Za-z0-9_\-\.]+)', line)
        if route:
            rec["gateway"] = route.group(1)
            candidate = clean_value(route.group(2))
            if candidate and not candidate.startswith("ifindex-"):
                rec["destinationInterface"] = candidate

        out_if = re.search(r'out-\[([^\]]+)\]', line)
        if out_if:
            rec["destinationInterface"] = clean_value(out_if.group(1))

        if "iprope_dnat_check" in line and "ret-matched" in line:
            rec["dnatMatched"] = True
        if "DNAT" in line:
            rec["dnatMatched"] = True

        allowed = re.search(r'Allowed by Policy-(\d+)', line)
        if allowed:
            rec["policyIdFinal"] = allowed.group(1)
            rec["actionFinal"] = "ACCEPT"

        if "Denied by forward policy check" in line:
            rec["actionFinal"] = "DENY"

        if rec["policyIdFinal"] is None:
            pol_match = re.search(r'policy-(\d+)\s+is matched,\s*act-accept', line)
            if pol_match:
                rec["policyIdFinal"] = pol_match.group(1)

        snat = re.search(r'SNAT\s+\d+\.\d+\.\d+\.\d+->(\d+\.\d+\.\d+\.\d+):(\d+)', line)
        if snat:
            rec["snatIP"] = snat.group(1)

        if "npu session installation succeeded" in line:
            rec["npuOffload"] = "Yes"

    unique_records = []
    seen_ids = set()

    for rec in trace_map.values():
        oid = id(rec)
        if oid not in seen_ids:
            seen_ids.add(oid)
            unique_records.append(finalize_record(rec))

    return unique_records
