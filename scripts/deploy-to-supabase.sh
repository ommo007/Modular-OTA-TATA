#!/bin/bash

# Deploys a pre-built binary to Supabase.
#
# Arguments:
#   $1: The module name (e.g., "speed_governor")
#   $2: The full path to the binary file to upload (e.g., "mock_drivers/speed_governor/build/speed_governor.bin")

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
SUPABASE_BUCKET="ota-modules"
UPLOAD_RETRIES=3
RETRY_DELAY=5

# --- Color Definitions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# --- Argument Validation ---
MODULE_NAME="$1"
LOCAL_BINARY_PATH="$2"

if [ -z "$MODULE_NAME" ] || [ -z "$LOCAL_BINARY_PATH" ]; then
    echo -e "${RED}❌ Error: Missing arguments. Usage: $0 <module-name> <path-to-binary>${NC}" >&2
    exit 1
fi
if [ ! -f "$LOCAL_BINARY_PATH" ]; then
    echo -e "${RED}❌ Error: Binary file not found at '$LOCAL_BINARY_PATH'.${NC}" >&2
    exit 1
fi
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo -e "${RED}❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY secrets.${NC}" >&2
    exit 1
fi

# --- Utility Functions ---
get_file_size() {
    stat -c%s "$1"
}

# Uploads a file with retries
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"
    local attempt=1

    echo -e "${YELLOW}☁️  Uploading: '$local_path' to '$remote_path'...${NC}" >&2
    while [ $attempt -le $UPLOAD_RETRIES ]; do
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "$SUPABASE_URL/storage/v1/object/$SUPABASE_BUCKET/$remote_path" \
            -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
            -H "Content-Type: $content_type" \
            -H "x-upsert: true" \ # Use upsert to allow overwriting latest.bin and manifest.json
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

    echo -e "${RED}❌ All upload attempts failed for '$remote_path'.${NC}" >&2
    return 1
}

# Fetches existing versions to determine the next one
get_next_version() {
    local latest_version
    latest_version=$(curl -s -f "$SUPABASE_URL/storage/v1/object/list/$SUPABASE_BUCKET?prefix=$MODULE_NAME/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" | \
        jq -r '.[] | .name' | \
        grep -oE "v[0-9]+\.[0-9]+\.[0-9]+" | sed 's/v//' | \
        sort -V | tail -n 1)

    if [ -z "$latest_version" ]; then
        echo "1.0.0" # Start with version 1.0.0
        return
    fi

    IFS='.' read -r major minor patch <<< "$latest_version"
    next_patch=$((patch + 1))
    echo "${major}.${minor}.${next_patch}"
}

update_manifest() {
    local metadata="$1"
    IFS=':' read -r module_name version hash size <<< "$metadata"
    local manifest_path="manifest.json"

    echo -e "\n${BLUE}--- Updating Master Manifest ---${NC}" >&2

    # Download existing manifest or create an empty one
    curl -s -f -o "$manifest_path" \
        "$SUPABASE_URL/storage/v1/object/public/$SUPABASE_BUCKET/manifest.json" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" || echo "{}" > "$manifest_path"

    # Update the manifest with the new module info
    jq --arg module "$module_name" --arg ver "v$version" --arg sha256 "$hash" --argjson sz "$size" \
      '.modules[$module] = { latest_version: $ver, sha256: $sha256, file_size: $sz, updated_at: now | todate }' \
      "$manifest_path" > "${manifest_path}.tmp" && mv "${manifest_path}.tmp" "$manifest_path"

    echo "✍️  Uploading updated manifest for '$module_name' to v$version..." >&2
    if ! upload_file "$manifest_path" "manifest.json" "application/json"; then
        rm -f "$manifest_path"
        return 1
    fi
    
    echo -e "${GREEN}✅ Manifest updated successfully.${NC}" >&2
    rm -f "$manifest_path"
}

# --- Main Logic ---
main() {
    echo -e "\n${BLUE}--- Deploying Module: $MODULE_NAME ---${NC}"

    # 1. Determine version and metadata
    local version=$(get_next_version)
    local hash=$(sha256sum "$LOCAL_BINARY_PATH" | cut -d' ' -f1)
    local size=$(get_file_size "$LOCAL_BINARY_PATH")
    local versioned_filename="${MODULE_NAME}-v${version}.bin"
    
    echo "📦 Version: v$version | Size: $size bytes | SHA256: $hash"

    # 2. Upload the new, immutable versioned binary
    if ! upload_file "$LOCAL_BINARY_PATH" "$MODULE_NAME/$versioned_filename" "application/octet-stream"; then 
        exit 1
    fi

    # 3. Upload the same binary as the mutable 'latest' pointer
    if ! upload_file "$LOCAL_BINARY_PATH" "$MODULE_NAME/latest.bin" "application/octet-stream"; then 
        exit 1
    fi

    # 4. Update the master manifest file
    local module_metadata="$MODULE_NAME:$version:$hash:$size"
    if ! update_manifest "$module_metadata"; then
        exit 1
    fi

    echo -e "${GREEN}🎉 Module '$MODULE_NAME' deployed successfully!${NC}"
}

main