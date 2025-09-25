# OnLog - Raspberry Pi Edition

Smart Factory IoT Edge-to-Cloud Data Pipeline for Raspberry Pi

## 🚀 Overview

This project provides a complete LoRaWAN gateway solution for Raspberry Pi, designed for industrial IoT data collection and monitoring. It integrates ChirpStack LoRaWAN Network Server with monitoring capabilities for robust edge computing.

### Architecture
- **Edge Computing**: Raspberry Pi with LoRa sensors
- **LoRaWAN Network**: ChirpStack server for device management
- **Data Processing**: Real-time data logging and processing
- **Monitoring**: Prometheus-based system monitoring
- **Cloud Integration**: AWS connectivity for data pipeline

## 📁 Project Structure

```
onlog-edangfood-rpi/
├── chirpstack/              # LoRaWAN Network Server
│   ├── docker-compose.yml   # ChirpStack services
│   ├── configuration/       # Regional LoRa configurations
│   └── logger/              # Data logging application
├── deployment-scripts/      # Deployment automation
│   └── get-docker.sh       # Docker installation script
├── infra/                   # Infrastructure services
│   └── docker-compose.yml   # Supporting services
├── monitoring/              # System monitoring
│   └── node_exporter       # Prometheus Node Exporter
└── README.md
```

## 🔧 Quick Start

### Prerequisites
- Raspberry Pi 4 (recommended) with Raspberry Pi OS
- LoRa concentrator module (e.g., RAK2245, RAK2287)
- Docker and Docker Compose

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/OnLog-System/onlog-edangfood-rpi.git
   cd onlog-edangfood-rpi
   ```

2. **Install Docker (automated)**
   ```bash
   chmod +x deployment-scripts/get-docker.sh
   ./deployment-scripts/get-docker.sh
   ```

3. **Configure LoRa settings**
   ```bash
   # Edit configuration files based on your region
   cd chirpstack/configuration/chirpstack/
   # Modify region-specific .toml files
   ```

4. **Start services**
   ```bash
   # Start infrastructure services
   cd infra
   docker-compose up -d
   
   # Start ChirpStack and monitoring
   cd ../chirpstack
   docker-compose up -d
   ```

## 🌐 Services

| Service | Port | Description |
|---------|------|-------------|
| ChirpStack | 8080 | LoRaWAN Network Server Web UI |
| PostgreSQL | 5432 | Database for ChirpStack |
| Redis | 6379 | Session storage |
| Mosquitto | 1883 | MQTT Broker |
| Node Exporter | 9100 | System metrics |

## 📊 Monitoring

Access monitoring dashboards:
- **ChirpStack UI**: `http://raspberry-pi-ip:8080`
- **Node Exporter Metrics**: `http://raspberry-pi-ip:9100/metrics`
- **Device Synchronization Dashboard**: `./chirpstack/scripts/monitor.sh dashboard`

Default ChirpStack credentials:
- Username: `admin`
- Password: `admin`

### 🔄 Sensor Message Synchronization

The system now includes advanced sensor message synchronization features:

**Features:**
- **Uniform Message Intervals**: Ensures all sensors send messages at consistent intervals
- **Real-time Balance Monitoring**: Detects devices sending too many or too few messages
- **Auto-correction System**: Provides specific recommendations for problematic devices
- **Enhanced Reliability**: Uses MQTT QoS 1 for acknowledged message delivery

**Quick Start:**
```bash
# Setup synchronization features
./chirpstack/scripts/setup.sh install

# Monitor device balance
./chirpstack/scripts/monitor.sh dashboard

# Check current balance status
./chirpstack/scripts/monitor.sh balance

# Run auto-correction analysis
./chirpstack/scripts/monitor.sh correct
```

**Configuration:**
Edit `chirpstack/logger/sync_config.conf` to customize:
- Expected message intervals (default: 60 seconds)
- Balance check frequency (default: 5 minutes)
- QoS levels and timing tolerances

For detailed documentation, see: `chirpstack/logger/README.md`

## 🔌 Hardware Setup

1. **Connect LoRa concentrator** to Raspberry Pi SPI interface
2. **Configure GPIO pins** according to your concentrator module
3. **Update packet forwarder configuration** in ChirpStack settings

## 🐛 Troubleshooting

### Common Issues

**Docker permission denied**
```bash
sudo usermod -aG docker $USER
# Logout and login again
```

**LoRa module not detected**
```bash
# Check SPI is enabled
sudo raspi-config
# Enable SPI in Interface Options
```

**ChirpStack can't connect to database**
```bash
# Check if PostgreSQL container is running
docker ps
# Check logs
docker-compose logs postgresql
```

**Sensor message synchronization issues**
```bash
# Check device message balance
./chirpstack/scripts/monitor.sh balance

# View detailed device status
./chirpstack/scripts/monitor.sh dashboard

# Check logger service status
./chirpstack/scripts/monitor.sh status

# View recent logger activity
./chirpstack/scripts/monitor.sh logs
```

**MQTT message delivery problems**
```bash
# Check MQTT broker logs
docker logs mosquitto

# Verify MQTT logger connectivity
docker exec mqtt-logger python -c "
import paho.mqtt.client as mqtt
c = mqtt.Client()
c.connect('mosquitto', 1883, 60)
print('✅ MQTT connection successful')
"

# Check QoS configuration
docker exec mqtt-logger python -c "
import os
print(f'QoS Level: {os.getenv(\"QOS_LEVEL\", \"1\")}')
"
```

## 📈 Performance Optimization

For Raspberry Pi deployment:
- Allocate at least 2GB RAM
- Use Class 10 SD card or better
- Enable SPI and I2C interfaces
- Consider heat management for continuous operation

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
- Create an issue in this repository
- Contact: OnLog System Team

---
**OnLog System** - Smart Factory IoT Solutions