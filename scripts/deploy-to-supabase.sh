#!/bin/bash

# Improved Deployment Script for Modular OTA System
# - Uses a robust, flat-file versioning scheme (e.g., module-v1.1.0.bin).
# - Retries uploads to handle transient network issues.
# - Centralized configuration and dependency checks.
# - Clear separation of build and deployment logic.

set -e

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SUPABASE_BUCKET="ota-modules"
UPLOAD_RETRIES=3
RETRY_DELAY=5

# --- Dependency Checks ---
if ! command -v jq &> /dev/null; then
    echo "❌ Error: 'jq' is not installed. Please install it to continue." >&2
    exit 1
fi
if ! command -v curl &> /dev/null; then
    echo "❌ Error: 'curl' is not installed. Please install it to continue." >&2
    exit 1
fi

# --- Environment Variable Checks ---
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY secrets." >&2
    exit 1
fi

# --- Color Definitions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# --- Utility Functions ---
get_file_size() {
    stat -c%s "$1" 2>/dev/null || stat -f%z "$1" 2>/dev/null || echo "N/A"
}

# --- Core Functions ---

# Fetches existing versions for a module from Supabase
get_existing_versions() {
    local module_name="$1"
    curl -s -f "$SUPABASE_URL/storage/v1/object/list/$SUPABASE_BUCKET?prefix=$module_name/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" | \
        jq -r '.[] | .name' | \
        grep -oE "${module_name}-v[0-9]+\.[0-9]+\.[0-9]+\.bin" | \
        sed -E "s/.*-v([0-9]+\.[0-9]+\.[0-9]+)\.bin/\1/" | \
        sort -V || echo ""
}

# Calculates the next semantic version
get_next_version() {
    local module_name="$1"
    local base_version="1.1.0"
    echo -e "${BLUE}🔍 Determining next version for '$module_name'...${NC}" >&2
    local latest_version=$(get_existing_versions "$module_name" | tail -n 1)

    if [ -z "$latest_version" ]; then
        echo -e "${GREEN}📦 No previous versions found. Starting with $base_version.${NC}" >&2
        echo "$base_version"
        return
    fi

    IFS='.' read -r major minor patch <<< "$latest_version"
    local next_patch=$((patch + 1))
    local next_version="${major}.${minor}.${next_patch}"
    echo -e "${GREEN}📦 Latest version is v$latest_version. Next will be v$next_version.${NC}" >&2
    echo "$next_version"
}

# Deletes a file from Supabase storage
delete_file() {
    local remote_path="$1"
    echo -e "${YELLOW}🗑️  Ensuring path is clear: $remote_path${NC}" >&2
    curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE "$SUPABASE_URL/storage/v1/object/$SUPABASE_BUCKET/$remote_path" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" || true
}

# Uploads a file with retries
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"
    local attempt=1

    echo -e "${YELLOW}☁️  Uploading: $local_path -> $remote_path${NC}" >&2
    while [ $attempt -le $UPLOAD_RETRIES ]; do
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "$SUPABASE_URL/storage/v1/object/$SUPABASE_BUCKET/$remote_path" \
            -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
            -H "Content-Type: $content_type" \
            --data-binary "@$local_path")

        if [ "$http_code" -eq 200 ]; then
            echo -e "${GREEN}✅ Upload successful (HTTP $http_code).${NC}" >&2
            return 0
        else
            echo -e "${RED}⚠️ Upload attempt $attempt failed (HTTP $http_code). Retrying in $RETRY_DELAY seconds...${NC}" >&2
            sleep $RETRY_DELAY
        fi
        ((attempt++))
    done

    echo -e "${RED}❌ All upload attempts failed for $remote_path.${NC}" >&2
    return 1
}

# --- Build and Deployment Logic ---

build_module() {
    local module_name="$1"
    local module_path="$PROJECT_ROOT/mock_drivers/$module_name"

    echo -e "\n${BLUE}--- Building Module: $module_name ---${NC}" >&2
    if [ ! -d "$module_path" ]; then
        echo -e "${RED}❌ Module directory not found: $module_path${NC}" >&2
        return 1
    fi
    
    cd "$module_path"
    echo "🧹 Cleaning previous build..." >&2
    make clean > /dev/null 2>&1 || true

    echo "🔨 Running make build..." >&2
    if ! make build; then 
        echo -e "${RED}❌ Build failed for '$module_name'.${NC}" >&2
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    local binary_path="build/$module_name.bin"
    if [ ! -f "$binary_path" ]; then
        echo -e "${RED}❌ Built binary not found at $binary_path${NC}" >&2
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    echo -e "${GREEN}✅ Build successful. Binary: $binary_path (${GREEN}$(get_file_size "$binary_path") bytes${NC})" >&2
    cd "$PROJECT_ROOT"
    echo "$binary_path"
}

deploy_module() {
    local module_name="$1"
    local binary_path="$2"

    echo -e "\n${BLUE}--- Deploying Module: $module_name ---${NC}" >&2

    local version=$(get_next_version "$module_name")
    local hash=$(sha256sum "$binary_path" | cut -d' ' -f1)
    local size=$(get_file_size "$binary_path")
    local versioned_filename="${module_name}-v${version}.bin"
    
    echo "☁️  Uploading immutable artifact: $versioned_filename" >&2
    if ! upload_file "$binary_path" "$module_name/$versioned_filename" "application/octet-stream"; then 
        return 1
    fi

    echo "☁️  Updating mutable 'latest' pointer..." >&2
    delete_file "$module_name/latest.bin"
    if ! upload_file "$binary_path" "$module_name/latest.bin" "application/octet-stream"; then 
        return 1
    fi

    echo -e "${GREEN}🎉 Module '$module_name' deployed successfully!${NC}" >&2
    echo "$module_name:$version:$hash:$size"
}

update_manifest() {
    local metadata="$1"
    IFS=':' read -r module_name version hash size <<< "$metadata"
    local manifest_path="temp_manifest.json"

    echo -e "\n${BLUE}--- Updating Master Manifest ---${NC}" >&2

    # Download existing manifest or create an empty one
    curl -s -f -o "$manifest_path" "$SUPABASE_URL/storage/v1/object/public/$SUPABASE_BUCKET/manifest.json" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" || echo "{}" > "$manifest_path"

    echo "✍️  Updating entry for '$module_name' to v$version..." >&2
    jq --arg module "$module_name" --arg ver "v$version" --arg sha256 "$hash" --argjson sz "$size" \
      '.modules[$module] = { latest_version: $ver, sha256: $sha256, file_size: $sz, updated_at: now | todate }' \
      "$manifest_path" > "$manifest_path.tmp" && mv "$manifest_path.tmp" "$manifest_path"

    delete_file "manifest.json"
    if ! upload_file "$manifest_path" "manifest.json" "application/json"; then
        rm -f "$manifest_path"
        return 1
    fi
    
    echo -e "${GREEN}✅ Manifest updated successfully.${NC}" >&2
    rm -f "$manifest_path"
}

# --- Main Execution ---
main() {
    local changed_files=("$@")
    if [ ${#changed_files[@]} -eq 0 ]; then
        echo "No files specified. Exiting." >&2
        exit 0
    fi

    declare -A modules_to_process
    for file in "${changed_files[@]}"; do
        if [[ $file == mock_drivers/* ]]; then
            modules_to_process[$(basename "$(dirname "$file")")]=1
        fi
    done

    if [ ${#modules_to_process[@]} -eq 0 ]; then
        echo "✅ No changes in module directories. Nothing to deploy." >&2
        exit 0
    fi

    echo "📦 Modules to process: ${!modules_to_process[@]}" >&2
    for module in "${!modules_to_process[@]}"; do
        local binary_path
        if ! binary_path=$(build_module "$module"); then
            echo -e "${RED}❌ Halting deployment due to build failure in '$module'.${NC}" >&2
            exit 1
        fi

        local module_metadata
        if ! module_metadata=$(deploy_module "$module" "$binary_path"); then
            echo -e "${RED}❌ Halting deployment due to deployment failure of '$module'.${NC}" >&2
            exit 1
        fi

        update_manifest "$module_metadata"
    done

    echo -e "\n${GREEN}🎉 All changed modules built and deployed successfully!${NC}" >&2
}

# Pass all script arguments to main
main "$@"