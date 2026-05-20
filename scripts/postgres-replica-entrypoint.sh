#!/usr/bin/env sh
set -eu

pgdata="${PGDATA:-/var/lib/postgresql/data}"
primary_host="${POSTGRES_PRIMARY_HOST:-postgres}"
primary_port="${POSTGRES_PRIMARY_PORT:-5432}"
slot="${POSTGRES_REPLICATION_SLOT:-dune_standby}"
repl_user="${POSTGRES_REPLICATION_USER:-dune_replicator}"

if [ -z "${POSTGRES_REPLICATION_PASSWORD:-}" ]; then
  echo "POSTGRES_REPLICATION_PASSWORD is required" >&2
  exit 1
fi

mkdir -p "$pgdata"
chown -R postgres:postgres "$pgdata"
chmod 700 "$pgdata"

if [ ! -s "$pgdata/PG_VERSION" ]; then
  echo "initializing standby from ${primary_host}:${primary_port} slot ${slot}"
  rm -rf "$pgdata"/*
  export PGPASSWORD="$POSTGRES_REPLICATION_PASSWORD"
  until pg_isready -h "$primary_host" -p "$primary_port" -U "$repl_user"; do
    sleep 2
  done
  gosu postgres pg_basebackup \
    -h "$primary_host" \
    -p "$primary_port" \
    -U "$repl_user" \
    -D "$pgdata" \
    -Fp \
    -Xs \
    -P \
    -R \
    -S "$slot"
fi

exec gosu postgres postgres -D "$pgdata"
