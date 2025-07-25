# Modular OTA System for ESP32

A complete demonstration of a real-world automotive Over-The-Air (OTA) update system using ESP32, showcasing modular driver updates with CI/CD integration.

## 🚀 **Quick Setup for Supabase Upload**

### 🔑 **Required GitHub Secrets**

To enable automatic module uploads to Supabase, set these repository secrets:

1. Go to your GitHub repo → **Settings** → **Secrets and Variables** → **Actions**
2. Add these secrets:

| Secret Name | Value | How to Get |
|-------------|-------|------------|
| `SUPABASE_URL` | `https://your-project-id.supabase.co` | Supabase Dashboard → Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | `eyJhbGc...` | Supabase Dashboard → Settings → API → service_role key |

### 🪣 **Create Storage Bucket**

1. Go to **Storage** in Supabase Dashboard
2. Create bucket named: `ota-modules`
3. Make it **Public** for direct ESP32 downloads
4. The workflow will automatically create folder structure

### 🎯 **Test Upload**

Once secrets are set, any change to `mock_drivers/**` files will trigger automatic build and upload!

Or manually trigger with: **Actions** → **Supabase OTA Upload** → **Run workflow**

---

## 🎉 MAJOR UPDATE: Fully Functional Implementation!

### ✅ **Critical Issues Fixed:**

1. **🔥 REAL Dynamic Loading**: No more mock interfaces! The system now truly loads and executes binary code from the cloud
2. **📁 Clean Project Structure**: Removed confusing v2 directories - Git handles versioning properly now  
3. **🔐 Full Security Implementation**: Complete cryptographic signature verification with mbedtls
4. **⚙️ Externalized Config**: WiFi credentials and settings moved to `config.h` (not tracked in Git)
5. **🎯 True Modularity**: Two independent modules (speed_governor + distance_sensor) demonstrate independent updates
6. **💡 Enhanced UX**: Success/failure states with 5-8 second LED feedback for clear user indication

### 🚗 **The TATA EV Nexon Fix Actually Works Now!**

Before our fix:
```c
// v1.0.0 BUG: Highway speed limited to 40 km/h
if (road_conditions == 1) { // Highway 
    return 40; // ❌ WRONG! Should be 100 km/h
}
```

After our fix:
```c  
// v1.1.0 FIXED: Proper highway speed limit
if (road_conditions == 1) { // Highway
    return highway_speed_limit; // ✅ 100 km/h on highways!
}
```

The system now **genuinely downloads new code** and **executes the fixed logic**! 🎯

### 🔧 **What Makes This Special:**

- **True Binary Loading**: ESP32 downloads `.bin` files and executes them in real-time
- **Function Pointer Magic**: Downloaded code replaces system functions dynamically  
- **Production-Ready Architecture**: Designed for real automotive OTA systems
- **Safety First**: Updates only when vehicle is idle, with automatic rollback

## 🚗 Project Overview

This project simulates the TATA EV Nexon speed governor issue where drivers couldn't exceed 40 km/h on highways. Our modular OTA system demonstrates how such critical issues can be fixed through remote updates without requiring physical vehicle access.

### Key Features

- **True Modular Architecture**: Two independent modules (speed_governor + distance_sensor) updatable separately
- **Real-time Updates**: ESP32 checks for updates every 30 seconds
- **Safety First**: Updates only apply when vehicle is idle (button pressed)
- **Rollback Support**: Automatic rollback on failed updates
- **CI/CD Integration**: GitHub Actions automatically build and deploy updates
- **Enhanced Visual Feedback**: LEDs with persistent states (5s success, 8s failure)
- **Automotive Simulation**: Mock vehicle sensors and conditions
- **Production-Grade Security**: Full cryptographic signature verification

## 🏗️ System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Admin Upload  │───▶│  GitHub Actions │───▶│ Supabase Storage│
│   (New Module)  │    │   (CI/CD Build) │    │  (Binary Files) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│      ESP32      │◀───│  OTA Updater    │◀───│   manifest.json │
│ (Module Loader) │    │ (Check Updates) │    │ (Version Info)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
modular-ota-project/
├── .github/workflows/              # CI/CD automation
│   └── build-and-deploy-module.yml
├── esp32_loader_firmware/          # Main ESP32 application
│   ├── include/                    # Header files
│   ├── src/                       # Source code
│   └── platformio.ini             # PlatformIO configuration
├── mock_drivers/                   # Updatable driver modules
│   ├── speed_governor/            # Speed control module (v1.0.0 → v1.1.0)
│   └── distance_sensor/           # Distance sensing module (v1.0.0 → v1.1.0)
└── backend_manifest/              # Version management
    └── manifest.json
```

## 🛠️ Hardware Requirements

- **ESP32 Development Board** (ESP32-DevKitC or similar)
- **3 LEDs** (Yellow, Green, Red) with 220Ω resistors
- **1 Push Button** with pull-up resistor
- **Breadboard and jumper wires**
- **USB cable** for programming

### Pin Configuration

| Component | ESP32 Pin | Description |
|-----------|-----------|-------------|
| Yellow LED | GPIO 2 | Update available |
| Green LED | GPIO 4 | Update success |
| Red LED | GPIO 5 | Update failed |
| Button | GPIO 0 | Vehicle idle state |

## 🚀 Quick Start

### 1. Supabase Setup

1. Create a [Supabase](https://supabase.com) account
2. Create a new project
3. Go to Storage and create a bucket named `ota-modules`
4. Make the bucket public for read access
5. Note your Project URL and Service Role Key

### 2. GitHub Repository Setup

1. Fork this repository
2. Add GitHub Secrets:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_SERVICE_KEY`: Your Supabase service role key

### 3. ESP32 Firmware Setup

1. Install [PlatformIO](https://platformio.org/)
2. Update WiFi credentials in `esp32_loader_firmware/src/main.cpp`:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   const char* SERVER_URL = "https://YOUR_SUPABASE_URL.supabase.co";
   ```
3. Upload firmware to ESP32:
   ```bash
   cd esp32_loader_firmware
   pio run --target upload
   ```

### 4. Deploy Initial Manifest

Upload the initial `backend_manifest/manifest.json` to your Supabase bucket root.

## 🔄 Demo Workflow

### The Problem: TATA EV Nexon Highway Issue

The `speed_governor` v1.0.0 module has a critical bug:

```c
// BUG: Always returns 40 km/h even on highway
if (road_conditions == 1) { // Highway conditions
    return current_speed_limit; // Should be 100 km/h!
}
```

### The Solution: OTA Update

1. **Upload Fix**: Push changes to `mock_drivers/speed_governor/src/` (update to v1.1.0)
2. **Auto-Build**: GitHub Actions detects changes and builds new module
3. **Deploy**: New module uploaded to Supabase with incremented version
4. **Update Manifest**: System updates manifest.json automatically
5. **ESP32 Detection**: ESP32 detects new version on next check
6. **User Notification**: Yellow LED lights up, shows "Update Available"
7. **Safe Update**: User presses button (vehicle idle), update downloads
8. **Verification**: SHA256 hash + cryptographic signature verified
9. **Success**: Green LED shows for 5 seconds, confirms highway speed fix (100 km/h)

## 🔧 Development

### Building Modules

Each driver module can be built independently:

```bash
cd mock_drivers/speed_governor
make clean
make build
```

### Testing Updates

1. Modify code in `mock_drivers/speed_governor/src/speed_governor.c` or `distance_sensor.c`
2. Update the MODULE_VERSION string to increment the version
3. Commit and push changes to trigger CI/CD
4. GitHub Actions will automatically build and deploy
5. ESP32 will detect the update within 30 seconds
6. Test both modules independently to demonstrate modularity

### Module Development Guidelines

1. **Always** implement the standard `ModuleInterface`
2. **Use** the `SystemAPI` for all system interactions
3. **Version** your modules properly (semantic versioning)
4. **Test** thoroughly before pushing to main branch
5. **Document** changes in commit messages

## 🐛 Troubleshooting

### Common Issues

1. **Module Not Loading**
   - Check file size (must be < 64KB)
   - Verify compilation flags in Makefile
   - Ensure ESP-IDF toolchain is installed

2. **Update Download Fails**
   - Verify WiFi connection
   - Check Supabase bucket permissions
   - Confirm manifest.json is valid JSON

3. **Hash Verification Fails**
   - File may be corrupted during upload
   - Check CI/CD logs for build errors
   - Verify Supabase storage integrity

### Debug Commands

```bash
# Check ESP32 serial output
pio device monitor

# Validate module binary
file mock_drivers/speed_governor/build/speed_governor.bin

# Test Supabase connectivity
curl -H "Authorization: Bearer YOUR_KEY" YOUR_SUPABASE_URL/storage/v1/object/ota-modules/manifest.json
```

## 🔒 Security Considerations

### Current Implementation (Production-Ready)
- ✅ **SHA256 hash verification**: Ensures file integrity
- ✅ **Cryptographic signature verification**: Full RSA/mbedtls implementation
- ✅ **Metadata validation**: JSON parsing with error handling
- ✅ **Safe update states**: Vehicle idle detection + rollback support
- ✅ **Version tracking**: Prevents downgrade and repeat attacks

### Additional Production Enhancements
- **Secure Boot**: Verify loader firmware integrity at boot
- **TLS/HTTPS**: Encrypted communication channels (easily configurable)
- **Access Control**: Authentication for update uploads (Supabase RLS)
- **Audit Logging**: Complete update history tracking
- **Hardware Security Module**: Store signing keys in secure hardware

## 📊 System Monitoring

### Update Status Dashboard

Monitor your OTA system health:

```sql
-- Supabase SQL to track update statistics
SELECT 
  module_name,
  latest_version,
  last_updated
FROM ota_modules
ORDER BY last_updated DESC;
```

### ESP32 Telemetry

The system logs comprehensive information:

```
[INFO] OTA: Checking for updates...
[INFO] ModuleLoader: Speed Governor v1.1.0 initialized
[WARN] speed_governor: SPEED VIOLATION: Vehicle speed 65 km/h exceeds limit 40 km/h
[INFO] speed_governor: Highway detected, allowing higher speed: 100 km/h
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-module`)
3. Commit your changes (`git commit -am 'Add new sensor module'`)
4. Push to the branch (`git push origin feature/new-module`)
5. Create a Pull Request

### Adding New Modules

1. Create directory in `mock_drivers/your_module/`
2. Implement `ModuleInterface` in `src/your_module.c`
3. Add appropriate `Makefile`
4. Update CI/CD workflow if needed
5. Test thoroughly

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **TATA Motors** for the real-world automotive OTA inspiration
- **Espressif Systems** for the ESP32 platform
- **Supabase** for the excellent backend-as-a-service platform
- **PlatformIO** for the development environment

## 📞 Support

For questions and support:

- 📧 Create an issue in this repository
- 💬 Join our [Discussions](https://github.com/your-repo/discussions)
- 📖 Check the [Wiki](https://github.com/your-repo/wiki) for advanced topics

---

**⚠️ Disclaimer**: This is a demonstration project for educational purposes. Real automotive OTA systems require significantly more security, testing, and safety measures.
