#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <esp_system.h>
#include <esp_heap_caps.h>

#include "system_api.h"
#include "ota_updater.h"
#include "module_loader.h"
#include "config.h"  // Include externalized configuration

// GPIO Pin definitions
#define LED_YELLOW_PIN 2
#define LED_GREEN_PIN 4
#define LED_RED_PIN 5
#define BUTTON_PIN 0
#define DISTANCE_SENSOR_TRIGGER_PIN 18
#define DISTANCE_SENSOR_ECHO_PIN 19

// System state
enum SystemState {
    STATE_INIT,
    STATE_NORMAL_OPERATION,
    STATE_CHECK_UPDATES,
    STATE_UPDATE_AVAILABLE,
    STATE_WAIT_FOR_IDLE,
    STATE_DOWNLOADING_UPDATE,
    STATE_APPLYING_UPDATE,
    STATE_UPDATE_SUCCESS,
    STATE_UPDATE_FAILURE,
    STATE_ERROR
};

// Global variables
SystemState current_state = STATE_INIT;
unsigned long last_update_check = 0;
unsigned long last_sensor_read = 0;
unsigned long state_change_time = 0;
unsigned long success_state_start_time = 0;
unsigned long failure_state_start_time = 0;
const unsigned long UPDATE_CHECK_INTERVAL = 30000; // 30 seconds
const unsigned long SENSOR_READ_INTERVAL = 1000;   // 1 second

// System components
SystemAPI system_api;
OTAUpdater ota_updater;
ModuleLoader module_loader;

// Mock sensor values
float mock_distance = 50.0;
float mock_temperature = 25.0;
bool button_pressed = false;
bool vehicle_idle = false;

// Function prototypes
void setup_gpio();
void setup_wifi();
void setup_filesystem();
void setup_system_api();
void handle_state_machine();
void update_sensors();
void log_message_impl(log_level_t level, const char* tag, const char* message);
void log_printf_impl(log_level_t level, const char* tag, const char* format, ...);
uint32_t get_millis_impl();
uint64_t get_micros_impl();
void set_led_state_impl(led_type_t led, bool is_on);
bool get_button_state_impl();
float read_distance_sensor_impl();
float read_temperature_sensor_impl();
bool is_vehicle_idle_impl();
uint32_t get_vehicle_speed_impl();
bool is_ignition_on_impl();
bool save_module_data_impl(const char* key, const void* data, size_t size);
bool load_module_data_impl(const char* key, void* data, size_t max_size);
bool is_wifi_connected_impl();
const char* get_device_id_impl();
const char* get_module_version_impl(const char* module_name);

void setup() {
    Serial.begin(115200);
    Serial.println("ESP32 Modular OTA System Starting...");
    
    // Initialize components
    setup_gpio();
    setup_filesystem();
    setup_wifi();
    setup_system_api();
    
    // Initialize OTA updater
    if (!ota_updater_init(&ota_updater, SERVER_URL, DEVICE_ID, SIGNING_PUBLIC_KEY)) {
        Serial.println("Failed to initialize OTA updater");
        current_state = STATE_ERROR;
        return;
    }
    
    // Initialize module loader
    if (!module_loader_init(&module_loader, &system_api)) {
        Serial.println("Failed to initialize module loader");
        current_state = STATE_ERROR;
        return;
    }
    
    // Load initial modules
    Serial.println("Loading initial modules...");
    
    // Load speed governor module
    if (module_loader_load_module(&module_loader, "speed_governor") == MODULE_LOAD_SUCCESS) {
        Serial.println("Speed governor module loaded successfully");
        // Track the module version in OTA updater
        LoadedModule* module = module_loader_get_module(&module_loader, "speed_governor");
        if (module) {
            ota_updater_set_module_version(&ota_updater, "speed_governor", module->version);
            Serial.printf("Tracking speed_governor version: %s\n", module->version);
        }
    } else {
        Serial.println("Failed to load speed governor module");
    }
    
    // Load distance sensor module
    if (module_loader_load_module(&module_loader, "distance_sensor") == MODULE_LOAD_SUCCESS) {
        Serial.println("Distance sensor module loaded successfully");
        // Track the module version in OTA updater
        LoadedModule* module = module_loader_get_module(&module_loader, "distance_sensor");
        if (module) {
            ota_updater_set_module_version(&ota_updater, "distance_sensor", module->version);
            Serial.printf("Tracking distance_sensor version: %s\n", module->version);
        }
    } else {
        Serial.println("Failed to load distance sensor module");
    }
    
    current_state = STATE_NORMAL_OPERATION;
    state_change_time = millis();
    
    Serial.println("System initialization complete");
}

void loop() {
    update_sensors();
    handle_state_machine();
    
    // Update all loaded modules
    module_loader_update_all_modules(&module_loader);
    
    // Small delay to prevent watchdog issues
    delay(10);
}

void setup_gpio() {
    pinMode(LED_YELLOW_PIN, OUTPUT);
    pinMode(LED_GREEN_PIN, OUTPUT);
    pinMode(LED_RED_PIN, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(DISTANCE_SENSOR_TRIGGER_PIN, OUTPUT);
    pinMode(DISTANCE_SENSOR_ECHO_PIN, INPUT);
    
    // Turn off all LEDs initially
    digitalWrite(LED_YELLOW_PIN, LOW);
    digitalWrite(LED_GREEN_PIN, LOW);
    digitalWrite(LED_RED_PIN, LOW);
}

void setup_wifi() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.println("WiFi connected!");
        Serial.print("IP address: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi connection failed!");
    }
}

void setup_filesystem() {
    if (!LittleFS.begin(true)) {
        Serial.println("LittleFS Mount Failed");
        return;
    }
    Serial.println("LittleFS mounted successfully");
}

void setup_system_api() {
    system_api.log_message = log_message_impl;
    system_api.log_printf = log_printf_impl;
    system_api.get_millis = get_millis_impl;
    system_api.get_micros = get_micros_impl;
    system_api.set_led_state = set_led_state_impl;
    system_api.get_button_state = get_button_state_impl;
    system_api.read_distance_sensor = read_distance_sensor_impl;
    system_api.read_temperature_sensor = read_temperature_sensor_impl;
    system_api.is_vehicle_idle = is_vehicle_idle_impl;
    system_api.get_vehicle_speed = get_vehicle_speed_impl;
    system_api.is_ignition_on = is_ignition_on_impl;
    system_api.save_module_data = save_module_data_impl;
    system_api.load_module_data = load_module_data_impl;
    system_api.is_wifi_connected = is_wifi_connected_impl;
    system_api.get_device_id = get_device_id_impl;
    system_api.get_module_version = get_module_version_impl;
}

void handle_state_machine() {
    unsigned long current_time = millis();
    
    switch (current_state) {
        case STATE_NORMAL_OPERATION:
            // Check for updates periodically
            if (current_time - last_update_check > UPDATE_CHECK_INTERVAL) {
                current_state = STATE_CHECK_UPDATES;
                state_change_time = current_time;
            }
            break;
            
        case STATE_CHECK_UPDATES:
            Serial.println("Checking for updates...");
            {
                update_status_t status = ota_updater_check_for_updates(&ota_updater);
                if (status == UPDATE_SUCCESS && ota_updater_has_pending_updates(&ota_updater)) {
                    Serial.println("Updates available!");
                    current_state = STATE_UPDATE_AVAILABLE;
                    set_led_state_impl(LED_YELLOW, true);
                } else {
                    Serial.println("No updates available");
                    current_state = STATE_NORMAL_OPERATION;
                }
                last_update_check = current_time;
            }
            break;
            
        case STATE_UPDATE_AVAILABLE:
            // Notify user and wait for idle state
            if (vehicle_idle) {
                Serial.println("Vehicle is idle, proceeding with update");
                current_state = STATE_DOWNLOADING_UPDATE;
                set_led_state_impl(LED_YELLOW, false);
            }
            break;
            
        case STATE_DOWNLOADING_UPDATE:
            Serial.println("Downloading and applying update...");
            {
                // For demo, update the first pending module
                if (ota_updater.pending_update_count > 0) {
                    const char* module_name = ota_updater.pending_updates[0].module_name;
                    update_status_t status = ota_updater_download_and_apply_update(&ota_updater, module_name);
                    
                    if (status == UPDATE_SUCCESS) {
                        Serial.printf("Update applied successfully for %s\n", module_name);
                        set_led_state_impl(LED_GREEN, true);
                        // Reload the module
                        if (module_loader_reload_module(&module_loader, module_name) == MODULE_LOAD_SUCCESS) {
                            // Update the tracked version
                            LoadedModule* module = module_loader_get_module(&module_loader, module_name);
                            if (module) {
                                ota_updater_set_module_version(&ota_updater, module_name, module->version);
                                Serial.printf("Updated tracking for %s to version: %s\n", module_name, module->version);
                            }
                        }
                        current_state = STATE_UPDATE_SUCCESS;
                        success_state_start_time = current_time;
                    } else {
                        Serial.printf("Update failed for %s\n", module_name);
                        set_led_state_impl(LED_RED, true);
                        current_state = STATE_UPDATE_FAILURE;
                        failure_state_start_time = current_time;
                    }
                }
                ota_updater_clear_pending_updates(&ota_updater);
            }
            break;
            
        case STATE_UPDATE_SUCCESS:
            // Show success LED for 5 seconds, then return to normal operation
            if (current_time - success_state_start_time > 5000) {
                Serial.println("Update success display complete, returning to normal operation");
                set_led_state_impl(LED_GREEN, false);
                current_state = STATE_NORMAL_OPERATION;
                state_change_time = current_time;
            }
            // Keep green LED on during this state
            break;
            
        case STATE_UPDATE_FAILURE:
            // Show failure LED for 8 seconds, then return to normal operation
            if (current_time - failure_state_start_time > 8000) {
                Serial.println("Update failure display complete, returning to normal operation");
                set_led_state_impl(LED_RED, false);
                current_state = STATE_NORMAL_OPERATION;
                state_change_time = current_time;
            }
            // Keep red LED on during this state
            break;
            
        case STATE_ERROR:
            set_led_state_impl(LED_RED, true);
            delay(5000);
            ESP.restart();
            break;
    }
}

void update_sensors() {
    unsigned long current_time = millis();
    
    if (current_time - last_sensor_read > SENSOR_READ_INTERVAL) {
        // Update button state
        button_pressed = !digitalRead(BUTTON_PIN);
        vehicle_idle = button_pressed; // Simulate vehicle idle when button is pressed
        
        // Update mock distance sensor (simulate varying distance)
        mock_distance = 50.0 + 10.0 * sin(current_time / 5000.0);
        
        // Update mock temperature
        mock_temperature = 25.0 + 5.0 * cos(current_time / 8000.0);
        
        last_sensor_read = current_time;
        
        // Test loaded modules - showcase both normal and highway conditions
        LoadedModule* speed_module = module_loader_get_module(&module_loader, "speed_governor");
        if (speed_module && speed_module->is_active) {
            // Call module function if available
            SpeedGovernorInterface* speed_interface = (SpeedGovernorInterface*)speed_module->interface->module_functions;
            if (speed_interface && speed_interface->get_speed_limit) {
                // Test normal road conditions
                int normal_speed_limit = speed_interface->get_speed_limit(60, 0); // 60 km/h, normal conditions
                Serial.printf("Normal road speed limit: %d km/h\n", normal_speed_limit);
                
                // Test highway conditions to showcase the fix
                int highway_speed_limit = speed_interface->get_speed_limit(60, 1); // 60 km/h, highway conditions
                Serial.printf("Highway speed limit: %d km/h (fixed in v1.1.0)\n", highway_speed_limit);
            }
        }
        
        // Test distance sensor module
        LoadedModule* distance_module = module_loader_get_module(&module_loader, "distance_sensor");
        if (distance_module && distance_module->is_active) {
            DistanceSensorInterface* distance_interface = (DistanceSensorInterface*)distance_module->interface->module_functions;
            if (distance_interface && distance_interface->get_distance) {
                float distance = distance_interface->get_distance();
                
                // Display units based on version to show the difference
                if (strcmp(distance_module->version, "1.0.0") == 0) {
                    Serial.printf("Distance reading: %.1f cm (from v%s)\n", distance, distance_module->version);
                    // v1.0.0 uses cm, so check for 30cm threshold
                    if (distance_interface->is_object_detected && distance_interface->is_object_detected(30.0f)) {
                        Serial.println("Object detected within 30cm!");
                    }
                } else {
                    Serial.printf("Distance reading: %.0f mm (from v%s - NEW UNITS!)\n", distance, distance_module->version);
                    // v1.1.0 uses mm, so check for 300mm threshold (same as 30cm)
                    if (distance_interface->is_object_detected && distance_interface->is_object_detected(300.0f)) {
                        Serial.println("Object detected within 300mm (30cm)!");
                    }
                }
            }
        }
    }
}

// System API implementations
void log_message_impl(log_level_t level, const char* tag, const char* message) {
    const char* level_str[] = {"DEBUG", "INFO", "WARN", "ERROR"};
    Serial.printf("[%s] %s: %s\n", level_str[level], tag, message);
}

void log_printf_impl(log_level_t level, const char* tag, const char* format, ...) {
    char buffer[256];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    log_message_impl(level, tag, buffer);
}

uint32_t get_millis_impl() {
    return millis();
}

uint64_t get_micros_impl() {
    return micros();
}

void set_led_state_impl(led_type_t led, bool is_on) {
    int pin = -1;
    switch (led) {
        case LED_YELLOW: pin = LED_YELLOW_PIN; break;
        case LED_GREEN: pin = LED_GREEN_PIN; break;
        case LED_RED: pin = LED_RED_PIN; break;
    }
    if (pin >= 0) {
        digitalWrite(pin, is_on ? HIGH : LOW);
    }
}

bool get_button_state_impl() {
    return button_pressed;
}

float read_distance_sensor_impl() {
    return mock_distance;
}

float read_temperature_sensor_impl() {
    return mock_temperature;
}

bool is_vehicle_idle_impl() {
    return vehicle_idle;
}

uint32_t get_vehicle_speed_impl() {
    return vehicle_idle ? 0 : 65; // 0 when idle, 65 km/h when moving
}

bool is_ignition_on_impl() {
    return true; // Always on for demo
}

bool save_module_data_impl(const char* key, const void* data, size_t size) {
    String filename = "/module_data_" + String(key);
    File file = LittleFS.open(filename, "w");
    if (file) {
        size_t written = file.write((uint8_t*)data, size);
        file.close();
        return written == size;
    }
    return false;
}

bool load_module_data_impl(const char* key, void* data, size_t max_size) {
    String filename = "/module_data_" + String(key);
    File file = LittleFS.open(filename, "r");
    if (file) {
        size_t size = file.size();
        if (size <= max_size) {
            size_t read_bytes = file.readBytes((char*)data, size);
            file.close();
            return read_bytes == size;
        }
        file.close();
    }
    return false;
}

bool is_wifi_connected_impl() {
    return WiFi.status() == WL_CONNECTED;
}

const char* get_device_id_impl() {
    return DEVICE_ID;
}

const char* get_module_version_impl(const char* module_name) {
    LoadedModule* module = module_loader_get_module(&module_loader, module_name);
    return module ? module->version : "unknown";
} 
} 