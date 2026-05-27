# NetScout — Home Lab Network Scanner
#
# Build:  docker build -t netscout .
# Run:    see docker-compose.yml for the recommended setup (host network
#         or macvlan is required for ARP scanning to work).

FROM python:3.12-slim

# System packages: SNMP tools for switch/AP queries, libpcap for scapy,
# iputils for ping latency, iproute2 for interface detection.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpcap0.8 \
        iputils-ping \
        iputils-arping \
        iproute2 \
        snmp \
        net-tools \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY netscout/   ./netscout/
COPY templates/  ./templates/
COPY static/     ./static/
COPY run.py      ./

# Persist devices.json and oui.txt across container restarts via this volume
VOLUME ["/data"]
ENV NETSCOUT_DATA_DIR=/data

EXPOSE 80

CMD ["python", "-u", "run.py"]
