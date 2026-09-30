from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Adapter:
    id: str
    name: str
    kind: str
    priority: int
    estimated_cpu: float
    estimated_memory_mb: int
    capabilities: tuple[str, ...]
    fallbacks: tuple[str, ...]
    realtime: bool = False
    healthy: bool = True


class AdapterRegistry:
    """Capability-facing registry for replaceable runtime modules.

    These are placeholders for native/plugin adapters. The state/API only sees
    capabilities and resource contracts, not vendor-specific implementation.
    """

    def __init__(self) -> None:
        self._adapters = {
            "audio-core": Adapter(
                "audio-core", "Audio Core", "audio", 0, 24.0, 96,
                ("clock.authority", "audio.transport", "audio.monitor", "audio.mix", "audio.output.multi", "audio.output.fanout"),
                ("full", "minimal"), True,
            ),
            "native-show-core": Adapter(
                "native-show-core", "Native Show Core", "core", 0, 5.0, 48,
                ("core.parameter-registry", "core.cue-action-graph", "core.runtime-show", "core.generation-swap",
                 "core.routing-transaction", "core.execution-journal", "core.shadow-render-plan", "core.shadow-prebuffer", "plugin.parameter-bridge"),
                ("full", "essential-only"), True,
            ),
            "audio-input": Adapter(
                "audio-input", "Audio Input Capture", "audio", 0, 6.0, 32,
                ("audio.input.discover", "audio.input.capture", "audio.input.multi", "audio.source.route", "authority.explicit-arm"),
                ("full", "off"), True,
            ),
            "witness-quorum": Adapter(
                "witness-quorum", "Authority Witness Quorum", "core", 0, 0.5, 8,
                ("authority.lease", "authority.quorum", "failover.fence", "failover.auto", "failover.continuity"),
                ("full", "manual-failover"), False,
            ),
            "replication-core": Adapter(
                "replication-core", "Hot Standby Replication", "core", 1, 1.5, 16,
                ("replication.push", "replication.heartbeat", "replication.execution-telemetry", "failover.detect", "failover.program-continuity", "handoff.readiness", "authority.fence"),
                ("full", "heartbeat-only"), False,
            ),
            "handoff-logic": Adapter(
                "handoff-logic", "Deterministic Handoff Policy", "core", 1, 0.5, 8,
                ("handoff.policy", "handoff.decision", "handoff.live-redundancy", "handoff.shadow-readiness", "handoff.execution-evidence"),
                ("full", "state-only"), False,
            ),
            "midi-bridge": Adapter(
                "midi-bridge", "MIDI Bridge", "midi", 1, 4.0, 24,
                ("midi.discover", "midi.hotplug", "midi.bind", "midi.read", "midi.write", "clock.follow"),
                ("full", "timestamped-only"), True,
            ),
            "lighting-core": Adapter(
                "lighting-core", "Lighting Scheduler", "lighting", 1, 2.0, 12,
                ("lighting.schedule", "lighting.state", "lighting.artnet.encode", "lighting.sacn.encode", "lighting.fixture.resolve", "clock.follow"),
                ("full", "state-only"), False, True,
            ),
            "lighting-network": Adapter(
                "lighting-network", "Art-Net Network Output", "lighting", 1, 3.0, 16,
                ("lighting.artnet.send", "lighting.unicast", "authority.explicit-arm"),
                ("full", "off"), False, True,
            ),
            "lighting-sacn": Adapter(
                "lighting-sacn", "sACN Network Output", "lighting", 1, 3.0, 16,
                ("lighting.sacn.send", "lighting.unicast", "authority.explicit-arm"),
                ("full", "off"), False, True,
            ),
            "logistics-core": Adapter(
                "logistics-core", "Logistics Core", "production", 2, 2.0, 16,
                ("cue.read", "cue.notify", "human.context"),
                ("full", "critical-only"), False,
            ),
            "notation-core": Adapter(
                "notation-core", "Auto Notation", "notation", 3, 3.0, 24,
                ("notation.capture", "notation.quantize", "notation.musicxml"),
                ("full", "capture-only", "off"), False,
            ),
            "visualizer": Adapter(
                "visualizer", "Stage Visualizer", "visual", 4, 18.0, 160,
                ("stage.render", "lighting.preview"),
                ("full", "reduced", "state-only", "off"), False,
            ),
            "compatibility-core": Adapter(
                "compatibility-core", "UPP Compatibility Core", "core", 1, 0.7, 12,
                ("compatibility.api-negotiate", "compatibility.schema-migrate", "compatibility.unknown-preserve", "compatibility.adapter-fallback", "compatibility.report", "venue.profile", "venue.compatibility-plan", "venue.discovery-evidence", "venue.human-fallback", "venue.adaptation-transaction", "venue.patch-layer", "venue.commit-boundary", "venue.rollback", "venue.reconciliation", "venue.realization-evidence", "venue.repair-proposal", "venue.authority-lease"),
                ("full", "preserve-only"), False,
            ),
            "technology-openness": Adapter(
                "technology-openness", "Technology Openness Resolver", "governance", 5, 0.5, 8,
                ("technology.experimental", "technology.maturity", "technology.independent-evidence", "technology.scale-safeguards", "technology.unknown-preservation"),
                ("full", "read-only"), False,
            ),
            "community-governance": Adapter(
                "community-governance", "Community Governance", "governance", 5, 0.5, 12,
                ("governance.proposal", "governance.vote", "governance.hype-decay", "governance.email-window", "governance.binding-gate"),
                ("full", "read-only"), False,
            ),
            "ai-connector": Adapter(
                "ai-connector", "AI Connector", "ai", 5, 20.0, 256,
                ("ai.interpret", "ai.recommend", "ai.compare"),
                ("full", "off"), False,
            ),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        # Keep the public projection aligned with adapter-manifest-v1.  The
        # dataclass retains Pythonic field names internally, but callers and
        # manifest validators consume the schema's camelCase names.
        return [
            {
                "id": adapter.id,
                "name": adapter.name,
                "kind": adapter.kind,
                "priority": adapter.priority,
                "estimatedCpu": adapter.estimated_cpu,
                "estimatedMemoryMb": adapter.estimated_memory_mb,
                "capabilities": list(adapter.capabilities),
                "fallbacks": list(adapter.fallbacks),
                "realtime": adapter.realtime,
                "healthy": adapter.healthy,
                "physicalOutputsArmed": False,
            }
            for adapter in self._adapters.values()
        ]

    def plan(self, capacity: float, mode: str) -> dict[str, Any]:
        capacity = max(0.0, min(100.0, float(capacity)))
        decisions = []
        used = 0.0
        mode_max_priority = {"full": 5, "reduced": 4, "safe": 2, "audio": 0}.get(mode, 2)

        for adapter in sorted(self._adapters.values(), key=lambda item: (item.priority, item.id)):
            status = "full"
            reason = "within policy and capacity"
            if not adapter.healthy:
                status, reason = "off", "adapter unhealthy"
            elif adapter.priority > mode_max_priority:
                status, reason = adapter.fallbacks[-1], f"disabled by {mode} policy"
            elif used + adapter.estimated_cpu > capacity:
                if adapter.priority <= 1:
                    status, reason = adapter.fallbacks[-2] if len(adapter.fallbacks) > 1 else "minimal", "protected critical/show adapter under constrained capacity"
                    used += max(1.0, adapter.estimated_cpu * 0.35)
                else:
                    status, reason = adapter.fallbacks[-1], "suspended to protect higher-priority work"
            else:
                used += adapter.estimated_cpu

            decisions.append({
                "id": adapter.id,
                "priority": adapter.priority,
                "status": status,
                "reason": reason,
                "capabilities": adapter.capabilities,
            })

        return {
            "capacity": capacity,
            "mode": mode,
            "estimatedCpuUsed": round(used, 1),
            "headroom": round(max(0.0, capacity - used), 1),
            "decisions": decisions,
        }
