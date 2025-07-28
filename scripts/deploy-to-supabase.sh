#!/bin/bash

# Deployment script for uploading OTA modules to Supabase
# Usage: ./scripts/deploy-to-supabase.sh

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    source "$PROJECT_ROOT/.env"
fi

# Check required environment variables
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: Missing required environment variables"
    echo "Please set SUPABASE_URL and SUPABASE_SERVICE_KEY"
    echo ""
    echo "Create a .env file in the project root with:"
    echo "SUPABASE_URL=https://xxxxxxxxxxx.supabase.co"
    echo "SUPABASE_SERVICE_KEY=eyJ..."
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Deploying OTA Modules to Supabase${NC}"
echo "Project: $SUPABASE_URL"
echo ""

# Function to get existing versions from Supabase
get_existing_versions() {
    local module_name="$1"
    
    response=$(curl -s \
        "$SUPABASE_URL/storage/v1/object/list/ota-modules?prefix=$module_name/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY")
    
    if [ $? -eq 0 ]; then
        # Extract version directories from the response and sort them
        echo "$response" | jq -r '.[] | select(.name | test("^[0-9]")) | .name' 2>/dev/null | sort -V || echo ""
    else
        echo ""
    fi
}

# Function to generate next available version
generate_next_version() {
    local module_name="$1"
    local base_version="$2"  # e.g., "1.1.0"
    
    # Get existing versions
    existing_versions=$(get_existing_versions "$module_name")
    
    if [ -z "$existing_versions" ]; then
        # No existing versions, use base version
        echo "$base_version"
        return 0
    fi
    
    # Find the highest patch version for this major.minor
    IFS='.' read -r major minor patch <<< "$base_version"
    highest_patch=$patch
    
    while IFS= read -r version; do
        if [[ "$version" =~ ^$major\.$minor\.([0-9]+) ]]; then
            current_patch="${BASH_REMATCH[1]}"
            if [ "$current_patch" -ge "$highest_patch" ]; then
                highest_patch=$((current_patch + 1))
            fi
        fi
    done <<< "$existing_versions"
    
    echo "$major.$minor.$highest_patch"
}

# Function to upload file to Supabase with conflict handling and auto-versioning
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"
    local allow_overwrite="${4:-false}"
    local module_name="${5:-}"
    local max_retries=3
    local retry_count=0
    
    echo -e "${YELLOW}📤 Uploading: $local_path → $remote_path${NC}"
    
    while [ $retry_count -lt $max_retries ]; do
        # Try to upload as new file
        response=$(curl -s -w "%{http_code}" \
            -X POST \
            "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
            -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
            -H "Content-Type: $content_type" \
            --data-binary "@$local_path")
        
        http_code="${response: -3}"
        
        if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
            echo -e "${GREEN}✅ Successfully uploaded $remote_path${NC}"
            return 0
        elif [ "$http_code" -eq 409 ] && [ "$allow_overwrite" = "true" ]; then
            # File exists, try to update it instead
            echo -e "${YELLOW}📝 File exists, attempting to update...${NC}"
            
            response=$(curl -s -w "%{http_code}" \
                -X PUT \
                "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
                -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
                -H "Content-Type: $content_type" \
                --data-binary "@$local_path")
            
            http_code="${response: -3}"
            
            if [ "$http_code" -eq 200 ]; then
                echo -e "${GREEN}✅ Successfully updated $remote_path${NC}"
                return 0
            else
                echo -e "${RED}❌ Failed to update $remote_path (HTTP $http_code)${NC}"
                return 1
            fi
        elif [ "$http_code" -eq 409 ] || [ "$http_code" -eq 400 ]; then
            # File conflict or bad request - likely version already exists
            echo -e "${YELLOW}⚠️  Conflict detected (HTTP $http_code): $remote_path${NC}"
            
            # If this is a versioned upload and we have module name, try to create new version
            if [ -n "$module_name" ] && [[ "$remote_path" == *"/$module_name/"* ]]; then
                retry_count=$((retry_count + 1))
                echo -e "${YELLOW}🔄 Attempt $retry_count: Creating new version to avoid conflict...${NC}"
                
                # Extract current version from path and increment it
                if [[ "$remote_path" =~ $module_name/([0-9]+\.[0-9]+\.[0-9]+)/ ]]; then
                    current_version="${BASH_REMATCH[1]}"
                    new_version=$(generate_next_version "$module_name" "$current_version")
                    new_remote_path=$(echo "$remote_path" | sed "s|$module_name/$current_version/|$module_name/$new_version/|")
                    
                    echo -e "${BLUE}🆕 Trying new version: $current_version → $new_version${NC}"
                    remote_path="$new_remote_path"
                    
                    # Update the global VERSION variable for this deployment
                    VERSION="$new_version"
                    continue
                fi
            fi
            
            if [ "$allow_overwrite" = "false" ]; then
                echo -e "${YELLOW}⚠️  File already exists: $remote_path (skipping to avoid conflicts)${NC}"
                return 0
            else
                echo -e "${RED}❌ Upload failed after $retry_count attempts${NC}"
                return 1
            fi
        else
            echo -e "${RED}❌ Failed to upload $remote_path (HTTP $http_code)${NC}"
            echo "Response: ${response%???}"  # Remove last 3 chars (http code)
            return 1
        fi
    done
    
    echo -e "${RED}❌ Failed to upload after $max_retries attempts${NC}"
    return 1
}

# Function to list existing versions of a module
list_module_versions() {
    local module_name="$1"
    
    echo -e "${BLUE}📋 Checking existing versions for $module_name...${NC}"
    
    response=$(curl -s \
        "$SUPABASE_URL/storage/v1/object/list/ota-modules?prefix=$module_name/" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY")
    
    if [ $? -eq 0 ]; then
        # Extract version directories from the response
        versions=$(echo "$response" | jq -r '.[] | select(.name | test("^[0-9]")) | .name' 2>/dev/null || echo "")
        if [ -n "$versions" ]; then
            echo -e "${GREEN}📦 Existing versions found:${NC}"
            echo "$versions" | while read -r version; do
                echo "  • $version"
            done
        else
            echo -e "${YELLOW}📦 No existing versions found (this will be the first)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Could not check existing versions${NC}"
    fi
    echo ""
}

# Function to build and upload module
deploy_module() {
    local module_name="$1"
    local module_path="$PROJECT_ROOT/mock_drivers/$module_name"
    
    if [ ! -d "$module_path" ]; then
        echo -e "${RED}❌ Module directory not found: $module_path${NC}"
        return 1
    fi
    
    echo -e "${BLUE}🔨 Building module: $module_name${NC}"
    
    # Check existing versions in cloud
    list_module_versions "$module_name"
    
    # Build the module
    cd "$module_path"
    if ! make clean && make build; then
        echo -e "${RED}❌ Failed to build module: $module_name${NC}"
        return 1
    fi
    
    # Check if binary exists
    binary_path="$module_path/build/$module_name.bin"
    if [ ! -f "$binary_path" ]; then
        echo -e "${RED}❌ Binary not found: $binary_path${NC}"
        return 1
    fi
    
    # Generate version number
    if [ -n "${GITHUB_RUN_NUMBER:-}" ]; then
        # Use GitHub run number for CI/CD builds
        VERSION="1.1.${GITHUB_RUN_NUMBER}"
        echo -e "${GREEN}📋 Using GitHub run number for version: $VERSION${NC}"
    else
        # Use semantic versioning based on existing versions in cloud for manual deploys
        echo -e "${BLUE}🔍 Checking for existing versions in cloud...${NC}"
        BASE_VERSION="1.1.0"  # Default starting version
        VERSION=$(generate_next_version "$module_name" "$BASE_VERSION")
        echo -e "${GREEN}📋 Generated semantic version: $VERSION${NC}"
    fi
    HASH=$(sha256sum "$binary_path" | cut -d' ' -f1)
    SIZE=$(stat -c%s "$binary_path")
    BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    COMMIT_HASH=$(git rev-parse HEAD)
    
    # Create metadata JSON with signature placeholder
    metadata_path="$module_path/build/metadata.json"
    cat > "$metadata_path" << EOF
{
  "module_name": "$module_name",
  "version": "$VERSION",
  "sha256": "$HASH",
  "signature": "placeholder-for-demo-signature",
  "size": $SIZE,
  "build_time": "$BUILD_TIME",
  "commit_hash": "$COMMIT_HASH",
  "priority": "normal",
  "deployment_strategy": "versioned_cloud_storage"
}
EOF
    
    echo -e "${GREEN}📝 Created metadata: v$VERSION ($SIZE bytes)${NC}"
    
    # Upload to versioned path (immutable - auto-version on conflict)
    echo -e "${BLUE}📤 Uploading versioned files (v$VERSION)...${NC}"
    ORIGINAL_VERSION="$VERSION"
    if ! upload_file "$binary_path" "$module_name/$VERSION/$module_name.bin" "application/octet-stream" "false" "$module_name"; then
        echo -e "${RED}❌ Failed to upload versioned binary${NC}"
        return 1
    fi
    
    # If version was updated during upload, recreate metadata with correct version
    if [ "$VERSION" != "$ORIGINAL_VERSION" ]; then
        echo -e "${YELLOW}📝 Version was updated to $VERSION, recreating metadata...${NC}"
        cat > "$metadata_path" << EOF
{
  "module_name": "$module_name",
  "version": "$VERSION",
  "sha256": "$HASH",
  "signature": "placeholder-for-demo-signature",
  "size": $SIZE,
  "build_time": "$BUILD_TIME",
  "commit_hash": "$COMMIT_HASH",
  "priority": "normal",
  "deployment_strategy": "versioned_cloud_storage"
}
EOF
    fi
    
    if ! upload_file "$metadata_path" "$module_name/$VERSION/metadata.json" "application/json" "false" "$module_name"; then
        echo -e "${RED}❌ Failed to upload versioned metadata${NC}"
        return 1
    fi
    
    # Upload to latest path (allow overwrite - this is the "current" pointer)
    echo -e "${BLUE}📤 Updating latest pointers...${NC}"
    if ! upload_file "$binary_path" "$module_name/latest/$module_name.bin" "application/octet-stream" "true"; then
        echo -e "${RED}❌ Failed to update latest binary${NC}"
        return 1
    fi
    
    if ! upload_file "$metadata_path" "$module_name/latest/metadata.json" "application/json" "true"; then
        echo -e "${RED}❌ Failed to update latest metadata${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ Module $module_name deployed successfully${NC}"
    echo ""
    
    # Return to project root
    cd "$PROJECT_ROOT"
    
    # Return full metadata for manifest update (format: module_name:version:hash:size)
    echo "$module_name:$VERSION:$HASH:$SIZE"
}

# Function to update manifest
update_manifest() {
    local modules=("$@")
    
    echo -e "${BLUE}📋 Updating manifest...${NC}"
    
    # Download current manifest (or create empty)
    manifest_path="$PROJECT_ROOT/temp_manifest.json"
    if ! curl -s -o "$manifest_path" \
        "$SUPABASE_URL/storage/v1/object/ota-modules/manifest.json" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY"; then
        echo "{}" > "$manifest_path"
    fi
    
    # Update manifest with new versions
    for module_data in "${modules[@]}"; do
        # Parse the new metadata format: module_name:version:hash:size
        IFS=':' read -r module_name version hash size <<< "$module_data"
        
        echo -e "${BLUE}📝 Updating manifest entry for $module_name v$version${NC}"
        
        # Use jq to update manifest with complete metadata
        jq --arg module "$module_name" \
           --arg version "$version" \
           --arg sha256 "$hash" \
           --argjson size "$size" \
           '.[$module] = {
             "latest_version": $version,
             "sha256": $sha256,
             "file_size": $size,
             "path": "/" + $module + "/",
             "last_updated": (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
             "description": "Updated via deployment script",
             "priority": "normal"
           }' "$manifest_path" > "$manifest_path.tmp" && mv "$manifest_path.tmp" "$manifest_path"
    done
    
    # Upload updated manifest (allow overwrite since this is the central index)
    if ! upload_file "$manifest_path" "manifest.json" "application/json" "true"; then
        echo -e "${RED}❌ Failed to update manifest${NC}"
        return 1
    fi
    
    # Clean up
    rm -f "$manifest_path"
    
    echo -e "${GREEN}✅ Manifest updated${NC}"
}

# Function to detect changed modules from environment or arguments
detect_changed_modules() {
    local modules_to_deploy=()
    
    # Check if specific modules were requested as arguments
    if [ $# -gt 0 ]; then
        # Convert file paths to module names
        for file in "$@"; do
            if [[ $file == mock_drivers/* ]]; then
                module_name=$(echo "$file" | cut -d'/' -f2)
                modules_to_deploy+=("$module_name")
            fi
        done
    else
        # Check if we have changed files from GitHub Actions environment
        if [ -n "${GITHUB_ACTIONS:-}" ] && [ -n "${GITHUB_EVENT_PATH:-}" ]; then
            echo -e "${BLUE}🔍 Detecting changes from GitHub Actions context...${NC}"
            # In GitHub Actions, we can get changed files from the context
            # This is a fallback - normally files should be passed as arguments
        fi
        
        # If no specific changes, deploy all modules (fallback behavior)
        if [ ${#modules_to_deploy[@]} -eq 0 ]; then
            echo -e "${YELLOW}⚠️  No specific changes detected, scanning all modules...${NC}"
            for module_dir in "$PROJECT_ROOT"/mock_drivers/*/; do
                if [ -d "$module_dir" ]; then
                    module_name=$(basename "$module_dir")
                    # Skip v2 directories (they're updates, not separate modules)
                    if [[ ! "$module_name" =~ _v[0-9]+$ ]]; then
                        modules_to_deploy+=("$module_name")
                    fi
                fi
            done
        fi
    fi
    
    # Remove duplicates
    printf '%s\n' "${modules_to_deploy[@]}" | sort -u
}

# Main deployment logic
main() {
    local deployed_modules=()
    
    # Detect which modules to deploy
    readarray -t modules_to_deploy < <(detect_changed_modules "$@")
    
    if [ ${#modules_to_deploy[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No modules found to deploy${NC}"
        exit 0
    fi
    
    echo -e "${BLUE}📦 Modules to deploy: ${modules_to_deploy[*]}${NC}"
    echo ""
    
    # Deploy each module
    for module_name in "${modules_to_deploy[@]}"; do
        # Execute deploy_module and capture full metadata string (name:version:hash:size)
        if module_metadata=$(deploy_module "$module_name"); then
            deployed_modules+=("$module_metadata")
        else
            echo -e "${RED}❌ Failed to deploy module: $module_name${NC}"
            exit 1
        fi
    done
    
    # Update manifest with all deployed modules
    if [ ${#deployed_modules[@]} -gt 0 ]; then
        update_manifest "${deployed_modules[@]}"
    fi
    
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
    echo ""
    echo -e "${BLUE}📊 Deployment Summary:${NC}"
    for module_data in "${deployed_modules[@]}"; do
        IFS=':' read -r module_name version <<< "$module_data"
        echo -e "  • $module_name: $version"
        echo -e "    📁 Versioned: /$module_name/$version/"
        echo -e "    🔗 Latest: /$module_name/latest/"
    done
    echo ""
    echo -e "${BLUE}📋 Version Control Strategy:${NC}"
    echo -e "  • Versioned files are immutable (never overwritten)"
    echo -e "  • Latest symlinks are updated to point to new versions"
    echo -e "  • Each deployment creates a unique version identifier"
    echo -e "  • Conflicts are handled gracefully with fallback strategies"
    echo ""
    echo -e "${BLUE}🔗 Supabase Storage: $SUPABASE_URL/dashboard/project/_/storage/buckets/ota-modules${NC}"
}

# Check dependencies
check_dependencies() {
    local missing_deps=()
    
    if ! command -v curl >/dev/null 2>&1; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        missing_deps+=("jq")
    fi
    
    if ! command -v make >/dev/null 2>&1; then
        missing_deps+=("make")
    fi
    
    if ! command -v git >/dev/null 2>&1; then
        missing_deps+=("git")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo -e "${RED}❌ Missing required dependencies: ${missing_deps[*]}${NC}"
        echo ""
        echo "Please install the missing dependencies:"
        echo "  Ubuntu/Debian: sudo apt-get install ${missing_deps[*]}"
        echo "  macOS: brew install ${missing_deps[*]}"
        echo "  Windows: Install via package manager or download binaries"
        exit 1
    fi
}

# Script entry point
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    # Check dependencies first
    check_dependencies
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Run main deployment
    main "$@"
fi 