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

# Keep release artifacts explicit and reproducible. Cross builds may package the
# linked binaries, but runtime qualification still belongs on matching hosts.
include(GNUInstallDirs)
install(TARGETS stagemesh_engine stageforge_core
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
if(TARGET stageforge_devices)
    install(TARGETS stageforge_devices
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
endif()
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(DIRECTORY native/include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

set(CPACK_PACKAGE_NAME "stagemesh")
set(CPACK_PACKAGE_VENDOR "StageMesh")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "StageMesh native engine and device services")
set(CPACK_PACKAGE_VERSION "0.1.0")
set(CPACK_PACKAGE_FILE_NAME "stagemesh-${CPACK_PACKAGE_VERSION}-${CMAKE_SYSTEM_NAME}-${CMAKE_SYSTEM_PROCESSOR}")
include(CPack)
