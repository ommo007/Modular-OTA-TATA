#include "module_loader.h"
#include <LittleFS.h>
#include <esp_heap_caps.h>
#include <esp_system.h>

// Internal function prototypes
static LoadedModule* find_module_slot(ModuleLoader* loader);
static LoadedModule* find_loaded_module(ModuleLoader* loader, const char* module_name);
static bool load_module_from_file(ModuleLoader* loader, const char* module_name, LoadedModule* module_slot);
static bool validate_module_binary(const void* code_data, size_t code_size);
static ModuleInterface* extract_module_interface(void* code_memory, size_t code_size);
static void log_module_info(const char* message);
static void log_module_error(const char* message);

bool module_loader_init(ModuleLoader* loader, SystemAPI* api) {
    if (!loader || !api) {
        return false;
    }
    
    // Clear all module slots
    memset(loader->modules, 0, sizeof(loader->modules));
    loader->loaded_count = 0;
    loader->system_api = api;
    
    log_module_info("Module loader initialized");
    return true;
}

module_status_t module_loader_load_module(ModuleLoader* loader, const char* module_name) {
    if (!loader || !module_name) {
        return MODULE_LOAD_INVALID_FORMAT;
    }
    
    // Check if module is already loaded
    if (module_loader_is_module_loaded(loader, module_name)) {
        log_module_error("Module already loaded");
        return MODULE_LOAD_ALREADY_LOADED;
    }
    
    // Find available slot
    LoadedModule* module_slot = find_module_slot(loader);
    if (!module_slot) {
        log_module_error("No available module slots");
        return MODULE_LOAD_MEMORY_ERROR;
    }
    
    // Load module from file
    if (!load_module_from_file(loader, module_name, module_slot)) {
        return MODULE_LOAD_FILE_NOT_FOUND;
    }
    
    loader->loaded_count++;
    log_module_info("Module loaded successfully");
    return MODULE_LOAD_SUCCESS;
}

module_status_t module_loader_unload_module(ModuleLoader* loader, const char* module_name) {
    if (!loader || !module_name) {
        return MODULE_UNLOAD_ERROR;
    }
    
    LoadedModule* module = find_loaded_module(loader, module_name);
    if (!module) {
        return MODULE_UNLOAD_NOT_FOUND;
    }
    
    // Call module's deinitialize function if available
    if (module->interface && module->interface->deinitialize) {
        module->interface->deinitialize();
    }
    
    // Free executable memory
    if (module->code_memory) {
        module_loader_free_executable_memory(module->code_memory, module->code_size);
    }
    
    // Clear module slot
    memset(module, 0, sizeof(LoadedModule));
    loader->loaded_count--;
    
    log_module_info("Module unloaded successfully");
    return MODULE_UNLOAD_SUCCESS;
}

module_status_t module_loader_reload_module(ModuleLoader* loader, const char* module_name) {
    if (!loader || !module_name) {
        return MODULE_LOAD_INVALID_FORMAT;
    }
    
    // Unload if currently loaded
    if (module_loader_is_module_loaded(loader, module_name)) {
        module_status_t unload_result = module_loader_unload_module(loader, module_name);
        if (unload_result != MODULE_UNLOAD_SUCCESS) {
            return MODULE_LOAD_INVALID_FORMAT;
        }
    }
    
    // Load the module again
    return module_loader_load_module(loader, module_name);
}

LoadedModule* module_loader_get_module(ModuleLoader* loader, const char* module_name) {
    return find_loaded_module(loader, module_name);
}

bool module_loader_is_module_loaded(ModuleLoader* loader, const char* module_name) {
    return find_loaded_module(loader, module_name) != nullptr;
}

void module_loader_update_all_modules(ModuleLoader* loader) {
    if (!loader) return;
    
    for (int i = 0; i < MAX_LOADED_MODULES; i++) {
        LoadedModule* module = &loader->modules[i];
        if (module->is_active && module->interface && module->interface->update) {
            module->interface->update();
        }
    }
}

void module_loader_list_loaded_modules(ModuleLoader* loader) {
    if (!loader) return;
    
    Serial.printf("Loaded modules (%d/%d):\n", loader->loaded_count, MAX_LOADED_MODULES);
    
    for (int i = 0; i < MAX_LOADED_MODULES; i++) {
        LoadedModule* module = &loader->modules[i];
        if (module->is_active) {
            Serial.printf("  %s v%s (size: %d bytes, loaded: %lu ms ago)\n",
                         module->name, module->version, module->code_size,
                         (millis() - module->load_time));
        }
    }
}

void* module_loader_allocate_executable_memory(size_t size) {
    // Allocate executable memory (IRAM for ESP32)
    void* memory = heap_caps_malloc(size, MALLOC_CAP_EXEC);
    if (memory) {
        Serial.printf("Allocated %d bytes of executable memory at 0x%p\n", size, memory);
    } else {
        log_module_error("Failed to allocate executable memory");
    }
    return memory;
}

void module_loader_free_executable_memory(void* ptr, size_t size) {
    if (ptr) {
        Serial.printf("Freeing %d bytes of executable memory at 0x%p\n", size, ptr);
        heap_caps_free(ptr);
    }
}

bool module_loader_validate_module(const char* file_path) {
    File file = LittleFS.open(file_path, "r");
    if (!file) {
        return false;
    }
    
    size_t file_size = file.size();
    file.close();
    
    // Basic validation - check if file size is reasonable
    if (file_size < 100 || file_size > 65536) {
        Serial.printf("Invalid module size: %d bytes\n", file_size);
        return false;
    }
    
    return true;
}

bool module_loader_check_abi_compatibility(const void* code_data, size_t code_size) {
    // Basic ABI compatibility check
    // In a real implementation, you would check ELF headers, symbols, etc.
    if (!code_data || code_size == 0) {
        return false;
    }
    
    // For this demo, we assume all modules are compatible
    return true;
}

bool module_loader_file_exists(const char* module_name) {
    String file_path = "/" + String(module_name) + ".bin";
    return LittleFS.exists(file_path);
}

size_t module_loader_get_file_size(const char* module_name) {
    String file_path = "/" + String(module_name) + ".bin";
    File file = LittleFS.open(file_path, "r");
    if (file) {
        size_t size = file.size();
        file.close();
        return size;
    }
    return 0;
}

bool module_loader_read_module_file(const char* module_name, void* buffer, size_t buffer_size) {
    String file_path = "/" + String(module_name) + ".bin";
    File file = LittleFS.open(file_path, "r");
    if (!file) {
        return false;
    }
    
    size_t file_size = file.size();
    if (file_size > buffer_size) {
        file.close();
        return false;
    }
    
    size_t bytes_read = file.readBytes((char*)buffer, file_size);
    file.close();
    
    return bytes_read == file_size;
}

// Internal helper functions
static LoadedModule* find_module_slot(ModuleLoader* loader) {
    for (int i = 0; i < MAX_LOADED_MODULES; i++) {
        if (!loader->modules[i].is_active) {
            return &loader->modules[i];
        }
    }
    return nullptr;
}

static LoadedModule* find_loaded_module(ModuleLoader* loader, const char* module_name) {
    for (int i = 0; i < MAX_LOADED_MODULES; i++) {
        LoadedModule* module = &loader->modules[i];
        if (module->is_active && strcmp(module->name, module_name) == 0) {
            return module;
        }
    }
    return nullptr;
}

static bool load_module_from_file(ModuleLoader* loader, const char* module_name, LoadedModule* module_slot) {
    // Check if module file exists
    if (!module_loader_file_exists(module_name)) {
        log_module_error("Module file not found");
        return false;
    }
    
    // Validate module
    String file_path = "/" + String(module_name) + ".bin";
    if (!module_loader_validate_module(file_path.c_str())) {
        log_module_error("Module validation failed");
        return false;
    }
    
    // Get file size
    size_t file_size = module_loader_get_file_size(module_name);
    if (file_size == 0) {
        log_module_error("Invalid module file size");
        return false;
    }
    
    // Allocate executable memory
    void* code_memory = module_loader_allocate_executable_memory(file_size);
    if (!code_memory) {
        log_module_error("Failed to allocate memory for module");
        return false;
    }
    
    // Read module into memory
    if (!module_loader_read_module_file(module_name, code_memory, file_size)) {
        log_module_error("Failed to read module file");
        module_loader_free_executable_memory(code_memory, file_size);
        return false;
    }
    
    // Validate binary compatibility
    if (!validate_module_binary(code_memory, file_size)) {
        log_module_error("Module binary validation failed");
        module_loader_free_executable_memory(code_memory, file_size);
        return false;
    }
    
    // Extract module interface
    ModuleInterface* interface = extract_module_interface(code_memory, file_size);
    if (!interface) {
        log_module_error("Failed to extract module interface");
        module_loader_free_executable_memory(code_memory, file_size);
        return false;
    }
    
    // Initialize module
    if (interface->initialize && !interface->initialize(loader->system_api)) {
        log_module_error("Module initialization failed");
        module_loader_free_executable_memory(code_memory, file_size);
        return false;
    }
    
    // Fill module slot
    strncpy(module_slot->name, module_name, sizeof(module_slot->name) - 1);
    strncpy(module_slot->version, interface->module_version ? interface->module_version : "unknown", 
           sizeof(module_slot->version) - 1);
    module_slot->code_memory = code_memory;
    module_slot->code_size = file_size;
    module_slot->interface = interface;
    module_slot->is_active = true;
    module_slot->load_time = millis();
    
    Serial.printf("Module %s v%s loaded successfully\n", module_slot->name, module_slot->version);
    return true;
}

static bool validate_module_binary(const void* code_data, size_t code_size) {
    // Simple validation - check for basic patterns
    // In a real implementation, you would check ELF headers, magic numbers, etc.
    if (!code_data || code_size < 32) {
        return false;
    }
    
    // For this demo, assume all binaries are valid
    return true;
}

static ModuleInterface* extract_module_interface(void* code_memory, size_t code_size) {
    // This is a simplified approach - in reality, you would need to:
    // 1. Parse the ELF/binary format
    // 2. Find the symbol table
    // 3. Locate the get_module_interface function
    // 4. Call it to get the interface
    
    // For this demo, we assume the interface is at a fixed offset
    // or use a simple function pointer cast (very unsafe in real code!)
    
    // This is a mock implementation - real dynamic loading is much more complex
    typedef ModuleInterface* (*GetModuleInterfaceFunc)(void);
    
    // WARNING: This is highly unsafe and won't work with real binaries
    // It's just for demonstration purposes
    
    // In a real implementation, you would:
    // 1. Use a proper ELF loader
    // 2. Resolve symbols and relocations
    // 3. Set up proper calling conventions
    
    // For now, return a mock interface
    static ModuleInterface mock_interface = {
        .module_name = "mock_module",
        .module_version = "1.0.0",
        .initialize = nullptr,
        .deinitialize = nullptr,
        .update = nullptr,
        .module_functions = nullptr
    };
    
    log_module_error("WARNING: Using mock module interface - real dynamic loading not implemented");
    return &mock_interface;
}

static void log_module_info(const char* message) {
    Serial.printf("[INFO] ModuleLoader: %s\n", message);
}

static void log_module_error(const char* message) {
    Serial.printf("[ERROR] ModuleLoader: %s\n", message);
} 