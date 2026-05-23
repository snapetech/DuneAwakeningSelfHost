#!/usr/bin/env bash
set -euo pipefail

# Example firewalld rules for the 30-partition warm-pool layout.
# Review before running. This intentionally does not expose the admin panel.

sudo firewall-cmd --add-port=7777-7810/udp --permanent
sudo firewall-cmd --add-port=7888-7918/udp --permanent
sudo firewall-cmd --add-port=31982/tcp --permanent
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
