# CHUYÊN ĐỀ 7: TRIỂN KHAI MÁY CHỦ PILOT, CI/CD & VẬN HÀNH DỊCH VỤ (PILOT DEPLOYMENT & CI/CD OPERATIONS)

> **Mã chuyên đề**: `SPEC-07-PILOT-OPS`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: DevOps Engineer, System Administrator, SRE, Technical Lead

---

## 1. THÔNG SỐ HẠ TẦNG MÁY CHỦ PILOT

* **Địa chỉ IP Public**: `14.161.34.37`
* **Cổng dịch vụ Web/API**: `8080` (qua Nginx Reverse Proxy)
* **Cổng dịch vụ Nội bộ**: `8000` (Uvicorn ASGI Worker)
* **Tài khoản SSH**: `msa`
* **Đường dẫn thư mục dự án**: `/opt/ocr-bill`
* **Cấu hình phần cứng**:
  * **CPU**: Intel Core i7-13700KF (16 Cores, 24 Threads).
  * **GPU**: NVIDIA GeForce RTX 3060 (12GB GDDR6 VRAM, CUDA 12.4).
  * **RAM**: 32GB DDR4.
  * **Ổ đĩa**: 
    * `/dev/sda5` (Phân vùng root 42GB): Dành cho OS và binary hệ thống.
    * `/dev/sda6` (Phân vùng dữ liệu 932GB mount tại `/mnt/data`): Dành cho cache mô hình 7B và tệp ảnh hóa đơn.

---

## 2. QUY TRÌNH CI/CD TỰ ĐỘNG HÓA QUA `deploy_to_pilot.py`

Hệ thống đã xây dựng sẵn script CI/CD [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py) giúp Developer triển khai mã nguồn từ máy Mac lên máy chủ Pilot một cách an toàn và tự động:

```bash
# Kích hoạt CI/CD đẩy toàn bộ code mới nhất lên Pilot
python deploy_to_pilot.py
```

### Quy trình 4 bước tự động:
1. **Kiểm tra cú pháp cục bộ (Syntax Pre-check)**:
   * Chạy `py_compile` trên máy Dev đối với `app_review.py`, `db.py`, `ocr_engine.py`. Nếu có lỗi cú pháp, tiến trình lập tức hủy bỏ để bảo vệ máy chủ Pilot.
2. **Đồng bộ mã nguồn qua SFTP/Paramiko**:
   * Tải lên 10 tệp mã nguồn cốt lõi (bỏ qua `__pycache__`, `.git`, file rác).
3. **Tự động Khởi động lại Dịch vụ hệ thống**:
   * Thực thi lệnh: `echo Admin@2026 | sudo -S systemctl restart ocr-bill`.
   * Kiểm tra xác nhận trạng thái `systemctl is-active ocr-bill == 'active'`.
4. **Kiểm tra sức khỏe đầu cuối (Smoke Test)**:
   * Gửi request kiểm tra `http://14.161.34.37:8080/api/stats` và `http://14.161.34.37:8080/api/health`.
   * Đo đạc độ trễ phản hồi (thường đạt ~80ms cho các API quản trị).

---

## 3. CẤU HÌNH DỊCH VỤ HỆ THỐNG SYSTEMD (`ocr-bill.service`)

Định nghĩa tại `/etc/systemd/system/ocr-bill.service`:
```ini
[Unit]
Description=GigaMall OCR Bill Review & Ingestion API
After=network.target

[Service]
Type=simple
User=msa
WorkingDirectory=/opt/ocr-bill
Environment=PATH=/opt/ocr-bill/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=FREETDSCONF=/opt/ocr-bill/freetds.conf
Environment=HF_HOME=/mnt/data/ocr-bill/cache/huggingface
ExecStart=/opt/ocr-bill/venv/bin/uvicorn app_review:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/var/log/ocr-bill.log
StandardError=append:/var/log/ocr-bill-error.log

[Install]
WantedBy=multi-user.target
```

### Các lệnh quản trị dịch vụ:
```bash
# Xem trạng thái
sudo systemctl status ocr-bill

# Khởi động lại
sudo systemctl restart ocr-bill

# Dừng dịch vụ
sudo systemctl stop ocr-bill

# Xem log thực thi theo thời gian thực
tail -f /var/log/ocr-bill.log

# Xem log lỗi
tail -f /var/log/ocr-bill-error.log
```

---

## 4. CẤU HÌNH NGINX REVERSE PROXY (PORT 8080 ➔ PORT 8000)

Cấu hình tại `/etc/nginx/sites-available/ocr-bill`:
```nginx
server {
    listen 8080;
    server_name _;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
        proxy_connect_timeout 60s;
    }
}
```
* **Lưu ý**: `client_max_body_size 25M` là bắt buộc để hỗ trợ nhận các bức ảnh chụp hóa đơn độ phân giải cao hoặc payload Base64 lớn.
