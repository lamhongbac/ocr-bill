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

## 6. QUY TRÌNH QUẢN LÝ THAY ĐỔI & TRIỂN KHAI PILOT (DEPLOYMENT & CHANGE MANAGEMENT RUNBOOK)

Để đảm bảo hệ thống Pilot vận hành liên tục (Zero-Downtime), an toàn dữ liệu và các kỹ sư kế thừa có thể triển khai cập nhật một cách nhất quán, quy trình triển khai được chuẩn hóa thành 2 phương thức: **Tự động hóa (Khuyến nghị)** và **Thủ công (Dự phòng)**.

---

### 6.1. Kiến trúc Triển khai (Deployment Architecture)

```
[Máy Dev / Mac Mini]
        │
        ├── 1. Kiểm tra cú pháp (py_compile)
        ├── 2. Kết nối SSH/SFTP (Port 22, User: msa)
        │       │
        │       ▼
[Server Pilot: 14.161.34.37]
        ├── Đẩy mã nguồn vào /opt/ocr-bill/
        ├── Restart dịch vụ ocr-bill.service (Systemd)
        │       │
        │       ▼
[Kiểm thử khói (Smoke Test)]
        └── HTTP GET http://14.161.34.37:8080/api/stats
            (Kiểm tra độ trễ phản hồi & kết nối Database)
```

* **Thông số kết nối Pilot Server**:
  * **IP / Host**: `14.161.34.37` (Port SSH: `22`)
  * **Tài khoản**: `msa`
  * **Thư mục cài đặt**: `/opt/ocr-bill/`
  * **Dịch vụ Backend**: `ocr-bill.service` (Quản lý bởi `systemd`, chạy Uvicorn trên `127.0.0.1:8000`)
  * **Reverse Proxy**: Nginx lắng nghe cổng Public `8080` (chuyển tiếp về `127.0.0.1:8000`)

---

### 6.2. Triển khai Tự động hóa qua Script `deploy_to_pilot.py` (Khuyến nghị)

Dự án đã tích hợp sẵn script triển khai tự động [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py). Kỹ sư chỉ cần chạy một lệnh duy nhất từ máy trạm:

```bash
# Đứng tại thư mục gốc dự án trên máy Dev
./venv/bin/python deploy_to_pilot.py
```

#### Quy trình 5 bước thực thi tự động của Script:
1. **Bước 1: Pre-flight Syntax Check**:
   - Sử dụng module `py_compile` để biên dịch thử `app_review.py`, `db.py`, `ocr_engine.py`.
   - Nếu có lỗi cú pháp (SyntaxError/IndentationError), script lập tức dừng lại, **không đẩy mã lỗi lên server**.
2. **Bước 2: Differential SFTP Upload**:
   - Mở kênh SFTP an toàn tới `14.161.34.37:22`.
   - Tải các tệp mã nguồn mới nhất lên `/opt/ocr-bill/` (ghi nhận kích thước KB từng tệp).
   - *Lưu ý*: Script **không ghi đè** `db_config.json` hay `freetds.conf` đã cấu hình riêng cho môi trường của máy chủ.
3. **Bước 3: Graceful Service Restart**:
   - Thực thi lệnh từ xa: `sudo systemctl restart ocr-bill`.
   - Kiểm tra ngay trạng thái bằng `sudo systemctl is-active ocr-bill` (phải trả về `active`).
4. **Bước 4: Automated Smoke Testing & Latency Verification**:
   - Gửi yêu cầu `GET http://14.161.34.37:8080/api/stats`.
   - Xác nhận mã phản hồi `HTTP 200 OK`, đo độ trễ mạng (thường < 150ms) và in ra số liệu thống kê hóa đơn thực tế từ CSDL.
5. **Bước 5: Đồng bộ Phiên bản vào Git**:
   - Sau khi deploy thành công, kỹ sư thực hiện commit và push lên kho mã nguồn Git chung:
     ```bash
     git commit -am "feat/fix: mô tả nội dung cập nhật"
     git push origin main
     ```

---

### 6.3. Quy trình Triển khai Thủ công qua Terminal (Dành cho Kỹ sư)

Trong trường hợp cần can thiệp từng file hoặc không có môi trường chạy script Python:

#### 1. Đẩy mã nguồn qua `scp` hoặc `rsync`:
```bash
# Đẩy các file mã nguồn cốt lõi
scp app_review.py db.py ocr_engine.py master_outlets.json msa@14.161.34.37:/opt/ocr-bill/
```

#### 2. Đăng nhập SSH vào Server kiểm tra toàn vẹn file:
```bash
ssh msa@14.161.34.37
cd /opt/ocr-bill

# Kiểm tra MD5 checksum đối chiếu
md5sum app_review.py db.py
```

#### 3. Khởi động lại dịch vụ Backend & Nginx:
```bash
# Nạp lại dịch vụ OCR Backend
sudo systemctl restart ocr-bill

# Kiểm tra trạng thái đang chạy
sudo systemctl status ocr-bill --no-pager

# (Chỉ khi có sửa đổi cấu hình Nginx)
sudo nginx -t && sudo systemctl reload nginx
```

#### 4. Kiểm tra sức khỏe hệ thống (Health Check Validation):
```bash
# Kiểm tra API cục bộ trên server
curl -I http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/stats | jq .

# Kiểm tra qua cổng Nginx Public 8080
curl -I http://14.161.34.37:8080/api/health
```

---

### 6.4. Nguyên tắc Cách ly Cấu hình & Bảo mật (Configuration Safety)

1. **Tuyệt đối không ghi đè `db_config.json`**:
   - Máy Dev có thể trỏ tới database Dev (`OCRInvoice` tại `45.119.87.247`).
   - Server Pilot hiện đang trỏ tới database UAT/POC (`CLMHQTEST` tại `115.165.166.208:6868`).
   - Mọi thay đổi về cấu hình DB trên server phải sửa trực tiếp trên file `/opt/ocr-bill/db_config.json` tại server, không deploy file này từ máy dev.
2. **Quyền sở hữu file (Permissions)**:
   - Toàn bộ file trong `/opt/ocr-bill/` thuộc quyền sở hữu của user `msa:msa`:
     ```bash
     sudo chown -R msa:msa /opt/ocr-bill/
     ```
3. **Thư mục lưu trữ ảnh hóa đơn**:
   - Ảnh hóa đơn được lưu vào ổ cứng 1TB qua symlink `/opt/ocr-bill/uploads -> /mnt/data/ocr-bill/uploads`.
   - Tuyệt đối không xóa hoặc thay thế symlink này.

---

### 6.5. Quy trình Rollback & Xử lý Sự cố khẩn cấp (Incident & Rollback Runbook)

Nếu phiên bản mới phát sinh lỗi nghiêm trọng sau khi deploy:

#### 1. Kiểm tra log lỗi thời gian thực:
```bash
# Xem log systemd của dịch vụ
sudo journalctl -u ocr-bill -n 100 -f

# Hoặc xem file log ứng dụng
tail -n 100 -f /var/log/ocr-bill-error.log
```

#### 2. Phục hồi nhanh từ bản sao lưu (Rollback trong 30 giây):
Trước mỗi đợt bảo trì lớn, tạo bản snapshot dự phòng trên server:
```bash
# Trên server: Tạo snapshot trước khi deploy
cp /opt/ocr-bill/app_review.py /opt/ocr-bill/app_review.py.bak_$(date +%Y%m%d_%H%M%S)

# Nếu cần rollback khôi phục bản cũ:
cp /opt/ocr-bill/app_review.py.bak_<timestamp> /opt/ocr-bill/app_review.py
sudo systemctl restart ocr-bill
```

#### 3. Chuyển đổi môi trường CSDL (Khi chính thức Golive Production):
1. Mở file `/opt/ocr-bill/db_config.json` trên server.
2. Đổi giá trị `"database": "CLMHQTEST"` thành `"database": "CLMHQ4GIGA"`.
3. Khởi động lại dịch vụ: `sudo systemctl restart ocr-bill`.
4. Gọi `/api/stats` để xác nhận kết nối thành công tới database Production.

