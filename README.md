# 🛒 Smart Vending Machine with AI Face Recognition
### (Máy Bán Hàng Tự Động Thông Minh Tích Hợp Nhận Diện Khuôn Mặt)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![AI](https://img.shields.io/badge/AI-Face_Recognition-green)
![GUI](https://img.shields.io/badge/GUI-CustomTkinter-orange)

## 👨‍💻 Authors (Tác giả)

| Full Name (Họ và Tên) | Student ID (MSSV) | Role (Vai trò) |
| :--- | :--- | :--- |
| **Lê Trần Tùng Dương** | **22520299** | Developer |
| **Đoàn Ngọc Cẩn** | **22520142** | Developer |

---

## 🇻🇳 TIẾNG VIỆT

### 📖 Giới thiệu
Đây là dự án **Máy Bán Hàng Tự Động (Smart Vending Machine)** được phát triển trên nền tảng Python. Hệ thống tích hợp trí tuệ nhân tạo (AI) để nhận diện khuôn mặt khách hàng, cho phép đăng ký thành viên, đăng nhập nhanh chóng và thanh toán tích điểm. Dự án được thiết kế để chạy trên các thiết bị nhúng (như Raspberry Pi) với giao diện cảm ứng thân thiện.

### 🚀 Tính năng nổi bật
* **AI Face Recognition:** Sử dụng **EdgeFace** và **FAISS** để trích xuất đặc trưng và tìm kiếm khuôn mặt tốc độ cao (Real-time).
* **Face Detection:** Sử dụng **MediaPipe** để phát hiện và căn chỉnh khuôn mặt chính xác.
* **Giao diện Kiosk (GUI):** Xây dựng bằng `Tkinter` và `CustomTkinter`, hỗ trợ màn hình cảm ứng, chế độ toàn màn hình.
* **Quản lý bán hàng:** Chọn sản phẩm, giỏ hàng, tính tổng tiền, trừ kho cục bộ.
* **Đồng bộ dữ liệu:** Cơ chế **Offline-First**. Dữ liệu được lưu tại `SQLite` local và tự động đồng bộ lên Server qua API khi có mạng.
* **Đa luồng (Multi-threading):** Tách biệt luồng xử lý Camera/AI và luồng giao diện (UI) giúp ứng dụng mượt mà, không bị treo.

### 🛠 Công nghệ sử dụng
* **Ngôn ngữ:** Python 3.x
* **Giao diện:** Tkinter, CustomTkinter, PIL
* **AI/Computer Vision:** PyTorch, OpenCV, MediaPipe, FAISS, NumPy
* **Database:** SQLite3
* **Hardware Control:** GPIO (LEDs) thông qua driver `PCF8574T` (mô phỏng).

---

## 🇬🇧 ENGLISH

### 📖 Introduction
This is a **Smart Vending Machine** project developed using Python. The system integrates Artificial Intelligence (AI) for facial recognition, enabling customer registration, quick login, and loyalty point payments. The project is optimized for embedded devices (like Raspberry Pi) with a user-friendly touch interface.

### 🚀 Key Features
* **AI Face Recognition:** Utilizes **EdgeFace** and **FAISS** for high-speed, real-time feature extraction and vector search.
* **Face Detection:** Implements **MediaPipe** for accurate face detection and alignment.
* **Kiosk Interface (GUI):** Built with `Tkinter` and `CustomTkinter`, supporting touchscreens and full-screen mode.
* **Sales Management:** Product selection, shopping cart logic, total calculation, and local inventory deduction.
* **Data Synchronization:** **Offline-First** architecture. Data is stored in local `SQLite` and automatically syncs to the Server via API when online.
* **Multi-threading:** Separates Camera/AI processing threads from the UI thread to ensure a smooth, non-blocking user experience.

### 🛠 Tech Stack
* **Language:** Python 3.x
* **GUI:** Tkinter, CustomTkinter, PIL
* **AI/Computer Vision:** PyTorch, OpenCV, MediaPipe, FAISS, NumPy
* **Database:** SQLite3
* **Hardware Control:** GPIO (LEDs) via `PCF8574T` driver (simulated).

---

## 📂 Project Structure (Cấu trúc dự án)

```text
📦 SHOPPING_KEYPAD_APP
 ┣ 📂 core
 ┃ ┣ 📂 Camera_AI
 ┃ ┃ ┣ 📂 backbones
 ┃ ┃ ┣ 📜 face_recognition_library.py  # Core AI logic (EdgeFace, FAISS)
 ┃ ┃ ┗ 📂 checkpoints                  # Contains AI Models (.pt files)
 ┃ ┣ 📂 database
 ┃ ┃ ┗ 📜 local_database_manager.py    # SQLite handler & Sync logic
 ┃ ┣ 📂 ui
 ┃ ┃ ┣ 📜 ui_controller.py             # Main App Controller
 ┃ ┃ ┣ 📜 ai_face_login_screen.py      # Face Login UI
 ┃ ┃ ┣ 📜 ai_face_register_screen.py   # Face Register UI
 ┃ ┃ ┣ 📜 ui_confirmation              
 ┃ ┃ ┣ 📜 ui_login
 ┃ ┃ ┣ 📜 ui_main
 ┃ ┃ ┣ 📜 ui_register
 ┃ ┃ ┣ 📜 ui_thankyou
 ┃ ┃ ┣ 📜 ui_welcome
 ┃ ┃ ┗ 
 ┣ 📜 config.py                        # Configuration settings
 ┣ 📜 main.py                   
 ┗ 📜 requirements.txt                 # Python dependencies