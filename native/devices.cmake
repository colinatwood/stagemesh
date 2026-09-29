cmake_minimum_required(VERSION 3.20)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(STAGEFORGE_DEVICE_ASAN "Enable AddressSanitizer for device lifecycle tests" OFF)

add_library(stageforge_devices
  device_monitor.cpp
  device_identity.cpp
  device_execution_fence.cpp
  audio_preflight.cpp
  audio_stream_lifecycle.cpp
  audio_conversion.cpp
  software_audio_render.cpp
  native_endpoint_stream.cpp)
target_include_directories(stageforge_devices PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(WIN32)
  include(CheckCXXSourceCompiles)
  check_cxx_source_compiles(
    "#include <windows.h>\n#include <mmdeviceapi.h>\nint main(){ (void)PKEY_AudioEndpoint_StableId; return 0; }"
    STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID)
  if(STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID)
    target_compile_definitions(stageforge_devices PRIVATE STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID=1)
  else()
    target_compile_definitions(stageforge_devices PRIVATE STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID=0)
  endif()
  target_link_libraries(stageforge_devices PUBLIC ole32 uuid winmm cfgmgr32)
elseif(APPLE)
  target_link_libraries(stageforge_devices PUBLIC "-framework CoreAudio" "-framework CoreMIDI" "-framework CoreFoundation" "-framework AudioToolbox" "-framework AudioUnit")
  if(STAGEFORGE_DEVICE_ASAN)
    target_compile_options(stageforge_devices PRIVATE -fsanitize=address -fno-omit-frame-pointer)
  endif()
else()
  message(FATAL_ERROR "Device monitor requires Windows or macOS")
endif()

add_executable(device_lifecycle_smoke device_lifecycle_smoke.cpp)
target_link_libraries(device_lifecycle_smoke PRIVATE stageforge_devices)
add_executable(device_execution_fence_smoke device_execution_fence_smoke.cpp)
target_link_libraries(device_execution_fence_smoke PRIVATE stageforge_devices)
add_executable(audio_preflight_smoke audio_preflight_smoke.cpp)
target_link_libraries(audio_preflight_smoke PRIVATE stageforge_devices)
add_executable(audio_stream_lifecycle_smoke audio_stream_lifecycle_smoke.cpp)
target_link_libraries(audio_stream_lifecycle_smoke PRIVATE stageforge_devices)
add_executable(native_playback_smoke native_playback_smoke.cpp)
target_link_libraries(native_playback_smoke PRIVATE stageforge_devices)
add_executable(native_capture_smoke native_capture_smoke.cpp)
target_link_libraries(native_capture_smoke PRIVATE stageforge_devices)
add_executable(native_selected_loss_smoke native_selected_loss_smoke.cpp)
target_link_libraries(native_selected_loss_smoke PRIVATE stageforge_devices)
add_executable(audio_conversion_smoke audio_conversion_smoke.cpp)
target_link_libraries(audio_conversion_smoke PRIVATE stageforge_devices)
if(APPLE AND STAGEFORGE_DEVICE_ASAN)
  foreach(target device_lifecycle_smoke device_execution_fence_smoke audio_preflight_smoke audio_stream_lifecycle_smoke native_playback_smoke native_capture_smoke native_selected_loss_smoke audio_conversion_smoke)
    target_compile_options(${target} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
    target_link_options(${target} PRIVATE -fsanitize=address)
  endforeach()
endif()

enable_testing()
add_test(NAME device_lifecycle COMMAND device_lifecycle_smoke)
set_tests_properties(device_lifecycle PROPERTIES TIMEOUT 30)
add_test(NAME device_execution_fence COMMAND device_execution_fence_smoke)
set_tests_properties(device_execution_fence PROPERTIES TIMEOUT 30)
add_test(NAME audio_preflight COMMAND audio_preflight_smoke)
set_tests_properties(audio_preflight PROPERTIES TIMEOUT 30)
add_test(NAME audio_stream_lifecycle COMMAND audio_stream_lifecycle_smoke)
set_tests_properties(audio_stream_lifecycle PROPERTIES TIMEOUT 30)

add_test(NAME native_playback COMMAND native_playback_smoke)
set_tests_properties(native_playback PROPERTIES TIMEOUT 30)

add_test(NAME native_capture COMMAND native_capture_smoke)
set_tests_properties(native_capture PROPERTIES TIMEOUT 30)

add_test(NAME native_selected_loss COMMAND native_selected_loss_smoke)
set_tests_properties(native_selected_loss PROPERTIES TIMEOUT 30)
add_test(NAME audio_conversion COMMAND audio_conversion_smoke)
set_tests_properties(audio_conversion PROPERTIES TIMEOUT 30)
