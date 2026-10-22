# TÀI LIỆU HƯỚNG DẪN THỬ NGHIỆM HỆ THỐNG (POC / UAT GUIDE)
## HỆ THỐNG AI OCR HÓA ĐƠN & DUYỆT KIỂM TOÁN TẬP TRUNG GIGAMALL

---

## 1. THÔNG TIN TRUY CẬP HỆ THỐNG THỬ NGHIỆM

* **Địa chỉ Cổng duyệt hóa đơn (Web Portal)**: [http://14.161.34.37:8080/](http://14.161.34.37:8080/)
* **Tài liệu API tích hợp dành cho đội CRM (Swagger)**: [http://14.161.34.37:8080/docs](http://14.161.34.37:8080/docs)
* **Môi trường Cơ sở dữ liệu thử nghiệm**: `CLMHQTEST` (MS-SQL Server 2012)
* **Đối tượng sử dụng**: CRM Admin, Kế toán / Kiểm toán viên (Auditor), Đội ngũ kỹ thuật CRM.

---

## 2. CÁC THÔNG SỐ KỸ THUẬT NỔI BẬT (SYSTEM SPECIFICATIONS)

| Tiêu chí | Thông số kỹ thuật / Thực tế ghi nhận |
| :--- | :--- |
| **Mô hình AI thị giác** | Mô hình Vision-Language chuyên biệt, tối ưu hóa đọc hóa đơn tiếng Việt & nhiệt mờ |
| **Tốc độ xử lý OCR (AI Latency)** | **0.8 giây – 1.8 giây / hóa đơn** (chạy trực tiếp trên phần cứng GPU chuyên dụng) |
| **Độ trễ phản hồi Web (UI Latency)** | **< 50ms** cho các thao tác chuyển hóa đơn, zoom xoay ảnh, duyệt hoặc sửa dữ liệu |
| **Độ phủ danh mục gian hàng** | Đồng bộ tự động thời gian thực từ 2 bảng `G_Outlet` và `G_Brand` của GigaMall |
| **Thuật toán khớp gian hàng** | Fuzzy Matching kết hợp Levenshtein & Token Set Ratio (đạt độ chính xác cao dù hóa đơn viết tắt) |
| **Bảo toàn dữ liệu đối chứng** | **100% Bất biến (Immutable)** – Kết quả gốc do AI đọc được lưu riêng, không bị ghi đè |
| **Khả năng tiếp nhận hóa đơn** | Hỗ trợ 2 phương thức: Upload file trực tiếp (Multipart) hoặc đẩy chuỗi Base64 qua REST API |

---

## 3. QUY TRÌNH DUYỆT & KIẾN TRÚC DỮ LIỆU ĐỐI SOÁT (REVIEW WORKFLOW & DATA MODEL)

### 3.1. Phân định rõ 3 tầng dữ liệu: AI Data, Admin Data & Final Data (Cơ chế Coalesce)

Để phục vụ công tác thanh tra, kiểm toán (Auditing) và ngăn ngừa thất thoát dữ liệu, hệ thống tách biệt hoàn toàn giữa số liệu AI bóc tách và dữ liệu do con người hiệu chỉnh:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. AI DATA (BẤT BIẾN)        │ 2. ADMIN DATA (MẶC ĐỊNH ĐỂ TRỐNG) │ 3. FINAL DATA (KẾT QUẢ CUỐI) │
├──────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ • OcrOutletName              │ • AdminOutletName (Để trống)      │ = COALESCE(Admin, AI)        │
│ • OcrBrand                   │ • AdminBrand (Để trống)           │ Có sửa ➔ Lấy Admin          │
│ • OcrBillNumber              │ • AdminBillNumber (Để trống)      │ Không sửa ➔ Lấy AI           │
│ • OcrDateTime                │ • AdminDateTime (Để trống)        │                              │
│ • OcrTotal                   │ • AdminTotal (Để trống)           │                              │
└──────────────────────────────┴───────────────────────────────────┴──────────────────────────────┘
```

1. **AI Data (Dữ liệu AI bóc tách ban đầu - Bất biến / Immutable)**:
   - Các trường dữ liệu: `OcrOutletName`, `OcrBrand`, `OcrBillNumber`, `OcrDateTime`, `OcrTotal`, `OcrLatency`.
   - **Đặc tính**: Được lưu trữ nguyên bản và vĩnh viễn vào cơ sở dữ liệu ngay khi mô hình AI OCR xử lý xong ảnh bill.
   - **Quy tắc**: Tuyệt đối **không bị ghi đè, không bị xóa** bởi bất kỳ thao tác nào của người dùng. Đây là thước đo đối chứng độc lập để đo lường độ chính xác của AI và phục vụ kiểm toán đối soát với gian hàng.

2. **Admin Data (Dữ liệu Admin điều chỉnh - Mặc định để trống / Nullable)**:
   - Các trường dữ liệu: `AdminOutletName`, `AdminBrand`, `AdminBillNumber`, `AdminDateTime`, `AdminTotal`.
   - **Đặc tính**: Trên giao diện duyệt, các ô nhập liệu của Admin **mặc định để trống hoàn toàn (Empty/Placeholder)**.
   - **Quy tắc**:
     - Nếu AI đã đọc đúng 100%, Admin **không cần làm gì cả** (giữ nguyên để trống).
     - Admin chỉ nhập số liệu vào ô của trường nào mà AI đọc sai hoặc thiếu (Ví dụ: AI đọc thiếu số 0 ở tiền, hoặc tên quán viết tắt chưa đủ).
     - Hệ thống **tuyệt đối không tự ý sao chép dữ liệu AI sang cột Admin**, đảm bảo trong database trường nào Admin không sửa thì giá trị là `NULL`.

3. **Final Data (Số liệu chốt cuối cùng - Tính theo công thức Coalesce)**:
   - **Quy tắc cốt lõi**:
     > *`💡 Nếu Admin field để trống thì số liệu cuối cùng theo AI field, nếu Admin nhập thì số liệu cuối cùng theo Admin.`*
   - **Công thức SQL Coalesce**:
     ```sql
     FinalOutletName = COALESCE(AdminOutletName, OcrOutletName)
     FinalBrand      = COALESCE(AdminBrand, OcrBrand)
     FinalBillNumber = COALESCE(AdminBillNumber, OcrBillNumber)
     FinalDateTime   = COALESCE(AdminDateTime, OcrDateTime)
     FinalTotal      = COALESCE(AdminTotal, OcrTotal)
     ```
   - Dữ liệu `Final...` chính là căn cứ pháp lý và tài chính dùng để tích điểm thành viên, kết toán doanh thu gian hàng trên hệ thống CRM.

---

### 3.2. Vòng đời trạng thái duyệt hóa đơn (Review Status Lifecycle)

Mỗi hóa đơn trong hệ thống trải qua một chu trình kiểm soát trạng thái nghiêm ngặt theo mô hình State Machine:

```
                  ┌────────────────────────────────────────┐
                  │          ẢNH HÓA ĐƠN TẢI LÊN           │
                  └───────────────────┬────────────────────┘
                                      │ AI OCR xử lý (0.8s - 1.8s)
                                      ▼
                  ┌────────────────────────────────────────┐
                  │          CHỜ DUYỆT (PENDING)           │
                  │  (Admin được soi ảnh, sửa ô Admin)     │
                  └───────────┬────────────────┬───────────┘
                              │                │
            Nhấn [Phê duyệt]  │                │ Nhấn [Từ chối]
            (Bill hợp lệ)     │                │ (Kèm lý do bắt buộc)
                              ▼                ▼
                  ┌────────────────┐      ┌────────────────┐
                  │    APPROVED    │      │    REJECTED    │
                  │  (ĐÃ PHÊ DUYỆT)│      │  (ĐÃ TỪ CHỐI)  │
                  └───────┬────────┘      └───────┬────────┘
                          │                       │
                          └───────────┬───────────┘
                                      ▼
                       🔒 [KHÓA DỮ LIỆU CỨNG 100%]
                       (Khóa ô nhập liệu, ẩn nút duyệt,
                        chặn cập nhật tại API Backend)
```

1. **Trạng thái `PENDING` (Chờ duyệt)**:
   - Trạng thái mặc định sau khi AI OCR xong hóa đơn.
   - Cho phép Auditor/Admin xem ảnh phóng to, xoay ảnh, kiểm tra thông tin.
   - Cho phép nhập dữ liệu điều chỉnh vào các ô Admin và bấm **"Lưu thay đổi"**.
   - Chưa tích điểm CRM cho khách hàng.

2. **Trạng thái `APPROVED` (Đã phê duyệt - Chốt hợp lệ)**:
   - Kích hoạt khi người duyệt nhấn nút xanh **"Phê duyệt [A]"** (hoặc phím tắt `A`).
   - Hệ thống xác nhận số liệu `Final...` là hợp lệ, kích hoạt cộng điểm thưởng CRM cho hội viên.
   - **Cơ chế Khóa cứng (Immutability)**: Ngay lập tức vô hiệu hóa toàn bộ ô nhập liệu, ẩn nút duyệt/sửa. Backend API từ chối mọi yêu cầu chỉnh sửa tiếp theo (HTTP 400). Ngăn ngừa triệt để nguy cơ nhân viên gian lận hoặc sửa đổi số liệu sau khi đã duyệt.

3. **Trạng thái `REJECTED` (Đã từ chối - Không hợp lệ)**:
   - Kích hoạt khi người duyệt nhấn nút đỏ **"Từ chối [R]"** (hoặc phím tắt `R`).
   - **Bắt buộc nhập lý do từ chối**: Người duyệt phải chọn lý do chuẩn hóa từ danh mục gợi ý (hóa đơn mờ, quá hạn 48h, trùng lặp...) hoặc tự nhập chi tiết. Không cho phép gửi lý do rỗng.
   - Dữ liệu hóa đơn chuyển sang `REJECTED` và cũng được **Khóa cứng**. Lý do từ chối được lưu trữ và đồng bộ về ứng dụng khách hàng để phản hồi minh bạch.

4. **Cờ ghi nhận can thiệp thủ công (`IsManualEdited`)**:
   - `IsManualEdited = 0`: Hóa đơn được duyệt dựa trên 100% số liệu do AI bóc tách tự động (Admin không nhập bất kỳ trường nào).
   - `IsManualEdited = 1`: Hóa đơn có ít nhất một trường dữ liệu do Admin can thiệp điều chỉnh (`Admin... IS NOT NULL`).

---

### 3.3. Quy trình 4 bước thẩm định hóa đơn chi tiết trên Web Portal

```
[Bước 1: Soi ảnh] ➔ [Bước 2: Đối chiếu AI Data] ➔ [Bước 3: Nhập Admin Data (nếu sai)] ➔ [Bước 4: Phê duyệt / Từ chối]
```

* **Bước 1: Soi & kiểm tra hóa đơn (Cửa sổ bên trái)**:
  - Rê chuột vào ảnh để kích hoạt **Kính lúp phóng đại (Loupe)** soi rõ số tiền, ngày giờ, số hóa đơn in nhỏ.
  - Sử dụng các nút công cụ: Phóng to (+), Thu nhỏ (-), Xoay 90° (nếu bill chụp ngược), hoặc giữ `Ctrl` + rê chuột để kéo trượt ảnh (Pan).
* **Bước 2: Đối chiếu kết quả AI đọc (Cột AI Data)**:
  - Xem các thông tin do AI bóc tách: Cửa hàng (`OcrOutletName`), Thương hiệu (`OcrBrand`), Số hóa đơn (`OcrBillNumber`), Thời gian (`OcrDateTime`), Số tiền (`OcrTotal`).
  - Kiểm tra điểm tin cậy nhận diện gian hàng (`Match Score %`).
* **Bước 3: Điều chỉnh số liệu (Cột Admin Data - nếu có sai lệch)**:
  - Nếu AI đọc chính xác: **Để trống toàn bộ ô Admin**, chuyển thẳng sang Bước 4.
  - Nếu AI đọc sai/thiếu trường nào: Nhấp vào ô tương ứng ở cột **"Admin điều chỉnh"** và nhập giá trị đúng.
  - Nhập lý do vào ô **"Lý do điều chỉnh (Auditor Note)"** (ví dụ: *Bill mờ số 0, khách thanh toán 560.000đ*).
  - Nhấn nút **"💾 Lưu thay đổi"**: Hệ thống hiển thị Popup Modal xác nhận lưu thành công, thông báo rõ các trường vừa được cập nhật và ghi nhận vết kiểm toán.
* **Bước 4: Quyết định Phê duyệt hoặc Từ chối**:
  - Nếu hóa đơn hợp lệ: Nhấn **"✅ Phê duyệt [A]"**. Hóa đơn chuyển sang `APPROVED`, hiển thị banner khóa thành công.
  - Nếu hóa đơn sai quy định: Nhấn **"❌ Từ chối [R]"**, chọn hoặc gõ lý do từ chối ➔ Xác nhận.

---

### 3.4. Nhật ký kiểm toán toàn diện cấp trường (Field-level Audit Trail)

* Mọi hành động can thiệp của con người đều được ghi lại vào bảng `OcrBillAuditLogs`:
  - **Ai làm? (Actor)**: Định danh người duyệt / hệ thống (VD: `CRM Admin`, `Kế toán 1`).
  - **Làm gì? (Action)**: Duyệt (`APPROVE`), Từ chối (`REJECT`), hoặc Sửa dữ liệu (`UPDATE_FIELD`).
  - **Trường thay đổi (FieldName)**: Ghi rõ trường cụ thể (`AdminTotal`, `AdminOutletName`, `Status`...).
  - **Chi tiết sửa đổi**: Ghi nhận chính xác Giá trị cũ (`OldValue`) và Giá trị mới (`NewValue`).
  - **Lý do sửa**: Toàn bộ ghi chú điều chỉnh được lưu vết vĩnh viễn phục vụ thanh tra nội bộ và kiểm toán tài chính.
* **Tab "Nhật ký kiểm toán" trên giao diện**: Cho phép tra cứu toàn bộ dòng thời gian lịch sử của tất cả hóa đơn theo thời gian thực.

---

### 3.5. Bảng danh sách tổng hợp, Phân trang & Lọc thông minh (List & Filter)
* **Thống kê trực quan số lượng thẻ KPI**: Tổng số bill, Chờ duyệt (`PENDING`), Đã duyệt (`APPROVED`), Từ chối (`REJECTED`) và Đã sửa tay (`IsManualEdited = 1`).
* **Thanh phân trang linh hoạt**: Lựa chọn 10, 20, 50 hoặc 100 hóa đơn mỗi trang; nút chuyển trang Trước / Tiếp và nhảy trang tức thì.
* **Tìm kiếm đa năng**: Lọc theo trạng thái và tìm kiếm nhanh theo mã hóa đơn, tên file ảnh hoặc tên gian hàng.

---

## 4. QUY TRÌNH THỰC HIỆN THỬ NGHIỆM (KỊCH BẢN POC / UAT)

Người dùng và kiểm toán viên có thể thực hiện kiểm thử theo 4 kịch bản chuẩn sau:

### Kịch bản 1: Phê duyệt nhanh hóa đơn AI đọc đúng 100% (Không cần can thiệp)
1. Chọn một hóa đơn có trạng thái `CHỜ DUYỆT (PENDING)` trong danh sách.
2. Kiểm tra các trường ở cột **AI Data** khớp hoàn toàn với ảnh hóa đơn bên trái.
3. Các ô ở cột **Admin Data** giữ nguyên để trống.
4. Nhấn nút xanh **"Phê duyệt [A]"** (hoặc nhấn phím `A`).
5. **Kết quả**:
   - Trạng thái chuyển ngay sang **`APPROVED`** màu xanh lá.
   - Banner khóa dữ liệu xuất hiện: *"🔒 Hóa đơn đã duyệt bởi CRM Admin vào lúc... — ĐÃ KHÓA DỮ LIỆU"*.
   - Toàn bộ ô nhập liệu và nút duyệt/sửa tự động khóa, ngăn chặn mọi thay đổi tiếp theo.
   - Cột `IsManualEdited = 0` (hóa đơn duyệt tự động hoàn toàn).

### Kịch bản 2: Hiệu chỉnh khi AI đọc thiếu/sai tiền và Lưu Audit Log
1. Chọn một hóa đơn `PENDING` có số tiền AI nhận diện chưa chính xác (ví dụ AI đọc 50.000đ nhưng bill thực tế là 500.000đ).
2. Tại cột **"Admin điều chỉnh"**, nhấp vào ô **"Số tiền (VND)"** và gõ `500000` (hệ thống tự định dạng `500.000 đ`).
3. Các trường khác (Cửa hàng, Số bill, Giờ) nếu đúng thì **để trống hoàn toàn**.
4. Nhập lý do vào ô **"Lý do điều chỉnh (Auditor Note)"**: *"Hóa đơn in mờ số 0, khách thanh toán 500k"*.
5. Nhấn nút **"💾 Lưu thay đổi"**.
6. **Kết quả**:
   - Popup Modal thông báo lưu thành công hiển thị rõ ràng thông tin trường vừa sửa và lý do điều chỉnh.
   - Bảng **"Lịch sử kiểm toán của bill này"** ở góc dưới hiển thị bản ghi: `CRM Admin [UPDATE_FIELD] AdminTotal: NULL ➔ 500000`.
   - Cột `IsManualEdited` tự động chuyển thành `1`.
7. Nhấn **"Phê duyệt [A]"** để chốt hóa đơn.

### Kịch bản 3: Từ chối hóa đơn không hợp lệ
1. Chọn một hóa đơn không đủ điều kiện (hóa đơn mờ mất thông tin, hóa đơn ngoài TTTM, bill quá 48h).
2. Nhấn nút đỏ **"Từ chối [R]"** (hoặc phím tắt `R`).
3. Hộp thoại Từ chối xuất hiện: Chọn một lý do từ danh mục chuẩn hóa (hoặc chọn "Khác" và gõ chi tiết).
4. Bấm **"Xác nhận từ chối"**.
5. **Kết quả**:
   - Trạng thái bill chuyển sang **`REJECTED`** màu đỏ.
   - Banner từ chối xuất hiện kèm nội dung lý do từ chối.
   - Form bị khóa cứng, không thể sửa hay duyệt lại.

### Kịch bản 4: Kiểm tra tính bảo toàn dữ liệu & Tra cứu vết kiểm toán (Dành cho Auditor)
1. Mở bất kỳ hóa đơn nào đã được Admin chỉnh sửa ở Kịch bản 2.
2. **Quan sát**: Cột **AI Data** vẫn giữ nguyên giá trị gốc ban đầu (`OcrTotal = 50000`), cột **Admin Data** lưu `500000`. Dữ liệu gốc của AI không bao giờ bị mất đi.
3. Chuyển sang tab **"Nhật ký kiểm toán"** trên thanh điều hướng đầu trang để tra cứu toàn bộ dòng lịch sử thao tác của các nhân viên.

---

## 5. THÔNG TIN HỖ TRỢ KỸ THUẬT
* **Môi trường Database**: MS-SQL Server `CLMHQTEST` (toàn bộ dữ liệu thử nghiệm độc lập hoàn toàn với Production).
* **Đặc tả kỹ thuật dành cho đội lập trình CRM**: Tham khảo tài liệu [CRM_BILL_REVIEW_AND_AUDIT_TECH_SPEC.md](file:///Volumes/ExternalSSD/ocr-bill/CRM_BILL_REVIEW_AND_AUDIT_TECH_SPEC.md).
* **Đội hỗ trợ kỹ thuật**: Sẵn sàng giải đáp và tiếp nhận các yêu cầu điều chỉnh nghiệp vụ trong suốt quá trình UAT/POC.
