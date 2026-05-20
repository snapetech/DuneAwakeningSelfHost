#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
tls_dir="config/tls/rabbitmq"

if [[ -f "$env_file" ]]; then
  echo "$env_file already exists; leaving it unchanged" >&2
else
  cp .env.example "$env_file"
  postgres_super_password="$(openssl rand -hex 24)"
  postgres_dune_password="$(openssl rand -hex 24)"
  postgres_replication_password="$(openssl rand -hex 32)"
  rmq_secret="$(openssl rand -hex 64)"
  world_suffix="$(openssl rand -hex 3)"

  sed -i "s/^POSTGRES_SUPER_PASSWORD=.*/POSTGRES_SUPER_PASSWORD=$postgres_super_password/" "$env_file"
  sed -i "s/^POSTGRES_DUNE_PASSWORD=.*/POSTGRES_DUNE_PASSWORD=$postgres_dune_password/" "$env_file"
  sed -i "s/^POSTGRES_REPLICATION_PASSWORD=.*/POSTGRES_REPLICATION_PASSWORD=$postgres_replication_password/" "$env_file"
  sed -i "s/^RMQ_HTTP_TOKEN_AUTH_SECRET=.*/RMQ_HTTP_TOKEN_AUTH_SECRET=$rmq_secret/" "$env_file"
  sed -i "s/^WORLD_UNIQUE_NAME=.*/WORLD_UNIQUE_NAME=sh-example-$world_suffix/" "$env_file"
fi

mkdir -p "$tls_dir"

if [[ ! -f "$tls_dir/ca.crt" || ! -f "$tls_dir/server.crt" || ! -f "$tls_dir/server.key" ]]; then
  openssl genrsa -out "$tls_dir/ca.key" 4096
  openssl req -x509 -new -nodes -key "$tls_dir/ca.key" -sha256 -days 3650 \
    -subj "/CN=dune-example-rabbitmq-ca" \
    -out "$tls_dir/ca.crt"

  openssl genrsa -out "$tls_dir/server.key" 2048
  openssl req -new -key "$tls_dir/server.key" \
    -subj "/CN=game-rmq" \
    -out "$tls_dir/server.csr"

  cat > "$tls_dir/server.ext" <<'EOF'
subjectAltName = DNS:game-rmq,DNS:localhost,IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF

  openssl x509 -req -in "$tls_dir/server.csr" \
    -CA "$tls_dir/ca.crt" -CAkey "$tls_dir/ca.key" -CAcreateserial \
    -out "$tls_dir/server.crt" -days 3650 -sha256 \
    -extfile "$tls_dir/server.ext"

  chmod 644 "$tls_dir/server.key"
  chmod 600 "$tls_dir/ca.key"
fi

echo "Populated $env_file and $tls_dir"
echo "Next: edit $env_file and set FLS_SECRET, EXTERNAL_ADDRESS, and any world metadata."
