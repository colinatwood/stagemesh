#pragma once

#include <cstdint>

namespace stagemesh {

enum class InteropSessionState : std::uint8_t { empty=0,offered=1,authenticated=2,negotiated=3,consented=4,active=5,expired=6 };

struct AuthenticatedInteropSessionStatus {
    std::uint64_t session_id{0},transcript_hash{0},nonce{0},authority_epoch{0},sequence{0},expires_unix_ms{0};
    std::uint64_t profile_revision{0},registry_revision{0},consent_digest{0};
    std::uint32_t protocol_version{0},profile_schema_version{0};
    InteropSessionState state{InteropSessionState::empty};
    bool compatible{false},authenticated{false},physical_outputs_armed{false};
};

class AuthenticatedInteropSession final {
public:
    [[nodiscard]] bool offer(std::uint64_t session_id,std::uint64_t transcript_hash,std::uint64_t nonce,
                             std::uint64_t epoch,std::uint64_t sequence,std::uint64_t expires_unix_ms) noexcept {
        if(session_id==0||transcript_hash==0||nonce==0||epoch==0||sequence==0||expires_unix_ms==0||
           (status_.state!=InteropSessionState::empty&&status_.state!=InteropSessionState::expired))return false;
        status_={};status_.session_id=session_id;status_.transcript_hash=transcript_hash;status_.nonce=nonce;
        status_.authority_epoch=epoch;status_.sequence=sequence;status_.expires_unix_ms=expires_unix_ms;status_.state=InteropSessionState::offered;return true;
    }
    [[nodiscard]] bool authenticate(bool signature_verified,std::uint64_t now_unix_ms,std::uint64_t expected_epoch,
                                    std::uint64_t minimum_sequence) noexcept {
        if(status_.state!=InteropSessionState::offered||!signature_verified||now_unix_ms>status_.expires_unix_ms||
           status_.authority_epoch!=expected_epoch||status_.sequence<=minimum_sequence){expire();return false;}
        status_.authenticated=true;status_.state=InteropSessionState::authenticated;return true;
    }
    [[nodiscard]] bool negotiate(bool compatible,std::uint32_t protocol,std::uint32_t profile_schema,
                                 std::uint64_t profile_revision,std::uint64_t registry_revision) noexcept {
        if(status_.state!=InteropSessionState::authenticated||!compatible||protocol==0||profile_schema==0){expire();return false;}
        status_.compatible=true;status_.protocol_version=protocol;status_.profile_schema_version=profile_schema;
        status_.profile_revision=profile_revision;status_.registry_revision=registry_revision;status_.state=InteropSessionState::negotiated;return true;
    }
    [[nodiscard]] bool consent(bool accepted,std::uint64_t projection_digest) noexcept {
        if(status_.state!=InteropSessionState::negotiated||!accepted||projection_digest==0){expire();return false;}
        status_.consent_digest=projection_digest;status_.state=InteropSessionState::consented;return true;
    }
    [[nodiscard]] bool activate(std::uint64_t now_unix_ms,std::uint64_t epoch,std::uint64_t profile_revision,
                                std::uint64_t registry_revision) noexcept {
        if(status_.state!=InteropSessionState::consented||now_unix_ms>status_.expires_unix_ms||epoch!=status_.authority_epoch||
           profile_revision!=status_.profile_revision||registry_revision!=status_.registry_revision){expire();return false;}
        status_.state=InteropSessionState::active;status_.physical_outputs_armed=false;return true;
    }
    void invalidate_if_changed(std::uint64_t epoch,std::uint64_t profile_revision,std::uint64_t registry_revision) noexcept {
        if(status_.state==InteropSessionState::active&&(epoch!=status_.authority_epoch||profile_revision!=status_.profile_revision||registry_revision!=status_.registry_revision))expire();
    }
    void expire() noexcept {status_.state=InteropSessionState::expired;status_.compatible=false;status_.physical_outputs_armed=false;}
    [[nodiscard]] AuthenticatedInteropSessionStatus status() const noexcept{return status_;}
private: AuthenticatedInteropSessionStatus status_{};
};

} // namespace stagemesh
