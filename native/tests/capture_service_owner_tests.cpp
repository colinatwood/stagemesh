#include "stagemesh/capture_service_owner.hpp"
#include <atomic>
#include <cstdlib>
#define assert(condition) do { if (!(condition)) std::abort(); } while (false)
#include <stdexcept>

struct Evidence {
    std::atomic<unsigned> services{0};
    std::atomic<bool> destroyed{false}, wrong_thread{false};
};
struct FakeCapture {
    Evidence& evidence;
    std::thread::id owner = std::this_thread::get_id();
    bool active = false;
    bool fail = false;
    explicit FakeCapture(Evidence& value) : evidence(value) {}
    void check() { if (owner != std::this_thread::get_id()) evidence.wrong_thread = true; }
    void service(unsigned) { check(); ++evidence.services; if (fail) { fail = false; throw std::runtime_error("service failure"); } }
    void deactivate() noexcept { check(); active = false; }
    ~FakeCapture() { check(); assert(!active); evidence.destroyed = true; }
};
int main() {
    Evidence evidence;
    stagemesh::CaptureServiceOwner<FakeCapture> owner([&] { return std::make_unique<FakeCapture>(evidence); });
    const auto thread = owner.execute([](FakeCapture& service) { service.check(); service.active = true; return service.owner; });
    assert(thread != std::this_thread::get_id());
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (evidence.services < 3 && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    assert(evidence.services >= 3); // Progress while caller sends no commands.
    bool threw = false;
    try { owner.execute([](FakeCapture&) -> bool { throw std::runtime_error("command failure"); }); }
    catch (const std::runtime_error&) { threw = true; }
    assert(threw);
    assert(owner.execute([](FakeCapture& service) { return service.active; }));
    std::thread first([&] { for (unsigned i=0; i<50; ++i) owner.execute([](FakeCapture& service) { service.check(); return 1; }); });
    std::thread second([&] { for (unsigned i=0; i<50; ++i) owner.execute([](FakeCapture& service) { service.check(); return 2; }); });
    first.join(); second.join();
    owner.execute([](FakeCapture& service) { service.fail = true; });
    assert(!owner.execute([](FakeCapture& service) { return service.active; }));
    owner.shutdown(); owner.shutdown();
    assert(evidence.destroyed && !evidence.wrong_thread);
    threw = false;
    try { owner.execute([](FakeCapture&) { return true; }); } catch (const std::runtime_error&) { threw = true; }
    assert(threw);
    threw = false;
    try { stagemesh::CaptureServiceOwner<FakeCapture> bad([]() -> std::unique_ptr<FakeCapture> { throw std::runtime_error("startup failure"); }); }
    catch (const std::runtime_error&) { threw = true; }
    assert(threw);
}
