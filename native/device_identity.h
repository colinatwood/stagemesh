#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace stageforge {

enum class DeviceKind { Audio, Midi };
enum class IdentityStrength { Volatile, InstallationSnapshot, OsStableEndpoint };
enum class ResolutionStatus { Attached, Rebound, Detached, Ambiguous };

struct DeviceRecord {
    DeviceKind kind = DeviceKind::Audio;
    std::string native_hash;
    std::string persistent_hash;
    IdentityStrength identity_strength = IdentityStrength::Volatile;
    bool automatic_reconnect = false;
    bool input = false;
    bool output = false;
    std::uint32_t native_index = 0xffffffffu;
};

struct DeviceSelection {
    DeviceKind kind = DeviceKind::Audio;
    std::string native_hash;
    std::string persistent_hash;
    bool automatic_reconnect = false;
    bool require_input = false;
    bool require_output = false;
};

struct DeviceResolution {
    ResolutionStatus status = ResolutionStatus::Detached;
    std::size_t index = static_cast<std::size_t>(-1);
};

std::string sha256_hex(std::string_view input);
std::string sha256_token(std::string_view input);
DeviceSelection pin_device(const DeviceRecord& record, bool require_input = false, bool require_output = false);
// Strong selections require current stable identity and reconnect assurance,
// even for an unchanged native hash. Downgrades resolve Detached; duplicate
// identities remain Ambiguous rather than being filtered into a unique match.
DeviceResolution resolve_device(const DeviceSelection& selection, const std::vector<DeviceRecord>& devices);
const char* resolution_status_name(ResolutionStatus status);
const char* identity_strength_name(IdentityStrength strength);
const char* device_kind_name(DeviceKind kind);

}
