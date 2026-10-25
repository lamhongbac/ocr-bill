# CHUYÊN ĐỀ 3: QUY TẮC BÓC TÁCH TIỀN VIỆT NAM (VND) & SO KHỚP MỜ 193 CỬA HÀNG (VIETNAMESE CURRENCY & EXTRACTION RULES)

> **Mã chuyên đề**: `SPEC-03-RULES-VND`  
> **Phiên bản tài liệu**: 2.0 (Cập nhật 25/10/2026)  
> **Đối tượng áp dụng**: AI Engineer, Backend Developer, QA Tester, Data Analyst

---

## 1. ĐẶC THÙ ĐỊNH DẠNG TIỀN TỆ VIỆT NAM (VND) TRONG HÓA ĐƠN BÁN LẺ

### 1.1. Khác biệt cốt lõi giữa Chuẩn Việt Nam và Chuẩn Quốc tế
* **Chuẩn Quốc tế (US/EU)**: Dấu chấm `.` là dấu thập phân (Decimal point, ví dụ: `$204.00` = 204 đô la), dấu phẩy `,` là phân tách ngàn.
* **Chuẩn Việt Nam (VND)**:
  * Trong hóa đơn bán lẻ/F&B tại TTTM Gigamall, **dấu chấm `.` hoặc phẩy `,` đều được dùng làm dấu phân tách hàng nghìn** (ví dụ: `204.000`, `75.000`, `1.500.000` hoặc `75,000`).
  * Tại Việt Nam không có tiền xu hay số lẻ thập phân trong thanh toán tiền mặt bán lẻ.
  * Mệnh giá giao dịch tối thiểu trong trung tâm thương mại thông thường từ `1.000 đ` trở lên.

### 1.2. Phân tích Sai lệch Nhận thức của Mô hình AI (VLM Misinterpretation)
* Khi prompt chỉ ghi chung chung *"Chỉ ghi số nguyên, không dấu chấm phẩy"*, mô hình VLM gặp số `204.000` trên hóa đơn sẽ bị nhầm lẫn:
  * Mô hình nghĩ `204.000` có dấu chấm là số thập phân $\rightarrow$ Sinh ra `204.0` hoặc cắt bỏ phần sau dấu chấm thành `204`.
  * Hoặc mô hình không tìm thấy số nguyên không dấu nào nên rơi vào nhánh dự phòng prompt và sinh ra `"bill_total": 0`.

---

## 2. GIẢI PHÁP 3 LỚP XỬ LÝ ĐỊNH DẠNG TIỀN TỆ (3-LAYER REMEDIATION)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
3 LỚP BẢO VỆ XỬ LÝ ĐỊNH DẠNG TIỀN TỆ VIỆT NAM (VND) TRONG HỆ THỐNG AI OCR
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [LỚP 1: NÂNG CẤP PROMPT AI CHUYÊN SÂU]                                                │
│ └── Hướng dẫn rõ ràng: Dấu '.' hoặc ',' là phân tách hàng nghìn (204.000 -> 204000).  │
│     Bắt buộc ghi đủ toàn bộ các chữ số 0 hàng nghìn, không rút gọn hay ghi thập phân. │
│                                                                                        │
│ [LỚP 2: HẬU XỬ LÝ THÔNG MINH (POST-PROCESSING)]                                       │
│ ├── Parser Regex: Bóc tách chuỗi có dấu chấm/phẩy phân tách hàng nghìn                │
│ └── Thuật toán nhân 1.000: Nếu 0 < bill_total < 1000 đối với hóa đơn TTTM             │
│                                                                                        │
│ [LỚP 3: GIAO DIỆN KIỂM SOÁT SAI BIỆT TRÊN WEB ADMIN]                                  │
│ └── Tự động bật badge cảnh báo vàng khi phát hiện số tiền do Admin sửa lệch với AI     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Lớp 1: Cấu trúc Prompt Chuyên sâu (`EXTRACTION_PROMPT`)
Đoạn chỉ dẫn bắt buộc trong prompt gửi tới Qwen2-VL:
```text
- ĐỊNH DẠNG SỐ TIỀN (VIỆT NAM ĐỒNG - VND):
  * Hóa đơn tại Việt Nam dùng dấu chấm '.' hoặc phẩy ',' phân cách hàng nghìn (ví dụ: '75.000' hay '75,000' là 75 nghìn đồng -> phải ghi số nguyên 75000; '204.000' -> ghi 204000; '200.000' -> ghi 200000; '1.500.000' -> ghi 1500000).
  * Luôn ghi đầy đủ tất cả các chữ số nguyên, tuyệt đối không bỏ các số 0 hàng nghìn và không ghi số thập phân (không được ghi 75 hay 204).
  * Không ghi đơn vị tiền tệ (đ, VND), không ghi dấu chấm phẩy trong số bill_total.
- bill_total là số tiền CUỐI CÙNG khách thực trả (Tổng thanh toán / Khách phải trả / Total due / Net Amount) SAU khi đã trừ giảm giá, voucher, điểm. Không lấy tiền giảm giá, không lấy tiền khách đưa, không lấy tiền thối lại.
```

### 2.2. Lớp 2: Thuật toán Hậu Xử Lý Chuẩn hóa (`to_int_amount`)
Hàm chuẩn hóa số tiền trong [ocr_engine.py](file:///Volumes/ExternalSSD/ocr-bill/ocr_engine.py):
```python
def to_int_amount(value, raw_str: str = None) -> int:
    if value is None or isinstance(value, bool):
        return 0
    num = 0
    if isinstance(value, (int, float)):
        num = int(round(value))
    else:
        s = str(value).strip()
        s = re.sub(r"[^\d.,]", "", s)
        # Nếu đuôi có 3 số sau dấu chấm/phẩy (phân cách hàng nghìn) -> Xóa dấu lấy toàn bộ số
        if re.search(r"[.,]\d{3}$", s):
            digits = re.sub(r"[^\d]", "", s)
            num = int(digits) if digits else 0
        # Nếu đuôi có 2 số (dạng .00 / ,00 thập phân) -> Bỏ 2 số 0 cuối
        elif re.search(r"[.,]\d{2}$", s):
            base = re.sub(r"[.,]\d{2}$", "", s)
            digits = re.sub(r"[^\d]", "", base)
            num = int(digits) if digits else 0
        else:
            digits = re.sub(r"[^\d]", "", s)
            num = int(digits) if digits else 0

    # Cơ chế bọc an toàn: Nếu AI hiểu nhầm dấu chấm thành thập phân (204.0 -> 204):
    # Các giao dịch bán lẻ tại TTTM Gigamall tối thiểu từ 1.000 đ trở lên
    if 0 < num < 1000:
        num = num * 1000

    return num
```

---

## 3. QUY TẮC 4: CHUẨN HÓA SỐ HÓA ĐƠN (`optimize_bill_number`)

Hóa đơn bán lẻ có cách ghi số bill rất đa dạng (`No: 001894`, `Bill # 240 - 243`, `SO HD: 260909`). Để đồng bộ với CSDL CRM:
1. **Lấy 6 số cuối**: Chỉ giữ lại các chữ số và lấy 6 chữ số tận cùng.
2. **Bù số 0 (`zfill(6)`)**: Nếu chuỗi số ngắn hơn 6 chữ số, tự động thêm các số 0 vào đầu (ví dụ: `1894` $\rightarrow$ `001894`).
3. **Dự phòng bằng Ngày Giờ**: Nếu hóa đơn không in số bill, tự động lấy chuỗi chữ số ngày giờ giao dịch (`YYYYMMDDHHmmss`) làm mã định danh duy nhất chống trùng lặp.

---

## 4. THUẬT TOÁN SO KHỚP MỜ VỚI DANH MỤC 193 MASTER OUTLETS

### 4.1. Cấu trúc Danh mục Cửa hàng (`master_outlets.json`)
Được đồng bộ trực tiếp từ bảng `G_Outlet` JOIN `G_Brand` (193 cửa hàng hợp lệ trong CSDL DEV/PROD):
* `outlet_number`: Mã định danh CRM (ví dụ: `COOPXTRA`, `CHEESECOFFEE`, `JPSportGame`).
* `outlet_name`: Tên cửa hàng (ví dụ: `CO.OPXTRA`, `CHEESE COFFEE`).
* `brand_name`: Thương hiệu (ví dụ: `COOP.XTRA`).
* `outlet_address`: Vị trí mặt bằng (ví dụ: `L2-01, L3-01`, `Tầng 4`).

### 4.2. Cơ chế Chuẩn hóa & Tính Điểm Tương đồng (`resolve_outlet`)
1. **Khử dấu tiếng Việt & Ký tự đặc biệt**:
   ```python
   def normalize(text):
       text = str(text).replace("đ", "d").replace("Đ", "D")
       text = unicodedata.normalize("NFKD", text)
       text = "".join(c for c in text if not unicodedata.combining(c))
       text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
       return re.sub(r"\s+", " ", text).strip()
   ```
2. **Thuật toán Chấm điểm đa tầng**:
   * Khớp chính xác 100% $\rightarrow$ Điểm = `1.0`.
   * Khớp từ khóa con nguyên vẹn (ví dụ `HIGHLANDS` trong `HIGHLANDS COFFEE GIGAMALL`) $\rightarrow$ Điểm = `0.9`.
   * Khớp tỷ lệ chuỗi mờ qua `difflib.SequenceMatcher(None, candidate, key).ratio()`.
3. **Ngưỡng chấp nhận tự động (`MATCH_CUTOFF = 0.60`)**:
   * Nếu điểm $\ge 0.60$: Tự động gán `outlet_number` tương ứng vào hóa đơn.
   * Đồng thời trích xuất **Top 3 ứng viên có điểm cao nhất** (`top_candidates`) để phục vụ việc giải thích và kiểm toán của Admin.
