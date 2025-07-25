#ifndef SYSTEM_API_H
#define SYSTEM_API_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// LED types for visual feedback
typedef enum {
    LED_YELLOW = 0,  // Update available
    LED_GREEN = 1,   // Update success
    LED_RED = 2      // Update failed
} led_type_t;

// Log levels for system logging
typedef enum {
    LOG_DEBUG = 0,
    LOG_INFO = 1,
    LOG_WARN = 2,
    LOG_ERROR = 3
} log_level_t;

// System API structure - passed to each loaded module
typedef struct {
    // Logging functions
    void (*log_message)(log_level_t level, const char* tag, const char* message);
    void (*log_printf)(log_level_t level, const char* tag, const char* format, ...);
    
    // Time functions
    uint32_t (*get_millis)(void);
    uint64_t (*get_micros)(void);
    
    // GPIO/LED control
    void (*set_led_state)(led_type_t led, bool is_on);
    bool (*get_button_state)(void);
    
    // Sensor reading functions (mock implementations)
    float (*read_distance_sensor)(void);
    float (*read_temperature_sensor)(void);
    
    // Vehicle state functions (for automotive simulation)
    bool (*is_vehicle_idle)(void);
    uint32_t (*get_vehicle_speed)(void);
    bool (*is_ignition_on)(void);
    
    // Storage functions for module data
    bool (*save_module_data)(const char* key, const void* data, size_t size);
    bool (*load_module_data)(const char* key, void* data, size_t max_size);
    
    // Network functions
    bool (*is_wifi_connected)(void);
    const char* (*get_device_id)(void);
    
    // Module management
    const char* (*get_module_version)(const char* module_name);
    
} SystemAPI;

// Standard module interface - every module must implement these
typedef struct {
    // Module identification
    const char* module_name;
    const char* module_version;
    
    // Lifecycle functions
    bool (*initialize)(SystemAPI* api);
    void (*deinitialize)(void);
    void (*update)(void);  // Called in main loop
    
    // Module-specific functions (cast to appropriate type)
    void* module_functions;
    
} ModuleInterface;

// Speed governor specific interface
typedef struct {
    int (*get_speed_limit)(int current_speed, int road_conditions);
    void (*set_speed_limit_override)(int new_limit);
    bool (*is_speed_limiting_active)(void);
} SpeedGovernorInterface;

// Distance sensor specific interface  
typedef struct {
    float (*get_distance)(void);
    void (*calibrate_sensor)(void);
    bool (*is_object_detected)(float threshold);
} DistanceSensorInterface;

#ifdef __cplusplus
}
#endif

#endif // SYSTEM_API_H 