import http.client
import re
from email import policy
from email.parser import BytesParser
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import wave
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ApiTests(unittest.TestCase):
    def test_oversized_command_id_rejected_without_mutation(self):
        _, _, before = self.request('GET', '/api/v1/state')
        status, _, error = self.request('PATCH', '/api/v1/show', {'bpm': 137},
                                       headers={'X-StageMesh-Command-Id': 'a' * 129})
        self.assertEqual(status, 400)
        self.assertIn('command ID', error['error'])
        _, _, after = self.request('GET', '/api/v1/state')
        self.assertEqual(after['revision'], before['revision'])
        self.assertEqual(after['transport']['bpm'], before['transport']['bpm'])

    def test_audio_conversion_plan_requires_each_explicit_choice(self):
        request={"direction":"capture","device":{"sampleRate":48000,"format":"S24_3LE","channels":1},"conversionPolicy":{"sampleRate":"bounded-sinc","sampleFormat":"normalize-integer","channels":"mono-to-stereo"}}
        status,_,plan=self.request("POST","/api/v1/hardware/audio-conversion-plan",request)
        self.assertEqual(status,200);self.assertTrue(plan["requiresConversion"]);self.assertEqual(plan["nativeConversionFlags"],7);self.assertFalse(plan["upscalingRestoresMissingBandwidth"]);self.assertFalse(plan["physicalOutputsArmed"])
        del request["conversionPolicy"]["sampleRate"]
        status,_,error=self.request("POST","/api/v1/hardware/audio-conversion-plan",request)
        self.assertEqual(status,400);self.assertIn("sample-rate conversion",error["error"])

    def test_http_boundary_rejects_rebinding_cross_origin_and_form_mutations(self):
        status,headers,error=self.request("GET","/api/v1/state",headers={"Host":"attacker.example"})
        self.assertEqual(status,403);self.assertIn("Host",error["error"])
        status,_,error=self.request("POST","/api/v1/profile",{},headers={"Origin":"https://attacker.example"})
        self.assertEqual(status,403);self.assertIn("Origin",error["error"])
        status,_,error=self.request("POST","/api/v1/profile",{},headers={"Content-Type":"text/plain"})
        self.assertEqual(status,400);self.assertIn("Content-Type",error["error"])
        status,headers,_=self.request("GET","/api/v1/state")
        self.assertEqual(status,200);self.assertEqual(headers["X-Frame-Options"],"DENY");self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])

    def test_audio_recovery_requires_distinct_acknowledgement(self):
        for path, body in (("/api/v1/audio/recover", {"acknowledgePhysicalOutput":True}),
                           ("/api/v1/audio/input/recover", {"acknowledgePhysicalInput":True})):
            status,_,result=self.request("POST",path,body)
            self.assertEqual(status,400);self.assertIn("acknowledgeRecovery",result["error"])

    def test_audio_preflight_rejects_plugin_addresses_and_malformed_requests(self):
        for request in ({"address":"default"}, {"address":"hw:0,0", "channels":True}):
            status, _, report = self.request("POST", "/api/v1/hardware/audio-preflight", request)
            self.assertEqual(status, 400)
            self.assertIn("error", report)

    def test_hardware_diagnostics_is_read_only_and_unqualified(self):
        status, _, report = self.request("GET", "/api/v1/hardware/diagnostics")
        self.assertEqual(status, 200)
        self.assertEqual(report["documentType"], "org.upp.hardware-diagnostics")
        self.assertFalse(report["physicalOutputsArmed"])
        self.assertEqual(report["qualification"], "hardware-tests-required")
        self.assertTrue(all(not item["qualified"] for item in report["devices"]))

    def test_audio_hotplug_status_is_bounded_observation_only(self):
        status,_,report=self.request("GET","/api/v1/audio/hotplug?after=0")
        self.assertEqual(status,200);self.assertIn("generation",report);self.assertLessEqual(len(report["changes"]),128);self.assertFalse(report["automaticActivation"]);self.assertFalse(report["physicalOutputsArmed"])
        status,_,error=self.request("GET","/api/v1/audio/hotplug?after=bad")
        self.assertEqual(status,400);self.assertIn("integer",error["error"])

    def test_realtime_audit_includes_midi_ingress_without_arming_outputs(self):
        status, _, audit = self.request("GET", "/api/v1/realtime/audit")
        self.assertEqual(status, 200);self.assertFalse(audit["physicalOutputsArmed"])
        if audit["available"]:
            midi=audit["ingress"]["midi"];self.assertEqual(midi["domain"],"midi");self.assertIn("queueDrops",midi);self.assertIn("maxDurationNs",midi);self.assertEqual(midi["physicalOutputsArmed"],"0")
            self.assertEqual(len(audit["ingress"]["capture"]),4);capture=audit["ingress"]["capture"][0];self.assertEqual(capture["domain"],"capture");self.assertIn("queueRejections",capture);self.assertIn("nonfiniteSamples",capture);self.assertEqual(capture["physicalOutputsArmed"],"0")
            lighting=audit["ingress"]["lighting"];self.assertEqual(lighting["domain"],"lighting");self.assertIn("queueRejections",lighting);self.assertIn("drainCalls",lighting);self.assertEqual(lighting["physicalOutputsArmed"],"0")
            self.assertIsInstance(audit["ingress"]["pluginHosts"],list)

    def test_daw_editor_http_workflow_remains_disarmed(self):
        media = Path(self.temp.name) / "media"; media.mkdir(exist_ok=True)
        source = media / "http-workflow.wav"
        with wave.open(str(source), "wb") as output:
            output.setnchannels(2); output.setsampwidth(4); output.setframerate(192000)
            output.writeframes(struct.pack("<ii", 1000, -1000) * 1024)
        _, _, current = self.request("GET", "/api/v1/daw/session")
        session = {"sessionId":"http-workflow","revision":current["revision"]+1,"tracks":[{"trackId":"vox","name":"Vox","kind":"audio","clips":[{"clipId":"take","startFrame":0,"lengthFrames":1024,"sourceOffsetFrames":0,"source":{"type":"audio-file","uri":source.name}}]}]}
        status, _, saved = self.request("POST", "/api/v1/daw/session", session); self.assertEqual(status, 200); self.assertFalse(saved["physicalOutputsArmed"])
        status, _, marked = self.request("POST", "/api/v1/daw/markers", {"action":"add","markerId":"chorus","name":"Chorus","kind":"section","frame":256,"expectedRevision":saved["revision"]}); self.assertEqual(status, 200)
        status, _, automated = self.request("POST", "/api/v1/daw/automation", {"action":"upsert","trackId":"vox","pointId":"volume-1","parameter":"volume","frame":256,"value":0.5,"expectedRevision":marked["revision"]}); self.assertEqual(status, 200)
        status, _, moved = self.request("POST", "/api/v1/daw/edit", {"op":"move","clipId":"take","startFrame":256,"snapFrames":256,"expectedRevision":automated["revision"]}); self.assertEqual(status, 200)
        status, _, plan = self.request("POST", "/api/v1/daw/render-plan", {"startFrame":0,"endFrame":2048}); self.assertEqual(status, 200); self.assertEqual(plan["regions"][0]["renderStartFrame"],256)
        status, _, rendered = self.request("POST", "/api/v1/daw/render", {"fileName":"http-workflow-render.wav","startFrame":0,"endFrame":2048,"bits":32}); self.assertEqual(status, 201, rendered); self.assertEqual(rendered["frames"],2048); self.assertFalse(rendered["physicalOutputsArmed"])
        _, _, playback = self.request("GET", "/api/v1/daw/playback")
        if playback["available"]:
            status, _, started = self.request("POST", "/api/v1/daw/playback", {"action":"start","startFrame":0,"endFrame":2048}); self.assertEqual(status,200); self.assertFalse(started["physicalOutputsArmed"])
            status, _, stopped = self.request("POST", "/api/v1/daw/playback", {"action":"stop"}); self.assertEqual(status,200); self.assertFalse(stopped["physicalOutputsArmed"])

    def test_daw_production_projection_is_coherent_and_disarmed(self):
        status, _, production = self.request("GET", "/api/v1/daw/production")
        self.assertEqual(status, 200)
        self.assertEqual(production["canonicalSampleRate"], 192000)
        self.assertIn("playback", production)
        self.assertIn("capture", production)
        self.assertIn("recovery", production)
        self.assertFalse(production["physicalOutputsArmed"])
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            for path, marker in (("/production.js", b"mountDawProduction"), ("/openapi.json", b'"openapi": "3.1.0"')):
                conn.request("GET", path)
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(marker, response.read())
        finally:
            conn.close()

    def test_recovery_http_discovery_copy_and_validation_errors(self):
        media = Path(self.temp.name) / "media"
        source = media / ".http-recovery.partial.wav"
        with wave.open(str(source), "wb") as output:
            output.setnchannels(2); output.setsampwidth(4); output.setframerate(192000)
            output.writeframes(struct.pack("<ii", 123, -123))
        with source.open("ab") as output:
            output.write(struct.pack("<ii", 456, -456) + b"cut")
        original = source.read_bytes()
        status, _, candidates = self.request("GET", "/api/v1/daw/capture/recovery")
        self.assertEqual(status, 200)
        self.assertIn(source.name, [item["fileName"] for item in candidates["files"]])
        status, _, receipt = self.request("POST", "/api/v1/daw/capture", {"action": "recover", "fileName": source.name})
        self.assertEqual(status, 200)
        self.assertEqual(receipt["frames"], 2)
        self.assertEqual(receipt["discardedTrailingBytes"], 3)
        self.assertFalse(receipt["continuityVerified"])
        self.assertFalse(receipt["physicalOutputsArmed"])
        self.assertEqual(source.read_bytes(), original)
        with wave.open(receipt["path"], "rb") as recovered:
            self.assertEqual(recovered.readframes(2), original[44:60])
        for name in ("../escape.partial.wav", ".missing-http.partial.wav"):
            status, _, error = self.request("POST", "/api/v1/daw/capture", {"action": "recover", "fileName": name})
            self.assertEqual(status, 400)
            self.assertIn("error", error)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            conn.request("GET", "/recovery.js")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b"mountRecordingRecovery", response.read())
        finally:
            conn.close()

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.port = free_port()
        env = os.environ.copy()
        env["STAGEMESH_DATA_DIR"] = cls.temp.name
        env["STAGEMESH_GOVERNANCE_TOKEN_ONLY"] = "1"
        env["STAGEMESH_ADMIN_EMAIL_MODE"] = "outbox"
        env["STAGEMESH_AUTH_PROXY_TOKEN"] = "api-test-auth-proxy"
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / "backend" / "dev_server.py"), "--port", str(cls.port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=0.5)
                conn.request("GET", "/healthz")
                if conn.getresponse().status == 200:
                    conn.close()
                    return
            except OSError:
                time.sleep(0.05)
        cls.process.terminate()
        raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=3)
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        payload = json.dumps(body).encode() if body is not None else None
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=payload, headers=request_headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        result = (response.status, dict(response.getheaders()), data)
        conn.close()
        return result

    def test_stage_template_update_delete_enforce_expected_revision(self):
        status, _, created = self.request("POST", "/api/v1/templates", {
            "name": "Tour", "objects": [{"label": "Lead vocal", "x": 50, "y": 42}],
        })
        self.assertEqual(status, 201)
        template_id = created["templateId"]
        stale = self.request("PATCH", f"/api/v1/templates/{template_id}", {
            "expectedRevision": 99, "name": "Stale",
            "objects": [{"label": "Lead vocal", "x": 50, "y": 42}],
        })
        self.assertEqual(stale[0], 409)
        self.assertEqual(self.request("GET", f"/api/v1/templates/{template_id}")[2]["revision"], 1)
        status, _, updated = self.request("PATCH", f"/api/v1/templates/{template_id}", {
            "expectedRevision": 1, "name": "Updated",
            "objects": [{"label": "Lead vocal", "x": 50, "y": 42}],
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["revision"], 2)
        deleted = self.request("DELETE", f"/api/v1/templates/{template_id}", {"expectedRevision": 2})
        self.assertEqual(deleted[0], 200)
        self.assertTrue(deleted[2]["deleted"])
        self.assertEqual(self.request("GET", f"/api/v1/templates/{template_id}")[0], 404)

    def test_user_profile_customization_is_layered_portable_and_unarmed(self):
        profile = {
            "documentType": "org.upp.user-profile", "schemaVersion": 1,
            "minimumReaderSchemaVersion": 1, "profileId": "performer-alex", "revision": 1,
            "futureControlSurface": {"keep": True},
            "preferences": [
                {"namespace": "org.upp.ui", "key": "density", "layer": "base", "revision": 1, "type": "token", "value": "comfortable"},
                {"namespace": "org.upp.ui", "key": "density", "layer": "user", "revision": 2, "type": "token", "value": "compact"},
            ],
        }
        status, _, saved = self.request("POST", "/api/v1/profile", profile)
        self.assertEqual(status, 200)
        self.assertTrue(saved["futureControlSurface"]["keep"])
        self.assertEqual(saved["resolved"][0]["value"], "compact")
        self.assertFalse(saved["physicalOutputsArmed"])
        status, _, resolved = self.request("GET", "/api/v1/profile/resolved")
        self.assertEqual(status, 200)
        self.assertEqual(resolved["resolved"][0]["layer"], "user")

    def test_authenticated_interoperability_session_lifecycle(self):
        status, _, capability = self.request("POST", "/api/v1/interoperability/capabilities", {
            "id": "org.upp.profile.customization", "semanticVersion": "1.0.0", "schemaSha256": "a" * 64,
            "provenance": {"implementation": "api-test"},
        })
        self.assertEqual(status, 201); self.assertEqual(capability["id"], "org.upp.profile.customization")
        status, _, offer = self.request("POST", "/api/v1/interoperability/offer", {"targetParticipantId": "node-local", "ttlMs": 30000})
        self.assertEqual(status, 201); self.assertIn("transcriptSha256", offer)
        status, _, session = self.request("POST", "/api/v1/interoperability/accept", {"offer": offer})
        self.assertEqual(status, 200); self.assertEqual(session["state"], "negotiated"); self.assertTrue(session["authenticated"])
        status, _, consented = self.request("POST", "/api/v1/interoperability/consent", {"sessionId": session["sessionId"], "accepted": True})
        self.assertEqual(status, 200); self.assertEqual(consented["state"], "consented")
        status, _, active = self.request("POST", "/api/v1/interoperability/activate", {"sessionId": session["sessionId"]})
        self.assertEqual(status, 200); self.assertEqual(active["state"], "active"); self.assertFalse(active["physicalOutputsArmed"])

    def test_le_uwb_hub_end_to_end_sync_plan_never_arms_outputs(self):
        status, _, configured = self.request("POST", "/api/v1/le-uwb/configure", {"maxEndToEndNs": 25000000})
        if status == 503:
            self.skipTest("native engine not built")
        self.assertEqual(status, 200)
        self.assertFalse(configured["physicalOutputsArmed"])
        epoch = configured["authorityEpoch"]
        for node_id, stream_id, role, delay in ((301, 1, "performer-input", 2000000), (302, 2, "monitor-output", 3000000)):
            status, _, registered = self.request("POST", "/api/v1/le-uwb/nodes", {
                "nodeId": node_id, "leStreamId": stream_id, "role": role,
                "presentationDelayNs": delay, "required": True,
            })
            self.assertEqual(status, 201)
            self.assertFalse(registered["physicalOutputsArmed"])
        now = 2_000_000_000
        for node_id, offset in ((301, 70000), (302, -30000)):
            status, _, _ = self.request("POST", "/api/v1/le-uwb/observations/uwb", {
                "nodeId": node_id, "sequence": 1, "hubTimeNs": now, "nodeTimeNs": now + offset,
                "distanceMm": 8000, "rangeUncertaintyMm": 40, "clockUncertaintyNs": 30000,
            })
            self.assertEqual(status, 200)
            status, _, _ = self.request("POST", "/api/v1/le-uwb/observations/le", {
                "nodeId": node_id, "sequence": 1, "eventCounter": 1, "hubTimeNs": now,
                "transportLatencyNs": 3000000, "jitterNs": 100000,
            })
            self.assertEqual(status, 200)
        status, _, plan = self.request("POST", "/api/v1/le-uwb/plan", {
            "hubNowNs": now + 1000000, "showNowNs": 9000000000,
        })
        self.assertEqual(status, 200)
        self.assertEqual(plan["authorityEpoch"], epoch)
        self.assertTrue(plan["ready"])
        self.assertFalse(plan["physicalOutputsArmed"])
        status, _, node = self.request("GET", "/api/v1/le-uwb/nodes/301")
        self.assertEqual(status, 200)
        self.assertEqual(node["state"], "locked")
        self.assertTrue(node["authenticated"])

    def test_community_admin_email_window_and_token_vote(self):
        account_id = "api-community-user"
        proposal_id = "api-community-proposal"
        status, _, account = self.request("POST", "/api/v1/community/accounts", {"id": account_id, "email": "api@example.test"})
        self.assertEqual(status, 200)
        status, _, proposal = self.request("POST", "/api/v1/community/proposals", {"id": proposal_id, "title": "API community change"})
        self.assertEqual(status, 201)
        self.assertTrue(proposal["publicRecordRef"].startswith("upp-public-record:record-"))
        status, _, issued = self.request("POST", f"/api/v1/community/proposals/{proposal_id}/email-voters", {"userIds": [account_id], "windowHours": 24})
        self.assertEqual(status, 200)
        invitation = issued["issued"][0]
        self.assertTrue(invitation["publicRecordRef"].startswith("upp-public-record:record-"))
        sent = time.mktime(time.strptime(invitation["sentAt"][:19], "%Y-%m-%dT%H:%M:%S"))
        expires = time.mktime(time.strptime(invitation["expiresAt"][:19], "%Y-%m-%dT%H:%M:%S"))
        self.assertEqual(int(expires - sent), 24 * 3600)
        outbox = Path(self.temp.name) / "admin-email-outbox"
        messages = [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in outbox.glob("*.eml")]
        message = next(item for item in messages if str(item.get("To") or "") == "api@example.test")
        text = message.get_content()
        token = re.search(r"token=([A-Za-z0-9_-]+)", text).group(1)
        status, _, context = self.request("GET", "/api/v1/community/vote/context?token=" + token)
        self.assertEqual(status, 200)
        self.assertEqual(context["hypeVoteUnits"], 0.0)
        status, _, vote = self.request("POST", "/api/v1/community/vote", {"token": token, "choice": "yes"})
        self.assertEqual(status, 200)
        self.assertEqual(vote["rawVoteUnits"], 1.0)
        self.assertEqual(vote["hypeVoteUnits"], 0.0)
        self.assertTrue(vote["publicRecordRef"].startswith("upp-public-record:record-"))
        status, _, tally = self.request("GET", f"/api/v1/community/proposals/{proposal_id}/tally")
        self.assertEqual(status, 200)
        self.assertEqual(tally["rawVotes"]["yes"], 1)
        self.assertFalse(tally["bindingChangeReady"])
        status, _, reconciled = self.request("POST", "/api/v1/community/public-record/reconcile", {"proposalId": proposal_id})
        self.assertEqual(status, 200)
        self.assertEqual(reconciled["pending"], 0)
        self.assertTrue(reconciled["publicRecord"]["ok"])

    def test_community_account_session_votes_without_magic_link_credential(self):
        account_id = "api-session-user"
        proposal_id = "api-session-proposal"
        status, _, _ = self.request("POST", "/api/v1/community/accounts", {"id": account_id, "email": "session@example.test"})
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", "/api/v1/community/proposals", {"id": proposal_id, "title": "Session account vote"})
        self.assertEqual(status, 201)
        status, _, _ = self.request("POST", f"/api/v1/community/proposals/{proposal_id}/email-voters", {"userIds": [account_id], "windowHours": 24})
        self.assertEqual(status, 200)
        proxy_headers = {
            "X-StageMesh-Authenticated-User": account_id,
            "X-StageMesh-Auth-Proxy-Token": "api-test-auth-proxy",
        }
        status, _, session = self.request("POST", "/api/v1/community/session", {}, headers=proxy_headers)
        self.assertEqual(status, 201)
        self.assertEqual(session["account"]["id"], account_id)
        status, _, vote = self.request("POST", "/api/v1/community/vote", {
            "sessionToken": session["sessionToken"], "proposalId": proposal_id, "choice": "yes"
        })
        self.assertEqual(status, 200)
        self.assertEqual(vote["authMethod"], "account-session")

        status, _, _ = self.request("POST", "/api/v1/community/session/revoke", {}, headers=proxy_headers)
        self.assertEqual(status, 200)
        status, _, error = self.request("POST", "/api/v1/community/vote", {
            "sessionToken": session["sessionToken"], "proposalId": proposal_id, "choice": "yes"
        })
        self.assertEqual(status, 403)
        self.assertIn("revoked", error["error"])

    def test_compatibility_endpoints_and_version_headers(self):
        status, _, profile = self.request("GET", "/api/v1/compatibility")
        self.assertEqual(status, 200)
        self.assertEqual(profile["apiVersions"], [1])
        self.assertTrue(profile["preservesUnknown"])

        status, headers, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-UPP-API-Version"), "1")
        self.assertEqual(headers.get("X-UPP-Minimum-Reader-Version"), "1")
        self.assertTrue(state["compatibility"]["unknownFieldsPreserved"])

        status, _, report = self.request("POST", "/api/v1/compatibility/negotiate", {
            "remote": {
                "id": "legacy-node",
                "apiVersions": [1],
                "capabilities": profile["capabilities"],
                "preservesUnknown": True,
                "offlineCapable": True
            }
        })
        self.assertEqual(status, 200)
        self.assertTrue(report["compatible"])
        self.assertEqual(report["selectedApiVersion"], 1)

        legacy = dict(state)
        legacy.pop("compatibility", None)
        legacy.pop("apiVersion", None)
        legacy["transport"] = dict(legacy["transport"])
        legacy["transport"]["tempo"] = legacy["transport"].pop("bpm")
        status, _, migrated = self.request("POST", "/api/v1/compatibility/migrate-show-state", {"snapshot": legacy})
        self.assertEqual(status, 200)
        self.assertEqual(migrated["snapshot"]["apiVersion"], 1)
        self.assertIn("transport.tempo->transport.bpm", migrated["report"]["migrations"])

        status, _, plan = self.request("POST", "/api/v1/compatibility/show-plan", {
            "remote": {
                "id": "venue-node",
                "apiVersions": [1],
                "capabilities": profile["capabilities"],
                "preservesUnknown": True,
                "offlineCapable": True
            }
        })
        self.assertEqual(status, 200)
        self.assertTrue(plan["compatible"])
        self.assertTrue(any(item["id"] == "transport" for item in plan["showExecution"]["requirements"]))

    def test_venue_profile_and_prearrival_plan(self):
        venue = {
            "documentType": "org.upp.venue-profile",
            "schemaVersion": 1,
            "id": "api-venue",
            "name": "API Venue",
            "capabilities": ["audio.transport", "authority.fence"],
            "devices": [
                {"id": "api-audio", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
                 "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}},
                {"id": "api-lights", "status": "expected", "capabilities": ["lighting.artnet.send"],
                 "latency": {"fixedMs": 25, "jitterMs": 4, "timestamped": True}}
            ],
            "patch": {
                "audio.foh": {"target": "api-audio:out-1-2"},
                "audio.live-input": {"target": "api-audio:in-1-4"},
                "audio.monitor": {"target": "api-audio:out-3-6"},
                "lighting.primary": {"target": "api-lights:universe-1"}
            },
            "futureVenueExtension": {"preserve": True}
        }
        status, _, saved = self.request("POST", "/api/v1/venue/profile", {"venue": venue})
        self.assertEqual(status, 200)
        self.assertTrue(saved["futureVenueExtension"]["preserve"])
        status, _, loaded = self.request("GET", "/api/v1/venue/profile")
        self.assertEqual(status, 200)
        self.assertEqual(loaded["id"], "api-venue")
        status, _, plan = self.request("POST", "/api/v1/venue/plan", {})
        self.assertEqual(status, 200)
        self.assertTrue(plan["compatible"])
        self.assertIn(plan["readiness"], {"ready", "needs-patch"})
        self.assertTrue(any(item["id"] == "transport" for item in plan["devicePlan"]))

    def test_venue_adaptation_revision_conflict_is_explicit(self):
        status, _, current = self.request("GET", "/api/v1/venue/adaptations")
        self.assertEqual(status, 200)
        revision = current["revision"]
        status, _, _ = self.request("POST", "/api/v1/venue/adaptations/propose", {"expectedAdaptationRevision": revision})
        self.assertEqual(status, 201)
        status, _, conflict = self.request("POST", "/api/v1/venue/adaptations/propose", {"expectedAdaptationRevision": revision})
        self.assertEqual(status, 409)
        self.assertEqual(conflict["expected"], revision)
        self.assertGreater(conflict["current"], revision)

    def test_venue_adaptation_transaction_commit_and_rollback(self):
        native_status, _, native = self.request("GET", "/api/v1/native")
        if native_status != 200 or not native.get("available"):
            self.skipTest("native engine not built")
        status, _, before_state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        before_venue = before_state["system"]["venue"]
        venue = {
            "documentType": "org.upp.venue-profile",
            "schemaVersion": 1,
            "id": "tx-venue",
            "name": "Transactional Venue",
            "capabilities": ["audio.transport", "authority.fence"],
            "devices": [
                {"id": "tx-audio", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
                 "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}},
                {"id": "tx-lighting", "status": "expected", "capabilities": ["lighting.artnet.send", "lighting.schedule", "lighting.state"],
                 "latency": {"fixedMs": 25, "jitterMs": 4, "timestamped": True}},
                {"id": "tx-midi", "status": "expected", "capabilities": ["midi.read", "midi.write"],
                 "latency": {"fixedMs": 4, "jitterMs": 1, "timestamped": True}}
            ],
            "patch": {
                "audio.foh": {"target": "tx-audio:out-1-2"},
                "audio.live-input": {"target": "tx-audio:in-1-4"},
                "audio.monitor": {"target": "tx-audio:out-3-6"},
                "lighting.primary": {
                    "target": "tx-lighting:front-wash-left",
                    "execution": {
                        "protocol": "sacn", "target": "127.0.0.1", "port": 5568, "universeBase": 101,
                        "fixtures": {
                            "front-wash-left": {
                                "universe": 0, "address": 17,
                                "parameters": {"intensity": 0, "red": 1, "green": 2, "blue": 3}
                            }
                        }
                    }
                },
                "midi.performance": {"target": "tx-midi:input"}
            }
        }
        status, _, _ = self.request("POST", "/api/v1/venue/profile", {"venue": venue})
        self.assertEqual(status, 200)
        status, _, proposed = self.request("POST", "/api/v1/venue/adaptations/propose", {})
        self.assertEqual(status, 201)
        txid = proposed["transactionId"]
        status, _, validated = self.request("POST", f"/api/v1/venue/adaptations/{txid}/validate", {})
        self.assertEqual(status, 200)
        self.assertTrue(validated["validation"]["valid"])
        status, _, committed = self.request("POST", f"/api/v1/venue/adaptations/{txid}/commit", {"mode": "immediate", "requestedBy": "api-test"})
        self.assertEqual(status, 200)
        self.assertEqual(committed["status"], "committed")
        self.assertTrue(committed["receipt"]["intentPreserved"])
        status, _, active = self.request("GET", "/api/v1/venue/adaptations/active")
        self.assertEqual(status, 200)
        self.assertEqual(active["active"]["venueId"], "tx-venue")
        status, _, semantic = self.request("POST", "/api/v1/lighting/schedule", {
            "fixtureId": "front-wash-left", "parameter": "red", "normalizedValue": 0.5,
            "targetShowTimeNs": 0, "fixedLatencyNs": 0, "jitterNs": 0, "minimumLookaheadNs": 0
        })
        self.assertEqual(status, 200)
        self.assertTrue(semantic["venuePatchApplied"])
        self.assertEqual(semantic["universe"], 0)
        self.assertEqual(semantic["channel"], 18)
        self.assertEqual(semantic["value"], 128)
        status, _, rolled = self.request("POST", f"/api/v1/venue/adaptations/{txid}/rollback", {"requestedBy": "api-test"})
        self.assertEqual(status, 200)
        self.assertEqual(rolled["status"], "rolled-back")
        status, _, after_state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        self.assertEqual(after_state["system"]["venue"], before_venue)

    def test_state_has_etag_and_conflicts_are_explicit(self):
        status, headers, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        etag = headers["ETag"]
        status, _, updated = self.request("PATCH", "/api/v1/show", {"bpm": 128}, {"If-Match": etag, "X-StageMesh-Command-Id": "api-test-1"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["transport"]["bpm"], 128)
        status, _, conflict = self.request("PATCH", "/api/v1/show", {"bpm": 129}, {"If-Match": etag, "X-StageMesh-Command-Id": "api-test-2"})
        self.assertEqual(status, 409)
        self.assertIn("current", conflict)


    def test_node_authority_and_replication_fence_physical_execution(self):
        status, _, node = self.request("GET", "/api/v1/node")
        self.assertEqual(status, 200)
        self.assertEqual(node["role"], "primary")

        status, _, envelope = self.request("GET", "/api/v1/replication/export")
        self.assertEqual(status, 200)
        self.assertEqual(envelope["revision"], envelope["snapshot"]["revision"])

        status, _, standby = self.request("POST", "/api/v1/node/role", {
            "role": "standby", "acknowledgeAuthorityChange": True
        })
        self.assertEqual(status, 200)
        self.assertEqual(standby["role"], "standby")
        self.assertFalse(standby["physicalAuthority"])

        status, _, refused = self.request("PATCH", "/api/v1/system", {"capacity": 73})
        self.assertEqual(status, 503)
        self.assertIn("standby node is read-only", refused["error"])

        status, _, applied = self.request("POST", "/api/v1/replication/apply", envelope)
        self.assertEqual(status, 200)
        self.assertTrue(applied["accepted"])
        status, _, duplicate = self.request("POST", "/api/v1/replication/apply", envelope)
        self.assertEqual(status, 400)
        self.assertIn("duplicate", duplicate["error"])

        status, _, primary = self.request("POST", "/api/v1/node/role", {
            "role": "primary", "acknowledgeAuthorityChange": True, "forceAuthorityOverride": True
        })
        self.assertEqual(status, 200)
        self.assertEqual(primary["role"], "primary")
        self.assertTrue(primary["physicalAuthority"])
        self.assertFalse(primary["lightingArmed"])

    def test_resource_revisions_allow_unrelated_control_points(self):
        status, headers, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        stale_global = headers["ETag"]
        system_revision = state["resourceRevisions"]["system"]
        monitor_revision = state["resourceRevisions"]["monitor:alex"]

        status, _, _ = self.request(
            "PATCH", "/api/v1/system", {"capacity": 61},
            {"If-Match": stale_global, "X-StageMesh-Resource-If-Match": f'"system@{system_revision}"'}
        )
        self.assertEqual(status, 200)

        # Global ETag is now stale, but Alex's monitor resource has not changed.
        status, headers2, changed = self.request(
            "PATCH", "/api/v1/players/alex/monitor", {"self": 83},
            {"If-Match": stale_global, "X-StageMesh-Resource-If-Match": f'"monitor:alex@{monitor_revision}"'}
        )
        self.assertEqual(status, 200)
        self.assertEqual(changed["players"][0]["monitor"]["self"], 83)
        self.assertIn("X-StageMesh-Resource-ETag", headers2)

        # Reusing the now-stale monitor token conflicts on that resource only.
        status, _, conflict = self.request(
            "PATCH", "/api/v1/players/alex/monitor", {"self": 84},
            {"X-StageMesh-Resource-If-Match": f'"monitor:alex@{monitor_revision}"'}
        )
        self.assertEqual(status, 409)
        self.assertIn("monitor:alex", conflict["error"])

    def test_duplicate_command_is_returned_once(self):
        _, headers, state = self.request("GET", "/api/v1/state")
        etag = headers["ETag"]
        command_headers = {"If-Match": etag, "X-StageMesh-Command-Id": "duplicate-api-test"}
        status1, _, first = self.request("PATCH", "/api/v1/system", {"capacity": 66}, command_headers)
        status2, headers2, second = self.request("PATCH", "/api/v1/system", {"capacity": 20}, command_headers)
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertEqual(headers2.get("X-StageMesh-Deduplicated"), "true")
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(second["system"]["capacity"], 66)

    def test_runtime_plan_and_ledger_health(self):
        status, _, plan = self.request("GET", "/api/v1/system/plan")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["id"] == "audio-core" for item in plan["decisions"]))
        status, _, ledger = self.request("GET", "/api/v1/public-record/verify")
        self.assertEqual(status, 200)
        self.assertTrue(ledger["ok"])

    def test_timing_plan_is_latency_aware(self):
        status, _, plan = self.request("POST", "/api/v1/timing/plan", {
            "nowNs": 80000000,
            "targetNs": 100000000,
            "fixedLatencyNs": 5000000,
            "jitterNs": 2000000,
            "minimumLookaheadNs": 6000000,
            "timestamped": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(plan["reserveNs"], 9000000)
        self.assertEqual(plan["dispatchNs"], 91000000)
        self.assertFalse(plan["late"])
        self.assertIn(plan["source"], {"native", "bridge"})

    def test_native_status_endpoint_is_explicit(self):
        status, _, native = self.request("GET", "/api/v1/native")
        self.assertIn(status, {200, 503})
        self.assertIn("available", native)

    def test_auto_notation_capture_and_musicxml_export(self):
        status, _, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        resource = state["resourceRevisions"]["midi:alex"]
        headers = {"X-StageMesh-Resource-If-Match": f'"midi:alex@{resource}"'}
        status, _, state = self.request("POST", "/api/v1/players/alex/midi/input", {
            "status": 144, "data1": 60, "data2": 96, "showTimeSeconds": 0.12
        }, headers)
        self.assertEqual(status, 200)
        resource = state["resourceRevisions"]["midi:alex"]
        status, _, state = self.request("POST", "/api/v1/players/alex/midi/input", {
            "status": 128, "data1": 60, "data2": 0, "showTimeSeconds": 0.62
        }, {"X-StageMesh-Resource-If-Match": f'"midi:alex@{resource}"'})
        self.assertEqual(status, 200)
        self.assertEqual(state["notation"]["alex"]["notes"][0]["name"], "C4")

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("GET", "/api/v1/players/alex/notation.musicxml")
        response = conn.getresponse()
        xml = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("musicxml", response.getheader("Content-Type"))
        self.assertIn('<score-partwise version="4.0">', xml)
        conn.close()

    def test_clock_status_and_native_observation(self):
        status, _, clock = self.request("GET", "/api/v1/clock")
        self.assertEqual(status, 200)
        self.assertIn(clock["state"], {"free", "locked", "holdover"})
        self.assertEqual(clock["transportAuthority"], "stagemesh")
        if clock["available"]:
            status, _, _ = self.request("POST", "/api/v1/clock/source", {"source": "ptp-test"})
            self.assertEqual(status, 200)
            status, _, observed = self.request("POST", "/api/v1/clock/observe", {"localNs": 1000000, "sourceNs": 1005000})
            self.assertEqual(status, 200)
            self.assertEqual(observed["state"], "locked")
            self.assertEqual(observed["offsetNs"], 5000)

    def test_midi_device_bindings_are_desired_state(self):
        status, _, devices = self.request("GET", "/api/v1/midi/devices")
        self.assertEqual(status, 200)
        self.assertIn("devices", devices)

        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["midi-bindings"]
        status, _, bound = self.request(
            "POST", "/api/v1/midi/devices/future-controller/attach", {"playerId": "maya"},
            {"X-StageMesh-Resource-If-Match": f'"midi-bindings@{revision}"'}
        )
        self.assertEqual(status, 200)
        self.assertEqual(bound["midi"]["bindings"]["future-controller"], "maya")
        revision = bound["resourceRevisions"]["midi-bindings"]
        status, _, unbound = self.request(
            "POST", "/api/v1/midi/devices/future-controller/detach", {},
            {"X-StageMesh-Resource-If-Match": f'"midi-bindings@{revision}"'}
        )
        self.assertEqual(status, 200)
        self.assertNotIn("future-controller", unbound["midi"]["bindings"])

    def test_midi_learn_maps_next_control_without_manual_numbers(self):
        status, _, targets = self.request("GET", "/api/v1/midi/mapping-targets")
        self.assertEqual(status, 200); self.assertIn("filter.cutoff", {item["targetId"] for item in targets["targets"]})
        status, _, learning = self.request("POST", "/api/v1/midi/learn", {"targetId":"filter.cutoff","quantize":"off","keySync":False})
        self.assertEqual(status, 200); self.assertEqual(learning["learning"]["state"], "waiting-for-gesture")
        _, _, state = self.request("GET", "/api/v1/state"); resource=state["resourceRevisions"]["midi:alex"]
        status, _, _ = self.request("POST", "/api/v1/players/alex/midi/input", {"deviceId":"learn-controller","status":0xB3,"data1":74,"data2":96,"showTimeSeconds":1.0}, {"X-StageMesh-Resource-If-Match":f'"midi:alex@{resource}"'})
        self.assertEqual(status, 200)
        status, _, mapped = self.request("GET", "/api/v1/midi/mappings");self.assertEqual(status,200);self.assertIsNone(mapped["learning"]);self.assertEqual(mapped["mappings"][-1]["source"]["number"],74);self.assertEqual(mapped["mappings"][-1]["source"]["channel"],3);self.assertFalse(mapped["physicalOutputsArmed"])
        mapping_id=mapped["mappings"][-1]["mappingId"];status,_,after=self.request("POST",f"/api/v1/midi/mappings/{mapping_id}/delete",{});self.assertEqual(status,200);self.assertNotIn(mapping_id,{item["mappingId"] for item in after["mappings"]})


    def test_audio_device_selection_is_desired_state(self):
        status, _, devices = self.request("GET", "/api/v1/audio/devices")
        self.assertEqual(status, 200)
        self.assertIn("devices", devices)
        self.assertIn("executionBackend", devices)

        _, _, state = self.request("GET", "/api/v1/state")
        audio_revision = state["resourceRevisions"]["audio"]
        status, _, updated = self.request(
            "POST", "/api/v1/audio",
            {"deviceId": "future-venue-audio", "sampleRate": 96000, "bufferFrames": 128, "limiterCeilingDb": -2.0},
            {"X-StageMesh-Resource-If-Match": f'"audio@{audio_revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["audio"]["deviceId"], "future-venue-audio")
        self.assertEqual(updated["audio"]["sampleRate"], 96000)
        self.assertEqual(updated["audio"]["bufferFrames"], 128)
        status, _, devices = self.request("GET", "/api/v1/audio/devices")
        self.assertEqual(status, 200)
        self.assertEqual(devices["desiredDeviceId"], "future-venue-audio")
        self.assertFalse(devices["desiredConnected"])


    def test_audio_hardware_activation_is_explicit(self):
        status, _, devices = self.request("POST", "/api/v1/audio/scan", {})
        self.assertEqual(status, 200)
        alsa = next((device for device in devices.get("devices", []) if device.get("backend") == "alsa" and device.get("output")), None)
        if alsa is None:
            self.assertFalse(any(device.get("backend") == "alsa" and device.get("output") for device in devices.get("devices", [])))
            return

        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["audio"]
        status, _, state = self.request(
            "POST", "/api/v1/audio", {"deviceId": alsa["id"], "sampleRate": 48000, "bufferFrames": 64},
            {"X-StageMesh-Resource-If-Match": f'"audio@{revision}"'},
        )
        self.assertEqual(status, 200)

        status, _, refused = self.request("POST", "/api/v1/audio/activate", {"output": 0})
        self.assertEqual(status, 400)
        self.assertIn("acknowledgePhysicalOutput", refused["error"])

        status, _, active = self.request("POST", "/api/v1/audio/activate", {"output": 0, "acknowledgePhysicalOutput": True})
        if not re.fullmatch(r"hw:\d{1,3},\d{1,3}", alsa.get("address", "")):
            self.assertEqual(status, 503); self.assertIn("numeric ALSA", active["error"]); return
        self.assertEqual(status, 200)
        self.assertEqual(active["executionBackend"], "alsa")
        time.sleep(0.02)
        status, _, stream = self.request("GET", "/api/v1/audio/stream")
        self.assertEqual(status, 200)
        self.assertTrue(stream["active"])
        self.assertGreater(stream["callbacks"], 0)
        status, _, _ = self.request("POST", "/api/v1/audio/deactivate", {})
        self.assertEqual(status, 200)


    def test_multi_output_audio_surface_is_independent(self):
        status, _, devices = self.request("POST", "/api/v1/audio/scan", {})
        self.assertEqual(status, 200)
        status, _, outputs = self.request("GET", "/api/v1/audio/outputs")
        self.assertEqual(status, 200)
        self.assertEqual(len(outputs["outputs"]), 4)
        alsa = next((device for device in devices.get("devices", []) if device.get("backend") == "alsa" and device.get("output")), None)
        if alsa is None:
            self.assertFalse(any(device.get("backend") == "alsa" and device.get("output") for device in devices.get("devices", [])))
            return
        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["audio"]
        status, _, updated = self.request(
            "POST", "/api/v1/audio",
            {"outputs": [{"slot": 1, "deviceId": alsa["id"], "purpose": "monitor", "playerId": "alex", "master": 0.75, "limiterCeilingDb": -3.0}]},
            {"X-StageMesh-Resource-If-Match": f'"audio@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["audio"]["outputs"][1]["playerId"], "alex")
        status, _, active = self.request("POST", "/api/v1/audio/outputs/1/activate", {"acknowledgePhysicalOutput": True})
        if not re.fullmatch(r"hw:\d{1,3},\d{1,3}", alsa.get("address", "")):
            self.assertEqual(status, 503); self.assertIn("numeric ALSA", active["error"]); return
        self.assertEqual(status, 200)
        self.assertEqual(active["slot"], 1)
        time.sleep(0.02)
        status, _, output = self.request("GET", "/api/v1/audio/outputs/1")
        self.assertEqual(status, 200)
        self.assertTrue(output["active"])
        self.assertEqual(output["purpose"], "monitor")
        self.assertEqual(output["playerId"], "alex")
        self.assertIn("rateMeasured", output)
        self.assertIn("ratePpm", output)
        self.assertIn("correctionPpm", output)
        self.assertIn("compensatedBlocks", output)
        self.assertIn("maxExcessGapMs", output)
        status, _, _ = self.request("POST", "/api/v1/audio/outputs/1/deactivate", {})
        self.assertEqual(status, 200)

    def test_lighting_network_requires_persistent_target_and_transient_arm(self):
        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["lighting-network"]
        status, _, state = self.request(
            "POST", "/api/v1/lighting/network", {"protocol": "artnet", "target": "127.0.0.1", "port": 6454},
            {"X-StageMesh-Resource-If-Match": f'"lighting-network@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["lighting"]["network"]["target"], "127.0.0.1")
        self.assertFalse(state["lighting"]["network"]["armed"])

        status, _, refused = self.request("POST", "/api/v1/lighting/network/arm", {"armed": True})
        self.assertEqual(status, 400)
        self.assertIn("acknowledgePhysicalOutput", refused["error"])

        status, _, armed = self.request("POST", "/api/v1/lighting/network/arm", {"armed": True, "acknowledgePhysicalOutput": True})
        if status == 503 and "native lighting output unavailable" in armed.get("error", ""):
            self.skipTest("native lighting output unavailable")
        self.assertEqual(status, 200)
        self.assertTrue(armed["armed"])
        status, _, scheduled = self.request("POST", "/api/v1/lighting/schedule", {
            "universe": 0, "channel": 3, "value": 44,
            "targetShowTimeNs": 0, "fixedLatencyNs": 0, "jitterNs": 0, "minimumLookaheadNs": 0
        })
        self.assertEqual(status, 200)
        self.assertTrue(scheduled["physicalOutput"])
        time.sleep(0.03)
        status, _, network = self.request("GET", "/api/v1/lighting/network")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(network["packetsSent"], 1)
        status, _, disarmed = self.request("POST", "/api/v1/lighting/network/arm", {"armed": False})
        self.assertEqual(status, 200)
        self.assertFalse(disarmed["armed"])

        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["lighting-network"]
        status, _, state = self.request(
            "POST", "/api/v1/lighting/network",
            {"protocol": "sacn", "target": "127.0.0.1", "port": 5568, "universeBase": 101},
            {"X-StageMesh-Resource-If-Match": f'"lighting-network@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["lighting"]["network"]["protocol"], "sacn")
        status, _, armed = self.request("POST", "/api/v1/lighting/network/arm", {"armed": True, "acknowledgePhysicalOutput": True})
        self.assertEqual(status, 200)
        self.assertEqual(armed["protocol"], "sacn")
        self.assertEqual(armed["universeBase"], 101)
        status, _, _ = self.request("POST", "/api/v1/lighting/schedule", {
            "universe": 0, "channel": 1, "value": 55,
            "targetShowTimeNs": 0, "fixedLatencyNs": 0, "jitterNs": 0, "minimumLookaheadNs": 0
        })
        self.assertEqual(status, 200)
        time.sleep(0.03)
        status, _, network = self.request("GET", "/api/v1/lighting/network")
        self.assertEqual(status, 200)
        self.assertEqual(network["protocol"], "sacn")
        self.assertGreaterEqual(network["packetsSent"], 1)
        self.request("POST", "/api/v1/lighting/network/arm", {"armed": False})

    def test_timestamped_lighting_schedule_uses_show_time(self):
        status, _, native = self.request("GET", "/api/v1/native")
        if status != 200 or not native.get("available"):
            self.skipTest("native lighting scheduler unavailable")
        status, _, scheduled = self.request("POST", "/api/v1/lighting/schedule", {
            "universe": 0, "channel": 1, "value": 91,
            "targetShowTimeNs": 120000000,
            "fixedLatencyNs": 20000000, "jitterNs": 5000000, "minimumLookaheadNs": 20000000
        })
        self.assertEqual(status, 200)
        self.assertEqual(scheduled["reserveNs"], 30000000)
        self.assertEqual(scheduled["dispatchShowTimeNs"], 90000000)
        self.assertFalse(scheduled["physicalOutput"])


    def test_failover_status_and_controlled_promotion_surface(self):
        status, _, replication = self.request("GET", "/api/v1/replication/status")
        self.assertEqual(status, 200)
        self.assertIn("transport", replication)
        self.assertIn("authenticated", replication)
        status, _, failover = self.request("GET", "/api/v1/failover")
        self.assertEqual(status, 200)
        self.assertIn(failover["state"], {"primary", "waiting", "healthy", "suspect", "eligible"})
        self.assertEqual(failover["electionMode"], "manual-after-failure-detection")

    def test_audio_input_capture_is_explicit_and_separate_from_output(self):
        status, _, devices = self.request("POST", "/api/v1/audio/scan", {})
        self.assertEqual(status, 200)
        capture = next((d for d in devices.get("devices", []) if d.get("backend") == "alsa" and d.get("input") and d.get("connected")), None)
        if capture is None:
            self.assertFalse(any(device.get("backend") == "alsa" and device.get("input") for device in devices.get("devices", [])))
            return

        _, _, state = self.request("GET", "/api/v1/state")
        revision = state["resourceRevisions"]["audio"]
        status, _, state = self.request(
            "POST", "/api/v1/audio",
            {"inputDeviceId": capture["id"], "inputPlayerId": "jordan", "inputRoute": {"output": 0, "gain": 0.25}},
            {"X-StageMesh-Resource-If-Match": f'"audio@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["audio"]["inputDeviceId"], capture["id"])
        self.assertEqual(state["audio"]["inputRoute"]["gain"], 0.25)

        status, _, refused = self.request("POST", "/api/v1/audio/input/activate", {"acknowledgePhysicalInput": True})
        self.assertEqual(status, 400)
        self.assertIn("acknowledgeSignalRoute", refused["error"])

        status, _, active = self.request("POST", "/api/v1/audio/input/activate", {
            "acknowledgePhysicalInput": True, "acknowledgeSignalRoute": True, "channels": 2
        })
        if not re.fullmatch(r"hw:\d{1,3},\d{1,3}", capture.get("address", "")):
            self.assertEqual(status, 503); self.assertIn("numeric ALSA", active["error"]); return
        self.assertEqual(status, 200)
        self.assertTrue(active["active"])
        self.assertEqual(active["playerId"], "jordan")
        self.assertGreaterEqual(active["source"], 5)
        status, _, capture_status = self.request("GET", "/api/v1/audio/input")
        self.assertEqual(status, 200)
        self.assertTrue(capture_status["active"])
        status, _, _ = self.request("POST", "/api/v1/audio/input/deactivate", {})
        self.assertEqual(status, 200)

    def test_multi_input_status_and_witness_status_are_public(self):
        status, _, witness = self.request("GET", "/api/v1/witness")
        self.assertEqual(status, 200)
        self.assertIn("configured", witness)
        status, _, inputs = self.request("GET", "/api/v1/audio/inputs")
        self.assertEqual(status, 200)
        self.assertEqual(len(inputs["inputs"]), 4)
        self.assertEqual([item["slot"] for item in inputs["inputs"]], [0, 1, 2, 3])

    def test_event_stream_is_available(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("GET", "/api/v1/events?after=0")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertTrue(response.getheader("Content-Type").startswith("text/event-stream"))
        lines = []
        for _ in range(5):
            line = response.fp.readline().decode("utf-8").strip()
            lines.append(line)
            if line.startswith("data:"):
                break
        self.assertTrue(any(line.startswith("id:") for line in lines))
        self.assertTrue(any(line == "event: stagemesh" for line in lines))
        self.assertTrue(any(line.startswith("data:") for line in lines))
        conn.close()


    def test_handoff_policy_is_revisioned_and_decision_is_explicit(self):
        status, _, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        revision = state["resourceRevisions"]["handoff"]
        status, _, updated = self.request(
            "PATCH", "/api/v1/handoff",
            {
                "policy": {"maxLocalLagMs": 15.0},
                "liveInputs": [{"slot": 0, "mode": "network", "ready": True, "sourceId": "redundant-vocal"}],
                "deterministicSources": [{"id": "tracks-main", "kind": "track", "required": True, "shadowCapable": True, "localAssetReady": True}],
            },
            {"X-StageMesh-Resource-If-Match": f'"handoff@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["handoff"]["policy"]["maxLocalLagMs"], 15.0)
        self.assertTrue(updated["handoff"]["liveInputs"][0]["ready"])
        status, _, decision = self.request("GET", "/api/v1/handoff/decision")
        self.assertEqual(status, 200)
        self.assertIn("authorityReady", decision)
        self.assertIn("programLogicReady", decision)
        self.assertFalse(decision["readyForProgramTakeover"])
        self.assertIn("recommendedAction", decision)

    def test_technology_openness_api_scales_standardization_thresholds(self):
        status, _, state = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        revision = state["resourceRevisions"]["technology"]
        extension = {
            "id": "artist.open-motion.v1",
            "maturity": "standard",
            "publicSpec": True,
            "conformanceTests": True,
            "interoperabilityEvidence": True,
            "fallbackDefined": True,
            "backwardCompatible": True,
            "unknownPreservationTested": True,
            "futureField": {"preserve": True},
            "implementations": [
                {"id":"impl-a","independentGroup":"a","conformancePass":True,"interopPeers":["impl-b"]},
                {"id":"impl-b","independentGroup":"b","conformancePass":True,"interopPeers":["impl-a"]}
            ]
        }
        status, _, updated = self.request(
            "PATCH", "/api/v1/technology",
            {"ecosystemParticipants": 5, "extensions": [extension]},
            {"X-StageMesh-Resource-If-Match": f'"technology@{revision}"'},
        )
        self.assertEqual(status, 200)
        self.assertTrue(updated["technology"]["extensions"][0]["futureField"]["preserve"])
        status, _, unbound = self.request("GET", "/api/v1/technology/assessment")
        self.assertEqual(status, 200); self.assertIn("artist.open-motion.v1", unbound["invalidDeclaredMaturityIds"])

        status, _, receipt = self.request("POST", "/api/v1/technology/conformance-receipt", {
            "extensionId": "artist.open-motion.v1", "requestedBy": "api-test"
        })
        self.assertEqual(status, 201); self.assertTrue(receipt["adoptionRecordRef"].startswith("upp-public-record:record-"))

        status, _, current = self.request("GET", "/api/v1/state")
        revision = current["resourceRevisions"]["technology"]
        status, _, rebound = self.request(
            "PATCH", "/api/v1/technology",
            {"ecosystemParticipants": 75, "extensions": [{"id":"artist.open-motion.v1", "adoptionRecordRef":receipt["adoptionRecordRef"]}]},
            {"X-StageMesh-Resource-If-Match": f'"technology@{revision}"'},
        )
        self.assertEqual(status, 200); self.assertEqual(rebound["technology"]["ecosystemParticipants"], 75)
        status, _, assessment = self.request("GET", "/api/v1/technology/assessment")
        self.assertEqual(status, 200)
        self.assertEqual(assessment["scaleTier"], "large")
        self.assertEqual(assessment["standardIndependentGroupsRequired"], 4)
        self.assertNotIn("artist.open-motion.v1", assessment["invalidDeclaredMaturityIds"])
        self.assertIn("artist.open-motion.v1", assessment["scaleRevalidationIds"])
        self.assertIn("artist.open-motion.v1", assessment["verifiedConformanceReceiptIds"])
        self.assertTrue(assessment["experimentalWithoutPermission"])
        self.assertTrue(assessment["noAiParticipantValid"])
        status, _, negotiation = self.request("POST", "/api/v1/technology/negotiate", {
            "localCapabilities": ["upp.audio.output/1", "artist.future/9"],
            "remoteCapabilities": ["upp.audio.output/1", "vendor.new-light/2"],
        })
        self.assertEqual(status, 200)
        self.assertEqual(negotiation["common"], ["upp.audio.output/1"])
        self.assertFalse(negotiation["implicitCoercion"])
        self.assertIn("artist.future/9", negotiation["preservedUnknown"])


    def test_venue_reconciliation_adapter_evidence_and_status(self):
        venue = {
            "documentType": "org.upp.venue-profile", "schemaVersion": 1,
            "id": "reconcile-venue", "name": "Reconcile Venue",
            "capabilities": ["audio.transport", "authority.fence"],
            "devices": [
                {"id": "rec-audio", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
                 "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}},
                {"id": "rec-lighting", "status": "expected", "capabilities": ["lighting.artnet.send", "lighting.schedule", "lighting.state"],
                 "latency": {"fixedMs": 20, "jitterMs": 2, "timestamped": True}},
                {"id": "rec-midi", "status": "expected", "capabilities": ["midi.read", "midi.write"],
                 "latency": {"fixedMs": 4, "jitterMs": 1, "timestamped": True}}
            ],
            "patch": {
                "audio.foh": {"target": "rec-audio:out-1-2", "authority": "foh"},
                "audio.live-input": {"target": "rec-audio:in-1-4"},
                "audio.monitor": {"target": "rec-audio:out-3-6"},
                "lighting.primary": {"target": "rec-lighting:universe-1", "authority": "lighting"},
                "midi.performance": {"target": "rec-midi:input"}
            }
        }
        status, _, _ = self.request("POST", "/api/v1/venue/profile", {"venue": venue})
        self.assertEqual(status, 200)
        status, _, proposed = self.request("POST", "/api/v1/venue/adaptations/propose", {})
        self.assertEqual(status, 201)
        txid = proposed["transactionId"]
        status, _, validated = self.request("POST", f"/api/v1/venue/adaptations/{txid}/validate", {})
        self.assertEqual(status, 200)
        self.assertTrue(validated["validation"]["valid"])
        status, _, committed = self.request("POST", f"/api/v1/venue/adaptations/{txid}/commit", {"mode": "immediate"})
        self.assertEqual(status, 200)
        self.assertEqual(committed["status"], "committed")

        status, _, report = self.request("GET", "/api/v1/venue/reconciliation")
        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "unverified")

        status, _, accepted = self.request("POST", "/api/v1/venue/reconciliation/report", {
            "patchKey": "audio.foh", "providerId": "rec-audio", "target": "rec-audio:out-1-2",
            "healthy": True, "authorityHolder": "foh"
        })
        self.assertEqual(status, 200)
        self.assertTrue(accepted["accepted"])
        status, _, evidence = self.request("GET", "/api/v1/venue/reconciliation/evidence")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["patchKey"] == "audio.foh" for item in evidence["reports"]))
        status, _, lease = self.request("POST", "/api/v1/venue/authority/leases", {
            "scope": "audio.foh", "grantee": "production", "grantedBy": "foh", "ttlSeconds": 60
        })
        self.assertEqual(status, 201)
        self.assertTrue(lease["active"])
        status, _, authority = self.request("GET", "/api/v1/venue/authority")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["leaseId"] == lease["leaseId"] for item in authority["active"]))
        status, _, resource_lease = self.request("POST", "/api/v1/venue/authority/leases", {
            "scopeKind": "resource", "scope": "lighting-network", "grantee": "lighting", "ttlSeconds": 60
        })
        self.assertEqual(status, 201)
        self.assertEqual(resource_lease["scopeKind"], "resource")
        self.assertEqual(resource_lease["context"], "runtime")
        status, _, authority = self.request("GET", "/api/v1/venue/authority")
        self.assertTrue(any(item["leaseId"] == resource_lease["leaseId"] for item in authority["activeByKind"]["resource"]))
        status, _, revoked = self.request("POST", f"/api/v1/venue/authority/leases/{lease['leaseId']}/revoke", {"requestedBy": "foh"})
        self.assertEqual(status, 200)
        self.assertFalse(revoked["active"])
        status, _, public_record = self.request("GET", "/api/v1/public-record")
        self.assertEqual(status, 200)
        self.assertTrue(public_record["ok"]); self.assertGreaterEqual(public_record["records"], 3)
        status, _, witness_error = self.request("POST", "/api/v1/public-record/witness", {
            "version": 1, "witnessId": "unconfigured", "recordHash": revoked["publicRecord"]["recordHash"],
            "issuedAtNs": 1, "hmacSha256": "0" * 64
        })
        self.assertEqual(status, 403)

    def test_stage_launcher_projects_and_dispatches_core_transport(self):
        status, _, launcher = self.request("GET", "/api/v1/stage/launcher")
        self.assertEqual(status, 200)
        self.assertEqual(launcher["documentType"], "org.upp.stage-launcher")
        self.assertEqual(launcher["authority"], "core")
        self.assertFalse(launcher["physicalOutputsArmed"])
        status, _, running = self.request("POST", "/api/v1/stage/launcher/action", {"action":"transport.toggle","source":"keyboard","actionId":"launcher-test-toggle"})
        self.assertEqual(status, 200);self.assertTrue(running["transport"]["running"])
        self.assertEqual(running["feedback"]["source"], "keyboard")
        status, _, duplicate = self.request("POST", "/api/v1/stage/launcher/action", {"action":"transport.toggle","source":"keyboard","actionId":"launcher-test-toggle"})
        self.assertEqual(status,200);self.assertTrue(duplicate["transport"]["running"]);self.assertTrue(duplicate["feedback"]["deduplicated"])
        status, _, stopped = self.request("POST", "/api/v1/stage/launcher/action", {"action":"transport.stop","source":"touch","actionId":"launcher-test-stop"})
        self.assertEqual(status, 200);self.assertFalse(stopped["transport"]["running"]);self.assertFalse(stopped["physicalOutputsArmed"])



if __name__ == "__main__":
    unittest.main()
