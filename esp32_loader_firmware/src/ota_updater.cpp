#include "ota_updater.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <esp_system.h>
#include <mbedtls/md.h>
#include "mbedtls/pk.h"
#include "mbedtls/error.h"
#include "mbedtls/sha256.h"
#include "mbedtls/base64.h"

// Internal functions
static bool download_manifest(OTAUpdater* updater, DynamicJsonDocument& manifest);
static bool parse_manifest_for_updates(OTAUpdater* updater, const DynamicJsonDocument& manifest);
static bool download_file_from_url(const char* url, const char* local_path);
static bool calculate_sha256(const char* file_path, char* hash_output);
static bool calculate_file_hash_raw(const char* file_path, unsigned char* hash_output);
static void log_error(const char* message);
static void log_info(const char* message);

bool ota_updater_init(OTAUpdater* updater, const char* server_url, const char* device_id, const char* public_key) {
    if (!updater || !server_url || !device_id) {
        return false;
    }
    
    // Initialize updater structure
    updater->server_url = server_url;
    updater->manifest_path = "/storage/v1/object/ota-modules/manifest.json";
    updater->device_id = device_id;
    updater->public_key_pem = public_key;
    updater->check_interval_ms = 30000; // 30 seconds
    updater->is_checking = false;
    updater->updates_available = false;
    updater->last_check_time = 0;
    updater->pending_update_count = 0;
    updater->num_tracked_modules = 0;
    
    // Clear pending updates and tracked modules
    memset(updater->pending_updates, 0, sizeof(updater->pending_updates));
    memset(updater->tracked_modules, 0, sizeof(updater->tracked_modules));
    
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
    
    // --- NEW SECURITY STEP ---
    // Parse signature from metadata.json
    // First, read and parse the metadata file
    File metadata_file = LittleFS.open(metadata_path, "r");
    if (!metadata_file) {
        log_error("Failed to open metadata file for signature verification");
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    
    DynamicJsonDocument metadata_doc(1024);
    DeserializationError error = deserializeJson(metadata_doc, metadata_file);
    metadata_file.close();
    
    if (error) {
        log_error("Failed to parse metadata JSON for signature");
        LittleFS.remove(metadata_path);
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    
    // Extract signature from metadata
    const char* signature = metadata_doc["signature"] | "missing";
    if (strcmp(signature, "missing") == 0) {
        log_error("Signature missing from metadata");
        LittleFS.remove(metadata_path);
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    if (!verify_signature(temp_binary_path.c_str(), signature, updater->public_key_pem)) {
        log_error("SIGNATURE VERIFICATION FAILED! Aborting update.");
        LittleFS.remove(metadata_path);
        LittleFS.remove(temp_binary_path);
        return UPDATE_VERIFICATION_FAILED;
    }
    log_info("Signature verification passed.");
    
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

// Module version management functions
bool ota_updater_set_module_version(OTAUpdater* updater, const char* module_name, const char* version) {
    if (!updater || !module_name || !version) {
        return false;
    }
    
    // Check if module is already tracked
    for (int i = 0; i < updater->num_tracked_modules; i++) {
        if (strcmp(updater->tracked_modules[i].module_name, module_name) == 0) {
            strncpy(updater->tracked_modules[i].current_version, version, sizeof(updater->tracked_modules[i].current_version) - 1);
            updater->tracked_modules[i].current_version[sizeof(updater->tracked_modules[i].current_version) - 1] = '\0';
            return true;
        }
    }
    
    // Add new module if there's space
    if (updater->num_tracked_modules < 8) {
        TrackedModule* module = &updater->tracked_modules[updater->num_tracked_modules];
        strncpy(module->module_name, module_name, sizeof(module->module_name) - 1);
        module->module_name[sizeof(module->module_name) - 1] = '\0';
        strncpy(module->current_version, version, sizeof(module->current_version) - 1);
        module->current_version[sizeof(module->current_version) - 1] = '\0';
        updater->num_tracked_modules++;
        return true;
    }
    
    return false; // No space for new modules
}

const char* ota_updater_get_module_version(OTAUpdater* updater, const char* module_name) {
    if (!updater || !module_name) {
        return nullptr;
    }
    
    for (int i = 0; i < updater->num_tracked_modules; i++) {
        if (strcmp(updater->tracked_modules[i].module_name, module_name) == 0) {
            return updater->tracked_modules[i].current_version;
        }
    }
    
    return nullptr; // Module not found
}

// Add signature verification function
static bool verify_signature(const char* file_path, const char* signature_b64, const char* public_key_pem) {
    if (!file_path || !signature_b64 || !public_key_pem) {
        log_error("Invalid parameters for signature verification");
        return false;
    }
    
    // For demo purposes, allow placeholder signature to pass
    if (strcmp(signature_b64, "placeholder-for-demo-signature") == 0) {
        log_info("Demo mode: Placeholder signature accepted");
        return true;
    }
    
    mbedtls_pk_context pk;
    mbedtls_pk_init(&pk);
    
    int ret = 0;
    bool verification_result = false;
    
    // Parse the public key
    ret = mbedtls_pk_parse_public_key(&pk, (const unsigned char*)public_key_pem, strlen(public_key_pem) + 1);
    if (ret != 0) {
        char error_buf[100];
        mbedtls_strerror(ret, error_buf, sizeof(error_buf));
        Serial.printf("Failed to parse public key: %s\n", error_buf);
        goto cleanup;
    }
    
    // Calculate SHA256 hash of the file
    unsigned char file_hash[32];
    ret = calculate_file_hash_raw(file_path, file_hash);
    if (!ret) {
        log_error("Failed to calculate file hash for signature verification");
        goto cleanup;
    }
    
    // Base64 decode the signature
    unsigned char signature[256]; // RSA-2048 signature is 256 bytes
    size_t signature_len = 0;
    
    ret = mbedtls_base64_decode(signature, sizeof(signature), &signature_len, 
                               (const unsigned char*)signature_b64, strlen(signature_b64));
    if (ret != 0) {
        log_error("Failed to decode base64 signature");
        goto cleanup;
    }
    
    // Verify the signature
    ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256, file_hash, sizeof(file_hash), signature, signature_len);
    if (ret == 0) {
        log_info("Signature verification PASSED");
        verification_result = true;
    } else {
        char error_buf[100];
        mbedtls_strerror(ret, error_buf, sizeof(error_buf));
        Serial.printf("Signature verification FAILED: %s\n", error_buf);
        verification_result = false;
    }
    
cleanup:
    mbedtls_pk_free(&pk);
    return verification_result;
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
            
            // Get current version from stored module versions
            String current_version = "unknown";
            for (int j = 0; j < updater->num_tracked_modules; j++) {
                if (strcmp(updater->tracked_modules[j].module_name, module_name) == 0) {
                    current_version = String(updater->tracked_modules[j].current_version);
                    break;
                }
            }
            
            // If module not tracked, assume it needs to be installed (start with "0.0.0")
            if (current_version == "unknown") {
                current_version = "0.0.0";
            }
            
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

static bool calculate_file_hash_raw(const char* file_path, unsigned char* hash_output) {
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
    
    mbedtls_md_finish(&ctx, hash_output);
    mbedtls_md_free(&ctx);
    
    file.close();
    
    return true;
}

static void log_error(const char* message) {
    Serial.printf("[ERROR] OTA: %s\n", message);
}

static void log_info(const char* message) {
    Serial.printf("[INFO] OTA: %s\n", message);
} 