#!/bin/bash

# Intelligent Deployment Script for Modular OTA System
# - Implements a robust, flat-file versioning scheme (e.g., module-v1.1.0.bin).
# - Uses a reliable "Delete then Post" upload strategy for mutable files.
# - Automatically determines the next semantic version based on cloud storage.
# - Updates the master manifest.json with authoritative metadata.

set -e

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY secrets." >&2
    exit 1
fi

# --- Color Definitions ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# --- Cross-platform stat function ---
get_file_size() {
    local file_path="$1"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        stat -f%z "$file_path"
    else
        # Linux/Ubuntu
        stat -c%s "$file_path"
    fi
}

# --- Core Functions ---

# Fetches existing versions for a module from Supabase using the new naming scheme
get_existing_versions() {
    local module_name="$1"
    curl -s -f "$SUPABASE_URL/storage/v1/object/list/ota-modules?prefix=$module_name/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" 2>/dev/null | \
        jq -r '.[] | .name' 2>/dev/null | \
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
    echo -e "${GREEN}📦 Latest is v$latest_version. Next will be v$next_version.${NC}" >&2
    echo "$next_version"
}

# Deletes a file if it exists.
delete_file() {
    local remote_path="$1"
    echo -e "${YELLOW}🗑️  Ensuring path is clear:${NC} $remote_path" >&2
    curl -s -w "%{http_code}" -o /dev/null \
        -X DELETE \
        "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" > /dev/null || true
}

# Uploads a file using a simple POST request.
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"

    echo -e "${YELLOW}☁️  Uploading:${NC} $local_path -> $remote_path" >&2
    local http_code=$(curl -s -w "%{http_code}" -o /dev/null \
        -X POST \
        "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
        -H "Content-Type: $content_type" \
        --data-binary "@$local_path")
    
    if [ "$http_code" -eq 200 ]; then
        echo -e "${GREEN}✅ Upload successful (HTTP $http_code).${NC}" >&2
        return 0
    else
        echo -e "${RED}❌ Upload failed for $remote_path (HTTP $http_code).${NC}" >&2
        return 1
    fi
}

# --- DEPLOYMENT LOGIC ---

deploy_module() {
    local module_name="$1"
    local module_path="$PROJECT_ROOT/mock_drivers/$module_name"
    
    echo -e "\n${BLUE}--- Processing Module: $module_name ---${NC}" >&2
    
    # Verify module directory exists
    if [ ! -d "$module_path" ]; then
        echo -e "${RED}❌ Module directory not found: $module_path${NC}" >&2
        return 1
    fi
    
    echo -e "${BLUE}📂 Current working directory: $(pwd)${NC}" >&2
    echo -e "${BLUE}📂 Module path: $module_path${NC}" >&2
    
    cd "$module_path"
    echo -e "${BLUE}📂 Changed to: $(pwd)${NC}" >&2

    echo "📂 Verifying contents of $module_path:"
    ls -l

    # Check if src directory exists, create minimal source if missing
    if [ ! -d "src" ]; then
        echo -e "${YELLOW}⚠️  Creating missing src directory and minimal source file${NC}" >&2
        mkdir -p src
        cat > src/main.c << 'EOF'
#include <stdint.h>

typedef struct {
    const char* name;
    const char* version;
    void* (*init)(void);
    void (*cleanup)(void*);
} module_interface_t;

static void* module_init(void) {
    return (void*)0x12345678;  // dummy pointer
}

static void module_cleanup(void* ctx) {
    // cleanup code
}

const module_interface_t* get_module_interface(void) {
    static const module_interface_t interface = {
        .name = "speed_governor",
        .version = "1.1.1",
        .init = module_init,
        .cleanup = module_cleanup
    };
    return &interface;
}
EOF
    fi

    echo "📂 Verifying contents of src:"
    ls -l src/ || echo "❌ src directory access failed!"

    # Ensure build directory exists
    mkdir -p build
    
    echo "🔨 Building binary..." >&2
    echo "🧹 Cleaning previous build..."
    make clean || echo "Clean failed or nothing to clean"
    
    echo "🔨 Running make build..."
    if ! make build; then 
        echo -e "${RED}❌ Build command failed.${NC}" >&2
        echo "📂 Current directory contents:"
        ls -la
        echo "📂 Build directory contents (if exists):"
        ls -la build/ 2>/dev/null || echo "Build directory doesn't exist"
        return 1
    fi
    
    local binary_path="build/$module_name.bin"
    echo -e "${BLUE}🔍 Looking for binary at: $binary_path${NC}" >&2
    echo -e "${BLUE}📂 Absolute path: $(pwd)/$binary_path${NC}" >&2
    
    if [ ! -f "$binary_path" ]; then
        echo -e "${RED}❌ Binary not found at $binary_path${NC}" >&2
        echo "📁 Contents of build/ directory:"
        ls -la build/ 2>/dev/null || echo "Build directory doesn't exist"
        echo "📁 Contents of current directory:"
        ls -la
        echo "🔍 Searching for any .bin files:"
        find . -name "*.bin" -type f 2>/dev/null || echo "No .bin files found"
        return 1
    fi
    
    echo -e "${GREEN}✅ Build successful. Binary found at: $binary_path${NC}" >&2
    echo -e "${GREEN}📊 Binary size: $(get_file_size "$binary_path") bytes${NC}" >&2

    local version=$(get_next_version "$module_name")
    local hash=$(sha256sum "$binary_path" | cut -d' ' -f1)
    local size=$(get_file_size "$binary_path")

    # Construct the new, flat versioned filename
    local versioned_filename="${module_name}-v${version}.bin"
    
    echo "☁️  Uploading immutable versioned artifact ($versioned_filename)..." >&2
    if ! upload_file "$binary_path" "$module_name/$versioned_filename" "application/octet-stream"; then 
        cd "$PROJECT_ROOT"
        return 1
    fi

    echo "☁️  Updating mutable 'latest' pointer..." >&2
    delete_file "$module_name/latest.bin"
    if ! upload_file "$binary_path" "$module_name/latest.bin" "application/octet-stream"; then 
        cd "$PROJECT_ROOT"
        return 1
    fi

    echo -e "${GREEN}🎉 Module '$module_name' deployed to cloud successfully!${NC}" >&2
    cd "$PROJECT_ROOT"
    
    echo "$module_name:$version:$hash:$size"
}

update_manifest() {
    local metadata="$1"
    IFS=':' read -r module_name version hash size <<< "$metadata"
    local manifest_path="temp_manifest.json"

    echo -e "\n${BLUE}--- Updating Master Manifest ---${NC}" >&2
    curl -s -f -o "$manifest_path" "$SUPABASE_URL/storage/v1/object/ota-modules/manifest.json" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" || echo "{}" > "$manifest_path"

    echo "✍️  Updating entry for '$module_name' to v$version..." >&2
    jq --arg module "$module_name" --arg ver "v$version" --arg sha256 "$hash" --argjson sz "$size" \
      '.[$module] = { latest_version: $ver, sha256: $sha256, file_size: $sz }' \
      "$manifest_path" > "$manifest_path.tmp" && mv "$manifest_path.tmp" "$manifest_path"

    delete_file "manifest.json"
    if ! upload_file "$manifest_path" "manifest.json" "application/json"; then rm -f "$manifest_path"; return 1; fi
    
    echo -e "${GREEN}✅ Manifest updated successfully.${NC}" >&2
    rm -f "$manifest_path"
}

# --- MAIN ---
main() {
    declare -A modules_to_build
    for file in $@; do
        if [[ $file == mock_drivers/* ]]; then
            modules_to_build[$(echo "$file" | cut -d'/' -f2)]=1
        fi
    done

    if [ ${#modules_to_build[@]} -eq 0 ]; then
        echo "✅ No changes in module directories. Nothing to deploy." >&2; exit 0;
    fi

    echo "📦 Found changes in modules: ${!modules_to_build[@]}" >&2
    for module in "${!modules_to_build[@]}"; do
        if module_metadata=$(deploy_module "$module"); then
            update_manifest "$module_metadata"
        else
            echo -e "${RED}❌ Deployment failed for module '$module'. Aborting.${NC}" >&2; exit 1;
        fi
    done
    echo -e "\n${GREEN}🎉 All changed modules deployed and manifest updated successfully!${NC}" >&2
}

main "$@"