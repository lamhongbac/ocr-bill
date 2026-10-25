# BÁO CÁO TIẾN ĐỘ & TỔNG KẾT THEO PHIÊN (DAILY & SESSION PROGRESS REPORT)
## DỰ ÁN: HỆ THỐNG AI OCR HÓA ĐƠN & DUYỆT KIỂM TOÁN TẬP TRUNG GIGAMALL

---

> [!NOTE]
> **Quy tắc quản lý báo cáo phiên làm việc (Session Report Rule):**
> * Tệp `DAILY_REPORT.md` là tệp báo cáo duy nhất tại thư mục gốc dùng để cập nhật tiến độ vào cuối mỗi ngày / cuối mỗi phiên làm việc (Session).
> * Mỗi khi hoàn thành một phiên làm việc, kỹ sư ghi nhận một khối `## Session: Ngày DD/MM/YYYY` ở đầu phần nội dung phiên, bao gồm: Mục tiêu, Chi tiết kỹ thuật & Hạng mục hoàn thành, Thông số hiệu năng/Môi trường, và Kế hoạch phiên tiếp theo.
> * Các tài liệu chi tiết, tài liệu kiến trúc, hướng dẫn triển khai và đặc tả API được lưu trữ trong thư mục `docs/`.

---

## Session: Ngày 25/10/2026 – Tối ưu Pilot GPU RTX 3060 (Qwen2-VL-7B NF4), Dual Mode API, Chuẩn hóa Tiền tệ VNĐ & Tái cấu trúc Tài liệu

### 1. Tổng quan Mục tiêu & Kết quả Đạt được
Trong phiên làm việc ngày 25/10/2026, toàn bộ các mục tiêu tối ưu hóa hạ tầng máy chủ Pilot, nâng cấp mô hình AI, mở rộng API cho đội CRM và tái cấu trúc hệ thống tài liệu đã hoàn thành vượt chỉ tiêu:

| STT | Hạng mục công việc | Chi tiết kỹ thuật & Giải pháp triển khai | Trạng thái |
| :---: | :--- | :--- | :---: |
| **1** | **Nâng cấp AI Model trên Pilot (RTX 3060 12GB)** | • Khảo sát năng lực phần cứng máy chủ Pilot (Intel Core i5-10400F, 16GB RAM, GPU NVIDIA GeForce RTX 3060 12GB VRAM).<br>• Chuyển đổi mô hình từ 2B sang **Qwen2-VL-7B-Instruct** lượng tử hóa **NF4 (BitsAndBytes 4-bit)**.<br>• Mức chiếm dụng VRAM: ~5.8GB / 12GB VRAM (an toàn tuyệt đối, không tràn bộ nhớ).<br>• Tốc độ trích xuất hóa đơn đạt **~3.5s / bill** (nhanh hơn gấp đôi so với Mac Mini M4 ~7.7s). | ✅ **HOÀN THÀNH** |
| **2** | **Khắc phục lỗi Kết quả Rỗng (Empty AI Output)** | • Phát hiện nguyên nhân kết quả rỗng do danh mục cửa hàng cũ `master_outlets.json` trên Pilot bị thiếu dữ liệu đối soát.<br>• Xuất và đồng bộ đầy đủ **193 outlets** từ bảng `Outlet_Infor` của MS-SQL Server `CLMHQ4GIGA`.<br>• Sau khi đồng bộ, AI bóc tách chính xác 100% các hóa đơn Highlands Coffee, Phúc Long, Poseidon, CGV... | ✅ **HOÀN THÀNH** |
| **3** | **Chuẩn hóa Xử lý Tiền tệ VNĐ (Currency Formatting Rules)** | • Cập nhật `EXTRACTION_PROMPT` trong `ocr_engine.py`: Quy định rõ dấu chấm/phẩy ngăn cách hàng nghìn (ví dụ `204.000` $\rightarrow$ `204000`), không để sót số 0.<br>• Bổ sung hàm regex phân tích số tiền trong `to_int_amount()`: Hỗ trợ tự động chuẩn hóa các định dạng tiền tệ Việt Nam và áp dụng quy tắc nhân x1000 đối với hóa đơn bán lẻ TTTM khi model nhận diện thiếu phần ngàn lẻ. | ✅ **HOÀN THÀNH** |
| **4** | **Nâng cấp API Dual Mode cho CRM (`/api/v1/extract-bill`)** | • Bổ sung khả năng nhận diện payload tự động tại endpoint `POST /api/v1/extract-bill`: Phục vụ đồng thời `multipart/form-data` (Upload file ảnh trực tiếp) và `application/json` (`{"image_base64": "..."}`).<br>• Giúp đội CRM dễ dàng tích hợp trên mọi nền tảng (.NET Framework, .NET Core, Java, Node.js, Mobile App) mà không cần xây dựng multipart parser phức tạp. | ✅ **HOÀN THÀNH** |
| **5** | **Nhúng Mã nguồn Mẫu C# .NET Core Client** | • Xây dựng mã nguồn mẫu hoàn chỉnh C# .NET Core (`ExtractApiSampleNet.cs`) với đầy đủ DTOs, cấu hình `HttpClient`, xử lý mã hóa Base64 và parse JSON.<br>• Nhúng trực tiếp toàn bộ code mẫu vào tài liệu đặc tả tích hợp `docs/04_CRM_API_INTEGRATION_SPEC.md` để lập trình viên CRM có thể sao chép và chạy ngay. | ✅ **HOÀN THÀNH** |
| **6** | **Tái cấu trúc Toàn diện Bộ Tài liệu Kỹ thuật** | • Quy hoạch thư mục `docs/` với 8 tài liệu đặc tả chuyên sâu từ 01 đến 08.<br>• Tinh gọn `HANDOFF_SYSTEM_GUIDE.md` thành Master Catalog Document tra cứu trung tâm.<br>• Gom toàn bộ tài liệu dự án vào `docs/`, dọn sạch thư mục gốc chỉ giữ lại 3 file cốt lõi: `DEV_PLAN.md`, `DEV_HISTORY.md`, `DAILY_REPORT.md`. | ✅ **HOÀN THÀNH** |
| **7** | **Tổ chức Thư mục Scripts (`scripts/`) & Pipeline CI/CD** | • Tạo thư mục `scripts/` và gom toàn bộ scripts kiểm thử (`test_*.py`), script CSDL & migration (`sync_*.py`, `setup_database_dev.sql`, `migrate_coalesce_admin_fields.py`), worker ngầm (`cron_ocr_scanner.py`) và cấu hình Nginx.<br>• Chuẩn hóa tự động nhận diện `sys.path` cho toàn bộ các script để có thể thực thi độc lập từ mọi thư mục.<br>• Nâng cấp `scripts/deploy_to_pilot.py` tự động đồng bộ đầy đủ 3 khu vực: `root/`, `docs/`, và `scripts/` lên Pilot server qua SFTP. | ✅ **HOÀN THÀNH** |
| **8** | **Đóng gói & Đẩy Mã nguồn lên Git Remote** | • Thêm quy tắc loại trừ `*history.json` vào `.gitignore` để giữ sạch kho mã nguồn.<br>• Thực hiện commit `10a4c16` và push thành công lên GitHub remote branch `main` (`origin/main`).<br>• Trạng thái working tree sạch 100% (clean). | ✅ **HOÀN THÀNH** |

### 2. Thông số Hiệu năng & Môi trường Triển khai
* **Pilot Production Service**:
  * **Endpoint**: `http://14.161.34.37:8080/api/v1/extract-bill`
  * **Web Portal Thẩm định**: `http://14.161.34.37:8080/`
  * **AI Model Engine**: `Qwen/Qwen2-VL-7B-Instruct` (BitsAndBytes 4-bit NF4 via PyTorch CUDA)
  * **VRAM footprint**: 5,820 MB / 12,288 MB (~47% capacity)
  * **Latency**: ~3,500 ms / hóa đơn (Cold start lượt đầu nạp VRAM: ~3.5 phút)
  * **Database**: MS-SQL Server `115.165.166.208:6868`, DB `CLMHQ4GIGA` (193 Outlets, 127 Bills đã lưu trữ)
* **Kho lưu trữ Git**:
  * **Remote URL**: `github.com:lamhongbac/ocr-bill.git` (Nhánh: `main`)
  * **Commit mới nhất**: `10a4c16` (*feat & refactor: re-structure project into docs/ and scripts/, add Dual Mode API, 7B GPU optimization, VND rules, and consolidated DAILY_REPORT*)
  * **Trạng thái**: Đồng bộ hoàn toàn (`up to date with origin/main`).

### 3. Kế hoạch Phiên tiếp theo
1. Phối hợp với đội CRM chạy thử nghiệm tích hợp đầu cuối API `/api/v1/extract-bill` qua payload Base64 JSON.
2. Thẩm định bổ sung các mẫu hóa đơn đặc thù (hóa đơn viết tay, hóa đơn mờ nhiệt, bill rạp phim).
3. Đánh giá tính năng đồng bộ tự động danh mục Outlet định kỳ từ CRM sang bảng tra cứu AI.

---

## Session: Ngày 22/10/2026 – Hoàn thiện 6 Change Requests (CR 1 – CR 6), Kiến trúc Coalesce & Triển khai Pilot Server

### 1. Tổng quan Tiến độ & Các Hạng mục Hoàn thành
Trong ngày làm việc 22/10/2026, toàn bộ 6 yêu cầu cải tiến (Change Requests / CRs) và các tiêu chuẩn kiểm toán đối soát do Auditor & CRM yêu cầu đã được thiết kế, lập trình, kiểm thử nghiệm thu và triển khai hoàn tất:

| STT | Hạng mục / Yêu cầu | Chi tiết kỹ thuật & Giải pháp triển khai | Trạng thái |
| :---: | :--- | :--- | :---: |
| **CR 1** | **Xử lý Phân trang Danh sách tổng hợp (Batch Table Pagination)** | • Khắc phục triệt để lỗi layout Flexbox khiến thanh phân trang bị che khuất ở đáy màn hình.<br>• Bổ sung các nút điều hướng trang đầu (`<<`), trang cuối (`>>`), chuyển trang Trước/Tiếp và dropdown chọn kích thước trang (10, 20, 50, 100).<br>• Hiển thị số trang trực quan: `Trang X / Y (Tổng Z hóa đơn)`. | ✅ **HOÀN THÀNH** |
| **CR 2** | **Cải tiến UX Lưu thay đổi (Save Changes UX)** | • Thay thế hoàn toàn hàm `alert()` mặc định của trình duyệt vốn dễ bị bỏ qua.<br>• Tích hợp **Popup Modal xác nhận chi tiết**, hiển thị rõ ràng danh sách các trường vừa lưu kèm lý do điều chỉnh.<br>• Bổ sung thanh thông báo trạng thái cố định (persistent status banner), thông báo Toast nổi và hiệu ứng nút bấm xoay tròn khi đang lưu.<br>• Bắt lỗi và hiển thị cảnh báo thân thiện khi hóa đơn đã bị khóa (Locked). | ✅ **HOÀN THÀNH** |
| **CR 3** | **Kiến trúc Dữ liệu Kiểm toán Đối soát (Coalesce Pattern)** | • **Tầng 1 - AI Data (Bất biến)**: `Ocr...` (`OcrOutletName`, `OcrBrand`, `OcrBillNumber`, `OcrDateTime`, `OcrTotal`) lưu vĩnh viễn, không bao giờ bị ghi đè.<br>• **Tầng 2 - Admin Data (Mặc định để trống)**: `Admin...` chỉ lưu giá trị khi Admin can thiệp điều chỉnh; nếu AI đúng thì để trống (`NULL`). Tuyệt đối không sao chép dữ liệu AI sang cột của Admin.<br>• **Tầng 3 - Final Data**: Số liệu cuối cùng được tính toán theo quy tắc Coalesce: `Final = COALESCE(Admin, AI)` (Có sửa lấy Admin, không sửa lấy AI). | ✅ **HOÀN THÀNH** |
| **CR 4** | **Tối ưu hóa Giao diện Thẩm định (Ergonomic Inspector UI)** | • Loại bỏ dòng "Final" trùng lặp trên từng card trường dữ liệu để giao diện thoáng, tinh gọn.<br>• Bổ sung banner chỉ dẫn quy tắc nghiệp vụ nổi bật ngay đầu form:<br>*`💡 Quy tắc ghi nhận: Nếu Admin field để trống thì số liệu cuối cùng theo AI field, nếu Admin nhập thì số liệu cuối cùng theo Admin.`* | ✅ **HOÀN THÀNH** |
| **CR 5** | **Vòng đời & Khóa trạng thái duyệt hóa đơn (Immutability State Machine)** | • Hoàn thiện State Machine 3 trạng thái: `PENDING` $\rightarrow$ `APPROVED` (chốt duyệt) / `REJECTED` (từ chối).<br>• Ràng buộc bắt buộc chọn hoặc nhập lý do từ chối (không gửi lý do rỗng).<br>• Cơ chế khóa cứng dữ liệu đa tầng (Defense in Depth): Vô hiệu hóa input, ẩn nút duyệt/sửa trên Web UI và chặn cập nhật tại Backend API (HTTP 400).<br>• Cờ `IsManualEdited`: Đánh dấu tự động hóa đơn có can thiệp thủ công (`1`) hay duyệt tự động 100% (`0`). | ✅ **HOÀN THÀNH** |
| **CR 6** | **Chuẩn hóa & Đồng bộ Bộ Tài liệu Kỹ thuật** | • Cập nhật tài liệu: Quy trình thẩm định 4 bước, kiến trúc 3 tầng Coalesce và 4 kịch bản kiểm thử UAT.<br>• Cập nhật đặc tả: 5 nguyên tắc cốt lõi cho kỹ sư CRM.<br>• Cập nhật `setup_database_dev.sql`: Bổ sung cột `Admin...` và View `v_OcrBillsFinal`. | ✅ **HOÀN THÀNH** |

### 2. Thông tin Môi trường & Trạng thái Triển khai
* **Máy chủ Thử nghiệm Thẩm định (Pilot Server)**:
  * **Địa chỉ Cổng duyệt Web Portal**: [http://14.161.34.37:8080/](http://14.161.34.37:8080/)
  * **Tài liệu API Swagger**: [http://14.161.34.37:8080/docs](http://14.161.34.37:8080/docs)
  * **Trạng thái Dịch vụ**: `ACTIVE (running)` qua systemd `ocr-bill.service`.
  * **Smoke Test**: HTTP 200 OK, phản hồi API ~72.7ms.
  * **Thống kê thực tế trên server**: 127 bills (115 PENDING, 8 APPROVED, 4 REJECTED, 4 MANUAL_EDITED).
* **Mã nguồn Git**:
  * Nhánh `main` đã được đồng bộ đầy đủ lên GitHub remote (`origin/main`).
  * Commit: `2b232d1` (*docs: cap nhat quy trinh duyet bill OCR, phan dinh AI Data, Admin Data va Trang thai duyet theo co che Coalesce*).
