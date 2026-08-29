#!/bin/sh
set -eu

prefix=/usr/local
libexec="$prefix/libexec"
install_user="${SUDO_USER:-$(id -un)}"
install_home=$(getent passwd "$install_user" | cut -d: -f6)
if [ -n "${SUDO_UID:-}" ]; then
  install_uid=$SUDO_UID
  install_gid=$SUDO_GID
else
  install_uid=$(id -u "$install_user")
  install_gid=$(id -g "$install_user")
fi
plugin_id=omarchy-msi-gp66-fan-control
plugin_dir="${XDG_CONFIG_HOME:-$install_home/.config}/omarchy/plugins/$plugin_id"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo: sudo ./install.sh" >&2
  exit 1
fi

case "${1:-}" in
  ""|--uninstall) ;;
  *) echo "Usage: sudo ./install.sh [--uninstall]" >&2; exit 2 ;;
esac

if [ "${1:-}" = "--uninstall" ]; then
  systemctl disable --now msi-gp66-fan-control.service 2>/dev/null || true
  rm -f /etc/systemd/system/msi-gp66-fan-control.service
  rm -f /etc/default/msi-gp66-fan-control
  rm -f "$libexec/msi-gp66-fan-helper" "$libexec/msi-gp66-fan-client"
  rm -rf "$plugin_dir"
  systemctl daemon-reload
  echo "Removed MSI GP66 fan control service, helper, client, and plugin."
  exit 0
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -m 0755 "$libexec" "$plugin_dir"
install -o root -g root -m 0755 "$repo_dir/msi_fan_helper.py" "$libexec/msi-gp66-fan-helper"
install -o root -g root -m 0755 "$repo_dir/msi_fan_client.py" "$libexec/msi-gp66-fan-client"
install -o root -g root -m 0644 "$repo_dir/msi-gp66-fan-control.service" /etc/systemd/system/msi-gp66-fan-control.service
printf 'MSI_FAN_SOCKET_UID=%s\n' "$install_uid" > /etc/default/msi-gp66-fan-control
chmod 0644 /etc/default/msi-gp66-fan-control
install -o "$install_uid" -g "$install_gid" -m 0644 "$repo_dir/BarWidget.qml" "$plugin_dir/BarWidget.qml"
install -o "$install_uid" -g "$install_gid" -m 0644 "$repo_dir/manifest.json" "$plugin_dir/manifest.json"
systemctl daemon-reload
systemctl enable msi-gp66-fan-control.service
systemctl restart msi-gp66-fan-control.service
echo "Installed MSI fan widget and telemetry service. Restart Omarchy shell to activate it."
