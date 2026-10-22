# TÀI LIỆU ĐẶC TẢ TÍCH HỢP API OCR HÓA ĐƠN CHO HỆ THỐNG CRM GIGAMALL
> **Dành cho:** Đội ngũ phát triển CRM (.NET Core / Mobile App / Backend Server 2)  
> **Phiên bản API:** `v2.0`  
> **Định dạng dữ liệu:** `JSON` | `RESTful API`  
> **Mã hóa ký tự:** `UTF-8`

---

## 1. THÔNG TIN MÔI TRƯỜNG & ENDPOINT GỐC (BASE URL)

Tùy theo môi trường triển khai thực tế của Gigamall, hệ thống CRM có thể kết nối qua các địa chỉ sau:

| Môi trường | Base URL | Ghi chú |
| :--- | :--- | :--- |
| **Mạng nội bộ LAN** | `http://192.168.2.4:8000` | Kết nối trực tiếp giữa Server 2 và Server OCR (Tốc độ cao nhất) |
| **IP Public (Cổng tùy biến)** | `http://14.161.34.37:8088` | NAT Port Forwarding qua Modem mạng Gigamall |
| **Domain Internet (HTTPS)** | `https://ocr.gigamall.com.vn` | Kết nối an toàn qua Cloudflare Tunnel / SSL Let's Encrypt |
| **Môi trường Dev (Mac Mini)**| `http://127.0.0.1:8000` | Môi trường thử nghiệm cục bộ |

---

## 2. QUY ĐỊNH CHUNG VỀ DỮ LIỆU & BẢO MẬT

1. **Định dạng ảnh hỗ trợ**: `image/jpeg` (`.jpg`, `.jpeg`), `image/png` (`.png`), `image/webp` (`.webp`).
2. **Dung lượng tệp tối đa**: `20 MB` / ảnh.
3. **Authentication (Bảo mật)**:
   * Header: `X-API-Key: <GIGAMALL_CRM_SECRET_KEY>` *(nếu môi trường yêu cầu khóa API)*.
4. **Chuẩn hóa số tiền (`bill_total`)**:
   * Luôn là **số nguyên dương (Integer)**, đơn vị VNĐ. Đã trừ toàn bộ voucher, giảm giá, điểm thưởng.
   * Ví dụ: Hóa đơn 150.000 đ thì giá trị trả về là `150000` (không có dấu chấm, phẩy hay chữ đ).

---

## 3. DANH SÁCH ENDPOINTS CHI TIẾT

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. POST /api/v1/extract-bill     : Bóc tách hóa đơn từ file ảnh (Core AI)   │
│ 2. GET  /api/bills/{bill_id}     : Tra cứu thông tin chi tiết & vết kiểm toán│
│ 3. POST /api/bills/{bill_id}/review : CRM xác nhận duyệt / từ chối hóa đơn  │
│ 4. PUT  /api/bills/{bill_id}/edit   : Hiệu chỉnh thông tin hóa đơn (Admin)  │
│ 5. GET  /api/outlets             : Lấy danh mục 81 cửa hàng chuẩn Gigamall  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### API 1: BÓC TÁCH HÓA ĐƠN BẰNG AI (EXTRACT BILL OCR)

Dùng khi Mobile App khách hàng tải ảnh lên, hoặc CRM Server 2 chuyển tiếp ảnh hóa đơn sang để AI nhận diện.

* **Phương thức**: `POST`
* **Đường dẫn**: `/api/v1/extract-bill`
* **Content-Type**: `multipart/form-data`

#### Tham số Request (Form Data):
| Tham số | Kiểu dữ liệu | Bắt buộc | Mô tả |
| :--- | :--- | :--- | :--- |
| `file` | Binary (File) | **Có** | Tệp ảnh hóa đơn chụp thực tế |
| `mem_id` | String | Không | Mã thành viên / Khách hàng tích điểm (nếu có) |
| `image_number` | String | Không | Mã giao dịch / Tên định danh ảnh do CRM quản lý |

#### Cấu trúc Response thành công (HTTP 200 OK):
```json
{
  "success": true,
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

#### Giải thích ý nghĩa các trường dữ liệu trả về:
| Trường | Kiểu | Mô tả nghiệp vụ cho CRM |
| :--- | :--- | :--- |
| `brand_name` | String | Thương hiệu bóc tách được (Highlands, Fahasa,...) |
| `outlet_name` | String | Tên gian hàng in trên hóa đơn giấy |
| **`outlet_number`** | String | **Mã cửa hàng CRM** (Đã tự động so khớp chuẩn với `master_outlets.json`) |
| `bill_number` | String | Mã số hóa đơn / Bill No |
| `bill_datetime` | String | Ngày giờ giao dịch chuẩn ISO (`YYYY-MM-DD HH:mm:ss`) |
| **`bill_total`** | Integer | **Số tiền thực thanh toán** để làm căn cứ tích điểm |
| **`is_valid_bill`**| Boolean| `true`: Hóa đơn hợp lệ; `false`: Ảnh mờ / ảnh rác / không phải hóa đơn |
| `match_score` | Float | Điểm khớp tên quán với CRM (0.0 đến 1.0; $\ge 0.6$ là khớp tin cậy) |
| `latency_seconds`| Float | Thời gian AI xử lý bóc tách (giây) |

#### Mã lỗi thường gặp:
* `400 Bad Request`: Ảnh không đúng định dạng hoặc tệp bị hỏng.
* `413 Payload Too Large`: Tệp ảnh vượt quá 20MB.
* `500 Internal Server Error`: Lỗi suy luận mô hình AI.

---

### API 2: LẤY CHI TIẾT HÓA ĐƠN & LỊCH SỬ KIỂM TOÁN (GET BILL & AUDIT)

Dùng cho CRM Admin hoặc Auditor mở chi tiết một hóa đơn để xem lại ảnh và toàn bộ lịch sử can thiệp.

* **Phương thức**: `GET`
* **Đường dẫn**: `/api/bills/{bill_id}`
* **Response (HTTP 200 OK)**:
```json
{
  "BillId": 105,
  "Filename": "10305_181026095239.png",
  "ImagePath": "TEST_IMAGES/10305_181026095239.png",
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

### API 3: PHÊ DUYỆT HOẶC TỪ CHỐI HÓA ĐƠN (SUBMIT REVIEW)

Dùng khi nhân viên CRM CSKH hoặc Admin bấm duyệt tích điểm hoặc từ chối trên hệ thống.

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

#### Response (HTTP 200 OK):
```json
{
  "success": true,
  "bill_id": 105,
  "status": "APPROVED"
}
```

---

### API 4: CHỈNH SỬA THÔNG TIN HÓA ĐƠN (INLINE CORRECTION)

Dùng khi Admin phát hiện AI đọc nhầm số tiền hoặc tên cửa hàng và muốn sửa lại.

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

#### Response (HTTP 200 OK):
```json
{
  "success": true,
  "bill_id": 105,
  "fields_changed": 2
}
```
*(Hệ thống sẽ tự động ghi vết thay đổi vào bảng `OcrBillAuditLogs` phục vụ kiểm toán).*

---

### API 5: LẤY DANH MỤC CỬA HÀNG CHUẨN (GET MASTER OUTLETS)

Dùng để CRM lấy danh sách 81 gian hàng chuẩn của Gigamall phục vụ dropdown autocomplete.

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

## 4. BẢNG ÁNH XẠ DỮ LIỆU VỚI CSDL CRM GIGAMALL

Bảng đối chiếu giữa các trường API và các cột trong bảng CSDL hiện hữu của Gigamall (`mssOCRTrialTrans` / `mssOCRTrans` / `OcrBills`):

| Trường trong API JSON | Cột CSDL CRM (`mssOCRTrialTrans` / `mssOCRTrans`) | Cột CSDL (`OcrBills`) | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- | :--- |
| `data.brand_name` | `BrandName` | `OcrBrand` | Tên thương hiệu AI đọc |
| `data.outlet_name` | `OutletName` | `OcrOutletName` | Tên cửa hàng AI đọc |
| `data.outlet_number` | `OutletNumber` | `OcrOutletNumber` | Mã cửa hàng chuẩn CRM |
| `data.bill_number` | `BillNumber` | `OcrBillNumber` | Số hóa đơn ban đầu |
| `data.bill_datetime` | `BillDateTime` | `OcrDateTime` | Ngày giờ giao dịch ban đầu |
| `data.bill_total` | `BillTotal` | `OcrTotal` | Tổng tiền AI đọc |
| **`final_total`** | **`BillTotalA`** | **`FinalTotal`** | **Số tiền CHÍNH THỨC tích điểm (Admin duyệt/sửa)** |
| **`final_outlet_number`** | **`OutletNumberA`** | **`FinalOutletNumber`**| **Mã cửa hàng CHÍNH THỨC sau duyệt** |
| **`final_bill_number`** | **`BillNumberA`** | **`FinalBillNumber`** | **Số hóa đơn CHÍNH THỨC sau duyệt** |
| **`status`** | `Reviewed`, `Approved` | `Status` | Trạng thái: `APPROVED` (1/1), `REJECTED` (1/0) |
| `actor` | `ReviewBy`, `ModifiedBy` | `ReviewedBy` | Tên nhân viên thao tác |
| `reject_reason` | `ReviewNotes` | `RejectReason` | Lý do từ chối nếu không duyệt |

---

## 5. MÃ NGUỒN MẪU TÍCH HỢP CHO ĐỘI NGŨ CRM

### 5.1. Ví dụ C# (.NET Core HttpClient trên Server 2)

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
    // Thay đổi URL tùy theo mạng nội bộ hoặc Public
    private const string OCR_API_URL = "http://192.168.2.4:8000/api/v1/extract-bill";

    public GigamallOcrClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.Timeout = TimeSpan.FromSeconds(30);
    }

    public async Task<OcrResponseDto> ExtractBillAsync(string imageFilePath, string memberId = "")
    {
        using var form = new MultipartFormDataContent();
        
        // 1. Đọc file ảnh
        byte[] imageBytes = await File.ReadAllBytesAsync(imageFilePath);
        var fileContent = new ByteArrayContent(imageBytes);
        fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse("image/jpeg");
        form.Add(fileContent, "file", Path.GetFileName(imageFilePath));

        // 2. Tham số bổ sung (nếu có)
        if (!string.IsNullOrEmpty(memberId))
        {
            form.Add(new StringContent(memberId), "mem_id");
        }

        // 3. Gửi request sang Server AI
        HttpResponseMessage response = await _httpClient.PostAsync(OCR_API_URL, form);
        response.EnsureSuccessStatusCode();

        string jsonResponse = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<OcrResponseDto>(jsonResponse, new JsonSerializerOptions 
        { 
            PropertyNameCaseInsensitive = true 
        });
    }
}

// DTO Models
public class OcrResponseDto
{
    public bool Success { get; set; }
    public double Latency_Seconds { get; set; }
    public BillDataDto Data { get; set; }
}

public class BillDataDto
{
    public string Brand_Name { get; set; }
    public string Outlet_Name { get; set; }
    public string Outlet_Number { get; set; }
    public string Bill_Number { get; set; }
    public string Bill_DateTime { get; set; }
    public long Bill_Total { get; set; }
    public bool Is_Valid_Bill { get; set; }
    public double Match_Score { get; set; }
}
```

---

### 5.2. Ví dụ cURL (Dùng kiểm tra nhanh bằng Command Line hoặc Postman)

```bash
# 1. Gọi bóc tách ảnh hóa đơn:
curl -X POST "http://192.168.2.4:8000/api/v1/extract-bill" \
     -H "accept: application/json" \
     -F "file=@/path/to/bill_sample.jpg"

# 2. Phê duyệt hóa đơn:
curl -X POST "http://192.168.2.4:8000/api/bills/105/review" \
     -H "Content-Type: application/json" \
     -d '{"status": "APPROVED", "actor": "crm_staff_01"}'

# 3. Chỉnh sửa thông tin hóa đơn:
curl -X PUT "http://192.168.2.4:8000/api/bills/105/edit" \
     -H "Content-Type: application/json" \
     -d '{"final_total": 250000, "final_outlet_number": "ADIDAS", "actor": "crm_staff_01", "note": "Sửa lại đúng giá niêm yết"}'
```

---

## 6. THÔNG TIN HỖ TRỢ KỸ THUẬT (CONTACT & SUPPORT)
* **Tài liệu Swagger / OpenAPI tương tác trực tiếp**: Mở trình duyệt tại `http://<SERVER_IP>:8000/docs` để thử nghiệm trực tiếp từng API với giao diện Swagger UI.
* **Đội ngũ phát triển AI**: Dự án R&D OCR Bill Gigamall.
