# TÀI LIỆU BÀN GIAO & VẬN HÀNH DỰ ÁN OCR HÓA ĐƠN GIGAMALL
> **Dành cho Kỹ sư / AI Developer tiếp quản dự án**  
> *Cập nhật ngày: 20/10/2026*  
> *Đọc tệp này để nắm toàn bộ kiến trúc, dữ liệu, kết quả và lệnh chạy tiếp tục dự án.*

---

## 1. TỔNG QUAN DỰ ÁN
* **Mục tiêu**: Tự động hóa bóc tách dữ liệu từ ảnh hóa đơn mua sắm tại TTTM GigaMall bằng mô hình Vision-Language Model (VLM) chạy trên Mac Mini M4 nội bộ; phục vụ quy trình thẩm định, tích điểm thành viên và kiểm toán CRM.
* **Các trường thông tin cốt lõi**:
  1. `brand_name`: Thương hiệu (Highlands, Fahasa, Co.opXtra,...)
  2. `outlet_name`: Tên cửa hàng in trên bill
  3. `bill_number`: Số hóa đơn / Bill No
  4. `bill_datetime`: Ngày giờ giao dịch (`YYYY-MM-DD HH:mm:ss`)
  5. `bill_total`: Tổng tiền khách thực trả sau chiết khấu/voucher (số nguyên)
  6. `is_valid_bill`: Đánh giá bill hợp lệ hay ảnh rác / quá mờ
* **Chuẩn hóa CRM**: Tên quán được chuẩn hóa mờ (Fuzzy matching) với 81 cửa hàng trong danh mục `master_outlets.json` để lấy mã định danh `outlet_number` của CRM.

---

## 2. KIẾN TRÚC HỆ THỐNG & CÔNG NGHỆ (TECH STACK)

### 2.1. Phần cứng & Môi trường chạy
* **Máy trạm AI**: Mac Mini M4, 24GB Unified Memory, macOS 26.6.2.
* **Ổ đĩa chứa code**: SanDisk ExternalSSD định dạng **ExFAT** (`/Volumes/ExternalSSD/ocr-bill`).
  * *Lưu ý sống còn về ExFAT*: Hệ thống tệp ExFAT **không hỗ trợ symbolic link**. Do đó virtualenv phải được tạo bằng cờ `--copies`: `python3.11 -m venv --copies venv`.
* **Python Runtime**: Python 3.11.17 (`./venv`).

### 2.2. Thư viện & Mô hình AI
* **Inference Engine**: `mlx` (0.32.4) + `mlx-vlm` (0.7.9) tối ưu riêng cho Apple Silicon Metal Unified Memory.
* **Mô hình VLM**: `Qwen2-VL-7B-Instruct-4bit` (dung lượng 4.4GB).
  * Đã tải sẵn tại thư mục nội bộ: `/Volumes/ExternalSSD/ocr-bill/models/Qwen2-VL-7B-Instruct-4bit`.
  * Không tải lại từ HuggingFace khi chạy offline.
* **Web Framework**: `fastapi` (0.150.0) + `uvicorn` (0.54.0) + `pydantic` (2.14.1).
* **CSDL Driver**: `pymssql` (2.4.5) kết hợp `FreeTDS` (1.5.19).

### 2.3. Máy chủ Cơ sở Dữ liệu SQL Server
* **Server**: `115.165.166.208:6868`
* **CSDL**: `CLMHQ4GIGA`
* **Phiên bản**: Microsoft SQL Server 2012 - 11.0.2100.60 (X64).
* **Tài khoản**: `crmapp1` / `1q2w3e4r` (User ứng dụng có quyền `SELECT, INSERT, UPDATE, DELETE`).
* **LƯU Ý KỸ THUẬT VỀ TLS/SSL (CỰC KỲ QUAN TRỌNG)**:
  * SQL Server 2012 sử dụng TLS cũ mà OpenSSL 3 trên macOS hiện đại sẽ từ chối bắt tay (handshake failed).
  * **Giải pháp bắt buộc**: Dự án đã cấu hình tệp `freetds.conf` với thiết lập:
    ```ini
    [CLMHQ4GIGA]
    host = 115.165.166.208
    port = 6868
    tds version = 7.4
    encryption = off
    check certificate = no
    client charset = UTF-8
    ```
    Mọi script Python kết nối DB phải nạp biến môi trường: `os.environ["FREETDSCONF"] = str(BASE_DIR / "freetds.conf")` trước khi gọi `pymssql.connect`.

---

## 3. KẾT QUẢ ĐÃ ĐẠT ĐƯỢC

### 3.1. Giai đoạn 1 – POC Gate 1 (Bóc tách Batch 101 Hóa đơn)
* **Tập dữ liệu**: 101 ảnh hóa đơn thực tế trong `TEST_IMAGES/` (lấy từ nguồn CRM `mssOCRTrialTrans`).
* **Kỹ thuật xử lý lỗi quan trọng**:
  * Mô hình Qwen2-VL trước đó bị lặp số vô tận ở `bill_number` (lặp `110000000000...` tràn token và mất 20s/bill dẫn đến lỗi JSON).
  * Đã khắc phục triệt để bằng tham số `repetition_penalty=1.1` trong hàm `generate` kết hợp cơ chế `regex fallback` trong `evaluate_lean.py`.
* **Kết quả đo lường**:
  * Tỷ lệ bóc tách thành công: **101 / 101 (100%, 0 lỗi)**.
  * Tự động khớp cửa hàng CRM: **88 / 101 (87.1%)**.
  * Hóa đơn hợp lệ theo AI: **74 / 101**.
  * Latency trung bình: **7.69 giây / hóa đơn** (trên Mac Mini M4 bản thường).
* **Tệp kết quả**:
  * `results.csv`: Dữ liệu bảng 101 hóa đơn kèm thời gian xử lý từng bill.
  * `report.html`: Báo cáo trực quan cho phép chấm ĐẠT/SAI thủ công bằng mắt trên trình duyệt (có localStorage và xuất CSV).

### 3.2. Giai đoạn 2 – Ứng dụng Web Review & Vết kiểm toán (US 1, US 2, US 3)
* **Cơ sở dữ liệu MS-SQL**:
  * Đã chạy script `create_tables.sql` tạo 2 bảng trên `CLMHQ4GIGA`:
    1. `OcrBills`: Lưu thông tin hóa đơn, kết quả AI ban đầu và dữ liệu Admin phê duyệt chính thức.
    2. `OcrBillAuditLogs`: Lưu vết kiểm toán cho từng hành động sửa đổi/duyệt.
  * Đã nạp thành công toàn bộ **101 hóa đơn** vào bảng `OcrBills` ở trạng thái ban đầu `PENDING`.
* **Ứng dụng Web `app_review.py`**:
  * **US 1 (Review Workflow)**: 
    * Màn hình soi ảnh chất lượng cao (hỗ trợ zoom in/out, xoay ảnh 90°, đặt lại).
    * Phím tắt tốc độ cao: `[A]` (Phê duyệt), `[R]` (Từ chối kèm popup chọn lý do), `[←] / [→]` (Chuyển bill).
    * Màn hình danh sách tổng hợp (Batch table) có bộ lọc trạng thái và tìm kiếm.
  * **US 2 (Inline Correction)**: 
    * Cho phép Admin sửa Cửa hàng (dropdown autocomplete nối với 81 cửa hàng trong `master_outlets.json`).
    * Sửa Số tiền hợp lệ (tự động phát hiện sai biệt so với AI và bật tag cảnh báo màu vàng tránh gõ nhầm).
    * Sửa Số hóa đơn, Ngày giờ giao dịch.
    * Đánh dấu cờ `IsManualEdited = 1` khi có can thiệp của con người.
  * **US 3 (Audit Trail)**: 
    * Mọi thao tác sửa trường hoặc đổi trạng thái tự động ghi bản ghi vào `OcrBillAuditLogs` (`OldValue` $\rightarrow$ `NewValue`, `Actor`, `Note`, `CreatedAt`).
    * Timeline kiểm toán hiển thị trực tiếp ngay dưới màn hình soi của từng hóa đơn.
    * Tab riêng cho Auditor hiển thị toàn bộ lịch sử hệ thống kèm nút **"⬇ Xuất Báo cáo CSV"**.

### 3.3. Phát hiện về CSDL CRM hiện hữu (Quan trọng cho tương lai)
* Trong database `CLMHQ4GIGA` đã có sẵn 2 bảng:
  1. `mssOCRTrialTrans`: Bảng chạy thử nghiệm (đang có hơn 356.000 dòng). Toàn bộ 101 bill của chúng ta bắt nguồn từ bảng này.
  2. `mssOCRTrans`: Bảng OCR chính thức của CRM (hiện có 0 dòng, sẵn sàng cho Production).
* Bảng này đã được thiết kế sẵn các cột hậu tố **`A`** *(Approved/Admin)* như `BillTotalA`, `OutletNumberA`, `BillNumberA`, `BillDateTimeA` để lưu giá trị do Admin duyệt.

---

## 4. HƯỚNG DẪN KHỞI ĐỘNG & TIẾP TỤC DỰ ÁN

### 4.1. Kích hoạt môi trường ảo (Virtualenv)
Mở terminal trên Mac Mini tại thư mục dự án:
```bash
cd /Volumes/ExternalSSD/ocr-bill
source venv/bin/activate
```

### 4.2. Chạy lại đánh giá OCR Batch (nếu có thêm ảnh mới)
Nếu người dùng copy thêm ảnh hóa đơn vào thư mục `TEST_IMAGES/`:
```bash
# Chạy thử 3 ảnh
python evaluate_lean.py --limit 3

# Chạy toàn bộ ảnh trong TEST_IMAGES/
python evaluate_lean.py
```
Kết quả sẽ tự động ghi đè/cập nhật vào `results.csv` và `report.html`.

### 4.3. Khởi chạy Web Portal Duyệt & Kiểm toán (FastAPI)
```bash
# Chạy server
python app_review.py
# Hoặc chạy qua uvicorn
python -m uvicorn app_review:app --host 0.0.0.0 --port 8000 --reload
```
Truy cập giao diện tại trình duyệt: **`http://localhost:8000`**

### 4.4. Nạp lại hoặc đồng bộ hóa đơn mới vào CSDL MS-SQL
Nếu muốn import các hóa đơn mới từ `results.csv` vào bảng `OcrBills`:
```bash
python db.py
```

---

## 5. SƠ ĐỒ CẤU TRÚC THƯ MỤC DỰ ÁN

```
/Volumes/ExternalSSD/ocr-bill/
├── venv/                               # Môi trường Python 3.11 (được tạo với --copies)
├── models/
│   └── Qwen2-VL-7B-Instruct-4bit/     # Trọng số mô hình VLM cục bộ (4.4GB)
├── TEST_IMAGES/                        # 101 tệp ảnh hóa đơn thực tế (.png, .jpg)
├── master_outlets.json                 # Danh mục chuẩn 81 cửa hàng TTTM Gigamall
├── requirements.txt                    # Thư viện Python đã pin version
├── freetds.conf                        # Cấu hình FreeTDS kết nối SQL Server 2012
├── db_config.json                      # Cấu hình chuỗi kết nối MS-SQL (bảo mật, đã gitignore)
├── create_tables.sql                   # Script T-SQL tạo bảng OcrBills & OcrBillAuditLogs
├── db.py                               # Module Python DAO kết nối và thao tác MS-SQL
├── evaluate_lean.py                    # Script chạy suy luận VLM batch trên Mac Mini M4
├── app_review.py                       # Ứng dụng Web FastAPI Review & Audit Portal (US 1, 2, 3)
├── results.csv                         # Kết quả bóc tách 101 bill từ evaluate_lean.py
├── report.html                         # Báo cáo tĩnh HTML kiểm tra trực quan Gate 1
├── task201026.md                       # Checklist tiến độ nhiệm vụ
├── OCR_RD_MacMini_Deployment_Guide.md  # Tài liệu kiến trúc và hướng dẫn triển khai
└── HANDOFF_SYSTEM_GUIDE.md             # TÀI LIỆU NÀY (Bàn giao kỹ thuật toàn diện)
```

---

## 6. LỘ TRÌNH CHUYỂN GIAO TIẾP THEO (TỪ PHƯƠNG ÁN B SANG PHƯƠNG ÁN A)

Khi chuyển giao sang Giai đoạn 2 Production (Server 2 đảm nhiệm hoàn toàn UI/DB):
1. **API trên Mac Mini**: 
   * Trích xuất endpoint `/api/v1/extract-bill` từ tài liệu `OCR_RD_MacMini_Deployment_Guide.md` (Mục 6.2) để Mac Mini chỉ chạy dịch vụ AI thuần túy.
2. **Server 2 (.NET Core)**:
   * Backend .NET Core gọi API sang Mac Mini qua mạng LAN (`http://<IP_MAC_MINI>:8000/api/v1/extract-bill`).
   * Sử dụng trực tiếp cấu trúc bảng `OcrBills` / `OcrBillAuditLogs` (hoặc map vào bảng `mssOCRTrans` sẵn có).
   * Tái sử dụng thiết kế UI Split-screen Inspector từ `app_review.py` để tích hợp vào Web CRM hiện hành của Gigamall.

---

## 7. HƯỚNG DẪN TÍCH HỢP API UPLOAD DÀNH CHO MOBILE & CRM (HỖ TRỢ FAST SAVE & OCR NGẦM)

Hệ thống đã tích hợp 2 API chuyên dụng phục vụ việc Mobile chụp ảnh hoặc CRM đẩy ảnh lưu xuống ổ cứng máy chủ OCR (`uploads/`) theo cơ chế **Fast Save (Phản hồi < 0.1 giây, OCR chạy ngầm)**:
* **Mục tiêu**: Khách hàng chụp ảnh trên App không phải chờ 7–8 giây. Ảnh được lưu tức thì xuống đĩa, trả về mã `bill_id` ngay lập tức, tiến trình AI chạy bóc tách ngầm (Background Task).
* **Đảm bảo toàn vẹn**: Dù quá trình OCR có bị lỗi do ảnh mờ, ảnh rách thì bản ghi hóa đơn vẫn an toàn trong CSDL ở trạng thái `PENDING` để Admin duyệt tay trên Web Review Portal.

---

### 7.1. API 1: Multipart Form-Data (Tối ưu cho Mobile chụp ảnh)
* **Endpoint**: `POST http://<IP_MAY_CHU>:8000/api/v1/bills/upload`
* **Content-Type**: `multipart/form-data`
* **Tham số**:
  * `file` *(bắt buộc)*: Tệp nhị phân ảnh chụp (`.jpg`, `.png`, `.webp`).
  * `actor` *(tùy chọn, mặc định `"CRM Mobile"`)*: Số điện thoại khách hoặc mã định danh người dùng.
  * `note` *(tùy chọn)*: Ghi chú (VD: `"Chụp tại quầy Highlands"`).
  * `async_ocr` *(tùy chọn, mặc định `true`)*: 
    * `true` = **Fast Save**: Lưu đĩa và trả về ngay (< 0.1s), OCR bóc tách chạy ngầm.
    * `false` = Đồng bộ: Chờ AI bóc tách xong (khoảng 7s) mới trả về kết quả.
  * `auto_ocr` *(tùy chọn, mặc định `true`)*: `true` = Có chạy OCR; `false` = Chỉ lưu đĩa, không chạy OCR.
* **Ví dụ cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/bills/upload" \
       -F "file=@/duong/dan/anh_chup_bill.jpg" \
       -F "actor=0901234567" \
       -F "note=Khách nộp hóa đơn tích điểm" \
       -F "async_ocr=true"
  ```

---

### 7.2. API 2: Base64 JSON (Dành cho Mobile / CRM truyền chuỗi Base64)
* **Endpoint**: `POST http://<IP_MAY_CHU>:8000/api/v1/bills/upload-base64`
* **Content-Type**: `application/json`
* **Body mẫu**:
  ```json
  {
    "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "filename": "camera_capture.jpg",
    "actor": "0901234567",
    "note": "Khách chụp hóa đơn từ App",
    "async_ocr": true,
    "auto_ocr": true
  }
  ```

---

### 7.3. Cấu trúc JSON phản hồi từ Máy chủ OCR

#### Trường hợp A: Chế độ Fast Save (`async_ocr = true` - Mặc định, phản hồi < 0.1s)
Mobile App và CRM Backend nhận ngay kết quả trong chớp mắt:
```json
{
  "success": true,
  "bill_id": 106,
  "filename": "crm_20261021_100310_dabdd0_camera_capture.jpg",
  "image_url": "/api/images/crm_20261021_100310_dabdd0_camera_capture.jpg",
  "file_path": "uploads/crm_20261021_100310_dabdd0_camera_capture.jpg",
  "ocr_status": "PROCESSING",
  "ocr_result": null,
  "review_status": "PENDING",
  "save_latency_seconds": 0.085,
  "message": "Ảnh đã lưu an toàn xuống đĩa máy chủ trong 0.085s. AI đang chạy bóc tách ngầm."
}
```
*(Ngay sau đó, background worker sẽ tự động hoàn tất OCR và ghi đè thông tin bóc tách vào `OcrBills` trên CSDL MS-SQL).*

#### Trường hợp B: Chế độ đồng bộ (`async_ocr = false`)
Hệ thống đợi AI chạy xong (~7s) rồi trả về đầy đủ kết quả:
```json
{
  "success": true,
  "bill_id": 104,
  "filename": "crm_20261021_092446_eeffd3_camera_capture.jpg",
  "image_url": "/api/images/crm_20261021_092446_eeffd3_camera_capture.jpg",
  "file_path": "uploads/crm_20261021_092446_eeffd3_camera_capture.jpg",
  "ocr_status": "SUCCESS",
  "ocr_result": {
    "brand_name": "Highlands Coffee",
    "outlet_name": "Highlands Coffee GigaMall",
    "outlet_number": "T1-01",
    "resolved_outlet": "HIGHLANDS COFFEE GIGAMALL",
    "match_score": 0.95,
    "bill_number": "HD00129",
    "bill_datetime": "2026-10-21 09:15:00",
    "bill_total": 85000,
    "is_valid_bill": true,
    "latency": 7.42
  },
  "review_status": "PENDING",
  "save_latency_seconds": 7.48,
  "message": "Ảnh đã được lưu xuống đĩa máy chủ và hoàn tất bóc tách OCR."
}
```

* **Đường dẫn thư mục lưu ảnh vật lý trên ổ cứng máy chủ**:
  ```
  /Volumes/ExternalSSD/ocr-bill/uploads/
  ```
* **URL xem/tải lại ảnh qua HTTP**:
  ```
  GET http://<IP_MAY_CHU>:8000/api/images/{filename}
  ```

---

### 7.4. API 3 & 4: Kích hoạt chạy OCR chủ động từ Backend CRM (Trigger OCR APIs)

Khi Backend CRM muốn chủ động ra lệnh cho máy chủ OCR bóc tách lại hoặc bóc tách theo lô cho các hóa đơn:

#### A. Trigger bóc tách theo lô (Batch Trigger)
* **Endpoint**: `POST http://<IP_MAY_CHU>:8000/api/v1/bills/trigger-ocr`
* **Content-Type**: `application/json`
* **Body**:
  ```json
  {
    "bill_ids": [102, 103, 105],
    "limit": 50,
    "async_execution": true,
    "actor": "CRM Backend"
  }
  ```
  * *Lưu ý*: Nếu bỏ trống `bill_ids`, hệ thống sẽ tự động quét tối đa `limit` hóa đơn `PENDING` chưa từng được OCR.
  * `async_execution`: `true` = chạy ngầm trả về ngay; `false` = chờ AI chạy xong toàn bộ danh sách rồi trả kết quả.

#### B. Trigger bóc tách 1 hóa đơn cụ thể
* **Endpoint**: `POST http://<IP_MAY_CHU>:8000/api/v1/bills/{bill_id}/trigger-ocr?async_execution=true`

---

## 8. TIẾN TRÌNH QUÉT & BÓC TÁCH ĐỊNH KỲ ĐỘC LẬP (`cron_ocr_scanner.py`)

Tệp `cron_ocr_scanner.py` là công cụ độc lập giúp chống sót bill khi server restart hoặc để gom tải bóc tách vào ban đêm:

### 8.1. Các lệnh vận hành:
```bash
# 1. Kiểm tra nhanh (Dry-run): xem có bao nhiêu bill chưa được OCR mà không tốn tài nguyên
python cron_ocr_scanner.py --dry-run

# 2. Chạy quét bóc tách 1 đợt (tối đa 50 bill)
python cron_ocr_scanner.py --limit 50

# 3. Chạy chế độ DAEMON lặp lại liên tục (ví dụ quét mỗi 5 phút = 300s):
python cron_ocr_scanner.py --loop --interval 300

# 4. Chỉ định bóc tách duy nhất 1 BillId:
python cron_ocr_scanner.py --bill-id 105
```

### 8.2. Cấu hình chạy tự động bằng `crontab` trên Linux / macOS:
```bash
# Mở crontab
crontab -e

# Quét mỗi 5 phút một lần:
*/5 * * * * cd /Volumes/ExternalSSD/ocr-bill && ./venv/bin/python cron_ocr_scanner.py --limit 20 >> /Volumes/ExternalSSD/ocr-bill/cron.log 2>&1

# Hoặc chạy dồn tải vào 23:00 đêm mỗi ngày:
0 23 * * * cd /Volumes/ExternalSSD/ocr-bill && ./venv/bin/python cron_ocr_scanner.py --limit 500 >> /Volumes/ExternalSSD/ocr-bill/cron.log 2>&1
```

---

## 9. CƠ CHẾ TỰ ĐỘNG ĐỒNG BỘ DANH MỤC CỬA HÀNG (`master_outlets.json`) TỪ CSDL MS-SQL

Không cần copy file thủ công nữa. Hệ thống đã kết nối trực tiếp vào 2 bảng `G_Outlet` và `G_Brand` trong CSDL `CLMHQ4GIGA` để tự động hóa hoàn toàn việc cập nhật danh mục cửa hàng.

### 9.1. Câu truy vấn đồng bộ chuẩn xác từ CSDL:
```sql
SELECT 
    o.ID AS outlet_id,
    o.Number AS outlet_number,
    o.OutletName AS outlet_name,
    b.ID AS brand_id,
    b.Number AS brand_number,
    b.BrandName AS brand_name,
    o.Address AS outlet_address
FROM G_Outlet o WITH (NOLOCK)
INNER JOIN G_Brand b WITH (NOLOCK) ON o.BrandID = b.ID
WHERE o.IsActive = 1 AND o.IsUsed = 1
ORDER BY o.OutletName;
```
*(Kết quả: Trích xuất chính xác 81 cửa hàng đang hoạt động phục vụ việc so khớp tên quán).*

### 9.2. Ba cách đồng bộ linh hoạt:
1. **Qua API (Khuyến nghị cho CRM)**:
   * **Endpoint**: `POST http://<IP_MAY_CHU>:8000/api/v1/sync-outlets`
   * *Tác dụng*: Tự động cập nhật `master_outlets.json` và làm mới bộ nhớ RAM của AI ngay lập tức mà không cần restart server.
2. **Qua dòng lệnh Terminal (Dev / Sysadmin)**:
   ```bash
   python sync_outlets.py
   ```
3. **Tự động trong Cron Job định kỳ**:
   ```bash
   python cron_ocr_scanner.py --sync-outlets
   ```
