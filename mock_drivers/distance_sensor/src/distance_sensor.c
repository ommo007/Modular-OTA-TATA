#include "../../esp32_loader_firmware/include/system_api.h"
#include <stddef.h>

// Module metadata - Version 1.0.0
#define MODULE_NAME "distance_sensor"
#define MODULE_VERSION "1.0.0"  // Version 1.0.0 - outputs in centimeters

// Global system API pointer
static SystemAPI* sys_api = NULL;

// Distance sensor state
static float last_distance_reading = 50.0f;  // Default distance in cm
static bool sensor_calibrated = false;
static float calibration_offset = 0.0f;

// Function prototypes for module interface
static bool initialize_module(SystemAPI* api);
static void deinitialize_module(void);
static void update_module(void);
static float get_distance(void);
static void calibrate_sensor(void);
static bool is_object_detected(float threshold);

// Distance sensor interface implementation
static DistanceSensorInterface distance_interface = {
    .get_distance = get_distance,
    .calibrate_sensor = calibrate_sensor,
    .is_object_detected = is_object_detected
};

// Main module interface
static ModuleInterface module_interface = {
    .module_name = MODULE_NAME,
    .module_version = MODULE_VERSION,
    .initialize = initialize_module,
    .deinitialize = deinitialize_module,
    .update = update_module,
    .module_functions = &distance_interface
};

// Entry point - this function must be exported for dynamic loading
ModuleInterface* get_module_interface(void) {
    return &module_interface;
}

// Module lifecycle functions
static bool initialize_module(SystemAPI* api) {
    if (!api) {
        return false;
    }
    
    sys_api = api;
    
    // Initialize distance sensor state
    last_distance_reading = 50.0f;
    sensor_calibrated = false;
    calibration_offset = 0.0f;
    
    sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                       "Distance sensor initialized v%s - outputs in CENTIMETERS", 
                       MODULE_VERSION);
    
    return true;
}

static void deinitialize_module(void) {
    if (sys_api) {
        sys_api->log_message(LOG_INFO, MODULE_NAME, "Distance sensor deinitialized");
        sys_api = NULL;
    }
}

static void update_module(void) {
    if (!sys_api) {
        return;
    }
    
    // Read raw distance from system API (mock sensor)
    float raw_distance = sys_api->read_distance_sensor();
    
    // Apply calibration offset and convert to centimeters
    // v1.0.0: Raw reading is already in cm, just apply offset
    last_distance_reading = raw_distance + calibration_offset;
    
    // Ensure reasonable bounds
    if (last_distance_reading < 0.0f) {
        last_distance_reading = 0.0f;
    }
    if (last_distance_reading > 400.0f) {  // 4 meter max range
        last_distance_reading = 400.0f;
    }
    
    // Log distance reading periodically (every ~10 seconds)
    static uint32_t last_log_time = 0;
    uint32_t current_time = sys_api->get_millis();
    if (current_time - last_log_time > 10000) {
        sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                           "Distance: %.1f cm (v1.0.0)", 
                           last_distance_reading);
        last_log_time = current_time;
    }
}

// Distance sensor interface implementation
static float get_distance(void) {
    // v1.0.0: Return distance in centimeters
    return last_distance_reading;
}

static void calibrate_sensor(void) {
    if (!sys_api) {
        return;
    }
    
    sys_api->log_message(LOG_INFO, MODULE_NAME, "Calibrating distance sensor...");
    
    // Simple calibration: assume current reading should be 30cm
    float raw_reading = sys_api->read_distance_sensor();
    calibration_offset = 30.0f - raw_reading;
    sensor_calibrated = true;
    
    sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                       "Calibration complete. Offset: %.2f cm", 
                       calibration_offset);
}

static bool is_object_detected(float threshold) {
    // Return true if current distance is less than threshold
    return (last_distance_reading < threshold);
} 