# Core 5.10 real-time qualification instrumentation

Core 5.10 makes two important real-time assumptions measurable in qualification builds: the native render callback should not allocate memory and should not acquire mutexes. Configure with `-DSTAGEMESH_RT_QUALIFICATION=ON`; normal builds leave the probes compiled out. The developer-alpha release gate enables them explicitly.

`RealtimeQualificationScope` marks only the render callback thread and publishes violations into its existing per-output `RealtimeAudit`. C++ `new`/`new[]` requests record an attempt and requested byte count. On Linux, link-time wrapping of `pthread_mutex_lock` records mutex acquisition attempts. Reporting uses relaxed atomics and remains outside the callback.

These probes are evidence, not enforcement. The allocation detector covers C++ allocation operators linked through the engine; it does not prove that every third-party shared library allocator call is visible. The lock detector covers pthread mutex acquisition linked through the qualification executable; it does not classify lock duration or non-pthread synchronization. A stage-qualified build still requires platform tracing and hardware soak evidence.

The isolated plugin host is intentionally outside the audio callback and necessarily serializes JSON IPC. In qualification mode its audit reports serialization-lock attempts, actual contention (a failed nonblocking acquisition), maximum acquisition wait, and cumulative encoded request/response bytes. Counters update under the acquired lock. Those values reveal pressure at the isolation boundary; they are not presented as native callback allocation counts.

Qualification builds currently require Linux. CMake rejects this option on unsupported platforms instead of advertising enabled probes with incomplete mutex interception. Ordinary builds remain available with the option off, and the native protocol tests accept either mode while requiring the handshake and status to agree.

Status remains observational and always reports `physicalOutputsArmed=false`. A zero violation count is meaningful only when `qualificationEnabled` is true and the exercised callbacks, adapters, hardware, duration and load are recorded alongside it.

## 5.10.1 validation checkpoint

The Python suite passes against a directly compiled ordinary engine (304 tests).
Direct native builds exercise both qualification modes, including nested scope
restoration and concurrent thread-local isolation; the current C ABI smoke test
and automation work-budget check also pass. CMake and CTest were unavailable in
this session, so these results do not constitute a fresh full release-gate pass.
No hardware or installer qualification was performed.
