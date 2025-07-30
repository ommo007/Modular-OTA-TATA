#!/usr/bin/env python3
"""
Module Loader for Raspberry Pi OTA System
Replaces ESP32 module_loader.cpp functionality using importlib
"""

import os
import sys
import time
import json
import hashlib
import threading
import importlib
import importlib.util
from typing import Dict, List, Optional, Any, Type
from pathlib import Path
import logging

from modules.base_module import BaseModule, ModuleState, ModuleInfo


class ModuleLoadError(Exception):
    """Exception raised when module loading fails"""
    pass


class ModuleManager:
    """
    Manages dynamically loaded modules
    Handles loading, unloading, reloading, and execution of Python modules
    """
    
    def __init__(self, system_api, config: Dict[str, Any]):
        """
        Initialize module manager
        
        Args:
            system_api: System API instance
            config: Module system configuration
        """
        self.system_api = system_api
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Module storage
        self.loaded_modules: Dict[str, BaseModule] = {}
        self.module_info: Dict[str, ModuleInfo] = {}
        self.module_configs: Dict[str, Dict[str, Any]] = {}
        self.module_file_hashes: Dict[str, str] = {}
        
        # Module execution
        self.module_threads: Dict[str, threading.Thread] = {}
        self.running = False
        self.update_intervals: Dict[str, float] = {}
        
        # Module paths
        self.modules_path = Path(config.get('base_path', './modules'))
        self.modules_path.mkdir(exist_ok=True)
        
        # Add modules path to Python path if not already there
        modules_str = str(self.modules_path.absolute())
        if modules_str not in sys.path:
            sys.path.insert(0, modules_str)
        
        # Load timeout
        self.load_timeout = config.get('load_timeout', 10)
        
        self.logger.info(f"Module manager initialized with path: {self.modules_path}")
    
    def start(self):
        """Start the module manager"""
        self.running = True
        self.logger.info("Module manager started")
    
    def stop(self):
        """Stop the module manager and unload all modules"""
        self.running = False
        
        # Stop all module threads
        for module_name in list(self.loaded_modules.keys()):
            self.unload_module(module_name)
        
        self.logger.info("Module manager stopped")
    
    def discover_modules(self) -> List[str]:
        """
        Discover available modules in the modules directory
        
        Returns:
            List of module names
        """
        modules = []
        
        try:
            for item in self.modules_path.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    # Check if module has __init__.py or main module file
                    init_file = item / '__init__.py'
                    main_file = item / f'{item.name}.py'
                    
                    if init_file.exists() or main_file.exists():
                        modules.append(item.name)
                        self.logger.debug(f"Discovered module: {item.name}")
            
            self.logger.info(f"Discovered {len(modules)} modules: {modules}")
            return modules
            
        except Exception as e:
            self.logger.error(f"Error discovering modules: {e}")
            return []
    
    def load_module(self, module_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Load a module dynamically
        
        Args:
            module_name: Name of the module to load
            config: Module configuration (optional)
            
        Returns:
            True if module loaded successfully
        """
        try:
            if module_name in self.loaded_modules:
                self.logger.warning(f"Module {module_name} is already loaded")
                return True
            
            self.logger.info(f"Loading module: {module_name}")
            
            # Find module file
            module_path = self._find_module_file(module_name)
            if not module_path:
                raise ModuleLoadError(f"Module file not found for {module_name}")
            
            # Calculate file hash for integrity checking
            file_hash = self._calculate_file_hash(module_path)
            self.module_file_hashes[module_name] = file_hash
            
            # Load module class
            module_class = self._load_module_class(module_name, module_path)
            if not module_class:
                raise ModuleLoadError(f"Failed to load module class for {module_name}")
            
            # Validate module class
            if not issubclass(module_class, BaseModule):
                raise ModuleLoadError(f"Module {module_name} does not inherit from BaseModule")
            
            # Create module instance
            module_config = config or self._get_default_module_config(module_name)
            module_instance = module_class(self.system_api, module_config)
            
            # Get module info
            module_info = module_instance.get_info()
            self.module_info[module_name] = module_info
            self.module_configs[module_name] = module_config
            
            # Validate module configuration
            if not module_instance.validate_config(module_config):
                raise ModuleLoadError(f"Invalid configuration for module {module_name}")
            
            # Initialize module
            if not module_instance.initialize():
                raise ModuleLoadError(f"Module {module_name} initialization failed")
            
            # Store module instance
            self.loaded_modules[module_name] = module_instance
            self.update_intervals[module_name] = module_info.update_interval
            
            # Start module execution thread
            self._start_module_thread(module_name)
            
            self.logger.info(f"Module {module_name} v{module_info.version} loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load module {module_name}: {e}")
            # Cleanup on failure
            if module_name in self.loaded_modules:
                del self.loaded_modules[module_name]
            if module_name in self.module_info:
                del self.module_info[module_name]
            return False
    
    def unload_module(self, module_name: str) -> bool:
        """
        Unload a module
        
        Args:
            module_name: Name of the module to unload
            
        Returns:
            True if module unloaded successfully
        """
        try:
            if module_name not in self.loaded_modules:
                self.logger.warning(f"Module {module_name} is not loaded")
                return True
            
            self.logger.info(f"Unloading module: {module_name}")
            
            module = self.loaded_modules[module_name]
            
            # Stop module thread
            self._stop_module_thread(module_name)
            
            # Deinitialize module
            try:
                module.deinitialize()
            except Exception as e:
                self.logger.error(f"Error during module {module_name} deinitialization: {e}")
            
            # Remove from storage
            del self.loaded_modules[module_name]
            del self.module_info[module_name]
            del self.module_configs[module_name]
            if module_name in self.update_intervals:
                del self.update_intervals[module_name]
            if module_name in self.module_file_hashes:
                del self.module_file_hashes[module_name]
            
            # Remove from Python module cache
            module_full_name = f"modules.{module_name}"
            if module_full_name in sys.modules:
                del sys.modules[module_full_name]
            
            self.logger.info(f"Module {module_name} unloaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unload module {module_name}: {e}")
            return False
    
    def reload_module(self, module_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Reload a module (unload and load again)
        
        Args:
            module_name: Name of the module to reload
            config: New module configuration (optional)
            
        Returns:
            True if module reloaded successfully
        """
        self.logger.info(f"Reloading module: {module_name}")
        
        # Store current config if none provided
        if config is None and module_name in self.module_configs:
            config = self.module_configs[module_name].copy()
        
        # Unload first
        if not self.unload_module(module_name):
            return False
        
        # Small delay to ensure cleanup
        time.sleep(0.1)
        
        # Load again
        return self.load_module(module_name, config)
    
    def update_module_config(self, module_name: str, new_config: Dict[str, Any]) -> bool:
        """
        Update module configuration dynamically
        
        Args:
            module_name: Name of the module
            new_config: New configuration
            
        Returns:
            True if configuration updated successfully
        """
        try:
            if module_name not in self.loaded_modules:
                self.logger.error(f"Module {module_name} is not loaded")
                return False
            
            module = self.loaded_modules[module_name]
            
            # Update configuration
            if module.configure(new_config):
                self.module_configs[module_name].update(new_config)
                self.logger.info(f"Configuration updated for module {module_name}")
                return True
            else:
                self.logger.error(f"Failed to update configuration for module {module_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating configuration for module {module_name}: {e}")
            return False
    
    def get_module_status(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        Get module status
        
        Args:
            module_name: Name of the module
            
        Returns:
            Module status dictionary or None if module not found
        """
        if module_name in self.loaded_modules:
            return self.loaded_modules[module_name].get_status()
        return None
    
    def get_all_modules_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all loaded modules
        
        Returns:
            Dictionary mapping module names to their status
        """
        status = {}
        for module_name, module in self.loaded_modules.items():
            status[module_name] = module.get_status()
        return status
    
    def pause_module(self, module_name: str) -> bool:
        """Pause module execution"""
        if module_name in self.loaded_modules:
            return self.loaded_modules[module_name].pause()
        return False
    
    def resume_module(self, module_name: str) -> bool:
        """Resume module execution"""
        if module_name in self.loaded_modules:
            return self.loaded_modules[module_name].resume()
        return False
    
    def check_module_integrity(self, module_name: str) -> bool:
        """
        Check if module file has been modified
        
        Args:
            module_name: Name of the module
            
        Returns:
            True if module file is unchanged
        """
        try:
            if module_name not in self.module_file_hashes:
                return False
            
            module_path = self._find_module_file(module_name)
            if not module_path:
                return False
            
            current_hash = self._calculate_file_hash(module_path)
            stored_hash = self.module_file_hashes[module_name]
            
            return current_hash == stored_hash
            
        except Exception as e:
            self.logger.error(f"Error checking integrity for module {module_name}: {e}")
            return False
    
    def _find_module_file(self, module_name: str) -> Optional[Path]:
        """Find the main module file"""
        module_dir = self.modules_path / module_name
        
        # Check for main module file
        main_file = module_dir / f"{module_name}.py"
        if main_file.exists():
            return main_file
        
        # Check for __init__.py
        init_file = module_dir / "__init__.py"
        if init_file.exists():
            return init_file
        
        return None
    
    def _load_module_class(self, module_name: str, module_path: Path) -> Optional[Type[BaseModule]]:
        """Load module class from file"""
        try:
            # Create module spec
            spec = importlib.util.spec_from_file_location(
                f"modules.{module_name}",
                module_path
            )
            
            if spec is None or spec.loader is None:
                self.logger.error(f"Could not create spec for module {module_name}")
                return None
            
            # Create and execute module
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"modules.{module_name}"] = module
            spec.loader.exec_module(module)
            
            # Find the module class (should inherit from BaseModule)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseModule) and 
                    attr is not BaseModule):
                    return attr
            
            self.logger.error(f"No BaseModule subclass found in {module_name}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error loading module class {module_name}: {e}")
            return None
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def _get_default_module_config(self, module_name: str) -> Dict[str, Any]:
        """Get default configuration for module"""
        # Check if module has config in main system config
        available_modules = self.config.get('available', [])
        for module_config in available_modules:
            if module_config.get('name') == module_name:
                return {
                    'enabled': module_config.get('enabled', True),
                    'version': module_config.get('version', '1.0.0')
                }
        
        return {'enabled': True, 'version': '1.0.0'}
    
    def _start_module_thread(self, module_name: str):
        """Start execution thread for module"""
        def module_execution_loop():
            module = self.loaded_modules[module_name]
            update_interval = self.update_intervals[module_name]
            
            self.logger.debug(f"Started execution thread for {module_name} (interval: {update_interval}s)")
            
            while (self.running and 
                   module_name in self.loaded_modules and 
                   module.state in [ModuleState.RUNNING, ModuleState.PAUSED]):
                
                try:
                    if module.state == ModuleState.RUNNING:
                        module._execute_update()
                    
                    time.sleep(update_interval)
                    
                except Exception as e:
                    self.logger.error(f"Error in module {module_name} execution: {e}")
                    module.set_state(ModuleState.ERROR, str(e))
                    break
            
            self.logger.debug(f"Execution thread for {module_name} terminated")
        
        thread = threading.Thread(target=module_execution_loop, daemon=True)
        thread.start()
        self.module_threads[module_name] = thread
    
    def _stop_module_thread(self, module_name: str):
        """Stop execution thread for module"""
        if module_name in self.module_threads:
            # Module thread will stop when module state changes or is removed
            thread = self.module_threads[module_name]
            thread.join(timeout=2.0)  # Wait up to 2 seconds
            del self.module_threads[module_name]
    
    def load_modules_from_config(self) -> int:
        """
        Load all modules specified in configuration
        
        Returns:
            Number of successfully loaded modules
        """
        loaded_count = 0
        available_modules = self.config.get('available', [])
        
        for module_config in available_modules:
            module_name = module_config.get('name')
            enabled = module_config.get('enabled', True)
            
            if enabled and module_name:
                if self.load_module(module_name, module_config):
                    loaded_count += 1
        
        self.logger.info(f"Loaded {loaded_count} modules from configuration")
        return loaded_count
    
    def save_module_manifest(self, file_path: str = None) -> bool:
        """
        Save current module state to manifest file
        
        Args:
            file_path: Path to save manifest (optional)
            
        Returns:
            True if saved successfully
        """
        try:
            if file_path is None:
                file_path = self.modules_path / "module_manifest.json"
            
            manifest = {
                'timestamp': time.time(),
                'modules': {}
            }
            
            for module_name, module in self.loaded_modules.items():
                info = self.module_info[module_name]
                status = module.get_status()
                
                manifest['modules'][module_name] = {
                    'name': info.name,
                    'version': info.version,
                    'state': status['state'],
                    'config': self.module_configs[module_name],
                    'file_hash': self.module_file_hashes.get(module_name, ''),
                    'metrics': status['metrics']
                }
            
            with open(file_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            self.logger.info(f"Module manifest saved to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving module manifest: {e}")
            return False


# Testing
if __name__ == "__main__":
    import logging
    from modules.base_module import ExampleModule
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Mock system API
    class MockSystemAPI:
        def log_info(self, module_name, message):
            print(f"INFO [{module_name}]: {message}")
        def log_warning(self, module_name, message):
            print(f"WARNING [{module_name}]: {message}")
        def log_error(self, module_name, message):
            print(f"ERROR [{module_name}]: {message}")
        def log_debug(self, module_name, message):
            print(f"DEBUG [{module_name}]: {message}")
        def store_data(self, key, value, module_name):
            pass
        def read_sensor(self, sensor_name):
            return None
    
    # Test module manager
    mock_api = MockSystemAPI()
    config = {
        'base_path': './modules',
        'load_timeout': 10,
        'available': [
            {'name': 'example_module', 'enabled': True, 'version': '1.0.0'}
        ]
    }
    
    manager = ModuleManager(mock_api, config)
    manager.start()
    
    print("Discovering modules...")
    modules = manager.discover_modules()
    print(f"Found modules: {modules}")
    
    print("\nTesting module loading...")
    success = manager.load_module('example_module')
    print(f"Load result: {success}")
    
    if success:
        print("\nModule status:")
        status = manager.get_module_status('example_module')
        print(status)
        
        time.sleep(2)
        
        print("\nUnloading module...")
        manager.unload_module('example_module')
    
    manager.stop() 