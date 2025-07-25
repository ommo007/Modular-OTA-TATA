#ifndef MODULE_LOADER_H
#define MODULE_LOADER_H

#include "system_api.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Maximum number of loaded modules
#define MAX_LOADED_MODULES 8

// Module loading status
typedef enum {
    MODULE_LOAD_SUCCESS = 0,
    MODULE_LOAD_FILE_NOT_FOUND = 1,
    MODULE_LOAD_MEMORY_ERROR = 2,
    MODULE_LOAD_INVALID_FORMAT = 3,
    MODULE_LOAD_INIT_FAILED = 4,
    MODULE_LOAD_ALREADY_LOADED = 5,
    MODULE_UNLOAD_SUCCESS = 6,
    MODULE_UNLOAD_NOT_FOUND = 7,
    MODULE_UNLOAD_ERROR = 8
} module_status_t;

// Loaded module information
typedef struct {
    char name[32];
    char version[32];
    void* code_memory;        // Executable memory region
    size_t code_size;
    ModuleInterface* interface;
    bool is_active;
    uint32_t load_time;
} LoadedModule;

// Module loader structure
typedef struct {
    LoadedModule modules[MAX_LOADED_MODULES];
    uint8_t loaded_count;
    SystemAPI* system_api;
} ModuleLoader;

// Function declarations
bool module_loader_init(ModuleLoader* loader, SystemAPI* api);
module_status_t module_loader_load_module(ModuleLoader* loader, const char* module_name);
module_status_t module_loader_unload_module(ModuleLoader* loader, const char* module_name);
module_status_t module_loader_reload_module(ModuleLoader* loader, const char* module_name);

// Module management
LoadedModule* module_loader_get_module(ModuleLoader* loader, const char* module_name);
bool module_loader_is_module_loaded(ModuleLoader* loader, const char* module_name);
void module_loader_update_all_modules(ModuleLoader* loader);
void module_loader_list_loaded_modules(ModuleLoader* loader);

// Memory management
void* module_loader_allocate_executable_memory(size_t size);
void module_loader_free_executable_memory(void* ptr, size_t size);

// Module validation
bool module_loader_validate_module(const char* file_path);
bool module_loader_check_abi_compatibility(const void* code_data, size_t code_size);

// Module file operations
bool module_loader_file_exists(const char* module_name);
size_t module_loader_get_file_size(const char* module_name);
bool module_loader_read_module_file(const char* module_name, void* buffer, size_t buffer_size);

#ifdef __cplusplus
}
#endif

#endif // MODULE_LOADER_H 