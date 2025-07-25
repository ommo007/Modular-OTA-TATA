#include "module_loader.h"
#include <LittleFS.h>
#include <esp_heap_caps.h>
#include <esp_system.h>

// Internal function prototypes
static LoadedModule* find_loaded_module(ModuleLoader* loader, const char* module_name);
static void log_module_info(const char* message);
static void log_module_error(const char* message);

// This is the function signature we expect to find at the start of our binary blob.
typedef ModuleInterface* (*GetModuleInterfaceFunc)(void);

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
    if (module_loader_is_module_loaded(loader, module_name)) {
        return MODULE_LOAD_ALREADY_LOADED;
    }

    String file_path = "/" + String(module_name) + ".bin";
    if (!LittleFS.exists(file_path)) {
        log_module_error("Module file not found");
        return MODULE_LOAD_FILE_NOT_FOUND;
    }

    File file = LittleFS.open(file_path, "r");
    size_t file_size = file.size();
    if (file_size == 0) {
        log_module_error("Module file is empty");
        file.close();
        return MODULE_LOAD_INVALID_FORMAT;
    }

    // Allocate memory with execute permissions
    void* code_memory = heap_caps_malloc(file_size, MALLOC_CAP_EXEC);
    if (!code_memory) {
        log_module_error("Failed to allocate executable memory");
        file.close();
        return MODULE_LOAD_MEMORY_ERROR;
    }

    // Read the binary into the allocated memory
    if (file.read((uint8_t*)code_memory, file_size) != file_size) {
        log_module_error("Failed to read module into memory");
        heap_caps_free(code_memory);
        file.close();
        return MODULE_LOAD_INVALID_FORMAT;
    }
    file.close();

    // **THE MAGIC HAPPENS HERE**
    // Cast the beginning of our executable memory to our entry point function pointer
    GetModuleInterfaceFunc get_interface = (GetModuleInterfaceFunc)code_memory;
    ModuleInterface* interface = get_interface();

    if (!interface || !interface->module_name || !interface->initialize) {
        log_module_error("Invalid module interface returned");
        heap_caps_free(code_memory);
        return MODULE_LOAD_INVALID_FORMAT;
    }

    // Initialize the module, passing the system API
    if (!interface->initialize(loader->system_api)) {
        log_module_error("Module initialization function failed");
        heap_caps_free(code_memory);
        return MODULE_LOAD_INIT_FAILED;
    }

    // Find a slot and store the loaded module info
    LoadedModule* module_slot = &loader->modules[loader->loaded_count];
    strncpy(module_slot->name, interface->module_name, sizeof(module_slot->name) - 1);
    strncpy(module_slot->version, interface->module_version, sizeof(module_slot->version) - 1);
    module_slot->code_memory = code_memory;
    module_slot->code_size = file_size;
    module_slot->interface = interface;
    module_slot->is_active = true;
    module_slot->load_time = millis();

    loader->loaded_count++;
    log_module_info("Module loaded successfully");
    module_loader_list_loaded_modules(loader);
    return MODULE_LOAD_SUCCESS;
}

module_status_t module_loader_unload_module(ModuleLoader* loader, const char* module_name) {
    LoadedModule* module = find_loaded_module(loader, module_name);
    if (!module) return MODULE_UNLOAD_NOT_FOUND;

    if (module->interface && module->interface->deinitialize) {
        module->interface->deinitialize();
    }
    if (module->code_memory) {
        heap_caps_free(module->code_memory);
    }

    // Shift remaining modules to fill the gap (simple approach)
    int module_index = module - loader->modules;
    for (int i = module_index; i < loader->loaded_count - 1; i++) {
        loader->modules[i] = loader->modules[i + 1];
    }
    memset(&loader->modules[loader->loaded_count - 1], 0, sizeof(LoadedModule));
    loader->loaded_count--;

    log_module_info("Module unloaded successfully");
    return MODULE_UNLOAD_SUCCESS;
}

module_status_t module_loader_reload_module(ModuleLoader* loader, const char* module_name) {
    log_module_info("Reloading module...");
    module_loader_unload_module(loader, module_name);
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

// Remove the now-unused helper functions since we integrated the logic directly

// Internal helper functions
static LoadedModule* find_loaded_module(ModuleLoader* loader, const char* module_name) {
    for (int i = 0; i < MAX_LOADED_MODULES; i++) {
        LoadedModule* module = &loader->modules[i];
        if (module->is_active && strcmp(module->name, module_name) == 0) {
            return module;
        }
    }
    return nullptr;
}

static void log_module_info(const char* message) {
    Serial.printf("[INFO] ModuleLoader: %s\n", message);
}

static void log_module_error(const char* message) {
    Serial.printf("[ERROR] ModuleLoader: %s\n", message);
} 