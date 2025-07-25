#include "../../esp32_loader_firmware/include/system_api.h"
#include <stddef.h>

// Module metadata
static const char* MODULE_NAME = "speed_governor";
static const char* MODULE_VERSION = "1.0.0";

// Global system API pointer
static SystemAPI* sys_api = NULL;

// Speed governor state
static int current_speed_limit = 40;  // Default: 40 km/h (problematic limit)
static int override_speed_limit = -1; // -1 means no override
static bool speed_limiting_active = true;

// Function prototypes for module interface
static bool initialize_module(SystemAPI* api);
static void deinitialize_module(void);
static void update_module(void);
static int get_speed_limit(int current_speed, int road_conditions);
static void set_speed_limit_override(int new_limit);
static bool is_speed_limiting_active(void);

// Speed governor interface implementation
static SpeedGovernorInterface speed_interface = {
    .get_speed_limit = get_speed_limit,
    .set_speed_limit_override = set_speed_limit_override,
    .is_speed_limiting_active = is_speed_limiting_active
};

// Module interface structure
static ModuleInterface module_interface = {
    .module_name = MODULE_NAME,
    .module_version = MODULE_VERSION,
    .initialize = initialize_module,
    .deinitialize = deinitialize_module,
    .update = update_module,
    .module_functions = &speed_interface
};

// Entry point called by module loader
ModuleInterface* get_module_interface(void) {
    return &module_interface;
}

// Module lifecycle functions
static bool initialize_module(SystemAPI* api) {
    if (api == NULL) {
        return false;
    }
    
    sys_api = api;
    
    // Load saved configuration if any
    int saved_limit;
    if (sys_api->load_module_data("speed_limit", &saved_limit, sizeof(saved_limit))) {
        current_speed_limit = saved_limit;
        sys_api->log_printf(LOG_INFO, MODULE_NAME, "Loaded saved speed limit: %d km/h", current_speed_limit);
    } else {
        sys_api->log_printf(LOG_INFO, MODULE_NAME, "Using default speed limit: %d km/h", current_speed_limit);
    }
    
    sys_api->log_message(LOG_INFO, MODULE_NAME, "Speed Governor module initialized");
    return true;
}

static void deinitialize_module(void) {
    if (sys_api) {
        // Save current configuration
        sys_api->save_module_data("speed_limit", &current_speed_limit, sizeof(current_speed_limit));
        sys_api->log_message(LOG_INFO, MODULE_NAME, "Speed Governor module deinitialized");
        sys_api = NULL;
    }
}

static void update_module(void) {
    // This function is called periodically from the main loop
    static uint32_t last_log_time = 0;
    uint32_t current_time = sys_api->get_millis();
    
    // Log status every 10 seconds
    if (current_time - last_log_time > 10000) {
        uint32_t vehicle_speed = sys_api->get_vehicle_speed();
        bool vehicle_idle = sys_api->is_vehicle_idle();
        
        if (!vehicle_idle && speed_limiting_active) {
            int effective_limit = (override_speed_limit > 0) ? override_speed_limit : current_speed_limit;
            
            if (vehicle_speed > effective_limit) {
                sys_api->log_printf(LOG_WARN, MODULE_NAME, 
                    "SPEED VIOLATION: Vehicle speed %d km/h exceeds limit %d km/h", 
                    vehicle_speed, effective_limit);
            }
        }
        
        last_log_time = current_time;
    }
}

// Speed governor specific functions
static int get_speed_limit(int current_speed, int road_conditions) {
    if (!sys_api) {
        return 120; // Safe default
    }
    
    // Check for override
    if (override_speed_limit > 0) {
        sys_api->log_printf(LOG_DEBUG, MODULE_NAME, "Using override speed limit: %d km/h", override_speed_limit);
        return override_speed_limit;
    }
    
    // This is the problematic logic that will be updated via OTA
    // Version 1.0.0: Always returns 40 km/h regardless of conditions
    // This causes the highway problem mentioned in the requirements
    
    if (road_conditions == 0) { // Normal conditions
        sys_api->log_printf(LOG_DEBUG, MODULE_NAME, "Normal conditions, speed limit: %d km/h", current_speed_limit);
        return current_speed_limit; // Problematic: 40 km/h even on highway
    } else if (road_conditions == 1) { // Highway conditions
        // BUG: Should allow higher speeds on highway, but doesn't
        sys_api->log_printf(LOG_DEBUG, MODULE_NAME, "Highway detected, but limiting to: %d km/h", current_speed_limit);
        return current_speed_limit; // This will be fixed in v1.1.0
    } else if (road_conditions == 2) { // City conditions
        int city_limit = current_speed_limit - 10;
        sys_api->log_printf(LOG_DEBUG, MODULE_NAME, "City conditions, speed limit: %d km/h", city_limit);
        return city_limit;
    }
    
    return current_speed_limit;
}

static void set_speed_limit_override(int new_limit) {
    if (!sys_api) return;
    
    override_speed_limit = new_limit;
    if (new_limit > 0) {
        sys_api->log_printf(LOG_INFO, MODULE_NAME, "Speed limit override set to: %d km/h", new_limit);
    } else {
        sys_api->log_message(LOG_INFO, MODULE_NAME, "Speed limit override cleared");
    }
}

static bool is_speed_limiting_active(void) {
    return speed_limiting_active;
} 