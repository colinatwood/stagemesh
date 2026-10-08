# Reject unsupported arguments before device access, even with endpoint opt-ins.
foreach(argument_set IN ITEMS "--unknown" "--help;extra")
  execute_process(
    COMMAND "${CMAKE_COMMAND}" -E env
      STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST=1
      STAGEMESH_ALLOW_ENDPOINT_CAPTURE_TEST=1
      "${SMOKE}" ${argument_set}
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error
    TIMEOUT 5)
  if(NOT result STREQUAL "2" OR NOT error MATCHES "Unsupported arguments")
    message(FATAL_ERROR "Expected usage rejection before device access: ${result}, ${output}, ${error}")
  endif()
endforeach()
