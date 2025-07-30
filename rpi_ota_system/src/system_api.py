#!/usr/bin/env python3
"""
System API for Raspberry Pi OTA System
Replaces ESP32 system_api.h functionality for dynamically loaded modules
"""

import os
import time
import json
import logging
import psutil
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

from .hardware.gpio_controller import GPIOController, LEDState


@dataclass
class SensorReading:
    """Sensor reading data structure"""
    sensor_name: str
    value: float
    unit: str
    timestamp: float
    quality: str = "good"  # good, fair, poor, error


@dataclass
class SystemStatus:
    """System status information"""
    uptime: float
    cpu_usage: float
    memory_usage: float
    temperature: float
    disk_usage: float
    network_connected: bool
    last_update_check: float
    active_modules: List[str]
    error_count: int


class SystemAPI:
    """
    System API for dynamically loaded modules
    Provides logging, timing, GPIO, sensor reading, and data storage capabilities
    """
    
    def __init__(self, config: Dict[str, Any], gpio_controller: GPIOController):
        """
        Initialize System API
        
        Args:
            config: System configuration dictionary
            gpio_controller: GPIO controller instance
        """
        self.config = config
        self.gpio = gpio_controller
        self.logger = logging.getLogger(__name__)
        
        # Data storage
        self.data_storage: Dict[str, Any] = {}
        self.sensor_data: Dict[str, List[SensorReading]] = {}
        self.system_stats: Dict[str, Any] = {}
        
        # Timing and scheduling
        self.start_time = time.time()
        self.timers: Dict[str, float] = {}
        self.scheduled_tasks: Dict[str, Callable] = {}
        
        # Module communication
        self.module_data: Dict[str, Dict[str, Any]] = {}
        self.module_callbacks: Dict[str, List[Callable]] = {}
        
        # System monitoring
        self.monitoring_enabled = True
        self.stats_update_interval = 10.0  # seconds
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = 0.0
        
        # Start background monitoring
        self._start_system_monitoring()
        
        self.logger.info("System API initialized")
    
    # ==================== Logging Functions ====================
    
    def log_info(self, module_name: str, message: str):
        """
        Log info message for module
        
        Args:
            module_name: Name of the calling module
            message: Log message
        """
        module_logger = logging.getLogger(f"modules.{module_name}")
        module_logger.info(message)
    
    def log_warning(self, module_name: str, message: str):
        """Log warning message for module"""
        module_logger = logging.getLogger(f"modules.{module_name}")
        module_logger.warning(message)
    
    def log_error(self, module_name: str, message: str):
        """Log error message for module"""
        module_logger = logging.getLogger(f"modules.{module_name}")
        module_logger.error(message)
        self.error_count += 1
        self.last_error_time = time.time()
    
    def log_debug(self, module_name: str, message: str):
        """Log debug message for module"""
        module_logger = logging.getLogger(f"modules.{module_name}")
        module_logger.debug(message)
    
    # ==================== Timing Functions ====================
    
    def get_uptime(self) -> float:
        """
        Get system uptime in seconds
        
        Returns:
            Uptime in seconds
        """
        return time.time() - self.start_time
    
    def get_timestamp(self) -> float:
        """
        Get current timestamp
        
        Returns:
            Current Unix timestamp
        """
        return time.time()
    
    def get_datetime(self) -> datetime:
        """
        Get current datetime
        
        Returns:
            Current datetime object
        """
        return datetime.now()
    
    def start_timer(self, timer_name: str):
        """
        Start a named timer
        
        Args:
            timer_name: Name of the timer
        """
        self.timers[timer_name] = time.time()
    
    def get_timer(self, timer_name: str) -> Optional[float]:
        """
        Get elapsed time for named timer
        
        Args:
            timer_name: Name of the timer
            
        Returns:
            Elapsed time in seconds or None if timer not found
        """
        if timer_name in self.timers:
            return time.time() - self.timers[timer_name]
        return None
    
    def reset_timer(self, timer_name: str):
        """Reset named timer"""
        if timer_name in self.timers:
            self.timers[timer_name] = time.time()
    
    def sleep(self, seconds: float):
        """
        Sleep for specified seconds
        
        Args:
            seconds: Time to sleep
        """
        time.sleep(seconds)
    
    # ==================== GPIO Functions ====================
    
    def set_led_status(self, status: str):
        """
        Set LED status
        
        Args:
            status: Status string (normal, update_available, updating, success, error)
        """
        self.gpio.set_status_leds(status)
    
    def set_led(self, led_name: str, state: str, blink_rate: float = 1.0):
        """
        Set individual LED state
        
        Args:
            led_name: Name of the LED
            state: LED state (off, on, blink)
            blink_rate: Blink rate for blinking state
        """
        if state.lower() == 'off':
            self.gpio.set_led(led_name, LEDState.OFF)
        elif state.lower() == 'on':
            self.gpio.set_led(led_name, LEDState.ON)
        elif state.lower() == 'blink':
            self.gpio.set_led(led_name, LEDState.BLINK, blink_rate)
    
    def is_button_pressed(self, button_name: str) -> bool:
        """
        Check if button is pressed
        
        Args:
            button_name: Name of the button
            
        Returns:
            True if button is pressed
        """
        return self.gpio.is_button_pressed(button_name)
    
    def register_button_callback(self, button_name: str, callback: Callable, long_press: bool = False):
        """
        Register button callback
        
        Args:
            button_name: Name of the button
            callback: Callback function
            long_press: True for long press callback
        """
        self.gpio.register_button_callback(button_name, callback, long_press)
    
    # ==================== Sensor Functions ====================
    
    def read_sensor(self, sensor_name: str) -> Optional[SensorReading]:
        """
        Read sensor value (mock implementation)
        
        Args:
            sensor_name: Name of the sensor
            
        Returns:
            Sensor reading or None if sensor not found
        """
        try:
            # Mock sensor implementations
            timestamp = time.time()
            
            if sensor_name == "distance":
                # Mock distance sensor (HC-SR04)
                import random
                value = random.uniform(10.0, 300.0)  # cm
                return SensorReading("distance", value, "cm", timestamp)
            
            elif sensor_name == "temperature":
                # Mock temperature sensor
                import random
                value = random.uniform(20.0, 50.0)  # Celsius
                return SensorReading("temperature", value, "°C", timestamp)
            
            elif sensor_name == "cpu_temperature":
                # Real CPU temperature reading
                try:
                    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                        temp = float(f.read().strip()) / 1000.0
                    return SensorReading("cpu_temperature", temp, "°C", timestamp)
                except:
                    return SensorReading("cpu_temperature", 45.0, "°C", timestamp, "error")
            
            elif sensor_name == "speed":
                # Mock speed sensor
                import random
                value = random.uniform(0.0, 120.0)  # km/h
                return SensorReading("speed", value, "km/h", timestamp)
            
            else:
                self.log_warning("system_api", f"Unknown sensor: {sensor_name}")
                return None
                
        except Exception as e:
            self.log_error("system_api", f"Error reading sensor {sensor_name}: {e}")
            return None
    
    def store_sensor_reading(self, reading: SensorReading, max_history: int = 100):
        """
        Store sensor reading in history
        
        Args:
            reading: Sensor reading to store
            max_history: Maximum number of readings to keep
        """
        if reading.sensor_name not in self.sensor_data:
            self.sensor_data[reading.sensor_name] = []
        
        self.sensor_data[reading.sensor_name].append(reading)
        
        # Limit history size
        if len(self.sensor_data[reading.sensor_name]) > max_history:
            self.sensor_data[reading.sensor_name] = self.sensor_data[reading.sensor_name][-max_history:]
    
    def get_sensor_history(self, sensor_name: str, count: int = 10) -> List[SensorReading]:
        """
        Get sensor reading history
        
        Args:
            sensor_name: Name of the sensor
            count: Number of recent readings to return
            
        Returns:
            List of sensor readings
        """
        if sensor_name in self.sensor_data:
            return self.sensor_data[sensor_name][-count:]
        return []
    
    # ==================== Data Storage Functions ====================
    
    def store_data(self, key: str, value: Any, module_name: str = "system"):
        """
        Store data in system storage
        
        Args:
            key: Data key
            value: Data value
            module_name: Name of the module storing the data
        """
        if module_name not in self.module_data:
            self.module_data[module_name] = {}
        
        self.module_data[module_name][key] = {
            'value': value,
            'timestamp': time.time(),
            'type': type(value).__name__
        }
        
        self.log_debug("system_api", f"Stored data: {module_name}.{key}")
    
    def get_data(self, key: str, module_name: str = "system", default: Any = None) -> Any:
        """
        Get data from system storage
        
        Args:
            key: Data key
            module_name: Name of the module
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        if module_name in self.module_data and key in self.module_data[module_name]:
            return self.module_data[module_name][key]['value']
        return default
    
    def delete_data(self, key: str, module_name: str = "system") -> bool:
        """
        Delete data from storage
        
        Args:
            key: Data key
            module_name: Name of the module
            
        Returns:
            True if deleted, False if not found
        """
        if module_name in self.module_data and key in self.module_data[module_name]:
            del self.module_data[module_name][key]
            return True
        return False
    
    def get_all_module_data(self, module_name: str) -> Dict[str, Any]:
        """
        Get all data for a module
        
        Args:
            module_name: Name of the module
            
        Returns:
            Dictionary of all module data
        """
        if module_name in self.module_data:
            return {k: v['value'] for k, v in self.module_data[module_name].items()}
        return {}
    
    # ==================== System Status Functions ====================
    
    def get_system_status(self) -> SystemStatus:
        """
        Get comprehensive system status
        
        Returns:
            SystemStatus object
        """
        try:
            # CPU and memory usage
            cpu_usage = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Temperature
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temperature = float(f.read().strip()) / 1000.0
            except:
                temperature = 0.0
            
            # Network status (simplified)
            network_connected = self._check_network_connection()
            
            # Active modules
            active_modules = list(self.module_data.keys())
            
            return SystemStatus(
                uptime=self.get_uptime(),
                cpu_usage=cpu_usage,
                memory_usage=memory.percent,
                temperature=temperature,
                disk_usage=disk.percent,
                network_connected=network_connected,
                last_update_check=self.get_data('last_update_check', default=0.0),
                active_modules=active_modules,
                error_count=self.error_count
            )
            
        except Exception as e:
            self.log_error("system_api", f"Error getting system status: {e}")
            return SystemStatus(0, 0, 0, 0, 0, False, 0, [], self.error_count)
    
    def _check_network_connection(self) -> bool:
        """Check if network connection is available"""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False
    
    # ==================== Module Communication ====================
    
    def register_module_callback(self, event_name: str, callback: Callable, module_name: str):
        """
        Register callback for inter-module communication
        
        Args:
            event_name: Name of the event
            callback: Callback function
            module_name: Name of the registering module
        """
        if event_name not in self.module_callbacks:
            self.module_callbacks[event_name] = []
        
        self.module_callbacks[event_name].append({
            'callback': callback,
            'module': module_name
        })
        
        self.log_debug("system_api", f"Registered callback for {event_name} from {module_name}")
    
    def trigger_event(self, event_name: str, data: Any = None, source_module: str = "system"):
        """
        Trigger inter-module event
        
        Args:
            event_name: Name of the event
            data: Event data
            source_module: Name of the source module
        """
        if event_name in self.module_callbacks:
            for callback_info in self.module_callbacks[event_name]:
                try:
                    callback_info['callback'](data, source_module)
                except Exception as e:
                    self.log_error("system_api", f"Error in callback for {event_name}: {e}")
    
    # ==================== File Operations ====================
    
    def read_file(self, file_path: str) -> Optional[str]:
        """
        Read file content
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content or None if error
        """
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            self.log_error("system_api", f"Error reading file {file_path}: {e}")
            return None
    
    def write_file(self, file_path: str, content: str) -> bool:
        """
        Write content to file
        
        Args:
            file_path: Path to the file
            content: Content to write
            
        Returns:
            True if successful
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(content)
            return True
        except Exception as e:
            self.log_error("system_api", f"Error writing file {file_path}: {e}")
            return False
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists"""
        return os.path.exists(file_path)
    
    # ==================== Configuration Access ====================
    
    def get_config(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Configuration key path (e.g., 'system.log_level')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            keys = key_path.split('.')
            value = self.config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            
            return value
        except Exception:
            return default
    
    # ==================== Background Monitoring ====================
    
    def _start_system_monitoring(self):
        """Start background system monitoring"""
        if not self.monitoring_enabled:
            return
        
        def monitor_loop():
            while self.monitoring_enabled:
                try:
                    # Update system statistics
                    status = self.get_system_status()
                    self.system_stats = asdict(status)
                    
                    # Store temperature reading
                    temp_reading = self.read_sensor("cpu_temperature")
                    if temp_reading:
                        self.store_sensor_reading(temp_reading)
                    
                    # Check for critical conditions
                    if status.cpu_usage > 90:
                        self.log_warning("system_api", f"High CPU usage: {status.cpu_usage}%")
                    
                    if status.memory_usage > 90:
                        self.log_warning("system_api", f"High memory usage: {status.memory_usage}%")
                    
                    if status.temperature > 80:
                        self.log_warning("system_api", f"High temperature: {status.temperature}°C")
                    
                    time.sleep(self.stats_update_interval)
                    
                except Exception as e:
                    self.log_error("system_api", f"System monitoring error: {e}")
                    time.sleep(self.stats_update_interval)
        
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        self.logger.info("Started system monitoring thread")
    
    def cleanup(self):
        """Cleanup system API resources"""
        self.monitoring_enabled = False
        self.logger.info("System API cleanup completed")


# Example usage and testing
if __name__ == "__main__":
    import logging
    from .hardware.gpio_controller import GPIOController
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Mock configuration
    config = {
        'system': {
            'log_level': 'DEBUG',
            'main_loop_interval': 1.0
        }
    }
    
    # Test system API
    with GPIOController() as gpio:
        api = SystemAPI(config, gpio)
        
        # Test various functions
        api.log_info("test_module", "Testing system API")
        
        api.start_timer("test_timer")
        time.sleep(1)
        elapsed = api.get_timer("test_timer")
        print(f"Timer elapsed: {elapsed:.2f}s")
        
        # Test sensor reading
        temp_reading = api.read_sensor("temperature")
        if temp_reading:
            print(f"Temperature: {temp_reading.value} {temp_reading.unit}")
        
        # Test data storage
        api.store_data("test_key", "test_value", "test_module")
        value = api.get_data("test_key", "test_module")
        print(f"Stored value: {value}")
        
        # Test system status
        status = api.get_system_status()
        print(f"System status: CPU {status.cpu_usage}%, Memory {status.memory_usage}%")
        
        api.cleanup() 