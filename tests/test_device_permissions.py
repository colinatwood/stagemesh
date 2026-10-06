import os,pwd,stat,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from device_permissions import inspect_device,parse_device_spec,qualify_device_permissions

class DevicePermissionTests(unittest.TestCase):
    def test_spec_is_absolute_and_bounded_to_known_access_modes(self):
        self.assertEqual(parse_device_spec('/dev/snd/pcmC0D0p:r'),(Path('/dev/snd/pcmC0D0p'),'r'))
        self.assertEqual(parse_device_spec('/dev/ttyUSB0'),(Path('/dev/ttyUSB0'),'rw'))
        for value in ('relative:rw','/dev/null:x',''):
            with self.subTest(value=value),self.assertRaises(ValueError):parse_device_spec(value)
    def test_non_character_or_symlink_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);regular=root/'regular';regular.write_text('x');link=root/'link';link.symlink_to('/dev/null')
            self.assertFalse(inspect_device(regular,'r')['allowed'])
            self.assertFalse(inspect_device(link,'r')['allowed'])
    def test_character_device_reports_major_minor_and_access(self):
        row=inspect_device(Path('/dev/null'),'rw')
        self.assertTrue(row['characterDevice']);self.assertTrue(row['allowed']);self.assertIsInstance(row['major'],int);self.assertIsInstance(row['minor'],int)
    def test_qualification_must_run_as_requested_service_identity(self):
        current=pwd.getpwuid(os.geteuid()).pw_name
        value=qualify_device_permissions(service_user=current,device_specs=['/dev/null:rw'])
        self.assertTrue(value['serviceIdentityQualified']);self.assertTrue(value['hardwarePermissionsQualified']);self.assertFalse(value['physicalOutputsArmed'])
        with mock.patch('device_permissions.os.geteuid',return_value=os.geteuid()+100000):
            with mock.patch('device_permissions.pwd.getpwuid',return_value=type('P',(),{'pw_name':'other'})()):
                denied=qualify_device_permissions(service_user=current,device_specs=['/dev/null:rw'])
        self.assertFalse(denied['serviceIdentityQualified']);self.assertFalse(denied['hardwarePermissionsQualified']);self.assertEqual(denied['devices'],[])
    def test_missing_device_is_explicit_failure(self):
        row=inspect_device(Path('/dev/stagemesh-definitely-missing'),'rw')
        self.assertFalse(row['present']);self.assertFalse(row['allowed'])

if __name__=='__main__':unittest.main()
