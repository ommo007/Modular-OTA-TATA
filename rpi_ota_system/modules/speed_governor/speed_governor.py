#!/usr/bin/env python3
"""
Speed Governor Module for Raspberry Pi OTA System
Converted from ESP32 C implementation with highway speed limit fix (v1.1.1)
"""

import time
from typing import Dict, Any, Optional
from modules.base_module import BaseModule, ModuleInfo, ModuleState


class SpeedGovernorModule(BaseModule):
    """
    Speed Governor Module - Controls vehicle speed limits based on road conditions
    Version 1.1.1: Includes highway speed limit fix for TATA EV Nexon
    """
    
    def __init__(self, system_api, config: Dict[str, Any]):
        """Initialize Speed Governor Module"""
        super().__init__(system_api, config)
        
        # Speed governor state
        self.current_speed_limit = 40  # Default 40 km/h for city
        self.override_speed_limit = -1  # -1 means no override
        self.speed_limiting_active = True
        self.highway_speed_limit = 100  # NEW: Highway speed limit (fixes the TATA issue!)
        
        # Timing
        self.last_log_time = 0.0
        self.log_interval = 10.0  # Log every 10 seconds
        
        # Road condition constants
        self.ROAD_NORMAL = 0
        self.ROAD_HIGHWAY = 1
        self.ROAD_CITY = 2
        self.ROAD_SCHOOL_ZONE = 3
    
    def get_info(self) -> ModuleInfo:
        """Get module information"""
        return ModuleInfo(
            name="speed_governor",
            version="1.1.1",
            description="Vehicle speed governor with highway speed limit fix",
            author="Raspberry Pi OTA System",
            dependencies=[],
            config_schema={
                "current_speed_limit": {"type": "int", "default": 40, "min": 10, "max": 200},
                "highway_speed_limit": {"type": "int", "default": 100, "min": 60, "max": 200},
                "speed_limiting_active": {"type": "bool", "default": True},
                "log_interval": {"type": "float", "default": 10.0}
            },
            update_interval=1.0,  # Update every second
            priority=8  # High priority for safety
        )
    
    def initialize(self) -> bool:
        """Initialize the speed governor module"""
        try:
            self.log_info("Initializing Speed Governor module")
            self.set_state(ModuleState.INITIALIZING)
            
            # Load configuration
            self.current_speed_limit = self.get_config_value("current_speed_limit", 40)
            self.highway_speed_limit = self.get_config_value("highway_speed_limit", 100)
            self.speed_limiting_active = self.get_config_value("speed_limiting_active", True)
            self.log_interval = self.get_config_value("log_interval", 10.0)
            
            # Load saved data from previous runs
            saved_limit = self.system_api.get_data("speed_limit", self.get_info().name)
            if saved_limit is not None:
                self.current_speed_limit = saved_limit
                self.log_info(f"Loaded saved speed limit: {self.current_speed_limit} km/h")
            else:
                self.log_info(f"Using default speed limit: {self.current_speed_limit} km/h")
            
            # Load highway speed limit
            saved_highway_limit = self.system_api.get_data("highway_speed_limit", self.get_info().name)
            if saved_highway_limit is not None:
                self.highway_speed_limit = saved_highway_limit
            
            # Store initial state
            self.store_data("speed_limit", self.current_speed_limit)
            self.store_data("highway_speed_limit", self.highway_speed_limit)
            
            self.set_state(ModuleState.RUNNING)
            self.log_info(f"Speed Governor v{self.get_info().version} initialized "
                         f"(highway limit: {self.highway_speed_limit} km/h)")
            
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False
    
    def update(self) -> bool:
        """Update module - called periodically from main loop"""
        try:
            current_time = time.time()
            
            # Log status every log_interval seconds
            if current_time - self.last_log_time > self.log_interval:
                self._check_speed_violation()
                self.last_log_time = current_time
            
            # Update stored data
            self.store_data("last_update", current_time)
            self.store_data("speed_limiting_active", self.speed_limiting_active)
            
            return True
            
        except Exception as e:
            self.log_error(f"Update failed: {e}")
            return False
    
    def deinitialize(self) -> bool:
        """Deinitialize the speed governor module"""
        try:
            self.log_info("Deinitializing Speed Governor module")
            self.set_state(ModuleState.STOPPING)
            
            # Save current configuration
            self.store_data("speed_limit", self.current_speed_limit)
            self.store_data("highway_speed_limit", self.highway_speed_limit)
            
            self.set_state(ModuleState.STOPPED)
            self.log_info("Speed Governor module deinitialized")
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False
    
    def _check_speed_violation(self):
        """Check for speed violations and log warnings"""
        try:
            # Get mock vehicle data (in real implementation, this would come from CAN bus or sensors)
            vehicle_speed = self._get_vehicle_speed()
            vehicle_idle = self._is_vehicle_idle()
            
            if not vehicle_idle and self.speed_limiting_active:
                effective_limit = self.override_speed_limit if self.override_speed_limit > 0 else self.current_speed_limit
                
                if vehicle_speed > effective_limit:
                    self.log_warning(
                        f"SPEED VIOLATION: Vehicle speed {vehicle_speed} km/h exceeds limit {effective_limit} km/h"
                    )
                    # Set LED to warning state
                    self.system_api.set_led_status("error")
                else:
                    # Normal operation
                    self.system_api.set_led_status("normal")
        
        except Exception as e:
            self.log_error(f"Error checking speed violation: {e}")
    
    def _get_vehicle_speed(self) -> int:
        """Get current vehicle speed (mock implementation)"""
        # Mock vehicle speed - in real implementation, read from vehicle CAN bus
        import random
        return random.randint(30, 120)  # Random speed between 30-120 km/h
    
    def _is_vehicle_idle(self) -> bool:
        """Check if vehicle is idle (mock implementation)"""
        # Mock idle state - in real implementation, check engine/motor status
        import random
        return random.random() < 0.1  # 10% chance of being idle
    
    # ==================== Speed Governor Interface ====================
    
    def get_speed_limit(self, current_speed: int, road_conditions: int) -> int:
        """
        Get speed limit based on current conditions
        
        Args:
            current_speed: Current vehicle speed in km/h
            road_conditions: Road condition code (0=normal, 1=highway, 2=city, 3=school)
            
        Returns:
            Speed limit in km/h
        """
        # Check for override first
        if self.override_speed_limit > 0:
            self.log_debug(f"Using override speed limit: {self.override_speed_limit} km/h")
            return self.override_speed_limit
        
        # FIXED LOGIC - Version 1.1.0: Now properly handles highway conditions
        # This fixes the TATA EV Nexon highway issue!
        
        if road_conditions == self.ROAD_NORMAL:  # Normal conditions
            self.log_debug(f"Normal conditions, speed limit: {self.current_speed_limit} km/h")
            return self.current_speed_limit
            
        elif road_conditions == self.ROAD_HIGHWAY:  # Highway conditions - FIXED!
            # NEW: Allow higher speeds on highway
            self.log_info(f"Highway detected, allowing higher speed: {self.highway_speed_limit} km/h")
            return self.highway_speed_limit  # This fixes the 40 km/h highway problem!
            
        elif road_conditions == self.ROAD_CITY:  # City conditions
            city_limit = self.current_speed_limit - 10
            self.log_debug(f"City conditions, speed limit: {city_limit} km/h")
            return city_limit
            
        elif road_conditions == self.ROAD_SCHOOL_ZONE:  # School zone
            school_limit = 25  # Very low speed in school zones
            self.log_info(f"School zone detected, speed limit: {school_limit} km/h")
            return school_limit
        
        return self.current_speed_limit
    
    def set_speed_limit_override(self, new_limit: int):
        """
        Set speed limit override
        
        Args:
            new_limit: New speed limit in km/h, or -1 to clear override
        """
        self.override_speed_limit = new_limit
        
        if new_limit > 0:
            self.log_info(f"Speed limit override set to: {new_limit} km/h")
        else:
            self.log_info("Speed limit override cleared")
        
        # Store the override
        self.store_data("override_speed_limit", self.override_speed_limit)
    
    def is_speed_limiting_active(self) -> bool:
        """
        Check if speed limiting is active
        
        Returns:
            True if speed limiting is active
        """
        return self.speed_limiting_active
    
    def set_speed_limiting_active(self, active: bool):
        """
        Enable or disable speed limiting
        
        Args:
            active: True to enable speed limiting, False to disable
        """
        self.speed_limiting_active = active
        status = "enabled" if active else "disabled"
        self.log_info(f"Speed limiting {status}")
        self.store_data("speed_limiting_active", self.speed_limiting_active)
    
    def set_highway_speed_limit(self, limit: int):
        """
        Set highway speed limit
        
        Args:
            limit: Highway speed limit in km/h
        """
        if 60 <= limit <= 200:  # Reasonable highway speed limits
            self.highway_speed_limit = limit
            self.log_info(f"Highway speed limit set to: {limit} km/h")
            self.store_data("highway_speed_limit", self.highway_speed_limit)
        else:
            self.log_warning(f"Invalid highway speed limit: {limit} km/h (must be 60-200)")
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed module status"""
        base_status = super().get_status()
        
        # Add speed governor specific status
        speed_governor_status = {
            'current_speed_limit': self.current_speed_limit,
            'highway_speed_limit': self.highway_speed_limit,
            'override_speed_limit': self.override_speed_limit,
            'speed_limiting_active': self.speed_limiting_active,
            'vehicle_speed': self._get_vehicle_speed(),
            'vehicle_idle': self._is_vehicle_idle()
        }
        
        base_status.update(speed_governor_status)
        return base_status
    
    def handle_event(self, event_name: str, data: Any, source_module: str) -> bool:
        """Handle inter-module events"""
        try:
            if event_name == "road_condition_changed":
                road_condition = data.get("condition", 0)
                current_speed = data.get("speed", 50)
                new_limit = self.get_speed_limit(current_speed, road_condition)
                self.log_info(f"Road condition changed, new speed limit: {new_limit} km/h")
                return True
                
            elif event_name == "emergency_stop":
                self.set_speed_limit_override(0)
                self.log_warning("Emergency stop activated - speed override set to 0")
                return True
                
            elif event_name == "clear_override":
                self.set_speed_limit_override(-1)
                self.log_info("Speed limit override cleared by external command")
                return True
            
            return super().handle_event(event_name, data, source_module)
            
        except Exception as e:
            self.log_error(f"Error handling event {event_name}: {e}")
            return False


# For testing the module standalone
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
        
        def get_data(self, key, module_name, default=None):
            return self.data.get(f"{module_name}.{key}", default)
        
        def set_led_status(self, status):
            print(f"LED Status: {status}")
    
    # Test the module
    mock_api = MockSystemAPI()
    config = {
        "current_speed_limit": 50,
        "highway_speed_limit": 120,
        "speed_limiting_active": True
    }
    
    # Create and test module
    module = SpeedGovernorModule(mock_api, config)
    print(f"Module: {module}")
    
    # Test lifecycle
    print("\nTesting module lifecycle:")
    print(f"Initialize: {module.initialize()}")
    
    # Test speed limit logic
    print("\nTesting speed limit logic:")
    print(f"Normal road (60 km/h): {module.get_speed_limit(60, 0)} km/h")
    print(f"Highway (100 km/h): {module.get_speed_limit(100, 1)} km/h")  # Should return 120
    print(f"City (40 km/h): {module.get_speed_limit(40, 2)} km/h")
    print(f"School zone (30 km/h): {module.get_speed_limit(30, 3)} km/h")
    
    # Test override
    print("\nTesting override:")
    module.set_speed_limit_override(80)
    print(f"Highway with override: {module.get_speed_limit(100, 1)} km/h")  # Should return 80
    
    # Test update
    print(f"\nUpdate: {module.update()}")
    
    # Get status
    print(f"\nStatus: {module.get_status()}")
    
    print(f"\nDeinitialize: {module.deinitialize()}") 