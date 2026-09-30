#!/usr/bin/env python3
from __future__ import annotations
from copy import deepcopy
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from session_channel import AuthenticatedSessionChannel,MAX_PAYLOAD

def pair():
    args=(b"conformance-root","00112233445566778899aabbccddeeff","a"*64,[100,200])
    return AuthenticatedSessionChannel(*args,send_direction="a2b",receive_direction="b2a"),AuthenticatedSessionChannel(*args,send_direction="b2a",receive_direction="a2b")

def main():
    results=[]
    def check(identifier,action,expected):
        try:actual=action()
        except Exception as exc:actual=type(exc).__name__
        results.append({"id":identifier,"expected":expected,"actual":actual,"passed":actual==expected})
    check("valid-frame",lambda:(lambda ab: "accepted" if ab[1].decode(ab[0].encode(100,b"ok"))["authenticated"] else "rejected")(pair()),"accepted")
    def tamper():
        a,b=pair();frame=bytearray(a.encode(100,b"ok"));frame[-1]^=1
        try:b.decode(bytes(frame))
        except ValueError:return "authentication-failed"
        return "accepted"
    check("payload-tamper",tamper,"authentication-failed")
    def replay():
        a,b=pair();frame=a.encode(100,b"ok");b.decode(frame)
        try:b.decode(frame)
        except ValueError:return "rejected"
        return "accepted"
    check("replay",replay,"rejected")
    def rejected_encode(capability,payload):
        try:pair()[0].encode(capability,payload)
        except (ValueError,PermissionError):return "rejected"
        return "accepted"
    def wrong_session():
        a,b=pair();frame=bytearray(a.encode(100,b"x"));frame[8]^=1
        try:b.decode(bytes(frame))
        except ValueError:return "rejected"
        return "accepted"
    check("wrong-session",wrong_session,"rejected")
    check("out-of-scope-capability",lambda:rejected_encode(999,b"x"),"rejected")
    check("oversize-payload",lambda:rejected_encode(100,b"x"*(MAX_PAYLOAD+1)),"rejected")
    def rotated():
        a,b=pair();a.rotate(2);b.rotate(2);return "accepted" if b.decode(a.encode(100,b"new"))["keyEpoch"]==2 else "rejected"
    check("rotated-current-key",rotated,"accepted")
    def previous_grace():
        a,b=pair();old=a.encode(100,b"old");b.rotate(2);return "bounded" if b.decode(old)["keyEpoch"]==1 else "rejected"
    check("previous-key-grace",previous_grace,"bounded")
    def checkpoint_tamper():
        _,b=pair();checkpoint=b.checkpoint();checkpoint["inboundSequence"]=9
        try:b.restore(checkpoint)
        except ValueError:return "rejected"
        return "accepted"
    check("checkpoint-tamper",checkpoint_tamper,"rejected")
    report={"suite":"org.upp.conformance.session-channel-1","passed":all(item["passed"] for item in results),"results":results};print(json.dumps(report,indent=2));return 0 if report["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
