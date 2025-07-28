#include "../../esp32_loader_firmware/include/system_api.h"
#include <stddef.h>

// Module metadata - Version 1.1.0
#define MODULE_NAME "distance_sensor"
#define MODULE_VERSION "1.0.1"  // Version 1.1.0 - outputs in millimeters

// Global system API pointer
static SystemAPI* sys_api = NULL;

// Distance sensor state
static float last_distance_reading = 500.0f;  // Default distance in mm
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
    last_distance_reading = 500.0f;  // 50cm in mm
    sensor_calibrated = false;
    calibration_offset = 0.0f;
    
    sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                       "Distance sensor initialized v%s - outputs in MILLIMETERS", 
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
    
    // Read raw distance from system API (mock sensor returns cm)
    float raw_distance_cm = sys_api->read_distance_sensor();
    
    // Convert to millimeters and apply calibration offset
    // v1.1.0: Convert cm to mm and apply offset
    last_distance_reading = (raw_distance_cm * 10.0f) + calibration_offset;
    
    // Ensure reasonable bounds (in mm)
    if (last_distance_reading < 0.0f) {
        last_distance_reading = 0.0f;
    }
    if (last_distance_reading > 4000.0f) {  // 4000mm = 4 meter max range
        last_distance_reading = 4000.0f;
    }
    
    // Log distance reading periodically (every ~10 seconds)
    static uint32_t last_log_time = 0;
    uint32_t current_time = sys_api->get_millis();
    if (current_time - last_log_time > 10000) {
        sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                           "Distance: %.0f mm (v1.1.0 - UPDATED UNITS!)", 
                           last_distance_reading);
        last_log_time = current_time;
    }
}

// Distance sensor interface implementation
static float get_distance(void) {
    // v1.1.0: Return distance in millimeters
    return last_distance_reading;
}

static void calibrate_sensor(void) {
    if (!sys_api) {
        return;
    }
    
    sys_api->log_message(LOG_INFO, MODULE_NAME, "Calibrating distance sensor...");
    
    // Simple calibration: assume current reading should be 300mm (30cm)
    float raw_reading_cm = sys_api->read_distance_sensor();
    float raw_reading_mm = raw_reading_cm * 10.0f;
    calibration_offset = 300.0f - raw_reading_mm;
    sensor_calibrated = true;
    
    sys_api->log_printf(LOG_INFO, MODULE_NAME, 
                       "Calibration complete. Offset: %.2f mm", 
                       calibration_offset);
}

static bool is_object_detected(float threshold) {
    // Return true if current distance is less than threshold (in mm)
    return (last_distance_reading < threshold);
} 