import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHTTPServer, StageMeshHandler


class SmallServer(StageMeshHTTPServer):
    max_connections = 1
    socket_timeout = 0.15


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.server = SmallServer(('127.0.0.1', 0), StageMeshHandler)

    def tearDown(self):
        self.server.server_close()

    def test_exhausted_capacity_closes_without_spawning_worker(self):
        self.assertTrue(self.server._connection_slots.acquire(False))
        request = Mock()
        with patch.object(self.server, 'shutdown_request') as close, patch('http.server.ThreadingHTTPServer.process_request') as spawn:
            self.server.process_request(request, ('127.0.0.1', 1))
            close.assert_called_once_with(request)
            spawn.assert_not_called()
        self.server._connection_slots.release()

    def test_thread_start_failure_returns_capacity(self):
        with patch('http.server.ThreadingHTTPServer.process_request', side_effect=RuntimeError('start failed')):
            with self.assertRaises(RuntimeError):
                self.server.process_request(Mock(), ('127.0.0.1', 1))
        self.assertTrue(self.server._connection_slots.acquire(False))
        self.server._connection_slots.release()

    def test_worker_failure_returns_capacity(self):
        self.server._connection_slots.acquire(False)
        with patch('http.server.ThreadingHTTPServer.process_request_thread', side_effect=RuntimeError('handler failed')):
            with self.assertRaises(RuntimeError):
                self.server.process_request_thread(Mock(), ('127.0.0.1', 1))
        self.assertTrue(self.server._connection_slots.acquire(False))
        self.server._connection_slots.release()

    def test_idle_partial_header_is_closed_and_worker_exits(self):
        client, accepted = socket.socketpair()
        client.settimeout(2)
        accepted.settimeout(self.server.socket_timeout)
        self.server._connection_slots.acquire(False)
        worker = threading.Thread(target=self.server.process_request_thread, args=(accepted, ('127.0.0.1', 1)))
        worker.start()
        try:
            client.sendall(b'GET / HTTP/1.1\r\nHost:')
            self.assertEqual(client.recv(1), b'')
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertTrue(self.server._connection_slots.acquire(False))
            self.server._connection_slots.release()
        finally:
            client.close()
