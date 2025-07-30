# Raspberry Pi OTA System

A modular Over-The-Air (OTA) update system for Raspberry Pi, converted from ESP32 C++ implementation to Python. This system provides dynamic module loading, secure updates via Supabase, comprehensive logging, and hardware control through GPIO.

## 🌟 Features

### Core Functionality
- **Dynamic Module Loading**: Hot-swap Python modules without system restart
- **Secure OTA Updates**: SHA256 verification and digital signature validation
- **Supabase Integration**: Cloud-based update manifest and file storage
- **State Machine Architecture**: Robust system state management
- **Comprehensive Logging**: Multi-level logging with rotation and module-specific logs
- **GPIO Control**: LED status indicators and button input handling

### Hardware Support
- **LED Status Indicators**: Visual feedback for system state
  - 🟡 Yellow: Update available
  - 🟢 Green: Normal operation/Success
  - 🔴 Red: Error/Critical state
- **Button Controls**: Manual update triggers and system reset
- **Sensor Integration**: Mock sensors for testing and development
- **WiringPi Integration**: Hardware abstraction layer

### Security Features
- **Digital Signature Verification**: RSA signature validation for updates
- **File Integrity Checking**: SHA256 hash verification
- **Secure Configuration**: Protected credential storage
- **Sandboxed Modules**: Isolated module execution environment

## 📁 Project Structure

```
rpi_ota_system/
├── config/                     # Configuration files
│   ├── system_config.yaml     # Main system configuration
│   ├── gpio_config.yaml       # GPIO pin mappings
│   └── logging_config.yaml    # Logging configuration
├── src/                        # Core system source code
│   ├── main.py                # Main application with state machine
│   ├── system_api.py          # System API for modules
│   ├── module_loader.py       # Dynamic module loading
│   ├── ota_updater.py         # OTA update management
│   └── hardware/              # Hardware abstraction
│       ├── gpio_controller.py # GPIO control
│       └── sensors.py         # Sensor interfaces
├── modules/                    # Dynamically loadable modules
│   ├── base_module.py         # Base module interface
│   ├── speed_governor/        # Speed control module
│   │   └── speed_governor.py  # Highway speed limit fix (v1.1.1)
│   └── distance_sensor/       # Distance measurement module
│       └── distance_sensor.py # Ultrasonic sensor (v1.1.0)
├── logs/                      # Log files (created at runtime)
├── backups/                   # Module backups (created at runtime)
├── tests/                     # Unit tests
├── scripts/                   # Utility scripts
├── requirements.txt           # Python dependencies
├── install.sh                # Installation script
└── README.md                 # This file
```

## 🚀 Quick Start

### Prerequisites

- Raspberry Pi 4B or newer (recommended)
- Raspberry Pi OS (64-bit recommended)
- Python 3.8 or newer
- Internet connection for updates
- GPIO access for hardware features

### Installation

1. **Clone or download the project**:
   ```bash
   git clone <repository-url>
   cd rpi_ota_system
   ```

2. **Run the installation script**:
   ```bash
   sudo ./install.sh
   ```

   The installer will:
   - Update system packages
   - Install Python dependencies
   - Create system user and directories
   - Configure GPIO permissions
   - Set up systemd service
   - Start the OTA system

3. **Verify installation**:
   ```bash
   rpi-ota status
   ```

### Manual Installation

If you prefer manual installation:

```bash
# 1. Install system dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv wiringpi git -y

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure system
cp config/system_config.yaml.example config/system_config.yaml
# Edit configuration files as needed

# 5. Run the system
python src/main.py
```

## ⚙️ Configuration

### System Configuration (`config/system_config.yaml`)

```yaml
# Device Information
device:
  device_id: "rpi_001"
  device_name: "RaspberryPi_OTA_Node"
  firmware_version: "1.0.0"

# Supabase Configuration
supabase:
  url: "https://your-project.supabase.co"
  anon_key: "your-anon-key-here"

# OTA Update Configuration
ota:
  check_interval: 300  # Check every 5 minutes
  auto_update: true
  signature_verification: true

# Module Configuration
modules:
  base_path: "./modules"
  available:
    - name: "speed_governor"
      version: "1.1.1"
      enabled: true
    - name: "distance_sensor"
      version: "1.1.0"
      enabled: true
```

### GPIO Configuration (`config/gpio_config.yaml`)

```yaml
# LED Configuration (WiringPi pin numbers)
leds:
  yellow_led:
    pin: 0  # BCM 17, Physical 11
    description: "Update Available Indicator"
  green_led:
    pin: 1  # BCM 18, Physical 12
    description: "Success/Normal Operation"
  red_led:
    pin: 2  # BCM 27, Physical 13
    description: "Error/Failure Indicator"

# Button Configuration
buttons:
  update_button:
    pin: 3  # BCM 22, Physical 15
    description: "Manual Update Trigger"
  reset_button:
    pin: 4  # BCM 23, Physical 16
    description: "System Reset Button"
```

## 🔧 Module Development

### Creating a New Module

1. **Create module directory**:
   ```bash
   mkdir modules/my_module
   ```

2. **Implement module class**:
   ```python
   # modules/my_module/my_module.py
   from modules.base_module import BaseModule, ModuleInfo, ModuleState
   
   class MyModule(BaseModule):
       def get_info(self) -> ModuleInfo:
           return ModuleInfo(
               name="my_module",
               version="1.0.0",
               description="My custom module",
               author="Your Name",
               dependencies=[],
               config_schema={},
               update_interval=1.0,
               priority=5
           )
       
       def initialize(self) -> bool:
           self.log_info("Initializing my module")
           self.set_state(ModuleState.RUNNING)
           return True
       
       def update(self) -> bool:
           # Module logic here
           return True
       
       def deinitialize(self) -> bool:
           self.log_info("Deinitializing my module")
           return True
   ```

3. **Create module package**:
   ```python
   # modules/my_module/__init__.py
   from .my_module import MyModule
   __all__ = ['MyModule']
   ```

4. **Add to configuration**:
   ```yaml
   # config/system_config.yaml
   modules:
     available:
       - name: "my_module"
         version: "1.0.0"
         enabled: true
   ```

### Module API

Modules have access to the system API through `self.system_api`:

```python
# Logging
self.log_info("Information message")
self.log_warning("Warning message")
self.log_error("Error message")

# Data storage
self.store_data("key", value)
value = self.get_data("key", default=None)

# Sensor reading
reading = self.system_api.read_sensor("temperature")

# GPIO control
self.system_api.set_led_status("normal")  # or "error", "updating", etc.
button_pressed = self.system_api.is_button_pressed("update_button")

# Inter-module communication
self.trigger_event("my_event", {"data": "value"})
self.register_event_callback("other_event", self.handle_event)
```

## 📊 System Management

### Management Commands

```bash
# Service management
rpi-ota start     # Start the service
rpi-ota stop      # Stop the service
rpi-ota restart   # Restart the service
rpi-ota status    # Check service status

# Monitoring
rpi-ota logs      # View live logs
rpi-ota enable    # Enable auto-start on boot
rpi-ota disable   # Disable auto-start

# Updates
rpi-ota update    # Update system and restart
```

### Log Files

- **System logs**: `/opt/rpi_ota_system/logs/`
  - `system.log` - Main system log
  - `ota.log` - OTA update operations
  - `modules.log` - Module lifecycle and operations
  - `gpio.log` - Hardware control events
  - `errors.log` - Error messages only

- **Service logs**: `journalctl -u rpi-ota-system`

### Monitoring System Status

```bash
# Check service status
systemctl status rpi-ota-system

# View recent logs
journalctl -u rpi-ota-system -n 50

# Monitor logs in real-time
journalctl -u rpi-ota-system -f

# Check system resources
htop
df -h
free -h
```

## 🔒 Security

### Update Security

- **Digital Signatures**: All module updates must be signed with a private key
- **Hash Verification**: SHA256 checksums prevent corrupted downloads
- **Secure Storage**: Supabase integration with API key authentication
- **Sandboxed Execution**: Modules run in isolated Python environments

### Configuration Security

- **Protected Files**: Configuration files have restricted permissions (640)
- **Service Hardening**: Systemd service runs with security restrictions
- **Firewall Rules**: Optional UFW configuration for network security

### Best Practices

1. **Keep signatures enabled** in production
2. **Use strong API keys** for Supabase
3. **Regularly update** the base system
4. **Monitor logs** for security events
5. **Backup configurations** before major updates

## 🧪 Testing

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run specific test category
python -m pytest tests/test_modules.py -v

# Test module loading
python -m pytest tests/test_module_loader.py -v

# Test OTA functionality
python -m pytest tests/test_ota_updater.py -v
```

### Manual Testing

```bash
# Test module loading
cd rpi_ota_system
python -c "
from src.module_loader import ModuleManager
from src.system_api import SystemAPI
from src.hardware.gpio_controller import GPIOController

gpio = GPIOController()
api = SystemAPI({}, gpio)
manager = ModuleManager(api, {'base_path': './modules'})
manager.start()
print('Available modules:', manager.discover_modules())
"

# Test GPIO functionality
python src/hardware/gpio_controller.py

# Test individual modules
python modules/speed_governor/speed_governor.py
python modules/distance_sensor/distance_sensor.py
```

## 🔄 OTA Updates

### Update Process

1. **Check Phase**: System periodically checks Supabase for new module versions
2. **Download Phase**: New modules are downloaded to temporary storage
3. **Verification Phase**: SHA256 hashes and digital signatures are verified
4. **Backup Phase**: Current modules are backed up
5. **Install Phase**: New modules replace old ones
6. **Reload Phase**: Modules are hot-reloaded without system restart

### Supabase Setup

1. **Create Supabase project** at https://supabase.com
2. **Create tables**:
   ```sql
   -- Firmware manifest table
   CREATE TABLE firmware_manifest (
     id SERIAL PRIMARY KEY,
     device_id TEXT NOT NULL,
     manifest JSONB NOT NULL,
     created_at TIMESTAMP DEFAULT NOW()
   );

   -- Module files table  
   CREATE TABLE modules (
     id SERIAL PRIMARY KEY,
     name TEXT NOT NULL,
     version TEXT NOT NULL,
     file_url TEXT NOT NULL,
     sha256 TEXT NOT NULL,
     signature TEXT,
     created_at TIMESTAMP DEFAULT NOW()
   );
   ```

3. **Configure API keys** in `system_config.yaml`

### Manual Update Trigger

```bash
# Force update check
sudo systemctl kill -s USR1 rpi-ota-system

# Or use button press (long press update button)
```

## 🐛 Troubleshooting

### Common Issues

1. **Service won't start**:
   ```bash
   # Check service status
   systemctl status rpi-ota-system
   
   # Check logs
   journalctl -u rpi-ota-system -n 20
   
   # Check Python environment
   cd /opt/rpi_ota_system
   source venv/bin/activate
   python src/main.py
   ```

2. **GPIO permission errors**:
   ```bash
   # Add user to gpio group
   sudo usermod -a -G gpio rpi-ota
   
   # Check udev rules
   cat /etc/udev/rules.d/99-rpi-ota-gpio.rules
   ```

3. **Module loading failures**:
   ```bash
   # Check module directory
   ls -la /opt/rpi_ota_system/modules/
   
   # Test module import
   cd /opt/rpi_ota_system
   source venv/bin/activate
   python -c "from modules.speed_governor import SpeedGovernorModule"
   ```

4. **Update failures**:
   ```bash
   # Check network connectivity
   ping 8.8.8.8
   
   # Check Supabase connection
   curl -I https://your-project.supabase.co
   
   # Check update logs
   tail -f /opt/rpi_ota_system/logs/ota.log
   ```

### Debugging

```bash
# Enable debug logging
sudo vim /opt/rpi_ota_system/config/system_config.yaml
# Set: system.log_level: "DEBUG"

# Restart service
sudo systemctl restart rpi-ota-system

# Monitor debug logs
tail -f /opt/rpi_ota_system/logs/system.log
```

## 📈 Performance

### System Requirements

- **CPU**: ARM Cortex-A72 (Raspberry Pi 4) or better
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 8GB SD card minimum, 32GB recommended
- **Network**: WiFi or Ethernet for updates

### Performance Optimization

- **Module Update Intervals**: Adjust based on module complexity
- **Log Rotation**: Configure appropriate log retention
- **Update Scheduling**: Use update windows for non-critical times
- **Resource Monitoring**: Monitor CPU and memory usage

## 🤝 Contributing

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit changes**: `git commit -m 'Add amazing feature'`
4. **Push to branch**: `git push origin feature/amazing-feature`
5. **Open Pull Request**

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd rpi_ota_system

# Create development environment
python3 -m venv dev-venv
source dev-venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio black flake8

# Run tests
python -m pytest

# Format code
black src/ modules/ tests/

# Lint code
flake8 src/ modules/ tests/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Original ESP32 Implementation**: Converted from C++ to Python
- **WiringPi**: GPIO control library
- **Supabase**: Backend-as-a-Service platform
- **Python Community**: Amazing libraries and tools

## 📞 Support

- **Documentation**: Check this README and inline code comments
- **Issues**: Create GitHub issues for bug reports
- **Discussions**: Use GitHub Discussions for questions
- **Email**: [your-email@example.com]

---

**Built with ❤️ for the Raspberry Pi community** 