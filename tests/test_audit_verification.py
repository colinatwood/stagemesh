import unittest

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("audit_verification", ROOT / "scripts" / "audit-verification.py")
MODULE = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AuditVerificationTests(unittest.TestCase):
    def test_socket_permission_is_environment_only(self):
        text = "File socketserver.py, PermissionError: [Errno 1] Operation not permitted"
        self.assertEqual(MODULE.classify_failure(text), "environment-only: network sockets unavailable")

    def test_udp_permission_is_environment_only(self):
        self.assertEqual(MODULE.classify_failure("RuntimeError: argument: unable to create UDP socket"), "environment-only: UDP sockets unavailable")

    def test_unrelated_failure_is_unexpected(self):
        self.assertEqual(MODULE.classify_failure("AssertionError: wrong result"), "unexpected")


if __name__ == "__main__":
    unittest.main()
