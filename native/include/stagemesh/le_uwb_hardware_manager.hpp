#pragma once

#include "stagemesh/le_iso_hardware.hpp"
#include "stagemesh/le_uwb_hub.hpp"
#include "stagemesh/uwb_hardware_bridge.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace stagemesh {

struct LeUwbHardwareManagerStatus {
    std::uint32_t configured_le_slots{0};
    std::uint32_t connected_le_slots{0};
    std::uint64_t polls{0};
    std::uint64_t accepted_uwb_frames{0};
    std::uint64_t rejected_uwb_frames{0};
    std::uint64_t accepted_le_frames{0};
    std::uint64_t rejected_le_frames{0};
    bool uwb_open{false};
    bool kernel_iso_supported{false};
    bool physical_outputs_armed{false};
};

// Control-thread hardware pump. A single UWB bridge may multiplex all node
// observations. Each node gets a dedicated LE ISO timing sidecar socket; audio
// SDUs remain in the audio adapter so timing inspection never touches the
// real-time mix callback.
template <std::size_t MaxNodes = 64>
class LeUwbHardwareManager final {
public:
    explicit LeUwbHardwareManager(LeUwbHub<MaxNodes>& hub) noexcept
        : hub_(hub), kernel_iso_supported_(LeIsoHardwareSocket::probe_kernel_support()) {}

    [[nodiscard]] bool open_uwb(const char* path,std::uint32_t baud) noexcept {return uwb_.open_device(path,baud);}
    [[nodiscard]] bool adopt_uwb_fd_for_test(int fd) noexcept {return uwb_.adopt_fd_for_test(fd);}

    [[nodiscard]] bool connect_le(std::uint64_t node_id,const char* local_address,const char* remote_address,bool random_address) noexcept {
        auto* slot=ensure_slot(node_id);return slot&&slot->socket.open_unicast(local_address,remote_address,random_address);
    }
    [[nodiscard]] bool adopt_le_fd_for_test(std::uint64_t node_id,int fd) noexcept {
        auto* slot=ensure_slot(node_id);return slot&&slot->socket.adopt_fd_for_test(fd);
    }

    void close_uwb() noexcept {uwb_.close();}
    void close_le(std::uint64_t node_id) noexcept {if(auto* slot=find_slot(node_id))slot->socket.close();}
    void close_all() noexcept {uwb_.close();for(auto& slot:slots_)slot.socket.close();}

    [[nodiscard]] std::size_t poll(std::size_t budget=64) noexcept {
        ++polls_;std::size_t handled=0;UwbHardwareObservation uwb_observation{};
        while(handled<budget&&uwb_.try_read(uwb_observation)){
            if(hub_.observe_uwb(uwb_observation.node_id,uwb_observation.sequence,uwb_observation.authority_epoch,
                                uwb_observation.hub_time_ns,uwb_observation.node_time_ns,uwb_observation.distance_mm,
                                uwb_observation.range_uncertainty_mm,uwb_observation.clock_uncertainty_ns,
                                uwb_observation.authenticated))++accepted_uwb_;else ++rejected_uwb_;
            ++handled;
        }
        for(auto& slot:slots_){
            if(handled>=budget||!slot.used)break;
            std::array<std::uint8_t,le_iso_timing_frame_size> payload{};std::size_t received=0;std::uint64_t received_ns=0;
            if(!slot.socket.receive(payload.data(),payload.size(),received,received_ns))continue;
            ++handled;LeIsoTimingObservation observation{};
            if(received!=payload.size()||!decode_le_iso_timing_frame(payload.data(),received,observation)||observation.node_id!=slot.node_id){++rejected_le_;continue;}
            LeUwbNodeStatus node{};if(!hub_.status(slot.node_id,node)){++rejected_le_;continue;}
            const auto transmitted_hub_ns=subtract_signed(observation.node_transmit_ns,node.clock_offset_ns);
            if(received_ns==0||transmitted_hub_ns>received_ns){++rejected_le_;continue;}
            const auto latency=received_ns-transmitted_hub_ns;
            const auto jitter=slot.has_latency?(latency>slot.previous_latency?latency-slot.previous_latency:slot.previous_latency-latency):0ULL;
            slot.previous_latency=latency;slot.has_latency=true;
            if(hub_.observe_le(observation.node_id,observation.sequence,observation.authority_epoch,observation.event_counter,
                               received_ns,latency,jitter,observation.authenticated))++accepted_le_;else ++rejected_le_;
        }
        return handled;
    }

    [[nodiscard]] LeUwbHardwareManagerStatus status() const noexcept {
        LeUwbHardwareManagerStatus result{};result.polls=polls_;result.accepted_uwb_frames=accepted_uwb_;
        result.rejected_uwb_frames=rejected_uwb_;result.accepted_le_frames=accepted_le_;result.rejected_le_frames=rejected_le_;
        result.uwb_open=uwb_.status().open;result.physical_outputs_armed=false;
        result.kernel_iso_supported=kernel_iso_supported_;
        for(const auto& slot:slots_)if(slot.used){++result.configured_le_slots;if(slot.socket.status().connected)++result.connected_le_slots;}
        return result;
    }
    [[nodiscard]] UwbHardwareBridgeStatus uwb_status() const noexcept {return uwb_.status();}
    [[nodiscard]] bool le_status(std::uint64_t node_id,LeIsoHardwareStatus& out) const noexcept {
        const auto* slot=find_slot_const(node_id);if(!slot)return false;out=slot->socket.status();return true;
    }

private:
    struct LeSlot {
        bool used{false};
        std::uint64_t node_id{0};
        LeIsoHardwareSocket socket{};
        std::uint64_t previous_latency{0};
        bool has_latency{false};
    };
    [[nodiscard]] LeSlot* find_slot(std::uint64_t node_id) noexcept {for(auto& slot:slots_)if(slot.used&&slot.node_id==node_id)return &slot;return nullptr;}
    [[nodiscard]] const LeSlot* find_slot_const(std::uint64_t node_id) const noexcept {for(const auto& slot:slots_)if(slot.used&&slot.node_id==node_id)return &slot;return nullptr;}
    [[nodiscard]] LeSlot* ensure_slot(std::uint64_t node_id) noexcept {
        if(node_id==0)return nullptr;
        if(auto* existing=find_slot(node_id))return existing;
        for(auto& slot:slots_){
            if(!slot.used){slot.used=true;slot.node_id=node_id;return &slot;}
        }
        return nullptr;
    }
    [[nodiscard]] static std::uint64_t subtract_signed(std::uint64_t value,std::int64_t offset) noexcept {
        if(offset>=0){const auto amount=static_cast<std::uint64_t>(offset);return amount>value?0:value-amount;}
        const auto amount=static_cast<std::uint64_t>(-(offset+1))+1;
        return amount>std::numeric_limits<std::uint64_t>::max()-value?std::numeric_limits<std::uint64_t>::max():value+amount;
    }

    LeUwbHub<MaxNodes>& hub_;
    UwbHardwareBridge uwb_{};
    std::array<LeSlot,MaxNodes> slots_{};
    std::uint64_t polls_{0},accepted_uwb_{0},rejected_uwb_{0},accepted_le_{0},rejected_le_{0};
    bool kernel_iso_supported_{false};
};

} // namespace stagemesh
