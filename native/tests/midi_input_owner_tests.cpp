#include "stagemesh/midi_input_owner.hpp"

#include <cassert>
#include <thread>

int main() {
    stagemesh::MidiInputOwner owner;
    stagemesh::MidiInputMessage message{123, 0x90, 60, 100};
    constexpr unsigned producers = 4;
    constexpr unsigned per_producer = 100;
    std::thread workers[producers];
    for (unsigned producer = 0; producer < producers; ++producer) {
        workers[producer] = std::thread([&owner, message, producer] {
            for (unsigned i = 0; i < per_producer; ++i) {
                auto copy = message;
                copy.data1 = static_cast<std::uint8_t>(producer);
                assert(owner.inject("test-midi", "player", copy));
            }
        });
    }
    for (auto& worker : workers) worker.join();

    unsigned received = 0;
    stagemesh::CapturedMidiInput event{};
    while (owner.pop(event)) ++received;
    assert(received == producers * per_producer);
    assert(owner.audit_status().injected_messages == received);
    assert(owner.poll(456) == 0);
    return 0;
}
