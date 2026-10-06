"""Privacy-preserving cross-platform audio endpoint/driver evidence adapters.

These probes are read-only diagnostics. They deliberately separate endpoint presence,
installed OS driver evidence and reviewed package metadata from StageMesh qualification.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_USB_ID = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)


def _bounded(value: object, limit: int = 256) -> str:
    return str(value or "").strip()[:limit]


def _opaque_hash(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _usb_hardware_id(value: object) -> str | None:
    match = _USB_ID.search(str(value or ""))
    if not match:
        return None
    return "USB:" + ":".join(part.upper() for part in match.groups())


def windows_endpoint_probe(command_json) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = command_json([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "$ep=@(Get-PnpDevice -PresentOnly -Class AudioEndpoint | "
        "Select-Object Status,Class,FriendlyName,InstanceId); "
        "$drv=@(Get-CimInstance Win32_PnPSignedDriver | "
        "Where-Object {$_.DeviceClass -eq 'MEDIA'} | "
        "Select-Object DeviceName,DeviceID,DriverProviderName,DriverVersion,InfName,IsSigned,Signer); "
        "[pscustomobject]@{endpoints=$ep;drivers=$drv} | ConvertTo-Json -Compress -Depth 4"
    ])
    if not isinstance(payload, dict):
        raise ValueError("Windows audio evidence payload must be an object")
    endpoints_raw = payload.get("endpoints") or []
    drivers_raw = payload.get("drivers") or []
    if isinstance(endpoints_raw, dict): endpoints_raw = [endpoints_raw]
    if isinstance(drivers_raw, dict): drivers_raw = [drivers_raw]
    if not isinstance(endpoints_raw, list) or not isinstance(drivers_raw, list):
        raise ValueError("Windows audio evidence arrays malformed")
    endpoints=[]
    for row in endpoints_raw:
        if not isinstance(row, dict): continue
        token = _opaque_hash(row.get("InstanceId"))
        endpoints.append({"platform":"Windows","name":_bounded(row.get("FriendlyName") or "Audio endpoint"),"status":_bounded(row.get("Status") or "unknown",64),"endpointIdentityHash":token,"identityScope":"snapshot hash of opaque AudioEndpoint instance; not PKEY_AudioEndpoint_StableId","qualified":False})
    drivers=[]
    for row in drivers_raw:
        if not isinstance(row, dict): continue
        device_id=row.get("DeviceID"); signed_raw=row.get("IsSigned"); signed=signed_raw if isinstance(signed_raw,bool) else None
        drivers.append({"platform":"Windows","name":_bounded(row.get("DeviceName") or "Audio driver"),"hardwareId":_usb_hardware_id(device_id),"deviceIdentityHash":_opaque_hash(device_id),"provider":_bounded(row.get("DriverProviderName")) or None,"version":_bounded(row.get("DriverVersion")) or None,"infName":_bounded(row.get("InfName"),128) or None,"signed":signed,"signer":_bounded(row.get("Signer")) or None,"evidenceKind":"installed-pnp-signed-driver-metadata","packageSemantics":"installed-os-evidence-not-reviewed-package-catalog","qualified":False})
    return endpoints,drivers


def _iter_dicts(value: object):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from _iter_dicts(child)
    elif isinstance(value,list):
        for child in value: yield from _iter_dicts(child)


def _first_matching(row: dict[str, Any], *needles: str):
    lowered=tuple(needle.lower() for needle in needles)
    for key,value in row.items():
        key_lower=str(key).lower()
        if any(needle in key_lower for needle in lowered) and value not in (None,""):
            return value
    return None


def macos_endpoint_probe(command_json) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload=command_json(["system_profiler","SPAudioDataType","-json","-detailLevel","mini"])
    if not isinstance(payload,dict): raise ValueError("macOS audio evidence payload must be an object")
    rows=payload.get("SPAudioDataType") or []; endpoints=[]; seen=set()
    for row in _iter_dicts(rows):
        name=_bounded(row.get("_name") or row.get("name"))
        uid=_first_matching(row,"device_uid","device uid","coreaudio_uid","coreaudio device uid")
        manufacturer=_first_matching(row,"manufacturer"); transport=_first_matching(row,"transport")
        input_channels=_first_matching(row,"input channels","input_channels","device_input")
        output_channels=_first_matching(row,"output channels","output_channels","device_output")
        if not name or not any(v not in (None,"") for v in (uid,manufacturer,transport,input_channels,output_channels)): continue
        uid_hash=_opaque_hash(uid); dedupe=(name,uid_hash)
        if dedupe in seen: continue
        seen.add(dedupe)
        endpoints.append({"platform":"Darwin","name":name,"manufacturer":_bounded(manufacturer) or None,"transport":_bounded(transport,128) or None,"endpointIdentityHash":uid_hash,"inputChannels":_bounded(input_channels,64) or None,"outputChannels":_bounded(output_channels,64) or None,"identityScope":"hash of host-reported CoreAudio device UID when available; raw UID not exported","qualified":False})
    drivers=[{"platform":"Darwin","name":item["name"],"deviceIdentityHash":item.get("endpointIdentityHash"),"provider":item.get("manufacturer"),"version":None,"evidenceKind":"coreaudio-device-present","packageSemantics":"not-applicable-no-windows-style-package-claim","qualified":False} for item in endpoints]
    return endpoints,drivers
