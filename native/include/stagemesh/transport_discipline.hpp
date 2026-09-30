#pragma once

#include "stagemesh/clock_discipline.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace stagemesh {

struct TransportDisciplineStatus {
    ClockDisciplineState state{ClockDisciplineState::free_running};
    std::uint64_t source_id{0},authority_epoch{0},last_sequence{0},observations{0},rejected{0},holdover_entries{0};
    std::int64_t phase_error_ns{0};
    double drift_ppm{0},correction_ppm{0},applied_rate{1};
    std::uint64_t source_age_ns{0};
    bool configured{false},physical_outputs_armed{false};
};

// Single-control-owner policy that converts paired source-clock plus source-
// Show-Time observations into a bounded rate command. It never seeks transport.
class TransportDiscipline final {
public:
    [[nodiscard]] bool configure(std::uint64_t source_id,std::uint64_t authority_epoch,std::uint64_t holdover_ns,
                                 double max_slew_ppm,std::uint64_t recovery_window_ns) noexcept {
        if(!source_id||!authority_epoch||!holdover_ns||!recovery_window_ns||!std::isfinite(max_slew_ppm)||max_slew_ppm<1||max_slew_ppm>500)return false;
        source_id_=source_id;epoch_=authority_epoch;max_slew_ppm_=max_slew_ppm;recovery_window_ns_=recovery_window_ns;last_sequence_=0;phase_error_ns_=0;
        discipline_.reset();discipline_.set_holdover_timeout(holdover_ns);last_state_=ClockDisciplineState::free_running;configured_=true;return true;
    }
    [[nodiscard]] bool observe(std::uint64_t sequence,std::uint64_t authority_epoch,std::uint64_t local_ns,std::uint64_t source_ns,
                               std::uint64_t local_show_ns,std::uint64_t source_show_ns) noexcept {
        if(!configured_||authority_epoch!=epoch_||sequence<=last_sequence_||!local_ns||!source_ns){++rejected_;return false;}
        last_sequence_=sequence;discipline_.observe(local_ns,source_ns);phase_error_ns_=difference(source_show_ns,local_show_ns);return apply(local_ns);
    }
    [[nodiscard]] double update(std::uint64_t local_ns) noexcept {if(configured_)(void)apply(local_ns);return applied_rate_;}
    [[nodiscard]] TransportDisciplineStatus status(std::uint64_t local_ns) noexcept {if(configured_)(void)apply(local_ns);const auto clock=discipline_.snapshot(local_ns);return{
        clock.state,source_id_,epoch_,last_sequence_,clock.observations,rejected_,holdover_entries_,phase_error_ns_,clock.drift_ppm,correction_ppm_,applied_rate_,clock.source_age_ns,configured_,false};}
private:
    [[nodiscard]] bool apply(std::uint64_t local_ns) noexcept {
        const auto clock=discipline_.snapshot(local_ns);if(clock.state==ClockDisciplineState::holdover&&last_state_!=ClockDisciplineState::holdover)++holdover_entries_;
        last_state_=clock.state;double phase_ppm=0;
        if(clock.state==ClockDisciplineState::locked)phase_ppm=static_cast<double>(phase_error_ns_)/static_cast<double>(recovery_window_ns_)*1'000'000.0;
        correction_ppm_=std::clamp(clock.drift_ppm+phase_ppm,-max_slew_ppm_,max_slew_ppm_);applied_rate_=1.0+correction_ppm_/1'000'000.0;return true;
    }
    [[nodiscard]] static std::int64_t difference(std::uint64_t a,std::uint64_t b) noexcept {
        if(a>=b)return static_cast<std::int64_t>(std::min<std::uint64_t>(a-b,0x7fffffffffffffffULL));
        return -static_cast<std::int64_t>(std::min<std::uint64_t>(b-a,0x7fffffffffffffffULL));
    }
    ClockDiscipline discipline_{};std::uint64_t source_id_{0},epoch_{0},last_sequence_{0},recovery_window_ns_{5'000'000'000ULL};
    std::uint64_t rejected_{0},holdover_entries_{0};std::int64_t phase_error_ns_{0};double max_slew_ppm_{500},correction_ppm_{0},applied_rate_{1};
    ClockDisciplineState last_state_{ClockDisciplineState::free_running};bool configured_{false};
};

} // namespace stagemesh
