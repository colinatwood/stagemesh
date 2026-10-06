#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct SessionFrameHeader {std::uint64_t session_id_high{0},session_id_low{0},key_epoch{0},sequence{0},capability_id{0};std::uint32_t payload_size{0};};
struct SessionChannelStatus {std::uint64_t session_id_high{0},session_id_low{0},key_epoch{0},previous_key_epoch{0},outbound_sequence{0},inbound_sequence{0},accepted{0},rejected{0};std::uint32_t capability_count{0};bool authenticated{false},confidential{false},physical_outputs_armed{false};};

template <std::size_t MaxCapabilities=64>
class SessionChannelGuard final {
public:
    [[nodiscard]] bool configure(std::uint64_t high,std::uint64_t low,std::uint64_t key_epoch,const std::uint64_t* capabilities,std::size_t count) noexcept {
        if((high==0&&low==0)||key_epoch==0||!capabilities||count==0||count>MaxCapabilities)return false;
        status_={};status_.session_id_high=high;status_.session_id_low=low;status_.key_epoch=key_epoch;status_.capability_count=static_cast<std::uint32_t>(count);status_.authenticated=true;
        for(std::size_t i=0;i<count;++i){if(capabilities[i]==0)return false;capabilities_[i]=capabilities[i];}return true;
    }
    [[nodiscard]] bool authorize_inbound(const SessionFrameHeader& frame,bool authentication_verified) noexcept {
        if(!status_.authenticated||!authentication_verified||frame.session_id_high!=status_.session_id_high||frame.session_id_low!=status_.session_id_low||frame.payload_size>4096||!allowed(frame.capability_id)||frame.sequence<=status_.inbound_sequence){++status_.rejected;return false;}
        const bool epoch_ok=frame.key_epoch==status_.key_epoch||(frame.key_epoch==status_.previous_key_epoch&&frame.sequence<=previous_accept_until_);
        if(!epoch_ok){++status_.rejected;return false;}status_.inbound_sequence=frame.sequence;++status_.accepted;return true;
    }
    [[nodiscard]] bool next_outbound(std::uint64_t capability_id,std::uint32_t payload_size,SessionFrameHeader& out) noexcept {
        if(!status_.authenticated||!allowed(capability_id)||payload_size>4096){++status_.rejected;return false;}
        out={status_.session_id_high,status_.session_id_low,status_.key_epoch,++status_.outbound_sequence,capability_id,payload_size};return true;
    }
    [[nodiscard]] bool rotate(std::uint64_t new_epoch,std::uint32_t grace_frames=32) noexcept {if(new_epoch<=status_.key_epoch)return false;status_.previous_key_epoch=status_.key_epoch;status_.key_epoch=new_epoch;previous_accept_until_=status_.inbound_sequence+(grace_frames>1024?1024:grace_frames);return true;}
    [[nodiscard]] bool restore_sequences(std::uint64_t key_epoch,std::uint64_t outbound,std::uint64_t inbound,bool checkpoint_authenticated) noexcept {if(!checkpoint_authenticated||key_epoch<status_.key_epoch||outbound<status_.outbound_sequence||inbound<status_.inbound_sequence)return false;status_.key_epoch=key_epoch;status_.outbound_sequence=outbound;status_.inbound_sequence=inbound;return true;}
    [[nodiscard]] SessionChannelStatus status() const noexcept{return status_;}
private:
    [[nodiscard]] bool allowed(std::uint64_t id) const noexcept {for(std::size_t i=0;i<status_.capability_count;++i)if(capabilities_[i]==id)return true;return false;}
    std::array<std::uint64_t,MaxCapabilities> capabilities_{};SessionChannelStatus status_{};std::uint64_t previous_accept_until_{0};
};

} // namespace stagemesh
