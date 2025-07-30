#!/usr/bin/env python3
"""
Distance Sensor Module for Raspberry Pi OTA System
Converted from ESP32 C implementation (v1.1.0)
Outputs distance measurements in centimeters with calibration support
"""

import time
import math
from typing import Dict, Any, Optional
from modules.base_module import BaseModule, ModuleInfo, ModuleState


class DistanceSensorModule(BaseModule):
    """
    Distance Sensor Module - Measures distance using ultrasonic sensor
    Version 1.1.0: Outputs in centimeters with calibration functionality
    """
    
    def __init__(self, system_api, config: Dict[str, Any]):
        """Initialize Distance Sensor Module"""
        super().__init__(system_api, config)
        
        # Distance sensor state
        self.last_distance_reading = 50.0  # Default distance in cm
        self.sensor_calibrated = False
        self.calibration_offset = 0.0  # Calibration offset in cm
        
        # Sensor parameters
        self.max_range = 400.0  # 4 meter max range in cm
        self.min_range = 0.0    # Minimum range in cm
        
        # Timing
        self.last_log_time = 0.0
        self.log_interval = 10.0  # Log every 10 seconds
        
        # Detection thresholds
        self.default_detection_threshold = 30.0  # cm
    
    def get_info(self) -> ModuleInfo:
        """Get module information"""
        return ModuleInfo(
            name="distance_sensor",
            version="1.1.0",
            description="Ultrasonic distance sensor with calibration (outputs in centimeters)",
            author="Raspberry Pi OTA System",
            dependencies=[],
            config_schema={
                "max_range": {"type": "float", "default": 400.0, "min": 50.0, "max": 800.0},
                "min_range": {"type": "float", "default": 0.0, "min": 0.0, "max": 10.0},
                "log_interval": {"type": "float", "default": 10.0, "min": 1.0, "max": 60.0},
                "detection_threshold": {"type": "float", "default": 30.0, "min": 5.0, "max": 100.0},
                "auto_calibrate": {"type": "bool", "default": False}
            },
            update_interval=0.5,  # Update every 500ms for responsive distance readings
            priority=6  # Medium-high priority for obstacle detection
        )
    
    def initialize(self) -> bool:
        """Initialize the distance sensor module"""
        try:
            self.log_info("Initializing Distance Sensor module")
            self.set_state(ModuleState.INITIALIZING)
            
            # Load configuration
            self.max_range = self.get_config_value("max_range", 400.0)
            self.min_range = self.get_config_value("min_range", 0.0)
            self.log_interval = self.get_config_value("log_interval", 10.0)
            self.default_detection_threshold = self.get_config_value("detection_threshold", 30.0)
            auto_calibrate = self.get_config_value("auto_calibrate", False)
            
            # Initialize sensor state
            self.last_distance_reading = 50.0
            self.sensor_calibrated = False
            self.calibration_offset = 0.0
            
            # Load previous calibration if available
            saved_offset = self.system_api.get_data("calibration_offset", self.get_info().name)
            if saved_offset is not None:
                self.calibration_offset = saved_offset
                self.sensor_calibrated = True
                self.log_info(f"Loaded saved calibration offset: {self.calibration_offset:.2f} cm")
            
            # Auto-calibrate if requested
            if auto_calibrate:
                self.calibrate_sensor()
            
            self.set_state(ModuleState.RUNNING)
            self.log_info(f"Distance sensor initialized v{self.get_info().version} - outputs in CENTIMETERS")
            
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False
    
    def update(self) -> bool:
        """Update module - read and process distance sensor data"""
        try:
            # Read raw distance from system API (mock sensor)
            raw_distance = self._read_distance_sensor_raw()
            
            # Apply calibration offset and ensure it's in centimeters
            self.last_distance_reading = raw_distance + self.calibration_offset
            
            # Ensure reasonable bounds
            if self.last_distance_reading < self.min_range:
                self.last_distance_reading = self.min_range
            
            if self.last_distance_reading > self.max_range:
                self.last_distance_reading = self.max_range
            
            # Store the reading
            self.store_data("last_distance", self.last_distance_reading)
            self.store_data("last_update", time.time())
            
            # Log distance reading periodically
            current_time = time.time()
            if current_time - self.last_log_time > self.log_interval:
                self._log_distance_reading()
                self.last_log_time = current_time
            
            # Update LED status based on object detection
            if self.is_object_detected(self.default_detection_threshold):
                self.system_api.set_led_status("update_available")  # Yellow for object detected
            else:
                self.system_api.set_led_status("normal")  # Green for clear
            
            return True
            
        except Exception as e:
            self.log_error(f"Update failed: {e}")
            return False
    
    def deinitialize(self) -> bool:
        """Deinitialize the distance sensor module"""
        try:
            self.log_info("Deinitializing Distance Sensor module")
            self.set_state(ModuleState.STOPPING)
            
            # Save calibration data
            self.store_data("calibration_offset", self.calibration_offset)
            self.store_data("sensor_calibrated", self.sensor_calibrated)
            
            self.set_state(ModuleState.STOPPED)
            self.log_info("Distance sensor deinitialized")
            return True
            
        except Exception as e:
            self.set_state(ModuleState.ERROR, str(e))
            return False
    
    def _read_distance_sensor_raw(self) -> float:
        """Read raw distance from sensor (mock implementation)"""
        # Mock distance sensor reading - in real implementation, this would
        # use GPIO to trigger ultrasonic sensor and measure echo time
        
        # Simulate realistic HC-SR04 ultrasonic sensor readings
        import random
        
        # Simulate some variation in readings
        base_distance = 50.0 + random.uniform(-20.0, 100.0)  # 30-150 cm range
        
        # Add some noise (±1 cm)
        noise = random.uniform(-1.0, 1.0)
        
        return base_distance + noise
    
    def _log_distance_reading(self):
        """Log the current distance reading"""
        cm = int(self.last_distance_reading)
        decimal = int(abs(self.last_distance_reading * 10.0)) % 10
        
        self.log_info(f"Distance: {cm}.{decimal} cm (v1.1.0)")
        
        # Also store sensor reading in system API for other modules
        sensor_reading = self.system_api.read_sensor("distance")
        if sensor_reading:
            self.system_api.store_sensor_reading(sensor_reading)
    
    # ==================== Distance Sensor Interface ====================
    
    def get_distance(self) -> float:
        """
        Get current distance reading
        
        Returns:
            Distance in centimeters
        """
        return self.last_distance_reading
    
    def get_distance_mm(self) -> float:
        """
        Get current distance reading in millimeters
        
        Returns:
            Distance in millimeters
        """
        return self.last_distance_reading * 10.0
    
    def get_distance_m(self) -> float:
        """
        Get current distance reading in meters
        
        Returns:
            Distance in meters
        """
        return self.last_distance_reading / 100.0
    
    def calibrate_sensor(self, reference_distance: float = 30.0):
        """
        Calibrate the distance sensor
        
        Args:
            reference_distance: Known reference distance in cm (default 30 cm)
        """
        self.log_info("Calibrating distance sensor...")
        
        try:
            # Take multiple readings for better accuracy
            readings = []
            for i in range(10):
                reading = self._read_distance_sensor_raw()
                readings.append(reading)
                time.sleep(0.1)  # 100ms between readings
            
            # Calculate average reading
            avg_reading = sum(readings) / len(readings)
            
            # Calculate calibration offset
            self.calibration_offset = reference_distance - avg_reading
            self.sensor_calibrated = True
            
            # Store calibration data
            self.store_data("calibration_offset", self.calibration_offset)
            self.store_data("sensor_calibrated", self.sensor_calibrated)
            
            # Log results
            cm = int(self.calibration_offset)
            decimal = int(abs(self.calibration_offset * 100.0)) % 100
            
            self.log_info(f"Calibration complete. Offset: {cm}.{decimal:02d} cm")
            self.log_info(f"Average raw reading: {avg_reading:.2f} cm, Reference: {reference_distance:.1f} cm")
            
        except Exception as e:
            self.log_error(f"Calibration failed: {e}")
            self.sensor_calibrated = False
    
    def is_object_detected(self, threshold: float = None) -> bool:
        """
        Check if an object is detected within threshold distance
        
        Args:
            threshold: Detection threshold in cm (default uses configured threshold)
            
        Returns:
            True if object detected within threshold
        """
        if threshold is None:
            threshold = self.default_detection_threshold
        
        return self.last_distance_reading < threshold
    
    def get_closest_object_distance(self, num_readings: int = 5) -> float:
        """
        Get the closest object distance from multiple readings
        
        Args:
            num_readings: Number of readings to take
            
        Returns:
            Closest distance in cm
        """
        distances = []
        
        for _ in range(num_readings):
            raw_distance = self._read_distance_sensor_raw()
            calibrated_distance = raw_distance + self.calibration_offset
            distances.append(calibrated_distance)
            time.sleep(0.05)  # 50ms between readings
        
        return min(distances)
    
    def reset_calibration(self):
        """Reset sensor calibration"""
        self.calibration_offset = 0.0
        self.sensor_calibrated = False
        self.store_data("calibration_offset", self.calibration_offset)
        self.store_data("sensor_calibrated", self.sensor_calibrated)
        self.log_info("Sensor calibration reset")
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed module status"""
        base_status = super().get_status()
        
        # Add distance sensor specific status
        distance_sensor_status = {
            'last_distance_cm': self.last_distance_reading,
            'last_distance_mm': self.get_distance_mm(),
            'last_distance_m': self.get_distance_m(),
            'sensor_calibrated': self.sensor_calibrated,
            'calibration_offset': self.calibration_offset,
            'max_range': self.max_range,
            'min_range': self.min_range,
            'object_detected': self.is_object_detected(),
            'detection_threshold': self.default_detection_threshold
        }
        
        base_status.update(distance_sensor_status)
        return base_status
    
    def handle_event(self, event_name: str, data: Any, source_module: str) -> bool:
        """Handle inter-module events"""
        try:
            if event_name == "calibrate_distance_sensor":
                reference_distance = data.get("reference_distance", 30.0) if data else 30.0
                self.calibrate_sensor(reference_distance)
                return True
                
            elif event_name == "set_detection_threshold":
                new_threshold = data.get("threshold", 30.0) if data else 30.0
                self.default_detection_threshold = new_threshold
                self.store_data("detection_threshold", new_threshold)
                self.log_info(f"Detection threshold set to {new_threshold} cm")
                return True
                
            elif event_name == "reset_calibration":
                self.reset_calibration()
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
        
        def read_sensor(self, sensor_name):
            from system_api import SensorReading
            return SensorReading(sensor_name, 45.7, "cm", time.time())
        
        def store_sensor_reading(self, reading):
            print(f"Stored sensor reading: {reading.sensor_name} = {reading.value} {reading.unit}")
    
    # Test the module
    mock_api = MockSystemAPI()
    config = {
        "max_range": 400.0,
        "log_interval": 5.0,
        "detection_threshold": 25.0,
        "auto_calibrate": True
    }
    
    # Create and test module
    module = DistanceSensorModule(mock_api, config)
    print(f"Module: {module}")
    
    # Test lifecycle
    print("\nTesting module lifecycle:")
    print(f"Initialize: {module.initialize()}")
    
    # Test distance readings
    print("\nTesting distance readings:")
    for i in range(3):
        module.update()
        distance = module.get_distance()
        print(f"Reading {i+1}: {distance:.1f} cm ({module.get_distance_mm():.1f} mm, {module.get_distance_m():.3f} m)")
        print(f"Object detected: {module.is_object_detected()}")
        time.sleep(1)
    
    # Test calibration
    print("\nTesting calibration:")
    module.calibrate_sensor(25.0)
    
    # Test closest object detection
    print("\nTesting closest object detection:")
    closest = module.get_closest_object_distance(3)
    print(f"Closest object: {closest:.1f} cm")
    
    # Get status
    print(f"\nStatus: {module.get_status()}")
    
    print(f"\nDeinitialize: {module.deinitialize()}") 