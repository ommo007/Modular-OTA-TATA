# Makefile for Speed Governor Module
# Compiles C code into a raw binary for ESP32 dynamic loading

# ESP-IDF toolchain (adjust path as needed)
TOOLCHAIN_PREFIX ?= xtensa-esp32-elf-
CC = $(TOOLCHAIN_PREFIX)gcc
OBJCOPY = $(TOOLCHAIN_PREFIX)objcopy
SIZE = $(TOOLCHAIN_PREFIX)size

# Module name
MODULE_NAME = speed_governor

# Directories
SRC_DIR = src
INCLUDE_DIR = include
BUILD_DIR = build

# Source files
SOURCES = $(wildcard $(SRC_DIR)/*.c)
OBJECTS = $(SOURCES:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)

# Compiler flags for ESP32 module compilation
CFLAGS = -Os \
         -mlongcalls \
         -mtext-section-literals \
         -ffunction-sections \
         -fdata-sections \
         -fPIC \
         -nostdlib \
         -nostartfiles \
         -nodefaultlibs \
         -std=c99 \
         -Wall \
         -Wextra \
         -I$(INCLUDE_DIR) \
         -I../../esp32_loader_firmware/include \
         -DESP32_MODULE_BUILD

# Linker flags
LDFLAGS = -nostdlib \
          -nodefaultlibs \
          -nostartfiles \
          -Wl,--gc-sections \
          -Wl,-shared \
          -Wl,-Bsymbolic

# Default target
all: $(BUILD_DIR)/$(MODULE_NAME).bin

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Compile source files to object files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	@echo "Compiling $<..."
	$(CC) $(CFLAGS) -c $< -o $@

# Link object files into an ELF
$(BUILD_DIR)/$(MODULE_NAME).elf: $(OBJECTS)
	@echo "Linking $(MODULE_NAME).elf..."
	$(CC) $(LDFLAGS) $(OBJECTS) -o $@
	$(SIZE) $@

# Extract .text section to create raw binary
$(BUILD_DIR)/$(MODULE_NAME).bin: $(BUILD_DIR)/$(MODULE_NAME).elf
	@echo "Creating binary $(MODULE_NAME).bin..."
	$(OBJCOPY) -O binary -j .text $< $@
	@echo "Binary size: $$(stat -c%s $@) bytes"
	@echo "Binary created: $@"

# Build target (for CI/CD)
build: $(BUILD_DIR)/$(MODULE_NAME).bin

# Clean build artifacts
clean:
	rm -rf $(BUILD_DIR)

# Install ESP-IDF toolchain (helper target)
install-toolchain:
	@echo "Please install ESP-IDF and ensure xtensa-esp32-elf-gcc is in your PATH"
	@echo "Visit: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/"

# Show help
help:
	@echo "Available targets:"
	@echo "  all              - Build the module binary (default)"
	@echo "  build           - Build the module binary (alias for all)"
	@echo "  clean           - Clean build artifacts"
	@echo "  install-toolchain - Show toolchain installation instructions"
	@echo "  help            - Show this help message"

# Declare phony targets
.PHONY: all build clean install-toolchain help

# Check if toolchain is available
check-toolchain:
	@which $(CC) > /dev/null || (echo "Error: $(CC) not found. Please install ESP-IDF toolchain." && exit 1) 