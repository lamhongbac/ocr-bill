# SỔ TAY BÀN GIAO & MỤC LỤC DANH MỤC GIẢI PHÁP HỆ THỐNG AI OCR HÓA ĐƠN GIGAMALL
## MASTER SYSTEM GUIDE & TOPIC CATALOG SPECIFICATION

> **Tài liệu Bàn giao Tổng thể & Danh mục Chuyên đề Hệ thống**  
> **Phiên bản**: `2.0 - Final Production Catalog`  
> **Ngày cập nhật**: `25/10/2026`  
> **Áp dụng cho**: Toàn bộ Kỹ sư AI, Backend CRM, DevOps, Solution Architect và Kiểm toán viên tiếp quản hệ thống.

---

> [!IMPORTANT]
> ### 🧭 CẤU TRÚC TÀI LIỆU DẠNG MỤC LỤC (CATALOG ARCHITECTURE)
> Tài liệu này đóng vai trò là **Mục Lục Trung Tâm (Master Catalog Document)**:
> 1. Trình bày bức tranh tổng thể, kiến trúc hệ thống và tóm tắt giải pháp cốt lõi của tất cả các chủ đề.
> 2. **Toàn bộ thông số kỹ thuật chi tiết, thuật toán, mã nguồn mẫu và hướng dẫn cài đặt sâu** được phân rã thành **8 tài liệu chuyên đề độc lập** trong thư mục [`docs/`](file:///Volumes/ExternalSSD/ocr-bill/docs).
> 3. Độc giả có thể nhấp chuột trực tiếp vào từng liên kết chuyên đề dưới đây để tra cứu chi tiết tương ứng với vai trò của mình.

---

## 1. TỔNG QUAN GIẢI PHÁP & NGUYÊN LÝ HOẠT ĐỘNG

Hệ thống **AI OCR Hóa đơn & Quản trị Duyệt Kiểm toán Gigamall** là giải pháp trí tuệ nhân tạo thị giác đa phương thức (Vision-Language Model - VLM) phục vụ tự động hóa quy trình bóc tách dữ liệu từ ảnh chụp hóa đơn mua sắm, F&B, giải trí tại Trung tâm Thương mại Gigamall.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           SƠ ĐỒ TỔNG THỂ GIẢI PHÁP AI OCR HÓA ĐƠN GIGAMALL                      │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                 │
│  [NGUỒN DỮ LIỆU ĐẦU VÀO]                                                                        │
│  ├── Khách hàng chụp ảnh trên Gigamall Mobile App                                               │
│  └── Backend CRM đẩy ảnh tự động (Base64 hoặc Multipart)                                        │
│          │                                                                                      │
│          ▼                                                                                      │
│  [MÁY CHỦ PILOT OCR - 14.161.34.37:8080]                                                        │
│  ├── Nginx Reverse Proxy (Port 8080, client_max_body_size 25M)                                  │
│  ├── FastAPI Core Engine (Port 8000)                                                            │
│  │   ├── POST /api/v1/extract-bill  ──> Hỗ trợ KÉP (Multipart Form-Data & Base64 JSON)          │
│  │   ├── POST /api/v1/bills/upload  ──> Chế độ Fast Save (< 0.1s lưu đĩa, OCR ngầm)             │
│  │   └── POST /api/v1/sync-outlets ──> Hot-reload RAM danh mục 193 cửa hàng                    │
│  │                                                                                              │
│  └── CORE AI VISION - GPU NVIDIA RTX 3060 (12GB VRAM)                                           │
│      ├── Mô hình Qwen2-VL-7B-Instruct (NF4 4-bit qua BitsAndBytes)                              │
│      ├── Tốc độ bóc tách: ~3.5 giây / hóa đơn (Nhanh gấp 2.2 lần so với Mac Mini M4)            │
│      ├── Thường trú VRAM (3.8GB / 12GB VRAM) - Không lo tràn bộ nhớ                            │
│      └── Thuật toán Bóc tách Định dạng Tiền Việt Nam (VND) & So khớp mờ 193 Outlets             │
│          │                                                                                      │
│          ▼                                                                                      │
│  [CSDL MS-SQL SERVER 2012 - 115.165.166.208:6868 (CLMHQ4GIGA)]                                  │
│  ├── Bảng OcrBills: Lưu hóa đơn, kết quả AI ban đầu & giá trị Admin phê duyệt chính thức        │
│  ├── Bảng OcrBillAuditLogs: Vết kiểm toán chi tiết từng thao tác sửa đổi                       │
│  └── Bảng G_Outlet & G_Brand: Nguồn danh mục 193 cửa hàng đồng bộ thời gian thực                │
│          │                                                                                      │
│          ▼                                                                                      │
│  [CỔNG QUẢN TRỊ DUYỆT & KIỂM TOÁN - http://14.161.34.37:8080]                                   │
│  ├── US 1 (Review Workflow): Màn hình soi ảnh độ nét cao (zoom/xoay), phím tắt [A], [R]         │
│  ├── US 2 (Inline Correction): Sửa quán (Autocomplete 193 Outlets), sửa tiền (cảnh báo vàng)   │
│  ├── US 3 (Audit Trail): Dòng thời gian lịch sử & xuất báo cáo CSV cho Auditor                  │
│  └── AI Inspector Tooling: Phân tích Top 3 ứng viên so khớp mờ & Raw VLM JSON                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. BẢNG MỤC LỤC DANH MỤC 8 CHUYÊN ĐỀ HỆ THỐNG (CATALOG SPECIFICATION)

Dưới đây là danh mục 8 chuyên đề kỹ thuật chi tiết của hệ thống. Mỗi chuyên đề bao gồm phạm vi tài liệu, đối tượng áp dụng, tóm lược giải pháp cốt lõi và liên kết trực tiếp tới tài liệu chuyên sâu:

| Mã | Tên Chuyên đề & Liên kết | Đối tượng | Tóm lược Nội dung & Phát hiện Kỹ thuật Trọng tâm |
| :---: | :--- | :--- | :--- |
| **01** | [**Kiến trúc Hệ thống, Môi trường & CSDL**](file:///Volumes/ExternalSSD/ocr-bill/docs/01_SYSTEM_ARCHITECTURE_TECH_STACK.md)<br>`SPEC-01-ARCH` | System Arch,<br>AI Eng,<br>Sysadmin | • Kiến trúc 2 môi trường: Mac Mini M4 (Metal/MLX) và Pilot Linux (NVIDIA RTX 3060 CUDA).<br>• Cấu hình FreeTDS 1.5.19 giải quyết lỗi bắt tay TLS với SQL Server 2012.<br>• Lưu ý ExFAT trên ổ đĩa ngoài (bắt buộc dùng `venv --copies`). |
| **02** | [**Tối ưu hóa Mô hình 7B & Tăng tốc GPU RTX 3060**](file:///Volumes/ExternalSSD/ocr-bill/docs/02_VLM_MODEL_AND_GPU_OPTIMIZATION.md)<br>`SPEC-02-VLM-GPU` | AI Eng,<br>MLOps,<br>DevOps | • **Giải mã lỗi Empty Result**: Do mô hình 2B nhại lại schema rỗng của prompt.<br>• Nâng cấp lên `Qwen2-VL-7B-Instruct` NF4 4-bit (chỉ tốn 3.8GB/12GB VRAM).<br>• Chuyển cache HuggingFace sang phân vùng 924GB (`/mnt/data`).<br>• **Hạ độ trễ từ 7.8s xuống ~3.5s/bill (nhanh gấp 2.2x)**. |
| **03** | [**Quy tắc Bóc tách Tiền VND & So khớp 193 Outlets**](file:///Volumes/ExternalSSD/ocr-bill/docs/03_VIETNAMESE_CURRENCY_AND_EXTRACTION_RULES.md)<br>`SPEC-03-RULES-VND` | AI Eng,<br>Backend,<br>QA Tester | • Quy tắc tiền tệ Việt Nam: Dấu `.` và `,` là phân tách ngàn (`204.000` $\rightarrow$ `204000`).<br>• Thuật toán `to_int_amount()` tự động nhân 1000 cho hóa đơn bán lẻ TTTM.<br>• Quy tắc 4 chuẩn hóa số HĐ: 6 số cuối, `zfill`, dự phòng ngày giờ.<br>• So khớp mờ 193 Outlets từ CSDL DEV, trích xuất Top 3 ứng viên. |
| **04** | [**Đặc tả API Tích hợp CRM & Mobile (.NET Sample)**](file:///Volumes/ExternalSSD/ocr-bill/docs/04_CRM_API_INTEGRATION_SPEC.md)<br>`SPEC-04-CRM-API` | CRM Dev,<br>Mobile Dev,<br>Solution Arch | • Đặc tả chi tiết `/api/v1/extract-bill` hỗ trợ kép Multipart Form và Base64 JSON.<br>• Cơ chế Fast Save phản hồi `< 0.1s`, OCR chạy ngầm.<br>• Quản lý trùng lặp (`warn`, `allow`, `reject`).<br>• **Mã nguồn mẫu C# .NET hoàn chỉnh** được nhúng trực tiếp trong tài liệu tích hợp. |
| **05** | [**Cổng Quản trị Duyệt Bill & Vết Kiểm toán CRM**](file:///Volumes/ExternalSSD/ocr-bill/docs/05_WEB_REVIEW_AUDIT_PORTAL.md)<br>`SPEC-05-REVIEW-PORTAL` | Product Owner,<br>Auditor,<br>Fullstack Dev | • US 1: Giao diện soi ảnh (zoom/xoay), phím tắt tốc độ cao `[A]`, `[R]`, `[←]`, `[→]`.<br>• US 2: Autocomplete 193 Outlets, tag cảnh báo vàng sai lệch số tiền.<br>• US 3: Timeline lịch sử, vết kiểm toán `OcrBillAuditLogs`, xuất báo cáo CSV.<br>• Khối công cụ AI Inspector trên Web UI: Top 3 so khớp mờ, Raw VLM JSON. |
| **06** | [**Tác vụ Quét Ngầm Cron & Đồng bộ CSDL Tự động**](file:///Volumes/ExternalSSD/ocr-bill/docs/06_CRON_SCANNER_AND_SYNC_OPERATIONS.md)<br>`SPEC-06-CRON-SYNC` | Sysadmin,<br>DevOps,<br>Backend Dev | • Tiến trình `cron_ocr_scanner.py`: Quét độc lập 15 phút/lần hoặc ban đêm, chống sót bill.<br>• **Chốt chặn an toàn môi trường DEV**: Khóa tự động trên Dev, chỉ chạy trên Pilot/Prod.<br>• API Báo cáo Giám sát Cron (`/api/v1/admin/cron-report`).<br>• Đồng bộ danh mục tự động qua API `POST /api/v1/sync-outlets` (Hot-reload RAM). |
| **07** | [**Triển khai Máy chủ Pilot, CI/CD & Vận hành Dịch vụ**](file:///Volumes/ExternalSSD/ocr-bill/docs/07_PILOT_DEPLOYMENT_CI_CD_OPS.md)<br>`SPEC-07-PILOT-OPS` | DevOps,<br>Sysadmin,<br>SRE Lead | • Thông số máy chủ Pilot `14.161.34.37:8080` (i7-13700KF, RTX 3060 12GB).<br>• Script CI/CD tự động [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py) (Kiểm tra cú pháp, đẩy code, restart, smoke test).<br>• Dịch vụ systemd `ocr-bill.service` và cấu hình Nginx Reverse Proxy. |
| **08** | [**Đối chiếu Môi trường & Quản lý Thay đổi**](file:///Volumes/ExternalSSD/ocr-bill/docs/08_SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md)<br>`SPEC-08-CHANGE-MGMT` | All Team<br>Members,<br>Project Lead | • **Nguyên tắc Quản lý Thay đổi bắt buộc**: Luôn lập Kế hoạch đề xuất (Plan for Review) $\rightarrow$ Chờ chấp thuận bằng lệnh `"OK"` trước khi chỉnh sửa.<br>• Quy trình ghi chép song hành [DEV_PLAN.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_PLAN.md) và [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).<br>• Ma trận đối chiếu chi tiết giữa Môi trường Dev và Pilot. |

---

## 3. BẢNG TRA CỨU NHANH LỆNH VẬN HÀNH (QUICK OPERATIONS CHEAT SHEET)

### 3.1. Dành cho Môi trường Phát triển (DEV - Mac Mini M4)
```bash
# 1. Kích hoạt môi trường ảo Python
cd /Volumes/ExternalSSD/ocr-bill
source venv/bin/activate

# 2. Khởi chạy Web Review Portal cục bộ
python app_review.py
# -> Truy cập: http://localhost:8000

# 3. Đồng bộ danh mục 193 cửa hàng từ CSDL DEV về file JSON và nạp nóng RAM
python sync_outlets.py --force

# 4. Chạy kiểm thử đánh giá 4 ảnh hóa đơn mẫu thực tế ngày 10/09/2026
python test_demo_extract_bill.py
```

### 3.2. Dành cho Quy trình Triển khai Lên Máy chủ Pilot (CI/CD)
```bash
# Đẩy toàn bộ mã nguồn mới nhất lên máy chủ Pilot và restart dịch vụ tự động
python deploy_to_pilot.py

# Chạy kiểm thử tự động trực tiếp trên máy chủ Pilot (14.161.34.37:8080)
python test_pilot_extract_bill.py
```

### 3.3. Dành cho Quản trị Dịch vụ trên Máy chủ Pilot (Ubuntu Server)
```bash
# Kết nối SSH vào máy chủ Pilot
ssh msa@14.161.34.37

# Xem trạng thái dịch vụ OCR
sudo systemctl status ocr-bill

# Khởi động lại dịch vụ
sudo systemctl restart ocr-bill

# Theo dõi nhật ký log ứng dụng theo thời gian thực
tail -f /var/log/ocr-bill.log

# Kiểm tra tài nguyên GPU NVIDIA
nvidia-smi
```

---

## 4. CẤU TRÚC THƯ MỤC TOÀN BỘ DỰ ÁN (PROJECT REPOSITORY LAYOUT)

```
/Volumes/ExternalSSD/ocr-bill/
├── HANDOFF_SYSTEM_GUIDE.md                  ⭐ TÀI LIỆU NÀY (Master Catalog & Sổ tay Bàn giao)
├── CRM_API_INTEGRATION_SPEC.md              📖 Tài liệu Đặc tả Tích hợp CRM (Bàn giao đối tác)
├── CRM_BILL_REVIEW_AND_AUDIT_TECH_SPEC.md   📖 Tài liệu Kỹ thuật Cổng Review & Kiểm toán
├── SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md 📖 Tài liệu Đối chiếu Môi trường & Quản lý Thay đổi
├── DEV_PLAN.md                              📋 Kế hoạch Phát triển Chi tiết (Plan for Review)
├── DEV_HISTORY.md                           📜 Nhật ký Chi tiết Tiến trình & Kết quả Nghiệm thu
│
├── docs/                                    📁 THƯ MỤC 8 CHUYÊN ĐỀ KỸ THUẬT CHI TIẾT
│   ├── 01_SYSTEM_ARCHITECTURE_TECH_STACK.md
│   ├── 02_VLM_MODEL_AND_GPU_OPTIMIZATION.md
│   ├── 03_VIETNAMESE_CURRENCY_AND_EXTRACTION_RULES.md
│   ├── 04_CRM_API_INTEGRATION_SPEC.md
│   ├── 05_WEB_REVIEW_AUDIT_PORTAL.md
│   ├── 06_CRON_SCANNER_AND_SYNC_OPERATIONS.md
│   ├── 07_PILOT_DEPLOYMENT_CI_CD_OPS.md
│   └── 08_SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md
│
├── app_review.py                            🚀 Ứng dụng Web FastAPI Review & Ingestion Server
├── ocr_engine.py                            🧠 Core AI Engine (Qwen2-VL, AutoProcessor, Fuzzy Match)
├── db.py                                    🗄️ Module DAO tương tác CSDL MS-SQL Server
├── master_outlets.json                      🏪 Danh mục 193 cửa hàng TTTM Gigamall
├── deploy_to_pilot.py                       🔄 Script CI/CD tự động hóa lên máy chủ Pilot
├── test_pilot_extract_bill.py               🧪 Script kiểm thử bóc tách trực tiếp trên Pilot
├── test_demo_extract_bill.py                🧪 Script kiểm thử demo bóc tách trên máy Dev
├── cron_ocr_scanner.py                      ⏰ Tiến trình Cron quét hóa đơn ngầm định kỳ
├── sync_outlets.py                          🔄 Script đồng bộ danh mục từ CSDL MS-SQL
├── freetds.conf                             🔒 Cấu hình FreeTDS vượt lỗi TLS với SQL Server 2012
├── db_config.json                           🔒 Cấu hình tài khoản & CSDL (đã bảo mật gitignore)
├── setup_database_dev.sql                   📜 Script T-SQL khởi tạo bảng & đồng bộ CSDL DEV
└── requirements.txt                         📦 Danh mục thư viện Python đã chốt phiên bản
```

---

> [!TIP]
> **Khuyến nghị cho Người tiếp quản mới**:  
> Bắt đầu bằng việc đọc bảng danh mục chuyên đề ở **Mục 2** để nắm tổng quan, sau đó mở tài liệu chuyên đề chi tiết theo từng nhiệm vụ kỹ thuật cụ thể trong thư mục [`docs/`](file:///Volumes/ExternalSSD/ocr-bill/docs).
