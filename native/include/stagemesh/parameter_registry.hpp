#pragma once

#include "stagemesh/automation_state.hpp"

#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace stagemesh {

enum class CoreParameterUnit : std::uint8_t { normalized=0, linear=1, percent=2, decibels=3, boolean_value=4, meters=5, dmx=6 };
enum class CoreParameterTiming : std::uint8_t { sample=0, block=1, show=2, human=3 };
enum class CoreParameterSafety : std::uint8_t { normal=0, guarded=1, physical_output=2 };
enum class CoreParameterEndpointKind : std::uint8_t { generic=0, mixer_gain=1, monitor_gain=2, spatial=3, plugin=4, lighting=5 };

struct CoreParameterDescriptor {
    std::uint64_t target_id{0};
    std::uint64_t parameter_id{0};
    CoreParameterUnit unit{CoreParameterUnit::normalized};
    CoreParameterTiming timing{CoreParameterTiming::show};
    CoreParameterSafety safety{CoreParameterSafety::normal};
    CoreParameterEndpointKind endpoint_kind{CoreParameterEndpointKind::generic};
    float minimum{0.0F};
    float maximum{1.0F};
    float default_value{0.0F};
    float smoothing_ms{0.0F};
    bool writable{true};
    bool persistent{true};
    bool realtime_safe{false};
};

using CoreParameterApplyFn = void (*)(void*, float) noexcept;

struct CoreParameterStatus {
    bool registered{false};
    CoreParameterDescriptor descriptor{};
    float last_applied{0.0F};
    std::uint64_t applications{0};
    std::uint64_t automation_revision{0};
};

struct CoreParameterRegistryMetrics {
    std::uint64_t registered{0};
    std::uint64_t applications{0};
    std::uint64_t rejected{0};
    std::uint64_t clamps{0};
};

template <std::size_t Capacity = 256>
class CoreParameterRegistry final {
public:
    [[nodiscard]] bool register_endpoint(const CoreParameterDescriptor& descriptor, CoreParameterApplyFn apply, void* context) noexcept {
        if (descriptor.target_id == 0 || descriptor.parameter_id == 0 || !apply || !std::isfinite(descriptor.minimum) ||
            !std::isfinite(descriptor.maximum) || descriptor.maximum < descriptor.minimum ||
            !std::isfinite(descriptor.default_value)) {
            rejected_.fetch_add(1, std::memory_order_relaxed); return false;
        }
        if (find(descriptor.target_id, descriptor.parameter_id)) {
            rejected_.fetch_add(1, std::memory_order_relaxed); return false;
        }
        for (auto& entry : entries_) {
            if (entry.registered.load(std::memory_order_acquire)) continue;
            entry.descriptor = descriptor;
            entry.apply = apply;
            entry.context = context;
            const float initial = clamp(entry, descriptor.default_value);
            entry.last_applied.store(initial, std::memory_order_relaxed);
            entry.applications.store(1, std::memory_order_relaxed);
            entry.automation_revision.store(0, std::memory_order_relaxed);
            apply(context, initial);
            entry.registered.store(true, std::memory_order_release);
            registered_.fetch_add(1, std::memory_order_relaxed);
            applications_.fetch_add(1, std::memory_order_relaxed);
            return true;
        }
        rejected_.fetch_add(1, std::memory_order_relaxed); return false;
    }

    template <std::size_t AutomationCapacity>
    void apply_realtime(const CoreAutomationState<AutomationCapacity>& automation, std::uint64_t show_ns) noexcept {
        apply_class(automation, show_ns, true);
    }

    template <std::size_t AutomationCapacity>
    void apply_control(const CoreAutomationState<AutomationCapacity>& automation, std::uint64_t show_ns) noexcept {
        apply_class(automation, show_ns, false);
    }

    [[nodiscard]] bool status(std::uint64_t target, std::uint64_t parameter, CoreParameterStatus& out) const noexcept {
        const auto* entry = find_const(target, parameter);
        if (!entry) return false;
        out.registered = true;
        out.descriptor = entry->descriptor;
        out.last_applied = entry->last_applied.load(std::memory_order_acquire);
        out.applications = entry->applications.load(std::memory_order_relaxed);
        out.automation_revision = entry->automation_revision.load(std::memory_order_acquire);
        return true;
    }

    [[nodiscard]] CoreParameterRegistryMetrics metrics() const noexcept {
        return {registered_.load(std::memory_order_acquire), applications_.load(std::memory_order_relaxed),
                rejected_.load(std::memory_order_relaxed), clamps_.load(std::memory_order_relaxed)};
    }

private:
    struct Entry {
        std::atomic<bool> registered{false};
        CoreParameterDescriptor descriptor{};
        CoreParameterApplyFn apply{nullptr};
        void* context{nullptr};
        std::atomic<float> last_applied{0.0F};
        std::atomic<std::uint64_t> applications{0};
        std::atomic<std::uint64_t> automation_revision{0};
    };

    [[nodiscard]] float clamp(const Entry& entry, float value) noexcept {
        const float result = value < entry.descriptor.minimum ? entry.descriptor.minimum :
                             value > entry.descriptor.maximum ? entry.descriptor.maximum : value;
        if (result != value) clamps_.fetch_add(1, std::memory_order_relaxed);
        return result;
    }

    template <std::size_t AutomationCapacity>
    void apply_class(const CoreAutomationState<AutomationCapacity>& automation, std::uint64_t show_ns, bool realtime) noexcept {
        for (auto& entry : entries_) {
            if (!entry.registered.load(std::memory_order_acquire) || entry.descriptor.realtime_safe != realtime) continue;
            AutomationParameterSnapshot state{};
            if (!automation.snapshot(entry.descriptor.target_id, entry.descriptor.parameter_id, show_ns, state)) continue;
            const float value = clamp(entry, state.current_value);
            const float previous = entry.last_applied.load(std::memory_order_relaxed);
            const auto previous_revision = entry.automation_revision.load(std::memory_order_relaxed);
            if (previous_revision == state.revision && !state.ramping && std::fabs(previous - value) <= 1.0e-7F) continue;
            entry.apply(entry.context, value);
            entry.last_applied.store(value, std::memory_order_release);
            entry.automation_revision.store(state.revision, std::memory_order_release);
            entry.applications.fetch_add(1, std::memory_order_relaxed);
            applications_.fetch_add(1, std::memory_order_relaxed);
        }
    }

    [[nodiscard]] Entry* find(std::uint64_t target, std::uint64_t parameter) noexcept {
        for (auto& entry : entries_) if (entry.registered.load(std::memory_order_acquire) &&
            entry.descriptor.target_id == target && entry.descriptor.parameter_id == parameter) return &entry;
        return nullptr;
    }
    [[nodiscard]] const Entry* find_const(std::uint64_t target, std::uint64_t parameter) const noexcept {
        for (const auto& entry : entries_) if (entry.registered.load(std::memory_order_acquire) &&
            entry.descriptor.target_id == target && entry.descriptor.parameter_id == parameter) return &entry;
        return nullptr;
    }

    std::array<Entry, Capacity> entries_{};
    std::atomic<std::uint64_t> registered_{0}, applications_{0}, rejected_{0}, clamps_{0};
};

// Provider-neutral plugin seam. A CLAP/VST/LV2 adapter can expose its native
// setter through this callback without making the Core parameter model plugin-format-specific.
using CorePluginParameterSetFn = void (*)(void*, std::uint32_t, float) noexcept;
struct CorePluginParameterBinding { void* plugin{nullptr}; std::uint32_t native_parameter{0}; CorePluginParameterSetFn set{nullptr}; };
inline void apply_plugin_parameter(void* raw, float value) noexcept {
    auto* binding = static_cast<CorePluginParameterBinding*>(raw);
    if (binding && binding->set) binding->set(binding->plugin, binding->native_parameter, value);
}

} // namespace stagemesh
