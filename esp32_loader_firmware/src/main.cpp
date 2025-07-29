#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <esp_system.h>
#include <esp_heap_caps.h>

#include "system_api.h"
#include "ota_updater.h"
#include "module_loader.h"
#include "config.h"  // Include externalized configuration - MISSING SEMICOLON FIXED

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

// LED feedback system - Visual status indicators
// 💛 Yellow LED: Slow blink = Update available, Fast blink = Downloading
// 💚 Green LED: Solid = Update success (5 seconds)
// ❤  Red LED: Solid = Update failure (8 seconds)
unsigned long last_led_blink_time = 0;
bool led_blink_state = false;
const unsigned long SLOW_BLINK_INTERVAL = 1000;    // 1 second for slow blink
const unsigned long FAST_BLINK_INTERVAL = 200;     // 200ms for fast blink

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
    Serial.println("\n=== ESP32 Modular OTA System ===");
    Serial.println("🚀 Starting secure modular firmware platform...");
    
    // Initialize components
    setup_gpio();
    setup_filesystem();
    setup_wifi();
    setup_system_api();
    
    // Initialize OTA updater
    Serial.println("🔐 Initializing secure OTA updater...");
    if (!ota_updater_init(&ota_updater, SERVER_URL, DEVICE_ID, SIGNING_PUBLIC_KEY)) {
        Serial.println("❌ OTA updater initialization failed!");
        current_state = STATE_ERROR;
        return;
    }
    Serial.println("✅ OTA updater ready");
    
    // Initialize module loader
    Serial.println("📦 Initializing dynamic module loader...");
    if (!module_loader_init(&module_loader, &system_api)) {
        Serial.println("❌ Module loader initialization failed!");
        current_state = STATE_ERROR;
        return;
    }
    Serial.println("✅ Module loader ready");
    
    // Load initial modules
    Serial.println("\n🔧 Loading initial automotive modules...");
    
    // Load speed governor module
    if (module_loader_load_module(&module_loader, "speed_governor") == MODULE_LOAD_SUCCESS) {
        LoadedModule* module = module_loader_get_module(&module_loader, "speed_governor");
        if (module) {
            ota_updater_set_module_version(&ota_updater, "speed_governor", module->version);
            Serial.printf("✅ Speed Governor v%s loaded and tracked\n", module->version);
        }
    } else {
        Serial.println("⚠  Speed governor module not found (will be downloaded if available)");
    }
    
    // Load distance sensor module
    if (module_loader_load_module(&module_loader, "distance_sensor") == MODULE_LOAD_SUCCESS) {
        LoadedModule* module = module_loader_get_module(&module_loader, "distance_sensor");
        if (module) {
            ota_updater_set_module_version(&ota_updater, "distance_sensor", module->version);
            Serial.printf("✅ Distance Sensor v%s loaded and tracked\n", module->version);
        }
    } else {
        Serial.println("⚠  Distance sensor module not found (will be downloaded if available)");
    }
    
    current_state = STATE_NORMAL_OPERATION;
    state_change_time = millis();
    
    Serial.println("\n🎯 System initialization complete - Ready for OTA updates!");
    Serial.println("💡 Press button to simulate vehicle idle for updates");
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
    Serial.println("📶 Connecting to WiFi network...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("   Attempting connection");
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.println("✅ WiFi connected successfully!");
        Serial.printf("   📍 IP Address: %s\n", WiFi.localIP().toString().c_str());
        Serial.println("   🌐 Ready for OTA server communication");
    } else {
        Serial.println("\n❌ WiFi connection failed!");
        Serial.println("   ⚠  OTA updates will not be available");
    }
}

void setup_filesystem() {
    Serial.println("💾 Initializing filesystem...");
    if (!LittleFS.begin(true)) {
        Serial.println("❌ LittleFS mount failed!");
        return;
    }
    Serial.println("✅ LittleFS mounted - Ready for module storage");
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
            Serial.println("\n🔍 Checking OTA server for module updates...");
            {
                update_status_t status = ota_updater_check_for_updates(&ota_updater);
                if (status == UPDATE_SUCCESS && ota_updater_has_pending_updates(&ota_updater)) {
                    Serial.println("🆕 New updates discovered!");
                    Serial.println("   💛 Yellow LED: Blinking slowly - waiting for vehicle idle");
                    current_state = STATE_UPDATE_AVAILABLE;
                    // Initialize blinking state
                    led_blink_state = true;
                    last_led_blink_time = current_time;
                    set_led_state_impl(LED_YELLOW, led_blink_state);
                } else {
                    Serial.println("✅ All modules up to date");
                    current_state = STATE_NORMAL_OPERATION;
                }
                last_update_check = current_time;
            }
            break;
            
        case STATE_UPDATE_AVAILABLE:
            // Slow blink yellow LED to indicate update available
            if (current_time - last_led_blink_time > SLOW_BLINK_INTERVAL) {
                led_blink_state = !led_blink_state;
                set_led_state_impl(LED_YELLOW, led_blink_state);
                last_led_blink_time = current_time;
            }
            
            // Wait for vehicle idle state
            if (vehicle_idle) {
                Serial.println("🚗 Vehicle idle detected - safe to update!");
                Serial.println("⬇  Starting secure download process...");
                current_state = STATE_DOWNLOADING_UPDATE;
                set_led_state_impl(LED_YELLOW, false); // Turn off blinking
                last_led_blink_time = current_time; // Reset blink timer
            }
            break;
            
        case STATE_DOWNLOADING_UPDATE:
            // Fast blink yellow LED during download
            if (current_time - last_led_blink_time > FAST_BLINK_INTERVAL) {
                led_blink_state = !led_blink_state;
                set_led_state_impl(LED_YELLOW, led_blink_state);
                last_led_blink_time = current_time;
            }
            
            {
                // Process the first pending module update
                if (ota_updater.pending_update_count > 0) {
                    const char* module_name = ota_updater.pending_updates[0].module_name;
                    update_status_t status = ota_updater_download_and_apply_update(&ota_updater, module_name);
                    
                    if (status == UPDATE_SUCCESS) {
                        Serial.println("🎉 Module update completed successfully!");
                        Serial.println("   💚 Green LED: Update success");
                        
                        // Turn off blinking yellow LED and turn on solid green
                        set_led_state_impl(LED_YELLOW, false);
                        set_led_state_impl(LED_GREEN, true);
                        
                        // Reload the module with new version
                        Serial.println("🔄 Reloading updated module...");
                        if (module_loader_reload_module(&module_loader, module_name) == MODULE_LOAD_SUCCESS) {
                            LoadedModule* module = module_loader_get_module(&module_loader, module_name);
                            if (module) {
                                ota_updater_set_module_version(&ota_updater, module_name, module->version);
                                Serial.printf("✅ %s v%s now active and tracked\n", module_name, module->version);
                            }
                        }
                        current_state = STATE_UPDATE_SUCCESS;
                        success_state_start_time = current_time;
                    } else {
                        Serial.println("❌ Module update failed!");
                        Serial.println("   ❤  Red LED: Update failure");
                        
                        // Turn off blinking yellow LED and turn on solid red
                        set_led_state_impl(LED_YELLOW, false);
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
                Serial.println("🟢 Update celebration complete - resuming normal operation");
                set_led_state_impl(LED_GREEN, false);
                current_state = STATE_NORMAL_OPERATION;
                state_change_time = current_time;
            }
            // Keep green LED on during this state
            break;
            
        case STATE_UPDATE_FAILURE:
            // Show failure LED for 8 seconds, then return to normal operation
            if (current_time - failure_state_start_time > 8000) {
                Serial.println("🔴 Failure notification complete - resuming normal operation");
                Serial.println("   💡 Previous module version still active and safe");
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
        
        // Demonstrate speed governor functionality
        LoadedModule* speed_module = module_loader_get_module(&module_loader, "speed_governor");
        if (speed_module && speed_module->is_active) {
            SpeedGovernorInterface* speed_interface = (SpeedGovernorInterface*)speed_module->interface->module_functions;
            if (speed_interface && speed_interface->get_speed_limit) {
                // Test different road conditions
                int normal_speed_limit = speed_interface->get_speed_limit(60, 0);
                int highway_speed_limit = speed_interface->get_speed_limit(60, 1);
                
                Serial.printf("🚗 Speed Governor v%s: Normal %d km/h | Highway %d km/h\n", 
                             speed_module->version, normal_speed_limit, highway_speed_limit);
                
                // Highlight the fix in v1.1.0
                if (strcmp(speed_module->version, "1.1.0") == 0) {
                    Serial.println("   ✨ Highway speed limit bug fixed in this version!");
                }
            }
        }
        
        // Demonstrate distance sensor functionality
        LoadedModule* distance_module = module_loader_get_module(&module_loader, "distance_sensor");
        if (distance_module && distance_module->is_active) {
            DistanceSensorInterface* distance_interface = (DistanceSensorInterface*)distance_module->interface->module_functions;
            if (distance_interface && distance_interface->get_distance) {
                float distance = distance_interface->get_distance();
                
                // Show different units based on version
                if (strcmp(distance_module->version, "1.0.0") == 0) {
                    Serial.printf("📏 Distance Sensor v%s: %.1f cm\n", distance_module->version, distance);
                    if (distance_interface->is_object_detected && distance_interface->is_object_detected(30.0f)) {
                        Serial.println("   ⚠  Object detected within 30cm!");
                    }
                } else {
                    Serial.printf("📏 Distance Sensor v%s: %.0f mm (improved precision!)\n", distance_module->version, distance);
                    if (distance_interface->is_object_detected && distance_interface->is_object_detected(300.0f)) {
                        Serial.println("   ⚠  Object detected within 300mm!");
                    }
                    if (strcmp(distance_module->version, "1.1.0") == 0) {
                        Serial.println("   ✨ Enhanced precision with millimeter units!");
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