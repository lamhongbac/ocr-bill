# ĐẶC TẢ THIẾT KẾ KỸ THUẬT: MODULE THẨM ĐỊNH, HIỆU CHỈNH & PHÊ DUYỆT HÓA ĐƠN CRM
> **Tài liệu tham chiếu chuẩn cho đội ngũ phát triển CRM Gigamall**  
> **Dành cho:** CRM Solution Architect, Backend Engineers (.NET Core / SQL Server), Frontend Engineers (Web/Admin Portal), QA/QC Team  
> **Mục tiêu:** Tái cấu trúc (Refactor) tính năng Chỉnh sửa & Phê duyệt hóa đơn bên CRM theo đúng chuẩn kiến trúc và quy tắc nghiệp vụ đã chứng minh hiệu quả trên OCR Review Portal.

---

## 1. BỐI CẢNH & VẤN ĐỀ THỰC TRẠNG (PROBLEM STATEMENT)

### 1.1. Thực trạng & Rủi ro trong cơ chế cũ của CRM
Trước đây, quy trình duyệt và chỉnh sửa hóa đơn trên hệ thống CRM thường gặp các vấn đề nghiêm trọng:
1. **Thiếu cơ chế khóa trạng thái (No Immutability)**: Hóa đơn sau khi đã được nhân viên bấm "Duyệt" (tích điểm thành công) vẫn có thể bị mở ra sửa số tiền hoặc thông tin gian hàng. Điều này dẫn đến nguy cơ gian lận nội bộ hoặc sai lệch số liệu tài chính đối soát với đối tác gian hàng (Tenant Settlement).
2. **Ghi đè dữ liệu gốc (Data Overwrite)**: Khi nhân viên sửa lại số tiền hoặc tên quán, hệ thống ghi đè trực tiếp lên dữ liệu do AI bóc tách ban đầu. Hậu quả là không thể đo lường được tỷ lệ nhận diện chính xác của AI và không thể xác minh khiếu nại của khách hàng.
3. **Thiếu nhật ký kiểm toán cấp trường (No Field-Level Audit Trail)**: Chỉ ghi nhận chung chung "Hóa đơn đã được sửa bởi user A", không biết cụ thể đã sửa trường nào, giá trị cũ là bao nhiêu, giá trị mới là bao nhiêu và lý do sửa là gì.
4. **Xung đột thao tác đồng thời (Concurrency Conflicts)**: Khi hai nhân viên CSKH cùng mở một hóa đơn để duyệt, người lưu sau sẽ ghi đè lên thao tác của người trước mà không có cảnh báo.

### 1.2. Mục tiêu Chuẩn hóa
Tài liệu này đặc tả toàn bộ quy tắc nghiệp vụ, kiến trúc dữ liệu và trải nghiệm giao diện người dùng (UI/UX) đã được thiết kế và vận hành chuẩn mực trên hệ thống **OCR Review Portal**, làm căn cứ kỹ thuật để đội ngũ dev CRM tái triển khai module quản lý hóa đơn.

---

## 2. NĂM NGUYÊN TẮC CỐT LÕI (5 KEY ARCHITECTURAL PILLARS)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. TÍNH BẤT BIẾN SAU PHÊ DUYỆT: Duyệt rồi (hoặc Từ chối rồi) là KHÓA CỨNG   │
│ 2. DỮ LIỆU GIÁ TRỊ KÉP (DUAL-VALUE): Giữ nguyên AI Raw, chỉ sửa trường Final│
│ 3. KIỂM TOÁN CẤP TRƯỜNG: Lưu vết chi tiết từng thay đổi (Ai, Gì, Cũ, Mới)   │
│ 4. PHÒNG NGỪA XUNG ĐỘT ĐỒNG THỜI: Kiểm soát phiên làm việc bằng Concurrency │
│ 5. CHUẨN HÓA LÝ DO TỪ CHỐI: Bắt buộc chọn/nhập lý do từ chối rõ ràng       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### MẤU CHỐT 1: TÍNH BẤT BIẾN SAU PHÊ DUYỆT (IMMUTABILITY AFTER FINALIZATION)

> **Quy tắc vàng**: **Hóa đơn một khi đã `APPROVED` (hoặc `REJECTED`) là ĐÃ KHÓA (LOCKED) — Tuyệt đối không được phép chỉnh sửa!**

#### 1. Rationale (Lý do nghiệp vụ bắt buộc):
* Khi hóa đơn đạt trạng thái `APPROVED`, giao dịch tích điểm (Loyalty Points) đã được kích hoạt, điểm thưởng đã cộng vào ví khách hàng, và doanh thu đã ghi nhận vào báo cáo đối soát gian hàng.
* Nếu cho phép sửa sau khi duyệt:
  * Số tiền tích điểm sẽ không khớp với số tiền thực tế trên hóa đơn.
  * Nhân viên có thể gian lận bằng cách duyệt trước rồi sau đó nâng khống số tiền lên để trục lợi điểm thưởng.
* Tương tự, khi hóa đơn đã `REJECTED`, thông báo từ chối đã gửi cho khách hàng. Không được tự ý đổi sang thông tin khác trừ khi có quy trình Re-open đặc biệt.

#### 2. Triển khai Kỹ thuật Đa tầng (Defense in Depth):

##### Lớp 1: Giao diện Người dùng (Frontend UI/UX)
* Khi mở một hóa đơn có trạng thái `APPROVED` hoặc `REJECTED`:
  * **Vô hiệu hóa toàn bộ ô nhập liệu**: Thêm thuộc tính `disabled` / `readonly` cho tất cả các trường (`FinalOutletNumber`, `FinalOutletName`, `FinalTotal`, `FinalBillNumber`, `FinalDateTime`, `Note`).
  * **Ẩn các nút hành động duyệt/sửa**: Nút "✅ Phê duyệt", "❌ Từ chối", "💾 Lưu chỉnh sửa" phải bị ẩn hoàn toàn (`display: none`).
  * **Hiển thị Banner Khóa trực quan**:
    ```html
    <!-- Trạng thái APPROVED -->
    <div class="locked-banner active">
      🔒 HÓA ĐƠN ĐÃ DUYỆT BỞI <b>nguyenvana_cskh</b> VÀO LÚC 20/10/2026 15:07 — ĐÃ KHÓA DỮ LIỆU
    </div>

    <!-- Trạng thái REJECTED -->
    <div class="locked-banner active rejection-style">
      ⛔ HÓA ĐƠN ĐÃ TỪ CHỐI BỞI <b>tranthib_cskh</b> — LÝ DO: Hóa đơn quá hạn quy định 48h
    </div>
    ```

##### Lớp 2: Kiểm soát tại Backend API (Business Logic Layer)
* Không được tin tưởng vào Frontend. Backend **phải kiểm tra trạng thái hiện tại trong CSDL trước khi thực thi bất kỳ lệnh cập nhật nào**:
  ```csharp
  // C# .NET Core Implementation Pattern
  public async Task<UpdateResult> UpdateBillFieldsAsync(int billId, EditBillDto dto, string actor)
  {
      var currentBill = await _db.Bills.FindAsync(billId);
      if (currentBill == null)
          throw new NotFoundException($"Không tìm thấy hóa đơn #{billId}");

      // BẢO VỆ CHẶN SỬA KHI ĐÃ HOÀN TẤT
      if (currentBill.Status == "APPROVED" || currentBill.Status == "REJECTED")
      {
          throw new BusinessRuleException(
              $"Hóa đơn #{billId} đã ở trạng thái {currentBill.Status}. " +
              "Không được phép chỉnh sửa hóa đơn đã hoàn tất thẩm định!");
      }

      // Tiến hành cập nhật nếu trạng thái còn PENDING...
  }
  ```

##### Lớp 3: Ràng buộc Cơ sở Dữ liệu (Database Constraint / Trigger - Tùy chọn)
* Đội ngũ DBA có thể kích hoạt Trigger trên bảng `Bills` để từ chối lệnh `UPDATE` nếu bản ghi đã có `Status IN ('APPROVED', 'REJECTED')` và người gọi không phải `sa` (Super Admin).

---

### MẤU CHỐT 2: KIẾN TRÚC DỮ LIỆU GIÁ TRỊ KÉP (DUAL-VALUE PATTERN)

> **Quy tắc vàng**: **Tuyệt đối không ghi đè dữ liệu AI đọc ban đầu. Luôn duy trì 2 nhóm trường: `Ocr...` (Raw) và `Final...` (Actual).**

#### 1. Cấu trúc Cột đối chiếu:

| Thông tin nghiệp vụ | Cột Dữ liệu AI Raw (Bất biến) | Cột Dữ liệu Chính thức (Được sửa khi PENDING) | Ghi chú vận hành |
| :--- | :--- | :--- | :--- |
| **Tổng tiền thanh toán** | `OcrTotal` *(bigint)* | `FinalTotal` *(bigint)* | Điểm tích lũy tính trên `FinalTotal` |
| **Mã cửa hàng CRM** | `OcrOutletNumber` *(nvarchar)*| `FinalOutletNumber` *(nvarchar)* | Gian hàng tích điểm theo `FinalOutletNumber` |
| **Tên cửa hàng** | `OcrOutletName` *(nvarchar)* | `FinalOutletName` *(nvarchar)* | Hiển thị trên app người dùng |
| **Số hóa đơn (Bill No)** | `OcrBillNumber` *(nvarchar)* | `FinalBillNumber` *(nvarchar)* | Dùng chống trùng hóa đơn thanh toán |
| **Ngày giờ giao dịch** | `OcrDateTime` *(datetime)* | `FinalDateTime` *(datetime)* | Xác định tính hợp lệ thời gian (trong 48h) |
| **Cờ can thiệp người dùng**| - | `IsManualEdited` *(bit)* | Tự động bật `1` nếu có bất kỳ field nào bị sửa |

#### 2. Vòng đời dữ liệu (Lifecycle):
1. **Khi AI bóc tách xong**:
   * Hệ thống ghi nhận kết quả vào cả 2 nhóm trường: `OcrTotal = 560000` và khởi tạo `FinalTotal = 560000`.
   * Cờ `IsManualEdited = 0`.
2. **Khi nhân viên phát hiện sai và chỉnh sửa**:
   * Nhân viên sửa số tiền từ `560000` thành `500000`.
   * Hệ thống chỉ cập nhật: `FinalTotal = 500000`, `IsManualEdited = 1`.
   * Trường `OcrTotal` vẫn giữ nguyên là `560000`.
3. **Lợi ích to lớn**:
   * **Báo cáo chất lượng AI**: Ban Giám đốc và Data Scientist có thể chạy query đo lường chính xác tỷ lệ AI đọc đúng so với người sửa:
     $$\text{Tỷ lệ sửa tay} = \frac{\sum IsManualEdited = 1}{\text{Tổng hóa đơn}} \times 100\%$$
   * **Truy nguyên gốc**: Khi có nghi vấn nhân viên cố tình hạ/nâng khống tiền, luôn có số liệu `OcrTotal` làm bằng chứng đối chiếu.

---

### MẤU CHỐT 3: NHẬT KÝ KIỂM TOÁN CẤP TRƯỜNG (GRANULAR AUDIT TRAIL)

> **Quy tắc vàng**: **Mọi hành động can thiệp vào hóa đơn phải được ghi nhận chi tiết đến từng trường dữ liệu, không ghi chung chung.**

#### 1. Cấu trúc Bảng `OcrBillAuditLogs`:
```sql
CREATE TABLE OcrBillAuditLogs (
    AuditId     BIGINT IDENTITY(1,1) PRIMARY KEY,
    BillId      INT NOT NULL,
    Action      NVARCHAR(50) NOT NULL,   -- 'UPDATE_FIELD', 'APPROVE', 'REJECT', 'RE_OPEN'
    FieldName   NVARCHAR(50) NOT NULL,   -- 'FinalTotal', 'FinalOutletNumber', 'Status',...
    OldValue    NVARCHAR(MAX) NULL,      -- Giá trị trước khi sửa
    NewValue    NVARCHAR(MAX) NULL,      -- Giá trị sau khi sửa
    Actor       NVARCHAR(100) NOT NULL,  -- Username / Mã nhân viên thao tác
    Note        NVARCHAR(500) NULL,      -- Lý do can thiệp (ví dụ: 'Khách dùng voucher giấy 50k')
    CreatedAt   DATETIME NOT NULL DEFAULT GETDATE()
);
```

#### 2. Nguyên tắc Ghi Log:
* Nếu nhân viên mở hóa đơn và sửa cả **Tổng tiền** lẫn **Mã cửa hàng** trong cùng một lần lưu:
  * Hệ thống phải sinh ra **2 dòng bản ghi kiểm toán riêng biệt** (1 dòng cho `FinalTotal`, 1 dòng cho `FinalOutletNumber`).
* Nếu nhân viên bấm "Lưu" nhưng giá trị mới **trùng khớp với giá trị cũ**:
  * Hệ thống **không được sinh log rác** (so sánh `OldValue != NewValue` trước khi ghi).
* Khi duyệt:
  * Ghi bản ghi kiểm toán: `Action = 'APPROVE'`, `FieldName = 'Status'`, `OldValue = 'PENDING'`, `NewValue = 'APPROVED'`.

---

### MẤU CHỐT 4: KIỂM SOÁT XUNG ĐỘT ĐỒNG THỜI (CONCURRENCY CONTROL)

> **Quy tắc vàng**: **Ngăn chặn triệt để tình trạng 2 nhân viên CSKH cùng mở và duyệt 1 hóa đơn tại cùng một thời điểm.**

#### 1. Kịch bản Xung đột:
* Nhân viên A và Nhân viên B cùng mở Hóa đơn #105 (đang `PENDING`).
* Nhân viên A bấm duyệt (tích điểm).
* Nhân viên B không biết, bấm từ chối hoặc sửa số tiền.

#### 2. Giải pháp Triển khai (Optimistic Concurrency Control):
Khi thực hiện UPDATE trạng thái hoặc thông tin, câu lệnh SQL luôn có điều kiện kiểm tra trạng thái hoặc phiên bản:
```sql
-- Chỉ cập nhật nếu trạng thái vẫn còn đang là PENDING
UPDATE OcrBills 
SET Status = 'APPROVED', 
    ReviewedBy = @Actor, 
    ReviewedAt = GETDATE(),
    UpdatedAt = GETDATE()
WHERE BillId = @BillId 
  AND Status = 'PENDING';
```
* Nếu số dòng bị ảnh hưởng (`RowsAffected`) $= 0$:
  * Báo lỗi ngay cho Nhân viên B: *"Hóa đơn này vừa được xử lý bởi nhân viên khác. Vui lòng tải lại trang!"*
  * Không cho phép ghi đè.

---

### MẤU CHỐT 5: CHUẨN HÓA LÝ DO TỪ CHỐI (STRUCTURED REJECT REASONS)

> **Quy tắc vàng**: **Từ chối hóa đơn bắt buộc phải có lý do rõ ràng, dễ hiểu để giải thích cho khách hàng.**

#### 1. Danh mục Lý do Chuẩn hóa (Dropdown Suggestions):
* `"Hóa đơn bị mờ, mất góc, không đọc được số tiền"`
* `"Hóa đơn đã quá hạn quy định tích điểm (> 48 giờ)"`
* `"Hóa đơn trùng lặp với giao dịch đã tích điểm trước đó"`
* `"Ảnh chụp không phải là hóa đơn hợp lệ tại Gigamall"`
* `"Hóa đơn không có thông tin thanh toán hoàn tất"`
* `"Khác (Nhập lý do chi tiết thủ công)"`

#### 2. Ràng buộc Nghiệp vụ:
* Khi nhân viên bấm "❌ Từ chối [R]", hệ thống hiển thị Modal yêu cầu chọn lý do từ danh mục hoặc gõ nội dung cụ thể.
* **Không cho phép gửi lý do rỗng**. Lý do này sẽ được lưu vào cột `RejectReason` và hiển thị trên ứng dụng Mobile cho khách hàng đọc.

---

## 3. MÔ HÌNH TRẠNG THÁI NGHIỆP VỤ (STATE MACHINE)

```
             ┌─────────────────────────┐
             │       MỚI TẢI LÊN       │
             └────────────┬────────────┘
                          │
                          ▼
             ┌─────────────────────────┐
             │     PENDING (Chờ)       │◄────────────────────────┐
             └──────┬─────────────┬────┘                         │
                    │             │                              │
      Bấm Phê duyệt │             │ Bấm Từ chối                  │ Re-open (Chỉ Super Admin
      (Hợp lệ)      │             │ (Kèm lý do)                  │ kèm lý do kiểm toán)
                    ▼             ▼                              │
             ┌────────────┐ ┌────────────┐                       │
             │  APPROVED  │ │  REJECTED  │                       │
             │  (ĐÃ DUYỆT)│ │(ĐÃ TỪ CHỐI)│                       │
             └─────┬──────┘ └─────┬──────┘                       │
                   │              │                              │
                   ▼              ▼                              │
         [KHÓA CỨNG: BẤT BIẾN]    └──────────────────────────────┘
         (Không được sửa field)
```

### Bảng Ma trận Chuyển đổi Trạng thái (Transition Matrix):

| Trạng thái hiện tại | Thao tác yêu cầu | Trạng thái mới | Tính hợp lệ | Hành vi hệ thống |
| :---: | :---: | :---: | :---: | :--- |
| **`PENDING`** | Sửa các trường `Final...` | `PENDING` | ✅ **HỢP LỆ** | Cập nhật `Final...`, bật `IsManualEdited=1`, ghi Audit Log |
| **`PENDING`** | Phê duyệt | **`APPROVED`** | ✅ **HỢP LỆ** | Khóa dữ liệu, cộng điểm CRM, ghi Audit Log |
| **`PENDING`** | Từ chối | **`REJECTED`** | ✅ **HỢP LỆ** | Bắt buộc nhập lý do, khóa dữ liệu, ghi Audit Log |
| **`APPROVED`** | Sửa các trường `Final...` | - | ❌ **BỊ CHẶN** | **Trả mã lỗi HTTP 400 Bad Request ngay lập tức** |
| **`APPROVED`** | Bấm Duyệt lại | `APPROVED` | ⚠️ **IDEMPOTENT** | Giữ nguyên, không đổi dữ liệu, trả HTTP 200 OK |
| **`APPROVED`** | Bấm Từ chối | - | ❌ **BỊ CHẶN** | Không được đổi trạng thái sau khi đã duyệt |
| **`REJECTED`** | Sửa các trường `Final...` | - | ❌ **BỊ CHẶN** | **Trả mã lỗi HTTP 400 Bad Request ngay lập tức** |
| **`APPROVED` / `REJECTED`**| Mở khóa đặc biệt (Re-open)| `PENDING` | 🔒 **HẠN CHẾ** | Chỉ dành cho User có quyền `SuperAdmin`, bắt buộc nhập lý do vào Audit Log |

---

## 4. ĐẶC TẢ GIAO DIỆN NGƯỜI DÙNG (UI/UX BEST PRACTICES)

Hệ thống OCR Review Portal đã tối ưu trải nghiệm cho nhân viên CSKH/Kiểm toán viên đạt tốc độ duyệt trung bình **< 5 giây/hóa đơn**. Đội ngũ Frontend CRM cần tuân thủ các chuẩn UI/UX sau:

### 4.1. Bố cục Chia đôi Màn hình (Side-by-side Layout)
* **Bên trái (60% màn hình)**: Khu vực hiển thị ảnh hóa đơn độ nét cao (Canvas / SVG Image Container).
* **Bên phải (40% màn hình)**: Khu vực Form thẩm định và lịch sử kiểm toán.

### 4.2. Cơ chế Kính lúp (Magnifier Loupe) & Kéo ảnh (Pan & Zoom)
* Khách hàng chụp hóa đơn thường dài, chữ nhỏ và mờ.
* **Kính lúp (Loupe)**:
  * Khi rê chuột vào ảnh, xuất hiện thấu kính tròn phóng đại 2.5x để soi rõ các dòng chữ nhỏ (mã hóa đơn, ngày giờ, số tiền lẻ).
* **Kéo di chuyển ảnh (Interactive Pan)**:
  * Khi zoom to, cho phép nhấn giữ phím `Ctrl` + kéo chuột trái (hoặc bấm nút chức năng Drag) để trượt bill lên xuống, xem trọn vẹn từ đầu bill (Tên quán, Logo) đến chân bill (Tổng tiền, Mã VAT).

### 4.3. Cảnh báo Chênh lệch Trực quan (Visual Diff Alert)
* Khi nhân viên sửa ô `inp-total` sang một con số khác với `OcrTotal`:
  * Ô nhập liệu tự động đổi viền sang **màu cam đậm (Warning Highlight)**.
  * Hiển thị ngay bên dưới: `⚠️ Chênh lệch so với AI: AI đọc 560.000 đ vs Người sửa 500.000 đ`.
  * Giúp nhân viên chú ý xác nhận lại để không bấm nhầm thừa/thiếu số 0.

### 4.4. Tự động Định dạng Tiền tệ Việt Nam
* Ô nhập tiền phải tự động phân tách dấu chấm hàng nghìn khi gõ:
  * Gõ `150000` $\rightarrow$ Tự hiển thị `150.000 đ`.
  * Tránh để người dùng phải tự đếm số lượng số 0.

### 4.5. Phím tắt Nhanh (Keyboard Shortcuts)
* Nhân viên không cần dùng chuột vẫn có thể thao tác:
  * Phím `[A]`: Phê duyệt nhanh
  * Phím `[R]`: Mở modal từ chối
  * Phím `[S]`: Lưu chỉnh sửa
  * Phím `[→]` hoặc `[J]`: Xem hóa đơn kế tiếp
  * Phím `[←]` hoặc `[K]`: Xem hóa đơn trước đó
  * Phím `[Esc]`: Đóng cửa sổ chi tiết

---

## 5. MÃ NGUỒN MẪU TRIỂN KHAI CHO CRM (.NET CORE BACKEND)

Dưới đây là đoạn mã tham khảo chuẩn mẫu thiết kế (Design Pattern) dành cho kỹ sư Backend CRM:

### 5.1. Service Thẩm định & Kiểm soát Trạng thái (`BillReviewService.cs`)

```csharp
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;

public class BillReviewService : IBillReviewService
{
    private readonly CrmDbContext _context;

    public BillReviewService(CrmDbContext context)
    {
        _context = context;
    }

    /// <summary>
    /// Chỉnh sửa thông tin hóa đơn (Chỉ cho phép khi hóa đơn đang ở trạng thái PENDING)
    /// </summary>
    public async Task<int> EditBillFieldsAsync(int billId, EditBillRequestDto dto, string actor)
    {
        using var transaction = await _context.Database.BeginTransactionAsync();
        try
        {
            var bill = await _context.OcrBills.FirstOrDefaultAsync(b => b.BillId == billId);
            if (bill == null)
                throw new KeyNotFoundException($"Không tìm thấy hóa đơn #{billId}");

            // [ĐIỂM MẤU CHỐT]: BẢO VỆ CHẶN SỬA KHI ĐÃ DUYỆT HOẶC ĐÃ TỪ CHỐI
            if (bill.Status == "APPROVED" || bill.Status == "REJECTED")
            {
                throw new InvalidOperationException(
                    $"Hóa đơn #{billId} đã ở trạng thái {bill.Status}. " +
                    "Dữ liệu đã khóa vĩnh viễn, không được phép chỉnh sửa!");
            }

            var auditLogs = new List<OcrBillAuditLog>();
            var now = DateTime.UtcNow;

            // 1. So sánh và ghi nhận Tổng tiền
            if (dto.FinalTotal.HasValue && dto.FinalTotal.Value != bill.FinalTotal)
            {
                auditLogs.Add(new OcrBillAuditLog
                {
                    BillId = bill.BillId,
                    Action = "UPDATE_FIELD",
                    FieldName = "FinalTotal",
                    OldValue = bill.FinalTotal.ToString(),
                    NewValue = dto.FinalTotal.Value.ToString(),
                    Actor = actor,
                    Note = dto.Note,
                    CreatedAt = now
                });
                bill.FinalTotal = dto.FinalTotal.Value;
            }

            // 2. So sánh và ghi nhận Mã Gian hàng
            if (!string.IsNullOrEmpty(dto.FinalOutletNumber) && dto.FinalOutletNumber != bill.FinalOutletNumber)
            {
                auditLogs.Add(new OcrBillAuditLog
                {
                    BillId = bill.BillId,
                    Action = "UPDATE_FIELD",
                    FieldName = "FinalOutletNumber",
                    OldValue = bill.FinalOutletNumber,
                    NewValue = dto.FinalOutletNumber,
                    Actor = actor,
                    Note = dto.Note,
                    CreatedAt = now
                });
                bill.FinalOutletNumber = dto.FinalOutletNumber;
                bill.FinalOutletName = dto.FinalOutletName;
            }

            // 3. Nếu có thay đổi: Bật cờ IsManualEdited và lưu Audit Log
            if (auditLogs.Count > 0)
            {
                bill.IsManualEdited = true;
                bill.UpdatedAt = now;

                await _context.OcrBillAuditLogs.AddRangeAsync(auditLogs);
                await _context.SaveChangesAsync();
                await transaction.CommitAsync();
            }

            return auditLogs.Count;
        }
        catch
        {
            await transaction.RollbackAsync();
            throw;
        }
    }

    /// <summary>
    /// Phê duyệt hoặc Từ chối hóa đơn
    /// </summary>
    public async Task<bool> ReviewBillAsync(int billId, ReviewBillRequestDto dto, string actor)
    {
        using var transaction = await _context.Database.BeginTransactionAsync();
        try
        {
            var bill = await _context.OcrBills.FirstOrDefaultAsync(b => b.BillId == billId);
            if (bill == null)
                throw new KeyNotFoundException($"Không tìm thấy hóa đơn #{billId}");

            // [ĐIỂM MẤU CHỐT]: Không cho phép đổi trạng thái nếu đã hoàn tất
            if (bill.Status == "APPROVED" || bill.Status == "REJECTED")
            {
                if (bill.Status == dto.Status) return true; // Idempotent
                throw new InvalidOperationException($"Hóa đơn #{billId} đã được thẩm định ({bill.Status}). Không thể thay đổi trạng thái!");
            }

            var now = DateTime.UtcNow;
            string oldStatus = bill.Status;

            bill.Status = dto.Status.ToUpper();
            bill.ReviewedBy = actor;
            bill.ReviewedAt = now;
            bill.RejectReason = dto.Status == "REJECTED" ? dto.RejectReason : null;
            bill.UpdatedAt = now;

            // Ghi nhận Audit Log
            var log = new OcrBillAuditLog
            {
                BillId = bill.BillId,
                Action = dto.Status,
                FieldName = "Status",
                OldValue = oldStatus,
                NewValue = dto.Status,
                Actor = actor,
                Note = dto.RejectReason,
                CreatedAt = now
            };

            await _context.OcrBillAuditLogs.AddAsync(log);
            await _context.SaveChangesAsync();
            await transaction.CommitAsync();

            return true;
        }
        catch
        {
            await transaction.RollbackAsync();
            throw;
        }
    }
}
```

---

## 6. MA TRẬN KIỂM THỬ CHẤP NHẬN (ACCEPTANCE TEST MATRIX)

Đội ngũ QA/QC của CRM bắt buộc phải kiểm thử đạt 10 kịch bản sau trước khi nghiệm thu:

| STT | Kịch bản Kiểm thử | Thao tác thực hiện | Kết quả mong đợi |
| :---: | :--- | :--- | :--- |
| **TC1** | **Chặn sửa khi đã APPROVED** | Mở 1 hóa đơn đã `APPROVED`, cố tình dùng DevTools mở khóa input và gọi API PUT `/api/bills/{id}/edit` | Hệ thống chặn lại, trả về mã lỗi `HTTP 400 Bad Request` kèm thông báo *"Hóa đơn đã duyệt, không thể chỉnh sửa!"*. Dữ liệu trong DB không bị đổi. |
| **TC2** | **Chặn sửa khi đã REJECTED** | Gọi API PUT `/api/bills/{id}/edit` trên hóa đơn đã `REJECTED` | Hệ thống chặn lại với lỗi `HTTP 400 Bad Request`. |
| **TC3** | **Kiểm tra Giao diện Đã Duyệt** | Mở hóa đơn `APPROVED` trên màn hình Web CRM | Toàn bộ input bị disabled. Ẩn nút Phê duyệt / Từ chối. Hiển thị banner khóa màu xanh: *"🔒 Hóa đơn đã duyệt bởi..."*. |
| **TC4** | **Kiểm tra Giao diện Từ chối** | Mở hóa đơn `REJECTED` trên màn hình Web CRM | Toàn bộ input bị disabled. Hiển thị banner từ chối màu đỏ kèm nội dung lý do từ chối. |
| **TC5** | **Bảo tồn Dữ liệu AI Raw** | Đổi số tiền hóa đơn từ 500k thành 700k và lưu | Cột `FinalTotal` đổi thành 700k. Cột `OcrTotal` vẫn giữ nguyên 500k. Cột `IsManualEdited` chuyển thành `1`. |
| **TC6** | **Kiểm toán Chi tiết Cấp trường** | Sửa đồng thời số tiền và mã cửa hàng | Bảng `OcrBillAuditLogs` sinh ra chính xác 2 dòng bản ghi: 1 dòng cho `FinalTotal` và 1 dòng cho `FinalOutletNumber`, ghi đúng giá trị cũ và mới. |
| **TC7** | **Không sinh Log rác** | Bấm lưu khi không thay đổi bất kỳ trường nào | Hệ thống không sinh thêm bản ghi kiểm toán nào trong CSDL. |
| **TC8** | **Bắt buộc nhập Lý do Từ chối** | Bấm "Từ chối" nhưng để trống lý do | Modal hiển thị cảnh báo yêu cầu chọn lý do hoặc nhập nội dung, không cho phép xác nhận. |
| **TC9** | **Cảnh báo Chênh lệch Tiền** | Gõ số tiền khác với số tiền AI đọc | Ô nhập tiền đổi màu viền sang đỏ cam và hiển thị badge cảnh báo chênh lệch trực quan. |
| **TC10**| **Thử nghiệm Kính lúp & Kéo ảnh** | Rê chuột vào ảnh và kéo rê bằng `Ctrl` + chuột trái | Thấu kính phóng đại 2.5x hoạt động mượt mà, ảnh trượt lên xuống trơn tru giúp soi rõ mã số thuế và dòng tổng tiền. |

---

## 7. KẾT LUẬN & LIÊN HỆ HỖ TRỢ
* **Mã nguồn mẫu thực tế**: Đội ngũ CRM có thể tham khảo trực tiếp mã nguồn Frontend & Backend đang chạy ổn định tại kho mã nguồn OCR:
  * Backend API & State Machine: [`db.py`](file:///Volumes/ExternalSSD/ocr-bill/db.py#L340-L435) & [`app_review.py`](file:///Volumes/ExternalSSD/ocr-bill/app_review.py#L383-L424).
  * Frontend UI/UX & Kính lúp / Khóa form: [`app_review.py`](file:///Volumes/ExternalSSD/ocr-bill/app_review.py#L2140-L2260).
* **Môi trường Trực quan**: Truy cập Web Review Portal tại `http://14.161.34.37:8080/` để trải nghiệm trực tiếp quy trình duyệt và khóa dữ liệu thực tế.
