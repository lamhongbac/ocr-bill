# HƯỚNG DẪN TRIỂN KHAI TRÊN LINUX SERVER & PUBLIC RA INTERNET
> **Dành cho môi trường Production / Khách hàng**  
> *Áp dụng cho: Ubuntu 22.04 / 24.04 LTS (Hỗ trợ GPU NVIDIA hoặc CPU)*

---

## PHẦN 1: SO SÁNH KIẾN TRÚC MAC MINI M4 vs LINUX SERVER

| Thành phần | Mac Mini M4 (Môi trường R&D hiện tại) | Linux Server (Môi trường Khách hàng / Production) |
| :--- | :--- | :--- |
| **Hệ điều hành** | macOS (Darwin ARM64) | Ubuntu 22.04 / 24.04 LTS (x86_64 hoặc ARM64) |
| **Thư viện AI** | `mlx` & `mlx-vlm` *(chỉ chạy trên chip Apple)* | `vLLM` hoặc `transformers` + `torch` *(tối ưu GPU NVIDIA)* |
| **Phần cứng AI** | 24GB Unified Memory (GPU tích hợp) | GPU NVIDIA $\ge 12\text{GB}$ VRAM (RTX 3060 12G, 4060Ti 16G, RTX 3090, A10, T4) |
| **Tốc độ (Latency)** | ~7.6 giây / hóa đơn | **~1.2 – 2.0 giây / hóa đơn** *(khi chạy vLLM trên GPU RTX 3090/4090)* |
| **Quản lý tiến trình** | Terminal / Chạy ngầm tạm thời | `systemd` daemon hoặc `Docker Compose` (tự khởi động cùng OS) |
| **Web Server** | Uvicorn trực tiếp (Port 8000) | **Nginx Reverse Proxy** + HTTPS Let's Encrypt (Port 80, 443) |

---

## PHẦN 2: CHECKLIST TRIỂN KHAI TRÊN LINUX SERVER (TỪ ĐẦU ĐẾN CUỐI)

### Checklist Tổng quan:
- [ ] **Bước 1**: Chuẩn bị máy chủ & Cài đặt NVIDIA Driver + CUDA (nếu có GPU)
- [ ] **Bước 2**: Cài đặt Python 3.11 & Thư viện hệ thống FreeTDS (kết nối MS-SQL)
- [ ] **Bước 3**: Chuyển đổi mã nguồn suy luận từ `mlx-vlm` sang `vLLM` / `transformers`
- [ ] **Bước 4**: Kiểm tra kết nối CSDL MS-SQL (`CLMHQ4GIGA`) từ Linux
- [ ] **Bước 5**: Đóng gói dịch vụ tự khởi động bằng `systemd`
- [ ] **Bước 6**: Cài đặt & cấu hình Nginx Reverse Proxy
- [ ] **Bước 7**: Mở Port Forwarding trên Router & Cài SSL/HTTPS miễn phí
- [ ] **Bước 8**: Thiết lập Tường lửa (Firewall) & Bảo mật hệ thống

---

### BƯỚC 1: Cài đặt Driver NVIDIA & CUDA (Áp dụng nếu Server có GPU NVIDIA)
```bash
# 1. Cập nhật hệ thống
sudo apt update && sudo apt upgrade -y

# 2. Cài đặt NVIDIA Driver chuẩn
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers autoinstall

# Khởi động lại máy để nhận Driver
sudo reboot

# 3. Kiểm tra card đồ họa sau khi reboot
nvidia-smi
```
*(Yêu cầu: Lệnh `nvidia-smi` hiển thị tên GPU và Driver version).*

---

### BƯỚC 2: Cài đặt Python 3.11 & Thư viện FreeTDS
Linux cần `freetds-dev` để thư viện `pymssql` giao tiếp với SQL Server 2012:
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
                    freetds-bin freetds-dev libssl-dev git curl wget

# Tạo thư mục dự án
sudo mkdir -p /opt/ocr-bill && sudo chown -R $USER:$USER /opt/ocr-bill
cd /opt/ocr-bill

# Tạo môi trường ảo Python
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

---

### BƯỚC 3: Cài đặt Thư viện AI & Chuyển đổi Inference Engine

#### Trường hợp 3A: Server có GPU NVIDIA (Khuyến nghị dùng `vLLM` – Tốc độ nhanh nhất)
`vLLM` là engine hàng đầu hiện nay, hỗ trợ Qwen2-VL bóc tách hóa đơn trong **1.2 – 1.8 giây**:
```bash
pip install vllm
pip install fastapi uvicorn pydantic pymssql pillow python-multipart
```

Tạo file dịch vụ suy luận AI chuẩn RESTful trên Linux (`/opt/ocr-bill/ai_service.py`):
```python
# /opt/ocr-bill/ai_service.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from vllm import LLM, SamplingParams
from PIL import Image
import io, json, re, time

app = FastAPI(title="Linux GPU OCR Service")

MODEL_ID = "Qwen/Qwen2-VL-7B-Instruct"  # Hoặc bản 4bit AWQ: Qwen/Qwen2-VL-7B-Instruct-AWQ
print("[*] Đang nạp mô hình vào VRAM GPU...")
llm = LLM(model=MODEL_ID, max_model_len=4096, trust_remote_code=True)
sampling_params = SamplingParams(temperature=0.0, max_tokens=384, repetition_penalty=1.1)

EXTRACTION_PROMPT = """Bạn là chuyên gia bóc tách hóa đơn tại TTTM Gigamall. Hãy đọc ảnh và trả về JSON:
{"brand_name":"","outlet_name":"","bill_number":"","bill_datetime":"YYYY-MM-DD HH:mm:ss","bill_total":0,"is_valid_bill":true}"""

@app.post("/api/v1/extract-bill")
async def extract_bill(file: UploadFile = File(...)):
    t0 = time.time()
    try:
        data = await file.read()
        image = Image.open(io.BytesIO(data)).convert("RGB")
        
        prompt = f"<|im_start|>system\nBạn là trợ lý AI.<|im_end|>\n<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>{EXTRACTION_PROMPT}<|im_end|>\n<|im_start|>assistant\n"
        inputs = {"prompt": prompt, "multi_modal_data": {"image": image}}
        
        outputs = llm.generate([inputs], sampling_params)
        raw_text = outputs[0].outputs[0].text.strip()
        
        return {
            "success": True,
            "latency": round(time.time() - t0, 2),
            "raw_output": raw_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### Trường hợp 3B: Server chỉ có CPU (Không có card GPU rời)
Cài đặt `transformers` + `torch` CPU:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install transformers accelerate qwen-vl-utils pymssql fastapi uvicorn
```

---

### BƯỚC 4: Cấu hình Kết nối MS-SQL Server trên Linux
Tạo file cấu hình FreeTDS tại `/opt/ocr-bill/freetds.conf`:
```ini
[global]
tds version = 7.4
check certificate = no

[CLMHQ4GIGA]
host = 115.165.166.208
port = 6868
tds version = 7.4
encryption = off
check certificate = no
client charset = UTF-8
```

---

### BƯỚC 5: Đóng gói Systemd Service (Tự khởi động cùng Linux)
Tạo tệp service để ứng dụng chạy nền liên tục, tự động khởi động lại nếu bị crash hoặc reboot máy:
```bash
sudo nano /etc/systemd/system/ocr-review.service
```
Dán nội dung:
```ini
[Unit]
Description=GigaMall OCR Review Portal Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/ocr-bill
Environment="PATH=/opt/ocr-bill/venv/bin"
Environment="FREETDSCONF=/opt/ocr-bill/freetds.conf"
ExecStart=/opt/ocr-bill/venv/bin/python -m uvicorn app_review:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Kích hoạt service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ocr-review.service
sudo systemctl start ocr-review.service

# Kiểm tra trạng thái
sudo systemctl status ocr-review.service
```

---

## PHẦN 3: HƯỚNG DẪN PUBLIC RA INTERNET QUA IP PUBLIC / PORT FORWARDING

### Sơ đồ luồng truy cập từ Internet:
```
[Client / Auditor ngoài Internet]
               │ HTTPS (Port 443)
               ▼
   [Router / Modem Khách hàng (IP Public: 115.x.x.x)]
               │ NAT / Port Forwarding
               ▼
[Linux Server: NGINX Reverse Proxy (Port 443 -> SSL Termination)]
               │ Proxy Pass HTTP (127.0.0.1:8000)
               ▼
  [FastAPI Backend: app_review.py] ──> [MS-SQL CLMHQ4GIGA (Port 6868)]
```

---

### BƯỚC 6: Cài đặt & Cấu hình NGINX Reverse Proxy
NGINX đóng vai trò lá chắn bảo vệ, xử lý SSL, cân bằng tải và chặn tấn công:
```bash
sudo apt install -y nginx
```

Tạo file cấu hình `/etc/nginx/sites-available/ocr-portal`:
```bash
sudo nano /etc/nginx/sites-available/ocr-portal
```
Nội dung cấu hình:
```nginx
server {
    listen 80;
    server_name ocr.gigamall.com.vn; # Thay bằng Domain hoặc IP Public của bạn

    # Giới hạn kích thước ảnh tải lên (cho phép bill dài tối đa 20MB)
    client_max_body_size 20M;

    # Chống tấn công brute-force / DDOS
    limit_req_zone $binary_remote_addr zone=ocr_limit:10m rate=10r/s;

    location / {
        limit_req zone=ocr_limit burst=20 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout dài cho model AI xử lý ảnh lớn
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }
}
```

Kích hoạt site:
```bash
sudo ln -s /etc/nginx/sites-available/ocr-portal /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
```

---

### BƯỚC 7: Cấu hình Port Forwarding trên Router & Cài HTTPS

#### 7.1. Cấu hình trên Modem/Router mạng của Khách hàng:
1. Đăng nhập vào trang quản trị Modem (thường là `192.168.1.1`).
2. Tìm mục **Port Forwarding** (hoặc **Virtual Server** / **NAT**).
3. Tạo 2 luật chuyển tiếp (Forwarding Rules) trỏ về IP nội bộ của Linux Server (ví dụ: `192.168.1.200`):
   * **Rule 1 (HTTP)**: External Port `80` $\rightarrow$ Internal Port `80`, Protocol `TCP`, IP `192.168.1.200`.
   * **Rule 2 (HTTPS)**: External Port `443` $\rightarrow$ Internal Port `443`, Protocol `TCP`, IP `192.168.1.200`.

#### 7.2. Cài đặt chứng chỉ SSL/HTTPS miễn phí (Let's Encrypt Certbot):
*(Yêu cầu đã trỏ bản ghi A của tên miền về IP Public của Router)*
```bash
sudo apt install -y certbot python3-certbot-nginx

# Tự động cấp và cấu hình SSL cho Nginx
sudo certbot --nginx -d ocr.gigamall.com.vn
```
Certbot sẽ tự động thiết lập HTTPS và cấu hình tự động gia hạn chứng chỉ trước khi hết hạn.

---

### BƯỚC 8: Tường lửa & Khuyến nghị Bảo mật Sống còn

Để bảo vệ Server khi mở ra Internet, thực hiện các bước sau:

#### 8.1. Cấu hình Tường lửa Linux UFW:
```bash
# Chỉ cho phép SSH, HTTP, HTTPS
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH (nếu đổi port SSH nhớ đổi số này)
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw enable
```

#### 8.2. Thêm mật khẩu bảo vệ Web Portal (HTTP Basic Auth):
Để tránh người ngoài truy cập vào màn hình duyệt bill, bạn có thể tạo tài khoản đăng nhập trực tiếp qua Nginx:
```bash
sudo apt install -y apache2-utils
# Tạo tài khoản crmadmin
sudo htpasswd -c /etc/nginx/.htpasswd crmadmin
```
Trong cấu hình Nginx `/etc/nginx/sites-available/ocr-portal`, thêm vào trong khối `location /`:
```nginx
auth_basic "GigaMall Restricted Review Portal";
auth_basic_user_file /etc/nginx/.htpasswd;
```
Sau đó chạy: `sudo nginx -s reload`.

---

## PHẦN 4: TÓM TẮT CÁC LỆNH VẬN HÀNH TRÊN LINUX

```bash
# Xem log chạy thực tế của ứng dụng
sudo journalctl -u ocr-review.service -f

# Khởi động lại service khi cập nhật code
sudo systemctl restart ocr-review.service

# Kiểm tra log NGINX
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```
