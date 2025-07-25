#include "ota_updater.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <esp_system.h>
#include <mbedtls/md.h>

// Internal functions
static bool download_manifest(OTAUpdater* updater, DynamicJsonDocument& manifest);
static bool parse_manifest_for_updates(OTAUpdater* updater, const DynamicJsonDocument& manifest);
static bool download_file_from_url(const char* url, const char* local_path);
static bool calculate_sha256(const char* file_path, char* hash_output);
static void log_error(const char* message);
static void log_info(const char* message);

bool ota_updater_init(OTAUpdater* updater, const char* server_url, const char* device_id) {
    if (!updater || !server_url || !device_id) {
        return false;
    }
    
    // Initialize updater structure
    updater->server_url = server_url;
    updater->manifest_path = "/storage/v1/object/ota-modules/manifest.json";
    updater->device_id = device_id;
    updater->check_interval_ms = 30000; // 30 seconds
    updater->is_checking = false;
    updater->updates_available = false;
    updater->last_check_time = 0;
    updater->pending_update_count = 0;
    
    // Clear pending updates
    memset(updater->pending_updates, 0, sizeof(updater->pending_updates));
    
    log_info("OTA Updater initialized");
    return true;
}

update_status_t ota_updater_check_for_updates(OTAUpdater* updater) {
    if (!updater || updater->is_checking) {
        return UPDATE_NETWORK_ERROR;
    }
    
    if (WiFi.status() != WL_CONNECTED) {
        log_error("WiFi not connected");
        return UPDATE_NETWORK_ERROR;
    }
    
    updater->is_checking = true;
    updater->last_check_time = millis();
    
    log_info("Checking for updates...");
    
    // Download and parse manifest
    DynamicJsonDocument manifest(4096);
    if (!download_manifest(updater, manifest)) {
        updater->is_checking = false;
        return UPDATE_DOWNLOAD_FAILED;
    }
    
    // Parse manifest for available updates
    if (!parse_manifest_for_updates(updater, manifest)) {
        updater->is_checking = false;
        return UPDATE_INVALID_MANIFEST;
    }
    
    updater->is_checking = false;
    updater->updates_available = (updater->pending_update_count > 0);
    
    if (updater->updates_available) {
        Serial.printf("Found %d pending updates\n", updater->pending_update_count);
        return UPDATE_SUCCESS;
    } else {
        log_info("No updates available");
        return UPDATE_NO_UPDATES_AVAILABLE;
    }
}

update_status_t ota_updater_download_and_apply_update(OTAUpdater* updater, const char* module_name) {
    if (!updater || !module_name) {
        return UPDATE_INSTALLATION_FAILED;
    }
    
    // Find the update for this module
    UpdateInfo* update_info = nullptr;
    for (int i = 0; i < updater->pending_update_count; i++) {
        if (strcmp(updater->pending_updates[i].module_name, module_name) == 0) {
            update_info = &updater->pending_updates[i];
            break;
        }
    }
    
    if (!update_info) {
        log_error("Update not found for module");
        return UPDATE_INSTALLATION_FAILED;
    }
    
    Serial.printf("Downloading update for %s v%s\n", module_name, update_info->available_version);
    
    // Construct download URLs
    String binary_url = String(updater->server_url) + 
                       "/storage/v1/object/ota-modules/" + 
                       module_name + "/latest/" + module_name + ".bin";
                       
    String metadata_url = String(updater->server_url) + 
                         "/storage/v1/object/ota-modules/" + 
                         module_name + "/latest/metadata.json";
    
    // Download metadata first
    String metadata_path = "/" + String(module_name) + "_metadata.json";
    if (!download_file_from_url(metadata_url.c_str(), metadata_path.c_str())) {
        log_error("Failed to download metadata");
        return UPDATE_DOWNLOAD_FAILED;
    }
    
    // Download binary
    String temp_binary_path = "/" + String(module_name) + ".bin.new";
    if (!download_file_from_url(binary_url.c_str(), temp_binary_path.c_str())) {
        log_error("Failed to download binary");
        LittleFS.remove(metadata_path);
        return UPDATE_DOWNLOAD_FAILED;
    }
    
    // Verify hash
    char calculated_hash[65];
    if (!calculate_sha256(temp_binary_path.c_str(), calculated_hash)) {
        log_error("Failed to calculate hash");
        LittleFS.remove(metadata_path);
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    
    if (strcmp(calculated_hash, update_info->sha256_hash) != 0) {
        Serial.printf("Hash mismatch! Expected: %s, Got: %s\n", 
                     update_info->sha256_hash, calculated_hash);
        LittleFS.remove(metadata_path);
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    
    // Backup current module if it exists
    String current_binary_path = "/" + String(module_name) + ".bin";
    String backup_path = "/" + String(module_name) + ".bin.backup";
    
    if (LittleFS.exists(current_binary_path)) {
        if (!ota_backup_current_module(module_name)) {
            log_error("Failed to backup current module");
            // Continue anyway, don't fail the update
        }
    }
    
    // Move new binary to active location
    if (LittleFS.exists(current_binary_path)) {
        LittleFS.remove(current_binary_path);
    }
    
    if (!LittleFS.rename(temp_binary_path, current_binary_path)) {
        log_error("Failed to install new module");
        // Try to restore backup
        ota_rollback_module(module_name);
        LittleFS.remove(metadata_path);
        return UPDATE_INSTALLATION_FAILED;
    }
    
    // Clean up
    LittleFS.remove(metadata_path);
    
    Serial.printf("Successfully updated %s to version %s\n", module_name, update_info->available_version);
    return UPDATE_SUCCESS;
}

bool ota_updater_has_pending_updates(OTAUpdater* updater) {
    return updater && updater->pending_update_count > 0;
}

UpdateInfo* ota_updater_get_pending_update(OTAUpdater* updater, const char* module_name) {
    if (!updater || !module_name) {
        return nullptr;
    }
    
    for (int i = 0; i < updater->pending_update_count; i++) {
        if (strcmp(updater->pending_updates[i].module_name, module_name) == 0) {
            return &updater->pending_updates[i];
        }
    }
    
    return nullptr;
}

void ota_updater_clear_pending_updates(OTAUpdater* updater) {
    if (updater) {
        updater->pending_update_count = 0;
        updater->updates_available = false;
        memset(updater->pending_updates, 0, sizeof(updater->pending_updates));
    }
}

// Utility functions
bool ota_verify_sha256(const char* file_path, const char* expected_hash) {
    char calculated_hash[65];
    if (!calculate_sha256(file_path, calculated_hash)) {
        return false;
    }
    return strcmp(calculated_hash, expected_hash) == 0;
}

bool ota_download_file(const char* url, const char* local_path) {
    return download_file_from_url(url, local_path);
}

bool ota_backup_current_module(const char* module_name) {
    String current_path = "/" + String(module_name) + ".bin";
    String backup_path = "/" + String(module_name) + ".bin.backup";
    
    if (LittleFS.exists(current_path)) {
        if (LittleFS.exists(backup_path)) {
            LittleFS.remove(backup_path);
        }
        return LittleFS.rename(current_path, backup_path);
    }
    
    return true; // No current module to backup
}

bool ota_rollback_module(const char* module_name) {
    String current_path = "/" + String(module_name) + ".bin";
    String backup_path = "/" + String(module_name) + ".bin.backup";
    
    if (LittleFS.exists(backup_path)) {
        if (LittleFS.exists(current_path)) {
            LittleFS.remove(current_path);
        }
        bool success = LittleFS.rename(backup_path, current_path);
        if (success) {
            log_info("Module rollback successful");
        } else {
            log_error("Module rollback failed");
        }
        return success;
    }
    
    log_error("No backup available for rollback");
    return false;
}

// Internal helper functions
static bool download_manifest(OTAUpdater* updater, DynamicJsonDocument& manifest) {
    HTTPClient http;
    String url = String(updater->server_url) + updater->manifest_path;
    
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    
    int httpCode = http.GET();
    
    if (httpCode == HTTP_CODE_OK) {
        String payload = http.getString();
        DeserializationError error = deserializeJson(manifest, payload);
        
        if (error) {
            Serial.printf("JSON parse error: %s\n", error.c_str());
            http.end();
            return false;
        }
        
        http.end();
        return true;
    } else {
        Serial.printf("HTTP error: %d\n", httpCode);
        http.end();
        return false;
    }
}

static bool parse_manifest_for_updates(OTAUpdater* updater, const DynamicJsonDocument& manifest) {
    updater->pending_update_count = 0;
    
    // List of modules we support
    const char* supported_modules[] = {"speed_governor", "distance_sensor"};
    const int num_supported = sizeof(supported_modules) / sizeof(supported_modules[0]);
    
    for (int i = 0; i < num_supported && updater->pending_update_count < 8; i++) {
        const char* module_name = supported_modules[i];
        
        if (manifest.containsKey(module_name)) {
            JsonObject module_info = manifest[module_name];
            
            String available_version = module_info["latest_version"].as<String>();
            
            // Get current version (for demo, assume we start with 1.0.0)
            String current_version = "1.0.0";
            
            // Simple version comparison (in real implementation, use semantic versioning)
            if (available_version != current_version) {
                UpdateInfo* update = &updater->pending_updates[updater->pending_update_count];
                
                strncpy(update->module_name, module_name, sizeof(update->module_name) - 1);
                strncpy(update->current_version, current_version.c_str(), sizeof(update->current_version) - 1);
                strncpy(update->available_version, available_version.c_str(), sizeof(update->available_version) - 1);
                
                // For demo, we'll fetch the actual hash when downloading
                strcpy(update->sha256_hash, "will_be_fetched_later");
                update->file_size = 0; // Will be determined during download
                update->is_critical = false;
                strcpy(update->priority, "normal");
                
                updater->pending_update_count++;
                
                Serial.printf("Found update for %s: %s -> %s\n", 
                             module_name, current_version.c_str(), available_version.c_str());
            }
        }
    }
    
    return true;
}

static bool download_file_from_url(const char* url, const char* local_path) {
    HTTPClient http;
    http.begin(url);
    
    int httpCode = http.GET();
    
    if (httpCode == HTTP_CODE_OK) {
        WiFiClient* client = http.getStreamPtr();
        File file = LittleFS.open(local_path, "w");
        
        if (!file) {
            Serial.printf("Failed to open file for writing: %s\n", local_path);
            http.end();
            return false;
        }
        
        int contentLength = http.getSize();
        uint8_t buffer[128];
        int bytesRead = 0;
        
        while (http.connected() && (contentLength > 0 || contentLength == -1)) {
            size_t size = client->available();
            if (size) {
                int c = client->readBytes(buffer, min(size, sizeof(buffer)));
                file.write(buffer, c);
                bytesRead += c;
                
                if (contentLength > 0) {
                    contentLength -= c;
                }
            }
            delay(1);
        }
        
        file.close();
        http.end();
        
        Serial.printf("Downloaded %d bytes to %s\n", bytesRead, local_path);
        return true;
    } else {
        Serial.printf("HTTP error downloading %s: %d\n", url, httpCode);
        http.end();
        return false;
    }
}

static bool calculate_sha256(const char* file_path, char* hash_output) {
    File file = LittleFS.open(file_path, "r");
    if (!file) {
        return false;
    }
    
    mbedtls_md_context_t ctx;
    mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;
    
    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 0);
    mbedtls_md_starts(&ctx);
    
    uint8_t buffer[512];
    while (file.available()) {
        size_t bytesRead = file.readBytes((char*)buffer, sizeof(buffer));
        mbedtls_md_update(&ctx, buffer, bytesRead);
    }
    
    uint8_t hash[32];
    mbedtls_md_finish(&ctx, hash);
    mbedtls_md_free(&ctx);
    
    file.close();
    
    // Convert to hex string
    for (int i = 0; i < 32; i++) {
        sprintf(hash_output + (i * 2), "%02x", hash[i]);
    }
    hash_output[64] = '\0';
    
    return true;
}

static void log_error(const char* message) {
    Serial.printf("[ERROR] OTA: %s\n", message);
}

static void log_info(const char* message) {
    Serial.printf("[INFO] OTA: %s\n", message);
} 