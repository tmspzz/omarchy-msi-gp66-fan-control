#!/usr/bin/env python3
"""Small, validated MSI GP66 EC interface for the Omarchy widget.

The default backend is intentionally conservative: it requires MS-1542 and
uses only the reviewed G1_3 addresses.  Use --simulate for development.
"""

import argparse
import json
import os
import grp
import socket
import subprocess
import sys
import threading

BOARD = "MS-1542"
RPM_CONSTANT = 478000
MODES = {"auto": 0x0D, "silent": 0x1D, "advanced": 0x8D}
ADDR = {"cpu_temp": 0x68, "gpu_temp": 0x80, "cpu_rpm": 0xCC,
        "gpu_rpm": 0xCA, "mode": 0xF4, "cooler_boost": 0x98}
_EC_LOCK = threading.Lock()
SOCKET_PATH = "/run/msi-gp66-fan-control.sock"


class HelperError(Exception):
    pass


def _set_ec_write_support(enabled):
    """Reload ec_sys for one write, then let callers restore read-only mode."""
    parameter = "1" if enabled else "0"
    try:
        subprocess.run(["/usr/bin/modprobe", "-r", "ec_sys"],
                       check=False, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/modprobe", "ec_sys",
                        f"write_support={parameter}"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HelperError(f"could not enable EC write support: {exc}") from exc


def board_name():
    try:
        with open("/sys/class/dmi/id/board_name", encoding="ascii") as f:
            return f.read().strip()
    except OSError as exc:
        raise HelperError(f"cannot read board identity: {exc}") from exc


class SimulatedEC:
    def __init__(self):
        self.memory = bytearray(256)
        self.writes = []
        self.memory[ADDR["cpu_temp"]] = 52
        self.memory[ADDR["gpu_temp"]] = 47
        self._set_word(ADDR["cpu_rpm"], RPM_CONSTANT // 2100)
        self._set_word(ADDR["gpu_rpm"], RPM_CONSTANT // 1900)
        self.memory[ADDR["mode"]] = MODES["auto"]

    def _set_word(self, address, value):
        self.memory[address:address + 2] = value.to_bytes(2, "big")

    def read(self, address):
        return self.memory[address]

    def write(self, address, value):
        self.writes.append((address, value))
        self.memory[address] = value


class DebugfsEC:
    """Access the EC snapshot exposed by the kernel's ec_sys driver."""
    PATH = "/sys/kernel/debug/ec/ec0/io"

    def __init__(self, read_only=False):
        flags = "rb" if read_only else "r+b"
        try:
            self.handle = open(self.PATH, flags)
        except OSError as exc:
            raise HelperError(f"cannot open ec_sys interface {self.PATH}: {exc}") from exc
        self.read_only = read_only

    def close(self):
        self.handle.close()

    def read(self, address):
        self.handle.seek(address)
        value = self.handle.read(1)
        if len(value) != 1:
            raise HelperError(f"short read from ec_sys interface at 0x{address:02x}")
        return value[0]

    def write(self, address, value):
        if self.read_only:
            raise HelperError("write refused in read-only mode")
        self.handle.seek(address)
        self.handle.write(bytes((value,)))
        self.handle.flush()


def _rpm(ec, address):
    raw = (ec.read(address) << 8) | ec.read(address + 1)
    return 0 if raw == 0 else RPM_CONSTANT // raw


def status(ec, read_only):
    mode_value = ec.read(ADDR["mode"])
    mode = next((name for name, value in MODES.items() if value == mode_value), "unknown")
    boost = bool(ec.read(ADDR["cooler_boost"]) & 0x80)
    return {"ok": True, "board": BOARD, "read_only": read_only,
            "mode": mode, "cooler_boost": boost,
            "cpu_temp": ec.read(ADDR["cpu_temp"]),
            "gpu_temp": ec.read(ADDR["gpu_temp"]),
            "cpu_rpm": _rpm(ec, ADDR["cpu_rpm"]),
            "gpu_rpm": _rpm(ec, ADDR["gpu_rpm"]),
            "available_modes": list(MODES)}


def run(command, value=None, simulate=False, read_only=True):
    if command not in {"status", "temperatures", "fan-speeds", "get-mode", "set-mode", "cooler-boost"}:
        raise HelperError("invalid command")
    if not simulate and board_name() != BOARD:
        raise HelperError(f"unsupported board (expected {BOARD})")
    temporary_write_mode = not simulate and not read_only and command in {"set-mode", "cooler-boost"}
    if temporary_write_mode:
        _set_ec_write_support(True)
    ec = None
    try:
        ec = SimulatedEC() if simulate else DebugfsEC(read_only=read_only)
        with _EC_LOCK:
            if command == "set-mode":
                if value not in MODES:
                    raise HelperError("unsupported fan mode")
                if read_only:
                    raise HelperError("write refused in read-only mode")
                ec.write(ADDR["mode"], MODES[value]); result = {"mode": value}
            elif command == "cooler-boost":
                if value not in {"on", "off"}:
                    raise HelperError("cooler boost must be on or off")
                if read_only:
                    raise HelperError("write refused in read-only mode")
                current = ec.read(ADDR["cooler_boost"])
                ec.write(ADDR["cooler_boost"], (current | 0x80) if value == "on" else (current & 0x7F))
                result = {"cooler_boost": value == "on"}
            else:
                full = status(ec, read_only)
                result = {"temperatures": {"cpu": full["cpu_temp"], "gpu": full["gpu_temp"]}} if command == "temperatures" else full
                if command == "fan-speeds": result = {"cpu": full["cpu_rpm"], "gpu": full["gpu_rpm"]}
                if command == "get-mode": result = {"mode": full["mode"], "available_modes": full["available_modes"]}
            return {"ok": True, **result}
    finally:
        if not simulate and ec is not None:
            ec.close()
            if temporary_write_mode:
                _set_ec_write_support(False)


def serve(socket_path=SOCKET_PATH, stop_event=None):
    """Serve validated status and Cooler Boost operations over a private socket."""
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    socket_uid = os.environ.get("MSI_FAN_SOCKET_UID")
    if socket_uid is not None:
        os.chmod(socket_path, 0o600)
        os.chown(socket_path, int(socket_uid), -1)
    else:
        os.chmod(socket_path, 0o660)
        try:
            os.chown(socket_path, 0, grp.getgrnam("wheel").gr_gid)
        except (KeyError, PermissionError):
            pass
    server.listen(128)
    server.settimeout(0.2)
    try:
        while stop_event is None or not stop_event.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection:
                request = connection.makefile("r", encoding="utf-8").readline(4096)
                try:
                    message = json.loads(request)
                    command = message.get("command")
                    if command == "status":
                        response = run("status", read_only=True)
                    elif command == "cooler-boost":
                        response = run("cooler-boost", message.get("value"), read_only=False)
                    else:
                        raise HelperError("unsupported socket command")
                except (ValueError, HelperError) as exc:
                    response = {"ok": False, "error": str(exc)}
                connection.sendall((json.dumps(response, sort_keys=True) + "\n").encode())
    finally:
        server.close()
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "temperatures", "fan-speeds", "get-mode", "set-mode", "cooler-boost", "serve"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--allow-write", action="store_true",
                        help="permit validated EC writes (off by default)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve()
        return 0
    try:
        print(json.dumps(run(args.command, args.value, args.simulate,
                              not args.allow_write), sort_keys=True))
        return 0
    except HelperError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
