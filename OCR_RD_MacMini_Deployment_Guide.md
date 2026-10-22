# KẾ HOẠCH R&D TRIỂN KHAI OCR HÓA ĐƠN VỚI VISION-LANGUAGE MODEL (VLM) TRÊN MÁY LAB (MAC MINI)

> 📌 **TÀI LIỆU HƯỚNG DẪN DÀNH CHO TEAM DEV (CHỈ TẬP TRUNG GIAI ĐOẠN 1)**  
> *Đề nghị đội ngũ Kỹ thuật đọc kỹ Bối cảnh, Mục tiêu và tuân thủ tuyệt đối danh sách phân định phạm vi (Must-Do vs Don't-Do) bên dưới trước khi thực hiện.*

---

## 1. BỐI CẢNH DỰ ÁN & MỤC TIÊU CHIẾN LƯỢC (PROJECT CONTEXT)

### 1.1. Hiện trạng hệ thống (Current State)
- Hệ thống CRM Gigamall hiện tại đang sử dụng dịch vụ **Google Cloud Vision OCR** kết hợp với các thuật toán cắt chuỗi / Regex truyền thống trên backend .NET Core.
- **Những tồn tại cần giải quyết**:
  1. **Chi phí vận hành**: Tốn chi phí bản quyền Google API hàng tháng tỷ lệ thuận theo số lượng hóa đơn khách hàng upload.
  2. **Hạn chế kỹ thuật**: OCR truyền thống chỉ đọc ra chuỗi text thô rời rạc (Bounding Boxes) mà không hiểu ngữ cảnh. Khi hóa đơn bị nhăn, chụp nghiêng, chụp thiếu sáng, hoặc có nhiều tầng giảm giá (Voucher, Điểm tích lũy, Chiết khấu), hệ thống cũ thường xuyên **nhầm lẫn giữa tiền thanh toán thực tế và tiền giảm giá**, hoặc không nhận diện được tên gian hàng nếu hóa đơn chỉ in logo hoặc tên pháp nhân công ty mẹ.

### 1.2. Hướng giải pháp R&D mới (Target Solution)
- Chuyển đổi sang ứng dụng **Mô hình Thị giác Ngôn ngữ Lớn (Vision-Language Model - VLM)**, cụ thể là dòng mô hình mã nguồn mở **Qwen2-VL-7B** tự lưu trữ (Self-hosted) trên phần cứng **Apple Silicon (Mac Mini)**.
- **Lợi ích kỳ vọng**:
  - **Hiểu sâu ngữ cảnh**: AI đọc và tư duy như con người, tự biết đâu là "Tổng tiền khách thực trả", đâu là "Tiền giảm giá", tự động nhận diện thương hiệu dù in tên viết tắt.
  - **Chi phí bản quyền bằng 0**: Chạy hoàn toàn trên máy chủ nội bộ (On-premises / Local Lab), không tốn phí API bên ngoài.
  - **Bảo mật**: Dữ liệu hóa đơn người dùng không gửi ra ngoài mạng internet.

---

## 2. TRIẾT LÝ PHÁT TRIỂN STAGE-GATE (BẮT BUỘC TUÂN THỦ)

Dự án tuân thủ nghiêm ngặt nguyên tắc **"Fail-Fast & Milestone-Driven"** chia làm 2 giai đoạn:

```
[GIAI ĐOẠN 1: CHỨNG MINH NĂNG LỰC AI - POC]
(Chạy script Python offline trên Mac Mini | Thử nghiệm 50-100 bill thật)
                         │
                         ▼
                [CỔNG QUYẾT ĐỊNH (GATE 1)]
   Thẩm định bằng mắt: Tổng tiền >= 95%, Tên quán >= 90%
               ├── KHÔNG ĐẠT ──> [DỪNG DỰ ÁN NGAY LẬP TỨC (ABORT)]
               │                 (Bảo toàn nguồn lực, KHÔNG viết API, KHÔNG sửa Server 2)
               └── ĐẠT KPI
                         │
                         ▼
[GIAI ĐOẠN 2: TỐI ƯU HÓA, ĐÓNG GÓI REST API & TÍCH HỢP HỆ THỐNG]
(Dựng FastAPI trên Mac Mini | Viết HttpClient tích hợp vào backend .NET Core trên Server 2)
                         │
                         ▼
                [CỔNG NGHIỆM THU PILOT (GATE 2)]
```

> ⚠️ **LƯU Ý CỐT TỬ DÀNH CHO TEAM DEV**:  
> **"Hiện tại chúng ta ĐANG Ở GIAI ĐOẠN 1. Tuyệt đối KHÔNG triển khai bất kỳ công việc nào của Giai đoạn 2 cho đến khi Giai đoạn 1 được nghiệm thu đạt yêu cầu!"**

---

## 3. BẢNG PHÂN ĐỊNH PHẠM VI DÀNH CHO TEAM DEV (GIAI ĐOẠN 1)

Nhằm tránh tình trạng Dev làm thừa việc hoặc hỏi những nội dung chưa cần thiết, bảng sau đây quy định rõ ràng:

| ✅ NHỮNG VIỆC DEV BẮT BUỘC LÀM (MUST-DO) | ❌ NHỮNG VIỆC DEV TUYỆT ĐỐI KHÔNG LÀM (OUT OF SCOPE) |
| :--- | :--- |
| 1. Cài đặt môi trường trên máy Mac Mini theo mục 5.1 (chỉ mất ~3 phút). | 1. ❌ **KHÔNG** đụng vào source code .NET Core, CMS Web hay Backend trên Server 2. |
| 2. Chạy đúng 1 câu lệnh SQL trên Server 1 để xuất file danh mục `master_outlets.json` sang Mac Mini (xem mục 5.2). | 2. ❌ **KHÔNG** dựng Web API, FastAPI, cấu hình IP mạng, port forwarding hay mở tường lửa. |
| 3. Copy ngẫu nhiên 50 - 100 file ảnh bill thực tế từ Server 2 vào thư mục `~/ocr-poc-gate1/test_images/`. | 3. ❌ **KHÔNG** tìm cách cài driver ODBC hay kết nối mạng từ Mac Mini vào DB SQL Server. |
| 4. Chạy script `evaluate_lean.py` để AI tự động bóc tách và sinh ra file `report.html`. | 4. ❌ **KHÔNG** mất thời gian viết tool query CSDL `CRMGiGaBill` để map ID với file ảnh. |
| 5. Mở file `report.html` trên trình duyệt để kiểm tra trực quan bằng mắt (Visual Audit) và báo cáo kết quả. | 5. ❌ **KHÔNG** hỏi về kiến trúc tích hợp hệ thống hay luồng dữ liệu Production ở giai đoạn này. |

---

## 4. KIẾN TRÚC MÁY LAB & LỰA CHỌN MÔ HÌNH VLM

### 4.1. Phần cứng máy Lab: Mac Mini (Apple Silicon)
- **Kiến trúc Bộ nhớ Hợp nhất (Unified Memory - UMA)**: GPU dùng chung toàn bộ RAM hệ thống (16GB/24GB). Khác với PC bị giới hạn VRAM card đồ họa rời, Mac Mini cho phép nạp trọn vẹn mô hình VLM 7B mà không lo tràn bộ nhớ.
- **Tăng tốc Metal & Tiết kiệm điện**: Khai thác tối đa GPU Apple Silicon, công suất chỉ 25W–45W, vận hành êm ái 24/7.

### 4.2. Lựa chọn Công nghệ & Mô hình AI
- **Framework lõi**: **`mlx-vlm`** (Thư viện Deep Learning mã nguồn mở do chính nhóm nghiên cứu AI của Apple phát triển riêng cho dòng chip Apple Silicon).
- **Mô hình VLM**: **`mlx-community/Qwen2-VL-7B-Instruct-4bit`**.
  - Đọc cực tốt tiếng Việt có dấu và hóa đơn in nhiệt.
  - Hỗ trợ **Dynamic Resolution**: Tự thích ứng với hóa đơn dài mà không vỡ nét chữ nhỏ.
  - Bản 4-bit chỉ chiếm **~4.5 GB RAM**, chạy siêu mượt trên Mac Mini 16GB.

---

## 5. GIAI ĐOẠN 1: HƯỚNG DẪN THỰC THI CHI TIẾT (STEP-BY-STEP DEV GUIDE)

### 5.1. Cài đặt môi trường kiểm thử trên Mac Mini
Mở Terminal trên Mac Mini và thiết lập môi trường độc lập:

```bash
# 1. Cài đặt Python 3.11 qua Homebrew
brew install python@3.11 git

# 2. Tạo thư mục làm việc cho Mục tiêu 1
mkdir -p ~/ocr-poc-gate1 && cd ~/ocr-poc-gate1

# 3. Tạo môi trường ảo Python
python3.11 -m venv venv
source venv/bin/activate

# 4. Cài đặt các thư viện phục vụ benchmark offline
pip install --upgrade pip
pip install mlx-vlm pillow pandas requests
```

---

### 5.2. Xuất dữ liệu Master Data từ CSDL thành JSON (Pre-preparation)

Để mô hình AI không chỉ "đọc chữ thô" mà có thể **chuẩn hóa dữ liệu tương thích 100% với hệ thống CRM**, Giai đoạn 1 cần danh mục Cửa hàng & Thương hiệu Gigamall làm từ điển đối chiếu (Entity Resolution).

#### 1. Nguyên tắc lấy dữ liệu:
- **KHÔNG kết nối mạng hay ODBC**: Tuyệt đối không mở port DB, không cài driver ODBC trên Mac Mini.
- **Chỉ xuất 1 file duy nhất**: `master_outlets.json` từ Server 1 và chép sang Mac Mini.
- **KHÔNG cần trích xuất bảng `CRMGiGaBill`**: Tránh việc tìm kiếm file ảnh phức tạp. Chúng ta dùng phương pháp kiểm tra trực quan (Manual Visual Audit) ở các bước sau.

---

#### 2. Câu lệnh SQL xuất trực tiếp ra JSON (Chọn 1 trong 2 cách):

##### Cách A: Dùng cú pháp `FOR JSON PATH` (Dành cho SQL Server 2016 trở lên)
Chạy câu lệnh sau trong SSMS:
```sql
SELECT 
    o.ID AS outlet_id,
    o.Number AS outlet_number,
    o.OutletName AS outlet_name,
    b.ID AS brand_id,
    b.Number AS brand_number,
    b.BrandName AS brand_name,
    o.Address AS outlet_address
FROM Outlet o WITH (NOLOCK)
INNER JOIN Brand b WITH (NOLOCK) ON o.BrandID = b.ID
WHERE o.IsAccPoint = 1 AND o.RecordStatus = 'A'
ORDER BY o.OutletName
FOR JSON PATH;
```
> *Lưu ý*: Nếu SSMS báo lỗi `Incorrect syntax near 'JSON'`, nguyên nhân là do CSDL đang để Compatibility Level thấp (< 130) hoặc là bản SQL Server 2014 trở về trước $\rightarrow$ Hãy dùng **Cách B** bên dưới.

##### Cách B: Dùng cú pháp `FOR XML PATH` (Tương thích 100% mọi phiên bản SQL 2008 / 2012 / 2014)
Câu lệnh này tự động ghép chuỗi JSON, bảo toàn tiếng Việt Unicode (`nvarchar`) và bọc sẵn ngoặc vuông:
```sql
SELECT '[' + STUFF((
    SELECT
          ',{'
        + '"outlet_id":' + CAST(o.ID AS varchar(20)) + ','
        + '"outlet_number":' + CASE WHEN o.Number IS NULL THEN 'null' ELSE '"' + REPLACE(REPLACE(o.Number, '\', '\\'), '"', '\"') + '"' END + ','
        + '"outlet_name":' + CASE WHEN o.OutletName IS NULL THEN 'null' ELSE '"' + REPLACE(REPLACE(o.OutletName, '\', '\\'), '"', '\"') + '"' END + ','
        + '"brand_id":' + CAST(b.ID AS varchar(20)) + ','
        + '"brand_number":' + CASE WHEN b.Number IS NULL THEN 'null' ELSE '"' + REPLACE(REPLACE(b.Number, '\', '\\'), '"', '\"') + '"' END + ','
        + '"brand_name":' + CASE WHEN b.BrandName IS NULL THEN 'null' ELSE '"' + REPLACE(REPLACE(b.BrandName, '\', '\\'), '"', '\"') + '"' END + ','
        + '"outlet_address":' + CASE WHEN o.Address IS NULL THEN 'null' ELSE '"' + REPLACE(REPLACE(o.Address, '\', '\\'), '"', '\"') + '"' END
        + '}'
    FROM Outlet o WITH (NOLOCK)
    INNER JOIN Brand b WITH (NOLOCK) ON o.BrandID = b.ID
    WHERE o.IsAccPoint = 1 AND o.RecordStatus = 'A'
    ORDER BY o.OutletName
    FOR XML PATH(''), TYPE).value('.', 'nvarchar(MAX)'), 1, 1, '') + ']' AS json_result;
```

#### 3. Thao tác lưu file:
- Sau khi chạy câu lệnh (Cách A hoặc Cách B), click vào ô kết quả trong SSMS $\rightarrow$ Bấm `Ctrl + S` $\rightarrow$ Lưu file với tên `master_outlets.json`.
- Chép file `master_outlets.json` vào thư mục `~/ocr-poc-gate1/` trên Mac Mini.

---

### 5.3. Chuẩn bị tập ảnh kiểm thử tinh gọn (Lean Dataset & Zero-Friction Setup)

Thay vì cố gắng viết script ánh xạ phức tạp giữa DB và file ảnh, ta áp dụng quy trình kiểm thử cực nhanh:
- Vào thư mục lưu trữ ảnh trên Server 2 (hoặc máy lưu trữ bill Gigamall), chọn ngẫu nhiên **50 - 100 file ảnh hóa đơn thực tế** ném thẳng vào thư mục `~/ocr-poc-gate1/test_images/` trên Mac Mini.
- *Gợi ý tập mẫu thử*:
  - 40 bill chụp đẹp, đủ sáng (các thương hiệu phổ biến: Highlands, Phúc Long, Haidilao, Co.opXtra...).
  - 20 bill chụp nghiêng, nhăn, góc chụp hơi tối.
  - 20 bill dài, nhiều món hàng.
  - 10-20 ảnh chụp sai/ảnh rác (ảnh phong cảnh, thẻ nhân viên, bill mờ câm không thấy chữ) để kiểm tra trường `is_valid_bill`.

---

### 5.4. Script kiểm thử độc lập và sinh Báo cáo Trực quan (`evaluate_lean.py`)

Script này chạy offline 100% trên Mac Mini:
1. Quét toàn bộ ảnh trong thư mục `test_images/`.
2. Dùng mô hình VLM bóc tách các trường: Thương hiệu, Cửa hàng, Số bill, Ngày giờ, Tổng tiền, Hóa đơn hợp lệ.
3. Đối chiếu tên quán với `master_outlets.json` qua thuật toán so khớp mờ (`difflib`).
4. Xuất dữ liệu ra file `results.csv` (dùng để tra cứu).
5. **ĐẶC BIỆT**: Tự động sinh ra file **`report.html`** có giao diện trực quan song song (Side-by-side): Cột trái là **Ảnh hóa đơn thật (click phóng to)**, Cột phải là **Dữ liệu AI bóc tách**, tích hợp sẵn các nút **[✅ ĐẠT] / [❌ SAI]** để người kiểm thử lướt qua đánh giá trong vòng 5-10 phút.

```python
# ~/ocr-poc-gate1/evaluate_lean.py
import os
import json
import time
import base64
import difflib
from pathlib import Path
from PIL import Image
import pandas as pd
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template

MASTER_OUTLETS_FILE = "./master_outlets.json"
IMAGE_DIR = Path("./test_images")
MODEL_PATH = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
HTML_REPORT_FILE = "report.html"
CSV_REPORT_FILE = "results.csv"

EXTRACTION_PROMPT = """Bạn là chuyên gia bóc tách hóa đơn tại Trung tâm Thương mại Gigamall.
Hãy đọc ảnh hóa đơn và xuất ra chuỗi JSON duy nhất (không kèm markdown ```json hay giải thích):
{
  "brand_name": "Tên thương hiệu (nếu có)",
  "outlet_name": "Tên cửa hàng in trên hóa đơn",
  "bill_number": "Mã số hóa đơn / Bill No",
  "bill_datetime": "Ngày giờ giao dịch YYYY-MM-DD HH:mm:ss",
  "bill_total": Số tiền thực tế khách phải thanh toán (chỉ lấy số nguyên, loại bỏ VND, đ, dấu chấm phẩy),
  "is_valid_bill": true nếu là hóa đơn mua hàng đọc được thông tin, false nếu ảnh mờ/ảnh rác/không đọc được
}"""

def resolve_outlet(raw_name, master_outlets):
    """Chuẩn hóa tên quán AI đọc được về mã Outlet chuẩn trong CRM qua so khớp mờ"""
    if not raw_name or not master_outlets:
        return None, raw_name
    outlet_names = [o["outlet_name"] for o in master_outlets]
    matches = difflib.get_close_matches(raw_name, outlet_names, n=1, cutoff=0.45)
    if matches:
        matched_obj = next(o for o in master_outlets if o["outlet_name"] == matches[0])
        return matched_obj["outlet_number"], matched_obj["outlet_name"]
    return None, raw_name

def image_to_base64(img_path):
    """Chuyển ảnh sang Base64 để nhúng trực tiếp vào file HTML báo cáo"""
    try:
        with open(img_path, "rb") as f:
            return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except Exception:
        return ""

def generate_html_report(items, avg_latency):
    """Tạo giao diện Web HTML trực quan để thẩm định thủ công siêu nhanh"""
    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Báo Cáo Nghiệm Thu Trực Quan - OCR VLM Gate 1</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; }}
        h1 {{ color: #1a1a1a; text-align: center; margin-bottom: 5px; }}
        .summary {{ text-align: center; margin-bottom: 25px; color: #555; font-size: 15px; }}
        .stat-badge {{ display: inline-block; background: #0071e3; color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; margin: 0 5px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 20px; max-width: 1600px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); display: flex; overflow: hidden; border: 2px solid transparent; transition: all 0.2s; }}
        .card.passed {{ border-color: #28a745; }}
        .card.failed {{ border-color: #dc3545; }}
        .img-box {{ width: 220px; min-width: 220px; background: #222; display: flex; align-items: center; justify-content: center; cursor: pointer; }}
        .img-box img {{ max-width: 100%; max-height: 280px; object-fit: contain; }}
        .data-box {{ padding: 15px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }}
        .field {{ margin-bottom: 8px; font-size: 13px; }}
        .label {{ font-weight: bold; color: #666; display: inline-block; width: 100px; }}
        .val {{ color: #111; font-weight: 500; }}
        .val-total {{ color: #d9381e; font-size: 16px; font-weight: bold; }}
        .val-outlet {{ color: #0066cc; font-weight: bold; }}
        .actions {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; display: flex; gap: 10px; align-items: center; }}
        button {{ border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px; }}
        .btn-pass {{ background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }}
        .btn-fail {{ background: #ffebee; color: #c62828; border: 1px solid #ef9a9a; }}
        .btn-pass.active {{ background: #2e7d32; color: white; }}
        .btn-fail.active {{ background: #c62828; color: white; }}
    </style>
</head>
<body>
    <h1>BÁO CÁO KIỂM THỬ TRỰC QUAN - MỤC TIÊU 1 (POC GATE 1)</h1>
    <div class="summary">
        Tổng số hóa đơn: <span class="stat-badge">{len(items)}</span> | 
        Thời gian xử lý trung bình: <span class="stat-badge">{avg_latency:.2f}s / bill</span>
        <br><small style="color: #888;">(Click vào ảnh để mở ảnh lớn. Bấm nút [ĐẠT] hoặc [SAI] để đánh dấu nghiệm thu)</small>
    </div>
    <div class="grid">
    """
    for idx, it in enumerate(items, 1):
        total_fmt = f"{it['bill_total']:,} đ" if isinstance(it['bill_total'], (int, float)) and it['bill_total'] > 0 else str(it['bill_total'])
        html_content += f"""
        <div class="card" id="card-{idx}">
            <div class="img-box" onclick="window.open('{it['img_b64']}', '_blank')">
                <img src="{it['img_b64']}" alt="Bill {idx}">
            </div>
            <div class="data-box">
                <div>
                    <div class="field"><span class="label">Tệp ảnh:</span> <span class="val">{it['filename']}</span></div>
                    <div class="field"><span class="label">Quán (AI đọc):</span> <span class="val">{it['raw_outlet']}</span></div>
                    <div class="field"><span class="label">Quán (CRM):</span> <span class="val val-outlet">{it['resolved_outlet']} ({it['outlet_number'] or 'Chưa khớp'})</span></div>
                    <div class="field"><span class="label">Số Bill:</span> <span class="val">{it['bill_number']}</span></div>
                    <div class="field"><span class="label">Ngày giờ:</span> <span class="val">{it['bill_datetime']}</span></div>
                    <div class="field"><span class="label">Tổng tiền:</span> <span class="val val-total">{total_fmt}</span></div>
                    <div class="field"><span class="label">Hợp lệ:</span> <span class="val">{'✅ Hợp lệ' if it['is_valid'] else '❌ Hóa đơn rác'}</span></div>
                    <div class="field"><span class="label">Độ trễ:</span> <span class="val">{it['latency']}s</span></div>
                </div>
                <div class="actions">
                    <button class="btn-pass" onclick="markCard({idx}, 'pass')">✅ ĐẠT</button>
                    <button class="btn-fail" onclick="markCard({idx}, 'fail')">❌ SAI</button>
                </div>
            </div>
        </div>
        """
    html_content += """
    </div>
    <script>
        function markCard(idx, status) {
            const card = document.getElementById('card-' + idx);
            const btnPass = card.querySelector('.btn-pass');
            const btnFail = card.querySelector('.btn-fail');
            if (status === 'pass') {
                card.classList.remove('failed');
                card.classList.add('passed');
                btnPass.classList.add('active');
                btnFail.classList.remove('active');
            } else {
                card.classList.remove('passed');
                card.classList.add('failed');
                btnFail.classList.add('active');
                btnPass.classList.remove('active');
            }
        }
    </script>
</body>
</html>
"""
    with open(HTML_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    print(f"[*] Nạp mô hình {MODEL_PATH} vào Apple Silicon Unified Memory...")
    model, processor = load(MODEL_PATH)
    config = model.config
    print("[+] Nạp mô hình thành công!\n")

    # Nạp Master Data Outlet
    master_outlets = []
    if os.path.exists(MASTER_OUTLETS_FILE):
        with open(MASTER_OUTLETS_FILE, "r", encoding="utf-8") as f:
            master_outlets = json.load(f)
        print(f"[+] Đã nạp {len(master_outlets)} cửa hàng từ {MASTER_OUTLETS_FILE}")
    else:
        print("[!] Không tìm thấy master_outlets.json, bỏ qua bước chuẩn hóa tên quán.")

    # Tìm toàn bộ ảnh trong thư mục test_images
    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    image_files = [f for f in IMAGE_DIR.iterdir() if f.suffix.lower() in valid_exts]
    total = len(image_files)

    if total == 0:
        print(f"[!] Thư mục {IMAGE_DIR} không có ảnh nào. Vui lòng copy 50-100 ảnh vào đây!")
        return

    print(f"[*] Bắt đầu bóc tách tinh gọn {total} ảnh trong thư mục {IMAGE_DIR}...\n")
    processed_items = []

    for idx, img_path in enumerate(image_files, 1):
        start_t = time.time()
        try:
            image = Image.open(img_path).convert("RGB")
            messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": EXTRACTION_PROMPT}]}]
            prompt = apply_chat_template(processor, config, messages)

            output = generate(model, processor, prompt, image, max_tokens=512, temperature=0.1, verbose=False)
            latency = round(time.time() - start_t, 2)

            # Làm sạch chuỗi JSON trả về
            clean = output.strip().replace("```json", "").replace("```", "").strip()
            pred = json.loads(clean)

            # Chuẩn hóa tên quán
            outlet_num, resolved_outlet = resolve_outlet(pred.get("outlet_name", ""), master_outlets)

            item = {
                "filename": img_path.name,
                "latency": latency,
                "raw_brand": pred.get("brand_name", ""),
                "raw_outlet": pred.get("outlet_name", ""),
                "outlet_number": outlet_num,
                "resolved_outlet": resolved_outlet,
                "bill_number": pred.get("bill_number", ""),
                "bill_datetime": pred.get("bill_datetime", ""),
                "bill_total": pred.get("bill_total", 0),
                "is_valid": pred.get("is_valid_bill", True),
                "img_b64": image_to_base64(img_path)
            }
            processed_items.append(item)
            print(f"[{idx}/{total}] {img_path.name} | {latency}s | Tiền: {item['bill_total']} | Quán: {resolved_outlet}")

        except Exception as e:
            print(f"[{idx}/{total}] {img_path.name} | LỖI: {e}")

    # Xuất CSV và HTML Report
    if processed_items:
        df = pd.DataFrame(processed_items).drop(columns=["img_b64"])
        df.to_csv(CSV_REPORT_FILE, index=False, encoding="utf-8-sig")
        avg_lat = df["latency"].mean()
        generate_html_report(processed_items, avg_lat)

        print("\n" + "="*60)
        print("          HOÀN THÀNH BÓC TÁCH MỤC TIÊU 1 (GATE 1)")
        print("="*60)
        print(f"1. Tổng số hóa đơn đã xử lý: {len(processed_items)}/{total}")
        print(f"2. Thời gian xử lý trung bình: {avg_lat:.2f} giây/hóa đơn")
        print(f"3. Tệp kết quả dữ liệu:        {CSV_REPORT_FILE}")
        print(f"4. Báo cáo trực quan nghiệm thu: {HTML_REPORT_FILE}")
        print("="*60)
        print("👉 HÃY MỞ FILE 'report.html' TRÊN TRÌNH DUYỆT ĐỂ KIỂM TRA TRỰC QUAN BẰNG MẮT!")

if __name__ == "__main__":
    main()
```

---

### 5.5. CỔNG NGHIỆM THU THẨM ĐỊNH TRỰC QUAN (VISUAL AUDIT - GATE 1)

Thay vì đối soát tự động với dữ liệu SQL cũ vốn có nguy cơ chứa sai sót, việc nghiệm thu Gate 1 được thực hiện bằng **Thẩm định trực quan (Visual Inspection) trên file `report.html`**:

1. **Cách thực hiện**:
   - Mở file `report.html` trên trình duyệt máy Mac Mini (hoặc copy file HTML sang máy cá nhân).
   - Người nghiệm thu duyệt qua từng thẻ hóa đơn (ảnh hóa đơn nằm ngay cạnh dữ liệu AI đọc được).
   - Bấm nút **✅ ĐẠT** hoặc **❌ SAI** cho từng hóa đơn.

2. **Tiêu chuẩn vượt Cổng (Gate 1 Thresholds)**:
   - **Tập mẫu thử**: Tối thiểu 50 - 100 hóa đơn thực tế đa dạng chủng loại.
   - **Tỷ lệ Tổng tiền chính xác (`bill_total`)**: $\ge 95\%$ trên tổng số bill đọc được bằng mắt thường.
   - **Tỷ lệ Khớp đúng Cửa hàng (`resolved_outlet`)**: $\ge 90\%$ (đã qua thuật toán so khớp mờ với `master_outlets.json`).
   - **Tốc độ xử lý trung bình**: $\le 2.2$ giây / hóa đơn trên chip Apple Silicon.

- 🔴 **KỊCH BẢN THẤT BẠI (FAIL)**: Nếu tỷ lệ đọc sai tiền > 5% hoặc AI hay bị ảo giác đọc nhầm tiền giảm giá thành tổng tiền $\rightarrow$ **DỪNG DỰ ÁN NGAY LẬP TỨC**. Không triển khai API, không đụng vào Server 2.
- 🟢 **KỊCH BẢN VƯỢT QUA (PASS)**: Khi các chỉ số thực tế được thẩm định bằng mắt đạt yêu cầu $\rightarrow$ **CHÍNH THỨC KÍCH HOẠT GIAI ĐOẠN 2**.

---

## 6. GIAI ĐOẠN 2: TỐI ƯU HÓA, ĐÓNG GÓI API VÀ TÍCH HỢP HỆ THỐNG (INTEGRATION - GATE 2)

> **Điều kiện tiên quyết**: Chỉ thực hiện khi Giai đoạn 1 đã có biên bản nghiệm thu **PASS**.

### 6.1. Phân tích lỗi (RCA) & Tối ưu hóa mô hình
- Lấy danh sách các hóa đơn bị đọc sai từ `results.csv` và `report.html` để phân tích nguyên nhân.
- Tinh chỉnh Prompt hoặc quy tắc hậu xử lý (Post-processing regex làm sạch số tiền, chuẩn hóa tên cửa hàng theo danh mục chuẩn trong DB).

---

### 6.2. Đóng gói thành Production-ready RESTful API (`app.py`)
Biến Mac Mini thành một AI Microservice nội bộ bằng FastAPI:

```python
# ~/ocr-service-gate2/app.py
import os
import json
import io
import time
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template

app = FastAPI(title="Gigamall AI OCR Service", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_PATH = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
print("[*] Nạp mô hình vào RAM...")
model, processor = load(MODEL_PATH)
config = model.config
print("[+] Sẵn sàng phục vụ API!")

EXTRACTION_PROMPT = """Bạn là chuyên gia bóc tách hóa đơn tại Gigamall. Hãy đọc ảnh hóa đơn và xuất ra chuỗi JSON duy nhất:
{
  "brand_name": "Tên thương hiệu",
  "outlet_name": "Tên cửa hàng",
  "bill_number": "Mã số hóa đơn",
  "bill_datetime": "YYYY-MM-DD HH:mm:ss",
  "bill_total": Số tiền thực trả (chỉ lấy số nguyên),
  "is_valid_bill": true/false
}"""

@app.post("/api/v1/extract-bill")
async def extract_bill(file: UploadFile = File(...)):
    start_time = time.time()
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")

        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": EXTRACTION_PROMPT}]}]
        prompt = apply_chat_template(processor, config, messages)

        output = generate(model, processor, prompt, image, max_tokens=512, temperature=0.1, verbose=False)
        clean = output.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)

        return {
            "success": True,
            "latency_seconds": round(time.time() - start_time, 2),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Lắng nghe trên IP mạng LAN ở port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### 6.3. Cấu hình Mạng LAN nội bộ cố định cho Mac Mini
1. Vào `System Settings` > `Network` trên Mac Mini, đặt IP tĩnh (ví dụ: `192.168.1.200`).
2. Khởi chạy server: `python app.py`. Dịch vụ mở tại: `http://192.168.1.200:8000/api/v1/extract-bill`.

---

### 6.4. Xây dựng Client tích hợp trên Server 2 (.NET Core)
Trên Backend .NET Core hiện tại của Server 2, tạo lớp dịch vụ gọi sang Mac Mini qua mạng LAN:

```csharp
// Server 2 (.NET Core Service)
using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading.Tasks;

public class MacMiniOcrService
{
    private readonly HttpClient _httpClient;
    private const string MAC_MINI_URL = "http://192.168.1.200:8000/api/v1/extract-bill";

    public MacMiniOcrService(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.Timeout = TimeSpan.FromSeconds(30);
    }

    public async Task<OcrResultDto> ProcessBillAsync(string imageFilePath)
    {
        using (var form = new MultipartFormDataContent())
        {
            byte[] fileBytes = await File.ReadAllBytesAsync(imageFilePath);
            var fileContent = new ByteArrayContent(fileBytes);
            fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse("image/jpeg");
            form.Add(fileContent, "file", Path.GetFileName(imageFilePath));

            var response = await _httpClient.PostAsync(MAC_MINI_URL, form);
            response.EnsureSuccessStatusCode();

            string json = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<OcrResultDto>(json);
        }
    }
}

public class OcrResultDto
{
    public bool success { get; set; }
    public double latency_seconds { get; set; }
    public BillDataDto data { get; set; }
}

public class BillDataDto
{
    public string brand_name { get; set; }
    public string outlet_name { get; set; }
    public string bill_number { get; set; }
    public string bill_datetime { get; set; }
    public decimal bill_total { get; set; }
    public bool is_valid_bill { get; set; }
}
```

---

### 6.5. CỔNG NGHIỆM THU TÍCH HỢP TOÀN TRÌNH (GATE 2 DECISION GATE)

Kiểm thử toàn trình E2E từ Mobile App $\rightarrow$ Server 2 (.NET Core) $\rightarrow$ Mac Mini $\rightarrow$ Server 1 (SQL Database):

| Chỉ số nghiệm thu Gate 2 | Ngưỡng bắt buộc (Threshold) | Cách đo lường |
| :--- | :---: | :--- |
| **Độ trễ toàn trình E2E** | $\le 2.5$ giây | Từ lúc Server 2 gửi request sang Mac Mini đến khi nhận kết quả |
| **Độ ổn định kết nối LAN** | $100\%$ | 500 request liên tục không bị drop connection hoặc timeout |
| **Tỷ lệ rò rỉ RAM trên Mac Mini** | $0\%$ | RAM ổn định $\le 6.5$ GB sau 500 request |
| **Tự động hóa tích điểm CRM** | Hoàn thành | Server 2 ghi nhận đúng vào `CRMGiGaBill` và gửi Push Notification |

- 🟢 **NGHIỆM THU THÀNH CÔNG**: Đưa hệ thống vào giai đoạn **Pilot chạy song song (Shadow Mode)** cùng hệ thống cũ trong vòng 2 tuần trước khi ngắt hoàn toàn Google Cloud Vision API.

---

## 7. BẢNG TỔNG KẾT PHÂN ĐỊNH TRÁCH NHIỆM 2 GIAI ĐOẠN

| Tiêu chí so sánh | Giai đoạn 1 (Mục tiêu 1) | Giai đoạn 2 (Mục tiêu 2) |
| :--- | :--- | :--- |
| **Trọng tâm duy nhất** | **Độ chính xác của Mô hình AI (Accuracy)** | **Hiệu năng & Tích hợp Hệ thống (Engineering)** |
| **Môi trường triển khai**| Offline, chạy script Python cục bộ trên Mac | Web Service API (FastAPI) + Mạng LAN nội bộ |
| **Server 2 (.NET Core)** | **Không can thiệp, không liên quan** | Viết code C# tích hợp gọi API |
| **Điều kiện thực hiện** | Bắt đầu ngay lập tức | **Chỉ làm khi Giai đoạn 1 ĐẠT CHỈ TIÊU** |
| **Hệ quả nếu thất bại** | Dừng dự án với chi phí lãng phí = 0 VNĐ | Tinh chỉnh timeout / hạ tầng mạng LAN |
