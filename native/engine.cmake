find_package(Threads REQUIRED)

add_library(stagemesh_core STATIC
    src/core_state.cpp
    src/audio_device.cpp
    src/audio_device_manager.cpp
    src/audio_graph.cpp
    src/alsa_audio_output.cpp
    src/alsa_audio_input.cpp
    src/artnet_udp_output.cpp
    src/sacn_udp_output.cpp
    src/monitor_bus.cpp
    src/monitor_mixer.cpp
    src/monitor_graph_router.cpp
    src/midi_input.cpp
    src/midi_input_owner.cpp
    src/transport_clock.cpp
    src/uwb_hardware_bridge.cpp
    src/le_iso_hardware.cpp
    src/realtime_qualification.cpp
)

target_compile_features(stagemesh_core PUBLIC cxx_std_20)
target_link_libraries(stagemesh_core PUBLIC ${CMAKE_DL_LIBS} Threads::Threads)
if(WIN32)
    target_compile_definitions(stagemesh_core PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN)
    target_link_libraries(stagemesh_core PUBLIC ws2_32)
endif()
target_include_directories(stagemesh_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${PROJECT_SOURCE_DIR}/include
)

if(STAGEMESH_RT_QUALIFICATION)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "STAGEMESH_RT_QUALIFICATION currently supports Linux only; disable it for ordinary builds")
    endif()
    target_compile_definitions(stagemesh_core PUBLIC STAGEMESH_RT_QUALIFICATION=1)
    if(UNIX AND NOT APPLE)
        target_link_options(stagemesh_core INTERFACE -Wl,--wrap=pthread_mutex_lock)
    endif()
endif()

if(MSVC)
    target_compile_options(stagemesh_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(stagemesh_core PRIVATE -Wall -Wextra -Wpedantic)
endif()


add_executable(stagemesh_engine src/engine_main.cpp)
target_link_libraries(stagemesh_engine PRIVATE stagemesh_core)
target_compile_features(stagemesh_engine PRIVATE cxx_std_20)
if(MSVC)
    target_compile_options(stagemesh_engine PRIVATE /W4 /permissive-)
    # The recovered engine owns several megabytes of fixed-capacity render scratch
    # in main() automatic storage. Windows' 1 MiB default process stack overflows
    # before authentication starts, while Linux/macOS already run the same bounded
    # storage successfully. Reserve a fixed 16 MiB stack for this consolidation
    # build; moving long-lived scratch into explicit engine-owned storage remains
    # a separate post-consolidation cleanup and must not touch RT callback stacks.
    target_link_options(stagemesh_engine PRIVATE /STACK:16777216)
else()
    target_compile_options(stagemesh_engine PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(STAGEMESH_BUILD_TESTS)
    enable_testing()
    add_executable(stagemesh_native_tests tests/native_tests.cpp)
    target_link_libraries(stagemesh_native_tests PRIVATE stagemesh_core)
    target_compile_features(stagemesh_native_tests PRIVATE cxx_std_20)
    if(MSVC)
        target_compile_options(stagemesh_native_tests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(stagemesh_native_tests PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    add_test(NAME stagemesh_native_tests COMMAND stagemesh_native_tests)
    add_executable(stagemesh_current_abi_smoke ../tests/core_api_510_smoke.c)
    target_include_directories(stagemesh_current_abi_smoke PRIVATE ${PROJECT_SOURCE_DIR}/include)
    add_test(NAME stagemesh_current_abi_smoke COMMAND stagemesh_current_abi_smoke)
endif()

add_executable(capture_service_owner_tests tests/capture_service_owner_tests.cpp)
target_include_directories(capture_service_owner_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(capture_service_owner_tests PRIVATE Threads::Threads)
target_compile_features(capture_service_owner_tests PRIVATE cxx_std_20)
add_test(NAME capture_service_owner COMMAND capture_service_owner_tests)
set_tests_properties(capture_service_owner PROPERTIES TIMEOUT 10)

add_executable(midi_input_owner_tests tests/midi_input_owner_tests.cpp)
target_link_libraries(midi_input_owner_tests PRIVATE stagemesh_core)
target_compile_features(midi_input_owner_tests PRIVATE cxx_std_20)
add_test(NAME midi_input_owner COMMAND midi_input_owner_tests)
set_tests_properties(midi_input_owner PROPERTIES TIMEOUT 10)

if(APPLE)
    add_executable(midi_hardware_smoke midi_hardware_smoke.cpp)
    target_link_libraries(midi_hardware_smoke PRIVATE stagemesh_core)
    target_compile_features(midi_hardware_smoke PRIVATE cxx_std_20)
endif()

# Report serialization is portable; no MIDI hardware is needed for this test.
add_executable(midi_smoke_evidence_tests tests/midi_smoke_evidence_tests.cpp)
target_include_directories(midi_smoke_evidence_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(midi_smoke_evidence_tests PRIVATE cxx_std_17)
add_test(NAME midi_smoke_evidence COMMAND midi_smoke_evidence_tests)
set_tests_properties(midi_smoke_evidence PROPERTIES TIMEOUT 5)
