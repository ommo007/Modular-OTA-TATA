#!/usr/bin/env python3
"""
OTA Updater for Raspberry Pi OTA System
Replaces ESP32 ota_updater.cpp functionality with Supabase integration
"""

import os
import json
import time
import hashlib
import shutil
import tempfile
import threading
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import logging

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Warning: Supabase client not available. Using HTTP fallback.")


class OTAUpdateError(Exception):
    """Exception raised during OTA update operations"""
    pass


class ModuleUpdate:
    """Represents a module update"""
    def __init__(self, name: str, version: str, url: str, hash_sha256: str, signature: str = None):
        self.name = name
        self.version = version
        self.url = url
        self.hash_sha256 = hash_sha256
        self.signature = signature
        self.downloaded_path: Optional[Path] = None
        self.verified = False


class OTAUpdater:
    """
    OTA Update Manager for Raspberry Pi
    Handles checking for updates, downloading modules, and applying updates securely
    """
    
    def __init__(self, system_api, module_manager, config: Dict[str, Any]):
        """
        Initialize OTA updater
        
        Args:
            system_api: System API instance
            module_manager: Module manager instance
            config: OTA configuration
        """
        self.system_api = system_api
        self.module_manager = module_manager
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.supabase_url = config.get('supabase', {}).get('url', '')
        self.supabase_key = config.get('supabase', {}).get('anon_key', '')
        self.service_role_key = config.get('supabase', {}).get('service_role_key', '')
        
        # Update settings
        self.check_interval = config.get('ota', {}).get('check_interval', 300)  # 5 minutes
        self.download_timeout = config.get('ota', {}).get('download_timeout', 120)
        self.backup_enabled = config.get('ota', {}).get('backup_enabled', True)
        self.backup_directory = Path(config.get('ota', {}).get('backup_directory', './backups'))
        
        # Security settings
        self.signature_verification = config.get('ota', {}).get('signature_verification', True)
        self.public_key_path = config.get('ota', {}).get('public_key_path', './config/public_key.pem')
        self.public_key = None
        
        # State
        self.update_in_progress = False
        self.last_check_time = 0.0
        self.available_updates: List[ModuleUpdate] = []
        self.update_thread: Optional[threading.Thread] = None
        
        # Supabase client
        self.supabase_client: Optional[Client] = None
        
        # Auto-update settings
        self.auto_update_enabled = config.get('ota', {}).get('auto_update', True)
        self.update_window_start = config.get('ota', {}).get('update_window', {}).get('start_hour', 2)
        self.update_window_end = config.get('ota', {}).get('update_window', {}).get('end_hour', 4)
        
        # Initialize
        self._initialize()
    
    def _initialize(self):
        """Initialize OTA updater"""
        try:
            # Create backup directory
            if self.backup_enabled:
                self.backup_directory.mkdir(parents=True, exist_ok=True)
            
            # Load public key for signature verification
            if self.signature_verification:
                self._load_public_key()
            
            # Initialize Supabase client
            if SUPABASE_AVAILABLE and self.supabase_url and self.supabase_key:
                try:
                    self.supabase_client = create_client(self.supabase_url, self.supabase_key)
                    self.logger.info("Supabase client initialized")
                except Exception as e:
                    self.logger.warning(f"Failed to initialize Supabase client: {e}")
            
            self.logger.info("OTA updater initialized")
            
        except Exception as e:
            self.logger.error(f"OTA updater initialization failed: {e}")
    
    def _load_public_key(self):
        """Load public key for signature verification"""
        try:
            if os.path.exists(self.public_key_path):
                with open(self.public_key_path, 'rb') as f:
                    self.public_key = serialization.load_pem_public_key(f.read())
                self.logger.info("Public key loaded for signature verification")
            else:
                self.logger.warning(f"Public key not found at {self.public_key_path}")
                if self.signature_verification:
                    self.signature_verification = False
                    self.logger.warning("Signature verification disabled due to missing public key")
        except Exception as e:
            self.logger.error(f"Failed to load public key: {e}")
            self.signature_verification = False
    
    def start_automatic_updates(self):
        """Start automatic update checking in background thread"""
        if self.update_thread and self.update_thread.is_alive():
            self.logger.warning("Automatic updates already running")
            return
        
        def update_loop():
            self.logger.info("Started automatic update checking")
            while True:
                try:
                    # Check if we're in the update window
                    if self.auto_update_enabled and self._is_in_update_window():
                        self.check_for_updates()
                        
                        if self.available_updates and not self.update_in_progress:
                            self.logger.info("Auto-applying available updates")
                            self.apply_updates()
                    
                    elif not self.auto_update_enabled:
                        # Still check for updates but don't apply automatically
                        self.check_for_updates()
                    
                    time.sleep(self.check_interval)
                    
                except Exception as e:
                    self.logger.error(f"Error in update loop: {e}")
                    time.sleep(self.check_interval)
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
    
    def _is_in_update_window(self) -> bool:
        """Check if current time is within the update window"""
        current_hour = datetime.now().hour
        
        if self.update_window_start <= self.update_window_end:
            # Normal case: 2 AM to 4 AM
            return self.update_window_start <= current_hour < self.update_window_end
        else:
            # Wrap-around case: 22 PM to 2 AM
            return current_hour >= self.update_window_start or current_hour < self.update_window_end
    
    def check_for_updates(self) -> List[ModuleUpdate]:
        """
        Check for available updates
        
        Returns:
            List of available updates
        """
        try:
            self.logger.info("Checking for updates...")
            self.last_check_time = time.time()
            
            # Get current manifest
            current_manifest = self._get_current_manifest()
            
            # Get remote manifest
            remote_manifest = self._get_remote_manifest()
            if not remote_manifest:
                self.logger.warning("Failed to get remote manifest")
                return []
            
            # Compare manifests and find updates
            self.available_updates = self._find_available_updates(current_manifest, remote_manifest)
            
            if self.available_updates:
                self.logger.info(f"Found {len(self.available_updates)} available updates")
                for update in self.available_updates:
                    self.logger.info(f"  - {update.name} v{update.version}")
                
                # Set LED to indicate updates available
                self.system_api.set_led_status("update_available")
            else:
                self.logger.info("No updates available")
                self.system_api.set_led_status("normal")
            
            # Store update check info
            self.system_api.store_data("last_update_check", self.last_check_time)
            self.system_api.store_data("available_updates_count", len(self.available_updates))
            
            return self.available_updates
            
        except Exception as e:
            self.logger.error(f"Error checking for updates: {e}")
            self.system_api.set_led_status("error")
            return []
    
    def _get_current_manifest(self) -> Dict[str, Any]:
        """Get current module manifest"""
        try:
            manifest = {
                'timestamp': time.time(),
                'device_id': self.config.get('device', {}).get('device_id', 'unknown'),
                'firmware_version': self.config.get('device', {}).get('firmware_version', '1.0.0'),
                'modules': {}
            }
            
            # Get module status from module manager
            module_status = self.module_manager.get_all_modules_status()
            
            for module_name, status in module_status.items():
                manifest['modules'][module_name] = {
                    'version': status.get('version', '1.0.0'),
                    'state': status.get('state', 'unknown')
                }
            
            return manifest
            
        except Exception as e:
            self.logger.error(f"Error getting current manifest: {e}")
            return {}
    
    def _get_remote_manifest(self) -> Optional[Dict[str, Any]]:
        """Get remote manifest from Supabase or HTTP"""
        try:
            if self.supabase_client:
                return self._get_manifest_from_supabase()
            else:
                return self._get_manifest_from_http()
        except Exception as e:
            self.logger.error(f"Error getting remote manifest: {e}")
            return None
    
    def _get_manifest_from_supabase(self) -> Optional[Dict[str, Any]]:
        """Get manifest from Supabase"""
        try:
            # Query firmware_manifest table
            device_id = self.config.get('device', {}).get('device_id', 'unknown')
            
            response = self.supabase_client.table('firmware_manifest').select('*').eq('device_id', device_id).execute()
            
            if response.data:
                manifest_data = response.data[0]
                self.logger.info("Retrieved manifest from Supabase")
                return manifest_data.get('manifest', {})
            else:
                # Try to get generic manifest
                response = self.supabase_client.table('firmware_manifest').select('*').eq('device_id', 'generic').execute()
                if response.data:
                    manifest_data = response.data[0]
                    self.logger.info("Retrieved generic manifest from Supabase")
                    return manifest_data.get('manifest', {})
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting manifest from Supabase: {e}")
            return None
    
    def _get_manifest_from_http(self) -> Optional[Dict[str, Any]]:
        """Get manifest from HTTP endpoint (fallback)"""
        try:
            # Use backend_manifest/manifest.json as fallback
            manifest_path = Path('./backend_manifest/manifest.json')
            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                self.logger.info("Retrieved manifest from local file")
                return manifest
            
            # Could also implement HTTP download here
            self.logger.warning("No manifest source available")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting manifest from HTTP: {e}")
            return None
    
    def _find_available_updates(self, current_manifest: Dict[str, Any], 
                               remote_manifest: Dict[str, Any]) -> List[ModuleUpdate]:
        """Find available updates by comparing manifests"""
        updates = []
        
        try:
            current_modules = current_manifest.get('modules', {})
            remote_modules = remote_manifest.get('modules', {})
            
            for module_name, remote_info in remote_modules.items():
                current_version = current_modules.get(module_name, {}).get('version', '0.0.0')
                remote_version = remote_info.get('version', '0.0.0')
                
                # Simple version comparison (could be enhanced with semantic versioning)
                if self._version_is_newer(remote_version, current_version):
                    update = ModuleUpdate(
                        name=module_name,
                        version=remote_version,
                        url=remote_info.get('download_url', ''),
                        hash_sha256=remote_info.get('sha256', ''),
                        signature=remote_info.get('signature', '')
                    )
                    updates.append(update)
                    self.logger.info(f"Update available: {module_name} {current_version} -> {remote_version}")
            
            return updates
            
        except Exception as e:
            self.logger.error(f"Error finding available updates: {e}")
            return []
    
    def _version_is_newer(self, remote_version: str, current_version: str) -> bool:
        """Simple version comparison"""
        try:
            remote_parts = [int(x) for x in remote_version.split('.')]
            current_parts = [int(x) for x in current_version.split('.')]
            
            # Pad with zeros if needed
            max_len = max(len(remote_parts), len(current_parts))
            remote_parts.extend([0] * (max_len - len(remote_parts)))
            current_parts.extend([0] * (max_len - len(current_parts)))
            
            return remote_parts > current_parts
            
        except Exception:
            # Fallback to string comparison
            return remote_version > current_version
    
    def apply_updates(self) -> bool:
        """
        Apply all available updates
        
        Returns:
            True if all updates applied successfully
        """
        if not self.available_updates:
            self.logger.info("No updates to apply")
            return True
        
        if self.update_in_progress:
            self.logger.warning("Update already in progress")
            return False
        
        try:
            self.update_in_progress = True
            self.system_api.set_led_status("updating")
            self.logger.info(f"Starting update process for {len(self.available_updates)} modules")
            
            success_count = 0
            
            for update in self.available_updates:
                if self._apply_single_update(update):
                    success_count += 1
                else:
                    self.logger.error(f"Failed to apply update for {update.name}")
            
            # Clear available updates
            self.available_updates = []
            
            if success_count == len(self.available_updates):
                self.logger.info("All updates applied successfully")
                self.system_api.set_led_status("success")
                return True
            else:
                self.logger.warning(f"Only {success_count}/{len(self.available_updates)} updates applied")
                self.system_api.set_led_status("error")
                return False
                
        except Exception as e:
            self.logger.error(f"Error applying updates: {e}")
            self.system_api.set_led_status("error")
            return False
        finally:
            self.update_in_progress = False
    
    def _apply_single_update(self, update: ModuleUpdate) -> bool:
        """Apply a single module update"""
        try:
            self.logger.info(f"Applying update for {update.name} v{update.version}")
            
            # Download the update
            if not self._download_update(update):
                return False
            
            # Verify the update
            if not self._verify_update(update):
                return False
            
            # Backup current module if enabled
            if self.backup_enabled:
                if not self._backup_module(update.name):
                    self.logger.warning(f"Failed to backup {update.name}, continuing anyway")
            
            # Apply the update
            if not self._install_update(update):
                # Try to restore from backup
                if self.backup_enabled:
                    self._restore_module(update.name)
                return False
            
            # Reload the module
            if not self._reload_module(update.name):
                self.logger.warning(f"Failed to reload {update.name} after update")
            
            self.logger.info(f"Successfully updated {update.name} to v{update.version}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error applying update for {update.name}: {e}")
            return False
    
    def _download_update(self, update: ModuleUpdate) -> bool:
        """Download update file"""
        try:
            self.logger.info(f"Downloading {update.name} v{update.version}")
            
            response = requests.get(update.url, timeout=self.download_timeout, stream=True)
            response.raise_for_status()
            
            # Create temporary file
            temp_dir = Path(tempfile.gettempdir()) / "rpi_ota_updates"
            temp_dir.mkdir(exist_ok=True)
            
            temp_file = temp_dir / f"{update.name}_{update.version}.py"
            
            # Download with progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        if downloaded % (total_size // 10) == 0:  # Log every 10%
                            self.logger.debug(f"Download progress: {progress:.1f}%")
            
            update.downloaded_path = temp_file
            self.logger.info(f"Downloaded {update.name} ({downloaded} bytes)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading {update.name}: {e}")
            return False
    
    def _verify_update(self, update: ModuleUpdate) -> bool:
        """Verify update integrity and signature"""
        try:
            if not update.downloaded_path or not update.downloaded_path.exists():
                self.logger.error(f"Downloaded file not found for {update.name}")
                return False
            
            # Verify SHA256 hash
            if not self._verify_hash(update):
                return False
            
            # Verify signature if enabled
            if self.signature_verification and update.signature:
                if not self._verify_signature(update):
                    return False
            
            update.verified = True
            self.logger.info(f"Update verified for {update.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error verifying update for {update.name}: {e}")
            return False
    
    def _verify_hash(self, update: ModuleUpdate) -> bool:
        """Verify SHA256 hash of downloaded file"""
        try:
            sha256_hash = hashlib.sha256()
            with open(update.downloaded_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            
            calculated_hash = sha256_hash.hexdigest()
            
            if calculated_hash.lower() == update.hash_sha256.lower():
                self.logger.debug(f"Hash verification passed for {update.name}")
                return True
            else:
                self.logger.error(f"Hash verification failed for {update.name}")
                self.logger.error(f"Expected: {update.hash_sha256}")
                self.logger.error(f"Calculated: {calculated_hash}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error verifying hash for {update.name}: {e}")
            return False
    
    def _verify_signature(self, update: ModuleUpdate) -> bool:
        """Verify digital signature of update"""
        try:
            if not self.public_key:
                self.logger.error("No public key available for signature verification")
                return False
            
            # Read file content
            with open(update.downloaded_path, 'rb') as f:
                file_content = f.read()
            
            # Decode signature from hex
            signature_bytes = bytes.fromhex(update.signature)
            
            # Verify signature
            try:
                self.public_key.verify(
                    signature_bytes,
                    file_content,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                self.logger.debug(f"Signature verification passed for {update.name}")
                return True
                
            except InvalidSignature:
                self.logger.error(f"Invalid signature for {update.name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error verifying signature for {update.name}: {e}")
            return False
    
    def _backup_module(self, module_name: str) -> bool:
        """Backup current module before update"""
        try:
            # Find current module file
            modules_path = Path(self.module_manager.modules_path)
            module_dir = modules_path / module_name
            
            if not module_dir.exists():
                self.logger.warning(f"Module directory not found: {module_dir}")
                return True  # Nothing to backup
            
            # Create backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{module_name}_{timestamp}"
            backup_path = self.backup_directory / backup_name
            
            shutil.copytree(module_dir, backup_path)
            
            self.logger.info(f"Backed up {module_name} to {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error backing up {module_name}: {e}")
            return False
    
    def _install_update(self, update: ModuleUpdate) -> bool:
        """Install the verified update"""
        try:
            modules_path = Path(self.module_manager.modules_path)
            module_dir = modules_path / update.name
            module_file = module_dir / f"{update.name}.py"
            
            # Create module directory if it doesn't exist
            module_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy updated file
            shutil.copy2(update.downloaded_path, module_file)
            
            # Set proper permissions
            os.chmod(module_file, 0o755)
            
            self.logger.info(f"Installed update for {update.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error installing update for {update.name}: {e}")
            return False
    
    def _reload_module(self, module_name: str) -> bool:
        """Reload module after update"""
        try:
            return self.module_manager.reload_module(module_name)
        except Exception as e:
            self.logger.error(f"Error reloading module {module_name}: {e}")
            return False
    
    def _restore_module(self, module_name: str) -> bool:
        """Restore module from backup"""
        try:
            # Find latest backup
            backups = list(self.backup_directory.glob(f"{module_name}_*"))
            if not backups:
                self.logger.error(f"No backup found for {module_name}")
                return False
            
            latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
            
            modules_path = Path(self.module_manager.modules_path)
            module_dir = modules_path / module_name
            
            # Remove current module
            if module_dir.exists():
                shutil.rmtree(module_dir)
            
            # Restore from backup
            shutil.copytree(latest_backup, module_dir)
            
            self.logger.info(f"Restored {module_name} from backup {latest_backup}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error restoring {module_name}: {e}")
            return False
    
    def force_update_check(self) -> List[ModuleUpdate]:
        """Force an immediate update check"""
        self.logger.info("Forcing update check")
        return self.check_for_updates()
    
    def get_update_status(self) -> Dict[str, Any]:
        """Get current update status"""
        return {
            'update_in_progress': self.update_in_progress,
            'last_check_time': self.last_check_time,
            'available_updates': len(self.available_updates),
            'available_update_list': [
                {'name': u.name, 'version': u.version} 
                for u in self.available_updates
            ],
            'auto_update_enabled': self.auto_update_enabled,
            'signature_verification': self.signature_verification,
            'backup_enabled': self.backup_enabled
        }


# Testing
if __name__ == "__main__":
    import logging
    from src.module_loader import ModuleManager
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Mock system API and module manager
    class MockSystemAPI:
        def log_info(self, module_name, message):
            print(f"INFO: {message}")
        def set_led_status(self, status):
            print(f"LED: {status}")
        def store_data(self, key, value, module_name="system"):
            print(f"Store: {key} = {value}")
    
    class MockModuleManager:
        def __init__(self):
            self.modules_path = "./modules"
        def get_all_modules_status(self):
            return {"test_module": {"version": "1.0.0", "state": "running"}}
        def reload_module(self, name):
            return True
    
    # Test configuration
    config = {
        'device': {'device_id': 'test_device', 'firmware_version': '1.0.0'},
        'ota': {
            'check_interval': 60,
            'auto_update': False,
            'signature_verification': True
        }
    }
    
    # Test OTA updater
    mock_api = MockSystemAPI()
    mock_manager = MockModuleManager()
    
    updater = OTAUpdater(mock_api, mock_manager, config)
    
    print("Checking for updates...")
    updates = updater.check_for_updates()
    print(f"Found {len(updates)} updates")
    
    print("Update status:")
    status = updater.get_update_status()
    print(status) 