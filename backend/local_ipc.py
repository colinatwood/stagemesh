from __future__ import annotations

import json
import os
import re
import socket
import struct
import threading
from pathlib import Path
from typing import Callable

from session_channel import AuthenticatedSessionChannel, HEADER_SIZE, MAX_PAYLOAD

MAX_FRAME = HEADER_SIZE + MAX_PAYLOAD
_SIZE = struct.Struct(">I")
_PIPE_NAME = re.compile(r"^\\\\\.\\pipe\\StageMesh\\[A-Za-z0-9_.-]{1,96}$", re.I)


def encode_transport_packet(frame: bytes) -> bytes:
    frame = bytes(frame)
    if len(frame) < HEADER_SIZE or len(frame) > MAX_FRAME:
        raise ValueError("local IPC frame size is outside bounds")
    return _SIZE.pack(len(frame)) + frame


def decode_transport_packet(packet: bytes) -> bytes:
    packet = bytes(packet)
    if len(packet) < _SIZE.size:
        raise ValueError("local IPC transport packet is truncated")
    size = _SIZE.unpack(packet[:_SIZE.size])[0]
    if size < HEADER_SIZE or size > MAX_FRAME:
        raise ValueError("local IPC frame size is outside bounds")
    if len(packet) != _SIZE.size + size:
        raise ValueError("local IPC transport packet size mismatch")
    return packet[_SIZE.size:]


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks=[]; remaining=size
    while remaining:
        block=sock.recv(remaining)
        if not block: raise EOFError("local IPC peer disconnected")
        chunks.append(block);remaining-=len(block)
    return b"".join(chunks)


def recv_frame(sock: socket.socket) -> bytes:
    size=_SIZE.unpack(recv_exact(sock, _SIZE.size))[0]
    if size < HEADER_SIZE or size > MAX_FRAME: raise ValueError("local IPC frame size is outside bounds")
    return recv_exact(sock, size)


def send_frame(sock: socket.socket, frame: bytes) -> None:
    sock.sendall(encode_transport_packet(frame))


def recv_message_frame(connection) -> bytes:
    """Receive one length-prefixed UPPF transport packet from a message pipe."""
    try:
        packet = connection.recv_bytes(MAX_FRAME + _SIZE.size)
    except TypeError:
        packet = connection.recv_bytes()
        if len(packet) > MAX_FRAME + _SIZE.size:
            raise ValueError("local IPC message exceeds transport bound")
    return decode_transport_packet(packet)


def send_message_frame(connection, frame: bytes) -> None:
    connection.send_bytes(encode_transport_packet(frame))


def serve_authenticated_connection(receive: Callable[[], bytes], send: Callable[[bytes], None],
                                   channel_factory: Callable[[], AuthenticatedSessionChannel],
                                   handler: Callable[[int, bytes], bytes], *, max_requests: int = 1024) -> None:
    channel=channel_factory();limit=max(1,min(int(max_requests),65536))
    for _ in range(limit):
        try:decoded=channel.decode(receive())
        except EOFError:break
        payload=handler(int(decoded["capabilityId"]),bytes(decoded["payload"]))
        send(channel.encode(int(decoded["capabilityId"]),payload))


class LocalIpcServer:
    def __init__(self, path: Path, channel_factory: Callable[[], AuthenticatedSessionChannel],
                 handler: Callable[[int, bytes], bytes], *, max_requests: int = 1024) -> None:
        if not hasattr(socket, "AF_UNIX"): raise RuntimeError("Unix sockets unavailable; use the Windows named-pipe adapter")
        self.path=Path(path);self.channel_factory=channel_factory;self.handler=handler
        self.max_requests=max(1,min(int(max_requests),65536));self._socket:socket.socket|None=None
        self._stop=threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.exists():
            if not self.path.is_socket(): raise FileExistsError(self.path)
            self.path.unlink()
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(str(self.path));os.chmod(self.path,0o600)
        sock.listen(8);sock.settimeout(.25);self._socket=sock

    def serve_once(self) -> None:
        if self._socket is None: raise RuntimeError("local IPC server is not started")
        try: connection,_=self._socket.accept()
        except socket.timeout:return
        with connection:
            connection.settimeout(2.0)
            serve_authenticated_connection(lambda:recv_frame(connection),lambda frame:send_frame(connection,frame),
                                           self.channel_factory,self.handler,max_requests=self.max_requests)

    def close(self) -> None:
        if self._socket:self._socket.close();self._socket=None
        if self.path.exists() and self.path.is_socket():self.path.unlink()


def validate_windows_pipe_name(name: str) -> str:
    value=str(name or "").strip()
    if not _PIPE_NAME.fullmatch(value):
        raise ValueError(r"Windows StageMesh pipe name must be \\.\pipe\StageMesh\<safe-name>")
    return value


class WindowsNamedPipeIpcServer:
    def __init__(self, name: str, channel_factory: Callable[[], AuthenticatedSessionChannel],
                 handler: Callable[[int, bytes], bytes], *, max_requests: int = 1024,
                 listener_factory=None, acl_validator: Callable[[str, object], bool] | None = None,
                 allowed_sids: tuple[str, ...] = (), allow_administrators: bool = False) -> None:
        self.name=validate_windows_pipe_name(name);self.channel_factory=channel_factory;self.handler=handler
        self.max_requests=max(1,min(int(max_requests),65536));self.listener_factory=listener_factory
        self.acl_validator=acl_validator;self.allowed_sids=tuple(allowed_sids)
        self.allow_administrators=bool(allow_administrators);self._listener=None

    def _factory(self):
        if self.listener_factory is not None:return self.listener_factory
        if os.name!="nt":raise RuntimeError("Windows named-pipe listener is unavailable on this platform")
        from windows_named_pipe import create_secure_windows_pipe_listener
        if not self.allowed_sids:
            raise PermissionError("Windows named-pipe native listener requires explicit allowed SIDs")
        return lambda name: create_secure_windows_pipe_listener(
            name,self.allowed_sids,allow_administrators=self.allow_administrators
        )

    def start(self) -> None:
        if self.listener_factory is not None and self.acl_validator is None:
            raise PermissionError("Windows named-pipe startup requires explicit ACL validation for injected listeners")
        listener=self._factory()(self.name)
        try:
            if self.acl_validator is not None:
                acl_ok=self.acl_validator(self.name,listener) is True
            else:
                acl_ok=bool(getattr(listener,"acl_policy_enforced",False))
            if not acl_ok:
                raise PermissionError("Windows named-pipe ACL validation failed")
        except Exception:
            try:listener.close()
            finally:raise
        self._listener=listener

    def serve_once(self) -> None:
        if self._listener is None:raise RuntimeError("Windows named-pipe server is not started")
        connection=self._listener.accept()
        try:
            serve_authenticated_connection(lambda:recv_message_frame(connection),lambda frame:send_message_frame(connection,frame),
                                           self.channel_factory,self.handler,max_requests=self.max_requests)
        finally:
            connection.close()

    def _wake_pending_native_accept(self) -> None:
        if os.name != "nt" or self.listener_factory is not None:
            return

        def wake() -> None:
            try:
                from multiprocessing.connection import Client
                connection = Client(self.name, family="AF_PIPE")
                connection.close()
            except (OSError, EOFError):
                pass

        threading.Thread(target=wake, name="stagemesh-pipe-close-wake", daemon=True).start()

    def close(self) -> None:
        listener=self._listener
        if listener is None:return
        self._wake_pending_native_accept()
        listener.close();self._listener=None


def json_command_handler(dispatch: Callable[[dict], dict]) -> Callable[[int, bytes], bytes]:
    def handle(capability_id: int, payload: bytes) -> bytes:
        request=json.loads(payload.decode("utf-8"));request["capabilityId"]=capability_id
        response=dispatch(request);response.setdefault("physicalOutputsArmed",False)
        encoded=json.dumps(response,separators=(",",":"),sort_keys=True).encode("utf-8")
        if len(encoded)>MAX_PAYLOAD:raise ValueError("local IPC response exceeds channel bound")
        return encoded
    return handle
