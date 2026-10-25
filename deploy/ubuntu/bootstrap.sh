#!/usr/bin/env bash
# Run on the Ubuntu server, from a trusted release checkout/package.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo bash bootstrap.sh' >&2; exit 1; }
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || {
  echo 'This bootstrap targets Ubuntu 24.04 LTS. No packages were changed.' >&2; exit 1;
}
if [[ -e /usr/local/lib/eval-platform/manage.py ]]; then
  echo 'Existing operations script detected; refusing to overwrite it.' >&2
  exit 1
fi
apt-get update
apt-get install -y ca-certificates curl python3 openssl
if ! command -v docker >/dev/null; then
  # Use the Docker official apt repository; never remove preexisting runtimes.
  task_runtime_packages=$(dpkg-query -W -f='${binary:Package} ${db:Status-Status}\n' docker.io containerd runc 2>/dev/null || true)
  if grep -qE ' installed$' <<< "$task_runtime_packages"; then
    echo 'Existing runtime packages detected; reconcile with Docker documentation before retrying.' >&2
    exit 1
  fi
  install -m 0755 -d /etc/apt/keyrings
  curl --fail --show-error --silent --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat >/etc/apt/sources.list.d/eval-docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version
systemctl enable --now docker
task_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -d -m 0755 /usr/local/lib/eval-platform
install -m 0755 "$task_dir/manage.py" /usr/local/lib/eval-platform/manage.py
install -m 0644 "$task_dir/nginx.conf.template" /usr/local/lib/eval-platform/nginx.conf.template
echo 'Runtime prepared. Firewall, DNS and TLS still require configuration. Run manage.py install next.'
