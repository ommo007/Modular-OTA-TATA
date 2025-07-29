# Makefile for Speed Governor Module v2 (Updated)
# Compiles C code into a raw binary for ESP32 dynamic loading

TOOLCHAIN_PREFIX ?= xtensa-esp32-elf-
CC = $(TOOLCHAIN_PREFIX)gcc
OBJCOPY = $(TOOLCHAIN_PREFIX)objcopy
SIZE = $(TOOLCHAIN_PREFIX)size

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

.PHONY: all build clean

# Default build target
all: $(BUILD_DIR) $(BUILD_DIR)/$(MODULE_NAME).bin

# Ensure build directory exists
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Generate linker script dynamically
$(BUILD_DIR)/$(LDSCRIPT): | $(BUILD_DIR)
	@echo "ENTRY($(ENTRY_POINT_FUNC))" > $(BUILD_DIR)/$(LDSCRIPT)
	@echo "SECTIONS" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "{" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "  .text : { *(.text) }" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "  .rodata : { *(.rodata) }" >> $(BUILD_DIR)/$(LDSCRIPT)
	@echo "}" >> $(BUILD_DIR)/$(LDSCRIPT)

# Compile object files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Link ELF binary
$(BUILD_DIR)/$(MODULE_NAME).elf: $(OBJECTS) $(BUILD_DIR)/$(LDSCRIPT) | $(BUILD_DIR)
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@
	$(SIZE) $@

# Generate raw binary
$(BUILD_DIR)/$(MODULE_NAME).bin: $(BUILD_DIR)/$(MODULE_NAME).elf | $(BUILD_DIR)
	$(OBJCOPY) -O binary $< $@
	@echo "Binary size: $$(stat -f%z $@) bytes"
	@echo "VERSION: This is the updated v1.1.1 that fixes highway speed limit issue"

# Targets for GitHub Actions
build: $(BUILD_DIR)/$(MODULE_NAME).bin

clean:
	rm -rf $(BUILD_DIR)