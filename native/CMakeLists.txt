cmake_minimum_required(VERSION 3.20)
# Preserve device-only CI; root builds include the recovered engine as well.
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(stagemesh_devices LANGUAGES CXX)
    enable_testing()
else()
    include(${CMAKE_CURRENT_SOURCE_DIR}/engine.cmake)
endif()
if(WIN32 OR APPLE)
    include(${CMAKE_CURRENT_SOURCE_DIR}/devices.cmake)
    # Full-tree builds reuse the same target-OS monitor/identity implementation
    # that device-only CI qualifies. Do not duplicate platform enumeration in
    # stagemesh_core or silently fall back to default endpoints.
    if(TARGET stagemesh_core)
        target_link_libraries(stagemesh_core PUBLIC stagemesh_devices)
    endif()
endif()
