import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from local_ipc import (WindowsNamedPipeIpcServer,decode_transport_packet,encode_transport_packet,
                       recv_message_frame,send_message_frame,validate_windows_pipe_name)
from session_channel import AuthenticatedSessionChannel


class FakeConnection:
    def __init__(self,incoming=None):self.incoming=list(incoming or []);self.outgoing=[];self.closed=False
    def recv_bytes(self,*args):
        if not self.incoming:raise EOFError()
        return self.incoming.pop(0)
    def send_bytes(self,payload):self.outgoing.append(bytes(payload))
    def close(self):self.closed=True


class FakeListener:
    def __init__(self,connection):self.connection=connection;self.closed=False
    def accept(self):return self.connection
    def close(self):self.closed=True


class WindowsNamedPipeIpcTests(unittest.TestCase):
    def channels(self):
        args=(b"k"*32,"11"*16,"22"*32,{7})
        return (AuthenticatedSessionChannel(*args,send_direction="client",receive_direction="server"),
                AuthenticatedSessionChannel(*args,send_direction="server",receive_direction="client"))

    def test_transport_packet_is_exact_and_bounded(self):
        client,_=self.channels();frame=client.encode(7,b'{"op":"status"}')
        packet=encode_transport_packet(frame);self.assertEqual(decode_transport_packet(packet),frame)
        with self.assertRaises(ValueError):decode_transport_packet(packet+b"x")
        with self.assertRaises(ValueError):decode_transport_packet(b"\x00\x00")

    def test_message_pipe_roundtrip_keeps_uppf_authentication(self):
        client,server=self.channels();connection=FakeConnection([encode_transport_packet(client.encode(7,b"request"))])
        decoded=server.decode(recv_message_frame(connection));self.assertEqual(decoded["payload"],b"request")
        send_message_frame(connection,server.encode(7,b"response"));reply=client.decode(decode_transport_packet(connection.outgoing[0]))
        self.assertEqual(reply["payload"],b"response")

    def test_pipe_name_is_stagemesh_scoped(self):
        self.assertEqual(validate_windows_pipe_name(r"\\.\pipe\StageMesh\Control"),r"\\.\pipe\StageMesh\Control")
        for value in (r"\\.\pipe\Other\Control",r"\\.\pipe\StageMesh\..\Admin","StageMesh"):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_windows_pipe_name(value)

    def test_server_refuses_start_without_acl_validation(self):
        client,server=self.channels();listener=FakeListener(FakeConnection())
        endpoint=WindowsNamedPipeIpcServer(r"\\.\pipe\StageMesh\Control",lambda:server,lambda c,p:b"ok",listener_factory=lambda _:listener)
        with self.assertRaises(PermissionError):endpoint.start()
        self.assertFalse(listener.closed)

    def test_failed_acl_validation_closes_listener(self):
        _,server=self.channels();listener=FakeListener(FakeConnection())
        endpoint=WindowsNamedPipeIpcServer(r"\\.\pipe\StageMesh\Control",lambda:server,lambda c,p:b"ok",listener_factory=lambda _:listener,acl_validator=lambda *_:False)
        with self.assertRaises(PermissionError):endpoint.start()
        self.assertTrue(listener.closed)

    def test_authenticated_server_is_request_bounded(self):
        client,server=self.channels();incoming=[encode_transport_packet(client.encode(7,b"a")),encode_transport_packet(client.encode(7,b"b"))]
        connection=FakeConnection(incoming);listener=FakeListener(connection)
        endpoint=WindowsNamedPipeIpcServer(r"\\.\pipe\StageMesh\Control",lambda:server,lambda c,p:p.upper(),max_requests=1,listener_factory=lambda _:listener,acl_validator=lambda *_:True)
        endpoint.start();endpoint.serve_once();self.assertTrue(connection.closed);self.assertEqual(len(connection.outgoing),1)
        response=client.decode(decode_transport_packet(connection.outgoing[0]));self.assertEqual(response["payload"],b"A")


if __name__=="__main__":unittest.main()
