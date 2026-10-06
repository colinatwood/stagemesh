from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LEGACY_LOWER = "stage" + "forge"
LEGACY_FORMS = (
    LEGACY_LOWER,
    LEGACY_LOWER.upper(),
    LEGACY_LOWER.title(),
)
SKIP_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
}


def repository_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if relative.parts and relative.parts[0].startswith("build"):
            continue
        yield path, relative


class ProductNamingTests(unittest.TestCase):
    def test_repository_paths_use_only_stagemesh_identity(self):
        offenders = [
            relative.as_posix()
            for _, relative in repository_files()
            if LEGACY_LOWER in relative.as_posix().casefold()
        ]
        self.assertEqual(offenders, [])

    def test_repository_text_uses_only_stagemesh_identity(self):
        offenders = []
        for path, relative in repository_files():
            if path.suffix.casefold() == ".xlsx":
                with zipfile.ZipFile(path) as workbook:
                    for member in workbook.namelist():
                        if member.endswith("/"):
                            continue
                        text = workbook.read(member).decode("utf-8", errors="ignore")
                        if any(form in text for form in LEGACY_FORMS):
                            offenders.append(f"{relative.as_posix()}!{member}")
                continue

            data = path.read_bytes()
            if b"\x00" in data:
                continue
            text = data.decode("utf-8", errors="ignore")
            if any(form in text for form in LEGACY_FORMS):
                offenders.append(relative.as_posix())

        self.assertEqual(offenders, [])

    def test_build_and_desktop_bundle_use_stagemesh_engine(self):
        cmake = (ROOT / "native" / "engine.cmake").read_text(encoding="utf-8")
        tauri = (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        self.assertIn("add_executable(stagemesh_engine", cmake)
        self.assertIn('"binaries/stagemesh_engine"', tauri)


if __name__ == "__main__":
    unittest.main()
