#include "stagemesh/realtime_qualification.hpp"

#include <cstddef>
#include <cstdlib>
#include <new>

#include "stagemesh/realtime_audit.hpp"

namespace {
thread_local stagemesh::RealtimeAudit* active_audit = nullptr;
}

namespace stagemesh {

RealtimeQualificationScope::RealtimeQualificationScope(RealtimeAudit* audit) noexcept
    : previous_(active_audit) {
#ifdef STAGEMESH_RT_QUALIFICATION
    active_audit = audit;
#else
    (void)audit;
#endif
}

RealtimeQualificationScope::~RealtimeQualificationScope() noexcept {
#ifdef STAGEMESH_RT_QUALIFICATION
    active_audit = previous_;
#endif
}

void note_realtime_allocation(unsigned long long bytes) noexcept {
#ifdef STAGEMESH_RT_QUALIFICATION
    if (active_audit) active_audit->note_allocation(bytes);
#else
    (void)bytes;
#endif
}

void note_realtime_lock_attempt() noexcept {
#ifdef STAGEMESH_RT_QUALIFICATION
    if (active_audit) active_audit->note_lock_attempt();
#endif
}

}  // namespace stagemesh

#ifdef STAGEMESH_RT_QUALIFICATION
void* operator new(std::size_t size) {
    stagemesh::note_realtime_allocation(size);
    if (void* value = std::malloc(size ? size : 1)) return value;
    throw std::bad_alloc();
}

void* operator new[](std::size_t size) {
    return ::operator new(size);
}

void* operator new(std::size_t size, std::align_val_t alignment) {
    stagemesh::note_realtime_allocation(size);
    void* value = nullptr;
    const auto boundary = static_cast<std::size_t>(alignment);
    if (posix_memalign(&value, boundary, size ? size : boundary) == 0) return value;
    throw std::bad_alloc();
}

void* operator new[](std::size_t size, std::align_val_t alignment) {
    return ::operator new(size, alignment);
}

void operator delete(void* value) noexcept { std::free(value); }
void operator delete[](void* value) noexcept { std::free(value); }
void operator delete(void* value, std::size_t) noexcept { std::free(value); }
void operator delete[](void* value, std::size_t) noexcept { std::free(value); }
void operator delete(void* value, std::align_val_t) noexcept { std::free(value); }
void operator delete[](void* value, std::align_val_t) noexcept { std::free(value); }
void operator delete(void* value, std::size_t, std::align_val_t) noexcept { std::free(value); }
void operator delete[](void* value, std::size_t, std::align_val_t) noexcept { std::free(value); }

#if defined(__linux__)
#include <pthread.h>
extern "C" int __real_pthread_mutex_lock(pthread_mutex_t* mutex);
extern "C" int __wrap_pthread_mutex_lock(pthread_mutex_t* mutex) {
    stagemesh::note_realtime_lock_attempt();
    return __real_pthread_mutex_lock(mutex);
}
#endif
#endif
