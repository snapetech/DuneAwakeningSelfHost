#!/usr/bin/env bash
set -euo pipefail

# Example UFW rules for the 30-partition warm-pool layout.
# Review before running. This intentionally does not expose the admin panel.

sudo ufw allow 7777:7806/udp comment 'Dune 30-map game UDP'
sudo ufw allow 31982/tcp comment 'Dune game RabbitMQ client login'
sudo ufw status numbered
