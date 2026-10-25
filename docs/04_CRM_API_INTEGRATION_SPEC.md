# CHUYÊN ĐỀ 4: ĐẶC TẢ KỸ THUẬT API TÍCH HỢP DÀNH CHO CRM & MOBILE (CRM API INTEGRATION SPEC)

> **Mã chuyên đề**: `SPEC-04-CRM-API`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: CRM Backend Developer, Mobile App Developer, Solution Architect, QA Engineer

---

## 1. TỔNG QUAN DANH SÁCH ENDPOINTS TÍCH HỢP

Máy chủ AI OCR cung cấp bộ API chuẩn RESTful phục vụ kết nối trực tiếp với CRM Gigamall và ứng dụng Mobile:

| Method | Endpoint | Định dạng Body | Mục đích & Nghiệp vụ | Độ trễ ước tính |
| :---: | :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/extract-bill` | `multipart/form-data` **HOẶC** `application/json` (Base64) | **Bóc tách tức thì (Real-time OCR)**: Trả về đầy đủ thông tin hóa đơn, tổng tiền, mã cửa hàng | **~3.5s** (GPU RTX 3060) |
| `POST` | `/api/v1/bills/upload` | `multipart/form-data` | **Fast Save**: Lưu ảnh tức thì xuống đĩa, trả mã `bill_id` ngay lập tức, AI bóc tách ngầm | **< 0.1s** |
| `POST` | `/api/v1/bills/upload-base64` | `application/json` (Base64) | **Fast Save qua Base64**: Dành cho client không gửi được form nhị phân | **< 0.1s** |
| `POST` | `/api/v1/bills/trigger-ocr` | `application/json` | **Kích hoạt quét theo lô**: Ra lệnh bóc tách lại danh sách các hóa đơn `PENDING` | Tùy số lượng |
| `POST` | `/api/v1/sync-outlets` | URL params / Query | **Đồng bộ danh mục CSDL**: Kéo danh sách cửa hàng mới nhất từ MS-SQL vào RAM AI | **~0.2s** |
| `GET`  | `/api/images/{filename}` | Query HTTP | Tải/Xem ảnh hóa đơn chất lượng cao phục vụ hiển thị trên Mobile/CRM | **< 0.05s** |

---

## 2. CHI TIẾT API CỐT LÕI: `POST /api/v1/extract-bill` (HỖ TRỢ KÉP MULTIPART & BASE64)

### 2.1. Hình thức 1: Multipart Form-Data (Khuyến nghị cho Mobile & Backend có stream)
* **URL**: `http://14.161.34.37:8080/api/v1/extract-bill`
* **Content-Type**: `multipart/form-data`
* **Headers**: `X-Duplicate-Action: warn` (hoặc `allow`, `reject`)
* **Tham số Form**:
  * `file` *(bắt buộc)*: Stream nhị phân tệp ảnh (`.png`, `.jpg`, `.jpeg`).
  * `mem_id` *(tùy chọn)*: Mã thành viên CRM (ví dụ: `"0901234567"` hoặc `"MEM_12345"`).
  * `image_number` *(tùy chọn)*: Tên định danh file ảnh phía CRM.
  * `duplicate_action` *(tùy chọn, mặc định `"warn"`)*:
    * `warn`: Bóc tách bình thường, trả kèm cờ cảnh báo `is_duplicate: true`.
    * `allow`: Cho phép upload lại bổ sung.
    * `reject`: Từ chối ngay, không chạy OCR, trả về HTTP 200 kèm `data: null`.

### 2.2. Hình thức 2: Application/JSON (Base64 Payload)
* **URL**: `http://14.161.34.37:8080/api/v1/extract-bill`
* **Content-Type**: `application/json`
* **Body JSON**:
  ```json
  {
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "mem_id": "0901234567",
    "image_number": "BILL_TEST_01",
    "duplicate_action": "warn"
  }
  ```

### 2.3. Cấu trúc Payload Phản hồi Chuẩn (Response Body)
```json
{
  "success": true,
  "bill_id": 180,
  "filename": "10852_100926222127.png",
  "image_url": "/api/images/10852_100926222127.png",
  "ocr_status": "SUCCESS",
  "data": {
    "brand_name": "COOP.XTRA",
    "outlet_name": "COOPXTRA",
    "outlet_number": "COOPXTRA",
    "resolved_outlet": "CO.OPXTRA",
    "match_score": 1.0,
    "confidence": 1.0,
    "bill_number": "261545",
    "bill_datetime": "2026-09-10 15:45:00",
    "bill_total": 204000,
    "is_valid_bill": true
  },
  "review_status": "PENDING",
  "is_duplicate": false,
  "action_taken": "WARNED",
  "latency_seconds": 3.52,
  "raw_output": "{\n  \"brand_name\": \"\",\n  \"outlet_name\": \"COOPXTRA\",\n  \"bill_number\": \"261545\",\n  \"bill_datetime\": \"2026-09-10 15:45:00\",\n  \"bill_total\": 204000,\n  \"is_valid_bill\": true\n}"
}
```

---

## 3. MÃ NGUỒN C# .NET MẪU CHUẨN DÀNH CHO ĐỘI NGŨ CRM (.NET CLIENT SAMPLE)

Mã nguồn C# .NET hoàn chỉnh được nhúng trực tiếp dưới đây để đội ngũ CRM tích hợp ngay mà không cần tải thêm tệp rời:

```csharp
using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace GigaMall.Crm.OcrIntegration
{
    public class OcrBillClient
    {
        private static readonly HttpClient _httpClient = new HttpClient
        {
            BaseAddress = new Uri("http://14.161.34.37:8080"),
            Timeout = TimeSpan.FromSeconds(60)
        };

        /// <summary>
        /// Bóc tách hóa đơn trực tiếp qua Multipart Form-Data (Khuyến nghị)
        /// </summary>
        public static async Task<ExtractBillResponse> ExtractBillAsync(
            string imageFilePath,
            string memId = null,
            string duplicateAction = "allow")
        {
            if (!File.Exists(imageFilePath))
                throw new FileNotFoundException("Không tìm thấy tệp ảnh hóa đơn:", imageFilePath);

            string fileName = Path.GetFileName(imageFilePath);
            string imageNumber = Path.GetFileNameWithoutExtension(imageFilePath);

            using (var form = new MultipartFormDataContent())
            {
                // Tên trường form data BẮT BUỘC phải đặt là "file" (chữ thường)
                byte[] fileBytes = await File.ReadAllBytesAsync(imageFilePath);
                var fileContent = new ByteArrayContent(fileBytes);
                fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse(GetMimeType(fileName));
                form.Add(fileContent, "file", fileName);

                if (!string.IsNullOrEmpty(memId))
                    form.Add(new StringContent(memId), "mem_id");

                form.Add(new StringContent(imageNumber), "image_number");
                form.Add(new StringContent(duplicateAction), "duplicate_action");

                HttpResponseMessage response = await _httpClient.PostAsync("/api/v1/extract-bill", form);
                string responseJson = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    throw new HttpRequestException(
                        $"OCR Server trả về lỗi HTTP {(int)response.StatusCode} ({response.ReasonPhrase}): {responseJson}");
                }

                var jsonOptions = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
                return JsonSerializer.Deserialize<ExtractBillResponse>(responseJson, jsonOptions);
            }
        }

        /// <summary>
        /// Bóc tách hóa đơn trực tiếp qua Chuỗi Base64 JSON
        /// </summary>
        public static async Task<ExtractBillResponse> ExtractBillBase64Async(
            string imageBase64String,
            string memId = null,
            string imageNumber = null,
            string duplicateAction = "allow")
        {
            var payload = new
            {
                image = imageBase64String,
                mem_id = memId,
                image_number = imageNumber,
                duplicate_action = duplicateAction
            };

            var content = new StringContent(
                JsonSerializer.Serialize(payload),
                System.Text.Encoding.UTF8,
                "application/json"
            );

            HttpResponseMessage response = await _httpClient.PostAsync("/api/v1/extract-bill", content);
            string responseJson = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
            {
                throw new HttpRequestException(
                    $"OCR Server trả về lỗi HTTP {(int)response.StatusCode} ({response.ReasonPhrase}): {responseJson}");
            }

            var jsonOptions = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
            return JsonSerializer.Deserialize<ExtractBillResponse>(responseJson, jsonOptions);
        }

        private static string GetMimeType(string fileName)
        {
            string ext = Path.GetExtension(fileName).ToLowerInvariant();
            return ext switch
            {
                ".png" => "image/png",
                ".jpg" or ".jpeg" => "image/jpeg",
                ".webp" => "image/webp",
                _ => "application/octet-stream"
            };
        }
    }

    public class ExtractBillResponse
    {
        [JsonPropertyName("success")]
        public bool Success { get; set; }

        [JsonPropertyName("bill_id")]
        public int BillId { get; set; }

        [JsonPropertyName("filename")]
        public string Filename { get; set; }

        [JsonPropertyName("is_duplicate")]
        public bool IsDuplicate { get; set; }

        [JsonPropertyName("duplicate_action")]
        public string DuplicateAction { get; set; }

        [JsonPropertyName("action_taken")]
        public string ActionTaken { get; set; }

        [JsonPropertyName("latency_seconds")]
        public double LatencySeconds { get; set; }

        [JsonPropertyName("data")]
        public ExtractedBillData Data { get; set; }

        [JsonPropertyName("raw_output")]
        public string RawOutput { get; set; }
    }

    public class ExtractedBillData
    {
        [JsonPropertyName("brand_name")]
        public string BrandName { get; set; }

        [JsonPropertyName("outlet_name")]
        public string OutletName { get; set; }

        [JsonPropertyName("outlet_number")]
        public string OutletNumber { get; set; }

        [JsonPropertyName("resolved_outlet")]
        public string ResolvedOutlet { get; set; }

        [JsonPropertyName("bill_number")]
        public string BillNumber { get; set; }

        [JsonPropertyName("bill_datetime")]
        public string BillDateTime { get; set; }

        [JsonPropertyName("bill_total")]
        public long BillTotal { get; set; }

        [JsonPropertyName("is_valid_bill")]
        public bool IsValidBill { get; set; }

        [JsonPropertyName("match_score")]
        public double MatchScore { get; set; }

        [JsonPropertyName("confidence")]
        public double Confidence { get; set; }
    }
}
```

---

## 4. BẢNG MÃ LỖI & XỬ LÝ SỰ CỐ (ERROR HANDLING)

| HTTP Status | Chi tiết lỗi | Nguyên nhân | Hướng dẫn khắc phục |
| :---: | :--- | :--- | :--- |
| `400 Bad Request` | `Thiếu dữ liệu ảnh` | Client không gửi trường `file` qua form hoặc không gửi `image` trong JSON | Kiểm tra đúng tên trường dữ liệu |
| `413 Payload Too Large` | `File quá lớn` | File ảnh vượt quá giới hạn Nginx (`client_max_body_size 25M`) | Nén ảnh xuống dưới 10MB trước khi gửi |
| `422 Unprocessable` | `Validation Error` | Dữ liệu sai định dạng Pydantic | Đối chiếu đúng schema định dạng tham số |
| `502 Bad Gateway` | `Nginx 502` | Dịch vụ `ocr-bill.service` đang khởi động lại hoặc nạp trọng số VRAM | Thử lại sau 5-10 giây |
