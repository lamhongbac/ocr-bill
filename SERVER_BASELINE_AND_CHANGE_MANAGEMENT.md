# HỒ SƠ QUẢN TRỊ MÁY CHỦ OCR (SERVER BASELINE & CHANGE MANAGEMENT)
## HỆ THỐNG AI OCR HÓA ĐƠN & REVIEW PORTAL GIGAMALL

> **Mục đích tài liệu**: Ghi nhận toàn bộ thông số phần cứng, hệ điều hành, cấu hình mạng, dịch vụ chạy ngầm, đường dẫn dữ liệu và quy trình quản lý thay đổi (Change Management) của máy chủ OCR GigaMall để phục vụ vận hành, bàn giao và bảo trì lâu dài.

---

## 1. THÔNG SỐ PHẦN CỨNG & HỆ ĐIỀU HÀNH (HARDWARE & OS BASELINE)

| Hạng mục | Chi tiết cấu hình | Ghi chú vận hành |
| :--- | :--- | :--- |
| **Hostname** | `server-ocr` | Tên định danh máy chủ |
| **Hệ điều hành** | **Ubuntu 22.04.5 LTS** (x86_64, Linux Kernel 6.8.0-40-generic) | Hỗ trợ dài hạn |
| **Bộ vi xử lý (CPU)** | **Intel Core i7-13700KF** (16 Nhân / 24 Luồng, tối đa 5.4 GHz) | Xử lý đa nhiệm & API |
| **Bộ nhớ RAM** | **8 GB DDR5** (Swap: 2 GB) | Mức sử dụng bình thường ~1.5 - 3.5 GB |
| **Card đồ họa (GPU)** | **NVIDIA GeForce RTX 3060 12GB VRAM** | Driver: `580.178.04`, CUDA 12.x chuyên dụng cho AI OCR |
| **Ổ đĩa hệ thống (OS)** | `/dev/sda5` (42 GB ext4) | Chứa OS, Docker, Python venv (`/opt/ocr-bill`) |
| **Ổ đĩa lưu trữ (Data)** | `/dev/sdb1` (**1 TB / 932 GB NTFS/fuseblk**) mount tại **`/mnt/data`** | Chứa Cache mô hình AI (`huggingface`) và kho ảnh hóa đơn (`uploads/`) |

---

## 2. CẤU HÌNH MẠNG & BẢN ĐỒ CỔNG DỊCH VỤ (NETWORK & PORTS)

### 2.1. Địa chỉ IP
* **IP Nội bộ (LAN)**: `192.168.2.4` (Interface: `enp2s0`)
* **IP Công cộng (Public IP Router)**: `14.161.34.37`
* **Default Gateway**: `192.168.2.1`

### 2.2. Danh sách cổng mở & Bản đồ chuyển tiếp (Port Forwarding / NAT)

| Cổng lắng nghe | Giao thức | Dịch vụ đảm nhiệm | Quyền truy cập | Mục đích sử dụng |
| :---: | :---: | :--- | :---: | :--- |
| **22** | TCP / SSH | `sshd` (OpenSSH) | LAN & Public | Quản trị từ xa (user `msa`) |
| **80** | TCP / HTTP | `nginx` | LAN | Web Portal nội bộ GigaMall |
| **8080** | TCP / HTTP | `nginx` | **Public (NAT)** | Cổng Public chính cho Web Review & CRM API |
| **5000** | TCP / HTTP | `nginx` | LAN | Cổng dự phòng reverse proxy |
| **8000** | TCP / HTTP | `uvicorn` (FastAPI) | Localhost/LAN | Backend xử lý OCR & nghiệp vụ (127.0.0.1:8000) |
| **7070** | TCP | `anydesk` | LAN/WAN | Điều khiển màn hình hỗ trợ từ xa |
| **5939** | TCP | `teamviewerd` | Localhost | TeamViewer daemon dự phòng |

---

## 3. CẤU TRÚC THƯ MỤC & PHÂN BỔ DỮ LIỆU (DIRECTORY LAYOUT)

```text
/opt/ocr-bill/                         <-- Thư mục gốc chứa mã nguồn hệ thống
├── app_review.py                      <-- FastAPI Web Application (UI + API)
├── db.py                              <-- Kết nối MS-SQL & các hàm nghiệp vụ
├── db_config.json                     <-- File cấu hình thông số kết nối CSDL
├── freetds.conf                       <-- Khắc phục mã hóa TLS cho SQL Server 2012
├── ocr_engine.py                      <-- Module nạp mô hình Qwen2-VL & suy luận AI
├── sync_outlets.py                    <-- Script đồng bộ Outlet từ MS-SQL sang JSON
├── master_outlets.json                <-- Danh mục chuẩn gian hàng sau đồng bộ
├── cron_ocr_scanner.py                <-- Script quét tự động hóa đơn PENDING
├── create_tables.sql                  <-- Script DDL tạo bảng OcrBills & Logs
├── venv/                              <-- Virtual Environment Python 3.10
├── TEST_IMAGES/                       <-- Thư mục chứa 101 ảnh hóa đơn mẫu UAT
└── uploads -> /mnt/data/ocr-bill/uploads   <-- Symlink trỏ sang ổ 1TB lưu ảnh hóa đơn
```

* **Vị trí Cache AI Model**: `/mnt/data/ocr-bill/cache/huggingface/` (Tránh làm đầy ổ đĩa hệ điều hành 42GB).
* **Vị trí Log hệ thống**:
  - Web & API stdout: `/var/log/ocr-bill.log`
  - Web & API error: `/var/log/ocr-bill-error.log`
  - Cron scan log: `/opt/ocr-bill/cron_scanner.log`
  - Cron sync outlet: `/opt/ocr-bill/sync_outlets.log`

---

## 4. QUẢN LÝ DỊCH VỤ HỆ THỐNG (SYSTEMD & CRON JOBS)

### 4.1. Dịch vụ Systemd chính
1. **`nginx.service`** (Tự động kích hoạt khi bật máy):
   - File cấu hình: `/etc/nginx/sites-available/ocr-bill`
   - Chức năng: Reverse Proxy điều hướng cổng 80, 8080, 5000 về `127.0.0.1:8000`. Giới hạn upload `client_max_body_size 50M;`.
2. **`ocr-bill.service`** (Tự động kích hoạt khi bật máy):
   - File cấu hình: `/etc/systemd/system/ocr-bill.service`
   - Lệnh thực thi: `/opt/ocr-bill/venv/bin/uvicorn app_review:app --host 0.0.0.0 --port 8000 --workers 1`
   - Biến môi trường: `HF_HOME=/mnt/data/ocr-bill/cache/huggingface`, `FREETDSCONF=/opt/ocr-bill/freetds.conf`.

### 4.2. Tác vụ định kỳ (Cron Jobs của user `msa`)
```bash
# Quét tự động các hóa đơn mới mỗi 15 phút
*/15 * * * * cd /opt/ocr-bill && /opt/ocr-bill/venv/bin/python /opt/ocr-bill/cron_ocr_scanner.py --limit 20 >> /opt/ocr-bill/cron_scanner.log 2>&1

# Đồng bộ lại danh mục gian hàng từ MS-SQL vào 02:00 sáng mỗi ngày
0 2 * * * cd /opt/ocr-bill && /opt/ocr-bill/venv/bin/python /opt/ocr-bill/sync_outlets.py >> /opt/ocr-bill/sync_outlets.log 2>&1
```

---

## 5. KẾT NỐI CƠ SỞ DỮ LIỆU (DATABASE INTEGRATION)

* **Hệ quản trị CSDL**: Microsoft SQL Server 2012 (Host: `115.165.166.208:6868`)
* **User kết nối**: `crmapp1`
* **Môi trường hiện tại**: **`CLMHQTEST`** (Database UAT/POC)
* **Bảng dữ liệu quản lý**:
  - `OcrBills`: Lưu danh sách hóa đơn, kết quả OCR AI đọc, kết quả duyệt.
  - `OcrBillAuditLogs`: Lưu nhật ký kiểm toán (Ai sửa, sửa gì, giá trị cũ/mới, lý do).
  - `G_Outlet` & `G_Brand`: Bảng danh mục gian hàng dùng để tra cứu mã Outlet.

---

## 6. QUY TRÌNH QUẢN LÝ THAY ĐỔI (CHANGE MANAGEMENT WORKFLOW)

Để đảm bảo hệ thống vận hành liên tục (Zero-Downtime) và không xảy ra xung đột khi nâng cấp:

### Bước 1: Phát triển & Kiểm thử tại Local (Máy Mac)
* Toàn bộ mã nguồn mới hoặc chỉnh sửa tính năng phải được kiểm thử trên máy dev trước.
* Đảm bảo không sửa đổi cấu trúc kết nối FreeTDS nếu không có thay đổi từ phía SQL Server.

### Bước 2: Đồng bộ mã nguồn lên Server qua SSH/SFTP
* Sử dụng công cụ đồng bộ an toàn (SFTP / rsync / Git).
* Sau khi đẩy code lên `/opt/ocr-bill/`, kiểm tra tính toàn vẹn bằng MD5 Checksum:
  ```bash
  md5sum /opt/ocr-bill/app_review.py
  ```

### Bước 3: Nạp cấu hình & Khởi động lại dịch vụ
* Nếu thay đổi cấu hình Nginx:
  ```bash
  sudo nginx -t && sudo systemctl reload nginx
  ```
* Nếu thay đổi mã nguồn Python hoặc cấu hình DB (`db_config.json`):
  ```bash
  sudo systemctl restart ocr-bill
  ```

### Bước 4: Kiểm tra sức khỏe hệ thống (Health Check Validation)
* Kiểm tra trạng thái service: `sudo systemctl status ocr-bill`
* Kiểm tra endpoint: `curl -I http://127.0.0.1:8080/api/health`
* Kiểm tra log nếu có lỗi: `tail -n 50 /var/log/ocr-bill-error.log`

### Bước 5: Chuyển đổi môi trường CSDL (Khi đưa lên Production)
Khi kết thúc giai đoạn UAT và cần chuyển sang Production:
1. Mở file `/opt/ocr-bill/db_config.json`.
2. Đổi giá trị `"database": "CLMHQTEST"` thành `"database": "CLMHQ4GIGA"`.
3. Chạy lệnh: `sudo systemctl restart ocr-bill`.
