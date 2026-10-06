#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from interoperability_sessions import CapabilityRegistry, InteroperabilitySessionManager, make_authenticated_offer, project_profile, verify_authenticated_offer


def participants():
    local = {"id": "local", "apiVersions": [1, 2], "minimumSecureApiVersion": 1,
             "schemaVersions": {"org.upp.show-state": [1]}, "capabilities": ["audio.transport", "future.local"],
             "requiredCapabilities": ["audio.transport"], "preservesUnknown": True, "offlineCapable": True}
    remote = {"id": "remote", "apiVersions": [1, 2], "minimumSecureApiVersion": 1,
              "schemaVersions": {"org.upp.show-state": [1]}, "capabilities": ["audio.transport", "future.remote"],
              "requiredCapabilities": ["audio.transport"], "preservesUnknown": True, "offlineCapable": True}
    return local, remote


def run_case(case):
    secret=b"core-4.0-conformance-key"; local,remote=participants(); now=2_000_000
    mutation=case["mutation"]
    if mutation=="downgrade": remote["minimumSecureApiVersion"]=2; remote["apiVersions"]=[1]
    if mutation=="required": remote["requiredCapabilities"].append("unavailable.required")
    target="other" if mutation=="target" else "local"
    offer=make_authenticated_offer(remote,target,authority_epoch=7,sequence=1,ttl_ms=1000,secret=secret,now_unix_ms=now,nonce="00112233445566778899aabbccddeeff")
    if mutation=="signature": offer["authentication"]["signature"]="0"*64
    if mutation=="capability": offer["participant"]["capabilities"].append("tampered")
    verify_now=now+2000 if mutation=="expired" else now
    valid,reason=verify_authenticated_offer(offer,expected_target="local",secret=secret,now_unix_ms=verify_now)
    if mutation in {"signature","capability","target","expired"}: return reason
    registry=CapabilityRegistry(); manager=InteroperabilitySessionManager("local")
    try:
        session=manager.authenticate_and_negotiate(offer,local,registry,secret=secret,now_unix_ms=now,profile_revision=1,authority_epoch=7)
        if mutation=="replay": manager.authenticate_and_negotiate(offer,local,registry,secret=secret,now_unix_ms=now,profile_revision=1,authority_epoch=7)
    except ValueError as exc: return str(exc)
    if mutation in {"none","unknown"}: return "compatible" if session["plan"]["compatible"] else "incompatible"
    if mutation=="required": return "compatible" if session["plan"]["compatible"] else "incompatible"
    if mutation in {"venue-override","accessibility"}:
        namespace="org.upp.accessibility.visual" if mutation=="accessibility" else "org.upp.ui"
        profile={"profileId":"test","revision":1,"preferences":[
            {"namespace":namespace,"key":"contrast","layer":"user","revision":1,"type":"scalar","value":0.8},
            {"namespace":namespace,"key":"contrast","layer":"venue","revision":2,"type":"scalar","value":0.3}]}
        projection=project_profile(profile)
        if mutation=="venue-override": return "consent-required" if projection["consentRequired"] else "no-consent"
        return "user-wins" if projection["values"][0]["value"]==0.8 else "venue-wins"
    return "unsupported"


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--vectors",type=Path,default=ROOT/"conformance"/"core-4.0-vectors.json");args=parser.parse_args()
    suite=json.loads(args.vectors.read_text("utf-8"));results=[]
    for case in suite["cases"]:
        actual=run_case(case);results.append({"id":case["id"],"expected":case["expected"],"actual":actual,"passed":actual==case["expected"]})
    report={"suite":suite["suite"],"passed":all(item["passed"] for item in results),"results":results};print(json.dumps(report,indent=2));return 0 if report["passed"] else 1

if __name__=="__main__": raise SystemExit(main())
