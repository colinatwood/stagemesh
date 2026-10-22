"""Check a real generated NSIS payload against its reference without installing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("binding", ROOT / "scripts/desktop-executable-binding.py")
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)


def executable_member(listing):
    normalized = listing.replace("\r\n", "\n")
    if "Type = Nsis" not in normalized.splitlines():
        raise ValueError("expected an NSIS archive")
    members = []
    for block in normalized.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if " = " not in line:
                continue
            key, value = line.split(" = ", 1)
            if key in fields:
                raise ValueError("ambiguous archive listing")
            fields[key] = value
        name = fields.get("Path", "").replace("\\", "/")
        if PurePosixPath(name).name.casefold() != binding.EXECUTABLE:
            continue
        if (not name or name.startswith("/") or ":" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or any(ord(c) < 32 for c in name)):
            raise ValueError("unsafe executable archive path")
        size = fields.get("Size", "")
        if not size.isascii() or not size.isdecimal() or not 0 < int(size) <= 512 * 1024 * 1024:
            raise ValueError("unsupported executable archive size")
        members.append((fields["Path"], int(size)))
    if len(members) != 1:
        raise ValueError("NSIS must contain exactly one desktop executable")
    return members[0]


def verify(directory, tool, commit, channel):
    tool = binding._plain_file(tool)
    root = directory.resolve(strict=True)
    reference, _ = binding._load(root / "executable-bindings/nsis.json")
    relative = reference.get("installer", {}).get("path")
    if binding._installer_path(relative) != "nsis":
        raise ValueError("expected an NSIS reference")
    if (reference.get("sourceCommit") != commit or reference.get("distributionChannel") != channel
            or reference.get("observation") != "post-bundle-build-output"
            or reference.get("installerPayloadExtracted") is not False
            or reference.get("sourceProvenanceVerified") is not False):
        raise ValueError("NSIS reference candidate or observation is invalid")
    installer = binding._plain_file(root / relative)
    before, _ = binding.snapshot(installer)
    if any(reference["installer"].get(k) != before[k] for k in ("bytes", "sha256")):
        raise ValueError("NSIS reference belongs to a different installer")
    listing = subprocess.run([str(tool), "l", "-slt", "-sccUTF-8", "--", str(installer)],
                             capture_output=True, check=True, timeout=180)
    member, size = executable_member(listing.stdout.decode("utf-8", errors="strict"))
    payload = subprocess.run([str(tool), "x", "-so", "-spd", "--", str(installer), member],
                             capture_output=True, check=True, timeout=180).stdout
    if len(payload) != size or not payload.startswith(b"MZ"):
        raise ValueError("NSIS executable payload is invalid or differs from its listed size")
    actual = {"name": binding.EXECUTABLE, "bytes": size, "sha256": hashlib.sha256(payload).hexdigest()}
    if reference.get("executable") != actual:
        raise ValueError("NSIS payload differs from its post-bundle executable reference: "
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
    print(json.dumps(verify(args.directory, args.seven_zip, args.commit, args.channel), sort_keys=True))


if __name__ == "__main__":
    main()
