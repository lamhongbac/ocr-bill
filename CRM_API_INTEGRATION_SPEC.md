# TÀI LIỆU ĐẶC TẢ TÍCH HỢP API OCR HÓA ĐƠN CHO HỆ THỐNG CRM GIGAMALL
> **Dành cho:** Đội ngũ phát triển CRM (.NET Core / Mobile App / Backend Server 2)  
> **Phiên bản API:** `v2.2` (Cập nhật: Tham số kiểm soát trùng lặp, Upload Base64/Multipart, Async OCR & Trigger Batch)  
> **Định dạng dữ liệu:** `JSON` | `RESTful API`  
> **Mã hóa ký tự:** `UTF-8`

---

## 1. THÔNG TIN MÔI TRƯỜNG & ENDPOINT GỐC (BASE URL)

Tùy theo môi trường triển khai thực tế của Gigamall, hệ thống CRM và Mobile App có thể kết nối qua các địa chỉ sau:

| Môi trường | Base URL | Cổng dịch vụ | Ghi chú vận hành |
| :--- | :--- | :---: | :--- |
| **Mạng nội bộ LAN** | `http://192.168.2.4:8000` | `8000` | Kết nối trực tiếp giữa Server CRM và Server OCR (Tốc độ cao nhất) |
| **Server Pilot Public** | `http://14.161.34.37:8080` | `8080` | Cổng Public chính qua Nginx Reverse Proxy (UAT / Pilot) |
| **Domain Internet (HTTPS)** | `https://ocr.gigamall.com.vn` | `443` | Kết nối an toàn SSL Cloudflare Tunnel / Let's Encrypt |
| **Môi trường Dev (Mac Mini)**| `http://127.0.0.1:8000` | `8000` | Môi trường thử nghiệm cục bộ |

---

## 2. QUY ĐỊNH CHUNG VỀ DỮ LIỆU & BẢO MẬT

1. **Định dạng ảnh hỗ trợ**:
   - `image/jpeg` (`.jpg`, `.jpeg`), `image/png` (`.png`), `image/webp` (`.webp`).
   - **Ảnh Windows BMP từ máy POS**: Hệ thống tích hợp bộ tự động nhận diện và chuyển đổi (on-the-fly conversion) sang chuẩn JPEG có cache để đảm bảo hiển thị mượt mà trên mọi trình duyệt Chrome, Safari và Mobile App WebView.
2. **Dung lượng tệp tối đa**: `20 MB` / ảnh.
3. **Mã băm toàn vẹn (SHA-256 FileHash)**: Mỗi ảnh tải lên đều được tính toán mã SHA-256 để chống trùng lặp dữ liệu tuyệt đối ở cấp độ byte.
4. **Tính nguyên tử (Atomicity)**: Khi tải lên, hệ thống đảm bảo nguyên tắc: nếu quá trình ghi nhận CSDL MS-SQL gặp sự cố, tệp ảnh trên đĩa cứng sẽ được tự động xóa (Rollback) ngay lập tức, không bao giờ để lại tệp rác mồ côi.
5. **Chuẩn hóa số tiền (`bill_total`, `final_total`)**:
   - Luôn là **số nguyên dương (Integer)**, đơn vị VNĐ. Đã trừ toàn bộ voucher, giảm giá, điểm thưởng.
   - Ví dụ: Hóa đơn 150.000 đ $\rightarrow$ `150000`.

---

## 3. DANH SÁCH ENDPOINTS CHI TIẾT

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ 1. POST /api/v1/bills/upload         : Upload ảnh hóa đơn qua Multipart Form   │
│ 2. POST /api/v1/bills/upload-base64  : Upload ảnh hóa đơn dạng Base64 JSON     │
│ 3. POST /api/v1/extract-bill         : Bóc tách hóa đơn trực tiếp (Core AI)    │
│ 4. POST /api/v1/bills/trigger-ocr    : Kích hoạt chạy OCR hàng loạt (Batch)    │
│ 5. POST /api/v1/bills/{id}/trigger-ocr: Kích hoạt chạy OCR cho 1 bill cụ thể   │
│ 6. GET  /api/bills/{bill_id}         : Tra cứu chi tiết hóa đơn & Audit Logs   │
│ 7. POST /api/bills/{bill_id}/review  : CRM xác nhận Duyệt / Từ chối hóa đơn    │
│ 8. PUT  /api/bills/{bill_id}/edit    : Chỉnh sửa thông tin hóa đơn (Admin/CSKH)│
│ 9. GET  /api/outlets                 : Danh mục 81 gian hàng chuẩn Gigamall    │
│ 10. GET /api/images/{filename}       : Xem ảnh hóa đơn (Auto BMP -> JPEG)     │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

### API 1: UPLOAD ẢNH HÓA ĐƠN QUA MULTIPART FORM-DATA (KHUYẾN NGHỊ CHO MOBILE)

Dùng khi Mobile App khách hàng hoặc máy quét POS gửi tệp ảnh trực tiếp. Hỗ trợ chế độ phản hồi cực nhanh (< 100ms) để giải phóng giao diện người dùng.

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/bills/upload`
* **Content-Type**: `multipart/form-data`

#### Bảng tham số Form Data:
| Tham số | Kiểu dữ liệu | Bắt buộc | Mặc định | Mô tả chi tiết |
| :--- | :--- | :---: | :---: | :--- |
| `file` | Binary (File) | **Có** | - | Tệp ảnh hóa đơn chụp thực tế |
| `filename` | String | Không | `null` | Tên tệp tùy biến nếu Mobile đã sinh mã riêng (vd: `10305_181026095239.png`) |
| `actor` | String | Không | `"CRM Mobile"`| Tên định danh đối tượng tải lên (Khách hàng / Mã NV thu ngân) |
| `note` | String | Không | `"Tải lên từ Mobile qua API Multipart"` | Ghi chú kèm theo hóa đơn |
| `async_ocr` | Boolean/String| Không | `true` | **`true`**: Lưu ảnh, ghi DB PENDING, kích hoạt OCR ngầm, **phản hồi ngay trong < 100ms**.<br>**`false`**: Chờ AI bóc tách xong mới phản hồi (Sync ~1-3s). |
| `auto_ocr` | Boolean/String| Không | `true` | **`true`**: Tự động đưa vào hàng đợi AI bóc tách.<br>**`false`**: Chỉ lưu ảnh và tạo bản ghi CSDL, đợi trigger thủ công. |
| `duplicate_action`| String | Không | `"warn"` | **Cơ chế kiểm soát khi phát hiện trùng ảnh**:<br>• `warn`: Tiếp nhận, cảnh báo trùng (mặc định)<br>• `allow`: Cho phép upload lại có chủ đích<br>• `reject`: Chặn ngay lập tức chống spam/phá |

> **Header thay thế**: CRM có thể truyền qua HTTP Header `X-Duplicate-Action: warn | allow | reject`.

#### Cấu trúc Response khi `async_ocr: true` (Phản hồi tức thì < 100ms):
```json
{
  "success": true,
  "bill_id": 128,
  "filename": "10305_181026095239.png",
  "image_path": "uploads/10305_181026095239.png",
  "status": "PENDING",
  "is_duplicate": false,
  "duplicate_action": "warn",
  "action_taken": null,
  "duplicate_info": null,
  "async_ocr": true,
  "message": "Đã tiếp nhận hóa đơn thành công. Đang bóc tách ngầm bằng AI.",
  "latency_seconds": 0.045
}
```

#### Cấu trúc Response khi `duplicate_action: "reject"` và ảnh bị trùng:
```json
{
  "success": false,
  "bill_id": 129,
  "filename": "ocr_dup_123.jpg",
  "is_duplicate": true,
  "duplicate_action": "reject",
  "action_taken": "REJECTED",
  "review_status": "REJECTED",
  "reject_reason": "Hóa đơn trùng lặp 100% với Bill #105 (10305_181026095239.png). Hệ thống từ chối nhận ảnh theo cấu hình CRM (chống spam/phá).",
  "duplicate_info": {
    "BillId": 105,
    "Filename": "10305_181026095239.png",
    "Status": "APPROVED",
    "CreatedAt": "2026-10-20 15:00:00"
  },
  "message": "⛔ TỪ CHỐI: Hóa đơn này trùng lặp với Bill #105 (10305_181026095239.png). Hệ thống đã từ chối nhận ảnh theo yêu cầu chống spam/phá của CRM.",
  "latency_seconds": 0.038
}
```

---

### API 2: UPLOAD ẢNH HÓA ĐƠN DẠNG BASE64 JSON (TỐI ƯU CHO MOBILE SDK)

Dành riêng cho các ứng dụng Mobile App (Flutter, React Native, iOS Swift, Android Kotlin) đã chuyển đổi ảnh thành chuỗi Base64 và muốn gửi qua payload JSON thuần.

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/bills/upload-base64`
* **Content-Type**: `application/json`
* **Header tùy chọn**: `X-Duplicate-Action: warn | allow | reject`

#### Request Body (`UploadBase64Request`):
```json
{
  "image_base64": "/9j/4AAQSkZJRgABAQEASABIAAD...",
  "filename": "mobile_bill_20261022_001.jpg",
  "actor": "Khách hàng VIP 0901234567",
  "note": "Khách chụp trực tiếp tại quầy Highlands",
  "async_ocr": true,
  "auto_ocr": true,
  "duplicate_action": "allow"
}
```

#### Giải thích tham số JSON:
| Trường | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
| :--- | :--- | :---: | :---: | :--- |
| `image_base64` | String | **Có** | - | Chuỗi Base64 ảnh (hỗ trợ cả dạng thô hoặc có tiền tố `data:image/jpeg;base64,...`) |
| `filename` | String | Không | `null` | Tên tệp lưu trữ trên server |
| `actor` | String | Không | `"CRM Mobile"` | Định danh người tải lên |
| `note` | String | Không | `"Tải lên từ Mobile qua API Base64"` | Ghi chú đi kèm |
| `async_ocr` | Boolean | Không | `true` | Xử lý OCR ngầm (phản hồi trong < 100ms) |
| `auto_ocr` | Boolean | Không | `true` | Tự động kích hoạt OCR |
| `duplicate_action`| String | Không | `"warn"` | Hành vi khi trùng: `"warn"`, `"allow"`, `"reject"` |

#### Response (HTTP 200 OK):
Tương tự cấu trúc của API 1.

---

### API 3: BÓC TÁCH HÓA ĐƠN TRỰC TIẾP BẰNG AI (EXTRACT BILL OCR - SYNC)

Dùng khi hệ thống cần AI bóc tách ngay lập tức và trả về đầy đủ các trường thông tin trong cùng một phiên kết nối HTTP.

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/extract-bill`
* **Content-Type**: `multipart/form-data`

#### Tham số Request:
| Tham số | Kiểu dữ liệu | Bắt buộc | Mô tả |
| :--- | :--- | :---: | :--- |
| `file` | Binary (File) | **Có** | Tệp ảnh hóa đơn |
| `mem_id` | String | Không | Mã thành viên / Khách hàng tích điểm |
| `image_number` | String | Không | Mã định danh do CRM quản lý |
| `duplicate_action`| String | Không | `"warn"` (mặc định), `"allow"`, `"reject"` |

#### Cấu trúc Response thành công (HTTP 200 OK):
```json
{
  "success": true,
  "bill_id": 118,
  "filename": "ocr_20261022_143000_abc123.jpg",
  "is_duplicate": false,
  "duplicate_action": "warn",
  "action_taken": null,
  "duplicate_info": null,
  "latency_seconds": 0.85,
  "data": {
    "brand_name": "HIGHLANDS COFFEE",
    "outlet_name": "HIGHLANDS COFFEE GIGAMALL",
    "outlet_number": "HIGHLANDS",
    "bill_number": "HD-1802023",
    "bill_datetime": "2026-10-20 14:30:00",
    "bill_total": 83000,
    "is_valid_bill": true,
    "match_score": 1.0,
    "confidence": 0.98
  },
  "raw_output": "{\"brand_name\": \"HIGHLANDS COFFEE\", ...}"
}
```

---

### API 4: KÍCH HOẠT CHẠY OCR HÀNG LOẠT (TRIGGER BATCH OCR)

Dùng khi hệ thống CRM muốn kích hoạt chạy bóc tách cho các hóa đơn đã được tải lên trước đó (khi `auto_ocr = false` hoặc quét lại các hóa đơn PENDING).

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/bills/trigger-ocr`
* **Content-Type**: `application/json`

#### Request Body (`TriggerOcrRequest`):
```json
{
  "bill_ids": [120, 121, 122],
  "limit": 50,
  "async_execution": true,
  "actor": "CRM Backend Scheduler"
}
```

#### Giải thích tham số:
| Trường | Kiểu | Mặc định | Mô tả |
| :--- | :--- | :---: | :--- |
| `bill_ids` | Array of Int | `null` | Danh sách BillId cụ thể cần chạy. Nếu bỏ trống, hệ thống sẽ tự quét N hóa đơn PENDING cũ nhất |
| `limit` | Integer | `50` | Số lượng hóa đơn tối đa cần quét khi không truyền `bill_ids` |
| `async_execution` | Boolean | `true` | `true`: Chạy ngầm trong nền, trả về mã tiếp nhận ngay; `false`: Chờ chạy xong toàn bộ |
| `actor` | String | `"CRM Backend API"` | Định danh đối tượng gọi kích hoạt |

#### Response (HTTP 200 OK):
```json
{
  "success": true,
  "queued_count": 3,
  "bill_ids": [120, 121, 122],
  "async_execution": true,
  "message": "Đã tiếp nhận 3 hóa đơn vào hàng đợi xử lý AI."
}
```

---

### API 5: KÍCH HOẠT OCR CHO 1 HÓA ĐƠN CỤ THỂ (TRIGGER SINGLE OCR)

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/bills/{bill_id}/trigger-ocr`
* **Query Parameters (Tùy chọn)**:
  * `async_execution`: `true` (mặc định) hoặc `false`
  * `actor`: Tên người thực hiện (mặc định: `"CRM Web Admin"`)

---

### API 6: TRA CỨU CHI TIẾT HÓA ĐƠN & VẾT KIỂM TOÁN (GET BILL & AUDIT)

* **Phương thức**: `GET`
* **Đường dẫn**: `/api/bills/{bill_id}`
* **Response (HTTP 200 OK)**:
```json
{
  "BillId": 105,
  "Filename": "10305_181026095239.png",
  "ImagePath": "uploads/10305_181026095239.png",
  "FileHash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "Status": "APPROVED",
  "OcrOutletName": "QUẦY INFORMATION GIGAMALL",
  "OcrTotal": 560000,
  "OcrIsValid": true,
  "FinalOutletNumber": "GIGAMALL",
  "FinalOutletName": "QUẦY INFORMATION GIGAMALL",
  "FinalTotal": 560000,
  "FinalBillNumber": "17.08.2023 - 14:59",
  "FinalDateTime": "2026-08-17T14:59:00",
  "IsManualEdited": true,
  "ReviewedBy": "admin_cskh",
  "ReviewedAt": "2026-10-20T15:07:56",
  "RejectReason": null,
  "audit_logs": [
    {
      "AuditId": 1,
      "Action": "UPDATE_FIELD",
      "FieldName": "FinalTotal",
      "OldValue": "560",
      "NewValue": "560000",
      "Actor": "admin_cskh",
      "Note": "Khách thanh toán 560k",
      "CreatedAt": "20/10/2026 15:07:46"
    },
    {
      "AuditId": 2,
      "Action": "APPROVE",
      "FieldName": "Status",
      "OldValue": "PENDING",
      "NewValue": "APPROVED",
      "Actor": "admin_cskh",
      "Note": "",
      "CreatedAt": "20/10/2026 15:07:56"
    }
  ]
}
```

---

### API 7: PHÊ DUYỆT HOẶC TỪ CHỐI HÓA ĐƠN (SUBMIT REVIEW)

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/bills/{bill_id}/review`
* **Content-Type**: `application/json`

#### Request Body:
```json
{
  "status": "APPROVED",
  "actor": "nguyenvana_cskh",
  "reject_reason": null
}
```
*(Nếu `status = "REJECTED"`, trường `reject_reason` điền lý do: "Hóa đơn quá hạn", "Hóa đơn mờ", "Ảnh không hợp lệ",...)*

---

### API 8: CHỈNH SỬA THÔNG TIN HÓA ĐƠN (INLINE CORRECTION)

* **Phương thức**: `PUT`
* **Đường dẫn**: `/api/bills/{bill_id}/edit`
* **Content-Type**: `application/json`

#### Request Body:
```json
{
  "final_outlet_number": "HIGHLANDS",
  "final_outlet_name": "HIGHLANDS COFFEE GIGAMALL",
  "final_total": 150000,
  "final_bill_number": "HD-99982",
  "final_datetime": "2026-10-20 18:30:00",
  "actor": "admin_cskh",
  "note": "Khách dùng voucher giấy 30k nên trừ bớt"
}
```

---

### API 9: LẤY DANH MỤC CỬA HÀNG CHUẨN (GET MASTER OUTLETS)

* **Phương thức**: `GET`
* **Đường dẫn**: `/api/outlets`
* **Response (HTTP 200 OK)**:
```json
[
  {
    "outlet_id": 3164,
    "outlet_number": "ADIDAS",
    "outlet_name": "ADIDAS",
    "brand_id": 1115,
    "brand_name": "ADIDAS",
    "outlet_address": "L1-12"
  },
  {
    "outlet_id": 3165,
    "outlet_number": "HIGHLANDS",
    "outlet_name": "HIGHLANDS COFFEE",
    "brand_id": 1116,
    "brand_name": "HIGHLANDS COFFEE",
    "outlet_address": "Tầng Trệt GIGAMALL"
  }
]
```

---

### API 10: XEM ẢNH HÓA ĐƠN (SERVE & OPTIMIZE IMAGE)

* **Phương thức**: `GET`
* **Đường dẫn**: `/api/images/{filename}`
* **Tính năng tối ưu hóa**: 
  - Tự động nhận diện nếu ảnh gốc là định dạng Windows BMP (thường xuất từ POS Gigamall nhưng đặt đuôi `.png`).
  - Tự động chuyển đổi sang JPEG với chất lượng cao (RGB 90%) và lưu vào thư mục cache `/uploads/.cache/` để phản hồi tức thì trong các lần gọi tiếp theo.
  - Tương thích 100% với thẻ `<img src="...">` của Chrome, Safari, Firefox và Mobile WebViews.

---

## 4. CHI TIẾT CƠ CHẾ KIỂM SOÁT TRÙNG LẶP (`duplicate_action`)

Nhằm bảo vệ hệ thống trước các hành vi gian lận hoặc gửi trùng lặp, CRM có toàn quyền điều khiển hành vi bóc tách thông qua tham số `duplicate_action` (hoặc header `X-Duplicate-Action`):

```
┌─────────────────┬───────────────────┬─────────────────┬───────────────────────────────┐
│ duplicate_action│ Trạng thái DB     │ Chạy AI OCR?    │ Ý nghĩa nghiệp vụ             │
├─────────────────┼───────────────────┼─────────────────┼───────────────────────────────┤
│ "warn"          │ PENDING           │ CÓ (bình thường)│ Báo cờ trùng để nhân viên     │
│ (Mặc định)      │ (Ghi chú trùng #) │                 │ thẩm định thủ công khi duyệt. │
├─────────────────┼───────────────────┼─────────────────┼───────────────────────────────┤
│ "allow"         │ PENDING           │ CÓ (bình thường)│ Khách/CRM chủ động gửi lại bổ │
│                 │ (Ghi chú Cho Phép)│                 │ sung; hệ thống ghi log chấp   │
│                 │                   │                 │ thuận tái sử dụng ảnh.        │
├─────────────────┼───────────────────┼─────────────────┼───────────────────────────────┤
│ "reject"        │ REJECTED          │ KHÔNG (Bỏ qua)  │ Chặn ngay hành vi spam/phá;   │
│                 │ (Lý do từ chối tự │                 │ tiết kiệm 100% chi phí tính   │
│                 │  động của CRM)    │                 │ toán GPU/CPU của hệ thống AI. │
└─────────────────┴───────────────────┴─────────────────┴───────────────────────────────┘
```

---

## 5. BẢNG ÁNH XẠ DỮ LIỆU CSDL (DATABASE SCHEMA MAPPING)

| Trường trong API JSON | Bảng CSDL CRM (`mssOCRTrans`) | Bảng CSDL OCR (`OcrBills`) | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- | :--- | :--- |
| `bill_id` | `TransID` / `BillID` | `BillId` | `INT IDENTITY` | Khóa chính hóa đơn |
| `filename` | `ImageName` | `Filename` | `NVARCHAR(255)`| Tên tệp ảnh |
| `FileHash` | - | `FileHash` | `NVARCHAR(64)` | Mã băm SHA-256 đối soát trùng ảnh |
| `data.brand_name` | `BrandName` | `OcrBrand` | `NVARCHAR(100)`| Tên thương hiệu AI đọc |
| `data.outlet_name` | `OutletName` | `OcrOutletName` | `NVARCHAR(255)`| Tên cửa hàng AI đọc |
| `data.outlet_number` | `OutletNumber` | `OcrOutletNumber` | `NVARCHAR(50)` | Mã cửa hàng chuẩn CRM |
| `data.bill_number` | `BillNumber` | `OcrBillNumber` | `NVARCHAR(100)`| Số hóa đơn ban đầu |
| `data.bill_datetime` | `BillDateTime` | `OcrDateTime` | `DATETIME` | Ngày giờ giao dịch ban đầu |
| `data.bill_total` | `BillTotal` | `OcrTotal` | `BIGINT` | Tổng tiền AI đọc |
| **`final_total`** | **`BillTotalA`** | **`FinalTotal`** | `BIGINT` | **Số tiền CHÍNH THỨC để tích điểm** |
| **`final_outlet_number`** | **`OutletNumberA`** | **`FinalOutletNumber`**| `NVARCHAR(50)` | **Mã cửa hàng CHÍNH THỨC sau duyệt** |
| **`final_bill_number`** | **`BillNumberA`** | **`FinalBillNumber`** | `NVARCHAR(100)`| **Số hóa đơn CHÍNH THỨC sau duyệt** |
| **`status`** | `Reviewed`, `Approved` | `Status` | `NVARCHAR(50)` | `PENDING`, `APPROVED`, `REJECTED`, `MANUAL_EDITED` |
| `actor` | `ReviewBy`, `ModifiedBy` | `ReviewedBy` | `NVARCHAR(100)`| Tên nhân viên thao tác |
| `reject_reason` | `ReviewNotes` | `RejectReason` | `NVARCHAR(500)`| Lý do từ chối nếu không duyệt |

---

## 6. MÃ NGUỒN MẪU TÍCH HỢP (CODE EXAMPLES)

### 6.1. Ví dụ C# (.NET Core HttpClient trên Backend CRM Server)

```csharp
using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading.Tasks;

public class GigamallOcrClient
{
    private readonly HttpClient _httpClient;
    private const string BASE_URL = "http://14.161.34.37:8080";

    public GigamallOcrClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.BaseAddress = new Uri(BASE_URL);
        _httpClient.Timeout = TimeSpan.FromSeconds(30);
    }

    /// <summary>
    /// Upload hóa đơn nhanh qua Multipart Form với cơ chế kiểm soát trùng lặp
    /// </summary>
    public async Task<OcrUploadResponseDto> UploadBillAsync(
        string imagePath, 
        string actor = "CRM Mobile", 
        string duplicateAction = "warn")
    {
        using var form = new MultipartFormDataContent();
        
        // 1. Nạp file ảnh
        byte[] imageBytes = await File.ReadAllBytesAsync(imagePath);
        var fileContent = new ByteArrayContent(imageBytes);
        fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse("image/jpeg");
        form.Add(fileContent, "file", Path.GetFileName(imagePath));

        // 2. Các tham số điều khiển
        form.Add(new StringContent(actor), "actor");
        form.Add(new StringContent(duplicateAction), "duplicate_action");
        form.Add(new StringContent("true"), "async_ocr"); // Phản hồi tức thì < 100ms

        // 3. Gửi request
        HttpResponseMessage response = await _httpClient.PostAsync("/api/v1/bills/upload", form);
        string json = await response.Content.ReadAsStringAsync();
        
        return JsonSerializer.Deserialize<OcrUploadResponseDto>(json, new JsonSerializerOptions 
        { 
            PropertyNameCaseInsensitive = true 
        });
    }
}

public class OcrUploadResponseDto
{
    public bool Success { get; set; }
    public int Bill_Id { get; set; }
    public string Filename { get; set; }
    public string Status { get; set; }
    public bool Is_Duplicate { get; set; }
    public string Duplicate_Action { get; set; }
    public string Message { get; set; }
    public double Latency_Seconds { get; set; }
}
```

### 6.2. Ví dụ Flutter / Dart (Mobile App Khách Hàng)

```dart
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

Future<void> uploadBillFromMobile(File imageFile, String memberId) async {
  final uri = Uri.parse('http://14.161.34.37:8080/api/v1/bills/upload');
  
  var request = http.MultipartRequest('POST', uri)
    ..fields['actor'] = 'Member_$memberId'
    ..fields['duplicate_action'] = 'warn'
    ..fields['async_ocr'] = 'true'
    ..files.add(await http.MultipartFile.fromPath('file', imageFile.path));

  var streamedResponse = await request.send();
  var response = await http.Response.fromStream(streamedResponse);

  if (response.statusCode == 200) {
    var data = jsonDecode(response.body);
    print('Đã tải lên thành công Bill ID: ${data['bill_id']}');
    if (data['is_duplicate'] == true) {
      print('Cảnh báo: Ảnh này đã từng được chụp trước đó!');
    }
  } else {
    print('Lỗi upload: ${response.body}');
  }
}
```

### 6.3. Ví dụ cURL (Command Line & Postman Testing)

```bash
# 1. Upload nhanh qua Multipart Form (Mặc định async_ocr=true, phản hồi < 100ms)
curl -X POST "http://14.161.34.37:8080/api/v1/bills/upload" \
     -F "file=@/path/to/bill.jpg" \
     -F "actor=Mobile_Tester" \
     -F "duplicate_action=warn"

# 2. Upload và yêu cầu từ chối ngay nếu trùng ảnh (Chống spam/phá)
curl -X POST "http://14.161.34.37:8080/api/v1/bills/upload" \
     -F "file=@/path/to/bill.jpg" \
     -F "duplicate_action=reject"

# 3. Kích hoạt bóc tách OCR hàng loạt cho danh sách hóa đơn PENDING
curl -X POST "http://14.161.34.37:8080/api/v1/bills/trigger-ocr" \
     -H "Content-Type: application/json" \
     -d '{"bill_ids": [105, 106], "actor": "CRM Admin"}'
```

---

## 7. THÔNG TIN HỖ TRỢ KỸ THUẬT & SWAGGER UI
* **Swagger / OpenAPI Documentation tương tác trực tiếp**:  
  Truy cập trực tiếp tại `http://14.161.34.37:8080/docs` hoặc `http://127.0.0.1:8000/docs` để thử nghiệm trực tiếp từng API với giao diện trực quan và đầy đủ schema.
* **Đội ngũ phát triển AI & Backend**: Dự án R&D OCR Hóa đơn Gigamall.
