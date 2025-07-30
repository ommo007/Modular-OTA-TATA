#!/bin/bash

# Raspberry Pi OTA System Installation Script
# Sets up Python environment, dependencies, systemd service, and GPIO permissions

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/rpi_ota_system"
SERVICE_NAME="rpi-ota-system"
USER_NAME="rpi-ota"
PYTHON_VERSION="python3"
VENV_NAME="venv"

# Logging
LOG_FILE="/tmp/rpi_ota_install.log"

# Functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a $LOG_FILE
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ✓ $1" | tee -a $LOG_FILE
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ⚠ $1" | tee -a $LOG_FILE
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ✗ $1" | tee -a $LOG_FILE
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_raspberry_pi() {
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null && ! grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
        log_warning "This doesn't appear to be a Raspberry Pi"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Installation cancelled"
            exit 1
        fi
    fi
}

update_system() {
    log "Updating system packages..."
    apt update && apt upgrade -y
    log_success "System packages updated"
}

install_system_dependencies() {
    log "Installing system dependencies..."
    
    # Essential packages
    apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        git \
        curl \
        wget \
        unzip \
        tree \
        htop \
        vim \
        screen \
        systemd
    
    # GPIO and hardware packages
    apt install -y \
        wiringpi \
        python3-rpi.gpio \
        i2c-tools \
        spi-tools
    
    # Development tools (optional)
    apt install -y \
        gcc \
        g++ \
        make \
        cmake \
        pkg-config
    
    log_success "System dependencies installed"
}

create_user() {
    log "Creating system user..."
    
    if id "$USER_NAME" &>/dev/null; then
        log_warning "User $USER_NAME already exists"
    else
        useradd -r -m -s /bin/bash $USER_NAME
        usermod -a -G gpio,i2c,spi,dialout $USER_NAME
        log_success "User $USER_NAME created and added to hardware groups"
    fi
}

setup_directories() {
    log "Setting up directories..."
    
    # Create main install directory
    mkdir -p $INSTALL_DIR
    
    # Create subdirectories
    mkdir -p $INSTALL_DIR/{config,logs,backups,modules,tests,scripts}
    
    # Set ownership
    chown -R $USER_NAME:$USER_NAME $INSTALL_DIR
    
    # Set permissions
    chmod 755 $INSTALL_DIR
    chmod 755 $INSTALL_DIR/config
    chmod 755 $INSTALL_DIR/logs
    chmod 755 $INSTALL_DIR/backups
    chmod 755 $INSTALL_DIR/modules
    
    log_success "Directories created"
}

copy_files() {
    log "Copying application files..."
    
    # Copy source files
    cp -r src/ $INSTALL_DIR/
    cp -r modules/ $INSTALL_DIR/
    cp -r config/ $INSTALL_DIR/
    cp requirements.txt $INSTALL_DIR/
    
    # Copy scripts
    cp install.sh $INSTALL_DIR/scripts/
    
    # Set ownership
    chown -R $USER_NAME:$USER_NAME $INSTALL_DIR
    
    # Make Python files executable
    find $INSTALL_DIR -name "*.py" -exec chmod +x {} \;
    
    log_success "Application files copied"
}

setup_python_environment() {
    log "Setting up Python virtual environment..."
    
    # Change to install directory
    cd $INSTALL_DIR
    
    # Create virtual environment as the rpi-ota user
    sudo -u $USER_NAME $PYTHON_VERSION -m venv $VENV_NAME
    
    # Activate virtual environment and install dependencies
    sudo -u $USER_NAME bash -c "
        source $VENV_NAME/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt
    "
    
    log_success "Python virtual environment created and dependencies installed"
}

configure_gpio() {
    log "Configuring GPIO access..."
    
    # Enable GPIO, I2C, and SPI interfaces
    if command -v raspi-config >/dev/null 2>&1; then
        raspi-config nonint do_i2c 0     # Enable I2C
        raspi-config nonint do_spi 0     # Enable SPI
        raspi-config nonint do_serial 0  # Enable Serial
        log_success "GPIO interfaces enabled via raspi-config"
    else
        log_warning "raspi-config not available, manual GPIO configuration may be needed"
    fi
    
    # Add user to gpio group (already done in create_user)
    # Create udev rules for GPIO access
    cat > /etc/udev/rules.d/99-rpi-ota-gpio.rules << 'EOF'
# GPIO access rules for Raspberry Pi OTA System
SUBSYSTEM=="gpio", GROUP="gpio", MODE="0664"
SUBSYSTEM=="i2c-dev", GROUP="i2c", MODE="0664"
SUBSYSTEM=="spidev", GROUP="spi", MODE="0664"
EOF
    
    # Reload udev rules
    udevadm control --reload-rules
    udevadm trigger
    
    log_success "GPIO access configured"
}

create_systemd_service() {
    log "Creating systemd service..."
    
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Raspberry Pi OTA System
Documentation=https://github.com/user/rpi-ota-system
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=10
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/$VENV_NAME/bin
ExecStart=$INSTALL_DIR/$VENV_NAME/bin/python src/main.py
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
KillSignal=SIGINT
TimeoutStopSec=30

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$INSTALL_DIR
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes

# Additional hardening
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
DeviceAllow=/dev/gpiomem rw
DeviceAllow=/dev/i2c-* rw
DeviceAllow=/dev/spidev* rw

# Resource limits
LimitNOFILE=65536
LimitNPROC=32768

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    log_success "Systemd service created"
}

configure_logrotate() {
    log "Configuring log rotation..."
    
    cat > /etc/logrotate.d/$SERVICE_NAME << EOF
$INSTALL_DIR/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER_NAME $USER_NAME
    postrotate
        systemctl reload $SERVICE_NAME >/dev/null 2>&1 || true
    endscript
}
EOF
    
    log_success "Log rotation configured"
}

setup_firewall() {
    log "Configuring firewall..."
    
    # Install and configure ufw if available
    if command -v ufw >/dev/null 2>&1; then
        ufw --force enable
        ufw default deny incoming
        ufw default allow outgoing
        ufw allow ssh
        ufw allow 80/tcp   # HTTP (if web interface is added later)
        ufw allow 443/tcp  # HTTPS
        log_success "Firewall configured"
    else
        log_warning "UFW not available, firewall not configured"
    fi
}

create_configuration() {
    log "Creating default configuration..."
    
    # Create example configuration if it doesn't exist
    if [ ! -f "$INSTALL_DIR/config/system_config.yaml" ]; then
        log_warning "system_config.yaml not found, creating from template"
        # The config files should already be copied, but add fallback
    fi
    
    # Set proper permissions on config files
    chmod 640 $INSTALL_DIR/config/*.yaml
    chown $USER_NAME:$USER_NAME $INSTALL_DIR/config/*.yaml
    
    log_success "Configuration files secured"
}

start_service() {
    log "Starting and enabling service..."
    
    # Enable service to start on boot
    systemctl enable $SERVICE_NAME
    
    # Start the service
    systemctl start $SERVICE_NAME
    
    # Check service status
    if systemctl is-active --quiet $SERVICE_NAME; then
        log_success "Service started successfully"
    else
        log_error "Service failed to start"
        systemctl status $SERVICE_NAME --no-pager
        return 1
    fi
}

create_management_scripts() {
    log "Creating management scripts..."
    
    # Create management script
    cat > $INSTALL_DIR/scripts/manage.sh << 'EOF'
#!/bin/bash

# Raspberry Pi OTA System Management Script

SERVICE_NAME="rpi-ota-system"
INSTALL_DIR="/opt/rpi_ota_system"

case "$1" in
    start)
        echo "Starting $SERVICE_NAME..."
        sudo systemctl start $SERVICE_NAME
        ;;
    stop)
        echo "Stopping $SERVICE_NAME..."
        sudo systemctl stop $SERVICE_NAME
        ;;
    restart)
        echo "Restarting $SERVICE_NAME..."
        sudo systemctl restart $SERVICE_NAME
        ;;
    status)
        sudo systemctl status $SERVICE_NAME --no-pager
        ;;
    logs)
        sudo journalctl -u $SERVICE_NAME -f
        ;;
    enable)
        echo "Enabling $SERVICE_NAME to start on boot..."
        sudo systemctl enable $SERVICE_NAME
        ;;
    disable)
        echo "Disabling $SERVICE_NAME from starting on boot..."
        sudo systemctl disable $SERVICE_NAME
        ;;
    update)
        echo "Updating system..."
        cd $INSTALL_DIR
        git pull 2>/dev/null || echo "Not a git repository"
        source venv/bin/activate
        pip install -r requirements.txt --upgrade
        sudo systemctl restart $SERVICE_NAME
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable|update}"
        exit 1
        ;;
esac
EOF
    
    chmod +x $INSTALL_DIR/scripts/manage.sh
    chown $USER_NAME:$USER_NAME $INSTALL_DIR/scripts/manage.sh
    
    # Create symlink for easy access
    ln -sf $INSTALL_DIR/scripts/manage.sh /usr/local/bin/rpi-ota
    
    log_success "Management scripts created"
}

show_completion_info() {
    log_success "Installation completed successfully!"
    echo
    echo -e "${GREEN}Raspberry Pi OTA System is now installed and running!${NC}"
    echo
    echo "Installation details:"
    echo "  • Install directory: $INSTALL_DIR"
    echo "  • Service name: $SERVICE_NAME"
    echo "  • System user: $USER_NAME"
    echo "  • Python environment: $INSTALL_DIR/$VENV_NAME"
    echo
    echo "Management commands:"
    echo "  • Check status: rpi-ota status"
    echo "  • View logs: rpi-ota logs"
    echo "  • Restart service: rpi-ota restart"
    echo "  • Stop service: rpi-ota stop"
    echo "  • Start service: rpi-ota start"
    echo
    echo "Configuration files:"
    echo "  • System config: $INSTALL_DIR/config/system_config.yaml"
    echo "  • GPIO config: $INSTALL_DIR/config/gpio_config.yaml"
    echo "  • Logging config: $INSTALL_DIR/config/logging_config.yaml"
    echo
    echo "Log files:"
    echo "  • System logs: $INSTALL_DIR/logs/"
    echo "  • Service logs: journalctl -u $SERVICE_NAME"
    echo
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Edit configuration files in $INSTALL_DIR/config/"
    echo "2. Configure your Supabase credentials in system_config.yaml"
    echo "3. Check service status: rpi-ota status"
    echo "4. View logs: rpi-ota logs"
    echo
    echo -e "${BLUE}For support and documentation, visit:${NC}"
    echo "https://github.com/user/rpi-ota-system"
}

# Main installation process
main() {
    echo -e "${BLUE}Raspberry Pi OTA System Installation${NC}"
    echo "======================================"
    echo
    
    log "Starting installation process..."
    
    check_root
    check_raspberry_pi
    
    # Installation steps
    update_system
    install_system_dependencies
    create_user
    setup_directories
    copy_files
    setup_python_environment
    configure_gpio
    create_systemd_service
    configure_logrotate
    setup_firewall
    create_configuration
    create_management_scripts
    start_service
    
    show_completion_info
}

# Run main function
main "$@" 