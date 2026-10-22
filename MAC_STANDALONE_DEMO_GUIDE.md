# HƯỚNG DẪN CHẠY DEMO ĐỘC LẬP TRÊN MÁY MAC & KẾT NỐI CSDL RIÊNG
## (Dành cho trình diễn khách hàng không phụ thuộc server GigaMall)

Khi bạn muốn mang máy Mac đi Demo cho khách hàng khác và sử dụng cơ sở dữ liệu (CSDL) riêng độc lập hoàn toàn với GigaMall, bạn chỉ cần thực hiện theo **3 bước đơn giản** dưới đây:

---

## BƯỚC 1: KHỞI TẠO BẢNG TRÊN CSDL MỚI

Trên hệ quản trị MS-SQL của CSDL mới (ví dụ database tên: `CUSTOMER_DEMO_DB`), bạn chạy script tạo bảng có sẵn trong thư mục dự án:
👉 File: `create_tables.sql`

```sql
USE [CUSTOMER_DEMO_DB]  -- Thay bằng tên Database mới của bạn
GO

-- Chạy nội dung trong create_tables.sql để tạo:
-- 1. Bảng OcrBills (lưu thông tin hóa đơn & kết quả OCR)
-- 2. Bảng OcrBillAuditLogs (lưu lịch sử kiểm toán & người sửa)
```

> **Mẹo**: Nếu CSDL mới là một hệ thống bán lẻ/TTTM khác, bạn có thể tạo trước 2 bảng danh mục `G_Outlet` và `G_Brand` (hoặc sửa file `master_outlets.json`) chứa danh sách cửa hàng của khách hàng đó để hệ thống AI tự động khớp tên gian hàng.

---

## BƯỚC 2: CẬU HÌNH KẾT NỐI CSDL TRÊN MÁY MAC

Mở file `db_config.json` trên máy Mac (`/Volumes/ExternalSSD/ocr-bill/db_config.json`) và điền thông tin CSDL mới:

```json
{
  "server": "IP_HOAC_DOMAIN_CSDL",
  "host": "IP_HOAC_DOMAIN_CSDL",
  "port": 1433,
  "database": "CUSTOMER_DEMO_DB",
  "user": "sa",
  "password": "MatKhauCuaBan"
}
```

*Nếu máy chủ SQL Server mới dùng cổng mặc định `1433`, bạn điền `1433`. Nếu là SQL Server 2012 cũ cần bypass TLS, cấu hình `freetds.conf` đã có sẵn trong thư mục dự án sẽ tự động xử lý.*

---

## BƯỚC 3: KHỞI ĐỘNG HỆ THỐNG TRÊN MÁY MAC

Môi trường máy Mac của bạn đã được cài đặt đầy đủ **FastAPI**, **Pymssql** và thư viện **MLX-VLM** (tận dụng tối đa phần cứng Apple Silicon GPU chạy cực nhanh).

Mở Terminal trên máy Mac và chạy lệnh:

```bash
cd /Volumes/ExternalSSD/ocr-bill

# Kích hoạt môi trường và khởi động Web Portal
./venv/bin/uvicorn app_review:app --host 0.0.0.0 --port 8080 --reload
```

Sau khi chạy lệnh trên:
* **Giao diện Web Portal Demo**: Mở trình duyệt vào [http://localhost:8080](http://localhost:8080)
* **Tài liệu API Swagger**: [http://localhost:8080/docs](http://localhost:8080/docs)

---

## BƯỚC 4: (TÙY CHỌN) PUBLIC RA INTERNET TỪ MÁY MAC ĐỂ KHÁCH THỬ NGHIỆM TRÊN ĐIỆN THOẠI CỦA HỌ

Nếu trong buổi Demo, bạn muốn khách hàng dùng **chính điện thoại của họ** truy cập vào web để thử chụp hóa đơn hoặc gọi API từ xa, bạn có thể dùng **Cloudflare Tunnel miễn phí (không cần mở port router)**:

1. Mở một tab Terminal mới trên Mac:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
2. Cloudflare sẽ tạo ra một đường link HTTPS công khai tạm thời (ví dụ: `https://demo-ocr-xyz.trycloudflare.com`).
3. Khách hàng mở link đó trên điện thoại là có thể dùng thử ngay lập tức!
