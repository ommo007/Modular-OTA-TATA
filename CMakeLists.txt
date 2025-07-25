# ESP-IDF Project CMakeLists.txt
# This file provides ESP-IDF compatibility for the Modular OTA TATA project
# Note: This project is primarily designed for PlatformIO. Use PlatformIO for development.

cmake_minimum_required(VERSION 3.16)

# Set the project name
set(PROJECT_NAME "modular_ota_tata")

# Include ESP-IDF build system
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Define the project
project(${PROJECT_NAME})

# Main component (firmware)
set(COMPONENT_SRCS 
    "esp32_loader_firmware/src/main.cpp"
    "esp32_loader_firmware/src/ota_updater.cpp"
    "esp32_loader_firmware/src/module_loader.cpp"
)

set(COMPONENT_INCLUDE_DIRS
    "esp32_loader_firmware/include"
)

# Register the main component
idf_component_register(
    SRCS ${COMPONENT_SRCS}
    INCLUDE_DIRS ${COMPONENT_INCLUDE_DIRS}
    REQUIRES arduino-esp32 json mbedtls
)

# Set C++ standard
target_compile_features(${PROJECT_NAME}.elf PRIVATE cxx_std_17)

# Add build flags similar to PlatformIO
target_compile_definitions(${PROJECT_NAME}.elf PRIVATE
    CORE_DEBUG_LEVEL=3
    BOARD_HAS_PSRAM=1
)

# Add compile options
target_compile_options(${PROJECT_NAME}.elf PRIVATE
    -mfix-esp32-psram-cache-issue
)

# Partition table
set(PARTITION_TABLE_CSV_PATH ${CMAKE_CURRENT_SOURCE_DIR}/esp32_loader_firmware/custom_partitions.csv) 