#!/usr/bin/env python3
"""Reference isolated adapter host. External formats are delegated, never dlopened in Core."""
import json,sys

manifest=None
for line in sys.stdin:
    request={}
    try:
        request=json.loads(line);op=request.get("op")
        if op=="activate":
            manifest=request["manifest"]
            if manifest.get("format")!="builtin":raise ValueError("external adapter executable handshake not implemented by reference host")
            response={"ok":True,"active":True,"protocolVersion":1,"pluginId":manifest["pluginId"],"format":manifest["format"],"supportsProcess":True,"latencyFrames":0}
        elif op=="process":
            if manifest is None:raise ValueError("host is inactive")
            samples=request.get("samples",[])
            if len(samples)>4096:raise ValueError("block exceeds bound")
            gain=float(manifest.get("configuration",{}).get("gain",1.0))
            response={"ok":True,"samples":[max(-1.0,min(1.0,float(v)*gain)) for v in samples]}
        elif op=="status":response={"ok":True,"active":manifest is not None}
        else:raise ValueError("unsupported operation")
    except Exception as exc:response={"ok":False,"error":str(exc)}
    response["requestId"]=request.get("requestId")
    print(json.dumps(response,separators=(",",":")),flush=True)
