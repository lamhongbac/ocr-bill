"""
Ứng dụng Web Review Hóa đơn & Quản lý Vết kiểm toán (CRM Review & Audit Portal)
Phục vụ 3 User Story:
- US 1: Review workflow (Approve/Reject theo từng bill và batch)
- US 2: Inline correction (Sửa cửa hàng, số tiền, ngày giờ, số hóa đơn)
- US 3: Audit trail (Vết kiểm toán chi tiết cho Auditor)
Chạy trên FastAPI + MS-SQL Server (CLMHQ4GIGA)
"""
import base64
import io
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image

from fastapi import FastAPI, HTTPException, Query, Response, File, UploadFile, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

import db
import ocr_engine

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "TEST_IMAGES"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MASTER_OUTLETS_FILE = BASE_DIR / "master_outlets.json"

app = FastAPI(title="GigaMall CRM - OCR Bill Review & Audit Portal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- Models -----------------------------

class ReviewRequest(BaseModel):
    status: str                         # APPROVED | REJECTED
    actor: str = "CRM Admin"
    reject_reason: Optional[str] = None


class EditFieldsRequest(BaseModel):
    final_outlet_number: Optional[str] = None
    final_outlet_name: Optional[str] = None
    final_bill_number: Optional[str] = None
    final_datetime: Optional[str] = None
    final_total: Optional[int] = None
    actor: str = "CRM Admin"
    note: Optional[str] = None


class UploadBase64Request(BaseModel):
    image_base64: str
    filename: Optional[str] = None
    actor: str = "CRM Mobile"
    note: Optional[str] = "Tải lên từ Mobile qua API Base64"
    async_ocr: bool = True
    auto_ocr: bool = True


class TriggerOcrRequest(BaseModel):
    bill_ids: Optional[List[int]] = None       # Danh sách BillId cụ thể cần chạy (vd: [102, 105, 106])
    limit: int = 50                            # Nếu không truyền bill_ids, chạy tối đa N bill PENDING chưa OCR
    async_execution: bool = True               # true = chạy ngầm trả về mã ngay; false = chờ chạy xong trả kết quả
    actor: str = "CRM Backend API"


def _save_and_validate_image_bytes(
    image_bytes: bytes,
    original_filename: Optional[str] = None,
    custom_filename: Optional[str] = None
) -> tuple[Path, str]:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Dữ liệu ảnh rỗng")

    # Kiểm tra tính hợp lệ bằng PIL
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img_format = (img.format or "JPEG").lower()
            if img_format not in ("jpeg", "jpg", "png", "webp", "bmp"):
                raise HTTPException(status_code=400, detail=f"Định dạng ảnh không được hỗ trợ: {img_format}")
            detected_ext = ".png" if img_format == "png" else (".webp" if img_format == "webp" else ".jpg")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File không phải là ảnh hợp lệ: {str(e)}")

    # Ưu tiên 1: Tên file do CRM chỉ định tường minh qua custom_filename
    # Nếu chỉ có original_filename từ HTTP multipart header:
    # - Nếu là tên chung chung (upload, image, file, blob,...) -> OCR tự sinh tên
    # - Nếu là tên thực tế do app truyền -> Sử dụng tên đó
    chosen_name = (custom_filename or "").strip()
    if not chosen_name and original_filename:
        base_orig = Path(original_filename).stem.lower().strip()
        if base_orig not in ("", "upload", "image", "file", "blob", "unknown"):
            chosen_name = original_filename.strip()
    
    if chosen_name:
        # Làm sạch tên file, loại bỏ path traversal
        clean_name = os.path.basename(chosen_name).strip()
        # Đảm bảo có phần mở rộng hợp lệ
        if not re.search(r"\.(jpe?g|png|webp|bmp)$", clean_name, re.IGNORECASE):
            clean_name = f"{clean_name}{detected_ext}"
        saved_filename = clean_name
    else:
        # Ưu tiên 2: Trong trường hợp CRM không truyền tên file, OCR server tự sinh tên duy nhất
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:6]
        saved_filename = f"ocr_{timestamp_str}_{unique_suffix}{detected_ext}"

    # Đảm bảo không ghi đè nếu trùng tên file đã có trên đĩa
    save_path = UPLOAD_DIR / saved_filename
    if save_path.exists():
        stem = Path(saved_filename).stem
        ext = Path(saved_filename).suffix
        counter = 1
        while (UPLOAD_DIR / f"{stem}_{counter}{ext}").exists():
            counter += 1
        saved_filename = f"{stem}_{counter}{ext}"
        save_path = UPLOAD_DIR / saved_filename

    with open(save_path, "wb") as f:
        f.write(image_bytes)

    return save_path, saved_filename


def run_background_ocr(bill_id: int, image_path: Path):
    """Tiến trình ngầm bóc tách VLM OCR và cập nhật vào CSDL MS-SQL."""
    try:
        ocr_res = ocr_engine.process_bill_image(image_path)
    except Exception as e:
        ocr_res = {
            "raw_brand": "",
            "raw_outlet": "",
            "bill_number": "",
            "bill_datetime": None,
            "bill_total": 0,
            "is_valid_bill": False,
            "outlet_number": None,
            "resolved_outlet": None,
            "match_score": 0.0,
            "latency": 0.0,
            "raw_output": f"OCR Error: {str(e)}",
        }
    try:
        db.update_bill_ocr_result(bill_id, ocr_res)
    except Exception as db_err:
        print(f"[!] Lỗi cập nhật kết quả OCR ngầm cho bill {bill_id}: {db_err}")


def _parse_bool(val: Any, default: bool = True) -> bool:
    """Chuyển đổi chuỗi/giá trị form thành boolean linh hoạt."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return default


def _find_image_file(filename: str, image_path: Optional[str] = None) -> Optional[Path]:
    """Tìm đường dẫn tệp ảnh vật lý trên ổ cứng."""
    clean = os.path.basename(filename)
    p = UPLOAD_DIR / clean
    if p.exists():
        return p
    if image_path:
        p2 = BASE_DIR / image_path
        if p2.exists():
            return p2
    p3 = IMAGE_DIR / clean
    if p3.exists():
        return p3
    return None


def _run_batch_ocr_worker(bills: List[dict]):
    """Tiến trình ngầm bóc tách tuần tự danh sách hóa đơn theo yêu cầu từ CRM."""
    for b in bills:
        bill_id = b["BillId"]
        img_path = _find_image_file(b["Filename"], b.get("ImagePath"))
        if not img_path:
            db.update_bill_ocr_result(bill_id, {
                "raw_brand": "", "raw_outlet": "", "bill_number": "", "bill_datetime": None,
                "bill_total": 0, "is_valid_bill": False, "outlet_number": None,
                "resolved_outlet": None, "match_score": 0.0, "latency": 0.0,
                "raw_output": f"Không tìm thấy file ảnh {b['Filename']} trên đĩa"
            })
            continue
        try:
            ocr_res = ocr_engine.process_bill_image(img_path)
        except Exception as e:
            ocr_res = {
                "raw_brand": "", "raw_outlet": "", "bill_number": "", "bill_datetime": None,
                "bill_total": 0, "is_valid_bill": False, "outlet_number": None,
                "resolved_outlet": None, "match_score": 0.0, "latency": 0.0,
                "raw_output": f"OCR Error: {str(e)}"
            }
        try:
            db.update_bill_ocr_result(bill_id, ocr_res)
        except Exception as err:
            print(f"[!] Lỗi cập nhật DB cho bill {bill_id}: {err}")


# ----------------------------- API Endpoints -----------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/stats")
def get_stats():
    try:
        return db.get_bill_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bills")
def get_bills(status: str = "ALL", search: Optional[str] = None, page: int = 1, limit: int = 50):
    try:
        return db.get_bills(status=status, search=search, page=page, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bills/{bill_id}")
def get_bill_detail(bill_id: int):
    try:
        bill = db.get_bill_detail(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Không tìm thấy hóa đơn")
        # Format datetimes
        for k in ["OcrDateTime", "FinalDateTime", "ReviewedAt", "CreatedAt", "UpdatedAt"]:
            if bill.get(k) and isinstance(bill[k], datetime):
                bill[k] = bill[k].isoformat()
        for log in bill.get("audit_logs", []):
            if log.get("CreatedAt") and isinstance(log["CreatedAt"], datetime):
                log["CreatedAt"] = log["CreatedAt"].strftime("%d/%m/%Y %H:%M:%S")
        return bill
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bills/{bill_id}/review")
def review_bill(bill_id: int, req: ReviewRequest):
    try:
        db.update_bill_review(
            bill_id=bill_id,
            status=req.status.upper(),
            actor=req.actor,
            reject_reason=req.reject_reason
        )
        return {"success": True, "bill_id": bill_id, "status": req.status.upper()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/bills/{bill_id}/edit")
def edit_bill_fields(bill_id: int, req: EditFieldsRequest):
    try:
        updates = {}
        if req.final_outlet_number is not None:
            updates["final_outlet_number"] = req.final_outlet_number
        if req.final_outlet_name is not None:
            updates["final_outlet_name"] = req.final_outlet_name
        if req.final_bill_number is not None:
            updates["final_bill_number"] = req.final_bill_number
        if req.final_datetime is not None:
            updates["final_datetime"] = req.final_datetime
        if req.final_total is not None:
            updates["final_total"] = req.final_total

        num_changed = db.update_bill_fields(
            bill_id=bill_id,
            updates=updates,
            actor=req.actor,
            note=req.note
        )
        return {"success": True, "bill_id": bill_id, "fields_changed": num_changed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/outlets")
def get_master_outlets():
    if not MASTER_OUTLETS_FILE.exists():
        return []
    with open(MASTER_OUTLETS_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


@app.post("/api/v1/sync-outlets")
def sync_outlets_from_db():
    """
    API đồng bộ danh mục cửa hàng từ 2 bảng G_Outlet và G_Brand trong MS-SQL:
    - Truy vấn danh mục cửa hàng đang hoạt động (IsActive=1, IsUsed=1)
    - Ghi đè file master_outlets.json chuẩn UTF-8
    - Làm mới cache bộ nhớ của OCR Engine ngay lập tức mà không cần restart server
    """
    try:
        count = db.sync_master_outlets_file()
        ocr_engine.reload_master_outlets()
        return {
            "success": True,
            "count": count,
            "message": f"Đã đồng bộ thành công {count} cửa hàng từ bảng G_Outlet & G_Brand vào master_outlets.json!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đồng bộ danh mục cửa hàng: {str(e)}")


@app.get("/api/images/{filename:path}")
def get_image(filename: str):
    clean_name = os.path.basename(filename)
    # Tìm trong uploads trước, rồi đến TEST_IMAGES
    img_path = UPLOAD_DIR / clean_name
    if not img_path.exists():
        img_path = IMAGE_DIR / clean_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file ảnh")
    media_type = "image/jpeg"
    lower_name = clean_name.lower()
    if lower_name.endswith(".png"):
        media_type = "image/png"
    elif lower_name.endswith(".bmp"):
        media_type = "image/bmp"
    elif lower_name.endswith(".webp"):
        media_type = "image/webp"
    try:
        with Image.open(img_path) as im:
            fmt = (im.format or "").lower()
            if fmt == "bmp":
                media_type = "image/bmp"
            elif fmt == "png":
                media_type = "image/png"
            elif fmt in ("jpeg", "jpg"):
                media_type = "image/jpeg"
            elif fmt == "webp":
                media_type = "image/webp"
    except Exception:
        pass
    return FileResponse(img_path, media_type=media_type)


@app.post("/api/v1/bills/upload")
async def upload_bill_multipart(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    actor: str = Form("CRM Mobile"),
    note: Optional[str] = Form("Tải lên từ Mobile qua API Multipart"),
    async_ocr: Optional[str] = Form(None),
    auto_ocr: Optional[str] = Form(None)
):
    """
    API tiếp nhận ảnh chụp từ Mobile qua Multipart Form-Data:
    - Lưu ảnh an toàn xuống ổ đĩa máy chủ (uploads/) trong < 50ms
    - Mặc định async_ocr=True: Kích hoạt OCR chạy ngầm, phản hồi ngay lập tức cho Mobile/CRM (< 100ms)
    - Nếu async_ocr=False: Chờ chạy xong OCR rồi mới phản hồi (Sync)
    - Tạo bản ghi trong CSDL MS-SQL (bảng OcrBills) ở trạng thái PENDING
    """
    try:
        t0 = time.time()
        is_async = _parse_bool(async_ocr, default=True)
        is_auto = _parse_bool(auto_ocr, default=True)

        content = await file.read()
        save_path, saved_filename = _save_and_validate_image_bytes(
            content,
            original_filename=file.filename,
            custom_filename=filename
        )

        if not is_auto:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": "",
                "raw_outlet": "",
                "outlet_number": None,
                "resolved_outlet": None,
                "match_score": 0.0,
                "bill_number": "",
                "bill_datetime": None,
                "bill_total": 0,
                "is_valid_bill": False,
                "latency": 0.0,
                "raw_output": "Chỉ lưu ảnh, không chạy OCR",
                "actor": actor,
                "note": note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            save_latency = round(time.time() - t0, 3)
            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": "SKIPPED",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": f"Ảnh đã lưu an toàn xuống đĩa máy chủ trong {save_latency}s."
            }

        if is_async:
            # Luồng Fast Save: Lưu đĩa xong trả về ngay, chạy OCR ngầm
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": "",
                "raw_outlet": "",
                "outlet_number": None,
                "resolved_outlet": None,
                "match_score": 0.0,
                "bill_number": "",
                "bill_datetime": None,
                "bill_total": 0,
                "is_valid_bill": False,
                "latency": 0.0,
                "raw_output": "Đang xếp hàng bóc tách OCR ngầm...",
                "actor": actor,
                "note": note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            background_tasks.add_task(run_background_ocr, bill_id, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": "PROCESSING",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": f"Ảnh đã lưu an toàn xuống đĩa máy chủ trong {save_latency}s. AI đang chạy bóc tách ngầm."
            }
        else:
            # Luồng đồng bộ: Chờ OCR chạy xong mới phản hồi
            try:
                ocr_data = ocr_engine.process_bill_image(save_path)
                ocr_status = "SUCCESS"
            except Exception as ocr_err:
                ocr_status = "FAILED"
                ocr_data = {
                    "raw_brand": "",
                    "raw_outlet": "",
                    "bill_number": "",
                    "bill_datetime": None,
                    "bill_total": 0,
                    "is_valid_bill": False,
                    "outlet_number": None,
                    "resolved_outlet": None,
                    "match_score": 0.0,
                    "latency": 0.0,
                    "raw_output": f"OCR Error: {str(ocr_err)}",
                }

            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": ocr_data["raw_brand"],
                "raw_outlet": ocr_data["raw_outlet"],
                "outlet_number": ocr_data["outlet_number"],
                "resolved_outlet": ocr_data["resolved_outlet"],
                "match_score": ocr_data["match_score"],
                "bill_number": ocr_data["bill_number"],
                "bill_datetime": ocr_data["bill_datetime"],
                "bill_total": ocr_data["bill_total"],
                "is_valid_bill": ocr_data["is_valid_bill"],
                "latency": ocr_data["latency"],
                "raw_output": ocr_data["raw_output"],
                "actor": actor,
                "note": note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": ocr_status,
                "ocr_result": ocr_data,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": "Ảnh đã được lưu xuống đĩa máy chủ và hoàn tất bóc tách OCR." if ocr_status == "SUCCESS" else "Ảnh đã lưu vào đĩa thành công. OCR không đọc được, đã chuyển Admin duyệt tay."
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bills/upload-base64")
def upload_bill_base64(req: UploadBase64Request, background_tasks: BackgroundTasks):
    """
    API tiếp nhận ảnh chụp từ Mobile qua Base64 JSON:
    - Lưu ảnh an toàn xuống ổ đĩa máy chủ (uploads/) trong < 50ms
    - Mặc định req.async_ocr=True: Kích hoạt OCR chạy ngầm, phản hồi ngay lập tức cho Mobile/CRM (< 100ms)
    - Nếu req.async_ocr=False: Chờ chạy xong OCR rồi mới phản hồi (Sync)
    - Tạo bản ghi trong CSDL MS-SQL (bảng OcrBills) ở trạng thái PENDING
    """
    try:
        t0 = time.time()
        is_async = _parse_bool(req.async_ocr, default=True)
        is_auto = _parse_bool(req.auto_ocr, default=True)

        raw_b64 = req.image_base64.strip()
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(raw_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Chuỗi Base64 không hợp lệ")

        save_path, saved_filename = _save_and_validate_image_bytes(
            image_bytes,
            custom_filename=req.filename
        )

        if not is_auto:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": "",
                "raw_outlet": "",
                "outlet_number": None,
                "resolved_outlet": None,
                "match_score": 0.0,
                "bill_number": "",
                "bill_datetime": None,
                "bill_total": 0,
                "is_valid_bill": False,
                "latency": 0.0,
                "raw_output": "Chỉ lưu ảnh, không chạy OCR",
                "actor": req.actor,
                "note": req.note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            save_latency = round(time.time() - t0, 3)
            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": "SKIPPED",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": f"Ảnh đã lưu an toàn xuống đĩa máy chủ trong {save_latency}s."
            }

        if is_async:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": "",
                "raw_outlet": "",
                "outlet_number": None,
                "resolved_outlet": None,
                "match_score": 0.0,
                "bill_number": "",
                "bill_datetime": None,
                "bill_total": 0,
                "is_valid_bill": False,
                "latency": 0.0,
                "raw_output": "Đang xếp hàng bóc tách OCR ngầm...",
                "actor": req.actor,
                "note": req.note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            background_tasks.add_task(run_background_ocr, bill_id, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": "PROCESSING",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": f"Ảnh đã lưu an toàn xuống đĩa máy chủ trong {save_latency}s. AI đang chạy bóc tách ngầm."
            }
        else:
            try:
                ocr_data = ocr_engine.process_bill_image(save_path)
                ocr_status = "SUCCESS"
            except Exception as ocr_err:
                ocr_status = "FAILED"
                ocr_data = {
                    "raw_brand": "",
                    "raw_outlet": "",
                    "bill_number": "",
                    "bill_datetime": None,
                    "bill_total": 0,
                    "is_valid_bill": False,
                    "outlet_number": None,
                    "resolved_outlet": None,
                    "match_score": 0.0,
                    "latency": 0.0,
                    "raw_output": f"OCR Error: {str(ocr_err)}",
                }

            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "raw_brand": ocr_data["raw_brand"],
                "raw_outlet": ocr_data["raw_outlet"],
                "outlet_number": ocr_data["outlet_number"],
                "resolved_outlet": ocr_data["resolved_outlet"],
                "match_score": ocr_data["match_score"],
                "bill_number": ocr_data["bill_number"],
                "bill_datetime": ocr_data["bill_datetime"],
                "bill_total": ocr_data["bill_total"],
                "is_valid_bill": ocr_data["is_valid_bill"],
                "latency": ocr_data["latency"],
                "raw_output": ocr_data["raw_output"],
                "actor": req.actor,
                "note": req.note,
            }
            bill_id = db.insert_ocr_bill(bill_record)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "ocr_status": ocr_status,
                "ocr_result": ocr_data,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": "Ảnh đã được lưu xuống đĩa máy chủ và hoàn tất bóc tách OCR." if ocr_status == "SUCCESS" else "Ảnh đã lưu vào đĩa thành công. OCR không đọc được, đã chuyển Admin duyệt tay."
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/extract-bill")
async def extract_bill_alias(
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    image_number: Optional[str] = Form(None),
    mem_id: Optional[str] = Form(None)
):
    """
    Endpoint tương thích ngược theo đặc tả CRM Spec (/api/v1/extract-bill):
    - Nhận ảnh qua multipart/form-data
    - Ưu tiên sử dụng tên file do CRM truyền (filename hoặc image_number)
    - Nếu không truyền thì OCR tự động sinh tên file (ocr_YYYYMMDD_HHMMSS_xxxxxx)
    - Thực hiện OCR đồng bộ và trả về kết quả bóc tách ngay lập tức
    """
    try:
        t0 = time.time()
        content = await file.read()
        chosen_filename = filename or image_number
        save_path, saved_filename = _save_and_validate_image_bytes(
            content,
            original_filename=file.filename,
            custom_filename=chosen_filename
        )
        actor = f"CRM Member {mem_id}" if mem_id else "CRM Direct API"
        note = f"Bóc tách qua /api/v1/extract-bill (image_number: {image_number or 'N/A'})"

        try:
            ocr_data = ocr_engine.process_bill_image(save_path)
            ocr_status = "SUCCESS"
        except Exception as ocr_err:
            ocr_status = "FAILED"
            ocr_data = {
                "raw_brand": "",
                "raw_outlet": "",
                "bill_number": "",
                "bill_datetime": None,
                "bill_total": 0,
                "is_valid_bill": False,
                "outlet_number": None,
                "resolved_outlet": None,
                "match_score": 0.0,
                "latency": 0.0,
                "raw_output": f"OCR Error: {str(ocr_err)}",
            }

        bill_record = {
            "filename": saved_filename,
            "image_path": f"uploads/{saved_filename}",
            "status": "PENDING",
            "raw_brand": ocr_data["raw_brand"],
            "raw_outlet": ocr_data["raw_outlet"],
            "outlet_number": ocr_data["outlet_number"],
            "resolved_outlet": ocr_data["resolved_outlet"],
            "match_score": ocr_data["match_score"],
            "bill_number": ocr_data["bill_number"],
            "bill_datetime": ocr_data["bill_datetime"],
            "bill_total": ocr_data["bill_total"],
            "is_valid_bill": ocr_data["is_valid_bill"],
            "latency": ocr_data["latency"],
            "raw_output": ocr_data["raw_output"],
            "actor": actor,
            "note": note,
        }
        bill_id = db.insert_ocr_bill(bill_record)
        total_latency = round(time.time() - t0, 3)

        return {
            "success": (ocr_status == "SUCCESS"),
            "bill_id": bill_id,
            "filename": saved_filename,
            "image_url": f"/api/images/{saved_filename}",
            "latency_seconds": total_latency,
            "data": {
                "brand_name": ocr_data.get("raw_brand", ""),
                "outlet_name": ocr_data.get("raw_outlet", ""),
                "outlet_number": ocr_data.get("outlet_number"),
                "resolved_outlet": ocr_data.get("resolved_outlet"),
                "bill_number": ocr_data.get("bill_number", ""),
                "bill_datetime": ocr_data.get("bill_datetime"),
                "bill_total": ocr_data.get("bill_total", 0),
                "is_valid_bill": ocr_data.get("is_valid_bill", False),
                "match_score": ocr_data.get("match_score", 0.0),
                "confidence": ocr_data.get("match_score", 0.0)
            },
            "raw_output": ocr_data.get("raw_output", "")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bills/trigger-ocr")
def trigger_batch_ocr(req: TriggerOcrRequest, background_tasks: BackgroundTasks):
    """
    API dành cho Backend CRM kích hoạt bóc tách OCR theo nhu cầu:
    - Có thể truyền danh sách bill_ids cụ thể (vd: [102, 105, 106])
    - Hoặc không truyền bill_ids để tự động quét tối đa `limit` hóa đơn PENDING chưa từng OCR
    - Mặc định async_execution=True: Chạy ngầm và trả về mã ngay
    """
    try:
        if req.bill_ids:
            bills = db.get_bills_by_ids(req.bill_ids)
        else:
            bills = db.get_unprocessed_bills(limit=req.limit)

        if not bills:
            return {
                "success": True,
                "count": 0,
                "message": "Không tìm thấy hóa đơn nào phù hợp để bóc tách OCR.",
                "bills": []
            }

        bill_ids_found = [b["BillId"] for b in bills]

        if req.async_execution:
            background_tasks.add_task(_run_batch_ocr_worker, bills)
            return {
                "success": True,
                "status": "PROCESSING",
                "count": len(bills),
                "bill_ids": bill_ids_found,
                "message": f"Đã xếp hàng {len(bills)} hóa đơn vào tiến trình bóc tách OCR ngầm."
            }
        else:
            results = []
            for b in bills:
                bill_id = b["BillId"]
                img_path = _find_image_file(b["Filename"], b.get("ImagePath"))
                if not img_path:
                    ocr_res = {
                        "raw_brand": "", "raw_outlet": "", "bill_number": "", "bill_datetime": None,
                        "bill_total": 0, "is_valid_bill": False, "outlet_number": None,
                        "resolved_outlet": None, "match_score": 0.0, "latency": 0.0,
                        "raw_output": f"Không tìm thấy file ảnh {b['Filename']} trên đĩa"
                    }
                else:
                    try:
                        ocr_res = ocr_engine.process_bill_image(img_path)
                    except Exception as e:
                        ocr_res = {
                            "raw_brand": "", "raw_outlet": "", "bill_number": "", "bill_datetime": None,
                            "bill_total": 0, "is_valid_bill": False, "outlet_number": None,
                            "resolved_outlet": None, "match_score": 0.0, "latency": 0.0,
                            "raw_output": f"OCR Error: {str(e)}"
                        }
                db.update_bill_ocr_result(bill_id, ocr_res)
                results.append({"bill_id": bill_id, "ocr_result": ocr_res})

            return {
                "success": True,
                "status": "COMPLETED",
                "count": len(results),
                "results": results,
                "message": f"Đã bóc tách xong {len(results)} hóa đơn thành công."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bills/{bill_id}/trigger-ocr")
def trigger_single_bill_ocr(bill_id: int, background_tasks: BackgroundTasks, async_execution: bool = True):
    """
    API kích hoạt chạy OCR cho DUY NHẤT 1 hóa đơn cụ thể từ Backend CRM.
    """
    try:
        bill = db.get_bill_detail(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy hóa đơn ID {bill_id}")

        img_path = _find_image_file(bill["Filename"], bill.get("ImagePath"))
        if not img_path:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy file ảnh {bill['Filename']} trên đĩa")

        if async_execution:
            background_tasks.add_task(run_background_ocr, bill_id, img_path)
            return {
                "success": True,
                "bill_id": bill_id,
                "status": "PROCESSING",
                "message": f"Hóa đơn {bill_id} đã được đưa vào tiến trình bóc tách OCR ngầm."
            }
        else:
            try:
                ocr_res = ocr_engine.process_bill_image(img_path)
            except Exception as e:
                ocr_res = {
                    "raw_brand": "", "raw_outlet": "", "bill_number": "", "bill_datetime": None,
                    "bill_total": 0, "is_valid_bill": False, "outlet_number": None,
                    "resolved_outlet": None, "match_score": 0.0, "latency": 0.0,
                    "raw_output": f"OCR Error: {str(e)}"
                }
            db.update_bill_ocr_result(bill_id, ocr_res)
            return {
                "success": True,
                "bill_id": bill_id,
                "status": "COMPLETED",
                "ocr_result": ocr_res,
                "message": "Bóc tách OCR hoàn tất."
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit-logs")
def get_audit_logs(limit: int = 200):
    try:
        logs = db.get_all_audit_logs(limit=limit)
        for log in logs:
            if log.get("CreatedAt") and isinstance(log["CreatedAt"], datetime):
                log["CreatedAt"] = log["CreatedAt"].strftime("%d/%m/%Y %H:%M:%S")
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export-audit")
def export_audit_csv():
    try:
        logs = db.get_all_audit_logs(limit=1000)
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["AuditId", "BillId", "Filename", "Action", "FieldName", "OldValue", "NewValue", "Actor", "Note", "CreatedAt"])
        for l in logs:
            dt_str = l["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(l.get("CreatedAt"), datetime) else str(l.get("CreatedAt"))
            writer.writerow([
                l["AuditId"], l["BillId"], l["Filename"], l["Action"],
                l["FieldName"], l["OldValue"], l["NewValue"], l["Actor"],
                l["Note"], dt_str
            ])
        csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------- Single Page Application UI -----------------------------

@app.get("/", response_class=HTMLResponse)
def index_page():
    return HTML_CONTENT


HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GigaMall CRM - Duyệt Hóa đơn & Kiểm toán OCR</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg-base: #0b0f19;
  --bg-surface: #111827;
  --bg-card: #1f2937;
  --bg-card-hover: #263345;
  --border: #374151;
  --border-focus: #38bdf8;
  --text-main: #f9fafb;
  --text-muted: #9ca3af;
  --text-dim: #6b7280;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --accent: #38bdf8;
  --success: #10b981;
  --success-bg: rgba(16, 185, 129, 0.12);
  --danger: #ef4444;
  --danger-bg: rgba(239, 68, 68, 0.12);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.15);
  --font: 'Inter', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font); background: var(--bg-base); color: var(--text-main); height: 100vh; overflow: hidden; display: flex; flex-direction: column; }

/* Header */
header {
  height: 60px; min-height: 60px; background: rgba(17, 24, 39, 0.85); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px;
}
.brand { display: flex; align-items: center; gap: 12px; font-weight: 700; font-size: 16px; letter-spacing: -0.3px; }
.brand-badge { background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; }
.nav-tabs { display: flex; gap: 6px; }
.nav-tab {
  background: transparent; border: 1px solid transparent; color: var(--text-muted);
  padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.15s;
}
.nav-tab:hover { color: var(--text-main); background: rgba(255,255,255,0.04); }
.nav-tab.active { background: var(--bg-card); color: var(--accent); border-color: var(--border); }

.stats-bar { display: flex; gap: 8px; align-items: center; }
.pill { background: rgba(31, 41, 55, 0.8); border: 1px solid var(--border); padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 500; }
.pill b { font-family: var(--font-mono); }
.pill.pending b { color: var(--warning); }
.pill.approved b { color: var(--success); }
.pill.rejected b { color: var(--danger); }
.pill.edited b { color: #a855f7; }

/* Main Container */
main { flex: 1; display: flex; overflow: hidden; position: relative; }
.tab-content { display: none; width: 100%; height: 100%; }
.tab-content.active { display: flex; }

/* Inspector Mode (US 1 & US 2) */
#view-inspector { display: flex; width: 100%; height: 100%; }
.inspector-left {
  flex: 1.2; background: #000; position: relative; display: flex; align-items: center; justify-content: center;
  overflow: hidden; border-right: 1px solid var(--border);
}
.img-canvas-wrap { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; cursor: grab; }
.img-canvas-wrap:active { cursor: grabbing; }
.bill-img { max-width: 90%; max-height: 90%; object-fit: contain; transition: transform 0.2s cubic-bezier(0.2,0,0,1); user-select: none; }
.img-toolbar {
  position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
  background: rgba(17, 24, 39, 0.9); backdrop-filter: blur(8px); border: 1px solid var(--border);
  border-radius: 999px; display: flex; gap: 4px; padding: 4px 8px; z-index: 10;
}
.tool-btn {
  background: transparent; border: 0; color: #fff; width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 15px; transition: background 0.15s;
}
.tool-btn:hover { background: rgba(255,255,255,0.15); }

.inspector-right {
  flex: 1; max-width: 600px; min-width: 460px; background: var(--bg-surface);
  display: flex; flex-direction: column; overflow-y: auto;
}

.panel-head {
  padding: 18px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;
}
.bill-title { font-size: 16px; font-weight: 700; }
.bill-sub { font-size: 12px; color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px; }
.status-tag { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.status-tag.PENDING { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245,158,11,0.3); }
.status-tag.APPROVED { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16,185,129,0.3); }
.status-tag.REJECTED { background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(239,68,68,0.3); }

.form-body { padding: 20px 24px; flex: 1; display: flex; flex-direction: column; gap: 16px; }

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-label { display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: var(--text-muted); }
.ocr-hint { font-size: 11px; color: var(--text-dim); }
.ocr-hint b { color: var(--accent); }

.input-box {
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main);
  padding: 10px 14px; border-radius: 8px; font-size: 14px; font-family: var(--font); width: 100%; transition: border 0.15s;
}
.input-box:focus { border-color: var(--border-focus); outline: none; }
.input-box.diff-highlight { border-color: var(--warning); background: rgba(245, 158, 11, 0.05); }

.amount-input { font-size: 18px; font-weight: 700; font-family: var(--font-mono); color: #fb923c; }

/* Diff Alert Card */
.diff-alert {
  background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px;
  padding: 10px 14px; font-size: 12px; color: #fde68a; display: none; align-items: center; gap: 8px;
}
.diff-alert.active { display: flex; }

/* Bottom Action Bar */
.action-bar {
  padding: 16px 24px; border-top: 1px solid var(--border); background: var(--bg-surface);
  display: flex; gap: 10px; align-items: center; justify-content: space-between;
}
.btn {
  padding: 10px 18px; border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer; border: 0;
  display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s;
}
.btn-approve { background: var(--success); color: #fff; }
.btn-approve:hover { background: #059669; }
.btn-reject { background: var(--danger); color: #fff; }
.btn-reject:hover { background: #dc2626; }
.btn-save { background: var(--primary); color: #fff; }
.btn-save:hover { background: var(--primary-hover); }
.btn-sec { background: var(--bg-card); color: var(--text-main); border: 1px solid var(--border); }
.btn-sec:hover { background: var(--bg-card-hover); }

/* Navigation buttons */
.nav-btns { display: flex; gap: 6px; }

/* Mini Audit Timeline inside Inspector */
.inspector-audit {
  border-top: 1px solid var(--border); padding: 16px 24px; background: rgba(0,0,0,0.15); max-height: 180px; overflow-y: auto;
}
.audit-title { font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.audit-item { font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; gap: 8px; }
.audit-item:last-child { border-bottom: 0; }
.audit-time { color: var(--text-dim); font-family: var(--font-mono); min-width: 120px; }
.audit-desc b { color: var(--accent); }

/* Table View (Batch Mode) */
#view-batch { width: 100%; height: 100%; flex-direction: column; overflow: hidden; }
.batch-toolbar {
  padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--bg-surface);
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
}
.filter-tabs { display: flex; gap: 6px; }
.filter-btn {
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted);
  padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.filter-btn:hover { color: var(--text-main); }
.filter-btn.active { background: var(--accent); color: #000; border-color: var(--accent); }

.table-wrap { flex: 1; overflow: auto; padding: 16px 24px; }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
th {
  background: var(--bg-surface); color: var(--text-muted); text-align: left; padding: 10px 14px;
  font-weight: 600; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 2;
}
td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
tr:hover td { background: rgba(255,255,255,0.02); cursor: pointer; }
.thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border); }

/* Auditor View */
#view-audit { width: 100%; height: 100%; flex-direction: column; overflow: hidden; }
.audit-toolbar {
  padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--bg-surface);
  display: flex; justify-content: space-between; align-items: center;
}
.tag-action { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; font-family: var(--font-mono); }
.tag-action.UPDATE_FIELD { background: rgba(168, 85, 247, 0.2); color: #c084fc; }
.tag-action.APPROVE { background: var(--success-bg); color: var(--success); }
.tag-action.REJECT { background: var(--danger-bg); color: var(--danger); }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
  display: none; align-items: center; justify-content: center; z-index: 999;
}
.modal-card {
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 14px;
  width: 440px; padding: 24px; display: flex; flex-direction: column; gap: 16px;
}
.modal-card.wide { width: 520px; }
.modal-card h3 { font-size: 16px; font-weight: 700; }

/* Upload Modal Styles */
.dropzone {
  border: 2px dashed rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 30px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.02);
}
.dropzone:hover, .dropzone.dragover {
  border-color: var(--accent);
  background: rgba(56, 189, 248, 0.06);
}
.dropzone-icon { font-size: 36px; margin-bottom: 8px; }
.dropzone-text { font-size: 13px; color: var(--text-muted); }
.dropzone-text b { color: var(--accent); }
.upload-preview {
  display: none;
  max-height: 180px;
  max-width: 100%;
  object-fit: contain;
  margin: 10px auto;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.upload-status-box {
  display: none;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--border);
}
.btn-upload-nav {
  background: linear-gradient(135deg, #0284c7, #2563eb);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.2s;
}
.btn-upload-nav:hover { opacity: 0.9; }
</style>
</head>
<body>

<header>
  <div class="brand">
    <span class="brand-badge">GigaMall CRM</span>
    <span>Duyệt Hóa Đơn & Kiểm Toán OCR</span>
  </div>

  <div class="nav-tabs">
    <button class="nav-tab active" data-tab="inspector" id="tab-inspector">🔍 Soi chi tiết (Inspector)</button>
    <button class="nav-tab" data-tab="batch" id="tab-batch">📋 Danh sách tổng hợp</button>
    <button class="nav-tab" data-tab="audit" id="tab-audit">📜 Nhật ký kiểm toán (Auditor)</button>
  </div>

  <div class="stats-bar">
    <button class="btn-upload-nav" id="btn-open-upload">
      <span>📤 Tải lên hóa đơn</span>
    </button>
    <div class="pill">Tổng: <b id="stat-total">0</b></div>
    <div class="pill pending">Chờ duyệt: <b id="stat-pending">0</b></div>
    <div class="pill approved">Đã duyệt: <b id="stat-approved">0</b></div>
    <div class="pill rejected">Từ chối: <b id="stat-rejected">0</b></div>
    <div class="pill edited">Đã sửa tay: <b id="stat-edited">0</b></div>
  </div>
</header>

<main>
  <!-- TAB 1: INSPECTOR (US 1 & US 2) -->
  <section class="tab-content active" id="content-inspector">
    <div class="inspector-left">
      <div class="img-canvas-wrap" id="canvas-wrap">
        <img class="bill-img" id="bill-img" src="" alt="Hóa đơn">
      </div>
      <div class="img-toolbar">
        <button class="tool-btn" id="btn-zoom-in" title="Phóng to (+)">🔍+</button>
        <button class="tool-btn" id="btn-zoom-out" title="Thu nhỏ (-)">🔍-</button>
        <button class="tool-btn" id="btn-rotate-left" title="Xoay trái 90°">↺</button>
        <button class="tool-btn" id="btn-rotate-right" title="Xoay phải 90°">↻</button>
        <button class="tool-btn" id="btn-zoom-reset" title="Đặt lại kích thước">⟲</button>
      </div>
    </div>

    <div class="inspector-right">
      <div class="panel-head">
        <div>
          <div class="bill-title" id="panel-filename">Đang tải...</div>
          <div class="bill-sub">ID: <span id="panel-billid">#–</span> | AI Latency: <span id="panel-latency">–</span>s</div>
        </div>
        <span class="status-tag PENDING" id="panel-status">PENDING</span>
      </div>

      <div class="form-body">
        <div class="diff-alert" id="diff-alert">
          ⚠️ <span>Admin đã sửa số tiền khác kết quả AI đọc ban đầu!</span>
        </div>

        <div class="form-group">
          <label class="form-label">
            <span>Cửa hàng / Gian hàng (Outlet)</span>
            <span class="ocr-hint">AI đọc: <b id="ocr-outlet">–</b></span>
          </label>
          <input list="outlets-datalist" class="input-box" id="inp-outlet-name" placeholder="Tìm tên cửa hàng...">
          <datalist id="outlets-datalist"></datalist>
        </div>

        <div class="form-group">
          <label class="form-label">
            <span>Số tiền thanh toán hợp lệ (VNĐ)</span>
            <span class="ocr-hint">AI đọc: <b id="ocr-total">–</b></span>
          </label>
          <input type="text" class="input-box amount-input" id="inp-total" placeholder="0">
        </div>

        <div class="form-group">
          <label class="form-label">
            <span>Mã số hóa đơn (Bill No)</span>
            <span class="ocr-hint">AI đọc: <b id="ocr-billno">–</b></span>
          </label>
          <input type="text" class="input-box" id="inp-billno" placeholder="Số bill...">
        </div>

        <div class="form-group">
          <label class="form-label">
            <span>Ngày giờ giao dịch</span>
            <span class="ocr-hint">AI đọc: <b id="ocr-datetime">–</b></span>
          </label>
          <input type="text" class="input-box" id="inp-datetime" placeholder="YYYY-MM-DD HH:mm:ss">
        </div>

        <div class="form-group">
          <label class="form-label">Ghi chú điều chỉnh (Auditor note)</label>
          <input type="text" class="input-box" id="inp-note" placeholder="Nhập lý do nếu có sửa đổi...">
        </div>
      </div>

      <div class="inspector-audit">
        <div class="audit-title">Lịch sử kiểm toán của bill này (Audit History)</div>
        <div id="inspector-audit-list">
          <div style="color: var(--text-dim); font-size: 11px;">Chưa có lịch sử thay đổi.</div>
        </div>
      </div>

      <div class="action-bar">
        <div class="nav-btns">
          <button class="btn btn-sec" id="btn-prev" title="Phím mũi tên Trái">◀ Trước</button>
          <button class="btn btn-sec" id="btn-next" title="Phím mũi tên Phải">Tiếp ▶</button>
        </div>

        <div style="display: flex; gap: 8px;">
          <button class="btn btn-save" id="btn-save" title="Phím Ctrl+S">💾 Lưu sửa đổi</button>
          <button class="btn btn-reject" id="btn-reject" title="Phím R">❌ Từ chối [R]</button>
          <button class="btn btn-approve" id="btn-approve" title="Phím A">✅ Phê duyệt [A]</button>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: BATCH TABLE (US 1) -->
  <section class="tab-content" id="content-batch">
    <div id="view-batch">
      <div class="batch-toolbar">
        <div class="filter-tabs">
          <button class="filter-btn active" data-filter="ALL">Tất cả (<span id="cnt-all">0</span>)</button>
          <button class="filter-btn" data-filter="PENDING">Chờ duyệt (<span id="cnt-pending">0</span>)</button>
          <button class="filter-btn" data-filter="APPROVED">Đã duyệt (<span id="cnt-approved">0</span>)</button>
          <button class="filter-btn" data-filter="REJECTED">Đã từ chối (<span id="cnt-rejected">0</span>)</button>
        </div>
        <input type="text" class="input-box" id="batch-search" placeholder="🔍 Tìm theo tên file, quán, mã bill..." style="max-width: 280px; padding: 6px 12px; font-size: 12px;">
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 50px;">Ảnh</th>
              <th>Tên file</th>
              <th>Quán AI đọc</th>
              <th>Quán Duyệt (CRM)</th>
              <th>Tiền AI</th>
              <th>Tiền Duyệt</th>
              <th>Trạng thái</th>
              <th>Người duyệt</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody id="batch-tbody">
            <tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 40px;">Đang tải danh sách...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- TAB 3: AUDITOR VIEW (US 3) -->
  <section class="tab-content" id="content-audit">
    <div id="view-audit">
      <div class="audit-toolbar">
        <div>
          <b style="font-size: 15px;">Toàn bộ Nhật ký Kiểm toán (System Audit Trail)</b>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Ghi nhận mọi thao tác phê duyệt, từ chối và thay đổi dữ liệu của Admin</div>
        </div>
        <button class="btn btn-sec" id="btn-export-audit">⬇ Xuất Báo cáo CSV</button>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Thời gian</th>
              <th>Tên file ảnh</th>
              <th>Hành động</th>
              <th>Trường thay đổi</th>
              <th>Giá trị cũ</th>
              <th>Giá trị mới sau sửa</th>
              <th>Người thực hiện</th>
              <th>Ghi chú</th>
            </tr>
          </thead>
          <tbody id="audit-tbody">
            <tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 40px;">Đang tải nhật ký...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</main>

<!-- Reject Modal -->
<div class="modal-overlay" id="modal-reject">
  <div class="modal-card">
    <h3>Từ chối hóa đơn</h3>
    <div class="form-group">
      <label class="form-label">Chọn lý do từ chối:</label>
      <select class="input-box" id="sel-reject-reason">
        <option value="Hóa đơn mờ không đọc được">Hóa đơn mờ không đọc được</option>
        <option value="Ảnh chụp không phải hóa đơn mua hàng">Ảnh chụp không phải hóa đơn mua hàng</option>
        <option value="Hóa đơn không thuộc TTTM Gigamall">Hóa đơn không thuộc TTTM Gigamall</option>
        <option value="Hóa đơn quá hạn tích điểm">Hóa đơn quá hạn tích điểm</option>
        <option value="Hóa đơn trùng lặp đã tích điểm trước đó">Hóa đơn trùng lặp đã tích điểm trước đó</option>
      </select>
    </div>
    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
      <button class="btn btn-sec" id="btn-cancel-reject">Hủy</button>
      <button class="btn btn-reject" id="btn-confirm-reject">Xác nhận Từ chối</button>
    </div>
  </div>
</div>

<!-- Upload Bill Modal -->
<div class="modal-overlay" id="modal-upload">
  <div class="modal-card wide">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h3>📤 Tải lên hóa đơn riêng lẻ & Chạy OCR</h3>
      <button id="btn-close-upload-x" style="background:none; border:none; color:var(--text-muted); font-size:18px; cursor:pointer;">✕</button>
    </div>

    <!-- Dropzone -->
    <div class="dropzone" id="upload-dropzone">
      <div class="dropzone-icon">📷</div>
      <div class="dropzone-text">Kéo thả ảnh hóa đơn vào đây hoặc <b>Nhấn để chọn file</b></div>
      <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">Hỗ trợ JPEG, PNG, BMP, WebP (Tối đa 20MB)</div>
      <img id="upload-preview-img" class="upload-preview" alt="Preview">
    </div>
    <input type="file" id="upload-file-input" accept="image/jpeg,image/png,image/bmp,image/webp" style="display: none;">

    <div class="form-group">
      <label class="form-label">
        <span>Tên file tùy chọn (CRM / Bill Code)</span>
        <span style="font-size: 11px; color: var(--text-dim);">Để trống = OCR tự sinh tên</span>
      </label>
      <input type="text" class="input-box" id="inp-upload-filename" placeholder="Ví dụ: CRM_HD_123456.jpg">
    </div>

    <div class="form-group">
      <label class="form-label">Ghi chú tải lên (Admin note):</label>
      <input type="text" class="input-box" id="inp-upload-note" value="Tải lên trực tiếp từ giao diện Admin">
    </div>

    <div class="upload-status-box" id="upload-status-box"></div>

    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 6px;">
      <button class="btn btn-sec" id="btn-cancel-upload">Đóng</button>
      <button class="btn btn-save" id="btn-submit-upload" style="background: linear-gradient(135deg, #0284c7, #2563eb);">⚡ Tải lên & Chạy OCR ngay</button>
    </div>
  </div>
</div>

<script>
// State
let allBills = [];
let currentIdx = 0;
let masterOutlets = [];
let imgScale = 1;
let imgRotate = 0;
let currentFilter = "ALL";

// Elements
const billImg = document.getElementById("bill-img");
const diffAlert = document.getElementById("diff-alert");

// Load Initial Data
async function init() {
  await loadOutlets();
  await loadStats();
  await loadBills();
  if (allBills.length > 0) {
    showBill(0);
  }
}

async function loadOutlets() {
  try {
    const res = await fetch("/api/outlets");
    masterOutlets = await res.json();
    const dl = document.getElementById("outlets-datalist");
    dl.innerHTML = masterOutlets.map(o => `<option value="${o.outlet_name}">${o.outlet_number} - ${o.brand_name || ''}</option>`).join("");
  } catch(e) { console.error(e); }
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    document.getElementById("stat-total").textContent = data.total || 0;
    document.getElementById("stat-pending").textContent = data.pending || 0;
    document.getElementById("stat-approved").textContent = data.approved || 0;
    document.getElementById("stat-rejected").textContent = data.rejected || 0;
    document.getElementById("stat-edited").textContent = data.manual_edited || 0;

    document.getElementById("cnt-all").textContent = data.total || 0;
    document.getElementById("cnt-pending").textContent = data.pending || 0;
    document.getElementById("cnt-approved").textContent = data.approved || 0;
    document.getElementById("cnt-rejected").textContent = data.rejected || 0;
  } catch(e) { console.error(e); }
}

async function loadBills() {
  try {
    const res = await fetch(`/api/bills?status=${currentFilter}&limit=150`);
    const data = await res.json();
    allBills = data.items || [];
    renderBatchTable();
  } catch(e) { console.error(e); }
}

function showBill(idx) {
  if (idx < 0 || idx >= allBills.length) return;
  currentIdx = idx;
  const b = allBills[idx];

  // Reset image transform
  imgScale = 1; imgRotate = 0;
  updateImgTransform();

  billImg.src = `/api/images/${b.Filename}`;
  document.getElementById("panel-filename").textContent = b.Filename;
  document.getElementById("panel-billid").textContent = `#${b.BillId}`;
  document.getElementById("panel-latency").textContent = b.OcrLatency || "–";

  const st = document.getElementById("panel-status");
  st.textContent = b.Status;
  st.className = `status-tag ${b.Status}`;

  // OCR Hints
  document.getElementById("ocr-outlet").textContent = b.OcrOutletName || "Chưa nhận diện";
  document.getElementById("ocr-total").textContent = (b.OcrTotal || 0).toLocaleString("vi-VN") + " đ";
  document.getElementById("ocr-billno").textContent = b.OcrBillNumber || "–";
  document.getElementById("ocr-datetime").textContent = b.OcrDateTime ? b.OcrDateTime.replace("T", " ") : "–";

  // Editable Form inputs
  document.getElementById("inp-outlet-name").value = b.FinalOutletName || b.OcrOutletName || "";
  document.getElementById("inp-total").value = (b.FinalTotal !== null ? b.FinalTotal : b.OcrTotal || 0).toLocaleString("vi-VN");
  document.getElementById("inp-billno").value = b.FinalBillNumber || b.OcrBillNumber || "";
  document.getElementById("inp-datetime").value = b.FinalDateTime ? b.FinalDateTime.replace("T", " ") : (b.OcrDateTime ? b.OcrDateTime.replace("T", " ") : "");
  document.getElementById("inp-note").value = "";

  checkDiff(b);
  loadBillAuditLogs(b.BillId);
}

function checkDiff(b) {
  const currentTotal = parseInt(document.getElementById("inp-total").value.replace(/[^0-9]/g, "")) || 0;
  const isDiff = currentTotal !== (b.OcrTotal || 0);
  diffAlert.classList.toggle("active", isDiff);
  document.getElementById("inp-total").classList.toggle("diff-highlight", isDiff);
}

document.getElementById("inp-total").addEventListener("input", e => {
  const digits = e.target.value.replace(/[^0-9]/g, "");
  e.target.value = digits ? parseInt(digits, 10).toLocaleString("vi-VN") : "0";
  if (allBills[currentIdx]) checkDiff(allBills[currentIdx]);
});

async function loadBillAuditLogs(billId) {
  try {
    const res = await fetch(`/api/bills/${billId}`);
    const data = await res.json();
    const list = document.getElementById("inspector-audit-list");
    if (!data.audit_logs || data.audit_logs.length === 0) {
      list.innerHTML = `<div style="color: var(--text-dim); font-size: 11px;">Chưa có lịch sử thay đổi.</div>`;
      return;
    }
    list.innerHTML = data.audit_logs.map(l => `
      <div class="audit-item">
        <span class="audit-time">${l.CreatedAt}</span>
        <span class="audit-desc"><b>${l.Actor}</b> [${l.Action}] ${l.FieldName}: <s>${l.OldValue || "null"}</s> ➔ <span style="color:var(--success)">${l.NewValue}</span> ${l.Note ? `(${l.Note})` : ''}</span>
      </div>
    `).join("");
  } catch(e) { console.error(e); }
}

// Actions
document.getElementById("btn-approve").addEventListener("click", async () => {
  await submitReview("APPROVED");
});

document.getElementById("btn-reject").addEventListener("click", () => {
  document.getElementById("modal-reject").style.display = "flex";
});

document.getElementById("btn-cancel-reject").addEventListener("click", () => {
  document.getElementById("modal-reject").style.display = "none";
});

document.getElementById("btn-confirm-reject").addEventListener("click", async () => {
  const reason = document.getElementById("sel-reject-reason").value;
  document.getElementById("modal-reject").style.display = "none";
  await submitReview("REJECTED", reason);
});

async function submitReview(status, rejectReason = null) {
  const b = allBills[currentIdx];
  if (!b) return;

  // Auto-save any form edits first
  await saveEdits(false);

  const res = await fetch(`/api/bills/${b.BillId}/review`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ status, actor: "CRM Admin", reject_reason: rejectReason })
  });

  if (res.ok) {
    b.Status = status;
    showBill(currentIdx);
    await loadStats();
    // Auto advance to next bill
    if (currentIdx < allBills.length - 1) {
      showBill(currentIdx + 1);
    }
  }
}

document.getElementById("btn-save").addEventListener("click", () => saveEdits(true));

async function saveEdits(showPrompt = true) {
  const b = allBills[currentIdx];
  if (!b) return;

  const total = parseInt(document.getElementById("inp-total").value.replace(/[^0-9]/g, "")) || 0;
  const outletName = document.getElementById("inp-outlet-name").value.trim();
  const billNo = document.getElementById("inp-billno").value.trim();
  const dt = document.getElementById("inp-datetime").value.trim();
  const note = document.getElementById("inp-note").value.trim();

  // Find outlet number if matching master outlets
  const matched = masterOutlets.find(o => o.outlet_name.toLowerCase() === outletName.toLowerCase());
  const outletNum = matched ? matched.outlet_number : b.FinalOutletNumber;

  const payload = {
    final_outlet_name: outletName,
    final_outlet_number: outletNum,
    final_total: total,
    final_bill_number: billNo,
    final_datetime: dt,
    actor: "CRM Admin",
    note: note
  };

  const res = await fetch(`/api/bills/${b.BillId}/edit`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    b.FinalOutletName = outletName;
    b.FinalTotal = total;
    b.FinalBillNumber = billNo;
    b.FinalDateTime = dt;
    if (showPrompt) {
      alert("✅ Đã lưu thay đổi vào CSDL và ghi nhận vết kiểm toán!");
      loadBillAuditLogs(b.BillId);
      loadStats();
    }
  }
}

// Image tools
function updateImgTransform() {
  billImg.style.transform = `scale(${imgScale}) rotate(${imgRotate}deg)`;
}
document.getElementById("btn-zoom-in").addEventListener("click", () => { imgScale = Math.min(imgScale + 0.25, 3.5); updateImgTransform(); });
document.getElementById("btn-zoom-out").addEventListener("click", () => { imgScale = Math.max(imgScale - 0.25, 0.5); updateImgTransform(); });
document.getElementById("btn-rotate-right").addEventListener("click", () => { imgRotate = (imgRotate + 90) % 360; updateImgTransform(); });
document.getElementById("btn-rotate-left").addEventListener("click", () => { imgRotate = (imgRotate - 90 + 360) % 360; updateImgTransform(); });
document.getElementById("btn-zoom-reset").addEventListener("click", () => { imgScale = 1; imgRotate = 0; updateImgTransform(); });

// Keyboard shortcuts
window.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft") { document.getElementById("btn-prev").click(); }
  if (e.key === "ArrowRight") { document.getElementById("btn-next").click(); }
  if (e.key === "a" || e.key === "A") { document.getElementById("btn-approve").click(); }
  if (e.key === "r" || e.key === "R") { document.getElementById("btn-reject").click(); }
});

document.getElementById("btn-prev").addEventListener("click", () => { if (currentIdx > 0) showBill(currentIdx - 1); });
document.getElementById("btn-next").addEventListener("click", () => { if (currentIdx < allBills.length - 1) showBill(currentIdx + 1); });

// Navigation tabs
document.querySelectorAll(".nav-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    const target = tab.dataset.tab;
    document.getElementById(`content-${target}`).classList.add("active");
    if (target === "batch") renderBatchTable();
    if (target === "audit") renderGlobalAudit();
  });
});

// Batch table
function renderBatchTable() {
  const tbody = document.getElementById("batch-tbody");
  if (!allBills || allBills.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 40px;">Không có hóa đơn nào</td></tr>`;
    return;
  }
  tbody.innerHTML = allBills.map((b, i) => `
    <tr onclick="switchToInspector(${i})">
      <td><img src="/api/images/${b.Filename}" class="thumb" loading="lazy"></td>
      <td><b>${b.Filename}</b></td>
      <td>${b.OcrOutletName || '<span style="color:var(--text-dim)">–</span>'}</td>
      <td style="color: var(--accent); font-weight: 600;">${b.FinalOutletName || b.OcrOutletName || '–'}</td>
      <td>${(b.OcrTotal || 0).toLocaleString('vi-VN')} đ</td>
      <td style="color: #fb923c; font-weight: 700;">${(b.FinalTotal !== null ? b.FinalTotal : b.OcrTotal || 0).toLocaleString('vi-VN')} đ</td>
      <td><span class="status-tag ${b.Status}">${b.Status}</span></td>
      <td style="color: var(--text-muted);">${b.ReviewedBy || '–'}</td>
      <td><button class="btn btn-sec" style="padding: 4px 10px; font-size: 11px;">🔍 Soi bill</button></td>
    </tr>
  `).join("");
}

function switchToInspector(idx) {
  document.getElementById("tab-inspector").click();
  showBill(idx);
}

// Global Audit
async function renderGlobalAudit() {
  try {
    const res = await fetch("/api/audit-logs?limit=200");
    const logs = await res.json();
    const tbody = document.getElementById("audit-tbody");
    if (!logs || logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 40px;">Chưa có nhật ký kiểm toán nào</td></tr>`;
      return;
    }
    tbody.innerHTML = logs.map(l => `
      <tr>
        <td style="font-family: var(--font-mono); color: var(--text-dim);">${l.CreatedAt}</td>
        <td><b>${l.Filename}</b></td>
        <td><span class="tag-action ${l.Action}">${l.Action}</span></td>
        <td style="color: var(--accent); font-weight: 600;">${l.FieldName || '–'}</td>
        <td style="color: var(--danger);"><s>${l.OldValue || 'null'}</s></td>
        <td style="color: var(--success); font-weight: 600;">${l.NewValue || 'null'}</td>
        <td><b>${l.Actor}</b></td>
        <td style="color: var(--text-muted);">${l.Note || ''}</td>
      </tr>
    `).join("");
  } catch(e) { console.error(e); }
}

// Upload Modal Logic
const modalUpload = document.getElementById("modal-upload");
const uploadDropzone = document.getElementById("upload-dropzone");
const uploadFileInput = document.getElementById("upload-file-input");
const uploadPreviewImg = document.getElementById("upload-preview-img");
const uploadStatusBox = document.getElementById("upload-status-box");
const btnSubmitUpload = document.getElementById("btn-submit-upload");
let selectedUploadFile = null;

document.getElementById("btn-open-upload").addEventListener("click", () => {
  modalUpload.style.display = "flex";
  resetUploadForm();
});

document.getElementById("btn-close-upload-x").addEventListener("click", () => {
  modalUpload.style.display = "none";
});

document.getElementById("btn-cancel-upload").addEventListener("click", () => {
  modalUpload.style.display = "none";
});

function resetUploadForm() {
  selectedUploadFile = null;
  uploadFileInput.value = "";
  uploadPreviewImg.src = "";
  uploadPreviewImg.style.display = "none";
  uploadStatusBox.style.display = "none";
  uploadStatusBox.innerHTML = "";
  document.getElementById("inp-upload-filename").value = "";
  btnSubmitUpload.disabled = false;
  btnSubmitUpload.innerHTML = "⚡ Tải lên & Chạy OCR ngay";
}

uploadDropzone.addEventListener("click", () => uploadFileInput.click());

uploadDropzone.addEventListener("dragover", e => {
  e.preventDefault();
  uploadDropzone.classList.add("dragover");
});

uploadDropzone.addEventListener("dragleave", () => {
  uploadDropzone.classList.remove("dragover");
});

uploadDropzone.addEventListener("drop", e => {
  e.preventDefault();
  uploadDropzone.classList.remove("dragover");
  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
    handleFileSelected(e.dataTransfer.files[0]);
  }
});

uploadFileInput.addEventListener("change", e => {
  if (e.target.files && e.target.files[0]) {
    handleFileSelected(e.target.files[0]);
  }
});

function handleFileSelected(file) {
  selectedUploadFile = file;
  if (!document.getElementById("inp-upload-filename").value) {
    document.getElementById("inp-upload-filename").value = file.name;
  }
  const reader = new FileReader();
  reader.onload = ev => {
    uploadPreviewImg.src = ev.target.result;
    uploadPreviewImg.style.display = "block";
  };
  reader.readAsDataURL(file);
}

btnSubmitUpload.addEventListener("click", async () => {
  if (!selectedUploadFile) {
    alert("Vui lòng chọn hoặc kéo thả 1 file ảnh hóa đơn!");
    return;
  }

  btnSubmitUpload.disabled = true;
  btnSubmitUpload.innerHTML = "⏳ Đang tải ảnh & AI đang đọc...";
  uploadStatusBox.style.display = "block";
  uploadStatusBox.style.borderColor = "var(--border)";
  uploadStatusBox.style.color = "var(--accent)";
  uploadStatusBox.innerHTML = "🔄 Đang lưu ảnh vào đĩa và kích hoạt mô hình AI OCR...";

  try {
    const formData = new FormData();
    formData.append("file", selectedUploadFile);
    formData.append("actor", "Admin Portal UI");
    formData.append("note", document.getElementById("inp-upload-note").value || "Tải lên từ giao diện Admin");
    formData.append("async_ocr", "false"); // Chạy đồng bộ để nhận kết quả OCR ngay lập tức

    const customName = document.getElementById("inp-upload-filename").value.trim();
    if (customName) {
      formData.append("filename", customName);
    }

    const res = await fetch("/api/v1/bills/upload", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.detail || data.message || "Tải lên hoặc chạy OCR thất bại");
    }

    uploadStatusBox.style.borderColor = "var(--success)";
    uploadStatusBox.style.color = "var(--success)";
    uploadStatusBox.innerHTML = `✅ <b>Thành công!</b> Đã bóc tách xong bill <b>#${data.bill_id}</b>. Đang chuyển sang màn hình soi duyệt...`;

    // Nạp lại danh sách hóa đơn và nhảy trực tiếp đến bill vừa upload
    setTimeout(async () => {
      modalUpload.style.display = "none";
      await loadStats();
      await loadBills();
      
      // Tìm index của bill vừa upload
      const newIdx = allBills.findIndex(b => b.BillId === data.bill_id);
      if (newIdx !== -1) {
        switchToInspector(newIdx);
      } else {
        switchToInspector(allBills.length - 1);
      }
    }, 1000);

  } catch (err) {
    console.error(err);
    uploadStatusBox.style.borderColor = "var(--danger)";
    uploadStatusBox.style.color = "var(--danger)";
    uploadStatusBox.innerHTML = `❌ <b>Lỗi:</b> ${err.message}`;
    btnSubmitUpload.disabled = false;
    btnSubmitUpload.innerHTML = "⚡ Thử lại";
  }
});

init();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_review:app", host="0.0.0.0", port=8000, reload=True)
