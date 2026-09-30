#pragma once

namespace stagemesh {

class RealtimeAudit;

class RealtimeQualificationScope final {
public:
    explicit RealtimeQualificationScope(RealtimeAudit* audit) noexcept;
    ~RealtimeQualificationScope() noexcept;
    RealtimeQualificationScope(const RealtimeQualificationScope&) = delete;
    RealtimeQualificationScope& operator=(const RealtimeQualificationScope&) = delete;

private:
    RealtimeAudit* previous_{nullptr};
};

void note_realtime_allocation(unsigned long long bytes) noexcept;
void note_realtime_lock_attempt() noexcept;

}  // namespace stagemesh
