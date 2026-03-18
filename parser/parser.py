import re

def analyze_debug(text):

    result = {
        "src_ip": None,
        "dst_ip": None,
        "src_port": None,
        "dst_port": None,
        "in_intf": None,
        "out_intf": None,
        "policy": None,
        "snat": None,
        "action": None,
        "npu": "No",
        "diagnosis": "Não foi possível identificar completamente"
    }

    lines = text.splitlines()

    for line in lines:

        # 🔹 IPs e portas
        if "received a packet" in line:
            m = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)->(\d+\.\d+\.\d+\.\d+):(\d+)', line)
            if m:
                result["src_ip"] = m.group(1)
                result["src_port"] = m.group(2)
                result["dst_ip"] = m.group(3)
                result["dst_port"] = m.group(4)

            intf = re.search(r'from (\S+)', line)
            if intf:
                result["in_intf"] = intf.group(1)

        # 🔹 Interface de saída
        if "find a route" in line:
            out = re.search(r'via (\S+)', line)
            if out:
                result["out_intf"] = out.group(1)

        # 🔹 Policy
        if "Allowed by Policy" in line:
            p = re.search(r'Policy-(\d+)', line)
            if p:
                result["policy"] = p.group(1)
                result["action"] = "ACCEPT"

        if "Denied by forward policy check" in line:
            result["action"] = "DENY"

        # 🔹 NAT
        if "SNAT" in line:
            sn = re.search(r'->(\d+\.\d+\.\d+\.\d+)', line)
            if sn:
                result["snat"] = sn.group(1)

        # 🔹 NPU
        if "npu session installation succeeded" in line:
            result["npu"] = "Yes"

    # 🧠 Diagnóstico inteligente

    if result["action"] == "DENY":
        result["diagnosis"] = "❌ Bloqueado por Firewall Policy"

    elif not result["policy"]:
        result["diagnosis"] = "❌ Nenhuma policy casou"

    elif not result["out_intf"]:
        result["diagnosis"] = "❌ Problema de roteamento"

    elif result["action"] == "ACCEPT":
        result["diagnosis"] = "✅ Tráfego permitido pelo firewall. Verificar aplicação/DNS/UTM se não funcionar"

    return result
