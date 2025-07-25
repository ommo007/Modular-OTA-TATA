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

# Function to upload file to Supabase
upload_file() {
    local local_path="$1"
    local remote_path="$2"
    local content_type="$3"
    
    echo -e "${YELLOW}📤 Uploading: $local_path → $remote_path${NC}"
    
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
    else
        echo -e "${RED}❌ Failed to upload $remote_path (HTTP $http_code)${NC}"
        return 1
    fi
}

# Function to delete existing file (for updates)
delete_file() {
    local remote_path="$1"
    
    echo -e "${YELLOW}🗑️  Deleting existing: $remote_path${NC}"
    
    response=$(curl -s -w "%{http_code}" \
        -X DELETE \
        "$SUPABASE_URL/storage/v1/object/ota-modules/$remote_path" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY")
    
    http_code="${response: -3}"
    
    if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 404 ]; then
        echo -e "${GREEN}✅ Cleared existing file${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  Could not delete existing file (HTTP $http_code)${NC}"
        return 0  # Continue anyway
    fi
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
    
    # Generate version and metadata
    VERSION="1.0.$(date +%s)-$(git rev-parse --short HEAD)"
    HASH=$(sha256sum "$binary_path" | cut -d' ' -f1)
    SIZE=$(stat -c%s "$binary_path")
    BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    COMMIT_HASH=$(git rev-parse HEAD)
    
    # Create metadata JSON
    metadata_path="$module_path/build/metadata.json"
    cat > "$metadata_path" << EOF
{
  "module_name": "$module_name",
  "version": "$VERSION",
  "sha256": "$HASH",
  "size": $SIZE,
  "build_time": "$BUILD_TIME",
  "commit_hash": "$COMMIT_HASH",
  "priority": "normal"
}
EOF
    
    echo -e "${GREEN}📝 Created metadata: v$VERSION ($SIZE bytes)${NC}"
    
    # Upload to versioned path
    echo -e "${BLUE}📤 Uploading versioned files...${NC}"
    delete_file "$module_name/$VERSION/$module_name.bin"
    upload_file "$binary_path" "$module_name/$VERSION/$module_name.bin" "application/octet-stream"
    
    delete_file "$module_name/$VERSION/metadata.json"
    upload_file "$metadata_path" "$module_name/$VERSION/metadata.json" "application/json"
    
    # Upload to latest path
    echo -e "${BLUE}📤 Updating latest files...${NC}"
    delete_file "$module_name/latest/$module_name.bin"
    upload_file "$binary_path" "$module_name/latest/$module_name.bin" "application/octet-stream"
    
    delete_file "$module_name/latest/metadata.json"
    upload_file "$metadata_path" "$module_name/latest/metadata.json" "application/json"
    
    echo -e "${GREEN}✅ Module $module_name deployed successfully${NC}"
    echo ""
    
    # Return to project root
    cd "$PROJECT_ROOT"
    
    # Return version for manifest update
    echo "$VERSION"
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
        IFS=':' read -r module_name version <<< "$module_data"
        
        # Use jq to update manifest
        jq --arg module "$module_name" --arg version "$version" \
           '.[$module] = {
             "latest_version": $version,
             "path": "/" + $module + "/",
             "last_updated": (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
             "description": "Updated via deployment script",
             "priority": "normal"
           }' "$manifest_path" > "$manifest_path.tmp" && mv "$manifest_path.tmp" "$manifest_path"
    done
    
    # Upload updated manifest
    delete_file "manifest.json"
    upload_file "$manifest_path" "manifest.json" "application/json"
    
    # Clean up
    rm -f "$manifest_path"
    
    echo -e "${GREEN}✅ Manifest updated${NC}"
}

# Main deployment logic
main() {
    local modules_to_deploy=()
    local deployed_modules=()
    
    # Check if specific modules were requested
    if [ $# -gt 0 ]; then
        modules_to_deploy=("$@")
    else
        # Deploy all modules by default
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
    
    if [ ${#modules_to_deploy[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No modules found to deploy${NC}"
        exit 0
    fi
    
    echo -e "${BLUE}📦 Modules to deploy: ${modules_to_deploy[*]}${NC}"
    echo ""
    
    # Deploy each module
    for module_name in "${modules_to_deploy[@]}"; do
        if version=$(deploy_module "$module_name"); then
            deployed_modules+=("$module_name:$version")
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
    done
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