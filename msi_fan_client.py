#!/usr/bin/env python3
"""Unprivileged client for the MSI fan read-only service."""
import json
import socket
import argparse
import os

SOCKET_PATH = os.environ.get("MSI_FAN_SOCKET", "/run/msi-gp66-fan-control.sock")

def request(command, value=None, socket_path=SOCKET_PATH):
    message = {"command": command}
    if command == "cooler-boost":
        message["value"] = value
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2.0)
        connection.connect(socket_path)
        connection.sendall((json.dumps(message) + "\n").encode())
        response = connection.makefile("r", encoding="utf-8").readline()
    return json.loads(response)

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "cooler-boost"])
    parser.add_argument("value", nargs="?", choices=["on", "off"])
    args = parser.parse_args(argv)
    if args.command == "cooler-boost" and args.value is None:
        parser.error("cooler-boost requires on or off")
    try:
        result = request(args.command, args.value)
    except (OSError, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
