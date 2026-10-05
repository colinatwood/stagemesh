from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / ".github",
    ROOT / "backend",
    ROOT / "ci",
    ROOT / "desktop",
    ROOT / "docs",
    ROOT / "native",
    ROOT / "packaging",
    ROOT / "scripts",
    ROOT / "tests",
)
TEXT_SUFFIXES = {
    ".cmake", ".cpp", ".h", ".hpp", ".json", ".md", ".py", ".rs",
    ".service", ".sh", ".toml", ".yaml", ".yml",
}
HISTORICAL_EVIDENCE = ROOT / "docs" / "evidence"


class ProductNamingTests(unittest.TestCase):
    def _live_source_offenders(self, legacy_text):
        offenders = []
        for source_root in SOURCE_ROOTS:
            for path in source_root.rglob("*"):
                if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                    continue
                if HISTORICAL_EVIDENCE in path.parents or path == Path(__file__):
                    continue
                if legacy_text in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(path.relative_to(ROOT).as_posix())
        return offenders

    def test_live_sources_do_not_restore_legacy_native_engine_name(self):
        legacy_name = "stageforge" + "_engine"
        offenders = self._live_source_offenders(legacy_name)
        for path in (ROOT / "CMakeLists.txt",):
            if legacy_name in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_live_sources_do_not_restore_legacy_native_engine_environment_variable(self):
        legacy_variable = "STAGEFORGE" + "_NATIVE_ENGINE"
        self.assertEqual(self._live_source_offenders(legacy_variable), [])

    def test_build_and_desktop_bundle_use_stagemesh_engine(self):
        cmake = (ROOT / "native" / "engine.cmake").read_text(encoding="utf-8")
        tauri = (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        self.assertIn("add_executable(stagemesh_engine", cmake)
        self.assertIn('"binaries/stagemesh_engine"', tauri)


if __name__ == "__main__":
    unittest.main()
