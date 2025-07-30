#!/usr/bin/env python3
"""
Base Module Interface for Raspberry Pi OTA System
Replaces ESP32 ModuleInterface struct with Python classes
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class ModuleState(Enum):
    """Module state enumeration"""
    UNLOADED = "unloaded"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class ModuleInfo:
    """Module information structure"""
    name: str
    version: str
    description: str
    author: str
    dependencies: List[str]
    config_schema: Dict[str, Any]
    update_interval: float  # seconds
    priority: int  # 1-10, higher = more important


@dataclass
class ModuleMetrics:
    """Module performance metrics"""
    total_updates: int
    successful_updates: int
    failed_updates: int
    average_update_time: float
    last_update_time: float
    memory_usage: float
    cpu_time: float


class BaseModule(ABC):
    """
    Base class for all dynamically loadable modules
    All modules must inherit from this class and implement required methods
    """
    
    def __init__(self, system_api, config: Dict[str, Any]):
        """
        Initialize base module
        
        Args:
            system_api: System API instance for hardware/system access
            config: Module configuration dictionary
        """
        self.system_api = system_api
        self.config = config
        self.logger = logging.getLogger(f"modules.{self.get_info().name}")
        
        # Module state
        self.state = ModuleState.UNLOADED
        self.error_message = ""
        self.start_time = 0.0
        self.last_update_time = 0.0
        
        # Performance tracking
        self.metrics = ModuleMetrics(
            total_updates=0,
            successful_updates=0,
            failed_updates=0,
            average_update_time=0.0,
            last_update_time=0.0,
            memory_usage=0.0,
            cpu_time=0.0
        )
        
        # Module data storage
        self.module_data: Dict[str, Any] = {}
        
        self.logger.info(f"Base module initialized: {self.get_info().name}")
    
    @abstractmethod
    def get_info(self) -> ModuleInfo:
        """
        Get module information
        Must be implemented by all modules
        
        Returns:
            ModuleInfo with module details
        """
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the module
        Called once when module is loaded
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    def update(self) -> bool:
        """
        Update module (main execution function)
        Called periodically based on module's update_interval
        
        Returns:
            True if update successful, False otherwise
        """
        pass
    
    @abstractmethod
    def deinitialize(self) -> bool:
        """
        Deinitialize the module
        Called when module is being unloaded
        
        Returns:
            True if deinitialization successful, False otherwise
        """
        pass
    
    # ==================== Optional Override Methods ====================
    
    def configure(self, new_config: Dict[str, Any]) -> bool:
        """
        Update module configuration
        Override this method to handle dynamic configuration updates
        
        Args:
            new_config: New configuration dictionary
            
        Returns:
            True if configuration update successful
        """
        self.config.update(new_config)
        self.logger.info("Configuration updated")
        return True
    
    def pause(self) -> bool:
        """
        Pause module execution
        Override this method to implement pause functionality
        
        Returns:
            True if pause successful
        """
        if self.state == ModuleState.RUNNING:
            self.state = ModuleState.PAUSED
            self.logger.info("Module paused")
            return True
        return False
    
    def resume(self) -> bool:
        """
        Resume module execution
        Override this method to implement resume functionality
        
        Returns:
            True if resume successful
        """
        if self.state == ModuleState.PAUSED:
            self.state = ModuleState.RUNNING
            self.logger.info("Module resumed")
            return True
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get module status information
        Override this method to provide custom status information
        
        Returns:
            Dictionary with module status
        """
        info = self.get_info()
        return {
            'name': info.name,
            'version': info.version,
            'state': self.state.value,
            'uptime': time.time() - self.start_time if self.start_time > 0 else 0,
            'last_update': self.last_update_time,
            'error_message': self.error_message,
            'metrics': {
                'total_updates': self.metrics.total_updates,
                'successful_updates': self.metrics.successful_updates,
                'failed_updates': self.metrics.failed_updates,
                'success_rate': (self.metrics.successful_updates / max(1, self.metrics.total_updates)) * 100,
                'average_update_time': self.metrics.average_update_time
            }
        }
    
    def handle_event(self, event_name: str, data: Any, source_module: str) -> bool:
        """
        Handle inter-module events
        Override this method to handle events from other modules
        
        Args:
            event_name: Name of the event
            data: Event data
            source_module: Name of the source module
            
        Returns:
            True if event handled successfully
        """
        self.logger.debug(f"Received event {event_name} from {source_module}")
        return True
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate module configuration
        Override this method to implement custom configuration validation
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if configuration is valid
        """
        return True
    
    # ==================== Built-in Utility Methods ====================
    
    def set_state(self, new_state: ModuleState, error_message: str = ""):
        """
        Set module state
        
        Args:
            new_state: New module state
            error_message: Error message if state is ERROR
        """
        old_state = self.state
        self.state = new_state
        self.error_message = error_message
        
        if new_state == ModuleState.RUNNING and old_state != ModuleState.RUNNING:
            self.start_time = time.time()
        
        self.logger.info(f"State changed: {old_state.value} -> {new_state.value}")
        
        if error_message:
            self.logger.error(f"Error: {error_message}")
    
    def _execute_update(self) -> bool:
        """
        Internal method to execute update with performance tracking
        
        Returns:
            True if update successful
        """
        if self.state != ModuleState.RUNNING:
            return False
        
        start_time = time.time()
        self.metrics.total_updates += 1
        
        try:
            success = self.update()
            
            # Update metrics
            update_time = time.time() - start_time
            self.last_update_time = time.time()
            
            if success:
                self.metrics.successful_updates += 1
            else:
                self.metrics.failed_updates += 1
            
            # Update average update time
            total_successful = self.metrics.successful_updates
            if total_successful > 0:
                current_avg = self.metrics.average_update_time
                self.metrics.average_update_time = (
                    (current_avg * (total_successful - 1) + update_time) / total_successful
                )
            
            return success
            
        except Exception as e:
            self.metrics.failed_updates += 1
            self.set_state(ModuleState.ERROR, str(e))
            self.logger.error(f"Update failed: {e}")
            return False
    
    def store_data(self, key: str, value: Any):
        """
        Store data in module's local storage
        
        Args:
            key: Data key
            value: Data value
        """
        self.module_data[key] = value
        # Also store in system API for inter-module access
        self.system_api.store_data(key, value, self.get_info().name)
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """
        Get data from module's local storage
        
        Args:
            key: Data key
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        return self.module_data.get(key, default)
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with default
        
        Args:
            key: Configuration key
            default: Default value
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
    
    def log_info(self, message: str):
        """Log info message"""
        self.system_api.log_info(self.get_info().name, message)
    
    def log_warning(self, message: str):
        """Log warning message"""
        self.system_api.log_warning(self.get_info().name, message)
    
    def log_error(self, message: str):
        """Log error message"""
        self.system_api.log_error(self.get_info().name, message)
    
    def log_debug(self, message: str):
        """Log debug message"""
        self.system_api.log_debug(self.get_info().name, message)
    
    def trigger_event(self, event_name: str, data: Any = None):
        """
        Trigger inter-module event
        
        Args:
            event_name: Name of the event
            data: Event data
        """
        self.system_api.trigger_event(event_name, data, self.get_info().name)
    
    def register_event_callback(self, event_name: str, callback_method):
        """
        Register callback for inter-module events
        
        Args:
            event_name: Name of the event
            callback_method: Method to call when event occurs
        """
        self.system_api.register_module_callback(event_name, callback_method, self.get_info().name)
    
    def __str__(self) -> str:
        """String representation of module"""
        info = self.get_info()
        return f"{info.name} v{info.version} ({self.state.value})"
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        info = self.get_info()
        return (f"BaseModule(name='{info.name}', version='{info.version}', "
                f"state={self.state.value}, updates={self.metrics.total_updates})")


# Example module implementation for reference
class ExampleModule(BaseModule):
    """
    Example module implementation showing how to use BaseModule
    This is for reference and testing purposes
    """
    
    def get_info(self) -> ModuleInfo:
        """Get module information"""
        return ModuleInfo(
            name="example_module",
            version="1.0.0",
            description="Example module for testing",
            author="System",
            dependencies=[],
            config_schema={
                "update_interval": {"type": "float", "default": 1.0},
                "enabled": {"type": "bool", "default": True}
            },
            update_interval=1.0,
            priority=5
        )
    
    def initialize(self) -> bool:
        """Initialize the module"""
        try:
            self.log_info("Initializing example module")
            self.set_state(ModuleState.INITIALIZING)
            
            # Perform initialization tasks
            self.store_data("initialization_time", time.time())
            
            self.set_state(ModuleState.RUNNING)
            self.log_info("Example module initialized successfully")
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False
    
    def update(self) -> bool:
        """Update module"""
        try:
            # Perform module's main functionality
            current_time = time.time()
            self.store_data("last_update", current_time)
            
            # Example: Read a sensor
            sensor_reading = self.system_api.read_sensor("temperature")
            if sensor_reading:
                self.store_data("last_temperature", sensor_reading.value)
                self.log_debug(f"Temperature: {sensor_reading.value}°C")
            
            return True
            
        except Exception as e:
            self.log_error(f"Update failed: {e}")
            return False
    
    def deinitialize(self) -> bool:
        """Deinitialize the module"""
        try:
            self.log_info("Deinitializing example module")
            self.set_state(ModuleState.STOPPING)
            
            # Perform cleanup tasks
            self.store_data("deinitialization_time", time.time())
            
            self.set_state(ModuleState.STOPPED)
            self.log_info("Example module deinitialized successfully")
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False


# Testing
if __name__ == "__main__":
    import logging
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Mock system API for testing
    class MockSystemAPI:
        def __init__(self):
            self.data = {}
        
        def log_info(self, module_name, message):
            print(f"INFO [{module_name}]: {message}")
        
        def log_warning(self, module_name, message):
            print(f"WARNING [{module_name}]: {message}")
        
        def log_error(self, module_name, message):
            print(f"ERROR [{module_name}]: {message}")
        
        def log_debug(self, module_name, message):
            print(f"DEBUG [{module_name}]: {message}")
        
        def store_data(self, key, value, module_name):
            self.data[f"{module_name}.{key}"] = value
        
        def read_sensor(self, sensor_name):
            return None
        
        def trigger_event(self, event_name, data, source):
            print(f"Event {event_name} from {source}")
    
    # Test example module
    mock_api = MockSystemAPI()
    config = {"update_interval": 1.0, "enabled": True}
    
    module = ExampleModule(mock_api, config)
    print(f"Module info: {module}")
    
    # Test lifecycle
    print("\nTesting module lifecycle:")
    print(f"Initialize: {module.initialize()}")
    print(f"Update: {module._execute_update()}")
    print(f"Status: {module.get_status()}")
    print(f"Deinitialize: {module.deinitialize()}") 