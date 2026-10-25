# CHUYÊN ĐỀ 5: CỔNG QUẢN TRỊ DUYỆT HÓA ĐƠN & VẾT KIỂM TOÁN CRM (WEB REVIEW & AUDIT PORTAL)

> **Mã chuyên đề**: `SPEC-05-REVIEW-PORTAL`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: Product Owner, QA / Business Analyst, CRM Auditor, Frontend / Fullstack Developer

---

## 1. TỔNG QUAN KIẾN TRÚC REVIEW & AUDIT

Ứng dụng Web Quản trị Review Hóa đơn (`app_review.py`) được xây dựng trên nền tảng **FastAPI** phục vụ trực tiếp 3 User Story (US 1, US 2, US 3) theo đúng yêu cầu kiểm soát gian lận và đối soát tài chính của Trung tâm Thương mại Gigamall.

* **URL truy cập nội bộ**: `http://localhost:8000` (Dev) hoặc `http://14.161.34.37:8080` (Pilot).
* **CSDL liên kết**: Bảng `OcrBills` và `OcrBillAuditLogs` trên MS-SQL Server.

---

## 2. CHI TIẾT 3 USER STORY NGHIỆP VỤ

### 2.1. US 1: Quy trình Phê duyệt Hóa đơn Tốc độ cao (Review Workflow)
* **Màn hình Split-Screen Soi ảnh**:
  * Bên trái: Khung hiển thị ảnh hóa đơn độ nét cao kèm bộ công cụ tương tác:
    * Zoom in / Zoom out / Reset tỉ lệ ảnh.
    * Xoay ảnh 90° từng chiều (`Rotate CW / CCW`) để đọc các hóa đơn bị nghiêng khi chụp.
  * Bên phải: Bảng thông tin bóc tách (Cửa hàng, Mã CRM, Thương hiệu, Số tiền, Số hóa đơn, Ngày giờ giao dịch).
* **Hệ thống Phím tắt (Keyboard Shortcuts)**:
  * `[A]`: Phê duyệt nhanh hóa đơn (`APPROVE`).
  * `[R]`: Từ chối hóa đơn (`REJECT`) $\rightarrow$ Mở popup chọn lý do (Ảnh mờ, Sai ngày, Hóa đơn không hợp lệ, Trùng lặp).
  * `[←] / [→]`: Chuyển qua lại giữa các hóa đơn trong danh sách.
* **Màn hình Quản lý Danh sách (Batch Table)**:
  * Bộ lọc đa chiều: Trạng thái (`PENDING`, `APPROVED`, `REJECTED`), Cửa hàng, Khoảng thời gian, Cờ sửa đổi thủ công (`IsManualEdited`).
  * Nút duyệt hàng loạt (Batch Approve) cho các bill có độ tin cậy AI cao.

### 2.2. US 2: Sửa đổi Trực tiếp & Chống Sai sót (Inline Correction & Guardrails)
* **Autocomplete Cửa hàng thông minh**:
  * Dropdown tìm kiếm tức thì theo thời gian thực nối với 193 cửa hàng trong `master_outlets.json`.
  * Hiển thị kèm vị trí mặt bằng (ví dụ: `Highlands Coffee - L1-02`).
* **Cảnh báo Sai lệch Số tiền (Amount Mismatch Warning)**:
  * Khi Admin sửa trường `bill_total` lệch so với kết quả AI ban đầu, hệ thống tự động bật nhãn cảnh báo màu vàng (*"⚠️ Số tiền sửa đổi lệch với AI bóc tách"*), yêu cầu xác nhận để tránh lỗi gõ nhầm chữ số 0.
* **Cờ đánh dấu can thiệp (`IsManualEdited`)**:
  * Mọi hóa đơn có chỉnh sửa của Admin tự động bật cờ `IsManualEdited = 1` phục vụ báo cáo đối soát tỷ lệ chính xác của AI.

### 2.3. US 3: Vết Kiểm toán Nghiêm ngặt (Audit Trail)
* Mọi hành động (duyệt, từ chối, sửa trường dữ liệu) được ghi tự động vào bảng `OcrBillAuditLogs`:
  ```sql
  INSERT INTO OcrBillAuditLogs (BillId, Action, FieldChanged, OldValue, NewValue, Actor, Note, CreatedAt)
  ```
* **Timeline trực quan**: Hiển thị dòng thời gian lịch sử sửa đổi ngay dưới chân màn hình của từng bill.
* **Tab Kiểm toán viên (Auditor View)**:
  * Tra cứu toàn bộ vết thao tác trong hệ thống theo nhân viên, thời gian, mã hóa đơn.
  * **Nút xuất Báo cáo CSV**: Tải toàn bộ dữ liệu kiểm toán ra file `.csv` phục vụ báo cáo tài chính hàng tháng.

---

## 3. KHỐI CÔNG CỤ DEBUG & GIÁM SÁT THUẬT TOÁN AI (AI INSPECTOR TOOLING)

Tích hợp trực tiếp trên giao diện dành cho Kỹ sư AI và Admin đánh giá chất lượng mô hình:
1. **Bảng Phân tích So khớp mờ (Fuzzy Matching Breakdown)**:
   * Hiển thị bảng **Top 3 ứng viên cửa hàng gần nhất** kèm % điểm số (ví dụ: Highlands: 95%, The Coffee House: 42%).
2. **Dữ liệu JSON gốc (Raw VLM Output)**:
   * Xem nguyên văn đoạn JSON mà mô hình Qwen2-VL sinh ra trước khi qua bộ chuẩn hóa.
3. **Đo đạc Độ trễ Xử lý (Latency Breakdown)**:
   * Hiển thị thời gian AI suy luận (Inference time) và thời gian xử lý ảnh (Preprocessing time).
