#!/bin/bash

# Intelligent Deployment Script for Modular OTA System
# - Automatically determines the next semantic version based on cloud storage.
# - Handles Supabase upload conflicts gracefully.
# - Creates immutable, versioned artifacts and updates a 'latest' pointer.
# - Updates the master manifest.json with authoritative metadata.

set -e

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables if a .env file exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    source "$PROJECT_ROOT/.env"
fi

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY secrets." >&2
    exit 1
fi

# --- Color Definitions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# --- Core Functions ---

# Fetches existing versions for a module from Supabase
get_existing_versions() {
    local module_name="$1"
    # Note: Error messages from curl are redirected to stderr to keep stdout clean
    curl -s -f \
        "$SUPABASE_URL/storage/v1/object/list/ota-modules?prefix=$module_name/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" 2>/dev/null | \
        jq -r '.[] | .name' 2>/dev/null | \
        grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | \
        sort -V || echo ""
}

# Calculates the next semantic version
get_next_version() {
    local module_name="$1"
    local base_version="v1.1.0"
    
    # FIX: All logging messages are redirected to stderr (>&2)
    echo -e "${BLUE}🔍 Determining next version for '$module_name'...${NC}" >&2
    local latest_version=$(get_existing_versions "$module_name" | tail -n 1)

    if [ -z "$latest_version" ]; then
        echo -e "${GREEN}📦 No previous versions found. Starting with $base_version.${NC}" >&2
        echo "$base_version" # This is the actual return value to stdout
        return
    fi

    IFS='.' read -r major minor patch <<< "${latest_version//v/}"
    local next_patch=$((patch + 1))
    local next_version="v${major}.${minor}.${next_patch}"
    echo -e "${GREEN}📦 Latest version is $latest_version. Next version will be $next_version.${NC}" >&2
    echo "$next_version" # This is the actual return value to stdout
}

# Uploads a file, using the correct Supabase method for each scenario.
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"
    local allow_overwrite="$4"

    echo -e "${YELLOW}☁️  Uploading:${NC} $local_path -> $remote_path (Overwrite: $allow_overwrite)" >&2

    local http_code
    
    if [ "$allow_overwrite" = "true" ]; then
        # For 'latest' files: Use POST with x-upsert:true. This will create or update.
        http_code=$(curl -s -w "%{http_code}" \
            -o /dev/null \
            -X POST \
            "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
            -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
            -H "Content-Type: $content_type" \
            -H "x-upsert: true" \
            --data-binary "@$local_path")
    else
        # For versioned files: Use a simple POST. This will only create new files.
        # If the file exists, it will correctly return a 409 Conflict error.
        http_code=$(curl -s -w "%{http_code}" \
            -o /dev/null \
            -X POST \
            "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
            -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
            -H "Content-Type: $content_type" \
            --data-binary "@$local_path")
    fi
    
    # Check for success (200 OK) or conflict when we expect it
    if [ "$http_code" -eq 200 ]; then
        echo -e "${GREEN}✅ Upload successful (HTTP $http_code).${NC}" >&2
        return 0
    elif [ "$allow_overwrite" = "false" ] && [ "$http_code" -eq 409 ]; then
        echo -e "${RED}❌ Upload failed: Version already exists (HTTP $http_code).${NC}" >&2
        return 1
    elif [ "$http_code" -ne 200 ]; then
        echo -e "${RED}❌ Upload failed for $remote_path (HTTP $http_code).${NC}" >&2
        return 1
    fi
}

# Builds a module and uploads its artifacts
deploy_module() {
    local module_name="$1"
    local module_path="$PROJECT_ROOT/mock_drivers/$module_name"
    
    echo -e "\n${BLUE}--- Processing Module: $module_name ---${NC}" >&2
    cd "$module_path"

    echo "🔨 Building binary..." >&2
    local build_output
    build_output=$( (make clean && make build) 2>&1 )
    local build_result=$?
    
    if [ $build_result -ne 0 ]; then
        echo -e "${RED}❌ Build failed for module '$module_name'.${NC}" >&2
        echo -e "${YELLOW}--- Build Log ---${NC}" >&2
        echo "$build_output" >&2
        echo -e "${YELLOW}--- End Build Log ---${NC}" >&2
        return 1
    fi
    local binary_path="build/$module_name.bin"
    if [ ! -f "$binary_path" ]; then
        echo -e "${RED}❌ Build succeeded, but binary file was not found.${NC}" >&2
        return 1
    fi
    echo -e "${GREEN}✅ Build successful.${NC}" >&2

    local version=$(get_next_version "$module_name")
    local hash=$(sha256sum "$binary_path" | cut -d' ' -f1)
    local size=$(stat -c%s "$binary_path")

    echo "☁️  Uploading immutable versioned artifact ($version)..." >&2
    if ! upload_file "$binary_path" "$module_name/$version/$module_name.bin" "application/octet-stream" "false"; then return 1; fi

    echo "☁️  Updating mutable 'latest' pointer..." >&2
    if ! upload_file "$binary_path" "$module_name/latest/$module_name.bin" "application/octet-stream" "true"; then return 1; fi

    echo -e "${GREEN}🎉 Module '$module_name' deployed to cloud successfully!${NC}" >&2
    cd "$PROJECT_ROOT"
    
    # Output metadata to stdout for capture
    echo "$module_name:$version:$hash:$size"
}

# Updates the master manifest file
update_manifest() {
    local metadata="$1"
    IFS=':' read -r module_name version hash size <<< "$metadata"
    local manifest_path="temp_manifest.json"

    echo -e "\n${BLUE}--- Updating Master Manifest ---${NC}" >&2
    echo "📥 Downloading current manifest..." >&2
    curl -s -f -o "$manifest_path" \
        "$SUPABASE_URL/storage/v1/object/ota-modules/manifest.json" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" || echo "{}" > "$manifest_path"

    echo "✍️  Updating entry for '$module_name' to $version..." >&2
    jq \
      --arg module "$module_name" --arg ver "$version" --arg sha256 "$hash" --argjson sz "$size" \
      '.[$module] = { latest_version: $ver, sha256: $sha256, file_size: $sz }' \
      "$manifest_path" > "$manifest_path.tmp" && mv "$manifest_path.tmp" "$manifest_path"

    if ! upload_file "$manifest_path" "manifest.json" "application/json" "true"; then
        rm -f "$manifest_path"
        return 1
    fi
    
    echo -e "${GREEN}✅ Manifest updated successfully.${NC}" >&2
    rm -f "$manifest_path"
}

# --- Main Script Logic ---
main() {
    declare -A modules_to_build
    for file in $@; do
        if [[ $file == mock_drivers/* ]]; then
            modules_to_build[$(echo "$file" | cut -d'/' -f2)]=1
        fi
    done

    if [ ${#modules_to_build[@]} -eq 0 ]; then
        echo "✅ No changes in module directories. Nothing to deploy." >&2
        exit 0
    fi

    echo "📦 Found changes in modules: ${!modules_to_build[@]}" >&2
    for module in "${!modules_to_build[@]}"; do
        if module_metadata=$(deploy_module "$module"); then
            update_manifest "$module_metadata"
        else
            echo -e "${RED}❌ Deployment failed for module '$module'. Aborting.${NC}" >&2
            exit 1
        fi
    done
    echo -e "\n${GREEN}🎉 All changed modules deployed and manifest updated successfully!${NC}" >&2
}

# --- Entry Point ---
main "$@" 