import json
import os
import stat
import tempfile
import unittest
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import msi_fan_helper as helper
import msi_fan_client as client


class HelperTests(unittest.TestCase):
    def test_simulated_status(self):
        result = helper.run("status", simulate=True)
        self.assertEqual(result["board"], "MS-1542")
        self.assertEqual(result["mode"], "auto")
        self.assertGreater(result["cpu_rpm"], 0)

    def test_writes_are_refused_read_only(self):
        with self.assertRaises(helper.HelperError):
            helper.run("set-mode", "advanced", simulate=True, read_only=True)

    def test_valid_simulated_write_uses_fixed_register(self):
        result = helper.run("set-mode", "advanced", simulate=True, read_only=False)
        self.assertEqual(result["mode"], "advanced")

    def test_invalid_mode_is_refused(self):
        with self.assertRaises(helper.HelperError):
            helper.run("set-mode", "basic", simulate=True, read_only=False)

    def test_board_mismatch(self):
        with patch.object(helper, "board_name", return_value="MS-1543"):
            with self.assertRaises(helper.HelperError):
                helper.run("status")

    def test_json_cli(self):
        output = json.loads(__import__("subprocess").check_output(
            ["python3", "-S", "msi_fan_helper.py", "status", "--simulate"], text=True))
        self.assertTrue(output["ok"])

    def test_debugfs_backend_reads_snapshot(self):
        with tempfile.NamedTemporaryFile() as backing:
            backing.write(bytes(range(256)))
            backing.flush()
            with patch.object(helper.DebugfsEC, "PATH", backing.name):
                ec = helper.DebugfsEC(read_only=True)
                self.assertEqual(ec.read(0x68), 0x68)
                ec.close()


class SocketProtocolTests(unittest.TestCase):
    def setUp(self):
        self.socket_file = tempfile.NamedTemporaryFile(delete=False)
        self.socket_path = self.socket_file.name
        self.socket_file.close()
        self.stop_event = threading.Event()
        self.run_patch = patch.object(helper, "run", side_effect=self.fake_run)
        self.run_patch.start()
        self.server_thread = threading.Thread(
            target=helper.serve, args=(self.socket_path, self.stop_event), daemon=True)
        self.server_thread.start()
        for _ in range(50):
            if os.path.exists(self.socket_path) and stat.S_ISSOCK(os.stat(self.socket_path).st_mode):
                break
            __import__("time").sleep(0.01)

    def tearDown(self):
        self.stop_event.set()
        self.server_thread.join(timeout=1)
        self.run_patch.stop()

    @staticmethod
    def fake_run(command, value=None, read_only=True):
        if command == "status":
            return {"ok": True, "mode": "auto", "cooler_boost": False}
        return {"ok": True, "cooler_boost": value == "on"}

    def test_status_and_invalid_command(self):
        for _ in range(50):
            try:
                result = client.request("status", socket_path=self.socket_path)
                break
            except ConnectionRefusedError:
                __import__("time").sleep(0.01)
        else:
            self.fail("socket service did not become ready")
        self.assertTrue(result["ok"])
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(self.socket_path)
            connection.sendall(b'{"command":"set-mode"}\n')
            response = __import__("json").loads(connection.makefile("r").readline())
        self.assertFalse(response["ok"])
        self.assertIn("unsupported", response["error"])

    def test_concurrent_requests(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: client.request("status", socket_path=self.socket_path), range(32)))
        self.assertEqual(len(results), 32)
        self.assertTrue(all(result["ok"] for result in results))

    def test_service_unavailable(self):
        missing = self.socket_path + ".missing"
        with self.assertRaises(OSError):
            client.request("status", socket_path=missing)


if __name__ == "__main__":
    unittest.main()
