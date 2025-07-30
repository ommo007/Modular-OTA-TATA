#!/usr/bin/env python3
"""
Main Application for Raspberry Pi OTA System
Converts ESP32 main.cpp functionality to Python with state machine
"""

import os
import sys
import time
import signal
import logging
import threading
import yaml
from typing import Dict, Any, Optional
from enum import Enum
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from system_api import SystemAPI
from module_loader import ModuleManager
from ota_updater import OTAUpdater
from hardware.gpio_controller import GPIOController


class SystemState(Enum):
    """System state enumeration matching ESP32 implementation"""
    INIT = "init"
    NORMAL_OPERATION = "normal_operation"
    CHECK_UPDATES = "check_updates"
    DOWNLOAD_UPDATES = "download_updates"
    APPLY_UPDATES = "apply_updates"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class RaspberryPiOTASystem:
    """
    Main Raspberry Pi OTA System
    Replaces ESP32 main.cpp functionality with Python state machine
    """
    
    def __init__(self, config_path: str = "./config/system_config.yaml"):
        """
        Initialize the OTA system
        
        Args:
            config_path: Path to system configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # Setup logging first
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # System state
        self.current_state = SystemState.INIT
        self.previous_state = SystemState.INIT
        self.state_enter_time = time.time()
        self.running = False
        
        # Core components
        self.gpio_controller: Optional[GPIOController] = None
        self.system_api: Optional[SystemAPI] = None
        self.module_manager: Optional[ModuleManager] = None
        self.ota_updater: Optional[OTAUpdater] = None
        
        # System monitoring
        self.main_loop_interval = self.config.get('system', {}).get('main_loop_interval', 1.0)
        self.sensor_read_interval = self.config.get('system', {}).get('sensor_read_interval', 0.5)
        self.status_update_interval = self.config.get('system', {}).get('status_update_interval', 10.0)
        
        # Error handling
        self.consecutive_errors = 0
        self.max_consecutive_errors = self.config.get('system', {}).get('max_consecutive_errors', 5)
        self.error_cooldown_period = self.config.get('system', {}).get('error_cooldown_period', 60.0)
        self.last_error_time = 0.0
        
        # Timing
        self.last_sensor_read = 0.0
        self.last_status_update = 0.0
        self.last_update_check = 0.0
        
        # Button handling
        self.update_button_pressed = False
        self.reset_button_pressed = False
        
        # Shutdown handling
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("Raspberry Pi OTA System initialized")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load system configuration"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config
        except Exception as e:
            print(f"Error loading config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'system': {
                'log_level': 'INFO',
                'main_loop_interval': 1.0,
                'sensor_read_interval': 0.5,
                'status_update_interval': 10.0,
                'max_consecutive_errors': 5,
                'error_cooldown_period': 60.0
            },
            'device': {
                'device_id': 'rpi_default',
                'firmware_version': '1.0.0'
            },
            'ota': {
                'check_interval': 300,
                'auto_update': True
            },
            'modules': {
                'base_path': './modules',
                'available': []
            }
        }
    
    def _setup_logging(self):
        """Setup comprehensive logging system"""
        try:
            # Load logging configuration
            logging_config_path = "./config/logging_config.yaml"
            if os.path.exists(logging_config_path):
                import logging.config
                with open(logging_config_path, 'r') as f:
                    log_config = yaml.safe_load(f)
                
                # Create log directory if it doesn't exist
                log_dir = Path("./logs")
                log_dir.mkdir(exist_ok=True)
                
                logging.config.dictConfig(log_config)
            else:
                # Fallback to basic logging
                log_level = self.config.get('system', {}).get('log_level', 'INFO')
                logging.basicConfig(
                    level=getattr(logging, log_level.upper()),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
        except Exception as e:
            print(f"Error setting up logging: {e}")
            logging.basicConfig(level=logging.INFO)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        signal_name = signal.Signals(signum).name
        if hasattr(self, 'logger'):
            self.logger.info(f"Received {signal_name}, initiating shutdown")
        else:
            print(f"Received {signal_name}, initiating shutdown")
        self.shutdown_requested = True
    
    def initialize(self) -> bool:
        """Initialize all system components"""
        try:
            self.logger.info("Starting system initialization...")
            self._set_state(SystemState.INIT)
            
            # Initialize GPIO controller
            self.logger.info("Initializing GPIO controller...")
            self.gpio_controller = GPIOController()
            self.gpio_controller.set_status_leds("normal")
            
            # Initialize System API
            self.logger.info("Initializing System API...")
            self.system_api = SystemAPI(self.config, self.gpio_controller)
            
            # Initialize Module Manager
            self.logger.info("Initializing Module Manager...")
            module_config = self.config.get('modules', {})
            self.module_manager = ModuleManager(self.system_api, module_config)
            self.module_manager.start()
            
            # Initialize OTA Updater
            self.logger.info("Initializing OTA Updater...")
            self.ota_updater = OTAUpdater(self.system_api, self.module_manager, self.config)
            
            # Setup button callbacks
            self._setup_button_callbacks()
            
            # Load modules from configuration
            self.logger.info("Loading modules...")
            loaded_count = self.module_manager.load_modules_from_config()
            self.logger.info(f"Loaded {loaded_count} modules")
            
            # Start automatic OTA updates
            if self.config.get('ota', {}).get('auto_update', True):
                self.ota_updater.start_automatic_updates()
            
            self.logger.info("System initialization completed successfully")
            self.gpio_controller.set_status_leds("success")
            time.sleep(1)  # Show success LED briefly
            
            return True
            
        except Exception as e:
            self.logger.error(f"System initialization failed: {e}")
            if self.gpio_controller:
                self.gpio_controller.set_status_leds("error")
            return False
    
    def _setup_button_callbacks(self):
        """Setup button press callbacks"""
        def on_update_button():
            self.logger.info("Update button pressed")
            self.update_button_pressed = True
        
        def on_reset_button():
            self.logger.info("Reset button pressed")
            self.reset_button_pressed = True
        
        def on_update_long_press():
            self.logger.info("Update button long press - forcing update check")
            if self.ota_updater:
                threading.Thread(target=self.ota_updater.force_update_check, daemon=True).start()
        
        def on_reset_long_press():
            self.logger.info("Reset button long press - initiating shutdown")
            self.shutdown_requested = True
        
        # Register callbacks
        self.gpio_controller.register_button_callback('update_button', on_update_button)
        self.gpio_controller.register_button_callback('reset_button', on_reset_button)
        self.gpio_controller.register_button_callback('update_button', on_update_long_press, long_press=True)
        self.gpio_controller.register_button_callback('reset_button', on_reset_long_press, long_press=True)
    
    def run(self):
        """Main system loop"""
        self.logger.info("Starting main system loop")
        self.running = True
        
        try:
            while self.running and not self.shutdown_requested:
                # Execute state machine
                self._execute_state_machine()
                
                # Handle button presses
                self._handle_button_presses()
                
                # Periodic sensor reading
                self._handle_sensor_reading()
                
                # Periodic status updates
                self._handle_status_updates()
                
                # Check for shutdown
                if self.shutdown_requested:
                    self._set_state(SystemState.SHUTDOWN)
                    break
                
                # Sleep for main loop interval
                time.sleep(self.main_loop_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
            self.shutdown_requested = True
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}")
            self._set_state(SystemState.ERROR)
        finally:
            self.shutdown()
    
    def _execute_state_machine(self):
        """Execute the main state machine"""
        try:
            if self.current_state == SystemState.INIT:
                self._state_init()
            elif self.current_state == SystemState.NORMAL_OPERATION:
                self._state_normal_operation()
            elif self.current_state == SystemState.CHECK_UPDATES:
                self._state_check_updates()
            elif self.current_state == SystemState.DOWNLOAD_UPDATES:
                self._state_download_updates()
            elif self.current_state == SystemState.APPLY_UPDATES:
                self._state_apply_updates()
            elif self.current_state == SystemState.ERROR:
                self._state_error()
            elif self.current_state == SystemState.SHUTDOWN:
                self._state_shutdown()
            
            # Reset consecutive errors on successful state execution
            self.consecutive_errors = 0
            
        except Exception as e:
            self.logger.error(f"Error in state {self.current_state.value}: {e}")
            self.consecutive_errors += 1
            self.last_error_time = time.time()
            
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.logger.critical("Too many consecutive errors, entering error state")
                self._set_state(SystemState.ERROR)
    
    def _state_init(self):
        """INIT state - system startup"""
        if self._time_in_state() > 5.0:  # Give 5 seconds for initialization
            self.logger.info("Initialization complete, entering normal operation")
            self._set_state(SystemState.NORMAL_OPERATION)
    
    def _state_normal_operation(self):
        """NORMAL_OPERATION state - regular system operation"""
        # Check if it's time for periodic update check
        update_interval = self.config.get('ota', {}).get('check_interval', 300)
        if time.time() - self.last_update_check > update_interval:
            self.logger.info("Time for periodic update check")
            self._set_state(SystemState.CHECK_UPDATES)
            return
        
        # Set normal operation LED status
        self.gpio_controller.set_status_leds("normal")
        
        # Monitor system health
        if self.system_api:
            status = self.system_api.get_system_status()
            
            # Check for critical conditions
            if status.cpu_usage > 95:
                self.logger.warning(f"High CPU usage: {status.cpu_usage}%")
            
            if status.memory_usage > 95:
                self.logger.warning(f"High memory usage: {status.memory_usage}%")
            
            if status.temperature > 80:
                self.logger.warning(f"High temperature: {status.temperature}°C")
    
    def _state_check_updates(self):
        """CHECK_UPDATES state - check for available updates"""
        self.logger.info("Checking for updates...")
        self.gpio_controller.set_status_leds("updating")
        
        try:
            if self.ota_updater:
                updates = self.ota_updater.check_for_updates()
                self.last_update_check = time.time()
                
                if updates:
                    self.logger.info(f"Found {len(updates)} available updates")
                    self.gpio_controller.set_status_leds("update_available")
                    
                    # Check if auto-update is enabled
                    if self.config.get('ota', {}).get('auto_update', True):
                        self._set_state(SystemState.APPLY_UPDATES)
                    else:
                        self.logger.info("Auto-update disabled, staying in normal operation")
                        self._set_state(SystemState.NORMAL_OPERATION)
                else:
                    self.logger.info("No updates available")
                    self._set_state(SystemState.NORMAL_OPERATION)
            else:
                self.logger.error("OTA updater not available")
                self._set_state(SystemState.ERROR)
                
        except Exception as e:
            self.logger.error(f"Error checking for updates: {e}")
            self._set_state(SystemState.ERROR)
    
    def _state_download_updates(self):
        """DOWNLOAD_UPDATES state - download available updates"""
        # This state is handled internally by the OTA updater
        # Transition directly to apply updates
        self._set_state(SystemState.APPLY_UPDATES)
    
    def _state_apply_updates(self):
        """APPLY_UPDATES state - apply downloaded updates"""
        self.logger.info("Applying updates...")
        self.gpio_controller.set_status_leds("updating")
        
        try:
            if self.ota_updater:
                success = self.ota_updater.apply_updates()
                
                if success:
                    self.logger.info("Updates applied successfully")
                    self.gpio_controller.set_status_leds("success")
                    time.sleep(2)  # Show success status briefly
                    self._set_state(SystemState.NORMAL_OPERATION)
                else:
                    self.logger.error("Failed to apply updates")
                    self.gpio_controller.set_status_leds("error")
                    time.sleep(2)  # Show error status briefly
                    self._set_state(SystemState.NORMAL_OPERATION)
            else:
                self.logger.error("OTA updater not available")
                self._set_state(SystemState.ERROR)
                
        except Exception as e:
            self.logger.error(f"Error applying updates: {e}")
            self._set_state(SystemState.ERROR)
    
    def _state_error(self):
        """ERROR state - handle system errors"""
        self.gpio_controller.set_status_leds("critical_error")
        
        # Wait for error cooldown period
        if time.time() - self.last_error_time > self.error_cooldown_period:
            self.logger.info("Error cooldown period ended, attempting recovery")
            self.consecutive_errors = 0
            self._set_state(SystemState.NORMAL_OPERATION)
        
        # Allow manual recovery via button press
        if self.reset_button_pressed:
            self.logger.info("Manual recovery requested via reset button")
            self.consecutive_errors = 0
            self.reset_button_pressed = False
            self._set_state(SystemState.NORMAL_OPERATION)
    
    def _state_shutdown(self):
        """SHUTDOWN state - clean shutdown"""
        self.logger.info("Entering shutdown state")
        self.running = False
    
    def _handle_button_presses(self):
        """Handle button press events"""
        if self.update_button_pressed:
            self.update_button_pressed = False
            
            if self.current_state == SystemState.NORMAL_OPERATION:
                self.logger.info("Manual update check requested")
                self._set_state(SystemState.CHECK_UPDATES)
            else:
                self.logger.info("Update button ignored - system not in normal operation")
        
        if self.reset_button_pressed:
            self.reset_button_pressed = False
            
            if self.current_state == SystemState.ERROR:
                self.logger.info("Reset button pressed - attempting recovery")
                self.consecutive_errors = 0
                self._set_state(SystemState.NORMAL_OPERATION)
            else:
                self.logger.info("Reset button pressed - restarting system")
                self.shutdown_requested = True
    
    def _handle_sensor_reading(self):
        """Handle periodic sensor readings"""
        current_time = time.time()
        
        if current_time - self.last_sensor_read > self.sensor_read_interval:
            try:
                # Read various sensors
                if self.system_api:
                    # Read temperature sensor
                    temp_reading = self.system_api.read_sensor("cpu_temperature")
                    if temp_reading:
                        self.system_api.store_sensor_reading(temp_reading)
                    
                    # Trigger sensor reading event for modules
                    self.system_api.trigger_event("sensor_update", {
                        "timestamp": current_time,
                        "temperature": temp_reading.value if temp_reading else None
                    })
                
                self.last_sensor_read = current_time
                
            except Exception as e:
                self.logger.error(f"Error reading sensors: {e}")
    
    def _handle_status_updates(self):
        """Handle periodic status updates"""
        current_time = time.time()
        
        if current_time - self.last_status_update > self.status_update_interval:
            try:
                if self.system_api:
                    status = self.system_api.get_system_status()
                    
                    self.logger.debug(f"System status: CPU {status.cpu_usage:.1f}%, "
                                    f"Memory {status.memory_usage:.1f}%, "
                                    f"Temp {status.temperature:.1f}°C")
                    
                    # Store status for monitoring
                    self.system_api.store_data("system_status", {
                        "cpu_usage": status.cpu_usage,
                        "memory_usage": status.memory_usage,
                        "temperature": status.temperature,
                        "uptime": status.uptime,
                        "state": self.current_state.value
                    })
                
                self.last_status_update = current_time
                
            except Exception as e:
                self.logger.error(f"Error updating status: {e}")
    
    def _set_state(self, new_state: SystemState):
        """Set system state with logging"""
        if new_state != self.current_state:
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_enter_time = time.time()
            
            self.logger.info(f"State transition: {self.previous_state.value} -> {new_state.value}")
            
            # Store state change for monitoring
            if self.system_api:
                self.system_api.store_data("current_state", new_state.value)
                self.system_api.store_data("state_change_time", self.state_enter_time)
    
    def _time_in_state(self) -> float:
        """Get time spent in current state"""
        return time.time() - self.state_enter_time
    
    def shutdown(self):
        """Clean system shutdown"""
        try:
            self.logger.info("Starting system shutdown...")
            self.running = False
            
            # Stop OTA updater
            if self.ota_updater:
                self.logger.info("Stopping OTA updater...")
                # OTA updater cleanup (if needed)
            
            # Stop module manager
            if self.module_manager:
                self.logger.info("Stopping module manager...")
                self.module_manager.stop()
            
            # Cleanup system API
            if self.system_api:
                self.logger.info("Cleaning up system API...")
                self.system_api.cleanup()
            
            # Cleanup GPIO controller
            if self.gpio_controller:
                self.logger.info("Cleaning up GPIO controller...")
                self.gpio_controller.cleanup()
            
            self.logger.info("System shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")


def main():
    """Main entry point"""
    try:
        # Change to script directory
        script_dir = Path(__file__).parent.parent
        os.chdir(script_dir)
        
        # Create and run the system
        system = RaspberryPiOTASystem()
        
        if system.initialize():
            system.run()
        else:
            print("System initialization failed")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 