cmake_minimum_required(VERSION 3.15)
project(MyAmpyWCX LANGUAGES CXX)

# 64‑bit build
set(CMAKE_GENERATOR_PLATFORM x64)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include SDK headers
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/SDK)

set(SRC_FILES
    src/MyAmpy.cpp
    src/SerialMicropythonClient.cpp
)

add_library(MyAmpy SHARED ${SRC_FILES} resources/MyAmpy.rc)

set_target_properties(MyAmpy PROPERTIES
    PREFIX ""
    OUTPUT_NAME "MyAmpy"
    SUFFIX ".wfx64"
)

if(MSVC)
    target_compile_options(MyAmpy PRIVATE /W4 /EHsc)
else()
    target_compile_options(MyAmpy PRIVATE -Wall -Wextra -O2)
endif()
