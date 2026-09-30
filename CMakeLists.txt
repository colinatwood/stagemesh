cmake_minimum_required(VERSION 3.20)
project(StageMesh LANGUAGES C CXX)

option(STAGEFORGE_BUILD_TESTS "Build native infrastructure tests" ON)
option(STAGEFORGE_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(STAGEFORGE_RT_QUALIFICATION "Instrument allocations and mutex acquisition inside real-time callback scopes" OFF)

if(STAGEFORGE_ENABLE_SANITIZERS)
    if(MSVC)
        message(FATAL_ERROR "STAGEFORGE_ENABLE_SANITIZERS currently requires GCC or Clang")
    endif()
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
endif()

if(STAGEFORGE_BUILD_TESTS)
    enable_testing()
endif()

add_subdirectory(native)
