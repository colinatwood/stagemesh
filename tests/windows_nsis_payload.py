"""Check a real generated NSIS payload against its reference without installing."""
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


executable_member = binding.nsis_member


def verify(directory, tool, commit, channel):
    tool = binding._plain_file(tool)
    root = directory.resolve(strict=True)
    reference, _ = binding._load(root / "executable-bindings/nsis.json")
    relative = reference.get("installer", {}).get("path")
    if binding._installer_path(relative) != "nsis":
        raise ValueError("expected an NSIS reference")
    if (reference.get("sourceCommit") != commit or reference.get("distributionChannel") != channel
            or reference.get("observation") != "extracted-nsis-payload"
            or reference.get("installerPayloadExtracted") is not True
            or reference.get("sourceProvenanceVerified") is not False):
        raise ValueError("NSIS reference candidate or observation is invalid")
    installer = binding._plain_file(root / relative)
    before, _ = binding.snapshot(installer)
    if any(reference["installer"].get(k) != before[k] for k in ("bytes", "sha256")):
        raise ValueError("NSIS reference belongs to a different installer")
    actual = {"name": binding.EXECUTABLE, **binding.nsis_payload(installer, tool)}
    if reference.get("executable") != actual:
        raise ValueError("NSIS payload differs from its executable reference: "
                         + json.dumps({"reference": reference.get("executable"), "actual": actual}, sort_keys=True))
    if binding.snapshot(installer)[0] != before:
        raise ValueError("NSIS installer changed during extraction")
    return {"passed": True, "sourceCommit": commit, "channel": channel,
            "installer": {"path": relative, **before}, "actualNsisPayload": actual,
            "referenceMatchesExtractedPayload": True, "installerExecuted": False,
            "sourceProvenanceVerified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--seven-zip", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--channel", choices=("online", "offline"), required=True)
    args = parser.parse_args()
    report = verify(args.directory, args.seven_zip, args.commit, args.channel)
    with tempfile.TemporaryDirectory(prefix="stagemesh-nsis-regression-") as temporary:
        root = Path(temporary); (root / "nsis").mkdir()
        installer = args.directory / report["installer"]["path"]
        shutil.copyfile(installer, root / "nsis" / installer.name)
        unrelated_build = root / binding.EXECUTABLE
        unrelated_build.write_bytes(b"deliberately unrelated post-bundle build output")
        recorded = binding.record(root, unrelated_build, "nsis", args.commit, args.channel,
                                  extract_nsis=True, seven_zip=args.seven_zip)
        if recorded["executable"] != report["actualNsisPayload"]:
            raise RuntimeError("NSIS recorder incorrectly used post-bundle build output")
    report["postBundleOutputIgnored"] = True
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
