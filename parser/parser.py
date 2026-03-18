import re

def parse_debug_flow(text):
    sessions = []

    lines = text.splitlines()

    for line in lines:
        if "received a packet" in line:
            match = re.search(
                r'(\d+\.\d+\.\d+\.\d+):(\d+)->(\d+\.\d+\.\d+\.\d+):(\d+)',
                line
            )

            if match:
                session = {
                    "src_ip": match.group(1),
                    "src_port": match.group(2),
                    "dst_ip": match.group(3),
                    "dst_port": match.group(4),
                    "raw": line
                }

                sessions.append(session)

    return sessions
