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

## 3. CÁC TÍNH NĂNG CHÍNH CỦA HỆ THỐNG

### 3.1. Soi & Đối soát chi tiết hóa đơn (Split Inspector Screen)
* **Màn hình chia đôi công thái học (Ergonomic Split Screen)**:
  - **Cửa sổ trái (Image Canvas)**: Trình xem ảnh hóa đơn chuẩn HD. Hỗ trợ phóng to (Zoom In/Out), xoay 90° (để xem hóa đơn chụp ngang/ngược) và kéo rê ảnh (Pan) mượt mà.
  - **Cửa sổ phải (Data Panel)**: Hiển thị song song **Kết quả AI đọc ban đầu** và **Ô dữ liệu thực tế** để người dùng đối chiếu tức thì mà không cần chuyển qua lại các tab.

### 3.2. Quản lý 2 tầng dữ liệu (Dual-layer Data Architecture)
Để phục vụ kiểm toán và đánh giá độ chính xác, hệ thống phân tách rõ 2 tầng dữ liệu trên từng hóa đơn:
1. **Dữ liệu AI đọc (OCR Original Data - Bất biến)**:
   - Tên gian hàng gốc trên bill (`OcrOutletRaw`) & Mã gian hàng nhận diện (`OcrOutletNumber`).
   - Độ tin cậy nhận diện gian hàng (`OcrMatchScore`: 0 - 100%).
   - Số hóa đơn (`OcrBillNumber`), Ngày giờ giao dịch (`OcrDateTime`), Số tiền thanh toán (`OcrTotal`).
   - Thời gian AI xử lý tính bằng giây (`OcrLatency`).
2. **Dữ liệu người dùng chốt (Final Approved Data)**:
   - Dữ liệu do AI đề xuất mặc định, nhưng cho phép người duyệt chỉnh sửa khi hóa đơn bị mờ, rách hoặc sai lệch.

### 3.3. Cơ chế chỉnh sửa trực tiếp (Inline Correction)
* Khi phát hiện số tiền, ngày giờ hoặc tên gian hàng chưa đúng:
  - Người dùng có thể nhấp trực tiếp vào ô dữ liệu để sửa.
  - Nhập **Ghi chú điều chỉnh (Auditor Note)** nêu rõ lý do sửa (ví dụ: *Khách thanh toán 560k nhưng bill in mờ số 0*).
  - Nhấn nút **"Lưu sửa đổi"**: Hệ thống sẽ tự động bật cảnh báo viền vàng **"Admin đã sửa dữ liệu khác kết quả AI đọc ban đầu"** để các cấp phê duyệt sau dễ dàng nhận biết.

### 3.4. Chế độ duyệt hóa đơn để chốt dữ liệu (Approval Workflow)
* **Phê duyệt [A] (Approve)**:
  - Chốt hóa đơn thành công và chuyển trạng thái sang `APPROVED`.
  - Dữ liệu `FinalTotal`, `FinalOutletNumber`, `FinalDateTime` được chốt chính thức để CRM cộng điểm/tích lũy cho hội viên.
* **Từ chối [R] (Reject)**:
  - Yêu cầu nhập lý do từ chối (Ví dụ: *Hóa đơn quá mờ không đọc được, Hóa đơn không thuộc trung tâm thương mại, v.v.*).
  - Hóa đơn chuyển trạng thái sang `REJECTED`.
* **Phím tắt tiện dụng (Keyboard Shortcuts)**:
  - Phím `A`: Phê duyệt nhanh.
  - Phím `R`: Mở bảng từ chối.
  - Phím `Mũi tên Trái / Phải`: Chuyển lùi / tiến giữa các hóa đơn kế tiếp.

### 3.5. Nhật ký kiểm toán toàn diện (Comprehensive Audit Trail)
* Mọi hành động can thiệp của con người đều được ghi lại vào bảng `OcrBillAuditLogs`:
  - **Ai làm? (Actor)**: Định danh người duyệt / hệ thống (VD: `CRM Admin`, `Kế toán 1`).
  - **Làm gì? (Action)**: Duyệt (`APPROVE`), Từ chối (`REJECT`), hoặc Sửa dữ liệu (`UPDATE_FIELD`).
  - **Chi tiết sửa đổi**: Ghi rõ trường bị sửa, Giá trị cũ (`OldValue`), Giá trị mới (`NewValue`).
  - **Lý do sửa**: Toàn bộ ghi chú điều chỉnh được lưu vết vĩnh viễn phục vụ thanh tra.
* **Tab "Nhật ký kiểm toán" trên giao diện**: Cho phép tra cứu toàn bộ dòng thời gian lịch sử của tất cả hóa đơn theo thời gian thực.

### 3.6. Bảng danh sách tổng hợp & Lọc thông minh (List & Filter)
* Thống kê trực quan số lượng: **Tổng số bill**, **Chờ duyệt (Pending)**, **Đã duyệt (Approved)**, **Từ chối (Rejected)** và **Đã sửa tay (Manual Edited)**.
* Bộ lọc theo trạng thái và thanh tìm kiếm tức thì theo mã hóa đơn, tên file hoặc tên gian hàng.

---

## 4. QUY TRÌNH THỰC HIỆN THỬ NGHIỆM (KỊCH BẢN POC)

Người dùng có thể thực hiện thử nghiệm theo 4 kịch bản sau:

### Kịch bản 1: Kiểm tra tốc độ đọc & Độ chính xác của AI
1. Truy cập vào Cổng duyệt: [http://14.161.34.37:8080/](http://14.161.34.37:8080/)
2. Duyệt qua các hóa đơn trong danh sách (sử dụng nút **Tiếp** hoặc phím mũi tên).
3. **Quan sát**:
   - Tốc độ hiển thị ảnh và độ trễ xử lý AI (`AI Latency`) ghi nhận trên từng hóa đơn.
   - Độ chính xác khi nhận diện: Tên gian hàng, Số hóa đơn, Ngày giờ và Tổng tiền thanh toán.

### Kịch bản 2: Phê duyệt nhanh hóa đơn đúng
1. Chọn một hóa đơn có trạng thái `CHỜ DUYỆT (PENDING)`.
2. Kiểm tra thông tin khớp với ảnh bên trái.
3. Nhấn nút xanh **"Phê duyệt [A]"** (hoặc nhấn phím `A`).
4. **Kết quả**: Huy hiệu trạng thái chuyển ngay sang **`APPROVED`** màu xanh lá; tổng số bill chờ duyệt tự động giảm 1.

### Kịch bản 3: Chỉnh sửa dữ liệu khi AI đọc thiếu/sai và Kiểm tra cảnh báo
1. Chọn một hóa đơn bất kỳ.
2. Thử thay đổi số tiền tại ô **"Số tiền thanh toán hợp lệ (VND)"** hoặc sửa **"Cửa hàng / Gian hàng"**.
3. Nhập lý do vào ô **"Ghi chú điều chỉnh"** (VD: *Khách hàng cung cấp bill bổ sung*).
4. Nhấn nút xanh dương **"Lưu sửa đổi"**.
5. **Kết quả**: 
   - Banner cảnh báo màu vàng xuất hiện: *"Admin đã sửa dữ liệu khác kết quả AI đọc ban đầu!"*.
   - Khung "Lịch sử kiểm toán của bill này" ở góc dưới ngay lập tức hiển thị bản ghi: `CRM Admin [UPDATE_FIELD] FinalTotal: Giá_trị_cũ ➔ Giá_trị_mới`.

### Kịch bản 4: Tra cứu vết kiểm toán dành cho Auditor / Kế toán
1. Nhấp chuột vào tab **"Nhật ký kiểm toán (Auditor)"** trên thanh điều hướng đầu trang.
2. **Quan sát**: Toàn bộ danh sách các thao tác duyệt, sửa trường dữ liệu, người sửa và thời gian thực hiện hiển thị chi tiết, minh bạch.

---

## 5. THÔNG TIN HỖ TRỢ KỸ THUẬT
* **Môi trường Database**: MS-SQL Server `CLMHQTEST` (toàn bộ dữ liệu thử nghiệm độc lập hoàn toàn với Production).
* **Đội hỗ trợ kỹ thuật**: Sẵn sàng giải đáp và tiếp nhận các yêu cầu điều chỉnh nghiệp vụ trong suốt quá trình UAT/POC.
