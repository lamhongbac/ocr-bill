# CHUYÊN ĐỀ 1: KIẾN TRÚC HỆ THỐNG, MÔI TRƯỜNG & HẠ TẦNG CSDL (SYSTEM ARCHITECTURE & TECH STACK)

> **Mã chuyên đề**: `SPEC-01-ARCH`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: AI Engineer, Solution Architect, System Administrator, DevOps

---

## 1. TỔNG QUAN GIẢI PHÁP & MỤC TIÊU NGHIỆP VỤ

Hệ thống **AI OCR Hóa đơn & Quản trị Duyệt Kiểm toán Gigamall** là giải pháp trí tuệ nhân tạo thị giác đa phương thức (Vision-Language Model - VLM) phục vụ tự động hóa quy trình bóc tách dữ liệu từ ảnh chụp hóa đơn bán lẻ, F&B, giải trí tại Trung tâm Thương mại Gigamall.

Hệ thống giải quyết 3 bài toán nghiệp vụ trọng tâm:
1. **Thẩm định & Tích điểm Tự động cho Thành viên CRM**: Tiếp nhận ảnh chụp từ Mobile App hoặc CRM Backend, trích xuất tức thì số tiền, ngày giờ, số hóa đơn và chuẩn hóa mã cửa hàng (`outlet_number`).
2. **Cổng Giám sát & Duyệt Hóa đơn (Admin Review & Audit Portal)**: Cung cấp giao diện trực quan cho Kiểm toán viên / Admin soi ảnh, sửa trực tiếp các trường sai lệch và lưu vết lịch sử kiểm toán nghiêm ngặt (`OcrBillAuditLogs`).
3. **Quét định kỳ & Chống thất lạc (Background Cron Scanner)**: Cơ chế quét độc lập, chống sót hóa đơn khi mất kết nối mạng hoặc dồn tải xử lý ban đêm.

---

## 2. KIẾN TRÚC HẠ TẦNG 2 MÔI TRƯỜNG (DUAL ENVIRONMENT ARCHITECTURE)

Hệ thống được thiết kế vận hành tương thích trên 2 kiến trúc phần cứng khác nhau:

```
┌────────────────────────────────────────────────────────┐       ┌────────────────────────────────────────────────────────┐
│               MÔI TRƯỜNG DEV (R&D & ĐÁNH GIÁ)          │       │             MÔI TRƯỜNG PILOT / PRODUCTION              │
├────────────────────────────────────────────────────────┤       ├────────────────────────────────────────────────────────┤
│ • Phần cứng: Mac Mini M4 (10-core CPU, 10-core GPU)    │       │ • Phần cứng: Intel Core i7-13700KF (24 vCPUs)          │
│ • Bộ nhớ: 24GB Unified Memory                          │       │ • GPU: NVIDIA GeForce RTX 3060 (12GB GDDR6 VRAM)       │
│ • Hệ điều hành: macOS 26.6.2 (Darwin ARM64)            │       │ • RAM: 32GB DDR4 | Đĩa cứng: 932GB chuyên dụng (/mnt) │
│ • AI Engine: Apple Silicon Metal qua MLX & mlx-vlm     │       │ • Hệ điều hành: Ubuntu 22.04 LTS (x86_64)              │
│ • Lưu trữ: SanDisk ExternalSSD (ExFAT)                 │       │ • AI Engine: PyTorch 2.4 + CUDA 12.4 + BitsAndBytes    │
│ • Web Server: FastAPI / Uvicorn (Port 8000)            │       │ • Systemd Service: ocr-bill.service + Nginx Proxy 8080 │
└──────────────────────────┬─────────────────────────────┘       └──────────────────────────┬─────────────────────────────┘
                           │                                                                │
                           └───────────────────────┬────────────────────────────────────────┘
                                                   │
                                                   ▼
                                ┌──────────────────────────────────────┐
                                │      CSDL MS-SQL SERVER 2012         │
                                │   115.165.166.208:6868 (CLMHQ4GIGA)  │
                                │    Driver: PyMSSQL 2.4.5 + FreeTDS   │
                                └──────────────────────────────────────┘
```

---

## 3. CÔNG NGHỆ THỰC THI (TECH STACK SPECIFICATIONS)

| Thành phần | Công nghệ / Thư viện | Phiên bản | Vai trò & Mục đích sử dụng |
| :--- | :--- | :---: | :--- |
| **Ngôn ngữ** | Python | `3.11.17` (Dev) / `3.10` (Pilot) | Runtime chính cho toàn bộ API và Core AI |
| **Mô hình VLM** | `Qwen2-VL-7B-Instruct` | 4-bit (NF4) | Bóc tách ngữ nghĩa thị giác đa ngôn ngữ tiếng Việt |
| **AI Inference (Dev)** | `mlx` & `mlx-vlm` | `0.32.4` / `0.7.9` | Tận dụng Unified Memory trên chip Apple Silicon M4 |
| **AI Inference (Pilot)**| `torch` + `bitsandbytes` | `2.4.0` / `0.43.3` | Nạp mô hình 7B 4-bit lên GPU NVIDIA RTX 3060 CUDA |
| **Vision Utilities** | `qwen-vl-utils` + `Pillow`| `0.0.8` / `10.4.0` | Tiền xử lý ảnh (xoay EXIF, resize thích ứng max 1600px) |
| **Web Framework** | `fastapi` | `0.150.0` | Cung cấp RESTful API hiệu năng cao, hỗ trợ Async |
| **ASGI Server** | `uvicorn` | `0.54.0` | Quản lý worker, lắng nghe kết nối HTTP |
| **CSDL Driver** | `pymssql` + `FreeTDS` | `2.4.5` / `1.5.19` | Kết nối CSDL MS-SQL Server 2012 qua cổng 6868 |
| **So khớp mờ** | `difflib` + `unicodedata` | Chuẩn Python | Thuật toán normalize tiếng Việt và SequenceMatcher |

---

## 4. KẾT NỐI CƠ SỞ DỮ LIỆU MS-SQL SERVER & CẤU HÌNH BẢO MẬT TLS

### 4.1. Thông số Kết nối Máy chủ CSDL
* **IP Server**: `115.165.166.208`
* **Port**: `6868`
* **Database Name**: `CLMHQ4GIGA` (Pilot/Prod) hoặc `OCRInvoice` / `CLMHQTEST` (Dev)
* **User ứng dụng**: `crmapp1`
* **Phiên bản máy chủ**: Microsoft SQL Server 2012 - 11.0.2100.60 (X64).

### 4.2. Giải pháp Kỹ thuật vượt qua lỗi Handshake TLS (CỰC KỲ QUAN TRỌNG)
* **Vấn đề**: SQL Server 2012 sử dụng bộ mã hóa TLS cũ mà OpenSSL 3.0 trên hệ điều hành hiện đại (macOS 14+ và Ubuntu 22.04+) mặc định từ chối bắt tay (Handshake Failure / `SSL routines:ssl3_read_bytes:tlsv1 alert internal error`).
* **Giải pháp chuẩn hóa**: Sử dụng `FreeTDS` phiên bản 1.5.19 kết hợp tệp cấu hình `freetds.conf` tại thư mục gốc dự án:
  ```ini
  [CLMHQ4GIGA]
  host = 115.165.166.208
  port = 6868
  tds version = 7.4
  encryption = off
  check certificate = no
  client charset = UTF-8
  ```
* **Kích hoạt trong mã nguồn Python**: Mọi script phải nạp biến môi trường trước khi import hoặc kết nối:
  ```python
  import os
  from pathlib import Path
  os.environ["FREETDSCONF"] = str(Path(__file__).parent / "freetds.conf")
  ```

---

## 5. ĐẶC TẢ LƯU TRỮ VẬT LÝ VÀ HỆ THỐNG TỆP (STORAGE & FILESYSTEM)

### 5.1. Môi trường Dev (Ổ đĩa ExFAT)
* Ổ đĩa ngoài định dạng **ExFAT** (`/Volumes/ExternalSSD/ocr-bill`).
* **Lưu ý sống còn về ExFAT**: Hệ thống tệp ExFAT **không hỗ trợ Symbolic Links**. Do đó, môi trường ảo Python phải được tạo bằng cờ sao chép nhị phân:
  ```bash
  python3.11 -m venv --copies venv
  ```

### 5.2. Môi trường Pilot (Phân vùng chuyên dụng 932GB)
* Phân vùng gốc `/` (42GB) dùng cho hệ điều hành.
* Phân vùng dữ liệu `/mnt/data` (932GB) dùng lưu trữ toàn bộ:
  * Cache trọng số HuggingFace: `/mnt/data/ocr-bill/cache/huggingface` (`HF_HOME`).
  * Trọng số 5 shards của mô hình `Qwen2-VL-7B-Instruct` (~15GB).
  * Ảnh hóa đơn lưu trữ dài hạn: `/opt/ocr-bill/uploads/`.
