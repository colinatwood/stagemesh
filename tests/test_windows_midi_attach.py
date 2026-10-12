from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsMidiAttachTests(unittest.TestCase):
    def test_winmm_open_passes_callback_before_instance(self):
        source = (ROOT / "native" / "src" / "midi_input.cpp").read_text(encoding="utf-8")
        call = re.search(r"midiInOpen\((.*?)\)\s*!=", source, re.DOTALL)
        self.assertIsNotNone(call)
        arguments = call.group(1)
        callback = arguments.index("reinterpret_cast<DWORD_PTR>(&winmm_read)")
        instance = arguments.index("reinterpret_cast<DWORD_PTR>(slot)")
        self.assertLess(callback, instance)

    def test_cm_notification_probe_links_cfgmgr32(self):
        source = (ROOT / "native" / "devices.cmake").read_text(encoding="utf-8")
        probe = re.search(
            r"cmake_push_check_state\(RESET\)(.*?)"
            r"check_cxx_source_compiles\((.*?)STAGEMESH_HAS_CM_NOTIFY_API\)"
            r"(.*?)cmake_pop_check_state\(\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(probe)
        self.assertRegex(probe.group(1), r"set\(CMAKE_REQUIRED_LIBRARIES\s+cfgmgr32\)")
        self.assertIn("CM_Register_Notification", probe.group(2))


if __name__ == "__main__":
    unittest.main()
