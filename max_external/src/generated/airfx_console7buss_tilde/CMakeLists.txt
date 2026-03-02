include(${MAX_SDK_BASE_DIR}/script/max-pretarget.cmake)

include_directories(
    "${MAX_SDK_INCLUDES}"
    "${MAX_SDK_MSP_INCLUDES}"
    "${MAX_SDK_JIT_INCLUDES}"
)

add_library(
    ${PROJECT_NAME}
    MODULE
    "airfx_console7buss_tilde.cpp"
    "Console7BussEngine.hpp"
)

if(WIN32)
    target_compile_definitions(${PROJECT_NAME} PRIVATE NOMINMAX)
endif()

set(${PROJECT_NAME}_EXTERN_OUTPUT_NAME "airfx.console7buss~" CACHE STRING "" FORCE)
mark_as_advanced(${PROJECT_NAME}_EXTERN_OUTPUT_NAME)

include(${MAX_SDK_BASE_DIR}/script/max-posttarget.cmake)
