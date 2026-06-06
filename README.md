# Smart Vending Machine with AI Face Recognition

An intelligent kiosk system for unattended retail/vending scenarios, featuring secure AI-powered face recognition, local inventory management, and seamless PayOS payment integration.

## ✨ Key Features

- **🔐 Face Recognition & Anti-Spoofing**: Secure user authentication with liveness detection to prevent fraud
- **🛒 Product Management**: Real-time inventory tracking with SQLite local database
- **💳 PayOS Integration**: QR-based payment flow for frictionless transactions
- **🔄 Cloud Sync**: Automatic background synchronization with backend server
- **📡 MQTT Updates**: Hot product updates via MQTT for dynamic content
- **🖥️ Touchscreen UI**: Modern PyQt5-based interface optimized for kiosk displays
- **📦 Edge Processing**: Minimal server dependency with local-first architecture

## 📹 Demo Video

Watch the Smart Vending Machine in action on YouTube:

[![Smart Vending Machine Demo](https://img.youtube.com/vi/K2tN-iw6_mU/0.jpg)](https://youtu.be/K2tN-iw6_mU?si=gx9MyUp3LhOzg25s)

**▶️ [Click to watch demo on YouTube](https://youtu.be/K2tN-iw6_mU?si=gx9MyUp3LhOzg25s)**

---

## 🔒 Security Notice
This project uses environment variables for sensitive/runtime values.
- Real secrets must stay in `.env` (already ignored by `.gitignore`).
- Use `.env.example` as a template for new deployments.
- Do not commit personal data, credentials, or API keys.

## Quick Start (Raspberry Pi 5)

### 1. System prerequisites
Recommended OS: Raspberry Pi OS 64-bit (Bookworm).

Install required system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-tk \
  libatlas-base-dev libopenblas-dev libjpeg-dev zlib1g-dev \
  libopenjp2-7 libtiff6 libxcb1 libxkbcommon0 libgtk-3-0 \
  libgl1 libglib2.0-0 v4l-utils chromium-browser
```

Optional (for I2C hardware / PCF8574):

```bash
sudo apt install -y i2c-tools python3-smbus
sudo raspi-config
# Interface Options -> I2C -> Enable
```

### 2. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd Vending_Machine_Project
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set real values:
- `VENDING_SERVER_URL`
- `VENDING_DEVICE_ID`
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`
- `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY`
- Optional local payment service settings (`FLASK_HOST`, `FLASK_PORT`, `FLASK_PUBLIC_BASE_URL`)

### 4. Run application

```bash
source .venv/bin/activate
python3 main.py
```

## Configuration Variables
Main runtime variables now centralized via `.env`:

- `VENDING_SERVER_URL`: backend API base URL
- `VENDING_DEVICE_ID`: unique ID for each vending machine
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`: broker connection settings
- `MQTT_TOPIC_PRODUCT_UPDATE`, `MQTT_TOPIC_DATA_CHANGED`: MQTT topics
- `PAYMENT_API_URL`: local endpoint used by UI to request payment links
- `FLASK_HOST`, `FLASK_PORT`, `FLASK_PUBLIC_BASE_URL`: local Flask/PayOS callback settings
- `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY`: PayOS credentials

## Project Structure

```text
Vending_Machine_Project/
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── core/
│   ├── Camera_AI/
│   ├── database/
│   ├── drivers/
│   ├── features/
│   └── ui/
├── images/
└── sounds/
```

## Notes for Production on Raspberry Pi 5
- Set static IP or DHCP reservation for stable device identity.
- Use a unique `VENDING_DEVICE_ID` per physical machine.
- Keep `.env` backed up securely outside source control.
- If running as kiosk, configure autostart and disable screen sleep.
- Verify camera permissions and hardware acceleration if UI/video is laggy.

## License
This project is licensed under the MIT License. See `LICENSE`.
