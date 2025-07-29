# Makefile for Speed Governor Module v2 (Updated)
# Compiles C code into a raw binary for ESP32 dynamic loading

# Toolchain configuration with fallback detection
TOOLCHAIN_PREFIX ?= xtensa-esp32-elf-
CC = $(TOOLCHAIN_PREFIX)gcc
OBJCOPY = $(TOOLCHAIN_PREFIX)objcopy
SIZE = $(TOOLCHAIN_PREFIX)size

# Check if toolchain is available
TOOLCHAIN_CHECK := $(shell which $(CC) 2>/dev/null)
ifeq ($(TOOLCHAIN_CHECK),)
$(error ESP32 toolchain not found. Please install xtensa-esp32-elf toolchain or set TOOLCHAIN_PREFIX)
endif

MODULE_NAME = speed_governor
SRC_DIR = src
BUILD_DIR = build
ENTRY_POINT_FUNC = get_module_interface
LDSCRIPT = esp32_module.ld

# Sources
SOURCES = $(wildcard $(SRC_DIR)/*.c)
OBJECTS = $(SOURCES:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)

# Flags
CFLAGS = -Os -mlongcalls -ffunction-sections -fdata-sections \
	-fPIC -nostdlib -std=c99 -Wall \
	-I../../esp32_loader_firmware/include

LDFLAGS = -nostdlib -Wl,--gc-sections -T $(BUILD_DIR)/$(LDSCRIPT) -lgcc -lm

# Cross-platform stat command
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    STAT_SIZE = stat -f%z
else
    STAT_SIZE = stat -c%s
endif

.PHONY: all build clean check-toolchain

# Default build target
all: check-toolchain $(BUILD_DIR)/$(MODULE_NAME).bin

# Check toolchain availability
check-toolchain:
	@echo "Checking ESP32 toolchain..."
	@which $(CC) > /dev/null || (echo "Error: $(CC) not found in PATH" && exit 1)
	@echo "Toolchain found: $(shell which $(CC))"

# Ensure build directory exists
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Generate linker script dynamically
$(BUILD_DIR)/$(LDSCRIPT): | $(BUILD_DIR)
	@echo "Generating linker script..."
	@echo "ENTRY($(ENTRY_POINT_FUNC))" > $(BUILD_DIR)/$(LDSCRIPT)
	@echo "SECTIONS" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "{" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "  .text : { *(.text) }" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "  .rodata : { *(.rodata) }" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "}" >> $(BUILD_DIR)/$(LDSCRIPT)

# Compile object files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	@echo "Compiling $<..."
	$(CC) $(CFLAGS) -c $< -o $@

# Link ELF binary
$(BUILD_DIR)/$(MODULE_NAME).elf: $(OBJECTS) $(BUILD_DIR)/$(LDSCRIPT)
	@echo "Linking ELF binary..."
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@
	$(SIZE) $@

# Generate raw binary
$(BUILD_DIR)/$(MODULE_NAME).bin: $(BUILD_DIR)/$(MODULE_NAME).elf
	@echo "Generating raw binary..."
	$(OBJCOPY) -O binary $< $@
	@echo "Binary size: $$($(STAT_SIZE) $@) bytes"

# Targets for GitHub Actions
build: check-toolchain $(BUILD_DIR)/$(LDSCRIPT) $(BUILD_DIR)/$(MODULE_NAME).bin

clean:
	rm -rf $(BUILD_DIR)

# Help target
help:
	@echo "Available targets:"
	@echo "  all         - Build the module binary (default)"
	@echo "  build       - Same as all, for GitHub Actions"
	@echo "  clean       - Remove build directory"
	@echo "  check-toolchain - Verify ESP32 toolchain is available"
	@echo "  help        - Show this help message"