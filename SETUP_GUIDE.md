# Complete Setup Guide

This guide will walk you through setting up the entire Modular OTA System from scratch.

## Prerequisites

Before starting, ensure you have:

- [ ] ESP32 development board
- [ ] Hardware components (LEDs, button, resistors)
- [ ] Computer with USB port
- [ ] Internet connection
- [ ] GitHub account
- [ ] Basic understanding of C programming

## Step 1: Development Environment Setup

### Install Required Software

1. **Install PlatformIO** (Choose one method):

   **Method A: VS Code Extension**
   ```bash
   # Install VS Code first, then add PlatformIO extension
   # Go to Extensions → Search "PlatformIO IDE" → Install
   ```

   **Method B: Command Line**
   ```bash
   # Install Python first, then PlatformIO Core
   pip install platformio
   ```

2. **Install ESP-IDF Toolchain** (for module compilation):
   ```bash
   # Linux/macOS
   mkdir -p ~/esp
   cd ~/esp
   git clone --recursive https://github.com/espressif/esp-idf.git
   cd esp-idf
   ./install.sh esp32
   . ./export.sh

   # Windows
   # Download and run ESP-IDF installer from Espressif website
   ```

3. **Verify Installation**:
   ```bash
   xtensa-esp32-elf-gcc --version
   pio --version
   ```

## Step 2: Supabase Backend Setup

### Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up
2. Click "New Project"
3. Fill in project details:
   - **Name**: `ota-demo`
   - **Database Password**: `your-secure-password`
   - **Region**: Choose closest to you
4. Wait for project creation (2-3 minutes)

### Configure Storage

1. Go to **Storage** in the left sidebar
2. Click **"New Bucket"**
3. Bucket settings:
   - **Name**: `ota-modules`
   - **Public bucket**: ✅ (checked)
   - **File size limit**: 50MB
   - **Allowed MIME types**: Leave empty (allow all)
4. Click **"Create bucket"**

### Get API Keys

1. Go to **Settings** → **API**
2. Copy and save these values:
   - **Project URL**: `https://xxxxxxxxxxx.supabase.co`
   - **Service Role Key**: `eyJ...` (starts with eyJ)
   - **Anon Public Key**: `eyJ...` (for read access)

## Step 3: GitHub Repository Setup

### Fork and Clone

1. **Fork this repository** to your GitHub account
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Modular-OTA-TATA.git
   cd Modular-OTA-TATA
   ```

### Configure GitHub Secrets

1. Go to your forked repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"** and add:

   | Secret Name | Value |
   |-------------|--------|
   | `SUPABASE_URL` | Your Supabase Project URL |
   | `SUPABASE_SERVICE_KEY` | Your Supabase Service Role Key |

### Upload Initial Manifest

Upload the initial manifest file to Supabase:

```bash
# Using curl (replace with your values)
curl -X POST \
  "https://YOUR_PROJECT.supabase.co/storage/v1/object/ota-modules/manifest.json" \
  -H "Authorization: Bearer YOUR_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  -d @backend_manifest/manifest.json
```

## Step 4: Hardware Assembly

### Components List

| Component | Quantity | Notes |
|-----------|----------|--------|
| ESP32 DevKit | 1 | Any ESP32 board works |
| LEDs (Yellow, Green, Red) | 3 | 5mm standard LEDs |
| 220Ω Resistors | 3 | For LED current limiting |
| Push Button | 1 | Momentary switch |
| 10kΩ Resistor | 1 | Button pull-up |
| Breadboard | 1 | Half-size sufficient |
| Jumper Wires | 10+ | Male-to-male |

### Wiring Diagram

```
ESP32 DevKit          Components
┌─────────────┐
│             │
│ GPIO2   ────┼──[220Ω]──[LED_YELLOW]──GND
│ GPIO4   ────┼──[220Ω]──[LED_GREEN]───GND  
│ GPIO5   ────┼──[220Ω]──[LED_RED]────GND
│             │
│ GPIO0   ────┼──[BUTTON]──GND
│         ────┼──[10kΩ]───3.3V (pull-up)
│             │
│ GND     ────┼─── Common Ground
│ 3.3V    ────┼─── Power Rails
└─────────────┘
```

### Assembly Steps

1. **Power Rails**: Connect 3.3V and GND to breadboard rails
2. **LEDs**: Connect each LED with resistor to respective GPIO pins
3. **Button**: Connect button between GPIO0 and GND, add pull-up resistor
4. **Double-check**: Verify all connections before powering on

## Step 5: ESP32 Firmware Configuration

### Update Configuration

1. **Open firmware project**:
   ```bash
   cd esp32_loader_firmware
   code . # or open in your preferred editor
   ```

2. **Copy and configure config file**:
   ```bash
   # Copy the example config file
   cp include/config.h.example include/config.h
   
   # Edit the config file with your credentials
   # Update WIFI_SSID, WIFI_PASSWORD, and SERVER_URL
   ```

3. **Edit `include/config.h`** and update these values:
   ```cpp
   // Update with your WiFi credentials
   #define WIFI_SSID "Your_WiFi_Name"
   #define WIFI_PASSWORD "Your_WiFi_Password"
   #define SERVER_URL "https://xxxxxxxxxxx.supabase.co"
   #define DEVICE_ID "esp32-demo-001" // Unique device ID
   ```

4. **Verify pin assignments** match your wiring:
   ```cpp
   // In main.cpp: GPIO pin definitions
   #define LED_YELLOW_PIN 2
   #define LED_GREEN_PIN 4
   #define LED_RED_PIN 5
   #define BUTTON_PIN 0
   ```

### Build and Upload

1. **Build the project**:
   ```bash
   pio run
   ```

2. **Connect ESP32** via USB cable

3. **Upload firmware**:
   ```bash
   pio run --target upload
   ```

4. **Monitor serial output**:
   ```bash
   pio device monitor
   ```

Expected output:
```
ESP32 Modular OTA System Starting...
WiFi connected!
IP address: 192.168.1.100
LittleFS mounted successfully
OTA Updater initialized
Module loader initialized
System initialization complete
```

## Step 6: Testing the System

### Initial System Test

1. **Power on ESP32** - All LEDs should be off initially
2. **Check serial monitor** - Should show successful initialization
3. **Press button** - Should log "Vehicle is idle" state
4. **Wait 30 seconds** - System should check for updates

### Simulate Update Process

1. **Modify speed governor code**:
   ```bash
   # Edit mock_drivers/speed_governor/src/speed_governor.c
   # Change MODULE_VERSION to "1.1.1" or similar
   ```

2. **Commit and push changes**:
   ```bash
   git add .
   git commit -m "Update speed governor to fix highway issue"
   git push origin main
   ```

3. **Watch GitHub Actions**:
   - Go to your repository → **Actions** tab
   - Should see workflow running automatically
   - Check logs for build success

4. **Observe ESP32 behavior**:
   - Within 30 seconds, yellow LED should light up
   - Press button to simulate vehicle idle
   - System should download and apply update
   - Green LED indicates success, red indicates failure

## Step 7: Monitoring and Debugging

### Serial Monitor Commands

Use the serial monitor to debug issues:

```bash
# Monitor with timestamp
pio device monitor --filter time

# Monitor with ESP32 exception decoder
pio device monitor --filter esp32_exception_decoder
```

### Common Log Messages

| Message | Meaning | Action |
|---------|---------|--------|
| `WiFi connected!` | Network OK | ✅ Continue |
| `Failed to initialize OTA updater` | Config error | Check SERVER_URL |
| `Found X pending updates` | Updates available | ✅ Normal operation |
| `Hash mismatch!` | Corrupted download | Check network/storage |
| `Module loaded successfully` | Update applied | ✅ Success |

### Troubleshooting Common Issues

**Issue: WiFi won't connect**
```
Solution:
1. Double-check SSID and password
2. Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
3. Check for special characters in credentials
```

**Issue: No updates detected**
```
Solution:
1. Verify manifest.json uploaded to Supabase
2. Check GitHub Actions ran successfully
3. Confirm module version changed in code
```

**Issue: Update download fails**
```
Solution:
1. Check Supabase bucket permissions (must be public)
2. Verify GitHub Secrets are correct
3. Monitor network connectivity
```

**Issue: Hash verification fails**
```
Solution:
1. Re-run GitHub Actions workflow
2. Check file integrity in Supabase storage
3. Clear ESP32 filesystem: LittleFS.format()
```

## Step 8: Advanced Configuration

### Adding New Modules

1. **Create module structure**:
   ```bash
   mkdir -p mock_drivers/your_module/{src,include,build}
   ```

2. **Implement module interface**:
   ```c
   // src/your_module.c
   #include "../../esp32_loader_firmware/include/system_api.h"
   
   static const char* MODULE_NAME = "your_module";
   static const char* MODULE_VERSION = "1.0.0";
   
   // Implement required functions...
   ```

3. **Add to CI/CD workflow**:
   ```yaml
   # Update .github/workflows/build-and-deploy-module.yml
   # Add your module to supported modules list
   ```

### Customizing Update Intervals

```cpp
// In main.cpp, change update check frequency
const unsigned long UPDATE_CHECK_INTERVAL = 10000; // 10 seconds
```

### Security Enhancements

For production use, consider:

1. **Code Signing**:
   ```bash
   # Generate signing keys
   openssl genrsa -out private_key.pem 2048
   openssl rsa -in private_key.pem -pubout -out public_key.pem
   ```

2. **Encrypted Communication**:
   ```cpp
   // Use HTTPS with certificate pinning
   client.setCACert(ca_cert);
   ```

3. **Access Control**:
   ```sql
   -- Supabase RLS policies
   CREATE POLICY "Public read access" ON storage.objects
   FOR SELECT USING (bucket_id = 'ota-modules');
   ```

## Step 9: Production Deployment

### Environment Configuration

Create environment-specific configurations:

```cpp
// config.h
#ifdef PRODUCTION
    #define UPDATE_CHECK_INTERVAL 3600000  // 1 hour
    #define DEBUG_LOGGING false
#else
    #define UPDATE_CHECK_INTERVAL 30000    // 30 seconds  
    #define DEBUG_LOGGING true
#endif
```

### Fleet Management

For managing multiple devices:

1. **Device Registration**:
   ```sql
   CREATE TABLE devices (
     id TEXT PRIMARY KEY,
     last_seen TIMESTAMP,
     firmware_version TEXT,
     location TEXT
   );
   ```

2. **Update Targeting**:
   ```json
   {
     "speed_governor": {
       "latest_version": "1.1.0",
       "target_devices": ["esp32-demo-001", "esp32-demo-002"],
       "rollout_percentage": 50
     }
   }
   ```

### Monitoring Dashboard

Create a web dashboard to monitor your fleet:

```html
<!-- Simple HTML dashboard -->
<!DOCTYPE html>
<html>
<head>
    <title>OTA Dashboard</title>
</head>
<body>
    <h1>Device Status</h1>
    <div id="devices"></div>
    
    <script>
        // Fetch device status from Supabase
        async function updateDashboard() {
            // Implementation here
        }
    </script>
</body>
</html>
```

## Next Steps

Congratulations! Your modular OTA system is now running. Consider these enhancements:

1. **Add More Modules**: Distance sensor, temperature sensor, etc.
2. **Implement Security**: Code signing, encrypted updates
3. **Build Dashboard**: Web interface for monitoring devices  
4. **Scale Up**: Deploy to multiple ESP32 devices
5. **Add Tests**: Unit tests for modules and integration tests

## Support

If you encounter issues:

1. **Check troubleshooting section** above
2. **Review logs** in serial monitor and GitHub Actions
3. **Create an issue** in the repository with:
   - Detailed error description
   - Serial monitor output
   - Hardware configuration
   - Steps to reproduce

Happy building! 🚗💨 