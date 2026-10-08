#pragma once

#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>

namespace stagemesh {

inline std::string format_windows_hresult(std::int32_t value) {
    std::ostringstream output;
    output << value << " (0x"
           << std::uppercase << std::hex << std::setfill('0') << std::setw(8)
           << static_cast<std::uint32_t>(value) << ')';
    return output.str();
}

} // namespace stagemesh
