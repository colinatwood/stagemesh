"""Required Windows CI regression using its real generated MSI, without installing."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("binding", ROOT / "scripts/desktop-executable-binding.py")
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--channel", choices=("online", "offline"), required=True)
    args = parser.parse_args()
    reference = json.loads((args.directory / "executable-bindings/msi.json").read_text())
    installer = args.directory / reference["installer"]["path"]
    actual = binding.msi_payload(installer)
    expected = {"name": binding.EXECUTABLE, **actual}
    if (reference["executable"] != expected or reference["observation"] != "extracted-msi-payload"
            or reference["installerPayloadExtracted"] is not True
            or reference["sourceCommit"] != args.commit or reference["distributionChannel"] != args.channel
            or any(reference["installer"][key] != binding.snapshot(installer)[0][key] for key in ("bytes", "sha256"))):
        raise RuntimeError("generated MSI reference does not match the real payload and candidate")
    with tempfile.TemporaryDirectory(prefix="stagemesh-msi-regression-") as temporary:
        root = Path(temporary); (root / "msi").mkdir()
        shutil.copyfile(installer, root / "msi" / installer.name)
        unrelated_build = root / binding.EXECUTABLE
        unrelated_build.write_bytes(b"deliberately different post-bundle build output")
        recorded = binding.record(root, unrelated_build, "msi", args.commit, args.channel, extract_msi=True)
        if recorded["executable"] != expected or recorded["executable"]["sha256"] == binding.snapshot(unrelated_build)[0]["sha256"]:
            raise RuntimeError("MSI recorder incorrectly used post-bundle build output")
    print(json.dumps({"passed": True, "channel": args.channel, "sourceCommit": args.commit,
                      "actualMsiPayload": actual, "installerExecuted": False,
                      "postBundleOutputIgnored": True}, sort_keys=True))


if __name__ == "__main__":
    main()
