# Potential Problems and Solutions

This document outlines the key challenges you might face when implementing the modular OTA system and provides proven solutions.

## 🔧 Technical Problems

### 1. Memory Management Issues

**Problem**: ESP32 has limited RAM (~320KB total, ~240KB usable) and Flash memory.

**Symptoms**:
- Module fails to load with "Memory allocation failed"
- ESP32 crashes or reboots unexpectedly
- Heap fragmentation errors

**Solutions**:
```cpp
// Use PSRAM if available
#define BOARD_HAS_PSRAM
#pragma GCC optimize ("Os")  // Optimize for size

// Allocate executable memory from IRAM
void* heap_caps_malloc(size_t size, uint32_t caps) {
    return heap_caps_malloc(size, MALLOC_CAP_EXEC | MALLOC_CAP_32BIT);
}

// Implement memory pooling
#define MAX_MODULE_SIZE 32768  // 32KB limit per module
static uint8_t module_memory_pool[MAX_MODULE_SIZE];
```

**Prevention**:
- Keep modules under 32KB each
- Use static allocation where possible
- Monitor heap usage: `Serial.printf("Free heap: %d\n", ESP.getFreeHeap());`

### 2. Dynamic Loading Complexity

**Problem**: Loading arbitrary binary code at runtime is extremely challenging on microcontrollers.

**Current Limitation**: Our implementation uses a simplified mock system. Real dynamic loading requires:

**Complete Solution** (for production):
```cpp
// ELF loader implementation
#include "esp_elf.h"

typedef struct {
    Elf32_Ehdr header;
    Elf32_Phdr* program_headers;
    Elf32_Shdr* section_headers;
    void* loaded_sections[MAX_SECTIONS];
} ELFModule;

bool load_elf_module(const void* elf_data, size_t size, ELFModule* module) {
    // 1. Validate ELF header
    if (!validate_elf_header(elf_data)) return false;
    
    // 2. Load program headers
    if (!load_program_headers(elf_data, module)) return false;
    
    // 3. Allocate memory for each section
    if (!allocate_sections(module)) return false;
    
    // 4. Apply relocations
    if (!apply_relocations(module)) return false;
    
    // 5. Resolve symbols
    if (!resolve_symbols(module)) return false;
    
    return true;
}
```

**Alternative Approaches**:
1. **Interpreted Scripts**: Use Lua or JavaScript interpreters
2. **Bytecode VM**: Custom virtual machine for module execution
3. **Fixed Interfaces**: Pre-compiled modules with standard ABIs

### 3. ABI Compatibility Issues

**Problem**: Binary modules compiled separately may have incompatible calling conventions.

**Symptoms**:
- Function calls crash the system
- Wrong parameters passed to functions
- Stack corruption

**Solutions**:
```cpp
// Use C ABI explicitly
extern "C" {
    typedef struct {
        const char* (*get_name)(void);
        uint32_t (*get_version)(void);
        bool (*initialize)(SystemAPI* api);
    } __attribute__((packed)) ModuleABI;
}

// Enforce calling conventions
#define MODULE_EXPORT __attribute__((visibility("default")))
#define MODULE_CALL __attribute__((stdcall))

MODULE_EXPORT MODULE_CALL ModuleABI* get_module_abi(void);
```

**Compilation Flags**:
```makefile
CFLAGS += -fPIC -nostdlib -nostartfiles -nodefaultlibs
CFLAGS += -mabi=ilp32 -march=rv32imc  # For consistent ABI
LDFLAGS += -shared -Bsymbolic
```

### 4. Network Reliability Issues

**Problem**: OTA updates can fail due to network interruptions, causing partially downloaded files.

**Symptoms**:
- Downloads timeout or fail
- Corrupted binary files
- Hash verification failures

**Solutions**:
```cpp
// Resumable download implementation
typedef struct {
    char url[256];
    char local_path[64];
    size_t total_size;
    size_t downloaded_size;
    uint32_t retry_count;
    bool is_resumable;
} DownloadContext;

bool download_with_resume(DownloadContext* ctx) {
    FILE* file = fopen(ctx->local_path, "ab");  // Append mode
    
    // Set HTTP Range header for resuming
    char range_header[64];
    snprintf(range_header, sizeof(range_header), 
            "Range: bytes=%zu-", ctx->downloaded_size);
    
    HTTPClient http;
    http.begin(ctx->url);
    http.addHeader("Range", range_header);
    
    int httpCode = http.GET();
    if (httpCode == HTTP_CODE_PARTIAL_CONTENT || httpCode == HTTP_CODE_OK) {
        // Continue download from where we left off
        return stream_to_file(http.getStreamPtr(), file, ctx);
    }
    
    return false;
}

// Retry mechanism with exponential backoff
bool download_with_retry(const char* url, const char* path, int max_retries) {
    for (int attempt = 0; attempt < max_retries; attempt++) {
        if (download_file(url, path)) {
            return true;
        }
        
        // Exponential backoff: 1s, 2s, 4s, 8s...
        int delay_ms = (1 << attempt) * 1000;
        delay(min(delay_ms, 30000));  // Max 30 seconds
    }
    return false;
}
```

### 5. Security Vulnerabilities

**Problem**: Loading unsigned code is extremely dangerous and can lead to system compromise.

**Current Risk**: Our demo uses only SHA256 for integrity, not authenticity.

**Production Security**:
```cpp
#include "mbedtls/rsa.h"
#include "mbedtls/pk.h"

// Digital signature verification
bool verify_module_signature(const uint8_t* module_data, size_t data_size,
                           const uint8_t* signature, size_t sig_size) {
    mbedtls_pk_context pk;
    mbedtls_pk_init(&pk);
    
    // Load public key (embedded in firmware)
    if (mbedtls_pk_parse_public_key(&pk, public_key_pem, 
                                   strlen(public_key_pem) + 1) != 0) {
        return false;
    }
    
    // Verify signature
    uint8_t hash[32];
    mbedtls_sha256(module_data, data_size, hash, 0);
    
    int ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256, hash, 32, 
                               signature, sig_size);
    
    mbedtls_pk_free(&pk);
    return ret == 0;
}

// Secure boot implementation
bool verify_system_integrity(void) {
    // Verify bootloader signature
    // Verify firmware signature
    // Check hardware security features
    return true;
}
```

### 6. Update Atomicity

**Problem**: System crashes during updates can leave the device in an unusable state.

**Solutions**:
```cpp
// A/B partition scheme
typedef enum {
    PARTITION_A = 0,
    PARTITION_B = 1
} partition_t;

typedef struct {
    partition_t active_partition;
    partition_t update_partition;
    uint32_t rollback_timeout_ms;
    bool update_in_progress;
} UpdateManager;

bool atomic_update_module(const char* module_name, const void* new_data, size_t size) {
    UpdateManager* mgr = get_update_manager();
    
    // 1. Write to inactive partition
    partition_t target = (mgr->active_partition == PARTITION_A) ? PARTITION_B : PARTITION_A;
    if (!write_to_partition(target, module_name, new_data, size)) {
        return false;
    }
    
    // 2. Verify integrity
    if (!verify_partition_integrity(target, module_name)) {
        erase_partition(target, module_name);
        return false;
    }
    
    // 3. Set update flag (atomic operation)
    mgr->update_in_progress = true;
    commit_update_state();
    
    // 4. Switch partition (this triggers reboot)
    mgr->active_partition = target;
    commit_partition_switch();
    
    // System reboots here and validates new module
    return true;
}

// Rollback mechanism
void check_update_success(void) {
    UpdateManager* mgr = get_update_manager();
    
    if (mgr->update_in_progress) {
        // Check if update was successful
        if (module_health_check_passed()) {
            // Commit the update
            mgr->update_in_progress = false;
            commit_update_state();
        } else {
            // Rollback to previous partition
            mgr->active_partition = (mgr->active_partition == PARTITION_A) ? PARTITION_B : PARTITION_A;
            mgr->update_in_progress = false;
            commit_partition_switch();
            ESP.restart();  // Boot from good partition
        }
    }
}
```

## 🏗️ Infrastructure Problems

### 1. CI/CD Pipeline Issues

**Problem**: Build failures, deployment errors, or inconsistent environments.

**Solutions**:
```yaml
# .github/workflows/build-and-deploy-module.yml
name: Robust Module Build

on:
  push:
    paths: ['mock_drivers/**']

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        module: [speed_governor, distance_sensor]
    
    steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0  # Full history for proper versioning
    
    - name: Cache ESP-IDF
      uses: actions/cache@v3
      with:
        path: ~/.espressif
        key: esp-idf-${{ runner.os }}-${{ hashFiles('**/sdkconfig') }}
    
    - name: Setup ESP-IDF
      uses: espressif/esp-idf-ci-action@v1
      with:
        esp_idf_version: v5.1.2
        target: esp32
    
    - name: Validate Module Changes
      run: |
        # Only build if this specific module changed
        if ! git diff --name-only HEAD~1 HEAD | grep -q "^mock_drivers/${{ matrix.module }}/"; then
          echo "No changes for ${{ matrix.module }}, skipping"
          exit 0
        fi
    
    - name: Build with Error Handling
      run: |
        cd mock_drivers/${{ matrix.module }}
        
        # Clean previous builds
        make clean || true
        
        # Build with detailed error reporting
        if ! make build 2>&1 | tee build.log; then
          echo "Build failed for ${{ matrix.module }}"
          cat build.log
          exit 1
        fi
        
        # Validate output
        if [ ! -f "build/${{ matrix.module }}.bin" ]; then
          echo "Binary not generated"
          exit 1
        fi
        
        # Check binary size
        size=$(stat -c%s "build/${{ matrix.module }}.bin")
        if [ $size -gt 65536 ]; then
          echo "Binary too large: $size bytes (max 64KB)"
          exit 1
        fi
    
    - name: Upload with Retry
      uses: nick-invision/retry@v2
      with:
        timeout_minutes: 5
        max_attempts: 3
        command: ./scripts/upload-to-supabase.sh ${{ matrix.module }}
```

### 2. Storage and CDN Issues

**Problem**: Supabase storage limits, global distribution, and access control.

**Solutions**:

**Multi-CDN Strategy**:
```json
{
  "storage_backends": [
    {
      "name": "supabase",
      "priority": 1,
      "regions": ["us-east-1", "eu-west-1"],
      "url": "https://project.supabase.co/storage/v1/object"
    },
    {
      "name": "aws_s3",
      "priority": 2,
      "regions": ["global"],
      "url": "https://ota-modules.s3.amazonaws.com"
    }
  ]
}
```

**Smart Client Selection**:
```cpp
// Geographic-aware endpoint selection
typedef struct {
    char url[256];
    float latency_ms;
    bool is_available;
    uint32_t last_check;
} StorageEndpoint;

StorageEndpoint endpoints[] = {
    {"https://project.supabase.co", 0, true, 0},
    {"https://ota-modules.s3.amazonaws.com", 0, true, 0},
    {"https://backup-cdn.example.com", 0, true, 0}
};

const char* select_best_endpoint(void) {
    // Test latency to each endpoint
    for (int i = 0; i < ARRAY_SIZE(endpoints); i++) {
        endpoints[i].latency_ms = test_endpoint_latency(endpoints[i].url);
    }
    
    // Sort by latency and return fastest available
    qsort(endpoints, ARRAY_SIZE(endpoints), sizeof(StorageEndpoint), compare_latency);
    
    for (int i = 0; i < ARRAY_SIZE(endpoints); i++) {
        if (endpoints[i].is_available) {
            return endpoints[i].url;
        }
    }
    
    return endpoints[0].url;  // Fallback to first
}
```

### 3. Version Management Complexity

**Problem**: Complex versioning schemes, dependency management, and rollout strategies.

**Solutions**:
```json
{
  "manifest_v2": {
    "format_version": "2.0",
    "devices": {
      "esp32-demo-001": {
        "current_modules": {
          "speed_governor": "1.0.0",
          "distance_sensor": "1.0.0"
        },
        "pending_updates": {
          "speed_governor": {
            "target_version": "1.1.0",
            "rollout_percentage": 25,
            "dependencies": [],
            "priority": "high",
            "deadline": "2024-02-01T00:00:00Z"
          }
        }
      }
    },
    "modules": {
      "speed_governor": {
        "versions": {
          "1.1.0": {
            "sha256": "abc123...",
            "size": 32768,
            "dependencies": {
              "system_api": ">=2.0.0"
            },
            "compatibility": {
              "min_firmware": "1.0.0",
              "max_firmware": "2.0.0"
            },
            "rollback_info": {
              "safe_rollback_version": "1.0.0",
              "rollback_timeout_minutes": 30
            }
          }
        }
      }
    }
  }
}
```

## 🚗 Automotive-Specific Problems

### 1. Functional Safety Requirements

**Problem**: Automotive systems must meet ISO 26262 (ASIL) safety standards.

**Solutions**:
```cpp
// Watchdog implementation
typedef struct {
    uint32_t timeout_ms;
    uint32_t last_kick;
    bool is_enabled;
    void (*timeout_callback)(void);
} SafetyWatchdog;

// Periodic safety checks
void safety_monitor_task(void* params) {
    while (1) {
        // Check critical system parameters
        if (!check_speed_governor_bounds()) {
            enter_safe_mode("Speed governor out of bounds");
        }
        
        if (!check_sensor_validity()) {
            enter_safe_mode("Sensor data invalid");
        }
        
        // Kick watchdog
        safety_watchdog_kick();
        
        vTaskDelay(pdMS_TO_TICKS(100));  // 100ms safety loop
    }
}

// Safe mode implementation
void enter_safe_mode(const char* reason) {
    // Log the failure
    log_safety_event(LOG_CRITICAL, reason);
    
    // Disable non-critical systems
    disable_all_updates();
    
    // Enable limp-home mode
    set_speed_limit_override(40);  // Safe speed
    
    // Signal failure to driver
    set_led_state(LED_RED, true);
    
    // Try to recover
    schedule_system_recovery();
}
```

### 2. Real-time Constraints

**Problem**: OTA updates must not interfere with real-time vehicle control systems.

**Solutions**:
```cpp
// Priority-based task scheduling
typedef enum {
    PRIORITY_CRITICAL = 5,    // Vehicle control
    PRIORITY_HIGH = 4,        // Safety monitoring
    PRIORITY_NORMAL = 3,      // Sensor reading
    PRIORITY_LOW = 2,         // OTA updates
    PRIORITY_BACKGROUND = 1   // Logging, diagnostics
} task_priority_t;

// Rate-limited OTA operations
typedef struct {
    uint32_t max_bandwidth_bps;
    uint32_t current_usage_bps;
    uint32_t last_reset_time;
    bool is_throttled;
} BandwidthLimiter;

bool throttle_ota_download(size_t bytes_requested) {
    BandwidthLimiter* limiter = get_bandwidth_limiter();
    
    // Reset usage counter every second
    uint32_t now = millis();
    if (now - limiter->last_reset_time > 1000) {
        limiter->current_usage_bps = 0;
        limiter->last_reset_time = now;
    }
    
    // Check if we can accommodate this request
    if (limiter->current_usage_bps + bytes_requested > limiter->max_bandwidth_bps) {
        limiter->is_throttled = true;
        return false;  // Deny request
    }
    
    limiter->current_usage_bps += bytes_requested;
    return true;  // Allow request
}

// Non-blocking update installation
void install_update_non_blocking(const char* module_name) {
    // Create background task with low priority
    xTaskCreatePinnedToCore(
        update_task,           // Task function
        "ota_update",         // Name
        8192,                 // Stack size
        (void*)module_name,   // Parameters
        PRIORITY_LOW,         // Priority
        NULL,                 // Task handle
        0                     // CPU core (0 = any)
    );
}
```

### 3. Vehicle State Management

**Problem**: Updates should only occur in safe vehicle states.

**Solutions**:
```cpp
typedef enum {
    VEHICLE_STATE_PARKED = 0,
    VEHICLE_STATE_IDLE = 1,
    VEHICLE_STATE_DRIVING = 2,
    VEHICLE_STATE_CHARGING = 3,
    VEHICLE_STATE_ERROR = 4
} vehicle_state_t;

typedef struct {
    vehicle_state_t current_state;
    uint32_t speed_kmh;
    bool ignition_on;
    bool parking_brake_engaged;
    bool charging_connected;
    uint32_t state_duration_ms;
} VehicleStatus;

bool is_safe_for_update(void) {
    VehicleStatus* status = get_vehicle_status();
    
    // Basic safety checks
    if (status->current_state == VEHICLE_STATE_DRIVING) {
        return false;
    }
    
    if (status->speed_kmh > 5) {  // 5 km/h threshold
        return false;
    }
    
    if (!status->parking_brake_engaged) {
        return false;
    }
    
    // Must be in safe state for at least 30 seconds
    if (status->state_duration_ms < 30000) {
        return false;
    }
    
    return true;
}

// State machine for update authorization
typedef enum {
    UPDATE_AUTH_WAITING = 0,
    UPDATE_AUTH_PENDING = 1,
    UPDATE_AUTH_AUTHORIZED = 2,
    UPDATE_AUTH_DENIED = 3
} update_auth_state_t;

void update_authorization_state_machine(void) {
    static update_auth_state_t auth_state = UPDATE_AUTH_WAITING;
    static uint32_t auth_start_time = 0;
    
    switch (auth_state) {
        case UPDATE_AUTH_WAITING:
            if (has_pending_updates() && is_safe_for_update()) {
                auth_state = UPDATE_AUTH_PENDING;
                auth_start_time = millis();
                notify_driver_update_pending();
            }
            break;
            
        case UPDATE_AUTH_PENDING:
            if (!is_safe_for_update()) {
                auth_state = UPDATE_AUTH_WAITING;
                cancel_update_notification();
            } else if (driver_approved_update()) {
                auth_state = UPDATE_AUTH_AUTHORIZED;
                start_update_process();
            } else if (millis() - auth_start_time > 300000) {  // 5 min timeout
                auth_state = UPDATE_AUTH_DENIED;
                log_update_timeout();
            }
            break;
            
        case UPDATE_AUTH_AUTHORIZED:
            // Update in progress
            if (is_update_complete()) {
                auth_state = UPDATE_AUTH_WAITING;
                notify_driver_update_complete();
            } else if (!is_safe_for_update()) {
                // Emergency abort
                abort_update();
                auth_state = UPDATE_AUTH_WAITING;
            }
            break;
            
        case UPDATE_AUTH_DENIED:
            // Wait before trying again
            if (millis() - auth_start_time > 3600000) {  // 1 hour
                auth_state = UPDATE_AUTH_WAITING;
            }
            break;
    }
}
```

## 📊 Monitoring and Diagnostics

### Fleet Management Dashboard

**Problem**: Managing updates across thousands of vehicles.

**Solution**:
```sql
-- Supabase database schema for fleet management
CREATE TABLE fleet_devices (
    device_id TEXT PRIMARY KEY,
    vin TEXT UNIQUE,
    model TEXT,
    firmware_version TEXT,
    last_seen TIMESTAMP,
    location GEOGRAPHY(POINT),
    status TEXT CHECK (status IN ('online', 'offline', 'updating', 'error'))
);

CREATE TABLE update_history (
    id SERIAL PRIMARY KEY,
    device_id TEXT REFERENCES fleet_devices(device_id),
    module_name TEXT,
    from_version TEXT,
    to_version TEXT,
    status TEXT CHECK (status IN ('started', 'completed', 'failed', 'rolled_back')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Real-time update monitoring
CREATE OR REPLACE FUNCTION notify_update_status()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('update_status', 
        json_build_object(
            'device_id', NEW.device_id,
            'module_name', NEW.module_name,
            'status', NEW.status,
            'timestamp', NEW.completed_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_status_trigger
    AFTER INSERT OR UPDATE ON update_history
    FOR EACH ROW EXECUTE FUNCTION notify_update_status();
```

### Health Monitoring

```cpp
// System health telemetry
typedef struct {
    uint32_t uptime_seconds;
    uint32_t free_heap_bytes;
    float cpu_usage_percent;
    uint32_t update_success_count;
    uint32_t update_failure_count;
    uint32_t network_reconnects;
    float average_update_time_seconds;
} SystemHealth;

void send_health_telemetry(void) {
    SystemHealth health;
    collect_system_health(&health);
    
    DynamicJsonDocument doc(1024);
    doc["device_id"] = get_device_id();
    doc["timestamp"] = get_utc_timestamp();
    doc["uptime"] = health.uptime_seconds;
    doc["free_heap"] = health.free_heap_bytes;
    doc["cpu_usage"] = health.cpu_usage_percent;
    doc["update_stats"] = {
        {"success_count", health.update_success_count},
        {"failure_count", health.update_failure_count},
        {"avg_time", health.average_update_time_seconds}
    };
    
    String payload;
    serializeJson(doc, payload);
    
    // Send to monitoring endpoint
    HTTPClient http;
    http.begin(TELEMETRY_ENDPOINT);
    http.addHeader("Content-Type", "application/json");
    http.POST(payload);
    http.end();
}
```

## 🔧 Testing and Validation

### Automated Testing Pipeline

```cpp
// Module testing framework
typedef struct {
    const char* test_name;
    bool (*test_function)(void);
    bool is_critical;
} ModuleTest;

// Speed governor tests
bool test_speed_governor_normal_conditions(void) {
    // Test normal road conditions (should return 40 km/h)
    int limit = get_speed_limit(50, 0);
    return limit == 40;
}

bool test_speed_governor_highway_conditions(void) {
    // Test highway conditions (should return 100 km/h in v1.1.0)
    int limit = get_speed_limit(80, 1);
    return limit == 100;  // This would fail in v1.0.0
}

bool test_speed_governor_city_conditions(void) {
    // Test city conditions (should return 30 km/h)
    int limit = get_speed_limit(40, 2);
    return limit == 30;
}

ModuleTest speed_governor_tests[] = {
    {"Normal Conditions", test_speed_governor_normal_conditions, true},
    {"Highway Conditions", test_speed_governor_highway_conditions, true},
    {"City Conditions", test_speed_governor_city_conditions, false}
};

// Test runner
bool run_module_tests(const char* module_name) {
    bool all_critical_passed = true;
    int passed = 0, failed = 0;
    
    ModuleTest* tests = get_tests_for_module(module_name);
    int test_count = get_test_count(module_name);
    
    for (int i = 0; i < test_count; i++) {
        bool result = tests[i].test_function();
        
        if (result) {
            passed++;
            Serial.printf("✅ %s\n", tests[i].test_name);
        } else {
            failed++;
            Serial.printf("❌ %s\n", tests[i].test_name);
            
            if (tests[i].is_critical) {
                all_critical_passed = false;
            }
        }
    }
    
    Serial.printf("Tests: %d passed, %d failed\n", passed, failed);
    
    if (!all_critical_passed) {
        Serial.println("CRITICAL TESTS FAILED - Module not safe for deployment");
        return false;
    }
    
    return true;
}
```

### Hardware-in-the-Loop Testing

```python
# HIL test framework (Python)
import serial
import time
import json

class ESP32OTATestFramework:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.serial = serial.Serial(port, baudrate)
        self.test_results = []
    
    def send_command(self, command):
        self.serial.write(f"{command}\n".encode())
        return self.wait_for_response()
    
    def wait_for_response(self, timeout=10):
        start_time = time.time()
        response = ""
        
        while time.time() - start_time < timeout:
            if self.serial.in_waiting > 0:
                response += self.serial.read().decode()
                if response.endswith('\n'):
                    return response.strip()
        
        raise TimeoutError("No response from ESP32")
    
    def test_ota_update_flow(self):
        """Test complete OTA update flow"""
        
        # 1. Check initial state
        response = self.send_command("GET_MODULE_VERSION speed_governor")
        assert "1.0.0" in response, f"Expected v1.0.0, got: {response}"
        
        # 2. Trigger update check
        self.send_command("CHECK_UPDATES")
        time.sleep(5)  # Wait for update check
        
        # 3. Verify update detected
        response = self.send_command("GET_UPDATE_STATUS")
        assert "UPDATE_AVAILABLE" in response, "Update should be available"
        
        # 4. Simulate vehicle idle
        self.send_command("SET_VEHICLE_IDLE true")
        
        # 5. Start update
        self.send_command("START_UPDATE speed_governor")
        
        # 6. Wait for update completion
        for _ in range(60):  # 60 second timeout
            response = self.send_command("GET_UPDATE_STATUS")
            if "UPDATE_COMPLETE" in response:
                break
            time.sleep(1)
        else:
            raise TimeoutError("Update did not complete")
        
        # 7. Verify new version
        response = self.send_command("GET_MODULE_VERSION speed_governor")
        assert "1.1.0" in response, f"Expected v1.1.0, got: {response}"
        
        # 8. Test functionality
        response = self.send_command("TEST_HIGHWAY_SPEED")
        assert "100" in response, "Highway speed should be 100 km/h"
        
        print("✅ OTA update flow test passed")
    
    def test_update_rollback(self):
        """Test update rollback on failure"""
        
        # Simulate corrupted update
        self.send_command("INJECT_CORRUPT_UPDATE")
        self.send_command("START_UPDATE speed_governor")
        
        # Wait for rollback
        time.sleep(10)
        
        # Verify rollback occurred
        response = self.send_command("GET_MODULE_VERSION speed_governor")
        assert "1.0.0" in response, "Should have rolled back to v1.0.0"
        
        print("✅ Update rollback test passed")

# Run tests
if __name__ == "__main__":
    test_framework = ESP32OTATestFramework()
    test_framework.test_ota_update_flow()
    test_framework.test_update_rollback()
    print("🎉 All tests passed!")
```

## 📋 Summary

The modular OTA system faces significant technical challenges, but with proper architecture and careful implementation, these can be overcome:

1. **Start Simple**: Begin with the mock implementation provided
2. **Iterate Gradually**: Add complexity only as needed
3. **Test Extensively**: Use automated testing at every stage
4. **Monitor Continuously**: Implement comprehensive logging and health checks
5. **Plan for Failure**: Always have rollback and recovery mechanisms

The provided system gives you a solid foundation to build upon and demonstrates the core concepts needed for real-world automotive OTA updates. 