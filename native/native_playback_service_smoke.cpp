#include "native_playback_service.h"

#include <iostream>
#include <stdexcept>
#include <thread>

using namespace stagemesh;

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void silence(float*, std::uint32_t, std::uint32_t, void*) noexcept {}
}

int main() {
    try {
        NativePlaybackService service(silence);
        AudioRequest request;
        require(!service.activate_endpoint(request, "missing-native-endpoint"),
                "missing native endpoint was accepted");
        require(!service.active(), "failed endpoint activation left service active");

        bool wrong_thread = false;
        std::thread other([&] {
            try { (void)service.stats(); }
            catch (const std::logic_error&) { wrong_thread = true; }
        });
        other.join();
        require(wrong_thread, "playback service owner-thread contract not enforced");
        service.deactivate();
        std::cout << "{\"contractPassed\":true,\"missingEndpointRejected\":true,\"ownerThreadEnforced\":true,\"physicalHardwareQualified\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
