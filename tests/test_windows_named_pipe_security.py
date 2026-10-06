import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from local_ipc import WindowsNamedPipeIpcServer
from windows_named_pipe import WindowsPipePolicy, build_windows_pipe_sddl, normalize_windows_sid


class _Listener:
    acl_policy_enforced=True
    def close(self): pass


class WindowsNamedPipeSecurityTests(unittest.TestCase):
    def test_sddl_is_protected_and_uses_only_explicit_sids(self):
        sddl=build_windows_pipe_sddl(['S-1-5-21-100-200-300-1001','s-1-5-80-12345'])
        self.assertEqual(sddl,'D:P(A;;GA;;;SY)(A;;GA;;;S-1-5-21-100-200-300-1001)(A;;GA;;;S-1-5-80-12345)')
        self.assertNotIn(';;;WD)',sddl);self.assertNotIn(';;;AU)',sddl);self.assertNotIn(';;;BU)',sddl)

    def test_broad_or_symbolic_principals_are_rejected(self):
        for value in ['WD','AU','BU','Everyone','Users','S-1-bad']:
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_windows_sid(value)
        with self.assertRaises(ValueError): build_windows_pipe_sddl([])

    def test_administrators_are_explicitly_opt_in(self):
        sid='S-1-5-21-1-2-3-1001'
        self.assertNotIn(';;;BA)',build_windows_pipe_sddl([sid]))
        self.assertIn(';;;BA)',build_windows_pipe_sddl([sid],allow_administrators=True))

    def test_policy_deduplicates_sid_entries(self):
        p=WindowsPipePolicy(('S-1-5-21-1-2-3-1001','s-1-5-21-1-2-3-1001'))
        self.assertEqual(p.sddl().count('S-1-5-21-1-2-3-1001'),1)

    def test_native_windows_path_requires_explicit_sid_configuration(self):
        endpoint=WindowsNamedPipeIpcServer(r'\\.\pipe\StageMesh\Control',lambda:None,lambda *_:b'')
        with mock.patch('local_ipc.os.name','nt'):
            with self.assertRaises(PermissionError): endpoint._factory()

    def test_self_validating_native_listener_may_satisfy_startup_contract(self):
        listener=_Listener()
        endpoint=WindowsNamedPipeIpcServer(
            r'\\.\pipe\StageMesh\Control',lambda:None,lambda *_:b'',
            allowed_sids=('S-1-5-21-1-2-3-1001',),
        )
        with mock.patch.object(endpoint,'_factory',return_value=lambda _:listener):
            endpoint.start()
        self.assertIs(endpoint._listener,listener)

    def test_non_self_validating_injected_listener_still_fails_closed(self):
        class WeakListener:
            def close(self): pass
        endpoint=WindowsNamedPipeIpcServer(
            r'\\.\pipe\StageMesh\Control',lambda:None,lambda *_:b'',
            listener_factory=lambda _:WeakListener(),
        )
        with self.assertRaises(PermissionError): endpoint.start()


if __name__=='__main__': unittest.main()
