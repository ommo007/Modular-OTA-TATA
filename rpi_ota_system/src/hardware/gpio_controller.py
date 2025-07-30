#!/usr/bin/env python3
"""
GPIO Controller for Raspberry Pi OTA System
Replaces ESP32 digitalWrite/digitalRead functionality with wiringPi
"""

import time
import threading
import logging
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum

try:
    import wiringpi
    WIRINGPI_AVAILABLE = True
except ImportError:
    WIRINGPI_AVAILABLE = False
    print("Warning: wiringPi not available. GPIO operations will be mocked.")

import yaml


class LEDState(Enum):
    """LED state enumeration"""
    OFF = 0
    ON = 1
    BLINK = 2


class PinMode(Enum):
    """Pin mode enumeration"""
    INPUT = 0
    OUTPUT = 1
    PWM = 2


@dataclass
class ButtonState:
    """Button state information"""
    pin: int
    current_state: bool
    previous_state: bool
    press_time: float
    release_time: float
    is_pressed: bool
    long_press_threshold: float = 2.0


@dataclass
class LEDConfig:
    """LED configuration"""
    pin: int
    description: str
    initial_state: bool
    blink_rate: float = 0.5


class GPIOController:
    """
    GPIO Controller for Raspberry Pi OTA System
    Manages LEDs, buttons, and other GPIO operations
    """
    
    def __init__(self, config_path: str = "./config/gpio_config.yaml"):
        """
        Initialize GPIO controller
        
        Args:
            config_path: Path to GPIO configuration file
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.config = self._load_config()
        
        # GPIO state tracking
        self.leds: Dict[str, LEDConfig] = {}
        self.buttons: Dict[str, ButtonState] = {}
        self.led_states: Dict[str, LEDState] = {}
        self.blink_threads: Dict[str, threading.Thread] = {}
        self.running = False
        
        # Button callbacks
        self.button_callbacks: Dict[str, Callable] = {}
        self.long_press_callbacks: Dict[str, Callable] = {}
        
        # Initialize wiringPi if available
        self.gpio_available = WIRINGPI_AVAILABLE
        if self.gpio_available:
            try:
                wiringpi.wiringPiSetup()
                self.logger.info("WiringPi initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize wiringPi: {e}")
                self.gpio_available = False
        
        self._setup_gpio()
        self._start_monitoring()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load GPIO configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
                self.logger.info(f"Loaded GPIO configuration from {self.config_path}")
                return config
        except Exception as e:
            self.logger.error(f"Failed to load GPIO configuration: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default GPIO configuration"""
        return {
            'leds': {
                'yellow_led': {'pin': 0, 'description': 'Update Available', 'initial_state': False},
                'green_led': {'pin': 1, 'description': 'Success', 'initial_state': False},
                'red_led': {'pin': 2, 'description': 'Error', 'initial_state': False}
            },
            'buttons': {
                'update_button': {'pin': 3, 'description': 'Update Button', 'pull_mode': 'up', 'debounce_time': 50},
                'reset_button': {'pin': 4, 'description': 'Reset Button', 'pull_mode': 'up', 'debounce_time': 50}
            },
            'setup': {
                'cleanup_on_exit': True,
                'button_poll_interval': 0.1
            }
        }
    
    def _setup_gpio(self):
        """Setup GPIO pins based on configuration"""
        try:
            # Setup LEDs
            for led_name, led_config in self.config.get('leds', {}).items():
                pin = led_config['pin']
                description = led_config.get('description', led_name)
                initial_state = led_config.get('initial_state', False)
                
                self.leds[led_name] = LEDConfig(
                    pin=pin,
                    description=description,
                    initial_state=initial_state
                )
                
                if self.gpio_available:
                    wiringpi.pinMode(pin, wiringpi.OUTPUT)
                    wiringpi.digitalWrite(pin, wiringpi.LOW if not initial_state else wiringpi.HIGH)
                
                self.led_states[led_name] = LEDState.ON if initial_state else LEDState.OFF
                self.logger.debug(f"Setup LED {led_name} on pin {pin}")
            
            # Setup buttons
            for button_name, button_config in self.config.get('buttons', {}).items():
                pin = button_config['pin']
                pull_mode = button_config.get('pull_mode', 'up')
                
                self.buttons[button_name] = ButtonState(
                    pin=pin,
                    current_state=False,
                    previous_state=False,
                    press_time=0.0,
                    release_time=0.0,
                    is_pressed=False
                )
                
                if self.gpio_available:
                    wiringpi.pinMode(pin, wiringpi.INPUT)
                    if pull_mode == 'up':
                        wiringpi.pullUpDnControl(pin, wiringpi.PUD_UP)
                    elif pull_mode == 'down':
                        wiringpi.pullUpDnControl(pin, wiringpi.PUD_DOWN)
                
                self.logger.debug(f"Setup button {button_name} on pin {pin}")
                
        except Exception as e:
            self.logger.error(f"Failed to setup GPIO: {e}")
    
    def _start_monitoring(self):
        """Start background monitoring for buttons"""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_buttons, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Started GPIO monitoring thread")
    
    def _monitor_buttons(self):
        """Monitor button states in background thread"""
        poll_interval = self.config.get('setup', {}).get('button_poll_interval', 0.1)
        
        while self.running:
            try:
                for button_name, button_state in self.buttons.items():
                    current_time = time.time()
                    
                    # Read button state (invert because of pull-up)
                    if self.gpio_available:
                        raw_state = wiringpi.digitalRead(button_state.pin)
                        button_pressed = not bool(raw_state)  # Invert for pull-up
                    else:
                        # Mock button state for testing
                        button_pressed = False
                    
                    button_state.previous_state = button_state.current_state
                    button_state.current_state = button_pressed
                    
                    # Detect button press
                    if button_pressed and not button_state.previous_state:
                        button_state.press_time = current_time
                        button_state.is_pressed = True
                        self.logger.debug(f"Button {button_name} pressed")
                        
                        # Call button press callback
                        if button_name in self.button_callbacks:
                            try:
                                self.button_callbacks[button_name]()
                            except Exception as e:
                                self.logger.error(f"Button callback error: {e}")
                    
                    # Detect button release
                    elif not button_pressed and button_state.previous_state:
                        button_state.release_time = current_time
                        press_duration = button_state.release_time - button_state.press_time
                        button_state.is_pressed = False
                        
                        self.logger.debug(f"Button {button_name} released after {press_duration:.2f}s")
                        
                        # Check for long press
                        if press_duration >= button_state.long_press_threshold:
                            if button_name in self.long_press_callbacks:
                                try:
                                    self.long_press_callbacks[button_name]()
                                except Exception as e:
                                    self.logger.error(f"Long press callback error: {e}")
                
                time.sleep(poll_interval)
                
            except Exception as e:
                self.logger.error(f"Button monitoring error: {e}")
                time.sleep(poll_interval)
    
    def set_led(self, led_name: str, state: LEDState, blink_rate: float = 0.5):
        """
        Set LED state
        
        Args:
            led_name: Name of the LED
            state: LED state (OFF, ON, BLINK)
            blink_rate: Blink rate in Hz for BLINK state
        """
        if led_name not in self.leds:
            self.logger.error(f"LED {led_name} not found")
            return
        
        led = self.leds[led_name]
        self.led_states[led_name] = state
        
        # Stop any existing blink thread
        if led_name in self.blink_threads:
            # The thread will stop when it checks the state
            pass
        
        if state == LEDState.OFF:
            self._set_led_physical(led.pin, False)
        elif state == LEDState.ON:
            self._set_led_physical(led.pin, True)
        elif state == LEDState.BLINK:
            self._start_blink(led_name, blink_rate)
        
        self.logger.debug(f"Set LED {led_name} to {state.name}")
    
    def _set_led_physical(self, pin: int, state: bool):
        """Set physical LED state"""
        if self.gpio_available:
            wiringpi.digitalWrite(pin, wiringpi.HIGH if state else wiringpi.LOW)
    
    def _start_blink(self, led_name: str, rate: float):
        """Start blinking LED in separate thread"""
        def blink_loop():
            led = self.leds[led_name]
            interval = 1.0 / (rate * 2)  # Half period for on/off cycle
            led_on = False
            
            while self.led_states.get(led_name) == LEDState.BLINK and self.running:
                self._set_led_physical(led.pin, led_on)
                led_on = not led_on
                time.sleep(interval)
            
            # Ensure LED is off when blinking stops
            self._set_led_physical(led.pin, False)
        
        thread = threading.Thread(target=blink_loop, daemon=True)
        thread.start()
        self.blink_threads[led_name] = thread
    
    def register_button_callback(self, button_name: str, callback: Callable, long_press: bool = False):
        """
        Register button press callback
        
        Args:
            button_name: Name of the button
            callback: Function to call when button is pressed
            long_press: True for long press callback, False for regular press
        """
        if button_name not in self.buttons:
            self.logger.error(f"Button {button_name} not found")
            return
        
        if long_press:
            self.long_press_callbacks[button_name] = callback
            self.logger.info(f"Registered long press callback for {button_name}")
        else:
            self.button_callbacks[button_name] = callback
            self.logger.info(f"Registered press callback for {button_name}")
    
    def is_button_pressed(self, button_name: str) -> bool:
        """
        Check if button is currently pressed
        
        Args:
            button_name: Name of the button
            
        Returns:
            True if button is pressed, False otherwise
        """
        if button_name not in self.buttons:
            self.logger.error(f"Button {button_name} not found")
            return False
        
        return self.buttons[button_name].is_pressed
    
    def get_led_state(self, led_name: str) -> Optional[LEDState]:
        """
        Get current LED state
        
        Args:
            led_name: Name of the LED
            
        Returns:
            Current LED state or None if LED not found
        """
        return self.led_states.get(led_name)
    
    def set_status_leds(self, status: str):
        """
        Set status LEDs based on system status
        
        Args:
            status: System status (normal, update_available, updating, success, error)
        """
        # Turn off all LEDs first
        self.set_led('yellow_led', LEDState.OFF)
        self.set_led('green_led', LEDState.OFF)
        self.set_led('red_led', LEDState.OFF)
        
        if status == 'normal':
            self.set_led('green_led', LEDState.ON)
        elif status == 'update_available':
            self.set_led('yellow_led', LEDState.ON)
        elif status == 'updating':
            self.set_led('yellow_led', LEDState.BLINK, 2.0)
        elif status == 'success':
            self.set_led('green_led', LEDState.BLINK, 1.0)
        elif status == 'error':
            self.set_led('red_led', LEDState.ON)
        elif status == 'critical_error':
            self.set_led('red_led', LEDState.BLINK, 3.0)
        
        self.logger.info(f"Set status LEDs for: {status}")
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        self.running = False
        
        # Turn off all LEDs
        for led_name in self.leds:
            self.set_led(led_name, LEDState.OFF)
        
        # Wait for threads to finish
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=1.0)
        
        for thread in self.blink_threads.values():
            thread.join(timeout=0.5)
        
        self.logger.info("GPIO cleanup completed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()


# Testing and example usage
if __name__ == "__main__":
    import logging
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Test GPIO controller
    with GPIOController() as gpio:
        # Test LEDs
        print("Testing LEDs...")
        gpio.set_status_leds('normal')
        time.sleep(2)
        
        gpio.set_status_leds('update_available')
        time.sleep(2)
        
        gpio.set_status_leds('updating')
        time.sleep(3)
        
        gpio.set_status_leds('success')
        time.sleep(2)
        
        gpio.set_status_leds('error')
        time.sleep(2)
        
        # Test button callbacks
        def on_update_button():
            print("Update button pressed!")
        
        def on_reset_button():
            print("Reset button pressed!")
        
        def on_long_press():
            print("Long press detected!")
        
        gpio.register_button_callback('update_button', on_update_button)
        gpio.register_button_callback('reset_button', on_reset_button)
        gpio.register_button_callback('update_button', on_long_press, long_press=True)
        
        print("Press buttons to test... (Ctrl+C to exit)")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...") 