# KẾ HOẠCH PHÁT TRIỂN & RÀ SOÁT KỸ THUẬT (DEV PLAN)
## DỰ ÁN: HỆ THỐNG AI OCR HÓA ĐƠN & QUẢN TRỊ DUYỆT KIỂM TOÁN GIGAMALL
**Ngày lập / Cập nhật kế hoạch**: 25/10/2026  
**Nguyên tắc triển khai**: Tối ưu hóa & kế thừa tối đa các module, API và cấu trúc dữ liệu đã có sẵn trong dự án; không viết lại bánh xe; tập trung vào tính an toàn môi trường và trải nghiệm báo cáo của Admin.

---

> [!IMPORTANT]
> ### ⚠️ NGUYÊN TẮC BẮT BUỘC CHO MỌI HÀNH ĐỘNG (CHANGE MANAGEMENT RULE)
> **CHO MỌI HÀNH ĐỘNG (change, dev... vv):**
> 1. **Luôn lập kế hoạch chi tiết (Plan for Review)** trước khi chỉnh sửa bất kỳ dòng mã nguồn hay tệp cấu hình nào.
> 2. **Chỉ thực hiện sau khi có Review và chấp nhận.**
> 3. **Sử dụng câu lệnh `"OK"` để thể hiện sự đồng ý / phê duyệt.**  
> *(Tuyệt đối không tự ý can thiệp mã nguồn, database hay chạy script tác động hệ thống khi chưa có phản hồi "OK" từ Quản lý / User).*

---

## 0. CHECKLIST GIAI ĐOẠN 1 – POC GATE 1 & R&D MAC MINI (TÍCH HỢP TỪ TASK201026.MD)

### A. Chuẩn bị môi trường (Đã hoàn thành)
- [x] Kiểm tra máy: Mac mini M4, 24GB RAM, macOS 26.6.2 – đủ mạnh cho Qwen2-VL-7B 4bit
- [x] Kiểm tra ổ: SanDisk ExternalSSD **ExFAT**, trống 821GB (ExFAT không hỗ trợ symlink)
- [x] `brew install python@3.11` (3.11.17)
- [x] Tạo venv bằng `python3.11 -m venv --copies venv` (bắt buộc `--copies` vì ExFAT)
- [x] Tải model vào `ocr-bill/models/Qwen2-VL-7B-Instruct-4bit` (4.4GB)
- [x] Smoke test bill giả: đọc đúng 6/6 trường, tổng tiền 83.000, khớp outlet HIGHLANDS.
- [x] Xóa file rác `._*` trong venv (nguyên nhân cảnh báo "invalid distribution")
- [x] Tạo `requirements.txt` có pin version (mlx-vlm 0.7.9, mlx 0.32.4, transformers 5.20.2…)
- [x] Tạo `.gitignore`

### B. Dữ liệu đầu vào
- [x] `master_outlets.json` đã có trong thư mục (81 outlet ban đầu)
- [x] Tạo thư mục `TEST_IMAGES/` (101 ảnh thật trong `TEST_IMAGES/`: đẹp, nghiêng, dài, ảnh rác)

### C. Viết script `evaluate_lean.py`
- [x] Nạp model `mlx-community/Qwen2-VL-7B-Instruct-4bit`
- [x] Prompt bóc tách 6 trường: brand, outlet, bill_number, datetime, bill_total, is_valid_bill
- [x] Parse JSON chắc chắn hơn (tìm khối `{...}`, regex fallback, thêm `repetition_penalty=1.1` chống lặp vô tận `bill_number`)
- [x] So khớp mờ tên quán với `master_outlets.json`
- [x] Xuất `results.csv` và sinh `report.html` (chống XSS, zoom lightbox, bộ đếm % lưu localStorage)

### D. Chạy đánh giá & Nghiệm thu Gate 1
- [x] Chạy toàn bộ tập ảnh 101/101 (100% thành công, 0 lỗi, khớp CRM: 88/101, valid bill: 74/101)
- [x] Ghi nhận latency trung bình: 7.69s/bill trên Mac Mini M4.

### E. Demo Duyệt hóa đơn & Vết kiểm toán trên MS-SQL (US 1, US 2, US 3)
- [x] Kết nối MS-SQL Server 2012 (`115.165.166.208:6868`, DB `CLMHQ4GIGA`) qua FreeTDS
- [x] Tạo bảng `OcrBills` và `OcrBillAuditLogs` qua script `create_tables.sql`
- [x] Xây dựng Web App `app_review.py` (FastAPI + HTML5/CSS/JS) chạy tại `http://localhost:8000`
- [x] US 1: Duyệt từng hóa đơn (phóng to, xoay ảnh, phím tắt A/R) và duyệt danh sách bảng
- [x] US 2: Sửa Cửa hàng (autocomplete outlet), sửa Số tiền (cảnh báo lệch AI), sửa Số bill/Ngày giờ
- [x] US 3: Ghi nhận nhật ký kiểm toán vào `OcrBillAuditLogs`, timeline chi tiết từng bill và xuất báo cáo CSV cho Auditor

---

## 1. TỔNG HỢP KẾT QUẢ RÀ SOÁT DỰ ÁN HIỆN CÓ (EXISTING BASELINE)

Qua rà soát toàn bộ tài liệu kỹ thuật ([HANDOFF_SYSTEM_GUIDE.md](file:///Volumes/ExternalSSD/ocr-bill/HANDOFF_SYSTEM_GUIDE.md), [SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md](file:///Volumes/ExternalSSD/ocr-bill/SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md)) và mã nguồn thực tế:

| Thành phần | Hiện trạng trong dự án | Đánh giá & Định hướng xử lý |
| :--- | :--- | :--- |
| **API đồng bộ Outlet/Brand vào JSON** | **ĐÃ CÓ SẴN HOÀN CHỈNH**: Endpoint `POST /api/v1/sync-outlets` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py#L454).<br>• Gọi hàm `db.sync_master_outlets_file()` query bảng `G_Outlet` JOIN `G_Brand`.<br>• Ghi đè file [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) chuẩn UTF-8.<br>• Tự động nạp nóng RAM OCR: `ocr_engine.reload_master_outlets()`.<br>• Có script [sync_from_api.py](file:///Volumes/ExternalSSD/ocr-bill/sync_from_api.py) để máy Dev kéo file từ xa. | ✅ **KHÔNG TẠO API MỚI**.<br>Chỉ cần rà soát, kiểm thử xác nhận API hiện hữu đáp ứng 100% nhiệm vụ cập nhật file JSON. |
| **Cơ chế ghi nhận lịch sử đồng bộ** | **ĐÃ CÓ SẴN**: Hàm `log_sync_event()` và `get_sync_history()` trong [db.py](file:///Volumes/ExternalSSD/ocr-bill/db.py#L717), lưu tối đa 100 lần chạy vào `sync_history.json`. Đã có API `GET /api/v1/sync-logs`. | ✅ **ĐÃ CÓ DỮ LIỆU LỊCH SỬ**.<br>Kế thừa trực tiếp cấu trúc này để đưa lên báo cáo tổng hợp. |
| **Chốt chặn an toàn Cron trên DEV** | • [sync_outlets.py](file:///Volumes/ExternalSSD/ocr-bill/sync_outlets.py): **ĐÃ CÓ** chốt chặn kiểm tra `env_name == "dev"`, tự thoát nếu không có cờ `--force`.<br>• [cron_ocr_scanner.py](file:///Volumes/ExternalSSD/ocr-bill/cron_ocr_scanner.py): **CHƯA CÓ** chốt chặn này. | ⚠️ **CẦN BỔ SUNG**: Đưa chốt chặn an toàn vào `cron_ocr_scanner.py` để tuyệt đối không chạy cron tự động trên môi trường DEV. |
| **Báo cáo tình trạng Cron Job cho Admin** | • **Giao diện hiện tại**: Đã có Tab 4 *"🔄 Quản lý Danh mục (Master)"* hiển thị lịch sử sync danh mục.<br>• **Điểm còn thiếu**: Chưa có màn hình Báo cáo tổng thể tình trạng các tác vụ Cron định kỳ (đặc biệt là tiến trình quét hóa đơn `cron_ocr_scanner.py` chạy 15 phút/lần).<br>• **Ràng buộc**: Báo cáo này **chỉ được phép chạy trên Pilot và Production**. | ⚠️ **CẦN THỰC HIỆN**: Nâng cấp giao diện Web Admin để hiển thị Báo cáo tình trạng thực hiện Cron Job (kết hợp Cron Quét Bill & Cron Sync Danh mục), có chốt chặn chỉ chạy trên Pilot và Prod, khóa trên Dev. |

---

## 2. KẾ HOẠCH TRIỂN KHAI CHI TIẾT 3 TASK

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SƠ ĐỒ TRIỂN KHAI PHÙ HỢP HIỆN TRẠNG                       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [TASK 1: BẢO VỆ AN TOÀN CRON TRÊN DEV]                                                │
│  ├── sync_outlets.py: Đã có chốt chặn ──> Giữ nguyên & kiểm tra lại                    │
│  └── cron_ocr_scanner.py: Bổ sung chốt chặn: if env == 'dev' and not force -> exit(0) │
│                                                                                        │
│  [TASK 2: RÀ SOÁT API CẬP NHẬT OUTLET/BRAND HIỆN CÓ]                                  │
│  ├── Kế thừa nguyên vẹn: POST /api/v1/sync-outlets                                     │
│  ├── Kế thừa nguyên vẹn: GET /api/v1/sync-logs & GET /api/outlets                      │
│  └── Kiểm chứng xác nhận hoạt động 100% đúng chuẩn                                     │
│                                                                                        │
│  [TASK 3: ĐƯA LỊCH SỬ CRON LÊN BÁO CÁO GIAO DIỆN ADMIN (PILOT/PROD ONLY)]              │
│  ├── Tận dụng dữ liệu lịch sử đã có (sync_history.json & ghi thêm cron_scanner)        │
│  ├── Tích hợp vào Web UI: Tab Giám sát & Báo cáo Tác vụ Cron cho Admin                 │
│  └── Ràng buộc môi trường: Pilot & Prod hiển thị đầy đủ, DEV bị khóa an toàn (HTTP 403)│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 📌 TASK 1: RÀ SOÁT CRON ĐẢM BẢO Ở CHẾ ĐỘ DEV, CRON SẼ KHÔNG THỰC HIỆN

#### 1.1. Mục tiêu kỹ thuật
- Đảm bảo khi cấu hình hệ thống đang ở môi trường `dev` (xác định qua `_active_env == "dev"` trong `db_config.json` hoặc biến môi trường `APP_ENV=dev`), tiến trình Cron chạy ngầm sẽ **tự động bỏ qua / dừng an toàn**, không kết nối truy vấn hoặc quét dữ liệu bill.

#### 1.2. Kế hoạch thực hiện cụ thể
1. **Rà soát `sync_outlets.py`**:
   - Hiện đã có chốt chặn tại dòng 28-36:
     ```python
     if env_name == "dev" and not args.force:
         print("⚠️ CHỐT CHẶN AN TOÀN: MÔI TRƯỜNG DEV KHÔNG ĐƯỢC CHẠY CRON!")
         sys.exit(0)
     ```
   - Xác nhận cơ chế này hoạt động chính xác.
2. **Bổ sung chốt chặn vào `cron_ocr_scanner.py`**:
   - Bổ sung đoạn kiểm tra môi trường tương tự ngay đầu hàm `main()` của [cron_ocr_scanner.py](file:///Volumes/ExternalSSD/ocr-bill/cron_ocr_scanner.py):
     - Đọc cấu hình `cfg = db.load_db_config()`.
     - Lấy `env_name = cfg.get("_active_env", "dev").lower()`.
     - Nếu `env_name == "dev"` và người dùng không truyền cờ `--force`:
       - In thông báo cảnh báo an toàn rõ ràng:  
         `⚠️ CHỐT CHẶN AN TOÀN: Môi trường DEV bị vô hiệu hóa Cron tự động quét hóa đơn!`  
         `👉 Để chạy thử trên Dev, vui lòng thêm cờ: --force`
       - Thoát an toàn bằng `sys.exit(0)`.
3. **Kiểm thử xác nhận**:
   - Chạy thử lệnh `python cron_ocr_scanner.py` trên máy Dev (Mac) $\rightarrow$ Xác nhận script lập tức in cảnh báo và thoát với exit code 0, không chạy vòng lặp hay quét bill.

---

### 📌 TASK 2: RÀ SOÁT & ĐẢM BẢO HOẠT ĐỘNG CỦA API CẬP NHẬT OUTLET & BRAND VÀO FILE JSON

#### 2.1. Mục tiêu kỹ thuật
- Tận dụng triệt để API đã được xây dựng sẵn trong dự án thay vì tạo API mới thừa thãi.
- Đảm bảo API này thực hiện đầy đủ và chính xác nhiệm vụ: Truy vấn từ CSDL MS-SQL (`G_Outlet` + `G_Brand`) $\rightarrow$ Ghi đè [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) chuẩn UTF-8 $\rightarrow$ Làm mới cache bộ nhớ của `ocr_engine`.

#### 2.2. Chi tiết API hiện có đã được rà soát
* **Endpoint API**: `POST /api/v1/sync-outlets` (trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py#L454-L478))
  * Tham số: `actor` (mặc định "CRM Admin"), `source` (mặc định "WEB_ADMIN").
  * Logic xử lý: Gọi `db.sync_master_outlets_file()`.
  * Câu truy vấn SQL: `SELECT o.ID, o.Number, o.OutletName, b.ID, b.Number, b.BrandName, o.Address FROM G_Outlet o INNER JOIN G_Brand b ON o.BrandID = b.ID WHERE o.IsActive = 1 AND o.IsUsed = 1 ORDER BY o.OutletName`.
  * Kết quả: Ghi trực tiếp ra file [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) và gọi `ocr_engine.reload_master_outlets()`.
  * Ghi nhật ký: Tự động lưu bản ghi vào `sync_history.json`.
* **API tải file JSON**: `GET /api/v1/download-master-outlets` và `GET /api/outlets`.
* **Tiện ích Client Dev**: [sync_from_api.py](file:///Volumes/ExternalSSD/ocr-bill/sync_from_api.py) đã cấu hình sẵn gọi về endpoint này trên máy chủ Pilot/Prod.

#### 2.3. Kế hoạch thực hiện cụ thể
1. **Kiểm thử end-to-end API hiện có**:
   - Gọi thử nghiệm endpoint `POST /api/v1/sync-outlets` qua Swagger UI (`/docs`) hoặc `curl`.
   - Xác nhận file [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) được cập nhật chuẩn xác tiếng Việt có dấu.
   - Xác nhận nhật ký trong `sync_history.json` được ghi nhận.
2. **Chuẩn hóa tài liệu kỹ thuật**:
   - Xác nhận endpoint này trong tài liệu hướng dẫn bàn giao, đảm bảo đội ngũ vận hành và CRM nắm rõ mà không bị phân tâm bởi các API dư thừa.

---

### 📌 TASK 3: ĐƯA LỊCH SỬ CRON JOB LÊN THÀNH BÁO CÁO TRÊN GIAO DIỆN WEB CHO ADMIN (CHỈ ÁP DỤNG PILOT & PROD)

#### 3.1. Mục tiêu kỹ thuật
- Tận dụng các dữ liệu lịch sử đã có sẵn (hoặc nhật ký chạy của cron), **đưa lên thành một Báo cáo trực quan trên Giao diện Web** dành cho Admin.
- Giúp Quản trị viên nắm bắt nhanh:
  - Tình trạng hoạt động của tác vụ Cron Quét Hóa Đơn (`cron_ocr_scanner.py` - 15 phút/lần).
  - Tình trạng hoạt động của tác vụ Cron Đồng Bộ Danh Mục (`sync_outlets.py` - 02:00 sáng hàng ngày).
- **Ràng buộc an toàn cốt lõi**: Báo cáo này **CHỈ KHẢ DỤNG TRÊN PILOT VÀ PRODUCTION**. Trên môi trường `DEV`, báo cáo bị khóa hoàn toàn.

#### 3.2. Kế hoạch thực hiện cụ thể
1. **Ghi nhận lịch sử cho `cron_ocr_scanner.py` (tương tự như `sync_outlets.py`)**:
   - Trong `db.py`, bổ sung hàm nhỏ `log_cron_scanner_event(event)` lưu vào tệp `cron_scanner_history.json` (tối đa 100 lần chạy gần nhất: thời điểm, số bill đã quét, số bill thành công, số bill lỗi, thời lượng).
   - Mỗi lần `cron_ocr_scanner.py` hoàn thành 1 đợt quét sẽ gọi hàm này để lưu vết.
2. **Xây dựng API Báo cáo Tổng hợp có Guard môi trường**:
   - Viết endpoint `GET /api/v1/admin/cron-report` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py):
     - **Chốt chặn môi trường**: Đọc `current_environment`.
     - Nếu là `dev`: Lập tức trả về mã lỗi `HTTP 403 Forbidden` kèm thông báo:  
       `"Báo cáo Cron Job chỉ khả dụng trên môi trường Pilot và Production. Môi trường DEV không chạy Cron tự động."`
     - Nếu là `pilot` hoặc `prod`: Đọc và tổng hợp từ `cron_scanner_history.json` và `sync_history.json`, trả về:
       - Trạng thái tổng quan nhịp tim (Health Status).
       - Lần chạy quét bill gần nhất + Lần đồng bộ danh mục gần nhất.
       - Thống kê tỷ lệ thành công trong 24 giờ.
       - Danh sách lịch sử các đợt chạy gần nhất.
3. **Nâng cấp Giao diện Web Admin Portal ([app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py))**:
   - Tận dụng Tab 4 hiện tại (hoặc nâng cấp thành Tab *"⏰ Giám sát & Báo cáo Cron"*):
     - **Khi mở trên DEV**: Hiển thị Guard Screen / Banner màu vàng nổi bật:  
       `💡 Chế độ Môi trường: DEV. Các tác vụ Cron Job tự động bị vô hiệu hóa để bảo vệ an toàn hệ thống. Báo cáo Cron chỉ khả dụng trên máy chủ Pilot và Production.`
     - **Khi mở trên PILOT / PROD**: Hiển thị Báo cáo Giám sát Cron hoàn chỉnh:
       - Thẻ tóm tắt KPI: Trạng thái quét bill 15p, Trạng thái sync 02:00 sáng, Tỷ lệ OCR thành công.
       - Bảng lịch sử các đợt chạy gần nhất kèm nhãn `SUCCESS` (Xanh) hoặc `FAILED` (Đỏ).
       - Nút *"Tải lại báo cáo"*.

---

## 3. CHECKLIST CÁC BƯỚC THỰC HIỆN (ACTION PLAN)

- [x] **Bước 1 (Task 1)**: Thêm chốt chặn an toàn môi trường `dev` vào [cron_ocr_scanner.py](file:///Volumes/ExternalSSD/ocr-bill/cron_ocr_scanner.py) (kiểm tra `_active_env == "dev"` và `not args.force` $\rightarrow$ exit 0).
- [x] **Bước 2 (Task 1)**: Rà soát lại [sync_outlets.py](file:///Volumes/ExternalSSD/ocr-bill/sync_outlets.py) để đảm bảo đồng nhất cơ chế chặn trên Dev.
- [x] **Bước 3 (Task 2)**: Kiểm thử rà soát API hiện có `POST /api/v1/sync-outlets` và `GET /api/v1/sync-logs`, xác nhận cập nhật file `master_outlets.json` chính xác.
- [x] **Bước 4 (Task 3)**: Bổ sung hàm lưu vết đợt quét `cron_scanner_history.json` cho [cron_ocr_scanner.py](file:///Volumes/ExternalSSD/ocr-bill/cron_ocr_scanner.py).
- [x] **Bước 5 (Task 3)**: Viết API `GET /api/v1/admin/cron-report` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py) có chốt chặn môi trường nghiêm ngặt (chặn HTTP 403 nếu `dev`).
- [x] **Bước 6 (Task 3)**: Cập nhật Giao diện Web Portal trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py) hiển thị Báo cáo Cron cho Admin (có banner khóa an toàn khi ở chế độ `dev`).
- [x] **Bước 7**: Kiểm thử xác nhận toàn diện cả 3 Task trên máy Dev Mac (Đã chạy smoke test & kiểm thử unit test thành công 100%).

---

> [!NOTE]
> Toàn bộ 3 nhiệm vụ Đợt 1 đã được lập trình, kiểm thử nghiệm thu và ghi nhận trạng thái hoàn thành vào hệ thống theo đúng quy trình.

---

## 4. KẾ HOẠCH ĐỢT 2: ĐỒNG BỘ CSDL VÀ TRIỂN KHAI DEBUG CODE ĐÁNH GIÁ OCR TRÊN GIAO DIỆN

### 📌 NHIỆM VỤ 1: THỰC THI API ĐỒNG BỘ VÀ XUẤT BÁO CÁO ĐỐI SOÁT (THỰC TẾ vs CSDL)
* **Bối cảnh & Phát hiện kỹ thuật**:
  - Quản trị viên vừa INSERT thêm dữ liệu mới vào CSDL DEV (`OCRInvoice` trên `45.119.87.247:1433`):
    - Bảng `G_Outlet`: Hiện có **194 bản ghi** (tăng từ 82 ban đầu).
    - Bảng `G_Brand`: Hiện có **233 bản ghi**.
  - **Điểm lưu ý kỹ thuật**: Các dòng mới INSERT có `IsActive = NULL` (thay vì 1) và `IsUsed = True`. Để không bỏ sót dữ liệu mới, câu truy vấn SQL cần sử dụng điều kiện:  
    `WHERE ISNULL(o.IsActive, 1) = 1 AND ISNULL(o.IsUsed, 1) = 1` $\rightarrow$ Trích xuất đầy đủ **193 cửa hàng hợp lệ** (so với 81 cửa hàng cũ).
* **Kế hoạch thực hiện**:
  1. Cập nhật điều kiện lọc `ISNULL` trong hàm `fetch_master_outlets_from_db()` ([db.py](file:///Volumes/ExternalSSD/ocr-bill/db.py#L709)).
  2. Gọi API `POST /api/v1/sync-outlets?actor=DEV_ADMIN&source=DEV_UPDATE` để đồng bộ dữ liệu vào [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json) và nạp nóng vào RAM OCR.
  3. **Lập Báo Cáo Đối Soát Chi Tiết (Comparative Report)**:
     - So sánh số lượng: CSDL (194 rows) $\leftrightarrow$ JSON trước sync (81 rows) $\leftrightarrow$ JSON sau sync (193 rows).
     - Liệt kê danh sách chi tiết các cửa hàng mới được thêm vào (Tên quán, Mã quán, Thương hiệu, Vị trí/Địa chỉ).
     - Phân tích rõ 1 bản ghi trong DB không vào file JSON (do `IsUsed = False` hoặc lỗi logic dữ liệu).

---

### 📌 NHIỆM VỤ 2: PHƯƠNG PHÁP ĐÁNH GIÁ & TRIỂN KHAI DEBUG CODE CHO USER TEST TRÊN GIAO DIỆN

#### 2.1. Phương pháp Đánh giá Hiệu quả Thuật toán OCR (Evaluation Methodology)
Người dùng sẽ trực tiếp upload ảnh hóa đơn qua Web Portal (`http://localhost:8000`) và thực hiện đánh giá theo 4 tiêu chí chuẩn mực:
1. **Độ trễ xử lý (Latency)**:
   - Thời gian xử lý từ lúc nhấn upload đến khi có kết quả.
   - Chuẩn kỳ vọng trên Mac Mini M4 (mô hình Qwen2-VL-7B-Instruct-4bit qua Apple Silicon Metal): $\approx 7 - 9$ giây/hóa đơn.
2. **Độ chính xác bóc tách 6 trường cốt lõi (Field Extraction Accuracy)**:
   - **Tổng tiền (`bill_total`)**: Số tiền thanh toán cuối cùng sau chiết khấu/voucher. Không nhầm với tổng tiền trước giảm giá hay tiền khách đưa.
   - **Tên cửa hàng (`raw_outlet`) & Thương hiệu (`raw_brand`)**: Đọc đúng tên in trên đầu bill.
   - **Số hóa đơn (`bill_number`)**: Áp dụng quy tắc 6 số cuối (hoặc chuỗi ngày giờ nếu không có số bill).
   - **Ngày giờ (`bill_datetime`)**: Chuẩn hóa định dạng `YYYY-MM-DD HH:mm:ss`.
   - **Tính hợp lệ (`is_valid_bill`)**: Nhận diện đúng ảnh là hóa đơn mua hàng (loại bỏ ảnh rác, phong cảnh, đồ vật).
3. **Độ chính xác so khớp mờ (Fuzzy Matching Efficiency)**:
   - Điểm số `match_score` $\ge 0.60$ để gán tự động vào cửa hàng trong danh mục Master Outlets.
   - Khả năng phân biệt giữa các thương hiệu gần giống nhau.
4. **Độ tin cậy của cấu trúc JSON**: AI sinh JSON sạch, không bị lặp vô tận token (repetition penalty).

#### 2.2. Triển khai Debug Code & Công cụ Giám sát trên Giao diện (Diagnostics Tooling)
Để hỗ trợ người dùng đánh giá sâu từng ca bóc tách khi thao tác trên Web UI:
1. **Nâng cấp `ocr_engine.py`**:
   - Mở rộng hàm `resolve_outlet()`: Không chỉ trả về kết quả tốt nhất mà còn trích xuất **Top 3 ứng viên cửa hàng có điểm số cao nhất (`top_candidates`)** kèm điểm tương đồng % (ví dụ: Highlands Coffee: 95%, The Coffee House: 42%, Phuc Long: 30%).
   - Bổ sung trường `top_candidates` vào kết quả trả về của hàm `process_bill_image()`.
2. **Nâng cấp Giao diện Web Inspector ([app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py))**:
   - Thêm nút/khối collapsible: **"🔬 Hộp Công Cụ Debug & Đánh Giá Thuật Toán AI"**:
     - **Mục 1 - Phân tích So khớp mờ**: Hiển thị bảng Top 3 ứng viên cửa hàng gần nhất kèm % điểm số (giúp người dùng thấy rõ tại sao thuật toán chọn quán này).
     - **Mục 2 - Dữ liệu JSON gốc (Raw VLM Output)**: Hiển thị nguyên văn đoạn JSON mà mô hình Qwen2-VL sinh ra trước khi qua bộ chuẩn hóa.
     - **Mục 3 - Đo đạc độ trễ (Latency Breakdown)**: Hiển thị thời gian AI suy luận và thời gian xử lý ảnh.
3. **Khởi chạy Web Service**:
   - Khởi chạy tiến trình `app_review.py` tại `http://localhost:8000` để người dùng mở trình duyệt, bấm "📤 Tải lên hóa đơn" và trực tiếp thử nghiệm đánh giá.

---

### BẢNG CHECKLIST THỰC HIỆN ĐỢT 2
- [x] **Bước 2.1 (Task 1)**: Cập nhật điều kiện SQL `ISNULL(IsActive, 1) = 1` trong [db.py](file:///Volumes/ExternalSSD/ocr-bill/db.py) để bao hàm các dòng mới INSERT.
- [x] **Bước 2.2 (Task 1)**: Kích hoạt API `POST /api/v1/sync-outlets` đồng bộ CSDL DEV vào `master_outlets.json`.
- [x] **Bước 2.3 (Task 1)**: Xuất Báo cáo đối soát so sánh chi tiết: Dữ liệu CSDL $\leftrightarrow$ File JSON (số lượng, danh sách outlet mới, phân tích bản ghi không khớp).
- [x] **Bước 2.4 (Task 2)**: Nâng cấp [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py) bổ sung `top_candidates` so khớp mờ.
- [x] **Bước 2.5 (Task 2)**: Tích hợp Khối Debug & Đánh giá Thuật toán vào Giao diện Web Inspector trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py).
- [x] **Bước 2.6 (Task 2)**: Khởi chạy Web Server tại `http://localhost:8000` và hướng dẫn User các bước tự thao tác kiểm thử đánh giá.
- [x] **Bước 2.7**: Cập nhật toàn bộ kết quả nghiệm thu và báo cáo vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).

---

## 5. KẾ HOẠCH ĐỢT 3: DEMO & ĐÁNH GIÁ API `POST /api/v1/extract-bill` VỚI TẬP ẢNH THỰC TẾ

### 📌 MỤC TIÊU KỸ THUẬT
* Kiểm chứng trực tiếp endpoint **`POST /api/v1/extract-bill`** (theo chuẩn [CRM_API_INTEGRATION_SPEC.md](file:///Volumes/ExternalSSD/ocr-bill/CRM_API_INTEGRATION_SPEC.md#L156)).
* Nguồn dữ liệu kiểm thử: Thư mục ảnh thực tế `/Volumes/ExternalSSD/temp/100926/OCR/`.
* Đánh giá toàn diện 4 khía cạnh:
  1. **Tính tương thích CRM Spec**: Cấu trúc payload response (`success`, `bill_id`, `data.bill_total`, `data.brand_name`, `data.outlet_name`, `data.outlet_number`, `data.bill_number`, `data.bill_datetime`, `data.match_score`, `data.confidence`, `raw_output`).
  2. **Độ trễ xử lý (Latency)**: Thời gian xử lý bóc tách qua mô hình Qwen2-VL-7B-Instruct 4-bit chạy trên GPU Metal.
  3. **Chất lượng bóc tách AI**: Bóc tách tổng tiền thanh toán, nhận diện thương hiệu, đọc số hóa đơn, ngày giờ giao dịch.
  4. **Hiệu quả so khớp danh mục mới**: Đối soát kết quả so khớp với 193 cửa hàng vừa đồng bộ từ CSDL DEV.

---

### 📌 KẾ HOẠCH TRIỂN KHAI CHI TIẾT
1. **Lựa chọn mẫu ảnh thực tế (Sampling Selection)**:
   * Chọn 3 - 5 ảnh hóa đơn đại diện từ `/Volumes/ExternalSSD/temp/100926/OCR/`:
     - Ảnh 1: `10852_100926222127.png`
     - Ảnh 2: `909_100926200240.png`
     - Ảnh 3: `13747_100926104559.png`
     - Ảnh 4: `44973_100926225318.png`
2. **Kịch bản thực thi API**:
   * Gửi request `POST /api/v1/extract-bill` dạng `multipart/form-data`:
     - `file`: Stream nhị phân tệp ảnh hóa đơn.
     - `mem_id`: Giả lập mã thành viên CRM (ví dụ: `MEM_TEST_99`).
     - `image_number`: Giữ nguyên mã tên file ảnh (ví dụ: `10852_100926222127`).
     - `duplicate_action`: `warn`.
3. **Đo lường & Lập Bảng Đánh Giá Kết Quả**:
   * Thu thập chi tiết từng lần gọi: `HTTP Status Code`, `Latency (s)`, `Bill ID`, `Tên quán nhận diện`, `Thương hiệu`, `Tổng tiền`, `Số bill`, `Ngày giờ`, `Match Score %`, `Top 1 & Top 2 Candidates`.
   * So sánh kết quả AI bóc tách với ảnh gốc để đánh giá tỷ lệ chính xác.
4. **Kiểm tra đồng bộ trên Web Review Portal**:
   * Xác nhận bill đã tự động xuất hiện trên giao diện Web Admin `http://localhost:8000` và hiển thị chi tiết trong Khối Debug mới.

---

### BẢNG CHECKLIST THỰC HIỆN ĐỢT 3
- [x] **Bước 3.1**: Chọn 3-5 ảnh mẫu thực tế từ `/Volumes/ExternalSSD/temp/100926/OCR/` và kiểm tra tính toàn vẹn.
- [x] **Bước 3.2**: Viết script thực thi demo `test_demo_extract_bill.py` gọi API `POST /api/v1/extract-bill`.
- [x] **Bước 3.3**: Chạy script demo, đo đạc độ trễ và tổng hợp dữ liệu bóc tách.
- [x] **Bước 3.4**: Lập Bảng Đánh Giá Chất Lượng Bóc Tách & So Khớp Mờ gửi Quản lý.
- [x] **Bước 3.5**: Cập nhật toàn bộ kết quả vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).

---

## 6. KẾ HOẠCH ĐỢT 4: CHUẨN HÓA SỐ TIỀN HẬU XỬ LÝ & ĐỒNG BỘ CƠ CHẾ GỌI API (BASE64 vs MULTIPART)

### 📌 MỤC TIÊU KỸ THUẬT
1. **Chuẩn hóa Hậu Xử Lý Số Tiền (`bill_total`) trong `ocr_engine.py`**:
   - Khắc phục lỗi VLM hiểu nhầm dấu chấm phân tách hàng nghìn kiểu Việt Nam (`75.000` $\rightarrow$ `75.0` $\rightarrow$ `75 đ`).
   - Xây dựng luật thông minh: Nếu hóa đơn có giá trị bóc tách $< 1.000$ (và chuỗi gốc thể hiện đơn vị ngàn/dấu chấm hoặc là hóa đơn bán lẻ thông thường $\ge 1.000$ VNĐ), tự động nhân hệ số $1.000$ để chuẩn hóa về đúng số tiền khách thanh toán.
2. **Làm rõ & Hỗ trợ kép phương thức truyền ảnh cho API `/api/v1/extract-bill`**:
   - Hiện trạng: `/api/v1/extract-bill` chỉ hỗ trợ `multipart/form-data` qua trường `file`.
   - Trong khi đó, `/api/v1/bills/upload-base64` hỗ trợ Base64 JSON thuần.
   - Kế hoạch: Nâng cấp `/api/v1/extract-bill` hỗ trợ linh hoạt cả 2 hình thức (nhận `multipart/form-data` HOẶC nhận payload `application/json` chứa Base64) để đội CRM có thể gọi trực tiếp theo bất kỳ phương thức nào mà không sợ lỗi rỗng dữ liệu.

---

### BẢNG CHECKLIST DỰ KIẾN (ĐỢT 4)
- [ ] **Bước 4.1**: Cập nhật hàm `to_int_amount()` và luật hậu xử lý số tiền trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py).
- [ ] **Bước 4.2**: Bổ sung hỗ trợ Base64 JSON vào endpoint `/api/v1/extract-bill` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py).
- [ ] **Bước 4.3**: Kiểm thử lại toàn diện với cả 2 hình thức: Multipart binary stream và Base64 JSON payload.
- [ ] **Bước 4.4**: Cập nhật kết quả vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).

---

## 7. KẾ HOẠCH ĐỢT 5: TRIỂN KHAI LÊN PILOT (14.161.34.37), KHỞI ĐỘNG DỊCH VỤ & THỰC NGHIỆM TẬP ẢNH THỰC TẾ

### 📌 MỤC TIÊU KỸ THUẬT
* Đồng bộ mã nguồn mới nhất từ máy Dev lên máy chủ Pilot (`14.161.34.37`) bao gồm:
  - [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py): Khối Debug & Giám sát trên Web UI, bảo vệ môi trường, API `ocr-debug`.
  - [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py): Cung cấp `top_candidates` và `resolve_outlet_debug`.
  - [db.py](file:///Volumes/ExternalSSD/ocr-bill/db.py): Lọc đầy đủ `ISNULL(IsActive, 1) = 1` và lưu vết Cron.
  - [master_outlets.json](file:///Volumes/ExternalSSD/ocr-bill/master_outlets.json): Danh mục 193 cửa hàng vừa đồng bộ từ CSDL DEV.
  - [ExtractApiSampleNet.cs](file:///Volumes/ExternalSSD/ocr-bill/ExtractApiSampleNet.cs): File mẫu C# .NET hoàn chỉnh cho đội CRM.
* Khởi động lại dịch vụ hệ thống `ocr-bill.service` trên Pilot và kiểm tra trạng thái `ACTIVE`.
* Gửi trực tiếp 4 ảnh hóa đơn mẫu thực tế (`temp/100926/OCR`) tới `http://14.161.34.37:8080/api/v1/extract-bill` để đối soát thực tế hoạt động trên GPU NVIDIA RTX 3060.

---

### BẢNG CHECKLIST THỰC HIỆN ĐỢT 5
- [x] **Bước 5.1**: Tạo file mã nguồn mẫu C# .NET: [ExtractApiSampleNet.cs](file:///Volumes/ExternalSSD/ocr-bill/ExtractApiSampleNet.cs).
- [x] **Bước 5.2**: Chạy quy trình CI/CD qua [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py) để đẩy mã nguồn lên `/opt/ocr-bill/` trên Pilot (`14.161.34.37`).
- [x] **Bước 5.3**: Khởi động lại dịch vụ `sudo systemctl restart ocr-bill` và kiểm tra `systemctl is-active ocr-bill`.
- [x] **Bước 5.4**: Kiểm tra sức khỏe Smoke Test qua `http://14.161.34.37:8080/api/stats` và `http://14.161.34.37:8080/api/health`.
- [x] **Bước 5.5**: Chạy script test bóc tách trực tiếp gửi tới `http://14.161.34.37:8080/api/v1/extract-bill` với 4 ảnh mẫu thực tế và đối chiếu kết quả bóc tách.
- [x] **Bước 5.6**: Cập nhật báo cáo nghiệm thu vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).

---

## 8. KẾ HOẠCH ĐỢT 6: NÂNG CẤP MÔ HÌNH 7B LÊN PILOT (RTX 3060 12GB) & CHUẨN HÓA HẬU XỬ LÝ SỐ TIỀN

### 📌 MỤC TIÊU KỸ THUẬT
* Nâng cấp mô hình trên máy chủ Pilot từ `Qwen2-VL-2B-Instruct` (2 Tỷ tham số) lên **`Qwen2-VL-7B-Instruct` (7 Tỷ tham số)** lượng hóa 4-bit qua `bitsandbytes` (NF4).
* Tận dụng tối đa tài nguyên phần cứng Pilot: CPU i7-13700KF (24 vCPUs), GPU RTX 3060 (12GB VRAM), và 924GB đĩa trống trên `/mnt/data`.
* Cập nhật quy tắc hậu xử lý số tiền trong `to_int_amount()`: Nếu `0 < bill_total < 1000` đối với hóa đơn bán lẻ TTTM, tự động nhân hệ số $1.000$ để chuẩn hóa về đúng số tiền thực tế.
* Sau khi nạp trọng số 7B vào cache hoàn tất, khởi động lại `ocr-bill.service` và chạy lại bộ 4 ảnh mẫu thực tế kiểm chứng kết quả bóc tách.

---

### BẢNG CHECKLIST THỰC HIỆN ĐỢT 6
- [x] **Bước 6.1**: Cập nhật hàm `to_int_amount()` trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py) nhân hệ số 1.000 cho các hóa đơn bị hiểu nhầm dấu chấm phân tách ngàn.
- [x] **Bước 6.2**: Cấu hình mô hình mặc định trên CUDA là `Qwen/Qwen2-VL-7B-Instruct` kèm `AutoProcessor` giới hạn pixel [512, 2048].
- [x] **Bước 6.3**: Đẩy mã nguồn mới lên Pilot qua [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py).
- [x] **Bước 6.4**: Chạy tác vụ nạp và tải đầy đủ trọng số 5 shards của mô hình 7B vào `/mnt/data/ocr-bill/cache/huggingface/`.
- [x] **Bước 6.5**: Khởi động lại dịch vụ `ocr-bill.service` trên Pilot.
- [x] **Bước 6.6**: Chạy lại thực nghiệm `test_pilot_extract_bill.py` trên 4 hóa đơn thực tế và đối chiếu tỷ lệ bóc tách (đạt tốc độ ~3.5s/bill, độ khớp 96-100%).
- [x] **Bước 6.7**: Cập nhật kết quả nghiệm thu chi tiết vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md).

---

## 9. KẾ HOẠCH ĐỢT 7: HOÀN TẤT CHUẨN HÓA ĐỊNH DẠNG SỐ TIỀN VIỆT NAM (VND FORMAT) & HỖ TRỢ KÉP API EXTRACT-BILL

### 📌 1. BỐI CẢNH & PHÂN TÍCH KỸ THUẬT (PROBLEM STATEMENT)
1. **Đặc thù Định dạng Số tiền Hóa đơn tại Việt Nam (VND Format)**:
   - Các hóa đơn bán lẻ, F&B tại Gigamall in số tiền với dấu chấm `.` hoặc phẩy `,` phân cách hàng nghìn (ví dụ: `204.000`, `75.000`, `200.000`, `124.416`).
   - Khác với chuẩn phương Tây (dấu `.` là số thập phân), ở Việt Nam không có tiền xu hay số thập phân trong hóa đơn bán lẻ.
2. **Nguyên nhân cốt lõi gây lỗi `bill_total` (0 đ hoặc 204 đ)**:
   - Trong `EXTRACTION_PROMPT` cũ chỉ quy định chung chung: *"Chỉ ghi số nguyên, không dấu chấm phẩy, không đơn vị. Trường nào không đọc được thì để 0"*.
   - Mô hình VLM gặp số `204.000` bị xung đột nhận thức:
     * Trên Mac: Diễn giải dấu `.` là thập phân, sinh ra `204.0` (sau đó bị hàm `to_int_amount` cũ ép kiểu thành `204`).
     * Trên Pilot: Mô hình không tìm thấy số nguyên không dấu nên rơi vào nhánh dự phòng prompt và sinh ra `"bill_total": 0`.
3. **Nhiệm vụ còn tồn đọng từ Đợt 4**:
   - Endpoint `POST /api/v1/extract-bill` cần hỗ trợ linh hoạt cả 2 định dạng truyền ảnh: `multipart/form-data` (upload file nhị phân) và `application/json` (Base64) để tương thích 100% với tài liệu tích hợp CRM ([CRM_API_INTEGRATION_SPEC.md](file:///Volumes/ExternalSSD/ocr-bill/CRM_API_INTEGRATION_SPEC.md)).

---

### 📌 2. GIẢI PHÁP 3 LỚP BẢO VỆ TOÀN DIỆN (3-LAYER REMEDIATION)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
3 LỚP XỬ LÝ ĐỊNH DẠNG TIỀN TỆ VIỆT NAM (VND) TRONG HỆ THỐNG AI OCR
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [LỚP 1: NÂNG CẤP PROMPT AI CHUYÊN SÂU]                                                │
│ └── Hướng dẫn AI hiểu rõ quy tắc tiền VND:                                            │
│     • Dấu '.' hoặc ',' là phân tách hàng nghìn (204.000 -> 204000; 75.000 -> 75000)   │
│     • Bắt buộc ghi đủ toàn bộ các chữ số 0 hàng nghìn, không rút gọn hay ghi thập phân │
│                                                                                        │
│ [LỚP 2: HẬU XỬ LÝ THÔNG MINH (POST-PROCESSING)]                                       │
│ ├── Parser Regex: Bóc tách cả số dạng chuỗi có dấu chấm/phẩy (ví dụ: "204.000 đ")      │
│ └── Thuật toán quy đổi: Nếu num < 1000 đối với bill Gigamall -> tự động nhân 1000      │
│                                                                                        │
│ [LỚP 3: HỖ TRỢ KÉP GỌI API /api/v1/extract-bill]                                       │
│ ├── Cách 1: multipart/form-data (trường 'file')                                        │
│ └── Cách 2: application/json (chuỗi Base64 'image' hoặc 'bill_image')                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.1. Lớp 1: Cập nhật `EXTRACTION_PROMPT` trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py)
Bổ sung đoạn chỉ dẫn định dạng tiền tệ Việt Nam rõ ràng:
```text
- ĐỊNH DẠNG SỐ TIỀN (VIỆT NAM ĐỒNG - VND):
  * Hóa đơn tại Việt Nam dùng dấu chấm '.' hoặc phẩy ',' phân tách hàng nghìn (ví dụ: '75.000' hay '75,000' là 75 nghìn đồng -> phải ghi số nguyên 75000; '204.000' -> ghi 204000; '1.500.000' -> ghi 1500000).
  * Luôn ghi đầy đủ tất cả các chữ số nguyên, tuyệt đối không bỏ các số 0 hàng nghìn và không ghi số thập phân (không được ghi 75 hay 204).
  * Không ghi đơn vị tiền tệ (đ, VND), không ghi dấu chấm phẩy trong số.
```

#### 2.2. Lớp 2: Cải tiến hàm `to_int_amount()` và Tiền xử lý ảnh trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py)
- Chuẩn hóa hàm `to_int_amount(value, raw_str)`:
  - Nếu `value` là float/int (ví dụ: `204.0` hoặc `204`): Nếu `0 < num < 1000`, tự động nhân `1000` $\rightarrow$ `204000`.
  - Nếu `value` là chuỗi (ví dụ: `"204.000"`, `"75,000 đ"`): Nhận diện dấu phân tách ngàn để bóc tách chính xác toàn bộ chữ số nguyên.
- Tinh chỉnh `AutoProcessor` trên NVIDIA GPU: Bỏ hạn chế `min_pixels` cứng, đảm bảo độ phân giải thích ứng để mô hình đọc rõ từng chi tiết số tiền nhỏ ở chân hóa đơn.

#### 2.3. Lớp 3: Nâng cấp API `POST /api/v1/extract-bill` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py)
- Hỗ trợ kép: Nhận `multipart/form-data` HOẶC nhận payload `application/json` (chứa chuỗi base64).
- Tương thích 100% với tài liệu đặc tả [CRM_API_INTEGRATION_SPEC.md](file:///Volumes/ExternalSSD/ocr-bill/CRM_API_INTEGRATION_SPEC.md).

---

### 📌 3. BẢNG CHECKLIST KẾ HOẠCH TRIỂN KHAI (ACTION PLAN)

- [x] **Bước 7.1**: Cập nhật `EXTRACTION_PROMPT`, `to_int_amount()` và tối ưu hóa xử lý ảnh trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py).
- [x] **Bước 7.2**: Nâng cấp endpoint `POST /api/v1/extract-bill` trong [app_review.py](file:///Volumes/ExternalSSD/ocr-bill/app_review.py) hỗ trợ kép cả Multipart Form và Base64 JSON.
- [x] **Bước 7.3**: Đẩy toàn bộ mã nguồn lên máy chủ Pilot (`14.161.34.37`) qua [deploy_to_pilot.py](file:///Volumes/ExternalSSD/ocr-bill/deploy_to_pilot.py) và khởi động lại dịch vụ hệ thống `ocr-bill.service`.
- [x] **Bước 7.4**: Chạy thực nghiệm kiểm thử trực tiếp trên Pilot bằng [test_pilot_extract_bill.py](file:///Volumes/ExternalSSD/ocr-bill/test_pilot_extract_bill.py) với các ảnh thực tế kiểm chứng độ trễ ~3.5s và so khớp danh mục.
- [x] **Bước 7.5**: Cập nhật kết quả nghiệm thu chi tiết vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md) và báo cáo kết quả tới Quản lý / User.

---

## 10. KẾ HOẠCH ĐỢT 8: TÁI CẤU TRÚC HỆ THỐNG TÀI LIỆU – BIẾN `HANDOFF_SYSTEM_GUIDE.md` THÀNH MASTER CATALOG & XÂY DỰNG BỘ TÀI LIỆU CHUYÊN ĐỀ CHI TIẾT (`docs/`)

### 📌 1. BỐI CẢNH & YÊU CẦU TỪ QUẢN LÝ
* Quản lý sẽ thực hiện kiểm thử `extract-bill` trên Pilot cùng với đội CRM sau.
* **Yêu cầu hiện tại**:
  1. Rà soát lại toàn bộ tài liệu [HANDOFF_SYSTEM_GUIDE.md](file:///Volumes/ExternalSSD/ocr-bill/HANDOFF_SYSTEM_GUIDE.md).
  2. Biến [HANDOFF_SYSTEM_GUIDE.md](file:///Volumes/ExternalSSD/ocr-bill/HANDOFF_SYSTEM_GUIDE.md) thành **Tài Liệu Mục Lục Danh Mục (Catalog Master Document)**:
     - Chứa toàn bộ các chủ đề/chuyên đề chính với phần mô tả tóm tắt, mục tiêu, kết quả cốt lõi.
     - **Chi tiết chuyên sâu của từng chủ đề phải được tách riêng thành từng tài liệu độc lập (Separated Detail Documents)** trong thư mục `docs/`.
  3. Đặc biệt, các bước **Tối ưu hóa vừa thực hiện** (Nâng cấp mô hình 7B trên GPU RTX 3060, hạ latency xuống ~3.5s, khắc phục lỗi Empty, chuẩn hóa định dạng số tiền VND, đối soát 193 outlets) phải được ghi chép đầy đủ, chi tiết và có hệ thống trong các tài liệu chuyên đề này.

---

### 📌 2. KIẾN TRÚC BỘ TÀI LIỆU MỤC LỤC & CHUYÊN ĐỀ (DOCUMENTATION CATALOG ARCHITECTURE)

```
/Volumes/ExternalSSD/ocr-bill/
├── HANDOFF_SYSTEM_GUIDE.md                  ⭐ MASTER CATALOG & SỔ TAY ĐIỀU HƯỚNG TỔNG THỂ
│                                            (Tóm lược tất cả chủ đề, sơ đồ hệ thống, bảng chỉ dẫn liên kết)
└── docs/                                    📁 THƯ MỤC CHUYÊN ĐỀ CHI TIẾT (DEEP-DIVE SPECS)
    ├── 01_SYSTEM_ARCHITECTURE_TECH_STACK.md ── Chuyên đề 1: Kiến trúc Hệ thống, Môi trường & Hạ tầng CSDL
    ├── 02_VLM_MODEL_AND_GPU_OPTIMIZATION.md ── Chuyên đề 2: Tối ưu hóa Mô hình 7B & Tăng tốc GPU RTX 3060 CUDA
    ├── 03_VIETNAMESE_CURRENCY_AND_EXTRACTION_RULES.md ── Chuyên đề 3: Quy tắc Bóc tách Tiền VND & So khớp Mờ 193 Outlets
    ├── 04_CRM_API_INTEGRATION_SPEC.md       ── Chuyên đề 4: Đặc tả Kỹ thuật API Tích hợp CRM & Mobile (.NET Sample)
    ├── 05_WEB_REVIEW_AUDIT_PORTAL.md        ── Chuyên đề 5: Cổng Quản trị Duyệt Bill & Vết Kiểm toán CRM
    ├── 06_CRON_SCANNER_AND_SYNC_OPERATIONS.md ── Chuyên đề 6: Tác vụ Quét Ngầm Cron & Đồng bộ CSDL Tự động
    ├── 07_PILOT_DEPLOYMENT_CI_CD_OPS.md     ── Chuyên đề 7: Triển khai Máy chủ Pilot, CI/CD & Vận hành Dịch vụ
    └── 08_SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md ── Chuyên đề 8: Đối chiếu Môi trường & Quy trình Quản lý Thay đổi
```

---

### 📌 3. BẢNG CHECKLIST KẾ HOẠCH TRIỂN KHAI (ACTION PLAN)

- [x] **Bước 8.1**: Tạo thư mục `docs/` và biên soạn các tài liệu chuyên đề chi tiết:
  - `docs/01_SYSTEM_ARCHITECTURE_TECH_STACK.md`
  - `docs/02_VLM_MODEL_AND_GPU_OPTIMIZATION.md` (Ghi chép chuyên sâu toàn bộ đợt tối ưu hóa 7B, RTX 3060 12GB VRAM, Latency ~3.5s, khắc phục Empty result).
  - `docs/03_VIETNAMESE_CURRENCY_AND_EXTRACTION_RULES.md` (Ghi chép chuyên sâu quy tắc tiền VND, dấu chấm/phẩy phân cách ngàn, Rule 4 số HĐ, thuật toán so khớp 193 Outlets).
  - `docs/04_CRM_API_INTEGRATION_SPEC.md`
  - `docs/05_WEB_REVIEW_AUDIT_PORTAL.md`
  - `docs/06_CRON_SCANNER_AND_SYNC_OPERATIONS.md`
  - `docs/07_PILOT_DEPLOYMENT_CI_CD_OPS.md`
  - `docs/08_SERVER_BASELINE_AND_CHANGE_MANAGEMENT.md`
- [x] **Bước 8.2**: Tái cấu trúc [HANDOFF_SYSTEM_GUIDE.md](file:///Volumes/ExternalSSD/ocr-bill/HANDOFF_SYSTEM_GUIDE.md) thành **Tài Liệu Mục Lục Danh Mục (Catalog Master Document)**:
  - Mục lục điều hướng tổng thể (Executive Summary & Architecture Map).
  - Bảng danh mục chuyên đề (Catalog Table) kèm mô tả, đối tượng áp dụng và link dẫn đến từng file trong `docs/`.
  - Bảng tra cứu nhanh lệnh vận hành (Quick Operations Cheat Sheet).
- [x] **Bước 8.3**: Rà soát tính toàn vẹn của tất cả các liên kết markdown github-style `file://`.
- [x] **Bước 8.4**: Cập nhật kết quả vào [DEV_HISTORY.md](file:///Volumes/ExternalSSD/ocr-bill/DEV_HISTORY.md) và báo cáo nghiệm thu tới Quản lý / User.








