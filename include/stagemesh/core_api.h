#ifndef STAGEMESH_CORE_API_H
#define STAGEMESH_CORE_API_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SF_API_VERSION(major, minor) ((((uint32_t)(major)) << 16u) | ((uint32_t)(minor)))
#define SF_API_VERSION_MAJOR(version) ((uint32_t)(version) >> 16u)
#define SF_API_VERSION_MINOR(version) ((uint32_t)(version) & 0xffffu)
#define SF_CORE_API_VERSION SF_API_VERSION(1u, 67u)

/* Base ABI stays deliberately small. Domain APIs are queried as versioned
 * string-named extensions so experimental work does not require changing the
 * core ABI or allocating globally coordinated bit flags. */
#define SF_EXT_EVENT_SINK_V1       "org.upp.core.event-sink/1"
#define SF_EXT_RESOURCE_CONTROL_V1 "org.upp.core.resource-control/1"
#define SF_EXT_RESOURCE_PLANNER_V1 "org.upp.core.resource-planner/1"
#define SF_EXT_STATE_PROVIDER_V1   "org.upp.core.state-provider/1"
#define SF_EXT_CORE_CONTROL_V1     "org.upp.core.control-state/1"
#define SF_EXT_SHOW_TIMELINE_V1    "org.upp.core.show-timeline/1"
#define SF_EXT_SHOW_DISPATCH_V1    "org.upp.core.show-dispatch/1"
#define SF_EXT_SHOW_EXECUTION_LOOP_V1 "org.upp.core.show-execution-loop/1"
#define SF_EXT_CUE_STATE_V1        "org.upp.core.cue-state/1"
#define SF_EXT_AUTOMATION_STATE_V1 "org.upp.core.automation-state/1"
#define SF_EXT_PARAMETER_REGISTRY_V1 "org.upp.core.parameter-registry/1"
#define SF_EXT_CUE_ACTION_GRAPH_V1 "org.upp.core.cue-action-graph/1"
#define SF_EXT_RUNTIME_SHOW_V1 "org.upp.core.runtime-show/1"
#define SF_EXT_ROUTING_TRANSACTION_V1 "org.upp.core.routing-transaction/1"
#define SF_EXT_CORE_JOURNAL_V1 "org.upp.core.journal/1"
#define SF_EXT_SHADOW_RENDER_PLANNER_V1 "org.upp.core.shadow-render-planner/1"
#define SF_EXT_SHADOW_PREBUFFER_V1 "org.upp.core.shadow-prebuffer/1"
#define SF_EXT_SHADOW_RENDER_EXECUTOR_V1 "org.upp.core.shadow-render-executor/1"
#define SF_EXT_PLUGIN_PARAMETER_BRIDGE_V1 "org.upp.plugin.parameter-bridge/1"
#define SF_EXT_AUDIO_EFFECT_CHAIN_V1 "org.upp.audio.effect-chain/1"
#define SF_EXT_AUDIO_EFFECT_ADAPTER_V1 "org.upp.audio.effect-adapter/1"
#define SF_EXT_CANONICAL_AUDIO_V1 "org.upp.audio.canonical-domain/1"
#define SF_EXT_AUDIO_RATE_CONVERTER_V1 "org.upp.audio.rate-converter/1"
#define SF_EXT_LE_UWB_HUB_V1 "org.upp.stage.le-uwb-hub/1"
#define SF_EXT_LE_ISO_HARDWARE_V1 "org.upp.hardware.le-iso/1"
#define SF_EXT_UWB_HARDWARE_BRIDGE_V1 "org.upp.hardware.uwb-bridge/1"
#define SF_EXT_USER_PROFILE_CUSTOMIZATION_V1 "org.upp.profile.customization/1"
#define SF_EXT_INTEROPERABILITY_HANDSHAKE_V1 "org.upp.core.interoperability-handshake/1"
#define SF_EXT_AUTHENTICATED_INTEROP_SESSION_V1 "org.upp.core.authenticated-interoperability-session/1"
#define SF_EXT_PROFILE_PROJECTION_V1 "org.upp.profile.projection/1"
#define SF_EXT_SEMANTIC_CAPABILITY_REGISTRY_V1 "org.upp.core.semantic-capability-registry/1"
#define SF_EXT_HARDWARE_BENCH_V1 "org.upp.hardware.bench-report/1"
#define SF_EXT_SESSION_CHANNEL_V1 "org.upp.core.session-channel/1"
#define SF_EXT_LOCAL_IPC_V1 "org.upp.core.local-ipc/1"
#define SF_EXT_SECURITY_STATE_V1 "org.upp.core.security-state/1"
#define SF_EXT_ISOLATED_PLUGIN_HOST_V1 "org.upp.audio.isolated-plugin-host/1"
#define SF_EXT_PLATFORM_QUALIFICATION_V1 "org.upp.hardware.platform-qualification/1"
#define SF_EXT_DAW_SESSION_V1 "org.upp.daw.session/1"
#define SF_EXT_DAW_RENDER_PLAN_V1 "org.upp.daw.render-plan/1"
#define SF_EXT_DAW_MEDIA_V1 "org.upp.daw.media/1"
#define SF_EXT_DAW_EDIT_HISTORY_V1 "org.upp.daw.edit-history/1"
#define SF_EXT_DAW_RENDERER_V1 "org.upp.daw.renderer/1"
#define SF_EXT_DAW_RECORDING_V1 "org.upp.daw.recording/1"
#define SF_EXT_DAW_TEMPO_MAP_V1 "org.upp.daw.tempo-map/1"
#define SF_EXT_DAW_MEDIA_LIBRARY_V1 "org.upp.daw.media-library/1"
#define SF_EXT_DAW_PLUGIN_CATALOG_V1 "org.upp.daw.plugin-catalog/1"
#define SF_EXT_DAW_RECOVERY_V1 "org.upp.daw.recovery/1"
#define SF_EXT_DAW_STREAM_RENDERER_V1 "org.upp.daw.stream-renderer/1"
#define SF_EXT_DAW_PLAYBACK_PREFETCH_V1 "org.upp.daw.playback-prefetch/1"
#define SF_EXT_DAW_RECORDING_SPOOL_V1 "org.upp.daw.recording-spool/1"
#define SF_EXT_DAW_PLAYBACK_QUEUE_V1 "org.upp.daw.playback-queue/1"
#define SF_EXT_DAW_MULTITRACK_CAPTURE_V1 "org.upp.daw.multitrack-capture/1"
#define SF_EXT_DAW_ARRANGEMENT_PRODUCER_V1 "org.upp.daw.arrangement-producer/1"
#define SF_EXT_DAW_PCM_BLOCK_TRANSFER_V1 "org.upp.daw.pcm-block-transfer/1"
#define SF_EXT_DAW_CAPTURE_DRAIN_V1 "org.upp.daw.capture-drain/1"
#define SF_EXT_DAW_PUNCH_CAPTURE_V1 "org.upp.daw.punch-loop-capture/1"
#define SF_EXT_STAGE_LAUNCHER_V1 "org.upp.stage.launcher-projection/1"
#define SF_EXT_STREAMING_SAMPLE_BANK_V1 "org.upp.audio.streaming-sample-bank/1"
#define SF_EXT_PLUGIN_DELAY_GRAPH_V1 "org.upp.audio.plugin-delay-graph/1"
#define SF_EXT_REALTIME_AUDIT_V1 "org.upp.core.realtime-audit/1"
#define SF_EXT_INGRESS_AUDIT_V1 "org.upp.core.ingress-audit/1"
#define SF_EXT_PLUGIN_DELAY_COMPENSATION_V1 "org.upp.audio.plugin-delay-compensation/1"
#define SF_EXT_MIDI_LEARN_MAPPING_V1 "org.upp.midi.learn-mapping/1"
#define SF_EXT_MASTER_MUSICAL_SYNC_V1 "org.upp.midi.master-musical-sync/1"
#define SF_EXT_NATIVE_MIDI_PERFORMANCE_V1 "org.upp.midi.native-performance/1"
#define SF_EXT_SAMPLER_VOICE_ENGINE_V1 "org.upp.audio.sampler-voice-engine/1"
#define SF_EXT_TRANSPORT_DISCIPLINE_V1 "org.upp.timing.transport-discipline/1"
#define SF_EXT_MIDI_CLOCK_V1 "org.upp.midi.clock-24ppqn/1"
#define SF_EXT_AUDIO_DEVICE_V1     "org.upp.audio.device/1"
#define SF_EXT_AUDIO_ROUTING_V1    "org.upp.audio.routing/1"
#define SF_EXT_AUDIO_STREAM_V1     "org.upp.audio.stream/1"
#define SF_EXT_MONITOR_CONTROL_V1  "org.upp.audio.monitor-control/1"
#define SF_EXT_TIMING_PROFILE_V1   "org.upp.timing.profile/1"
#define SF_EXT_CLOCK_DISCIPLINE_V1 "org.upp.timing.clock-discipline/1"
#define SF_EXT_MIDI_SCHEDULER_V1   "org.upp.midi.scheduler/1"
#define SF_EXT_MIDI_INPUT_V1       "org.upp.midi.input/1"
#define SF_EXT_NOTATION_CAPTURE_V1 "org.upp.notation.capture/1"
#define SF_EXT_LIGHTING_OUTPUT_V1  "org.upp.lighting.output/1"
#define SF_EXT_LIGHTING_NETWORK_V1 "org.upp.lighting.network/1"
#define SF_EXT_AUTHORITY_V1        "org.upp.core.authority/1"
#define SF_EXT_REPLICATION_V1      "org.upp.core.replication/1"
#define SF_EXT_REPLICATION_TRANSPORT_V1 "org.upp.core.replication-transport/1"
#define SF_EXT_FAILOVER_V1          "org.upp.core.failover/1"
#define SF_EXT_AUDIO_INPUT_STREAM_V1 "org.upp.audio.input-stream/1"
#define SF_EXT_AUDIO_MULTI_INPUT_V1  "org.upp.audio.multi-input-stream/1"
#define SF_EXT_WITNESS_LEASE_V1      "org.upp.core.witness-lease/1"
#define SF_EXT_AUDIO_MULTI_OUTPUT_V1  "org.upp.audio.multi-output-stream/1"
#define SF_EXT_AUDIO_DRIFT_COMPENSATION_V1 "org.upp.audio.drift-compensation/1"
#define SF_EXT_FAILOVER_CONTINUITY_V1 "org.upp.core.failover-continuity/1"
#define SF_EXT_FAILOVER_CONTINUITY_V2 "org.upp.core.failover-continuity/2"
#define SF_EXT_REPLICATION_TELEMETRY_V1 "org.upp.core.replication-telemetry/1"
#define SF_EXT_HANDOFF_READINESS_V1 "org.upp.core.handoff-readiness/1"
#define SF_EXT_HANDOFF_POLICY_V1 "org.upp.core.handoff-policy/1"
#define SF_EXT_HANDOFF_DECISION_V1 "org.upp.core.handoff-decision/1"
#define SF_EXT_HANDOFF_EXECUTION_V1 "org.upp.core.handoff-execution/1"
#define SF_EXT_PLANNED_HANDOFF_V1 "org.upp.core.planned-handoff/1"
#define SF_EXT_TECHNOLOGY_REGISTRY_V1 "org.upp.core.technology-registry/1"
#define SF_EXT_TECHNOLOGY_ASSESSMENT_V1 "org.upp.core.technology-assessment/1"
#define SF_EXT_TECHNOLOGY_NEGOTIATION_V1 "org.upp.core.technology-negotiation/1"
#define SF_EXT_COMMUNITY_GOVERNANCE_V1 "org.upp.core.community-governance/1"
#define SF_EXT_HYPE_MATURITY_V1 "org.upp.core.hype-maturity/1"
#define SF_EXT_VOTE_NOTIFICATION_V1 "org.upp.core.vote-notification/1"
#define SF_EXT_COMPATIBILITY_NEGOTIATION_V1 "org.upp.core.compatibility-negotiation/1"
#define SF_EXT_SCHEMA_MIGRATION_V1 "org.upp.core.schema-migration/1"
#define SF_EXT_UNKNOWN_PRESERVATION_V1 "org.upp.core.unknown-preservation/1"
#define SF_EXT_VENUE_PROFILE_V1 "org.upp.venue.profile/1"
#define SF_EXT_VENUE_COMPATIBILITY_V1 "org.upp.venue.compatibility/1"
#define SF_EXT_VENUE_ADAPTATION_V1 "org.upp.venue.adaptation/1"
#define SF_EXT_VENUE_PATCH_LAYER_V1 "org.upp.venue.patch-layer/1"
#define SF_EXT_VENUE_RECONCILIATION_V1 "org.upp.venue.reconciliation/1"
#define SF_EXT_VENUE_REALIZATION_EVIDENCE_V1 "org.upp.venue.realization-evidence/1"
#define SF_EXT_VENUE_AUTHORITY_LEASE_V1 "org.upp.venue.authority-lease/1"

typedef uint64_t sf_handle;

typedef enum sf_priority {
    SF_PRIORITY_CRITICAL = 0,
    SF_PRIORITY_SHOW = 1,
    SF_PRIORITY_PRODUCTION = 2,
    SF_PRIORITY_ENHANCEMENT = 3,
    SF_PRIORITY_VISUAL = 4,
    SF_PRIORITY_BACKGROUND = 5
} sf_priority;

typedef enum sf_result {
    SF_OK = 0,
    SF_ERROR_INVALID_ARGUMENT = 1,
    SF_ERROR_NOT_FOUND = 2,
    SF_ERROR_UNSUPPORTED = 3,
    SF_ERROR_PERMISSION = 4,
    SF_ERROR_BUSY = 5,
    SF_ERROR_VERSION = 6,
    SF_ERROR_CONFLICT = 7
} sf_result;

typedef struct sf_time {
    uint64_t monotonic_ns;
    uint64_t sample_position;
    double show_seconds;
    double bpm;
} sf_time;

typedef struct sf_resource_profile {
    sf_priority priority;
    float estimated_cpu_percent;
    uint64_t estimated_memory_bytes;
    uint8_t requires_gpu;
    uint8_t realtime;
    uint8_t can_degrade;
    uint8_t can_suspend;
} sf_resource_profile;

typedef enum sf_operating_mode {
    SF_MODE_FULL = 0,
    SF_MODE_REDUCED = 1,
    SF_MODE_SAFE_SHOW = 2,
    SF_MODE_AUDIO_ONLY = 3
} sf_operating_mode;

typedef enum sf_resource_plan_action {
    SF_RESOURCE_FULL = 0,
    SF_RESOURCE_DEGRADED = 1,
    SF_RESOURCE_SUSPENDED = 2,
    SF_RESOURCE_UNAVAILABLE = 3
} sf_resource_plan_action;

typedef enum sf_resource_plan_reason {
    SF_RESOURCE_WITHIN_BUDGET = 0,
    SF_RESOURCE_UNHEALTHY = 1,
    SF_RESOURCE_DISABLED_BY_MODE = 2,
    SF_RESOURCE_PROTECTED_UNDER_PRESSURE = 3,
    SF_RESOURCE_SUSPENDED_FOR_HEADROOM = 4,
    SF_RESOURCE_CANNOT_FIT = 5
} sf_resource_plan_reason;

typedef struct sf_resource_plan_request {
    uint32_t struct_size;
    sf_priority priority;
    float estimated_cpu_percent;
    float degraded_cpu_fraction;
    uint8_t healthy;
    uint8_t can_degrade;
    uint8_t can_suspend;
} sf_resource_plan_request;

typedef struct sf_resource_plan_decision {
    uint32_t struct_size;
    sf_resource_plan_action action;
    sf_resource_plan_reason reason;
    float allocated_cpu_percent;
} sf_resource_plan_decision;

typedef struct sf_resource_plan_summary {
    uint32_t struct_size;
    float capacity_percent;
    float used_percent;
    float headroom_percent;
    uint32_t full_count;
    uint32_t degraded_count;
    uint32_t suspended_count;
    uint32_t unavailable_count;
} sf_resource_plan_summary;

typedef struct sf_resource_planner_v1 {
    uint32_t struct_size;
    sf_result (*plan)(void *context, float capacity_percent, sf_operating_mode mode, const sf_resource_plan_request *requests, size_t request_count, sf_resource_plan_decision *decisions, sf_resource_plan_summary *out_summary);
    void *context;
} sf_resource_planner_v1;

typedef struct sf_module_info {
    uint32_t struct_size;
    uint32_t api_version;
    const char *id;
    const char *name;
    const char *version;
    const char *const *capability_ids;
    uint32_t capability_count;
    sf_resource_profile resources;
} sf_module_info;

typedef struct sf_event {
    uint32_t struct_size;
    uint64_t event_id;
    uint64_t revision;
    sf_time at;
    const char *type;
    const void *payload;
    uint32_t payload_size;
} sf_event;

typedef enum sf_core_mutation_status {
    SF_CORE_MUTATION_APPLIED = 0,
    SF_CORE_MUTATION_DUPLICATE = 1,
    SF_CORE_MUTATION_CONFLICT = 2,
    SF_CORE_MUTATION_INVALID = 3,
    SF_CORE_MUTATION_STALE_SNAPSHOT = 4,
    SF_CORE_MUTATION_BUSY = 5
} sf_core_mutation_status;

typedef enum sf_core_transport_action {
    SF_CORE_TRANSPORT_PLAY = 0,
    SF_CORE_TRANSPORT_PAUSE = 1,
    SF_CORE_TRANSPORT_STOP = 2,
    SF_CORE_TRANSPORT_REWIND = 3,
    SF_CORE_TRANSPORT_SET_BPM = 4,
    SF_CORE_TRANSPORT_SEEK_SECONDS = 5
} sf_core_transport_action;

typedef struct sf_core_control_status {
    uint32_t struct_size;
    uint64_t revision;
    uint64_t external_revision;
    uint64_t transport_revision;
    uint64_t applied_commands;
    uint64_t duplicate_commands;
    uint64_t conflicts;
    uint64_t snapshot_commits;
    uint64_t stale_snapshots;
} sf_core_control_status;

typedef struct sf_core_mutation_result {
    uint32_t struct_size;
    sf_core_mutation_status status;
    uint64_t revision;
    uint64_t resource_revision;
    uint64_t external_revision;
} sf_core_mutation_result;

typedef struct sf_core_control_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_core_control_status *out_status);
    sf_result (*transport_mutate)(void *context, uint64_t command_id, uint64_t expected_resource_revision, sf_core_transport_action action, double value, sf_core_mutation_result *out_result);
    sf_result (*monitor_mutate)(void *context, uint64_t command_id, uint64_t expected_resource_revision, const char *player_id, const char *field, double value, sf_core_mutation_result *out_result);
    void *context;
} sf_core_control_v1;

typedef enum sf_show_event_type {
    SF_SHOW_EVENT_TRANSPORT = 0,
    SF_SHOW_EVENT_MIDI = 1,
    SF_SHOW_EVENT_LIGHTING = 2,
    SF_SHOW_EVENT_CUE = 3,
    SF_SHOW_EVENT_AUTOMATION = 4
} sf_show_event_type;

typedef enum sf_show_event_flags {
    SF_SHOW_EVENT_NONE = 0,
    SF_SHOW_EVENT_AUTHORITATIVE = 1u << 0,
    SF_SHOW_EVENT_REPLAY_SAFE = 1u << 1,
    SF_SHOW_EVENT_DROP_IF_LATE = 1u << 2,
    SF_SHOW_EVENT_AUTOMATION_RELEASE_OWNER = 1u << 3
} sf_show_event_flags;

typedef struct sf_show_transport_payload {
    sf_core_transport_action action;
    double value;
} sf_show_transport_payload;

typedef struct sf_show_midi_payload {
    uint8_t status;
    uint8_t data1;
    uint8_t data2;
    uint8_t port;
} sf_show_midi_payload;

typedef struct sf_show_lighting_payload {
    uint16_t universe;
    uint16_t channel;
    uint8_t value;
    uint8_t reserved[3];
} sf_show_lighting_payload;

typedef struct sf_show_cue_payload {
    uint64_t cue_id;
} sf_show_cue_payload;

typedef struct sf_show_automation_payload {
    uint64_t target_id;
    uint64_t parameter_id;
    float value;
    uint32_t duration_ms;
} sf_show_automation_payload;

typedef union sf_show_event_payload {
    sf_show_transport_payload transport;
    sf_show_midi_payload midi;
    sf_show_lighting_payload lighting;
    sf_show_cue_payload cue;
    sf_show_automation_payload automation;
} sf_show_event_payload;

typedef struct sf_show_event {
    uint32_t struct_size;
    uint64_t event_id;
    uint64_t revision;
    uint64_t show_time_ns;
    uint64_t owner_id;
    sf_show_event_type type;
    sf_priority priority;
    uint16_t flags;
    uint16_t reserved;
    sf_show_event_payload payload;
} sf_show_event;

typedef struct sf_show_dispatch_status {
    uint32_t struct_size;
    uint64_t submitted;
    uint64_t accepted;
    uint64_t dispatched;
    uint64_t pending;
    uint64_t next_show_time_ns;
    uint64_t duplicates;
    uint64_t invalid;
    uint64_t ingress_overflow;
    uint64_t timeline_overflow;
    uint64_t late;
    uint64_t dropped_late;
    uint64_t dispatch_failures;
    uint64_t cancelled;
} sf_show_dispatch_status;

typedef struct sf_show_timeline_v1 {
    uint32_t struct_size;
    sf_result (*submit)(void *context, const sf_show_event *event);
    sf_result (*cancel)(void *context, sf_show_event_type type, uint64_t event_id);
    sf_result (*status)(void *context, sf_show_dispatch_status *out_status);
    void *context;
} sf_show_timeline_v1;

typedef struct sf_show_dispatch_v1 {
    uint32_t struct_size;
    /* Host/engine-owner operation. Implementations must serialize this call so
     * only one execution owner drains the typed timeline. */
    sf_result (*dispatch_until)(void *context, uint64_t show_time_ns, uint32_t *out_dispatched_count);
    sf_result (*status)(void *context, sf_show_dispatch_status *out_status);
    void *context;
} sf_show_dispatch_v1;

typedef struct sf_show_execution_loop_status {
    uint32_t struct_size;
    uint8_t running;
    uint8_t reserved0[3];
    uint64_t cycles;
    uint64_t wakeups;
    uint64_t timed_waits;
    uint64_t dispatched;
    uint64_t manual_drains;
    uint64_t cancel_requests;
    uint64_t last_show_time_ns;
    uint64_t pending;
    uint64_t next_show_time_ns;
} sf_show_execution_loop_status;

typedef struct sf_show_execution_loop_v1 {
    uint32_t struct_size;
    sf_result (*start)(void *context);
    sf_result (*stop)(void *context);
    sf_result (*wake)(void *context);
    sf_result (*status)(void *context, sf_show_execution_loop_status *out_status);
    void *context;
} sf_show_execution_loop_v1;

typedef struct sf_cue_state_status {
    uint32_t struct_size;
    uint64_t current_cue_id;
    uint64_t previous_cue_id;
    uint64_t last_event_id;
    uint64_t last_show_time_ns;
    uint64_t transitions;
} sf_cue_state_status;

typedef struct sf_cue_state_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_cue_state_status *out_status);
    void *context;
} sf_cue_state_v1;

typedef struct sf_automation_state_status {
    uint32_t struct_size;
    uint64_t revision;
    uint64_t registered;
    uint64_t applied;
    uint64_t owner_conflicts;
    uint64_t capacity_rejections;
    uint64_t invalid;
    uint64_t owner_releases;
} sf_automation_state_status;

typedef struct sf_automation_parameter_status {
    uint32_t struct_size;
    uint8_t registered;
    uint8_t ramping;
    uint8_t reserved0[2];
    uint64_t target_id;
    uint64_t parameter_id;
    uint64_t owner_id;
    uint64_t revision;
    uint64_t last_event_id;
    uint64_t ramp_start_show_ns;
    uint64_t ramp_end_show_ns;
    float start_value;
    float target_value;
    float current_value;
    uint32_t reserved1;
    uint64_t updates;
} sf_automation_parameter_status;

typedef struct sf_automation_state_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_automation_state_status *out_status);
    sf_result (*parameter_status)(void *context, uint64_t target_id, uint64_t parameter_id, uint64_t show_time_ns, sf_automation_parameter_status *out_status);
    sf_result (*render_block)(void *context, uint64_t target_id, uint64_t parameter_id, uint64_t start_show_ns, uint64_t step_ns, float *output, size_t frames);
    void *context;
} sf_automation_state_v1;


typedef enum sf_monitor_channel {
    SF_MONITOR_SELF = 0,
    SF_MONITOR_VOCALS = 1,
    SF_MONITOR_BAND = 2,
    SF_MONITOR_CLICK = 3,
    SF_MONITOR_TALKBACK = 4,
    SF_MONITOR_AMBIENT = 5
} sf_monitor_channel;

typedef struct sf_timing_profile {
    uint32_t struct_size;
    uint64_t fixed_latency_ns;
    uint64_t jitter_ns;
    uint64_t minimum_lookahead_ns;
    uint8_t jitter_margin_multiplier;
    uint8_t supports_timestamped_execution;
} sf_timing_profile;

typedef struct sf_timing_plan {
    uint32_t struct_size;
    uint64_t target_time_ns;
    uint64_t dispatch_time_ns;
    uint64_t reserve_ns;
    uint8_t late;
    uint8_t timestamped;
} sf_timing_plan;

typedef enum sf_clock_lock_state {
    SF_CLOCK_FREE_RUNNING = 0,
    SF_CLOCK_LOCKED = 1,
    SF_CLOCK_HOLDOVER = 2
} sf_clock_lock_state;

typedef struct sf_clock_status {
    uint32_t struct_size;
    sf_clock_lock_state state;
    int64_t offset_ns;
    double drift_ppm;
    uint64_t source_age_ns;
    uint64_t projected_time_ns;
    uint64_t observations;
} sf_clock_status;

typedef struct sf_clock_discipline_v1 {
    uint32_t struct_size;
    sf_result (*set_source)(void *context, const char *source_id);
    sf_result (*observe)(void *context, uint64_t local_ns, uint64_t source_ns);
    sf_result (*status)(void *context, uint64_t local_ns, sf_clock_status *out_status);
    void *context;
} sf_clock_discipline_v1;

typedef struct sf_transport_discipline_observation {
    uint32_t struct_size;
    uint64_t sequence, authority_epoch, local_ns, source_ns, local_show_ns, source_show_ns;
} sf_transport_discipline_observation;
typedef struct sf_transport_discipline_status {
    uint32_t struct_size;
    sf_clock_lock_state state;
    uint64_t source_id, authority_epoch, last_sequence, observations, rejected, holdover_entries;
    int64_t phase_error_ns;
    double drift_ppm, correction_ppm, applied_rate;
    uint64_t source_age_ns;
    uint8_t configured, physical_outputs_armed;
} sf_transport_discipline_status;
typedef struct sf_transport_discipline_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context,uint64_t source_id,uint64_t authority_epoch,uint64_t holdover_ns,double max_slew_ppm,uint64_t recovery_window_ns);
    sf_result (*observe)(void *context,const sf_transport_discipline_observation *observation);
    sf_result (*status)(void *context,uint64_t local_ns,sf_transport_discipline_status *out_status);
    void *context;
} sf_transport_discipline_v1;

typedef struct sf_midi_clock_status {
    uint32_t struct_size;
    uint64_t authority_epoch, emitted, received, rejected, last_sequence, last_pulse_show_ns, maximum_jitter_ns;
    double bpm;
    uint8_t running, configured, physical_outputs_armed;
} sf_midi_clock_status;
typedef struct sf_midi_clock_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context,uint64_t authority_epoch,double bpm,uint64_t boundary_show_ns);
    sf_result (*start)(void *context,uint64_t authority_epoch,uint64_t boundary_show_ns);
    sf_result (*stop)(void *context,uint64_t authority_epoch,uint64_t show_time_ns);
    sf_result (*set_tempo)(void *context,uint64_t authority_epoch,double bpm,uint64_t boundary_show_ns);
    sf_result (*observe_pulse)(void *context,uint64_t authority_epoch,uint64_t sequence,uint64_t show_time_ns);
    sf_result (*status)(void *context,sf_midi_clock_status *out_status);
    void *context;
} sf_midi_clock_v1;

typedef struct sf_audio_device_info {
    uint32_t struct_size;
    const char *id;
    const char *name;
    const char *backend;
    const char *backend_address;
    uint8_t input;
    uint8_t output;
    uint8_t connected;
} sf_audio_device_info;

typedef struct sf_audio_device_config {
    uint32_t struct_size;
    double sample_rate;
    uint32_t input_channels;
    uint32_t output_channels;
    uint32_t frames_per_buffer;
} sf_audio_device_config;

typedef struct sf_audio_device_v1 {
    uint32_t struct_size;
    uint32_t (*device_count)(void *context);
    sf_result (*get_device)(void *context, uint32_t index, sf_audio_device_info *out_device);
    sf_result (*rescan)(void *context);
    sf_result (*select_output)(void *context, const char *device_id, const sf_audio_device_config *config);
    void *context;
} sf_audio_device_v1;

typedef struct sf_audio_routing_v1 {
    uint32_t struct_size;
    sf_result (*set_route_gain)(void *context, uint32_t source_index, uint32_t output_index, float linear_gain);
    sf_result (*set_output_master)(void *context, uint32_t output_index, float linear_gain);
    sf_result (*set_output_limiter)(void *context, uint32_t output_index, float ceiling_dbfs);
    void *context;
} sf_audio_routing_v1;

typedef struct sf_audio_stream_status {
    uint32_t struct_size;
    uint8_t active;
    const char *backend;
    const char *device_id;
    uint32_t graph_output;
    uint64_t callback_count;
    uint64_t xruns;
} sf_audio_stream_status;

typedef struct sf_audio_stream_v1 {
    uint32_t struct_size;
    sf_result (*activate)(void *context, const char *device_id, const sf_audio_device_config *config, uint32_t graph_output);
    sf_result (*deactivate)(void *context);
    sf_result (*status)(void *context, sf_audio_stream_status *out_status);
    void *context;
} sf_audio_stream_v1;

typedef struct sf_audio_input_stream_status {
    uint32_t struct_size;
    uint8_t active;
    const char *backend;
    const char *device_id;
    uint32_t graph_source;
    uint64_t callback_count;
    uint64_t xruns;
    uint64_t queued_frames;
    uint64_t dropped_frames;
} sf_audio_input_stream_status;

typedef struct sf_audio_input_stream_v1 {
    uint32_t struct_size;
    sf_result (*activate)(void *context, const char *device_id, const sf_audio_device_config *config, uint32_t graph_source);
    sf_result (*deactivate)(void *context);
    sf_result (*status)(void *context, sf_audio_input_stream_status *out_status);
    void *context;
} sf_audio_input_stream_v1;

typedef struct sf_audio_multi_input_v1 {
    uint32_t struct_size;
    uint32_t (*slot_count)(void *context);
    sf_result (*activate)(void *context, uint32_t slot, const char *device_id, const sf_audio_device_config *config, uint32_t graph_source);
    sf_result (*deactivate)(void *context, uint32_t slot);
    sf_result (*status)(void *context, uint32_t slot, sf_audio_input_stream_status *out_status);
    void *context;
} sf_audio_multi_input_v1;

typedef struct sf_audio_multi_output_status {
    uint32_t struct_size;
    uint8_t active;
    const char *backend;
    const char *device_id;
    uint32_t graph_output;
    uint64_t callback_count;
    uint64_t xruns;
    uint64_t queued_frames;
    uint64_t dropped_frames;
    uint64_t underrun_frames;
    uint8_t rate_measured;
    double rate_ppm;
    uint8_t drift_enabled;
    double correction_ppm;
    uint32_t source_frames;
    uint64_t compensated_blocks;
    uint64_t first_write_ns;
    uint64_t last_write_ns;
    uint64_t max_excess_gap_ns;
    uint64_t frames_written;
} sf_audio_multi_output_status;

typedef struct sf_audio_drift_config {
    uint32_t struct_size;
    uint8_t enabled;
    double max_correction_ppm;
    double queue_gain_ppm;
} sf_audio_drift_config;

typedef struct sf_audio_drift_compensation_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, uint32_t slot, const sf_audio_drift_config *config);
    void *context;
} sf_audio_drift_compensation_v1;

typedef struct sf_audio_multi_output_v1 {
    uint32_t struct_size;
    uint32_t (*slot_count)(void *context);
    sf_result (*activate)(void *context, uint32_t slot, const char *device_id, const sf_audio_device_config *config, uint32_t graph_output);
    sf_result (*deactivate)(void *context, uint32_t slot);
    sf_result (*status)(void *context, uint32_t slot, sf_audio_multi_output_status *out_status);
    void *context;
} sf_audio_multi_output_v1;

typedef struct sf_monitor_control_v1 {
    uint32_t struct_size;
    sf_result (*set_master)(void *context, const char *player_id, float percent);
    sf_result (*set_level)(void *context, const char *player_id, sf_monitor_channel channel, float percent);
    sf_result (*set_muted)(void *context, const char *player_id, uint8_t muted);
    void *context;
} sf_monitor_control_v1;

typedef struct sf_timing_profile_v1 {
    uint32_t struct_size;
    sf_result (*get_profile)(void *context, sf_timing_profile *out_profile);
    sf_result (*plan)(void *context, uint64_t now_ns, uint64_t target_ns, sf_timing_plan *out_plan);
    void *context;
} sf_timing_profile_v1;

typedef struct sf_midi_device_info {
    uint32_t struct_size;
    const char *id;
    const char *name;
    uint8_t input;
    uint8_t output;
    uint8_t connected;
} sf_midi_device_info;

typedef struct sf_midi_input_v1 {
    uint32_t struct_size;
    uint32_t (*device_count)(void *context);
    sf_result (*get_device)(void *context, uint32_t index, sf_midi_device_info *out_device);
    sf_result (*bind_player)(void *context, const char *device_id, const char *player_id);
    sf_result (*unbind_player)(void *context, const char *device_id);
    sf_result (*rescan)(void *context);
    void *context;
} sf_midi_input_v1;

typedef enum sf_midi_map_message { SF_MIDI_MAP_NOTE=0, SF_MIDI_MAP_CC=1, SF_MIDI_MAP_PITCH_BEND=2, SF_MIDI_MAP_PROGRAM=3 } sf_midi_map_message;
typedef enum sf_midi_map_behavior { SF_MIDI_MAP_ABSOLUTE=0, SF_MIDI_MAP_RELATIVE=1, SF_MIDI_MAP_TRIGGER=2, SF_MIDI_MAP_TOGGLE=3, SF_MIDI_MAP_GATE=4 } sf_midi_map_behavior;
typedef enum sf_midi_mapped_action { SF_MIDI_ACTION_AUTOMATION=0, SF_MIDI_ACTION_TRANSPORT_PLAY=1, SF_MIDI_ACTION_TRANSPORT_STOP=2, SF_MIDI_ACTION_TRANSPORT_TEMPO=3, SF_MIDI_ACTION_SAMPLE_TRIGGER=4, SF_MIDI_ACTION_LOOP_TOGGLE=5, SF_MIDI_ACTION_LOOP_CLEAR=6 } sf_midi_mapped_action;
typedef struct sf_native_midi_mapping {
    uint32_t struct_size;
    uint64_t mapping_id,device_id,target_id,resource_id;
    uint32_t parameter_id;
    uint8_t channel,number,steps_per_beat,key_sync,enabled;
    sf_midi_map_message message;
    sf_midi_map_behavior behavior;
    sf_midi_mapped_action action;
    float minimum,maximum;
} sf_native_midi_mapping;
typedef struct sf_native_midi_performance_status {
    uint32_t struct_size,bindings,queued;
    uint64_t received,matched,dropped,submitted,rejected,ignored,last_event_id;
    uint8_t physical_outputs_armed;
} sf_native_midi_performance_status;
typedef struct sf_native_midi_performance_v1 {
    uint32_t struct_size;
    sf_result (*configure_master)(void *context,double bpm,uint8_t key_root,uint16_t scale_mask);
    sf_result (*upsert)(void *context,const sf_native_midi_mapping *mapping);
    sf_result (*remove)(void *context,uint64_t mapping_id);
    sf_result (*status)(void *context,sf_native_midi_performance_status *out_status);
    void *context;
} sf_native_midi_performance_v1;

typedef struct sf_sampler_sample_descriptor {
    uint32_t struct_size;
    uint64_t sample_id;
    const float *left, *right;
    uint32_t frames, loop_begin, loop_end;
    uint16_t loop_crossfade_frames;
    uint8_t choke_group, looped;
} sf_sampler_sample_descriptor;
typedef enum sf_sampler_command_kind { SF_SAMPLER_TRIGGER=0, SF_SAMPLER_STOP_SAMPLE=1, SF_SAMPLER_STOP_ALL=2 } sf_sampler_command_kind;
typedef struct sf_sampler_command {
    uint32_t struct_size;
    sf_sampler_command_kind kind;
    uint64_t event_id, sample_id;
    float velocity;
    uint8_t note;
} sf_sampler_command;
typedef struct sf_sampler_voice_engine_status {
    uint32_t struct_size, samples, active_voices, pending_voices, queued;
    uint64_t submitted, rendered_frames, completed_voices, stolen_voices, choked_voices, rejected_commands, queue_overflows;
    uint8_t physical_outputs_armed;
} sf_sampler_voice_engine_status;
typedef struct sf_sampler_voice_engine_v1 {
    uint32_t struct_size;
    sf_result (*register_sample)(void *context, const sf_sampler_sample_descriptor *sample);
    sf_result (*submit)(void *context, const sf_sampler_command *command);
    sf_result (*status)(void *context, sf_sampler_voice_engine_status *out_status);
    void *context;
} sf_sampler_voice_engine_v1;

typedef struct sf_lighting_event {
    uint32_t struct_size;
    uint64_t event_id;
    uint64_t show_time_ns;
    uint16_t universe;
    uint16_t channel;
    uint8_t value;
} sf_lighting_event;

typedef struct sf_lighting_output_v1 {
    uint32_t struct_size;
    sf_result (*schedule)(void *context, const sf_lighting_event *event);
    sf_result (*set_universe_target)(void *context, uint16_t universe, const char *target_id);
    void *context;
} sf_lighting_output_v1;

typedef struct sf_lighting_network_status {
    uint32_t struct_size;
    uint8_t configured;
    uint8_t armed;
    const char *protocol;
    const char *target;
    uint16_t port;
    uint64_t packets_sent;
    uint64_t send_errors;
} sf_lighting_network_status;

typedef struct sf_lighting_network_v1 {
    uint32_t struct_size;
    sf_result (*configure_unicast)(void *context, const char *protocol, const char *target, uint16_t port);
    sf_result (*arm)(void *context, uint8_t armed);
    sf_result (*status)(void *context, sf_lighting_network_status *out_status);
    void *context;
} sf_lighting_network_v1;

typedef struct sf_notation_note_event {
    uint32_t struct_size;
    const char *player_id;
    uint64_t show_time_ns;
    uint8_t pitch;
    uint8_t velocity;
    uint8_t note_on;
} sf_notation_note_event;

typedef struct sf_notation_capture_v1 {
    uint32_t struct_size;
    sf_result (*capture_note)(void *context, const sf_notation_note_event *event);
    sf_result (*clear_part)(void *context, const char *player_id);
    void *context;
} sf_notation_capture_v1;

typedef struct sf_event_sink_v1 {
    uint32_t struct_size;
    sf_result (*publish)(void *context, const sf_event *event);
    void *context;
} sf_event_sink_v1;

typedef struct sf_resource_control_v1 {
    uint32_t struct_size;
    sf_result (*set_degrade_level)(void *context, uint32_t level);
    sf_result (*suspend)(void *context);
    sf_result (*resume)(void *context);
    void *context;
} sf_resource_control_v1;

typedef struct sf_state_provider_v1 {
    uint32_t struct_size;
    uint64_t (*revision)(void *context);
    sf_result (*snapshot_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_state_provider_v1;

typedef enum sf_node_role {
    SF_NODE_PRIMARY = 0,
    SF_NODE_STANDBY = 1
} sf_node_role;

typedef struct sf_authority_status {
    uint32_t struct_size;
    sf_node_role role;
    uint64_t epoch;
    uint8_t physical_authority;
} sf_authority_status;

typedef struct sf_authority_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_authority_status *out_status);
    sf_result (*set_role)(void *context, sf_node_role role, uint64_t requested_epoch);
    void *context;
} sf_authority_v1;

typedef struct sf_replication_v1 {
    uint32_t struct_size;
    sf_result (*export_envelope_json)(void *context, char *buffer, size_t *inout_size);
    sf_result (*apply_envelope_json)(void *context, const char *json, size_t size);
    void *context;
} sf_replication_v1;

typedef enum sf_failover_state {
    SF_FAILOVER_PRIMARY = 0,
    SF_FAILOVER_WAITING = 1,
    SF_FAILOVER_HEALTHY = 2,
    SF_FAILOVER_SUSPECT = 3,
    SF_FAILOVER_ELIGIBLE = 4,
    SF_FAILOVER_LEASE_LOST = 5
} sf_failover_state;

typedef struct sf_failover_status {
    uint32_t struct_size;
    sf_failover_state state;
    uint8_t safe_to_promote;
    uint64_t replica_age_ms;
    uint64_t suspect_after_ms;
    uint64_t eligible_after_ms;
} sf_failover_status;

typedef struct sf_failover_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_failover_status *out_status);
    sf_result (*promote)(void *context);
    void *context;
} sf_failover_v1;

typedef enum sf_continuity_grade {
    SF_CONTINUITY_UNMEASURED = 0,
    SF_CONTINUITY_SAMPLE_WINDOW = 1,
    SF_CONTINUITY_TIGHT = 2,
    SF_CONTINUITY_DEGRADED = 3,
    SF_CONTINUITY_DISCONTINUOUS = 4
} sf_continuity_grade;

typedef struct sf_failover_continuity_status {
    uint32_t struct_size;
    uint8_t measured;
    uint8_t transport_running;
    sf_continuity_grade grade;
    uint64_t replica_age_ms;
    double bridge_show_seconds;
    double native_show_seconds;
    double timeline_error_ms;
    uint64_t first_audio_arm_after_ms;
    double first_audio_write_after_ms;
    double max_observed_output_gap_ms;
    uint64_t first_lighting_arm_after_ms;
} sf_failover_continuity_status;

typedef struct sf_failover_continuity_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_failover_continuity_status *out_status);
    void *context;
} sf_failover_continuity_v1;

typedef enum sf_handoff_mode {
    SF_HANDOFF_STATE_WARM = 0,
    SF_HANDOFF_DETERMINISTIC_PREBUFFER_ELIGIBLE = 1,
    SF_HANDOFF_LIVE_INPUT_STATE_WARM = 2
} sf_handoff_mode;

typedef struct sf_failover_continuity_status_v2 {
    uint32_t struct_size;
    uint8_t measured;
    uint8_t transport_running;
    sf_continuity_grade grade;
    uint64_t replica_age_ms;
    double bridge_show_seconds;
    double native_show_seconds;
    double timeline_error_ms;
    uint64_t first_audio_arm_after_ms;
    double first_audio_write_after_ms;
    double max_observed_output_gap_ms;
    uint64_t first_lighting_arm_after_ms;
    uint64_t source_last_program_show_ns;
    uint64_t new_first_program_show_ns;
    double cross_node_program_gap_ms;
    double cross_node_program_overlap_ms;
    sf_continuity_grade cross_node_program_grade;
    sf_handoff_mode handoff_mode;
    uint8_t deterministic_prebuffer_eligible;
    uint8_t prebuffer_ready;
    double handoff_adjustment_ms;
} sf_failover_continuity_status_v2;

typedef struct sf_failover_continuity_v2 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_failover_continuity_status_v2 *out_status);
    void *context;
} sf_failover_continuity_v2;

typedef struct sf_handoff_readiness_status {
    uint32_t struct_size;
    sf_handoff_mode mode;
    uint64_t replica_age_ms;
    uint64_t source_program_cursor_ns;
    uint64_t handoff_target_show_ns;
    uint64_t local_show_ns;
    double local_lag_ms;
    uint32_t active_live_input_mask;
    uint8_t deterministic_prebuffer_eligible;
    uint8_t prebuffer_ready;
    uint8_t physical_outputs_auto_arm;
    uint8_t ready_for_authority_transfer;
} sf_handoff_readiness_status;

typedef struct sf_handoff_readiness_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_handoff_readiness_status *out_status);
    void *context;
} sf_handoff_readiness_v1;

typedef struct sf_handoff_policy {
    uint32_t struct_size;
    uint64_t max_replica_age_ms;
    double max_local_lag_ms;
    double required_prebuffer_ms;
    uint64_t execution_status_fresh_ms;
    uint8_t require_program_cursor;
    uint8_t require_duplicated_live_inputs;
    uint8_t require_declared_deterministic_sources;
    uint8_t allow_authority_transfer_when_program_not_ready;
} sf_handoff_policy;

typedef enum sf_handoff_recommendation {
    SF_HANDOFF_WAIT_FOR_AUTHORITY = 0,
    SF_HANDOFF_AUTHORITY_READY = 1,
    SF_HANDOFF_AUTHORITY_READY_LIVE_FEEDS = 2,
    SF_HANDOFF_START_SHADOW_PREBUFFER = 3,
    SF_HANDOFF_AUTHORITY_ONLY = 4,
    SF_HANDOFF_HOLD = 5,
    SF_HANDOFF_PROGRAM_READY = 6,
    SF_HANDOFF_PROGRAM_READY_LIVE_FEEDS = 7
} sf_handoff_recommendation;

typedef struct sf_handoff_decision_status {
    uint32_t struct_size;
    sf_handoff_mode mode;
    uint8_t authority_ready;
    uint8_t program_logic_ready;
    uint8_t execution_ready;
    uint8_t ready_for_authority_transfer;
    uint8_t ready_for_program_takeover;
    uint8_t deterministic_prebuffer_eligible;
    uint8_t shadow_render_ready;
    uint8_t prebuffer_ready;
    sf_handoff_recommendation recommendation;
    uint8_t active_live_input_mask;
    uint8_t missing_live_input_mask;
    uint32_t deterministic_source_count;
    uint32_t unready_deterministic_source_count;
    double local_lag_ms;
} sf_handoff_decision_status;

typedef struct sf_handoff_policy_v1 {
    uint32_t struct_size;
    sf_result (*get_policy)(void *context, sf_handoff_policy *out_policy);
    sf_result (*set_policy)(void *context, const sf_handoff_policy *policy);
    void *context;
} sf_handoff_policy_v1;

typedef struct sf_handoff_decision_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_handoff_decision_status *out_status);
    void *context;
} sf_handoff_decision_v1;

typedef struct sf_handoff_shadow_report {
    uint32_t struct_size;
    const char *source_id;
    uint64_t buffered_until_show_ns;
    const char *content_hash;
    uint8_t healthy;
} sf_handoff_shadow_report;

typedef struct sf_handoff_live_feed_report {
    uint32_t struct_size;
    uint32_t slot;
    const char *source_id;
    uint8_t healthy;
    double latency_ms;
} sf_handoff_live_feed_report;

typedef struct sf_handoff_execution_v1 {
    uint32_t struct_size;
    sf_result (*report_shadow)(void *context, const sf_handoff_shadow_report *report);
    sf_result (*report_live_feed)(void *context, const sf_handoff_live_feed_report *report);
    void *context;
} sf_handoff_execution_v1;

typedef enum sf_planned_handoff_state {
    SF_PLANNED_HANDOFF_IDLE = 0,
    SF_PLANNED_HANDOFF_PREPARED = 1,
    SF_PLANNED_HANDOFF_TARGET_READY = 2,
    SF_PLANNED_HANDOFF_COMMITTED = 3,
    SF_PLANNED_HANDOFF_ABORTED = 4
} sf_planned_handoff_state;

typedef struct sf_planned_handoff_status {
    uint32_t struct_size;
    uint64_t transaction_id, source_epoch, target_epoch, target_show_ns;
    uint64_t prepares, commits, aborts, conflicts;
    sf_planned_handoff_state state;
    uint8_t allow_degraded_program, program_ready, authority_committed, physical_outputs_armed;
} sf_planned_handoff_status;

typedef struct sf_planned_handoff_v1 {
    uint32_t struct_size;
    sf_result (*prepare)(void *context, uint64_t transaction_id, uint64_t source_epoch,
                         uint64_t target_epoch, uint64_t target_show_ns, uint8_t allow_degraded_program);
    sf_result (*acknowledge_target)(void *context, uint64_t transaction_id, uint8_t program_ready);
    sf_result (*commit)(void *context, uint64_t transaction_id, uint64_t observed_source_epoch,
                        uint64_t witness_epoch, uint64_t current_show_ns);
    sf_result (*abort)(void *context, uint64_t transaction_id);
    sf_result (*status)(void *context, sf_planned_handoff_status *out_status);
    void *context;
} sf_planned_handoff_v1;

typedef struct sf_replication_audio_execution_point {
    uint32_t struct_size;
    uint32_t slot;
    uint64_t last_render_show_ns;
    uint64_t last_block_end_show_ns;
    uint64_t frames_written;
} sf_replication_audio_execution_point;

typedef struct sf_replication_execution_telemetry {
    uint32_t struct_size;
    uint64_t show_time_ns;
    uint8_t transport_running;
    uint32_t audio_output_count;
    const sf_replication_audio_execution_point *audio_outputs;
    uint32_t active_audio_input_mask;
} sf_replication_execution_telemetry;

typedef struct sf_replication_telemetry_v1 {
    uint32_t struct_size;
    sf_result (*snapshot)(void *context, sf_replication_execution_telemetry *out_telemetry);
    void *context;
} sf_replication_telemetry_v1;

typedef struct sf_replication_transport_v1 {
    uint32_t struct_size;
    sf_result (*set_peer)(void *context, const char *peer_url);
    sf_result (*status_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_replication_transport_v1;

typedef struct sf_witness_lease_status {
    uint32_t struct_size;
    uint8_t configured;
    uint8_t quorum_held;
    uint32_t witness_count;
    uint32_t quorum_size;
    uint64_t authority_epoch;
    uint64_t expires_in_ms;
} sf_witness_lease_status;

typedef struct sf_witness_lease_v1 {
    uint32_t struct_size;
    sf_result (*acquire_or_renew)(void *context);
    sf_result (*status)(void *context, sf_witness_lease_status *out_status);
    void *context;
} sf_witness_lease_v1;

typedef enum sf_technology_maturity {
    SF_TECHNOLOGY_EXPERIMENTAL = 0,
    SF_TECHNOLOGY_COMMUNITY = 1,
    SF_TECHNOLOGY_CANDIDATE = 2,
    SF_TECHNOLOGY_STANDARD = 3
} sf_technology_maturity;

typedef enum sf_technology_scale_tier {
    SF_TECHNOLOGY_SCALE_EMERGING = 0,
    SF_TECHNOLOGY_SCALE_GROWING = 1,
    SF_TECHNOLOGY_SCALE_LARGE = 2,
    SF_TECHNOLOGY_SCALE_INFRASTRUCTURE = 3
} sf_technology_scale_tier;

typedef enum sf_technology_openness_grade {
    SF_TECHNOLOGY_OPEN = 0,
    SF_TECHNOLOGY_GUARDED = 1,
    SF_TECHNOLOGY_AT_RISK = 2
} sf_technology_openness_grade;

typedef struct sf_technology_extension_status {
    uint32_t struct_size;
    const char *extension_id;
    sf_technology_maturity declared_maturity;
    sf_technology_maturity highest_eligible_maturity;
    uint8_t declared_maturity_valid;
    uint8_t core_eligible;
    uint8_t grandfathered_standard;
    uint8_t scale_revalidation_needed;
    uint32_t implementation_count;
    uint32_t independent_group_count;
    uint32_t conforming_independent_group_count;
    uint32_t interoperability_pair_count;
} sf_technology_extension_status;

typedef struct sf_technology_openness_status {
    uint32_t struct_size;
    sf_technology_openness_grade openness;
    sf_technology_scale_tier scale_tier;
    uint32_t ecosystem_participants;
    uint32_t extension_count;
    uint32_t standard_independent_groups_required;
    uint32_t core_independent_groups_required;
    uint8_t preserve_unknown_capabilities;
    uint8_t experimental_without_permission;
    uint8_t no_ai_participant_valid;
} sf_technology_openness_status;

typedef struct sf_technology_registry_v1 {
    uint32_t struct_size;
    sf_result (*upsert_extension_json)(void *context, const char *extension_json);
    sf_result (*remove_extension)(void *context, const char *extension_id);
    sf_result (*get_extension_json)(void *context, const char *extension_id, char *buffer, size_t *inout_size);
    void *context;
} sf_technology_registry_v1;

typedef struct sf_technology_assessment_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_technology_openness_status *out_status);
    sf_result (*extension_status)(void *context, const char *extension_id, sf_technology_extension_status *out_status);
    sf_result (*assessment_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_technology_assessment_v1;

typedef struct sf_technology_negotiation_v1 {
    uint32_t struct_size;
    sf_result (*negotiate_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    void *context;
} sf_technology_negotiation_v1;

typedef enum sf_community_vote_choice {
    SF_COMMUNITY_VOTE_ABSTAIN = 0,
    SF_COMMUNITY_VOTE_YES = 1,
    SF_COMMUNITY_VOTE_NO = 2
} sf_community_vote_choice;

typedef struct sf_community_hype_status {
    uint32_t struct_size;
    double hype;
    double durable_fraction;
    double hype_vote_units;
    uint32_t hype_zero_day;
    uint64_t evaluated_unix_ms;
} sf_community_hype_status;

typedef struct sf_community_vote_window_status {
    uint32_t struct_size;
    const char *proposal_id;
    uint32_t proposal_version;
    const char *user_id;
    uint64_t sent_unix_ms;
    uint64_t expires_unix_ms;
    uint8_t active;
    uint8_t consumed;
} sf_community_vote_window_status;

typedef struct sf_community_tally_status {
    uint32_t struct_size;
    uint32_t raw_yes;
    uint32_t raw_no;
    uint32_t raw_abstain;
    double durable_yes;
    double durable_no;
    double durable_abstain;
    double approval_ratio;
    double hype;
    double durable_fraction;
    uint8_t binding_change_ready;
    uint8_t all_issued_windows_closed;
} sf_community_tally_status;

typedef struct sf_community_governance_v1 {
    uint32_t struct_size;
    sf_result (*proposal_json)(void *context, const char *proposal_id, char *buffer, size_t *inout_size);
    sf_result (*tally)(void *context, const char *proposal_id, uint64_t at_unix_ms, sf_community_tally_status *out_status);
    sf_result (*cast_vote_json)(void *context, const char *vote_request_json, char *buffer, size_t *inout_size);
    void *context;
} sf_community_governance_v1;

typedef struct sf_hype_maturity_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, const char *proposal_id, uint64_t at_unix_ms, sf_community_hype_status *out_status);
    void *context;
} sf_hype_maturity_v1;

typedef struct sf_vote_notification_v1 {
    uint32_t struct_size;
    sf_result (*issue_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*window_status)(void *context, const char *invitation_id, sf_community_vote_window_status *out_status);
    void *context;
} sf_vote_notification_v1;


typedef enum sf_compatibility_grade {
    SF_COMPATIBILITY_DIRECT = 0,
    SF_COMPATIBILITY_EQUIVALENT = 1,
    SF_COMPATIBILITY_ACCEPTABLE = 2,
    SF_COMPATIBILITY_DEGRADED = 3,
    SF_COMPATIBILITY_PARTIAL_PRESERVED = 4,
    SF_COMPATIBILITY_BLOCKED = 5
} sf_compatibility_grade;

typedef struct sf_compatibility_status {
    uint32_t struct_size;
    uint8_t compatible;
    sf_compatibility_grade grade;
    uint32_t selected_api_version;
    uint32_t direct_capability_count;
    uint32_t translated_capability_count;
    uint32_t preserved_unknown_local_count;
    uint32_t preserved_unknown_remote_count;
    uint32_t blocker_count;
    double capability_quality;
    uint8_t unknown_preservation;
    uint8_t offline_compatible;
} sf_compatibility_status;

typedef struct sf_show_state_compatibility_status {
    uint32_t struct_size;
    uint8_t readable;
    uint8_t forward_compatible;
    uint8_t unknown_fields_preserved;
    uint32_t incoming_api_version;
    uint32_t minimum_reader_api_version;
    uint32_t reader_api_version;
    uint32_t migration_count;
} sf_show_state_compatibility_status;

typedef struct sf_compatibility_negotiation_v1 {
    uint32_t struct_size;
    sf_result (*local_profile_json)(void *context, char *buffer, size_t *inout_size);
    sf_result (*negotiate_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    void *context;
} sf_compatibility_negotiation_v1;

typedef enum sf_profile_layer {
    SF_PROFILE_BASE = 0,
    SF_PROFILE_USER = 1,
    SF_PROFILE_ROLE = 2,
    SF_PROFILE_VENUE = 3,
    SF_PROFILE_SESSION = 4
} sf_profile_layer;

typedef enum sf_profile_value_type {
    SF_PROFILE_BOOLEAN = 0,
    SF_PROFILE_INTEGER = 1,
    SF_PROFILE_SCALAR = 2,
    SF_PROFILE_TOKEN = 3
} sf_profile_value_type;

typedef struct sf_profile_preference {
    uint32_t struct_size;
    uint64_t namespace_id;
    uint64_t key_id;
    sf_profile_layer layer;
    sf_profile_value_type type;
    uint64_t revision;
    int64_t integer_value;
    double scalar_value;
    uint64_t token_value;
} sf_profile_preference;

typedef struct sf_user_profile_status {
    uint32_t struct_size;
    uint64_t profile_id;
    uint64_t authority_epoch;
    uint64_t revision;
    uint64_t accepted_updates;
    uint64_t rejected_updates;
    uint32_t stored_preferences;
    uint8_t configured;
    uint8_t physical_outputs_armed;
} sf_user_profile_status;

typedef struct sf_user_profile_customization_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, uint64_t profile_id, uint64_t authority_epoch);
    sf_result (*set)(void *context, const sf_profile_preference *preference);
    sf_result (*resolve)(void *context, uint64_t namespace_id, uint64_t key_id, sf_profile_preference *out_preference);
    sf_result (*clear_layer)(void *context, sf_profile_layer layer, uint32_t *out_removed);
    sf_result (*status)(void *context, sf_user_profile_status *out_status);
    void *context;
} sf_user_profile_customization_v1;

typedef struct sf_handshake_capability {
    uint64_t capability_id;
    uint8_t required;
} sf_handshake_capability;

typedef struct sf_handshake_offer {
    uint32_t struct_size;
    uint64_t participant_id;
    uint32_t protocol_min;
    uint32_t protocol_max;
    uint32_t profile_schema_min;
    uint32_t profile_schema_max;
    const sf_handshake_capability *capabilities;
    uint32_t capability_count;
    uint8_t preserves_unknown;
    uint8_t offline_capable;
} sf_handshake_offer;

typedef struct sf_handshake_adapter {
    uint64_t from_capability_id;
    uint64_t to_capability_id;
    uint8_t quality;
} sf_handshake_adapter;

typedef struct sf_handshake_plan {
    uint32_t struct_size;
    uint32_t protocol_version;
    uint32_t profile_schema_version;
    uint32_t direct_capabilities;
    uint32_t translated_capabilities;
    uint32_t preserved_unknown_capabilities;
    uint32_t missing_required;
    uint8_t minimum_adapter_quality;
    uint8_t compatible;
    uint8_t unknown_preservation;
    uint8_t offline_compatible;
    uint8_t physical_outputs_armed;
} sf_handshake_plan;

typedef struct sf_interoperability_handshake_v1 {
    uint32_t struct_size;
    sf_result (*configure_local)(void *context, const sf_handshake_offer *offer);
    sf_result (*register_adapter)(void *context, const sf_handshake_adapter *adapter);
    sf_result (*negotiate)(void *context, const sf_handshake_offer *remote, sf_handshake_plan *out_plan);
    void *context;
} sf_interoperability_handshake_v1;

typedef enum sf_interop_session_state {
    SF_INTEROP_SESSION_EMPTY = 0, SF_INTEROP_SESSION_OFFERED = 1,
    SF_INTEROP_SESSION_AUTHENTICATED = 2, SF_INTEROP_SESSION_NEGOTIATED = 3,
    SF_INTEROP_SESSION_CONSENTED = 4, SF_INTEROP_SESSION_ACTIVE = 5,
    SF_INTEROP_SESSION_EXPIRED = 6
} sf_interop_session_state;

typedef struct sf_authenticated_interop_session_status {
    uint32_t struct_size;
    uint64_t session_id, transcript_hash, nonce, authority_epoch, sequence, expires_unix_ms;
    uint64_t profile_revision, registry_revision, consent_digest;
    uint32_t protocol_version, profile_schema_version;
    sf_interop_session_state state;
    uint8_t compatible, authenticated, physical_outputs_armed;
} sf_authenticated_interop_session_status;

/* Signature verification is provider-supplied. Core consumes only a verified
 * transcript decision plus replay/downgrade/session identity fences. */
typedef struct sf_authenticated_interop_session_v1 {
    uint32_t struct_size;
    sf_result (*offer)(void *context, uint64_t session_id, uint64_t transcript_hash, uint64_t nonce,
                       uint64_t authority_epoch, uint64_t sequence, uint64_t expires_unix_ms);
    sf_result (*authenticate)(void *context, uint8_t signature_verified, uint64_t now_unix_ms,
                              uint64_t expected_epoch, uint64_t minimum_sequence);
    sf_result (*negotiate)(void *context, const sf_handshake_plan *plan, uint64_t profile_revision, uint64_t registry_revision);
    sf_result (*consent)(void *context, uint8_t accepted, uint64_t projection_digest);
    sf_result (*activate)(void *context, uint64_t now_unix_ms, uint64_t authority_epoch,
                          uint64_t profile_revision, uint64_t registry_revision);
    sf_result (*status)(void *context, sf_authenticated_interop_session_status *out_status);
    void *context;
} sf_authenticated_interop_session_v1;

typedef struct sf_profile_projection_status {
    uint32_t struct_size;
    uint64_t profile_id, profile_revision, projection_digest;
    uint32_t value_count, consent_required_count;
    uint8_t safe_to_apply, physical_outputs_armed;
} sf_profile_projection_status;

typedef struct sf_profile_projection_v1 {
    uint32_t struct_size;
    sf_result (*preview_json)(void *context, const char *profile_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, sf_profile_projection_status *out_status);
    void *context;
} sf_profile_projection_v1;

typedef struct sf_semantic_capability_descriptor {
    uint32_t struct_size;
    const char *id, *semantic_version, *schema_sha256, *provenance_json;
} sf_semantic_capability_descriptor;

typedef struct sf_semantic_capability_registry_v1 {
    uint32_t struct_size;
    sf_result (*register_capability)(void *context, const sf_semantic_capability_descriptor *descriptor);
    sf_result (*register_adapter_json)(void *context, const char *adapter_json);
    sf_result (*snapshot_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_semantic_capability_registry_v1;

typedef struct sf_hardware_bench_status {
    uint32_t struct_size;
    uint64_t duration_ms, sample_count, expected_sequences, lost_sequences;
    double packet_loss_ratio, latency_p95_ns, jitter_p95_ns, absolute_clock_offset_p95_ns;
    uint8_t measured_hardware, physical_outputs_armed;
} sf_hardware_bench_status;

typedef struct sf_hardware_bench_v1 {
    uint32_t struct_size;
    sf_result (*analyze_json)(void *context, const char *samples_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, sf_hardware_bench_status *out_status);
    void *context;
} sf_hardware_bench_v1;

typedef struct sf_session_frame_header {
    uint32_t struct_size;
    uint64_t session_id_high, session_id_low, key_epoch, sequence, capability_id;
    uint32_t payload_size;
} sf_session_frame_header;

typedef struct sf_session_channel_status {
    uint32_t struct_size;
    uint64_t session_id_high, session_id_low, key_epoch, previous_key_epoch;
    uint64_t outbound_sequence, inbound_sequence, accepted_frames, rejected_frames;
    uint32_t capability_count;
    uint8_t authenticated, confidential, physical_outputs_armed;
} sf_session_channel_status;

typedef struct sf_session_channel_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, uint64_t session_id_high, uint64_t session_id_low,
                           uint64_t key_epoch, const uint64_t *capability_ids, uint32_t capability_count);
    sf_result (*authorize_inbound)(void *context, const sf_session_frame_header *header,
                                  uint8_t authentication_verified);
    sf_result (*next_outbound)(void *context, uint64_t capability_id, uint32_t payload_size,
                               sf_session_frame_header *out_header);
    sf_result (*rotate_key)(void *context, uint64_t new_key_epoch, uint32_t previous_key_grace_frames);
    sf_result (*restore_checkpoint_json)(void *context, const char *authenticated_checkpoint_json);
    sf_result (*status)(void *context, sf_session_channel_status *out_status);
    void *context;
} sf_session_channel_v1;

typedef struct sf_schema_migration_v1 {
    uint32_t struct_size;
    sf_result (*inspect_show_state_json)(void *context, const char *input_json, sf_show_state_compatibility_status *out_status);
    sf_result (*migrate_show_state_json)(void *context, const char *input_json, char *buffer, size_t *inout_size);
    void *context;
} sf_schema_migration_v1;

typedef struct sf_unknown_preservation_v1 {
    uint32_t struct_size;
    sf_result (*preservation_report_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_unknown_preservation_v1;

typedef enum sf_venue_readiness {
    SF_VENUE_READY = 0,
    SF_VENUE_NEEDS_PATCH = 1,
    SF_VENUE_BLOCKED = 2
} sf_venue_readiness;

typedef struct sf_venue_compatibility_status {
    uint32_t struct_size;
    uint8_t compatible;
    sf_compatibility_grade grade;
    sf_venue_readiness readiness;
    uint32_t requirement_count;
    uint32_t blocked_requirement_count;
    uint32_t human_assisted_requirement_count;
    uint32_t unmapped_required_count;
    uint32_t discovery_warning_count;
} sf_venue_compatibility_status;

typedef struct sf_venue_profile_v1 {
    uint32_t struct_size;
    sf_result (*current_json)(void *context, char *buffer, size_t *inout_size);
    sf_result (*inspect_json)(void *context, const char *profile_json, char *buffer, size_t *inout_size);
    void *context;
} sf_venue_profile_v1;

typedef struct sf_venue_compatibility_v1 {
    uint32_t struct_size;
    sf_result (*plan_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, const char *request_json, sf_venue_compatibility_status *out_status);
    void *context;
} sf_venue_compatibility_v1;

typedef enum sf_venue_adaptation_state {
    SF_VENUE_ADAPTATION_PROPOSED = 0,
    SF_VENUE_ADAPTATION_VALIDATED = 1,
    SF_VENUE_ADAPTATION_PENDING_COMMIT = 2,
    SF_VENUE_ADAPTATION_COMMITTED = 3,
    SF_VENUE_ADAPTATION_ROLLED_BACK = 4
} sf_venue_adaptation_state;

typedef enum sf_venue_commit_boundary {
    SF_VENUE_COMMIT_IMMEDIATE = 0,
    SF_VENUE_COMMIT_NEXT_BAR = 1,
    SF_VENUE_COMMIT_CUE = 2
} sf_venue_commit_boundary;

typedef struct sf_venue_adaptation_status {
    uint32_t struct_size;
    const char *transaction_id;
    sf_venue_adaptation_state state;
    uint8_t validation_valid;
    uint8_t reversible;
    sf_compatibility_grade grade;
    uint32_t mapping_count;
    uint32_t blocker_count;
    sf_venue_commit_boundary commit_boundary;
    double target_show_seconds;
} sf_venue_adaptation_status;

typedef struct sf_venue_patch_layer_status {
    uint32_t struct_size;
    uint32_t patch_revision;
    const char *transaction_id;
    const char *venue_id;
    uint32_t mapping_count;
    double activated_show_seconds;
} sf_venue_patch_layer_status;

typedef struct sf_venue_adaptation_v1 {
    uint32_t struct_size;
    sf_result (*propose_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*validate_json)(void *context, const char *transaction_id, char *buffer, size_t *inout_size);
    sf_result (*commit_json)(void *context, const char *transaction_id, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*rollback_json)(void *context, const char *transaction_id, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, const char *transaction_id, sf_venue_adaptation_status *out_status);
    void *context;
} sf_venue_adaptation_v1;

typedef struct sf_venue_patch_layer_v1 {
    uint32_t struct_size;
    sf_result (*active_json)(void *context, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, sf_venue_patch_layer_status *out_status);
    sf_result (*trigger_cue_json)(void *context, const char *cue_id, char *buffer, size_t *inout_size);
    void *context;
} sf_venue_patch_layer_v1;

typedef enum sf_venue_reconciliation_state {
    SF_VENUE_RECONCILIATION_NO_ACTIVE_PATCH = 0,
    SF_VENUE_RECONCILIATION_UNVERIFIED = 1,
    SF_VENUE_RECONCILIATION_REALIZED = 2,
    SF_VENUE_RECONCILIATION_DRIFT = 3,
    SF_VENUE_RECONCILIATION_BLOCKED = 4
} sf_venue_reconciliation_state;

typedef struct sf_venue_reconciliation_status {
    uint32_t struct_size;
    sf_venue_reconciliation_state state;
    uint32_t patch_revision;
    uint32_t mapping_count;
    uint32_t realized_mapping_count;
    uint32_t blocker_count;
    uint32_t warning_count;
    uint8_t safe_to_continue;
    uint8_t fully_realized;
} sf_venue_reconciliation_status;

typedef struct sf_venue_reconciliation_v1 {
    uint32_t struct_size;
    sf_result (*report_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, sf_venue_reconciliation_status *out_status);
    sf_result (*propose_repair_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    void *context;
} sf_venue_reconciliation_v1;

typedef struct sf_venue_realization_evidence_v1 {
    uint32_t struct_size;
    sf_result (*report_json)(void *context, const char *evidence_json, char *buffer, size_t *inout_size);
    sf_result (*snapshot_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_venue_realization_evidence_v1;

typedef struct sf_venue_authority_lease_status {
    uint32_t struct_size;
    const char *lease_id;
    const char *scope;
    const char *grantee;
    double remaining_seconds;
    uint8_t active;
    uint8_t revoked;
} sf_venue_authority_lease_status;

typedef struct sf_venue_authority_lease_v1 {
    uint32_t struct_size;
    sf_result (*grant_json)(void *context, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*revoke_json)(void *context, const char *lease_id, const char *request_json, char *buffer, size_t *inout_size);
    sf_result (*status)(void *context, const char *lease_id, sf_venue_authority_lease_status *out_status);
    sf_result (*snapshot_json)(void *context, char *buffer, size_t *inout_size);
    void *context;
} sf_venue_authority_lease_v1;



typedef enum sf_core_parameter_unit {
    SF_CORE_PARAMETER_NORMALIZED = 0,
    SF_CORE_PARAMETER_LINEAR = 1,
    SF_CORE_PARAMETER_PERCENT = 2,
    SF_CORE_PARAMETER_DECIBELS = 3,
    SF_CORE_PARAMETER_BOOLEAN = 4,
    SF_CORE_PARAMETER_METERS = 5,
    SF_CORE_PARAMETER_DMX = 6
} sf_core_parameter_unit;

typedef enum sf_core_parameter_timing {
    SF_CORE_PARAMETER_SAMPLE = 0,
    SF_CORE_PARAMETER_BLOCK = 1,
    SF_CORE_PARAMETER_SHOW = 2,
    SF_CORE_PARAMETER_HUMAN = 3
} sf_core_parameter_timing;

typedef enum sf_core_parameter_safety {
    SF_CORE_PARAMETER_SAFETY_NORMAL = 0,
    SF_CORE_PARAMETER_SAFETY_GUARDED = 1,
    SF_CORE_PARAMETER_SAFETY_PHYSICAL_OUTPUT = 2
} sf_core_parameter_safety;

typedef enum sf_core_parameter_endpoint_kind {
    SF_CORE_PARAMETER_ENDPOINT_GENERIC = 0,
    SF_CORE_PARAMETER_ENDPOINT_MIXER_GAIN = 1,
    SF_CORE_PARAMETER_ENDPOINT_MONITOR_GAIN = 2,
    SF_CORE_PARAMETER_ENDPOINT_SPATIAL = 3,
    SF_CORE_PARAMETER_ENDPOINT_PLUGIN = 4,
    SF_CORE_PARAMETER_ENDPOINT_LIGHTING = 5
} sf_core_parameter_endpoint_kind;

typedef struct sf_core_parameter_descriptor {
    uint32_t struct_size;
    uint64_t target_id;
    uint64_t parameter_id;
    sf_core_parameter_unit unit;
    sf_core_parameter_timing timing;
    sf_core_parameter_safety safety;
    sf_core_parameter_endpoint_kind endpoint_kind;
    float minimum;
    float maximum;
    float default_value;
    float smoothing_ms;
    uint8_t writable;
    uint8_t persistent;
    uint8_t realtime_safe;
} sf_core_parameter_descriptor;

typedef struct sf_core_parameter_runtime_status {
    uint32_t struct_size;
    uint64_t target_id;
    uint64_t parameter_id;
    float current_value;
    uint64_t applications;
    uint64_t automation_revision;
} sf_core_parameter_runtime_status;

typedef struct sf_core_parameter_registry_v1 {
    uint32_t struct_size;
    sf_result (*descriptor)(void *context, uint64_t target_id, uint64_t parameter_id, sf_core_parameter_descriptor *out_descriptor);
    sf_result (*status)(void *context, uint64_t target_id, uint64_t parameter_id, sf_core_parameter_runtime_status *out_status);
    void *context;
} sf_core_parameter_registry_v1;

typedef struct sf_cue_action_graph_status {
    uint32_t struct_size;
    uint64_t revision;
    uint32_t cue_count;
    uint32_t action_count;
} sf_cue_action_graph_status;

typedef struct sf_cue_action_graph_v1 {
    uint32_t struct_size;
    sf_result (*define_json)(void *context, const char *cue_definition_json);
    sf_result (*status)(void *context, sf_cue_action_graph_status *out_status);
    void *context;
} sf_cue_action_graph_v1;

typedef struct sf_runtime_show_status {
    uint32_t struct_size;
    uint64_t active_generation;
    uint64_t pending_generation;
    uint64_t source_revision;
    uint64_t swaps;
    uint64_t rejected;
    uint8_t pending;
} sf_runtime_show_status;

typedef struct sf_runtime_show_v1 {
    uint32_t struct_size;
    sf_result (*compile_json)(void *context, const char *validated_show_json, uint64_t source_revision, uint64_t content_hash);
    sf_result (*queue_publish)(void *context, uint64_t boundary_show_ns);
    sf_result (*status)(void *context, sf_runtime_show_status *out_status);
    void *context;
} sf_runtime_show_v1;

typedef struct sf_routing_transaction_status {
    uint32_t struct_size;
    uint64_t revision;
    uint64_t commits;
    uint64_t conflicts;
    uint32_t route_count;
} sf_routing_transaction_status;

typedef struct sf_routing_transaction_v1 {
    uint32_t struct_size;
    sf_result (*begin)(void *context, uint64_t expected_revision);
    sf_result (*set_route_json)(void *context, const char *route_json);
    sf_result (*commit)(void *context);
    void (*rollback)(void *context);
    sf_result (*status)(void *context, sf_routing_transaction_status *out_status);
    void *context;
} sf_routing_transaction_v1;

typedef enum sf_core_journal_kind {
    SF_CORE_JOURNAL_TRANSPORT = 0,
    SF_CORE_JOURNAL_CUE = 1,
    SF_CORE_JOURNAL_AUTOMATION = 2,
    SF_CORE_JOURNAL_ROUTING = 3,
    SF_CORE_JOURNAL_RUNTIME_SWAP = 4,
    SF_CORE_JOURNAL_PARAMETER = 5,
    SF_CORE_JOURNAL_MIDI = 6,
    SF_CORE_JOURNAL_LIGHTING = 7
} sf_core_journal_kind;

typedef struct sf_core_journal_record {
    uint32_t struct_size;
    uint64_t sequence;
    uint64_t show_ns;
    uint64_t event_id;
    uint64_t subject_id;
    uint64_t revision;
    uint64_t previous_hash;
    uint64_t hash;
    sf_core_journal_kind kind;
} sf_core_journal_record;

typedef struct sf_core_journal_v1 {
    uint32_t struct_size;
    sf_result (*next)(void *context, sf_core_journal_record *out_record);
    uint64_t (*pending)(void *context);
    uint64_t (*dropped)(void *context);
    void *context;
} sf_core_journal_v1;

typedef struct sf_shadow_render_plan_status {
    uint32_t struct_size;
    uint64_t target_show_ns;
    uint64_t required_until_show_ns;
    uint32_t source_count;
    uint32_t ready_source_count;
    uint32_t blocked_source_count;
    uint8_t ready;
} sf_shadow_render_plan_status;

typedef struct sf_shadow_render_planner_v1 {
    uint32_t struct_size;
    sf_result (*declare_source_json)(void *context, const char *source_json);
    sf_result (*report_json)(void *context, const char *execution_report_json);
    sf_result (*plan)(void *context, uint64_t target_show_ns, uint64_t prebuffer_ns, sf_shadow_render_plan_status *out_status);
    void *context;
} sf_shadow_render_planner_v1;

typedef struct sf_shadow_prebuffer_status {
    uint32_t struct_size;
    uint64_t source_id;
    uint64_t generation;
    uint64_t show_revision;
    uint64_t content_hash;
    uint64_t contiguous_from_show_ns;
    uint64_t buffered_until_show_ns;
    uint64_t rendered_frames;
    uint64_t rendered_blocks;
    uint64_t discontinuities;
    uint8_t healthy;
} sf_shadow_prebuffer_status;

typedef struct sf_shadow_prebuffer_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, uint64_t source_id, uint64_t generation, uint64_t show_revision, uint64_t content_hash);
    sf_result (*ingest_rendered_block)(void *context, uint64_t source_id, uint64_t generation, uint64_t show_revision, uint64_t content_hash,
                                       uint64_t start_show_ns, uint64_t end_show_ns, uint32_t frames, uint8_t healthy);
    sf_result (*status)(void *context, uint64_t source_id, sf_shadow_prebuffer_status *out_status);
    void *context;
} sf_shadow_prebuffer_v1;

typedef uint8_t (*sf_shadow_render_block_fn)(void *renderer_context, uint64_t start_show_ns,
                                             uint64_t end_show_ns, uint32_t frames);
typedef struct sf_shadow_render_executor_status {
    uint32_t struct_size;
    uint64_t source_id, generation, show_revision, content_hash;
    uint64_t next_show_ns, requested_until_show_ns, rendered_frames, rendered_blocks, failures;
    uint8_t registered, healthy;
} sf_shadow_render_executor_status;
typedef struct sf_shadow_render_executor_v1 {
    uint32_t struct_size;
    sf_result (*register_source)(void *context, uint64_t source_id, uint64_t generation,
                                 uint64_t show_revision, uint64_t content_hash, uint64_t start_show_ns,
                                 sf_shadow_render_block_fn renderer, void *renderer_context);
    sf_result (*render_until)(void *context, uint64_t source_id, uint64_t target_show_ns,
                              uint64_t block_duration_ns, uint32_t frames_per_block);
    sf_result (*status)(void *context, uint64_t source_id, sf_shadow_render_executor_status *out_status);
    void *context;
} sf_shadow_render_executor_v1;

typedef void (*sf_plugin_parameter_set_fn)(void *plugin_context, uint32_t native_parameter_id, float value);
typedef struct sf_plugin_parameter_bridge_v1 {
    uint32_t struct_size;
    sf_result (*bind)(void *context, uint64_t target_id, uint64_t parameter_id, uint32_t native_parameter_id,
                      sf_plugin_parameter_set_fn setter, void *plugin_context);
    void *context;
} sf_plugin_parameter_bridge_v1;

typedef enum sf_canonical_audio_sample_format {
    SF_CANONICAL_AUDIO_FLOAT32 = 0,
    SF_CANONICAL_AUDIO_SIGNED16 = 1,
    SF_CANONICAL_AUDIO_SIGNED24 = 2,
    SF_CANONICAL_AUDIO_SIGNED32 = 3
} sf_canonical_audio_sample_format;

typedef struct sf_canonical_audio_format {
    uint32_t struct_size;
    double sample_rate;
    uint32_t bits_per_sample;
    uint32_t channels;
    sf_canonical_audio_sample_format sample_format;
    uint8_t planar;
} sf_canonical_audio_format;

typedef struct sf_audio_rate_conversion_status {
    uint32_t struct_size;
    double source_rate;
    double destination_rate;
    uint64_t input_frames;
    uint64_t output_frames;
    uint64_t converted_blocks;
    uint64_t rejected_blocks;
} sf_audio_rate_conversion_status;

typedef struct sf_audio_rate_converter_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, const sf_canonical_audio_format *source,
                           const sf_canonical_audio_format *destination);
    sf_result (*process_planar_float32)(void *context, const float *input_left,
                                       const float *input_right, uint32_t input_frames,
                                       float *output_left, float *output_right,
                                       uint32_t output_frames);
    sf_result (*status)(void *context, sf_audio_rate_conversion_status *out_status);
    void *context;
} sf_audio_rate_converter_v1;

typedef enum sf_le_uwb_node_role {
    SF_LE_UWB_PERFORMER_INPUT = 0,
    SF_LE_UWB_MONITOR_OUTPUT = 1,
    SF_LE_UWB_STAGE_OUTPUT = 2,
    SF_LE_UWB_LIGHTING = 3,
    SF_LE_UWB_CONTROL = 4
} sf_le_uwb_node_role;

typedef enum sf_le_uwb_sync_state {
    SF_LE_UWB_UNCONFIGURED = 0,
    SF_LE_UWB_AWAITING_UWB = 1,
    SF_LE_UWB_AWAITING_LE = 2,
    SF_LE_UWB_LOCKED = 3,
    SF_LE_UWB_HOLDOVER = 4,
    SF_LE_UWB_BLOCKED = 5
} sf_le_uwb_sync_state;

typedef struct sf_le_uwb_hub_policy {
    uint32_t struct_size;
    uint64_t target_presentation_lead_ns;
    uint64_t max_end_to_end_ns;
    uint64_t fresh_observation_ns;
    uint64_t holdover_ns;
    uint64_t max_clock_uncertainty_ns;
    uint64_t max_jitter_ns;
    double max_range_uncertainty_mm;
    double max_drift_ppm;
    uint8_t require_authenticated_observations;
} sf_le_uwb_hub_policy;

typedef struct sf_le_uwb_node_descriptor {
    uint32_t struct_size;
    uint64_t node_id;
    uint32_t le_stream_id;
    sf_le_uwb_node_role role;
    uint64_t presentation_delay_ns;
    uint8_t required;
} sf_le_uwb_node_descriptor;

typedef struct sf_le_uwb_node_status {
    uint32_t struct_size;
    sf_le_uwb_node_descriptor descriptor;
    sf_le_uwb_sync_state state;
    uint64_t authority_epoch;
    uint64_t uwb_sequence;
    uint64_t le_sequence;
    uint64_t le_event_counter;
    uint64_t last_uwb_hub_ns;
    uint64_t last_le_hub_ns;
    uint64_t transport_latency_ns;
    uint64_t jitter_ns;
    uint64_t clock_uncertainty_ns;
    double distance_mm;
    double range_uncertainty_mm;
    double drift_ppm;
    int64_t clock_offset_ns;
    uint64_t rejected_observations;
    uint8_t authenticated;
} sf_le_uwb_node_status;

typedef struct sf_le_uwb_sync_plan {
    uint32_t struct_size;
    uint64_t generation;
    uint64_t authority_epoch;
    uint64_t target_hub_ns;
    uint64_t target_show_ns;
    uint64_t presentation_lead_ns;
    uint32_t configured_nodes;
    uint32_t required_nodes;
    uint32_t ready_nodes;
    uint32_t holdover_nodes;
    uint32_t blocked_nodes;
    uint8_t ready;
    uint8_t physical_outputs_armed;
} sf_le_uwb_sync_plan;

typedef struct sf_le_uwb_hub_v1 {
    uint32_t struct_size;
    sf_result (*configure)(void *context, uint64_t authority_epoch, const sf_le_uwb_hub_policy *policy);
    sf_result (*register_node)(void *context, const sf_le_uwb_node_descriptor *descriptor);
    sf_result (*observe_uwb)(void *context, uint64_t node_id, uint64_t sequence, uint64_t authority_epoch,
                             uint64_t hub_time_ns, uint64_t node_time_ns, double distance_mm,
                             double range_uncertainty_mm, uint64_t clock_uncertainty_ns, uint8_t authenticated);
    sf_result (*observe_le)(void *context, uint64_t node_id, uint64_t sequence, uint64_t authority_epoch,
                            uint64_t event_counter, uint64_t hub_time_ns, uint64_t transport_latency_ns,
                            uint64_t jitter_ns, uint8_t authenticated);
    sf_result (*plan)(void *context, uint64_t hub_now_ns, uint64_t show_now_ns,
                      uint64_t authority_epoch, sf_le_uwb_sync_plan *out_plan);
    sf_result (*target_for)(void *context, uint64_t node_id, uint64_t plan_generation,
                            uint64_t *out_node_time_ns);
    sf_result (*status)(void *context, uint64_t node_id, sf_le_uwb_node_status *out_status);
    void *context;
} sf_le_uwb_hub_v1;

/* Normalized hardware evidence boundary. The UWB adapter may speak FiRa UCI
 * or a vendor protocol internally; Core consumes this stable, fenced record
 * and does not claim wire compatibility with either. */
typedef struct sf_uwb_hardware_observation {
    uint32_t struct_size;
    uint64_t node_id;
    uint64_t sequence;
    uint64_t authority_epoch;
    uint64_t hub_time_ns;
    uint64_t node_time_ns;
    double distance_mm;
    double range_uncertainty_mm;
    uint64_t clock_uncertainty_ns;
    uint8_t authenticated;
} sf_uwb_hardware_observation;

typedef struct sf_uwb_hardware_status {
    uint32_t struct_size;
    uint64_t bytes_read;
    uint64_t valid_frames;
    uint64_t invalid_frames;
    uint64_t resync_bytes;
    uint64_t io_errors;
    int32_t last_error;
    uint8_t open;
    uint8_t faulted;
    uint8_t physical_outputs_armed;
} sf_uwb_hardware_status;

typedef struct sf_uwb_hardware_bridge_v1 {
    uint32_t struct_size;
    sf_result (*open_device)(void *context, const char *path, uint32_t baud);
    sf_result (*close_device)(void *context);
    sf_result (*poll)(void *context, uint32_t budget, uint32_t *out_observations);
    sf_result (*status)(void *context, sf_uwb_hardware_status *out_status);
    void *context;
} sf_uwb_hardware_bridge_v1;

typedef struct sf_le_iso_hardware_status {
    uint32_t struct_size;
    uint64_t node_id;
    uint64_t received_sdus;
    uint64_t transmitted_sdus;
    uint64_t received_bytes;
    uint64_t transmitted_bytes;
    uint64_t would_block;
    uint64_t io_errors;
    int32_t last_error;
    uint8_t kernel_iso_supported;
    uint8_t open;
    uint8_t connecting;
    uint8_t connected;
    uint8_t physical_outputs_armed;
} sf_le_iso_hardware_status;

typedef struct sf_le_iso_hardware_v1 {
    uint32_t struct_size;
    sf_result (*open_unicast)(void *context, uint64_t node_id, const char *local_address,
                              const char *remote_address, uint8_t random_address);
    sf_result (*close_node)(void *context, uint64_t node_id);
    sf_result (*poll)(void *context, uint32_t budget, uint32_t *out_observations);
    sf_result (*status)(void *context, uint64_t node_id, sf_le_iso_hardware_status *out_status);
    void *context;
} sf_le_iso_hardware_v1;

typedef enum sf_audio_effect_format { SF_AUDIO_EFFECT_BUILTIN=0, SF_AUDIO_EFFECT_VST3=1, SF_AUDIO_EFFECT_CLAP=2, SF_AUDIO_EFFECT_LV2=3, SF_AUDIO_EFFECT_AUDIO_UNIT=4 } sf_audio_effect_format;
typedef uint8_t (*sf_audio_effect_activate_fn)(void*,double,uint32_t,uint32_t);
typedef uint8_t (*sf_audio_effect_process_fn)(void*,float *const*,uint32_t,uint32_t,uint64_t);
typedef void (*sf_audio_effect_deactivate_fn)(void*);
typedef struct sf_audio_effect_descriptor { uint32_t struct_size; uint64_t effect_id; sf_audio_effect_format format; uint32_t channels,latency_frames; uint8_t realtime_safe; } sf_audio_effect_descriptor;
typedef struct sf_audio_effect_adapter { uint32_t struct_size; void *effect_context; sf_audio_effect_activate_fn activate; sf_audio_effect_process_fn process; sf_audio_effect_deactivate_fn deactivate; } sf_audio_effect_adapter;
typedef struct sf_audio_effect_chain_status { uint32_t struct_size; uint32_t registered,active,bypassed,total_latency_frames; uint64_t processed_blocks,failures; } sf_audio_effect_chain_status;
typedef struct sf_audio_effect_chain_v1 {
    uint32_t struct_size;
    sf_result (*register_effect)(void*,const sf_audio_effect_descriptor*,const sf_audio_effect_adapter*);
    sf_result (*activate_all)(void*,double,uint32_t,uint32_t);
    sf_result (*set_bypass)(void*,uint64_t,uint8_t);
    sf_result (*status)(void*,sf_audio_effect_chain_status*);
    void (*deactivate_all)(void*);
    void *context;
} sf_audio_effect_chain_v1;

/* Control-thread punch/loop capture contract. Frame positions are expressed
 * in the capture adapter's frame domain; adapters must declare/convert their
 * rate before presenting the values as canonical 192 kHz Show Time. */
typedef struct sf_daw_punch_capture_plan {
    uint32_t struct_size;
    uint64_t generation;
    uint64_t punch_in_frame;
    uint64_t punch_out_frame;
    uint64_t pre_roll_frames;
    uint64_t latency_compensation_frames;
    uint64_t loop_start_frame;
    uint64_t loop_end_frame;
    uint32_t maximum_passes;
    uint8_t has_punch_out;
    uint8_t loop_enabled;
} sf_daw_punch_capture_plan;

typedef struct sf_daw_punch_capture_status {
    uint32_t struct_size;
    uint64_t generation;
    uint64_t selected_frames;
    uint64_t discarded_frames;
    uint64_t stale_blocks;
    uint32_t completed_passes;
    uint8_t punch_complete;
    uint8_t physical_input_armed;
    uint8_t physical_outputs_armed;
} sf_daw_punch_capture_status;

typedef struct sf_daw_punch_capture_v1 {
    uint32_t struct_size;
    sf_result (*prepare)(void *context, const sf_daw_punch_capture_plan *plan);
    sf_result (*status)(void *context, sf_daw_punch_capture_status *out_status);
    sf_result (*abort)(void *context);
    void *context;
} sf_daw_punch_capture_v1;

typedef struct sf_stage_launcher_status {
    uint32_t struct_size;
    uint64_t revision;
    uint64_t feedback_sequence;
    double transport_seconds;
    double bpm;
    uint32_t ready_pads;
    uint8_t transport_running;
    uint8_t physical_input_armed;
    uint8_t physical_outputs_armed;
} sf_stage_launcher_status;

typedef struct sf_stage_launcher_v1 {
    uint32_t struct_size;
    sf_result (*status)(void *context, sf_stage_launcher_status *out_status);
    sf_result (*dispatch)(void *context, const char *action_id, const char *action,
                          const char *resource_id, double value);
    void *context;
} sf_stage_launcher_v1;

typedef struct sf_streaming_sample_bank_status {
    uint32_t struct_size;
    uint64_t generation;
    uint64_t submitted_blocks;
    uint64_t underrun_blocks;
    uint32_t banks;
    uint32_t entries;
    uint32_t block_frames;
    uint8_t disk_io_in_audio_callback;
    uint8_t physical_outputs_armed;
} sf_streaming_sample_bank_status;

typedef struct sf_streaming_sample_bank_v1 {
    uint32_t struct_size;
    sf_result (*replace_bank)(void *context, const char *bank_id, uint64_t generation);
    sf_result (*trigger)(void *context, const char *action_id, const char *bank_id, uint32_t slot);
    sf_result (*status)(void *context, sf_streaming_sample_bank_status *out_status);
    void *context;
} sf_streaming_sample_bank_v1;
typedef struct sf_plugin_delay_graph_status {uint32_t struct_size;uint64_t active_generation,prepared_generation,activation_show_ns,swaps,rejected;uint32_t paths,maximum_latency_frames;uint8_t prepared,physical_outputs_armed;} sf_plugin_delay_graph_status;
typedef struct sf_plugin_delay_graph_v1 {uint32_t struct_size;sf_result(*prepare)(void*,uint64_t,uint64_t,const uint32_t*,uint32_t);sf_result(*activate)(void*,uint64_t);sf_result(*status)(void*,sf_plugin_delay_graph_status*);void*context;} sf_plugin_delay_graph_v1;
typedef struct sf_realtime_audit_status {uint32_t struct_size;uint64_t callbacks,deadline_misses,consecutive_misses,max_duration_ns,nonfinite_samples,queue_pressure_events,optional_shed_blocks,recovery_transitions;uint32_t overload_level;uint8_t physical_outputs_armed;uint64_t allocation_attempts,allocated_bytes,lock_attempts;uint8_t qualification_enabled;} sf_realtime_audit_status;
typedef struct sf_realtime_audit_v1 {uint32_t struct_size;sf_result(*status)(void*,uint32_t,sf_realtime_audit_status*);void*context;} sf_realtime_audit_v1;
typedef struct sf_ingress_audit_status {uint32_t struct_size;uint64_t callbacks,bytes,messages,queue_drops,injected_messages,max_duration_ns;uint32_t domain;uint8_t physical_outputs_armed;} sf_ingress_audit_status;
typedef struct sf_capture_ingress_audit_status {uint32_t struct_size;uint64_t callbacks,frames,record_blocks,queue_rejections,nonfinite_samples,max_duration_ns;uint32_t slot;uint8_t physical_outputs_armed;} sf_capture_ingress_audit_status;
typedef struct sf_lighting_ingress_audit_status {uint32_t struct_size;uint64_t accepted,queue_rejections,drained,drain_calls,max_duration_ns;uint8_t physical_outputs_armed;} sf_lighting_ingress_audit_status;
typedef struct sf_ingress_audit_v1 {uint32_t struct_size;sf_result(*status)(void*,uint32_t,sf_ingress_audit_status*);sf_result(*capture_status)(void*,uint32_t,sf_capture_ingress_audit_status*);sf_result(*lighting_status)(void*,sf_lighting_ingress_audit_status*);void*context;} sf_ingress_audit_v1;

typedef struct sf_host_api {
    uint32_t struct_size;
    uint32_t api_version;
    sf_time (*get_time)(void *host_context);
    void (*log_message)(void *host_context, int level, const char *message);
    const void *(*get_extension)(void *host_context, const char *extension_id, uint32_t min_version);
    void *host_context;
} sf_host_api;

typedef struct sf_module sf_module;

typedef const sf_module_info *(*sf_get_module_info_fn)(void);
typedef sf_result (*sf_create_module_fn)(const sf_host_api *, sf_module **);
typedef void (*sf_destroy_module_fn)(sf_module *);
typedef const void *(*sf_get_module_extension_fn)(sf_module *, const char *extension_id, uint32_t min_version);

#ifdef __cplusplus
}
#endif

#endif
