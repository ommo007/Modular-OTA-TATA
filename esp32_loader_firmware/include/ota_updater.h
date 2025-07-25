#ifndef OTA_UPDATER_H
#define OTA_UPDATER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Update status codes
typedef enum {
    UPDATE_SUCCESS = 0,
    UPDATE_NO_UPDATES_AVAILABLE = 1,
    UPDATE_DOWNLOAD_FAILED = 2,
    UPDATE_VERIFICATION_FAILED = 3,
    UPDATE_INSTALLATION_FAILED = 4,
    UPDATE_NETWORK_ERROR = 5,
    UPDATE_STORAGE_ERROR = 6,
    UPDATE_INVALID_MANIFEST = 7
} update_status_t;

// Update information structure
typedef struct {
    char module_name[32];
    char current_version[32];
    char available_version[32];
    uint32_t file_size;
    char sha256_hash[65];  // 64 chars + null terminator
    bool is_critical;
    char priority[16];
} UpdateInfo;

// Module version tracking structure
typedef struct {
    char module_name[32];
    char current_version[32];
} TrackedModule;

// OTA Updater Class Interface
typedef struct {
    // Configuration
    const char* server_url;
    const char* manifest_path;
    const char* device_id;
    const char* public_key_pem;
    uint32_t check_interval_ms;
    
    // State
    bool is_checking;
    bool updates_available;
    uint32_t last_check_time;
    
    // Available updates
    UpdateInfo pending_updates[8];  // Max 8 modules
    uint8_t pending_update_count;
    
    // Current module version tracking
    TrackedModule tracked_modules[8];  // Max 8 modules
    uint8_t num_tracked_modules;
    
} OTAUpdater;

// Function declarations
bool ota_updater_init(OTAUpdater* updater, const char* server_url, const char* device_id, const char* public_key);
update_status_t ota_updater_check_for_updates(OTAUpdater* updater);
update_status_t ota_updater_download_and_apply_update(OTAUpdater* updater, const char* module_name);
bool ota_updater_has_pending_updates(OTAUpdater* updater);
UpdateInfo* ota_updater_get_pending_update(OTAUpdater* updater, const char* module_name);
void ota_updater_clear_pending_updates(OTAUpdater* updater);

// Module version management
bool ota_updater_set_module_version(OTAUpdater* updater, const char* module_name, const char* version);
const char* ota_updater_get_module_version(OTAUpdater* updater, const char* module_name);

// Utility functions
bool ota_verify_sha256(const char* file_path, const char* expected_hash);
bool ota_download_file(const char* url, const char* local_path);
bool ota_backup_current_module(const char* module_name);
bool ota_rollback_module(const char* module_name);

#ifdef __cplusplus
}
#endif

#endif // OTA_UPDATER_H 