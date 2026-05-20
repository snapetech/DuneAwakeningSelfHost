#!/usr/bin/env bash
set -euo pipefail

# Example UFW rules for a single Survival_1 layout.
# Review before running. This intentionally does not expose the admin panel.

sudo ufw allow 7777/udp comment 'Dune Survival_1 game UDP'
sudo ufw allow 31982/tcp comment 'Dune game RabbitMQ client login'
sudo ufw status numbered
