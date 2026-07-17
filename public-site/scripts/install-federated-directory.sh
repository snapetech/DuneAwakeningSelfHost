#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
prefix="${PREFIX:-/usr/local}"
directory_root="${DIRECTORY_ROOT:-/srv/dash-public-site/directory}"
sources_file="${DIRECTORY_SOURCES_FILE:-/etc/dash-directory-sources.json}"
env_file="${DIRECTORY_ENV_FILE:-/etc/dash-directory.env}"
user_name="${DUNE_PUBLIC_SITE_USER:-${SUDO_USER:-$USER}}"
enable=false
replace_sources=false
source_urls=()

usage() {
  echo "Usage: sudo public-site/scripts/install-federated-directory.sh [--source HTTPS_URL ...] [--replace-sources] [--enable]" >&2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) enable=true; shift ;;
    --replace-sources) replace_sources=true; shift ;;
    --source)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      source_urls+=("$2")
      shift 2
      ;;
    --help|-h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done
if [[ "$replace_sources" == true && "${#source_urls[@]}" -eq 0 ]]; then
  echo "--replace-sources requires at least one --source URL" >&2
  exit 2
fi
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root to install the directory builder." >&2; exit 1; }
id "$user_name" >/dev/null 2>&1 || { echo "directory service user does not exist: $user_name" >&2; exit 1; }

install -d -m 0755 -o "$user_name" -g "$user_name" "$directory_root"
for asset in index.html directory.css directory.js; do
  install -m 0644 "$repo_root/public-site/directory/$asset" "$directory_root/$asset"
done
install -d -m 0755 "$prefix/sbin"
install -m 0755 "$repo_root/public-site/scripts/build-federated-directory.py" "$prefix/sbin/build-federated-directory.py"
install -m 0755 "$repo_root/public-site/scripts/configure-federated-directory-sources.py" "$prefix/sbin/configure-federated-directory-sources.py"
install -m 0755 "$repo_root/public-site/scripts/run-federated-directory.sh" "$prefix/sbin/run-federated-directory.sh"
if [[ "${#source_urls[@]}" -gt 0 ]]; then
  configure_args=(--output "$sources_file")
  for source_url in "${source_urls[@]}"; do
    configure_args+=(--source "$source_url")
  done
  [[ "$replace_sources" == true ]] && configure_args+=(--replace)
  "$repo_root/public-site/scripts/configure-federated-directory-sources.py" "${configure_args[@]}"
elif [[ ! -e "$sources_file" ]]; then
  install -m 0644 "$repo_root/public-site/directory/sources.example.json" "$sources_file"
fi
if [[ ! -e "$env_file" ]]; then
  tmp_env="$(mktemp)"
  sed \
    -e "s#^DUNE_ROOT=.*#DUNE_ROOT=$repo_root#" \
    -e "s#^DIRECTORY_ROOT=.*#DIRECTORY_ROOT=$directory_root#" \
    -e "s#^DIRECTORY_SOURCES_FILE=.*#DIRECTORY_SOURCES_FILE=$sources_file#" \
    "$repo_root/public-site/directory/directory.env.example" >"$tmp_env"
  install -m 0644 "$tmp_env" "$env_file"
  rm -f "$tmp_env"
fi

tmp_service="$(mktemp)"
trap 'rm -f "$tmp_service"' EXIT
sed \
  -e "s#^User=.*#User=$user_name#" \
  -e "s#^EnvironmentFile=.*#EnvironmentFile=-$env_file#" \
  -e "s#^ExecStart=.*#ExecStart=$prefix/sbin/run-federated-directory.sh#" \
  -e "s#^ReadWritePaths=.*#ReadWritePaths=$directory_root#" \
  "$repo_root/public-site/systemd/build-dash-federated-directory.service" >"$tmp_service"
install -m 0644 "$tmp_service" /etc/systemd/system/build-dash-federated-directory.service
install -m 0644 "$repo_root/public-site/systemd/build-dash-federated-directory.timer" /etc/systemd/system/build-dash-federated-directory.timer
systemctl daemon-reload
if [[ "$enable" == true ]]; then
  if grep -q '\.example\.test/' "$sources_file"; then
    echo "Refusing to enable the directory builder with placeholder example.test sources." >&2
    echo "Re-run with one or more --source URLs and --replace-sources." >&2
    exit 1
  fi
  systemctl enable --now build-dash-federated-directory.timer
  systemctl start build-dash-federated-directory.service
fi
echo "Installed signed directory builder to $directory_root"
echo "Review $sources_file and $env_file, then enable build-dash-federated-directory.timer."
