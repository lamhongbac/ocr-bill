"""
Ứng dụng Web Review Hóa đơn & Quản lý Vết kiểm toán (CRM Review & Audit Portal)
Phục vụ 3 User Story:
- US 1: Review workflow (Approve/Reject theo từng bill và batch)
- US 2: Inline correction (Sửa cửa hàng, số tiền, ngày giờ, số hóa đơn)
- US 3: Audit trail (Vết kiểm toán chi tiết cho Auditor)
Chạy trên FastAPI + MS-SQL Server (CLMHQ4GIGA)
"""
import base64
import hashlib
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

from fastapi import FastAPI, HTTPException, Query, Response, File, UploadFile, Form, BackgroundTasks, Header
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
    duplicate_action: Optional[str] = None  # "warn" (mặc định), "allow" (cố tình upload lại), "reject" (từ chối do spam/phá)


class TriggerOcrRequest(BaseModel):
    bill_ids: Optional[List[int]] = None       # Danh sách BillId cụ thể cần chạy (vd: [102, 105, 106])
    limit: int = 50                            # Nếu không truyền bill_ids, chạy tối đa N bill PENDING chưa OCR
    async_execution: bool = True               # true = chạy ngầm trả về mã ngay; false = chờ chạy xong trả kết quả
    actor: str = "CRM Backend API"


def _resolve_duplicate_action(action_str: Optional[str], header_str: Optional[str] = None) -> str:
    """Xác định hành vi xử lý trùng lặp: warn (mặc định), allow (cho phép tải lại), reject (chặn do phá/spam)."""
    raw = (action_str or header_str or "warn").strip().lower()
    if raw in ("reject", "block", "deny", "refuse"):
        return "reject"
    if raw in ("allow", "force", "permit", "reupload", "accept"):
        return "allow"
    return "warn"


def _get_duplicate_note_and_action(is_duplicate: bool, dup_action: str, duplicate_bill: Optional[dict], note: Optional[str]):
    """Chuẩn hóa ghi chú và nhãn action cho hóa đơn trùng lặp."""
    if not is_duplicate or not duplicate_bill:
        return note, None
    if dup_action == "allow":
        return f"[CRM CHO PHÉP UPLOAD LẠI - Bill #{duplicate_bill['BillId']}] {note or ''}".strip(), "ALLOWED"
    return f"[TRÙNG LẶP Bill #{duplicate_bill['BillId']}] {note or ''}".strip(), "WARNED"


def _insert_bill_atomic(bill_record: dict, save_path: Path) -> int:
    """
    Đảm bảo tính nguyên tử (Atomicity) tuyệt đối giữa việc ghi tệp vào đĩa cứng và lưu bản ghi vào CSDL:
    - Nếu lưu CSDL thành công: Trả về BillId vừa tạo.
    - Nếu lưu CSDL gặp lỗi (mất kết nối, lỗi ràng buộc): Tự động xóa tệp ảnh vừa ghi trên đĩa (Rollback)
      để không bao giờ để lại tệp rác mồ côi hoặc không khớp giữa đĩa và CSDL.
    """
    try:
        return db.insert_ocr_bill(bill_record)
    except Exception as e:
        if save_path and isinstance(save_path, Path) and save_path.exists():
            try:
                save_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Lỗi ghi nhận CSDL MS-SQL: {str(e)}")


def _build_duplicate_rejection_response(
    saved_filename: str,
    file_hash: str,
    duplicate_bill: dict,
    actor: str,
    note: Optional[str],
    t0: float
) -> dict:
    """Từ chối nhận hóa đơn trùng lặp do nghi vấn spam/phá từ CRM, ghi nhận audit và không chạy OCR."""
    bill_record = {
        "filename": saved_filename,
        "image_path": f"uploads/{saved_filename}",
        "status": "REJECTED",
        "file_hash": file_hash,
        "raw_brand": duplicate_bill.get("OcrBrand") or "",
        "raw_outlet": duplicate_bill.get("OcrOutletName") or "",
        "outlet_number": duplicate_bill.get("FinalOutletNumber"),
        "resolved_outlet": duplicate_bill.get("FinalOutletName"),
        "match_score": 0.0,
        "bill_number": duplicate_bill.get("FinalBillNumber") or "",
        "bill_datetime": duplicate_bill.get("FinalDateTime"),
        "bill_total": duplicate_bill.get("FinalTotal") or 0,
        "is_valid_bill": False,
        "latency": 0.0,
        "raw_output": f"Cảnh báo: Trùng với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']}). Tự động từ chối theo cấu hình CRM (chống spam/phá).",
        "actor": actor,
        "note": f"[CRM TỪ CHỐI - PHÁ/SPAM] Phát hiện trùng lặp với Bill #{duplicate_bill['BillId']}: {note or ''}",
        "reject_reason": f"Hóa đơn trùng lặp 100% với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']}). Hệ thống từ chối nhận ảnh theo cấu hình CRM (chống spam/phá).",
        "reviewed_by": actor,
        "reviewed_at": datetime.now()
    }
    bill_id = _insert_bill_atomic(bill_record, UPLOAD_DIR / saved_filename)
    db.insert_ocr_audit_log(
        bill_id=bill_id,
        actor=actor,
        action="REJECT_DUPLICATE_CRM",
        field_name="Status",
        old_value="PENDING",
        new_value="REJECTED",
        note=f"Tự động từ chối do trùng lặp với Bill #{duplicate_bill['BillId']} theo chính sách CRM"
    )
    save_latency = round(time.time() - t0, 3)
    return {
        "success": False,
        "bill_id": bill_id,
        "filename": saved_filename,
        "image_url": f"/api/images/{saved_filename}",
        "file_path": f"uploads/{saved_filename}",
        "is_duplicate": True,
        "duplicate_action": "reject",
        "action_taken": "REJECTED",
        "review_status": "REJECTED",
        "reject_reason": bill_record["reject_reason"],
        "duplicate_info": duplicate_bill,
        "ocr_status": "SKIPPED",
        "ocr_result": None,
        "save_latency_seconds": save_latency,
        "message": f"⛔ TỪ CHỐI: Hóa đơn này trùng lặp với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']}). Hệ thống đã từ chối nhận ảnh theo yêu cầu chống spam/phá của CRM."
    }


def _save_and_validate_image_bytes(
    image_bytes: bytes,
    original_filename: Optional[str] = None,
    custom_filename: Optional[str] = None
) -> tuple[Path, str, str]:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Dữ liệu ảnh rỗng")

    # Tính mã SHA-256 nội dung ảnh để chống trùng lặp (Anti-duplicate)
    file_hash = hashlib.sha256(image_bytes).hexdigest()

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

    # Đảm bảo không ghi đè nếu trùng tên file đã có trên đĩa hoặc trong CSDL
    save_path = UPLOAD_DIR / saved_filename
    stem = Path(saved_filename).stem
    ext = Path(saved_filename).suffix
    counter = 1
    while save_path.exists() or db.bill_exists_by_filename(saved_filename):
        saved_filename = f"{stem}_{counter}{ext}"
        save_path = UPLOAD_DIR / saved_filename
        counter += 1

    with open(save_path, "wb") as f:
        f.write(image_bytes)

    return save_path, saved_filename, file_hash


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
def get_bills(
    status: str = "ALL",
    edit_status: Optional[str] = None,
    brand: Optional[str] = None,
    outlet: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    try:
        return db.get_bills(
            status=status,
            edit_status=edit_status,
            brand=brand,
            outlet=outlet,
            search=search,
            page=page,
            limit=limit
        )
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
def review_bill(bill_id: int, req: ReviewRequest, x_actor: Optional[str] = Header(None)):
    try:
        actor_name = x_actor.strip() if x_actor and x_actor.strip() else (req.actor or "CRM Admin")
        db.update_bill_review(
            bill_id=bill_id,
            status=req.status.upper(),
            actor=actor_name,
            reject_reason=req.reject_reason
        )
        return {"success": True, "bill_id": bill_id, "status": req.status.upper(), "actor": actor_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/bills/{bill_id}/edit")
def edit_bill_fields(bill_id: int, req: EditFieldsRequest, x_actor: Optional[str] = Header(None)):
    try:
        actor_name = x_actor.strip() if x_actor and x_actor.strip() else (req.actor or "CRM Admin")
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
            actor=actor_name,
            note=req.note
        )
        return {"success": True, "bill_id": bill_id, "fields_changed": num_changed, "actor": actor_name}
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


CACHE_DIR = UPLOAD_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/images/{filename:path}")
def get_image(filename: str):
    clean_name = os.path.basename(filename)
    if clean_name.startswith("._"):
        clean_name = clean_name[2:]

    # Tìm trong uploads trước, rồi đến TEST_IMAGES
    img_path = UPLOAD_DIR / clean_name
    if not img_path.exists():
        img_path = IMAGE_DIR / clean_name
    if not img_path.exists():
        # Fallback tìm kiếm theo stem nếu đổi đuôi mở rộng
        stem = Path(clean_name).stem
        for alt_ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            for folder in (UPLOAD_DIR, IMAGE_DIR):
                cand = folder / f"{stem}{alt_ext}"
                if cand.exists():
                    img_path = cand
                    break
            if img_path and img_path.exists():
                break

    if not img_path or not img_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file ảnh")

    try:
        with Image.open(img_path) as im:
            fmt = (im.format or "").upper()
            # Trình duyệt web hiện đại (Chrome/Safari) KHÔNG hỗ trợ hiển thị định dạng BMP thuần trong thẻ <img>.
            # GigaMall POS xuất ảnh định dạng BMP (dù đặt tên là .png).
            # Tự động convert BMP sang JPEG chất lượng cao và cache lại để hiển thị tức thì.
            if fmt == "BMP":
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached_jpg = CACHE_DIR / f"{Path(clean_name).stem}_bmp_converted.jpg"
                if not cached_jpg.exists() or cached_jpg.stat().st_mtime < img_path.stat().st_mtime:
                    im.convert("RGB").save(cached_jpg, format="JPEG", quality=90)
                return FileResponse(cached_jpg, media_type="image/jpeg")
            elif fmt == "PNG":
                return FileResponse(img_path, media_type="image/png")
            elif fmt in ("JPEG", "JPG"):
                return FileResponse(img_path, media_type="image/jpeg")
            elif fmt == "WEBP":
                return FileResponse(img_path, media_type="image/webp")
    except Exception:
        pass

    return FileResponse(img_path, media_type="image/jpeg")


@app.post("/api/v1/bills/upload")
async def upload_bill_multipart(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    actor: str = Form("CRM Mobile"),
    note: Optional[str] = Form("Tải lên từ Mobile qua API Multipart"),
    async_ocr: Optional[str] = Form(None),
    auto_ocr: Optional[str] = Form(None),
    duplicate_action: Optional[str] = Form(None),
    x_duplicate_action: Optional[str] = Header(None)
):
    """
    API tiếp nhận ảnh chụp từ Mobile qua Multipart Form-Data:
    - Lưu ảnh an toàn xuống ổ đĩa máy chủ (uploads/) trong < 50ms
    - Mặc định async_ocr=True: Kích hoạt OCR chạy ngầm, phản hồi ngay lập tức cho Mobile/CRM (< 100ms)
    - Nếu async_ocr=False: Chờ chạy xong OCR rồi mới phản hồi (Sync)
    - Kiểm soát trùng lặp từ CRM qua duplicate_action / Header X-Duplicate-Action:
        + 'warn' (mặc định): Lưu bill PENDING, cảnh báo is_duplicate: True
        + 'allow': Cho phép upload lại bổ sung (cố tình), ghi nhận log rõ ràng
        + 'reject': Từ chối lập tức (chống spam/phá), không chạy OCR, lưu REJECTED
    """
    try:
        t0 = time.time()
        is_async = _parse_bool(async_ocr, default=True)
        is_auto = _parse_bool(auto_ocr, default=True)

        content = await file.read()
        save_path, saved_filename, file_hash = _save_and_validate_image_bytes(
            content,
            original_filename=file.filename,
            custom_filename=filename
        )

        # Kiểm tra trùng lặp ảnh (Duplicate Check)
        duplicate_bill = db.find_duplicate_bill(file_hash)
        is_duplicate = duplicate_bill is not None
        dup_action = _resolve_duplicate_action(duplicate_action, x_duplicate_action)

        if is_duplicate and dup_action == "reject":
            return _build_duplicate_rejection_response(
                saved_filename=saved_filename,
                file_hash=file_hash,
                duplicate_bill=duplicate_bill,
                actor=actor,
                note=note,
                t0=t0
            )

        final_note, action_taken = _get_duplicate_note_and_action(is_duplicate, dup_action, duplicate_bill, note)

        if not is_auto:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "file_hash": file_hash,
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
                "raw_output": "Chỉ lưu ảnh, không chạy OCR" if not is_duplicate else f"Cảnh báo: Trùng với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']})",
                "actor": actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            save_latency = round(time.time() - t0, 3)
            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": "SKIPPED",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Ảnh đã lưu an toàn trong {save_latency}s." + (
                        f" ⚠️ CẢNH BÁO: Trùng lặp với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                            f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                        )
                    )
                )
            }

        if is_async:
            # Luồng Fast Save: Lưu đĩa xong trả về ngay, chạy OCR ngầm
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "file_hash": file_hash,
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
                "raw_output": "Đang xếp hàng bóc tách OCR ngầm..." if not is_duplicate else f"Cảnh báo: Trùng với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']})",
                "actor": actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            background_tasks.add_task(run_background_ocr, bill_id, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": "PROCESSING",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Ảnh đã lưu trong {save_latency}s. AI đang chạy ngầm." + (
                        f" ⚠️ CẢNH BÁO: Trùng lặp với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                            f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                        )
                    )
                )
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
                "file_hash": file_hash,
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
                "raw_output": ocr_data["raw_output"] if not is_duplicate else f"[{action_taken} Bill #{duplicate_bill['BillId']}] {ocr_data['raw_output']}",
                "actor": actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": ocr_status,
                "ocr_result": ocr_data,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Bóc tách OCR hoàn tất trong {save_latency}s." + (
                        f" ⚠️ CẢNH BÁO: Hóa đơn này TRÙNG LẶP với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                            f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                        )
                    )
                )
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bills/upload-base64")
def upload_bill_base64(
    req: UploadBase64Request,
    background_tasks: BackgroundTasks,
    x_duplicate_action: Optional[str] = Header(None)
):
    """
    API tiếp nhận ảnh chụp từ Mobile qua Base64 JSON:
    - Lưu ảnh an toàn xuống ổ đĩa máy chủ (uploads/) trong < 50ms
    - Mặc định req.async_ocr=True: Kích hoạt OCR chạy ngầm, phản hồi ngay lập tức cho Mobile/CRM (< 100ms)
    - Nếu req.async_ocr=False: Chờ chạy xong OCR rồi mới phản hồi (Sync)
    - Kiểm soát trùng lặp từ CRM qua req.duplicate_action / Header X-Duplicate-Action:
        + 'warn' (mặc định): Lưu bill PENDING, cảnh báo is_duplicate: True
        + 'allow': Cho phép upload lại bổ sung (cố tình), ghi nhận log rõ ràng
        + 'reject': Từ chối lập tức (chống spam/phá), không chạy OCR, lưu REJECTED
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

        save_path, saved_filename, file_hash = _save_and_validate_image_bytes(
            image_bytes,
            custom_filename=req.filename
        )

        # Kiểm tra trùng lặp ảnh (Duplicate Check)
        duplicate_bill = db.find_duplicate_bill(file_hash)
        is_duplicate = duplicate_bill is not None
        dup_action = _resolve_duplicate_action(req.duplicate_action, x_duplicate_action)

        if is_duplicate and dup_action == "reject":
            return _build_duplicate_rejection_response(
                saved_filename=saved_filename,
                file_hash=file_hash,
                duplicate_bill=duplicate_bill,
                actor=req.actor,
                note=req.note,
                t0=t0
            )

        final_note, action_taken = _get_duplicate_note_and_action(is_duplicate, dup_action, duplicate_bill, req.note)

        if not is_auto:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "file_hash": file_hash,
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
                "raw_output": "Chỉ lưu ảnh, không chạy OCR" if not is_duplicate else f"Cảnh báo: Trùng với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']})",
                "actor": req.actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            save_latency = round(time.time() - t0, 3)
            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": "SKIPPED",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Ảnh đã lưu an toàn trong {save_latency}s." + (
                        f" ⚠️ CẢNH BÁO: Trùng lặp với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                            f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                        )
                    )
                )
            }

        if is_async:
            bill_record = {
                "filename": saved_filename,
                "image_path": f"uploads/{saved_filename}",
                "status": "PENDING",
                "file_hash": file_hash,
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
                "raw_output": "Đang xếp hàng bóc tách OCR ngầm..." if not is_duplicate else f"Cảnh báo: Trùng với Bill #{duplicate_bill['BillId']} ({duplicate_bill['Filename']})",
                "actor": req.actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            background_tasks.add_task(run_background_ocr, bill_id, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": "PROCESSING",
                "ocr_result": None,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Ảnh đã lưu an toàn xuống đĩa máy chủ trong {save_latency}s. AI đang chạy bóc tách ngầm." + (
                        f" ⚠️ CẢNH BÁO: Trùng lặp với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                            f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                        )
                    )
                )
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
                "file_hash": file_hash,
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
                "raw_output": ocr_data["raw_output"] if not is_duplicate else f"[{action_taken} Bill #{duplicate_bill['BillId']}] {ocr_data['raw_output']}",
                "actor": req.actor,
                "note": final_note,
            }
            bill_id = _insert_bill_atomic(bill_record, save_path)
            save_latency = round(time.time() - t0, 3)

            return {
                "success": True,
                "bill_id": bill_id,
                "filename": saved_filename,
                "image_url": f"/api/images/{saved_filename}",
                "file_path": f"uploads/{saved_filename}",
                "is_duplicate": is_duplicate,
                "duplicate_action": dup_action if is_duplicate else None,
                "action_taken": action_taken,
                "duplicate_info": duplicate_bill,
                "ocr_status": ocr_status,
                "ocr_result": ocr_data,
                "review_status": "PENDING",
                "save_latency_seconds": save_latency,
                "message": (
                    f"Ảnh đã được lưu và hoàn tất bóc tách OCR trong {save_latency}s." if ocr_status == "SUCCESS" else "Ảnh đã lưu vào đĩa thành công. OCR không đọc được, đã chuyển Admin duyệt tay."
                ) + (
                    f" ⚠️ CẢNH BÁO: Hóa đơn này TRÙNG LẶP với Bill #{duplicate_bill['BillId']}!" if is_duplicate and action_taken == "WARNED" else (
                        f" ✅ CRM đã chủ động cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else ""
                    )
                )
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
    mem_id: Optional[str] = Form(None),
    duplicate_action: Optional[str] = Form(None),
    x_duplicate_action: Optional[str] = Header(None)
):
    """
    Endpoint tương thích ngược theo đặc tả CRM Spec (/api/v1/extract-bill):
    - Nhận ảnh qua multipart/form-data
    - Ưu tiên sử dụng tên file do CRM truyền (filename hoặc image_number)
    - Nếu không truyền thì OCR tự động sinh tên file (ocr_YYYYMMDD_HHMMSS_xxxxxx)
    - Kiểm soát trùng lặp từ CRM qua duplicate_action / Header X-Duplicate-Action:
        + 'warn' (mặc định): Trả về cảnh báo is_duplicate: True, action_taken: 'WARNED'
        + 'allow': Cho phép upload lại bổ sung (cố tình), action_taken: 'ALLOWED'
        + 'reject': Từ chối lập tức (chống spam/phá), không chạy OCR, action_taken: 'REJECTED'
    - Thực hiện OCR đồng bộ và trả về kết quả bóc tách ngay lập tức
    """
    try:
        t0 = time.time()
        content = await file.read()
        chosen_filename = filename or image_number
        save_path, saved_filename, file_hash = _save_and_validate_image_bytes(
            content,
            original_filename=file.filename,
            custom_filename=chosen_filename
        )
        duplicate_bill = db.find_duplicate_bill(file_hash)
        is_duplicate = duplicate_bill is not None
        dup_action = _resolve_duplicate_action(duplicate_action, x_duplicate_action)

        actor = f"CRM Member {mem_id}" if mem_id else "CRM Direct API"
        base_note = f"Bóc tách qua /api/v1/extract-bill (image_number: {image_number or 'N/A'})"

        if is_duplicate and dup_action == "reject":
            res = _build_duplicate_rejection_response(
                saved_filename=saved_filename,
                file_hash=file_hash,
                duplicate_bill=duplicate_bill,
                actor=actor,
                note=base_note,
                t0=t0
            )
            res["data"] = None
            return res

        final_note, action_taken = _get_duplicate_note_and_action(is_duplicate, dup_action, duplicate_bill, base_note)

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
            "file_hash": file_hash,
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
            "raw_output": ocr_data["raw_output"] if not is_duplicate else f"[{action_taken} Bill #{duplicate_bill['BillId']}] {ocr_data['raw_output']}",
            "actor": actor,
            "note": final_note,
        }
        bill_id = _insert_bill_atomic(bill_record, save_path)
        total_latency = round(time.time() - t0, 3)

        return {
            "success": (ocr_status == "SUCCESS"),
            "bill_id": bill_id,
            "filename": saved_filename,
            "image_url": f"/api/images/{saved_filename}",
            "is_duplicate": is_duplicate,
            "duplicate_action": dup_action if is_duplicate else None,
            "action_taken": action_taken,
            "duplicate_info": duplicate_bill,
            "message": (
                f"Cảnh báo: Bill này đã từng được tải lên trước đó (Upload lại - Bill #{duplicate_bill['BillId']})." if is_duplicate and action_taken == "WARNED" else (
                    f"Thành công. CRM đã cho phép tải lại dù trùng với Bill #{duplicate_bill['BillId']}." if is_duplicate and action_taken == "ALLOWED" else "Thành công"
                )
            ),
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
            "raw_output": bill_record["raw_output"]
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
.tool-btn.active { background: #38bdf8 !important; color: #000 !important; font-weight: bold; }

/* Loupe Lens for Region Zoom */
.loupe-lens {
  position: absolute; width: 190px; height: 190px; border: 3px solid #38bdf8;
  border-radius: 50%; box-shadow: 0 0 25px rgba(0,0,0,0.85), inset 0 0 10px rgba(56, 189, 248, 0.4);
  pointer-events: none; display: none; z-index: 100; background-repeat: no-repeat;
  background-color: #000;
}

.inspector-right {
  flex: 1; max-width: 600px; min-width: 460px; background: var(--bg-surface);
  display: flex; flex-direction: column; overflow-y: auto; transition: background 0.3s, border-color 0.3s;
}
.inspector-right.bill-locked {
  border-left: 3px solid var(--success);
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.08) 0%, var(--bg-surface) 220px);
}
.locked-banner {
  background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 8px;
  padding: 10px 14px; font-size: 13px; color: #6ee7b7; display: none; align-items: center; gap: 8px; font-weight: 600;
}
.locked-banner.active { display: flex; }
.input-box:disabled {
  background: rgba(255, 255, 255, 0.03); color: #94a3b8; border-color: rgba(255, 255, 255, 0.08); cursor: not-allowed;
}
.batch-pagination {
  flex-shrink: 0;
  padding: 12px 24px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text-muted);
  background: var(--bg-surface);
  box-shadow: 0 -4px 14px rgba(0, 0, 0, 0.35);
  z-index: 10;
}
.batch-pagination .btn {
  padding: 5px 12px;
  font-size: 12px;
}
.batch-pagination .btn:disabled {
  opacity: 0.35;
  cursor: not-allowed !important;
  pointer-events: none;
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

/* Inline Save Success Banner */
.save-banner {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.18) 0%, rgba(5, 150, 105, 0.1) 100%);
  border: 1px solid rgba(16, 185, 129, 0.45);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
  color: #6ee7b7;
  display: none;
  align-items: center;
  gap: 10px;
  animation: bannerFadeIn 0.3s ease-out;
}
.save-banner.active { display: flex; }
@keyframes bannerFadeIn {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Coalesce & 3-Tier Audit Comparison Styles */
.coalesce-guide-box {
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #bae6fd;
}
.audit-field-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s;
}
.audit-field-card:hover {
  border-color: rgba(255, 255, 255, 0.16);
}
.audit-field-card.is-edited {
  border-color: rgba(255, 184, 108, 0.45);
  background: rgba(255, 184, 108, 0.035);
}
.field-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.field-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 6px;
}
.source-badge {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.source-badge.ai {
  background: rgba(56, 189, 248, 0.12);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.3);
}
.source-badge.edited {
  background: rgba(255, 184, 108, 0.15);
  color: #ffb86c;
  border: 1px solid rgba(255, 184, 108, 0.4);
}
.field-cols {
  display: flex;
  gap: 10px;
  align-items: center;
}
.ai-evidence-box {
  width: 42%;
  min-width: 140px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px;
  padding: 7px 10px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ai-evidence-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.ai-evidence-val {
  color: var(--accent);
  font-weight: 600;
  word-break: break-all;
}
.admin-input-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}
.btn-revert-ai {
  position: absolute;
  right: 6px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: var(--text-muted);
  font-size: 10.5px;
  padding: 3px 7px;
  border-radius: 5px;
  cursor: pointer;
  display: none;
  transition: all 0.15s;
}
.btn-revert-ai:hover {
  background: var(--accent);
  color: #000;
}
.field-final-preview {
  font-size: 11.5px;
  color: var(--text-dim);
  display: flex;
  justify-content: space-between;
  padding-top: 4px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
}
.field-final-val {
  font-weight: 700;
  color: var(--text-main);
}

/* Toast Notifications Container (Modern floating alerts) */
.toast-container {
  position: fixed;
  top: 72px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 9999;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  min-width: 320px;
  max-width: 440px;
  padding: 14px 18px;
  border-radius: 10px;
  background: rgba(17, 24, 39, 0.96);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 15px rgba(16, 185, 129, 0.15);
  color: var(--text-main);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  transform: translateX(120%);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
  opacity: 0;
}
.toast.show {
  transform: translateX(0);
  opacity: 1;
}
.toast-success {
  border-color: rgba(16, 185, 129, 0.5);
  background: linear-gradient(135deg, rgba(6, 78, 59, 0.95) 0%, rgba(17, 24, 39, 0.98) 60%);
}
.toast-info {
  border-color: rgba(56, 189, 248, 0.5);
  background: linear-gradient(135deg, rgba(12, 74, 110, 0.95) 0%, rgba(17, 24, 39, 0.98) 60%);
}
.toast-warning {
  border-color: rgba(245, 158, 11, 0.5);
  background: linear-gradient(135deg, rgba(120, 53, 15, 0.95) 0%, rgba(17, 24, 39, 0.98) 60%);
}
.toast-error {
  border-color: rgba(239, 68, 68, 0.5);
  background: linear-gradient(135deg, rgba(127, 29, 29, 0.95) 0%, rgba(17, 24, 39, 0.98) 60%);
}
.toast-icon {
  font-size: 20px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}
.toast-content { flex: 1; }
.toast-title { font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 3px; }
.toast-msg { font-size: 12px; color: #cbd5e1; line-height: 1.4; }
.toast-close {
  background: none; border: none; color: #94a3b8; font-size: 16px; cursor: pointer; padding: 0;
  line-height: 1; margin-left: 6px; transition: color 0.15s;
}
.toast-close:hover { color: #fff; }

@keyframes auditPulse {
  0% { background: rgba(16, 185, 129, 0.35); }
  50% { background: rgba(16, 185, 129, 0.15); }
  100% { background: transparent; }
}
.audit-item.highlight-new {
  animation: auditPulse 2.5s ease-out;
  border-left: 3px solid var(--success);
  padding-left: 6px;
}

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
.btn-save.saving { background: #334155 !important; color: #94a3b8 !important; cursor: wait !important; pointer-events: none; }
.btn-save.saved { background: #059669 !important; color: #fff !important; box-shadow: 0 0 15px rgba(16, 185, 129, 0.4); }
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
#content-batch.active { flex-direction: column; overflow: hidden; }
#view-batch {
  width: 100%; height: 100%; display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden;
}
.batch-toolbar {
  padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--bg-surface);
  display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-shrink: 0;
}
.filter-tabs { display: flex; gap: 6px; }
.filter-btn {
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted);
  padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.filter-btn:hover { color: var(--text-main); }
.filter-btn.active { background: var(--accent); color: #000; border-color: var(--accent); }

.table-wrap { flex: 1; min-height: 0; overflow-y: auto; overflow-x: auto; padding: 12px 24px; }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
th {
  background: var(--bg-surface); color: var(--text-muted); text-align: left; padding: 10px 14px;
  font-weight: 600; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 2;
}
td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
tr:hover td { background: rgba(255,255,255,0.02); cursor: pointer; }
.thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border); }

/* Auditor View */
#content-audit.active { flex-direction: column; overflow: hidden; }
#view-audit {
  width: 100%; height: 100%; display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden;
}
.audit-toolbar {
  padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--bg-surface);
  display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
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
    <div class="pill" id="user-badge" style="cursor: pointer; background: rgba(56, 189, 248, 0.1); border-color: rgba(56, 189, 248, 0.3); color: var(--accent);" title="Bấm để đổi người duyệt">
      👤 <b id="current-user-display">CRM Admin</b> ▾
    </div>
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
        <div class="loupe-lens" id="loupe-lens"></div>
      </div>
      <div class="img-toolbar">
        <button class="tool-btn" id="btn-toggle-loupe" title="Soi kính lúp (Phím Z). Giữ Ctrl + Kéo chuột trái để cuộn ảnh">🔬</button>
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
        <div class="locked-banner" id="locked-banner">
          🔒 <span>HÓA ĐƠN ĐÃ DUYỆT (CHỐT DỮ LIỆU) — ĐÃ KHÓA KHÔNG CHO CHỈNH SỬA</span>
        </div>

        <div class="diff-alert" id="diff-alert">
          ⚠️ <span>Admin đã sửa số tiền khác kết quả AI đọc ban đầu!</span>
        </div>

        <div class="save-banner" id="save-banner">
          <span style="font-size: 16px;">✅</span>
          <div style="flex: 1;">
            <b id="save-banner-title" style="color: #6ee7b7;">Đã lưu thay đổi thành công!</b>
            <div id="save-banner-sub" style="font-size: 11px; opacity: 0.9; margin-top: 1px;">Dữ liệu và vết kiểm toán đã được cập nhật vào CSDL.</div>
          </div>
          <button id="btn-close-save-banner" style="background:none; border:none; color:inherit; font-size:16px; cursor:pointer; opacity:0.7;" title="Đóng thông báo">✕</button>
        </div>

        <!-- Explanation Rule Notice -->
        <div class="coalesce-guide-box">
          <span style="font-size: 18px;">💡</span>
          <div style="flex: 1; font-size: 12px; line-height: 1.45;">
            <b>Quy tắc ghi nhận:</b> Nếu Admin field để trống thì số liệu cuối cùng theo AI field, nếu Admin nhập thì số liệu cuối cùng theo Admin.
          </div>
        </div>

        <!-- 1. Outlet Card -->
        <div class="audit-field-card" id="card-outlet">
          <div class="field-header">
            <div class="field-title">🏬 Cửa hàng / Gian hàng (Outlet)</div>
            <span class="source-badge ai" id="badge-outlet">Theo AI</span>
          </div>
          <div class="field-cols">
            <div class="ai-evidence-box">
              <span class="ai-evidence-label">AI đọc:</span>
              <span class="ai-evidence-val" id="ocr-outlet">–</span>
            </div>
            <div class="admin-input-wrap">
              <input list="outlets-datalist" class="input-box" id="inp-outlet-name" placeholder="(Để trống nếu AI đọc đúng)">
              <datalist id="outlets-datalist"></datalist>
            </div>
          </div>
        </div>

        <!-- 2. Total Amount Card -->
        <div class="audit-field-card" id="card-total">
          <div class="field-header">
            <div class="field-title">💰 Số tiền thanh toán hợp lệ (VNĐ)</div>
            <span class="source-badge ai" id="badge-total">Theo AI</span>
          </div>
          <div class="field-cols">
            <div class="ai-evidence-box">
              <span class="ai-evidence-label">AI đọc:</span>
              <span class="ai-evidence-val" id="ocr-total">0 đ</span>
            </div>
            <div class="admin-input-wrap">
              <input type="text" class="input-box amount-input" id="inp-total" placeholder="(Để trống nếu AI đọc đúng)">
            </div>
          </div>
        </div>

        <!-- 3. Bill Number Card -->
        <div class="audit-field-card" id="card-billno">
          <div class="field-header">
            <div class="field-title">🧾 Mã số hóa đơn (Bill No)</div>
            <span class="source-badge ai" id="badge-billno">Theo AI</span>
          </div>
          <div class="field-cols">
            <div class="ai-evidence-box">
              <span class="ai-evidence-label">AI đọc:</span>
              <span class="ai-evidence-val" id="ocr-billno">–</span>
            </div>
            <div class="admin-input-wrap">
              <input type="text" class="input-box" id="inp-billno" placeholder="(Để trống nếu AI đọc đúng)">
            </div>
          </div>
        </div>

        <!-- 4. DateTime Card -->
        <div class="audit-field-card" id="card-datetime">
          <div class="field-header">
            <div class="field-title">🕒 Ngày giờ giao dịch</div>
            <span class="source-badge ai" id="badge-datetime">Theo AI</span>
          </div>
          <div class="field-cols">
            <div class="ai-evidence-box">
              <span class="ai-evidence-label">AI đọc:</span>
              <span class="ai-evidence-val" id="ocr-datetime">–</span>
            </div>
            <div class="admin-input-wrap">
              <input type="text" class="input-box" id="inp-datetime" placeholder="(Để trống nếu AI đọc đúng: YYYY-MM-DD HH:mm:ss)">
            </div>
          </div>
        </div>

        <!-- 5. Auditor Note -->
        <div class="form-group" style="margin-top: 2px;">
          <label class="form-label">
            <span>📝 Ghi chú điều chỉnh (Auditor note - Nhập lý do nếu có sửa)</span>
          </label>
          <input type="text" class="input-box" id="inp-note" placeholder="Nhập lý do điều chỉnh nếu Admin có can thiệp số liệu...">
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

        <div id="inspector-action-buttons" style="display: flex; gap: 8px;">
          <button class="btn btn-save" id="btn-save" title="Phím Ctrl+S">💾 Lưu sửa đổi</button>
          <button class="btn btn-reject" id="btn-reject" title="Phím R">❌ Từ chối [R]</button>
          <button class="btn btn-approve" id="btn-approve" title="Phím A">✅ Phê duyệt [A]</button>
        </div>
        <div id="inspector-locked-msg" style="display: none; color: var(--success); font-weight: 700; font-size: 13px; align-items: center; gap: 6px;">
          🔒 ĐÃ KHÓA (APPROVED)
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: BATCH TABLE (US 1 & US 6) -->
  <section class="tab-content" id="content-batch">
    <div id="view-batch">
      <div class="batch-toolbar" style="flex-wrap: wrap; gap: 10px;">
        <div class="filter-tabs">
          <button class="filter-btn active" data-filter="ALL">Tất cả (<span id="cnt-all">0</span>)</button>
          <button class="filter-btn" data-filter="PENDING">Chờ duyệt (<span id="cnt-pending">0</span>)</button>
          <button class="filter-btn" data-filter="APPROVED">Đã duyệt (<span id="cnt-approved">0</span>)</button>
          <button class="filter-btn" data-filter="REJECTED">Đã từ chối (<span id="cnt-rejected">0</span>)</button>
        </div>

        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <select class="input-box" id="filter-edit-status" style="width: auto; padding: 6px 10px; font-size: 12px;">
            <option value="">-- Tất cả trạng thái sửa --</option>
            <option value="edited">Đã sửa tay (Manual Edited)</option>
            <option value="unedited">Chưa sửa (Giữ nguyên AI)</option>
          </select>

          <select class="input-box" id="filter-brand" style="width: auto; max-width: 170px; padding: 6px 10px; font-size: 12px;">
            <option value="">-- Tất cả Brand --</option>
          </select>

          <select class="input-box" id="filter-outlet" style="width: auto; max-width: 180px; padding: 6px 10px; font-size: 12px;">
            <option value="">-- Tất cả Cửa hàng --</option>
          </select>

          <input type="text" class="input-box" id="batch-search" placeholder="🔍 Tìm số HĐ, quán, brand, file..." style="max-width: 220px; padding: 6px 12px; font-size: 12px;">
        </div>
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

      <div class="batch-pagination">
        <div>Hiển thị <span id="page-start" style="color:var(--accent); font-weight:700;">0</span> - <span id="page-end" style="color:var(--accent); font-weight:700;">0</span> trên tổng số <b id="page-total" style="color:var(--text-main);">0</b> hóa đơn</div>
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="btn btn-sec" id="btn-page-first" title="Về trang đầu">⏮ Đầu</button>
          <button class="btn btn-sec" id="btn-page-prev">◀ Trước</button>
          <span style="margin: 0 4px;">Trang <b id="page-current" style="color:var(--accent); font-size:14px;">1</b> / <span id="page-last">1</span></span>
          <button class="btn btn-sec" id="btn-page-next">Sau ▶</button>
          <button class="btn btn-sec" id="btn-page-last-btn" title="Đến trang cuối">Cuối ⏭</button>
          <select id="sel-page-limit" class="input-box" style="width: auto; padding: 4px 8px; font-size: 12px; margin-left: 10px;">
            <option value="25">25 / trang</option>
            <option value="50" selected>50 / trang</option>
            <option value="100">100 / trang</option>
          </select>
        </div>
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

<!-- Toast Container (Modern floating alerts) -->
<div class="toast-container" id="toast-container"></div>

<!-- Popup Message Modal (Thông báo Lưu thành công hoặc Báo lỗi chi tiết) -->
<div class="modal-overlay" id="modal-popup-msg" style="display: none; z-index: 10000;">
  <div class="modal-card" style="max-width: 500px; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.7); border: 1px solid var(--border);">
    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span id="popup-msg-icon" style="font-size: 28px; line-height: 1;">✅</span>
        <div>
          <h3 id="popup-msg-title" style="margin: 0; font-size: 16px;">Thông báo</h3>
          <div id="popup-msg-subtitle" style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">Hệ thống CRM OCR Gigamall</div>
        </div>
      </div>
      <button id="btn-close-popup-msg-x" style="background:none; border:none; color:var(--text-muted); font-size:20px; cursor:pointer; line-height:1;">✕</button>
    </div>

    <div id="popup-msg-body" style="margin: 16px 0; font-size: 13px; line-height: 1.5; color: var(--text-main); background: rgba(0,0,0,0.25); padding: 14px 16px; border-radius: 8px; border: 1px solid var(--border);">
      Nội dung thông báo
    </div>

    <div style="display: flex; justify-content: flex-end; gap: 10px;">
      <button class="btn btn-save" id="btn-popup-msg-close" style="min-width: 100px;">Đã hiểu</button>
    </div>
  </div>
</div>

<!-- Reject Modal (Requirement 2) -->
<div class="modal-overlay" id="modal-reject">
  <div class="modal-card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h3>❌ Từ chối hóa đơn</h3>
      <button id="btn-close-reject-x" style="background:none; border:none; color:var(--text-muted); font-size:18px; cursor:pointer;">✕</button>
    </div>
    <div style="font-size: 12px; color: var(--text-dim);">
      Chọn lý do mẫu hoặc tự nhập nội dung từ chối gửi về CRM / Khách hàng:
    </div>

    <div class="form-group" style="margin-top: 8px;">
      <label class="form-label">Mẫu lý do cấu hình sẵn:</label>
      <select class="input-box" id="sel-reject-reason">
        <option value="">-- Chọn lý do mẫu cấu hình sẵn --</option>
        <option value="Hóa đơn mờ không đọc được">Hóa đơn mờ không đọc được</option>
        <option value="Ảnh chụp không phải hóa đơn mua hàng">Ảnh chụp không phải hóa đơn mua hàng</option>
        <option value="Hóa đơn không thuộc TTTM Gigamall">Hóa đơn không thuộc TTTM Gigamall</option>
        <option value="Hóa đơn quá hạn tích điểm (quá 48h)">Hóa đơn quá hạn tích điểm (quá 48h)</option>
        <option value="Hóa đơn trùng lặp đã được tích điểm">Hóa đơn trùng lặp đã được tích điểm</option>
        <option value="Số tiền thanh toán không đủ điều kiện">Số tiền thanh toán không đủ điều kiện</option>
      </select>
    </div>

    <div class="form-group">
      <label class="form-label">
        <span>Nội dung từ chối gửi khách (Bắt buộc):</span>
        <span style="color: var(--danger); font-size: 11px;">* Có thể sửa/đánh vào trực tiếp</span>
      </label>
      <textarea class="input-box" id="txt-reject-reason" rows="3" placeholder="Nhập lý do chi tiết từ chối..." style="resize: vertical; min-height: 70px;"></textarea>
    </div>

    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
      <button class="btn btn-sec" id="btn-cancel-reject">Hủy</button>
      <button class="btn btn-reject" id="btn-confirm-reject">Xác nhận Từ chối</button>
    </div>
  </div>
</div>

<!-- Duplicate Warning Modal (Requirement 5) -->
<div class="modal-overlay" id="modal-dup-warning">
  <div class="modal-card wide">
    <div style="display: flex; align-items: center; gap: 10px; color: #f59e0b;">
      <span style="font-size: 26px;">⚠️</span>
      <h3 style="margin: 0; color: #fde68a;">Cảnh báo: Hóa đơn Trùng lặp (Duplicate)!</h3>
    </div>
    <div id="dup-warning-body" style="font-size: 13px; line-height: 1.6; color: var(--text-main); margin-top: 10px; background: rgba(245, 158, 11, 0.08); padding: 12px; border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.2);">
      Đang tải thông tin trùng lặp...
    </div>
    <div style="font-size: 12px; color: var(--text-dim); margin-top: 4px;">
      Hệ thống phát hiện ảnh này giống 100% với một hóa đơn đã tải lên trước đó. Bạn muốn xử lý như thế nào?
    </div>
    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 14px;">
      <button class="btn btn-reject" id="btn-dup-reject-new">❌ Từ chối Bill mới</button>
      <button class="btn btn-sec" id="btn-dup-view-old">🔍 Xem Bill cũ</button>
      <button class="btn btn-save" id="btn-dup-keep-new">Tiếp tục xử lý Bill mới ▶</button>
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

<!-- Switch User / Login Modal -->
<div class="modal-overlay" id="modal-user">
  <div class="modal-card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h3>👤 Đăng nhập / Chọn người duyệt (Auditor)</h3>
      <button id="btn-close-user-x" style="background:none; border:none; color:var(--text-muted); font-size:18px; cursor:pointer;">✕</button>
    </div>
    <div style="font-size: 12px; color: var(--text-dim);">
      Tên người duyệt sẽ được tự động ghi nhận vào <b>Vết kiểm toán (Audit Trail)</b> cho mọi hành động Duyệt, Từ chối hoặc Sửa số tiền.
    </div>
    <div class="form-group">
      <label class="form-label">Chọn tài khoản mẫu:</label>
      <select class="input-box" id="sel-sample-user">
        <option value="CRM Admin">CRM Admin (Quản trị viên CRM)</option>
        <option value="Kế toán - Mai Lan">Kế toán - Mai Lan (Kiểm toán viên 1)</option>
        <option value="CSKH - Văn Hùng">CSKH - Văn Hùng (Chuyên viên quầy 2)</option>
        <option value="Auditor - Nguyễn Hoàng">Auditor - Nguyễn Hoàng (Thanh tra nội bộ)</option>
        <option value="__custom__">-- Tự nhập tên khác --</option>
      </select>
    </div>
    <div class="form-group" id="group-custom-user" style="display: none;">
      <label class="form-label">Nhập tên hoặc Email của bạn:</label>
      <input type="text" class="input-box" id="inp-custom-user" placeholder="Ví dụ: tranvanb@gigamall.com.vn">
    </div>
    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
      <button class="btn btn-sec" id="btn-cancel-user">Hủy</button>
      <button class="btn btn-save" id="btn-save-user">Xác nhận chuyển người dùng</button>
    </div>
  </div>
</div>

<script>
// User Management State
function getCurrentUser() {
  return localStorage.getItem("gigamall_ocr_actor") || "CRM Admin";
}

function setCurrentUser(userName) {
  const clean = (userName || "").trim() || "CRM Admin";
  localStorage.setItem("gigamall_ocr_actor", clean);
  document.getElementById("current-user-display").textContent = clean;
}

// User Modal Logic
const modalUser = document.getElementById("modal-user");
const selSampleUser = document.getElementById("sel-sample-user");
const groupCustomUser = document.getElementById("group-custom-user");
const inpCustomUser = document.getElementById("inp-custom-user");

document.getElementById("user-badge").addEventListener("click", () => {
  const current = getCurrentUser();
  modalUser.style.display = "flex";
  
  let found = false;
  for (let opt of selSampleUser.options) {
    if (opt.value === current) {
      selSampleUser.value = current;
      found = true;
      break;
    }
  }
  if (!found) {
    selSampleUser.value = "__custom__";
    groupCustomUser.style.display = "block";
    inpCustomUser.value = current;
  } else {
    groupCustomUser.style.display = "none";
  }
});

selSampleUser.addEventListener("change", e => {
  groupCustomUser.style.display = (e.target.value === "__custom__") ? "block" : "none";
  if (e.target.value === "__custom__") {
    inpCustomUser.focus();
  }
});

document.getElementById("btn-close-user-x").addEventListener("click", () => modalUser.style.display = "none");
document.getElementById("btn-cancel-user").addEventListener("click", () => modalUser.style.display = "none");

document.getElementById("btn-save-user").addEventListener("click", () => {
  let chosen = selSampleUser.value;
  if (chosen === "__custom__") {
    chosen = inpCustomUser.value.trim();
    if (!chosen) {
      alert("Vui lòng nhập tên người duyệt!");
      return;
    }
  }
  setCurrentUser(chosen);
  modalUser.style.display = "none";
});

// State
let allBills = [];
let currentIdx = 0;
let masterOutlets = [];
let imgScale = 1;
let imgRotate = 0;
let imgPanX = 0;
let imgPanY = 0;
let isPanning = false;
let startMouseX = 0;
let startMouseY = 0;
let startPanX = 0;
let startPanY = 0;
let currentFilter = "ALL";
let currentPage = 1;
let currentLimit = 50;
let totalBillsCount = 0;
let currentEditStatus = "";
let currentBrand = "";
let currentOutlet = "";
let currentSearch = "";
let searchDebounceTimer = null;
let isLoupeActive = false;
let loupeZoom = 3.0;
let lastDupData = null;

// Elements
const billImg = document.getElementById("bill-img");
const diffAlert = document.getElementById("diff-alert");
const canvasWrap = document.getElementById("canvas-wrap");
const loupeLens = document.getElementById("loupe-lens");
const btnToggleLoupe = document.getElementById("btn-toggle-loupe");
const filterEditStatus = document.getElementById("filter-edit-status");
const filterBrand = document.getElementById("filter-brand");
const filterOutlet = document.getElementById("filter-outlet");
const batchSearch = document.getElementById("batch-search");
const modalReject = document.getElementById("modal-reject");
const selRejectReason = document.getElementById("sel-reject-reason");
const txtRejectReason = document.getElementById("txt-reject-reason");
const modalDupWarning = document.getElementById("modal-dup-warning");

// Load Initial Data
async function init() {
  setCurrentUser(getCurrentUser());
  setupFiltersAndListeners();
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

    // Populate Brand Filter
    const brands = Array.from(new Set(masterOutlets.map(o => (o.brand_name || '').trim()).filter(Boolean))).sort();
    filterBrand.innerHTML = `<option value="">-- Tất cả Brand (${brands.length}) --</option>` +
      brands.map(b => `<option value="${b}">${b}</option>`).join("");

    // Populate Outlet Filter
    const outlets = Array.from(new Set(masterOutlets.map(o => (o.outlet_name || '').trim()).filter(Boolean))).sort();
    filterOutlet.innerHTML = `<option value="">-- Tất cả Cửa hàng (${outlets.length}) --</option>` +
      outlets.map(o => `<option value="${o}">${o}</option>`).join("");
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
    let url = `/api/bills?status=${currentFilter}&page=${currentPage}&limit=${currentLimit}`;
    if (currentEditStatus) url += `&edit_status=${encodeURIComponent(currentEditStatus)}`;
    if (currentBrand) url += `&brand=${encodeURIComponent(currentBrand)}`;
    if (currentOutlet) url += `&outlet=${encodeURIComponent(currentOutlet)}`;
    if (currentSearch) url += `&search=${encodeURIComponent(currentSearch)}`;

    const res = await fetch(url);
    const data = await res.json();
    allBills = data.items || [];
    totalBillsCount = data.total || 0;
    renderBatchTable();
    updatePaginationUI();
  } catch(e) { console.error(e); }
}

function updatePaginationUI() {
  const total = totalBillsCount;
  const lastPage = Math.max(1, Math.ceil(total / currentLimit));
  if (currentPage > lastPage) currentPage = lastPage;

  const start = total === 0 ? 0 : (currentPage - 1) * currentLimit + 1;
  const end = Math.min(currentPage * currentLimit, total);

  const elStart = document.getElementById("page-start");
  const elEnd = document.getElementById("page-end");
  const elTotal = document.getElementById("page-total");
  const elCurrent = document.getElementById("page-current");
  const elLast = document.getElementById("page-last");

  if (elStart) elStart.textContent = start;
  if (elEnd) elEnd.textContent = end;
  if (elTotal) elTotal.textContent = total;
  if (elCurrent) elCurrent.textContent = currentPage;
  if (elLast) elLast.textContent = lastPage;

  const btnFirst = document.getElementById("btn-page-first");
  const btnPrev = document.getElementById("btn-page-prev");
  const btnNext = document.getElementById("btn-page-next");
  const btnLast = document.getElementById("btn-page-last-btn");

  if (btnFirst) btnFirst.disabled = (currentPage <= 1);
  if (btnPrev) btnPrev.disabled = (currentPage <= 1);
  if (btnNext) btnNext.disabled = (currentPage >= lastPage);
  if (btnLast) btnLast.disabled = (currentPage >= lastPage);
}

function setupFiltersAndListeners() {
  // Filter tabs
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.dataset.filter;
      currentPage = 1;
      loadBills();
    });
  });

  // Edit status filter
  filterEditStatus.addEventListener("change", e => {
    currentEditStatus = e.target.value;
    currentPage = 1;
    loadBills();
  });

  // Brand filter
  filterBrand.addEventListener("change", e => {
    currentBrand = e.target.value;
    currentPage = 1;
    loadBills();
  });

  // Outlet filter
  filterOutlet.addEventListener("change", e => {
    currentOutlet = e.target.value;
    currentPage = 1;
    loadBills();
  });

  // Search box with debounce
  batchSearch.addEventListener("input", e => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      currentSearch = e.target.value.trim();
      currentPage = 1;
      loadBills();
    }, 350);
  });

  // Pagination buttons
  const btnFirst = document.getElementById("btn-page-first");
  if (btnFirst) {
    btnFirst.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage = 1;
        loadBills();
      }
    });
  }

  const btnPrev = document.getElementById("btn-page-prev");
  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        loadBills();
      }
    });
  }

  const btnNext = document.getElementById("btn-page-next");
  if (btnNext) {
    btnNext.addEventListener("click", () => {
      const lastPage = Math.max(1, Math.ceil(totalBillsCount / currentLimit));
      if (currentPage < lastPage) {
        currentPage++;
        loadBills();
      }
    });
  }

  const btnLast = document.getElementById("btn-page-last-btn");
  if (btnLast) {
    btnLast.addEventListener("click", () => {
      const lastPage = Math.max(1, Math.ceil(totalBillsCount / currentLimit));
      if (currentPage < lastPage) {
        currentPage = lastPage;
        loadBills();
      }
    });
  }

  document.getElementById("sel-page-limit").addEventListener("change", e => {
    currentLimit = parseInt(e.target.value, 10) || 50;
    currentPage = 1;
    loadBills();
  });
}

function showBill(idx) {
  if (idx < 0 || idx >= allBills.length) return;
  currentIdx = idx;
  const b = allBills[idx];

  // Reset image transform, pan & loupe
  imgScale = 1; imgRotate = 0; imgPanX = 0; imgPanY = 0;
  updateImgTransform();
  if (loupeLens) loupeLens.style.display = "none";

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
  const inpOutlet = document.getElementById("inp-outlet-name");
  const inpTotal = document.getElementById("inp-total");
  const inpBillNo = document.getElementById("inp-billno");
  const inpDateTime = document.getElementById("inp-datetime");
  // Editable Form inputs (Admin Override)
  // NGUYÊN TẮC: KHÔNG ĐƯỢC MANG DATA AI QUA CỘT ADMIN!
  // Mặc định ô nhập của Admin ĐỂ TRỐNG nếu Admin chưa từng sửa trường này.
  const isOutletEdited = Boolean(b.IsManualEdited && b.FinalOutletName && b.OcrOutletName && b.FinalOutletName.toLowerCase() !== b.OcrOutletName.toLowerCase());
  inpOutlet.value = isOutletEdited ? b.FinalOutletName : "";

  const isTotalEdited = Boolean(b.IsManualEdited && b.FinalTotal !== null && b.FinalTotal !== b.OcrTotal);
  inpTotal.value = isTotalEdited ? b.FinalTotal.toLocaleString("vi-VN") : "";

  const isBillNoEdited = Boolean(b.IsManualEdited && b.FinalBillNumber && b.OcrBillNumber && b.FinalBillNumber !== b.OcrBillNumber);
  inpBillNo.value = isBillNoEdited ? b.FinalBillNumber : "";

  const aiDtStr = (b.OcrDateTime || "").replace("T", " ");
  const finalDtStr = (b.FinalDateTime || "").replace("T", " ");
  const isDateTimeEdited = Boolean(b.IsManualEdited && finalDtStr && aiDtStr && finalDtStr !== aiDtStr);
  inpDateTime.value = isDateTimeEdited ? finalDtStr : "";

  inpNote.value = "";

  // Requirement 3: Lock if APPROVED or REJECTED & Change styling
  applyLockState(b);

  const saveBanner = document.getElementById("save-banner");
  if (saveBanner) saveBanner.classList.remove("active");

  checkDiff(b);
  loadBillAuditLogs(b.BillId);
}

function applyLockState(b) {
  if (!b) return;
  const isLocked = (b.Status === "APPROVED" || b.Status === "REJECTED");
  const panelRight = document.querySelector(".inspector-right");
  const lockedBanner = document.getElementById("locked-banner");
  const actionBtns = document.getElementById("inspector-action-buttons");
  const lockedMsg = document.getElementById("inspector-locked-msg");
  const st = document.getElementById("bill-status");
  if (st) {
    st.textContent = b.Status;
    st.className = `status-tag ${b.Status}`;
  }

  const inpOutlet = document.getElementById("inp-outlet-name");
  const inpTotal = document.getElementById("inp-total");
  const inpBillNo = document.getElementById("inp-billno");
  const inpDateTime = document.getElementById("inp-datetime");
  const inpNote = document.getElementById("inp-note");

  [inpOutlet, inpTotal, inpBillNo, inpDateTime, inpNote].forEach(inp => {
    if (inp) inp.disabled = isLocked;
  });

  if (isLocked) {
    if (panelRight) panelRight.classList.add("bill-locked");
    if (lockedBanner) {
      lockedBanner.classList.add("active");
      const actionText = b.Status === "APPROVED" ? "ĐÃ DUYỆT" : "ĐÃ TỪ CHỐI";
      lockedBanner.innerHTML = `🔒 <span>HÓA ĐƠN ${actionText} BỞI <b>${b.ReviewedBy || 'Admin'}</b> — ĐÃ KHÓA DỮ LIỆU KHÔNG CHO CHỈNH SỬA</span>`;
    }
    if (actionBtns) actionBtns.style.display = "none";
    if (lockedMsg) lockedMsg.style.display = "flex";
  } else {
    if (panelRight) panelRight.classList.remove("bill-locked");
    if (lockedBanner) lockedBanner.classList.remove("active");
    if (actionBtns) actionBtns.style.display = "flex";
    if (lockedMsg) lockedMsg.style.display = "none";
  }
}

function checkDiff(b) {
  if (!b) return;

  // 1. Outlet
  const curOutlet = document.getElementById("inp-outlet-name").value.trim();
  const hasAdminOutlet = curOutlet !== "";
  const cardOutlet = document.getElementById("card-outlet");
  const badgeOutlet = document.getElementById("badge-outlet");

  if (cardOutlet && badgeOutlet) {
    cardOutlet.classList.toggle("is-edited", hasAdminOutlet);
    badgeOutlet.className = `source-badge ${hasAdminOutlet ? 'edited' : 'ai'}`;
    badgeOutlet.innerHTML = hasAdminOutlet ? `✍️ Theo Admin` : `Theo AI`;
  }

  // 2. Total
  const aiTotal = b.OcrTotal || 0;
  const rawTotalStr = document.getElementById("inp-total").value.trim();
  const hasAdminTotal = rawTotalStr !== "";
  const curTotal = hasAdminTotal ? (parseInt(rawTotalStr.replace(/[^0-9]/g, ""), 10) || 0) : null;
  const cardTotal = document.getElementById("card-total");
  const badgeTotal = document.getElementById("badge-total");

  if (cardTotal && badgeTotal) {
    cardTotal.classList.toggle("is-edited", hasAdminTotal);
    badgeTotal.className = `source-badge ${hasAdminTotal ? 'edited' : 'ai'}`;
    badgeTotal.innerHTML = hasAdminTotal ? `✍️ Theo Admin` : `Theo AI`;
  }

  diffAlert.classList.toggle("active", hasAdminTotal && curTotal !== aiTotal);
  document.getElementById("inp-total").classList.toggle("diff-highlight", hasAdminTotal && curTotal !== aiTotal);

  // 3. Bill Number
  const curBillNo = document.getElementById("inp-billno").value.trim();
  const hasAdminBillNo = curBillNo !== "";
  const cardBillNo = document.getElementById("card-billno");
  const badgeBillNo = document.getElementById("badge-billno");

  if (cardBillNo && badgeBillNo) {
    cardBillNo.classList.toggle("is-edited", hasAdminBillNo);
    badgeBillNo.className = `source-badge ${hasAdminBillNo ? 'edited' : 'ai'}`;
    badgeBillNo.innerHTML = hasAdminBillNo ? `✍️ Theo Admin` : `Theo AI`;
  }

  // 4. DateTime
  const curDateTime = document.getElementById("inp-datetime").value.trim();
  const hasAdminDateTime = curDateTime !== "";
  const cardDateTime = document.getElementById("card-datetime");
  const badgeDateTime = document.getElementById("badge-datetime");

  if (cardDateTime && badgeDateTime) {
    cardDateTime.classList.toggle("is-edited", hasAdminDateTime);
    badgeDateTime.className = `source-badge ${hasAdminDateTime ? 'edited' : 'ai'}`;
    badgeDateTime.innerHTML = hasAdminDateTime ? `✍️ Theo Admin` : `Theo AI`;
  }
}

// Input event listeners for real-time diff & final preview
document.getElementById("inp-total").addEventListener("input", e => {
  const raw = e.target.value.replace(/[^0-9]/g, "");
  e.target.value = raw ? parseInt(raw, 10).toLocaleString("vi-VN") : "";
  if (allBills[currentIdx]) checkDiff(allBills[currentIdx]);
});
document.getElementById("inp-outlet-name").addEventListener("input", () => {
  if (allBills[currentIdx]) checkDiff(allBills[currentIdx]);
});
document.getElementById("inp-billno").addEventListener("input", () => {
  if (allBills[currentIdx]) checkDiff(allBills[currentIdx]);
});
document.getElementById("inp-datetime").addEventListener("input", () => {
  if (allBills[currentIdx]) checkDiff(allBills[currentIdx]);
});

function showToast(type, title, message, durationMs = 4500) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const icons = {
    success: "✅",
    info: "ℹ️",
    warning: "⚠️",
    error: "❌"
  };

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || "ℹ️"}</span>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      <div class="toast-msg">${message}</div>
    </div>
    <button class="toast-close" title="Đóng">✕</button>
  `;

  const closeBtn = toast.querySelector(".toast-close");
  const removeToast = () => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  };

  closeBtn.addEventListener("click", removeToast);
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("show"));

  if (durationMs > 0) {
    setTimeout(removeToast, durationMs);
  }
}

let popupOnCloseCallback = null;

function showPopupMessage({ type = "info", title = "Thông báo", subtitle = "Hệ thống CRM OCR Gigamall", bodyHtml = "", onClose = null }) {
  const modal = document.getElementById("modal-popup-msg");
  if (!modal) return;

  const iconEl = document.getElementById("popup-msg-icon");
  const titleEl = document.getElementById("popup-msg-title");
  const subtitleEl = document.getElementById("popup-msg-subtitle");
  const bodyEl = document.getElementById("popup-msg-body");
  const cardEl = modal.querySelector(".modal-card");

  const icons = {
    success: "✅",
    warning: "⚠️",
    error: "❌",
    info: "ℹ️"
  };

  const titleColors = {
    success: "var(--success)",
    warning: "#ffb86c",
    error: "var(--danger)",
    info: "var(--accent)"
  };

  const borderColors = {
    success: "rgba(16, 185, 129, 0.45)",
    warning: "rgba(255, 184, 108, 0.55)",
    error: "rgba(239, 68, 68, 0.55)",
    info: "rgba(56, 189, 248, 0.45)"
  };

  if (iconEl) iconEl.textContent = icons[type] || "ℹ️";
  if (titleEl) {
    titleEl.textContent = title;
    titleEl.style.color = titleColors[type] || "var(--text-main)";
  }
  if (subtitleEl) subtitleEl.textContent = subtitle;
  if (bodyEl) bodyEl.innerHTML = bodyHtml;

  if (cardEl) {
    cardEl.style.borderColor = borderColors[type] || "var(--border)";
  }

  popupOnCloseCallback = onClose;
  modal.style.display = "flex";
}

function closePopupMessage() {
  const modal = document.getElementById("modal-popup-msg");
  if (modal) modal.style.display = "none";
  if (typeof popupOnCloseCallback === "function") {
    const cb = popupOnCloseCallback;
    popupOnCloseCallback = null;
    cb();
  }
}

const btnPopupMsgClose = document.getElementById("btn-popup-msg-close");
if (btnPopupMsgClose) {
  btnPopupMsgClose.addEventListener("click", closePopupMessage);
}
const btnClosePopupMsgX = document.getElementById("btn-close-popup-msg-x");
if (btnClosePopupMsgX) {
  btnClosePopupMsgX.addEventListener("click", closePopupMessage);
}
const modalPopupMsg = document.getElementById("modal-popup-msg");
if (modalPopupMsg) {
  modalPopupMsg.addEventListener("click", (e) => {
    if (e.target === modalPopupMsg) closePopupMessage();
  });
}

async function loadBillAuditLogs(billId, highlightFirst = false) {
  try {
    const res = await fetch(`/api/bills/${billId}`);
    const data = await res.json();

    // Tự động đồng bộ trạng thái mới nhất từ CSDL (tránh lệch PENDING khi đã APPROVED/REJECTED)
    const b = allBills[currentIdx];
    if (b && b.BillId === billId && data && data.Status) {
      if (b.Status !== data.Status || b.ReviewedBy !== data.ReviewedBy) {
        b.Status = data.Status;
        b.ReviewedBy = data.ReviewedBy;
        b.ReviewedAt = data.ReviewedAt;
        if (data.FinalTotal !== undefined) b.FinalTotal = data.FinalTotal;
        if (data.FinalOutletName !== undefined) b.FinalOutletName = data.FinalOutletName;
        if (data.FinalBillNumber !== undefined) b.FinalBillNumber = data.FinalBillNumber;
        if (data.FinalDateTime !== undefined) b.FinalDateTime = data.FinalDateTime;
        applyLockState(b);
      }
    }

    const list = document.getElementById("inspector-audit-list");
    if (!data.audit_logs || data.audit_logs.length === 0) {
      list.innerHTML = `<div style="color: var(--text-dim); font-size: 11px;">Chưa có lịch sử thay đổi.</div>`;
      return;
    }
    list.innerHTML = data.audit_logs.map((l, i) => `
      <div class="audit-item ${highlightFirst && i === 0 ? 'highlight-new' : ''}">
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

// Requirement 2: Custom Reject Reason
document.getElementById("btn-reject").addEventListener("click", () => {
  selRejectReason.value = "";
  txtRejectReason.value = "";
  modalReject.style.display = "flex";
  txtRejectReason.focus();
});

document.getElementById("btn-close-reject-x").addEventListener("click", () => {
  modalReject.style.display = "none";
});

document.getElementById("btn-cancel-reject").addEventListener("click", () => {
  modalReject.style.display = "none";
});

selRejectReason.addEventListener("change", e => {
  if (e.target.value) {
    txtRejectReason.value = e.target.value;
  }
});

document.getElementById("btn-confirm-reject").addEventListener("click", async () => {
  const customReason = txtRejectReason.value.trim();
  if (!customReason) {
    showToast("warning", "Thiếu lý do", "Vui lòng nhập nội dung lý do từ chối vào ô văn bản!");
    txtRejectReason.focus();
    return;
  }
  modalReject.style.display = "none";
  await submitReview("REJECTED", customReason);
});

async function submitReview(status, rejectReason = null) {
  const b = allBills[currentIdx];
  if (!b) return;

  if (status !== "REJECTED") {
    // Auto-save any form edits first
    await saveEdits(false);
  }

  const currentUser = getCurrentUser();
  const res = await fetch(`/api/bills/${b.BillId}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Actor": currentUser
    },
    body: JSON.stringify({ status, actor: currentUser, reject_reason: rejectReason })
  });

  if (res.ok) {
    b.Status = status;
    showBill(currentIdx);
    await loadStats();
    if (status === "APPROVED") {
      showToast("success", `Đã phê duyệt Bill #${b.BillId}`, `Hóa đơn đã được chốt dữ liệu bởi <b>${currentUser}</b>.`);
    } else {
      showToast("warning", `Đã từ chối Bill #${b.BillId}`, `Lý do: <i>${rejectReason}</i>`);
    }
    // Auto advance to next bill
    if (currentIdx < allBills.length - 1) {
      setTimeout(() => showBill(currentIdx + 1), 600);
    }
  } else {
    showToast("error", "Lỗi phê duyệt", "Không thể cập nhật trạng thái hóa đơn.");
  }
}

document.getElementById("btn-save").addEventListener("click", () => saveEdits(true));

const btnCloseSaveBanner = document.getElementById("btn-close-save-banner");
if (btnCloseSaveBanner) {
  btnCloseSaveBanner.addEventListener("click", () => {
    const saveBanner = document.getElementById("save-banner");
    if (saveBanner) saveBanner.classList.remove("active");
  });
}

async function saveEdits(showPrompt = true) {
  const b = allBills[currentIdx];
  if (!b) return;

  if (b.Status === "APPROVED" || b.Status === "REJECTED") {
    const actionText = b.Status === "APPROVED" ? "Phê duyệt" : "Từ chối";
    showPopupMessage({
      type: "warning",
      title: "Không thể chỉnh sửa hóa đơn đã chốt",
      subtitle: `Hóa đơn #${b.BillId} • Trạng thái: ${b.Status}`,
      bodyHtml: `
        <div style="margin-bottom: 12px; font-weight: 600; color: #ffb86c; font-size: 13.5px;">
          ⚠️ Hóa đơn này đã ở trạng thái <b>${b.Status}</b> (đã được ${actionText} bởi <b>${b.ReviewedBy || 'Admin'}</b>).
        </div>
        <div style="line-height: 1.5; color: var(--text-main); margin-bottom: 12px;">
          Theo quy chuẩn kiểm toán CRM và CSDL, dữ liệu hóa đơn sau khi đã được chốt (APPROVED hoặc REJECTED) <b>không được phép tự ý sửa đổi</b> để đảm bảo tính minh bạch tài chính.
        </div>
        <div style="background: rgba(0,0,0,0.3); border-radius: 6px; padding: 10px 12px; font-size: 11.5px; color: var(--text-dim); border: 1px dashed rgba(255,255,255,0.1);">
          🔒 Các trường nhập liệu của hóa đơn này đã được hệ thống tự động khóa lại.
        </div>
      `,
      onClose: () => {
        applyLockState(b);
      }
    });
    applyLockState(b);
    return;
  }

  const btnSave = document.getElementById("btn-save");
  const originalBtnHtml = btnSave ? btnSave.innerHTML : "💾 Lưu sửa đổi";

  if (btnSave && showPrompt) {
    btnSave.classList.add("saving");
    btnSave.innerHTML = `⏳ Đang lưu CSDL...`;
  }

  try {
    const rawTotalStr = document.getElementById("inp-total").value.trim();
    const rawOutlet = document.getElementById("inp-outlet-name").value.trim();
    const rawBillNo = document.getElementById("inp-billno").value.trim();
    const rawDt = document.getElementById("inp-datetime").value.trim();
    const note = document.getElementById("inp-note").value.trim();

    // NGUYÊN TẮC: KHÔNG ĐƯỢC MANG DATA AI QUA CỘT ADMIN!
    // Nếu ô nhập trống => Admin KHÔNG sửa trường này => admin* = null!
    const adminTotal = rawTotalStr !== "" ? (parseInt(rawTotalStr.replace(/[^0-9]/g, ""), 10) || 0) : null;
    const adminOutlet = rawOutlet !== "" ? rawOutlet : null;
    const adminBillNo = rawBillNo !== "" ? rawBillNo : null;
    const adminDateTime = rawDt !== "" ? rawDt : null;

    // Kết quả Final là phép tính query COALESCE(Admin, AI):
    // Nếu có Admin thì lấy Admin, nếu không thì lấy AI:
    const finalTotal = adminTotal !== null ? adminTotal : (b.OcrTotal || 0);
    const finalOutlet = adminOutlet !== null ? adminOutlet : (b.OcrOutletName || "");
    const finalBillNo = adminBillNo !== null ? adminBillNo : (b.OcrBillNumber || "");
    const finalDateTime = adminDateTime !== null ? adminDateTime : (b.OcrDateTime ? b.OcrDateTime.replace("T", " ") : "");

    // Find outlet number if matching master outlets
    const matched = masterOutlets.find(o => o.outlet_name.toLowerCase() === finalOutlet.toLowerCase());
    const outletNum = matched ? matched.outlet_number : b.FinalOutletNumber;
    const currentUser = getCurrentUser();

    const payload = {
      final_outlet_name: finalOutlet,
      final_outlet_number: outletNum,
      final_total: finalTotal,
      final_bill_number: finalBillNo,
      final_datetime: finalDateTime,
      actor: currentUser,
      note: note
    };

    const res = await fetch(`/api/bills/${b.BillId}/edit`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Actor": currentUser
      },
      body: JSON.stringify(payload)
    });

    const result = await res.json().catch(() => ({}));

    if (res.ok) {
      b.FinalOutletName = finalOutlet;
      b.FinalTotal = finalTotal;
      b.FinalBillNumber = finalBillNo;
      b.FinalDateTime = finalDateTime;
      b.IsManualEdited = (adminTotal !== null || adminOutlet !== null || adminBillNo !== null || adminDateTime !== null) ? 1 : 0;
      checkDiff(b);

      const numChanged = result.fields_changed !== undefined ? result.fields_changed : 1;

      if (showPrompt) {
        if (btnSave) {
          btnSave.classList.remove("saving");
          btnSave.classList.add("saved");
          btnSave.innerHTML = `✅ Đã lưu xong!`;
          setTimeout(() => {
            btnSave.classList.remove("saved");
            btnSave.innerHTML = originalBtnHtml;
          }, 2000);
        }

        const nowStr = new Date().toLocaleTimeString("vi-VN");
        const formattedTotal = finalTotal.toLocaleString("vi-VN") + " VNĐ";

        // POPUP MESSAGE THÔNG BÁO LƯU THÀNH CÔNG RÕ RÀNG
        showPopupMessage({
          type: "success",
          title: "Lưu thay đổi thành công!",
          subtitle: `Hóa đơn #${b.BillId} • Cập nhật lúc ${nowStr} bởi ${currentUser}`,
          bodyHtml: `
            <div style="margin-bottom: 12px; color: var(--success); font-weight: 600; font-size: 13.5px;">
              ${numChanged > 0 ? `✅ Đã lưu thành công <b>${numChanged} trường</b> vào CSDL và ghi nhận vết kiểm toán.` : `ℹ️ Dữ liệu đã được kiểm tra khớp hoàn toàn với CSDL.`}
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 6px; overflow: hidden;">
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
                <td style="padding: 7px 10px; color: var(--text-dim); width: 38%;">Cửa hàng / Gian hàng:</td>
                <td style="padding: 7px 10px; font-weight: 600; color: var(--text-main);">
                  ${finalOutlet || "–"} 
                  <span style="font-size: 11px; margin-left: 6px; color: ${adminOutlet ? '#ffb86c' : 'var(--accent)'};">
                    (${adminOutlet ? '✍️ Admin nhập' : '🤖 Kế thừa AI'})
                  </span>
                </td>
              </tr>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
                <td style="padding: 7px 10px; color: var(--text-dim);">Số tiền hợp lệ:</td>
                <td style="padding: 7px 10px; font-weight: 700; color: var(--accent); font-size: 13px;">
                  ${formattedTotal}
                  <span style="font-size: 11px; margin-left: 6px; color: ${adminTotal !== null ? '#ffb86c' : 'var(--accent)'};">
                    (${adminTotal !== null ? '✍️ Admin nhập' : '🤖 Kế thừa AI'})
                  </span>
                </td>
              </tr>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
                <td style="padding: 7px 10px; color: var(--text-dim);">Mã số hóa đơn:</td>
                <td style="padding: 7px 10px; font-family: monospace; color: var(--text-main); font-weight: 600;">
                  ${finalBillNo || "–"}
                  <span style="font-size: 11px; margin-left: 6px; color: ${adminBillNo ? '#ffb86c' : 'var(--accent)'};">
                    (${adminBillNo ? '✍️ Admin nhập' : '🤖 Kế thừa AI'})
                  </span>
                </td>
              </tr>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">
                <td style="padding: 7px 10px; color: var(--text-dim);">Ngày giờ giao dịch:</td>
                <td style="padding: 7px 10px; color: var(--text-main);">
                  ${finalDateTime || "–"}
                  <span style="font-size: 11px; margin-left: 6px; color: ${adminDateTime ? '#ffb86c' : 'var(--accent)'};">
                    (${adminDateTime ? '✍️ Admin nhập' : '🤖 Kế thừa AI'})
                  </span>
                </td>
              </tr>
              ${note ? `
              <tr>
                <td style="padding: 7px 10px; color: var(--text-dim);">Ghi chú điều chỉnh:</td>
                <td style="padding: 7px 10px; color: #ffb86c; font-style: italic;">${note}</td>
              </tr>
              ` : ''}
            </table>
            <div style="font-size: 11.5px; color: var(--text-dim); border-top: 1px dashed var(--border); padding-top: 8px;">
              📝 Nhân viên thực hiện: <b>${currentUser}</b> • Quy tắc Coalesce: Không sao chép hay ghi đè dữ liệu AI gốc.
            </div>
          `
        });

        // Show inline banner in form
        const saveBanner = document.getElementById("save-banner");
        const saveBannerTitle = document.getElementById("save-banner-title");
        const saveBannerSub = document.getElementById("save-banner-sub");
        if (saveBanner && saveBannerTitle && saveBannerSub) {
          if (numChanged > 0) {
            saveBannerTitle.textContent = `Đã lưu thành công ${numChanged} trường thay đổi!`;
            saveBannerSub.textContent = `Cập nhật lúc ${nowStr} bởi ${currentUser}. Đã ghi nhận vết kiểm toán.`;
          } else {
            saveBannerTitle.textContent = `Không có thay đổi nào`;
            saveBannerSub.textContent = `Dữ liệu hiện tại khớp 100% với CSDL (lúc ${nowStr}).`;
          }
          saveBanner.classList.add("active");
        }

        // Show floating Toast
        showToast(
          "success",
          `Lưu thành công Bill #${b.BillId}`,
          `Đã cập nhật ${numChanged} trường vào CSDL lúc ${nowStr} bởi <b>${currentUser}</b>.`
        );

        await loadBillAuditLogs(b.BillId, true);
        loadStats();
      }
    } else {
      if (btnSave) {
        btnSave.classList.remove("saving");
        btnSave.innerHTML = originalBtnHtml;
      }

      const errorMsg = result.detail || `Lỗi máy chủ (${res.status})`;

      // Nếu lỗi do bill đã được duyệt hoặc từ chối, cập nhật trạng thái ngay
      if (errorMsg.includes("APPROVED") || errorMsg.includes("REJECTED") || errorMsg.includes("đã ở trạng thái")) {
        if (errorMsg.includes("APPROVED")) b.Status = "APPROVED";
        else if (errorMsg.includes("REJECTED")) b.Status = "REJECTED";
        applyLockState(b);
      }

      // POPUP MESSAGE THÔNG BÁO LỖI / TẠI SAO KHÔNG LƯU ĐƯỢC
      showPopupMessage({
        type: "error",
        title: "Không thể lưu thay đổi vào CSDL",
        subtitle: `Hóa đơn #${b.BillId} • Mã lỗi: ${res.status}`,
        bodyHtml: `
          <div style="margin-bottom: 10px; font-weight: 600; color: var(--danger); font-size: 13.5px;">
            ❌ Hệ thống từ chối lưu thay đổi do vi phạm quy tắc dữ liệu:
          </div>
          <div style="background: rgba(255, 85, 85, 0.12); border-left: 3px solid var(--danger); padding: 10px 12px; border-radius: 4px; margin-bottom: 12px; color: #ffb8b8; font-size: 12.5px; line-height: 1.5;">
            ${errorMsg}
          </div>
          <div style="font-size: 11.5px; color: var(--text-dim); line-height: 1.5;">
            💡 <b>Giải thích:</b> Hóa đơn này đã được xác nhận (APPROVED hoặc REJECTED). Để bảo vệ dữ liệu kế toán và kiểm toán, CSDL từ chối các thao tác ghi đè lên hóa đơn đã hoàn tất.
          </div>
        `,
        onClose: () => {
          applyLockState(b);
        }
      });

      showToast("error", "Lỗi lưu dữ liệu", errorMsg);
    }
  } catch (err) {
    if (btnSave) {
      btnSave.classList.remove("saving");
      btnSave.innerHTML = originalBtnHtml;
    }

    showPopupMessage({
      type: "error",
      title: "Lỗi kết nối máy chủ",
      subtitle: `Không thể kết nối đến máy chủ CSDL`,
      bodyHtml: `
        <div style="color: var(--danger); margin-bottom: 8px; font-weight: 600; font-size: 13.5px;">
          ❌ Gặp sự cố đường truyền mạng khi gửi yêu cầu lưu dữ liệu.
        </div>
        <div style="font-size: 12px; color: var(--text-dim); line-height: 1.4;">
          Chi tiết lỗi: <code>${err.message || 'Network disconnected'}</code>.<br/>
          Vui lòng kiểm tra lại kết nối mạng tới máy chủ hoặc tải lại trang.
        </div>
      `
    });

    showToast("error", "Lỗi kết nối", err.message || "Gặp lỗi kết nối khi lưu dữ liệu");
  }
}

// Image tools & Requirement 1: Loupe Magnifier (Zoom theo khu vực & Kéo cuộn ảnh)
function updateImgTransform() {
  billImg.style.transform = `translate(${imgPanX}px, ${imgPanY}px) scale(${imgScale}) rotate(${imgRotate}deg)`;
}
document.getElementById("btn-zoom-in").addEventListener("click", () => { imgScale = Math.min(imgScale + 0.25, 3.5); updateImgTransform(); });
document.getElementById("btn-zoom-out").addEventListener("click", () => { imgScale = Math.max(imgScale - 0.25, 0.5); updateImgTransform(); });
document.getElementById("btn-rotate-right").addEventListener("click", () => { imgRotate = (imgRotate + 90) % 360; updateImgTransform(); });
document.getElementById("btn-rotate-left").addEventListener("click", () => { imgRotate = (imgRotate - 90 + 360) % 360; updateImgTransform(); });
document.getElementById("btn-zoom-reset").addEventListener("click", () => {
  imgScale = 1; imgRotate = 0; imgPanX = 0; imgPanY = 0;
  updateImgTransform();
});

btnToggleLoupe.addEventListener("click", toggleLoupe);

function toggleLoupe() {
  isLoupeActive = !isLoupeActive;
  btnToggleLoupe.classList.toggle("active", isLoupeActive);
  btnToggleLoupe.title = isLoupeActive ? "Đang bật kính lúp vùng (Nhấn Z để tắt). Giữ Ctrl + Kéo chuột để cuộn ảnh" : "Soi kính lúp phóng to vùng trỏ chuột (Phím Z)";
  if (!isLoupeActive) {
    loupeLens.style.display = "none";
    canvasWrap.style.cursor = "grab";
  } else {
    canvasWrap.style.cursor = "crosshair";
  }
}

// Drag & Pan Image: Hỗ trợ Giữ Ctrl + Chuột trái HOẶC Chuột giữa HOẶC Chuột trái khi tắt Loupe
canvasWrap.addEventListener("mousedown", e => {
  const isCtrlLeft = (e.ctrlKey || e.metaKey) && e.button === 0;
  const isMiddle = e.button === 1;
  const isNormalPan = !isLoupeActive && e.button === 0;

  if (isCtrlLeft || isMiddle || isNormalPan) {
    isPanning = true;
    startMouseX = e.clientX;
    startMouseY = e.clientY;
    startPanX = imgPanX;
    startPanY = imgPanY;
    canvasWrap.style.cursor = "grabbing";
    billImg.style.transition = "none";
    if (loupeLens) loupeLens.style.display = "none";
    e.preventDefault();
  }
});

window.addEventListener("mousemove", e => {
  if (isPanning) {
    imgPanX = startPanX + (e.clientX - startMouseX);
    imgPanY = startPanY + (e.clientY - startMouseY);
    updateImgTransform();
    if (loupeLens) loupeLens.style.display = "none";
    return;
  }

  if (!isLoupeActive || !billImg.naturalWidth) return;
  const rect = billImg.getBoundingClientRect();
  const mouseX = e.clientX;
  const mouseY = e.clientY;

  // Check if mouse inside bill image
  if (mouseX < rect.left || mouseX > rect.right || mouseY < rect.top || mouseY > rect.bottom) {
    loupeLens.style.display = "none";
    return;
  }

  loupeLens.style.display = "block";
  const lensRadius = 95; // 190 / 2
  loupeLens.style.left = (mouseX - lensRadius) + "px";
  loupeLens.style.top = (mouseY - lensRadius) + "px";

  // Calculate relative coordinates
  const relX = (mouseX - rect.left) / rect.width;
  const relY = (mouseY - rect.top) / rect.height;

  loupeLens.style.backgroundImage = `url("${billImg.src}")`;
  loupeLens.style.backgroundSize = `${rect.width * loupeZoom}px ${rect.height * loupeZoom}px`;
  const bgX = -(relX * rect.width * loupeZoom - lensRadius);
  const bgY = -(relY * rect.height * loupeZoom - lensRadius);
  loupeLens.style.backgroundPosition = `${bgX}px ${bgY}px`;
});

window.addEventListener("mouseup", () => {
  if (isPanning) {
    isPanning = false;
    billImg.style.transition = "transform 0.15s cubic-bezier(0.2,0,0,1)";
    canvasWrap.style.cursor = isLoupeActive ? "crosshair" : "grab";
  }
});

// Wheel: Cuộn ảnh lên/xuống (hoặc chỉnh độ phóng kính lúp khi đang soi)
canvasWrap.addEventListener("wheel", e => {
  if (isLoupeActive) {
    if (e.ctrlKey || e.metaKey) {
      // Giữ Ctrl + Lăn chuột để cuộn ảnh lên xuống
      e.preventDefault();
      imgPanY -= e.deltaY;
      updateImgTransform();
      return;
    }
    // Lăn chuột bình thường trong chế độ kính lúp để tăng giảm độ phóng đại
    e.preventDefault();
    if (e.deltaY < 0) {
      loupeZoom = Math.min(loupeZoom + 0.5, 6);
    } else {
      loupeZoom = Math.max(loupeZoom - 0.5, 1.5);
    }
    canvasWrap.dispatchEvent(new MouseEvent("mousemove", { clientX: e.clientX, clientY: e.clientY }));
  } else {
    // Khi kính lúp tắt, lăn chuột để cuộn dọc hóa đơn
    e.preventDefault();
    imgPanY -= e.deltaY;
    updateImgTransform();
  }
}, { passive: false });

// Keyboard shortcuts
window.addEventListener("keydown", e => {
  // Support closing popup message with Escape or Enter
  if (e.key === "Escape" || (e.key === "Enter" && document.getElementById("modal-popup-msg")?.style.display === "flex")) {
    const modal = document.getElementById("modal-popup-msg");
    if (modal && modal.style.display === "flex") {
      e.preventDefault();
      closePopupMessage();
      return;
    }
  }

  // Support Ctrl+S / Cmd+S anywhere, including inside input fields
  if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
    e.preventDefault();
    document.getElementById("btn-save").click();
    return;
  }
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowLeft") { document.getElementById("btn-prev").click(); }
  if (e.key === "ArrowRight") { document.getElementById("btn-next").click(); }
  if (e.key === "a" || e.key === "A") { document.getElementById("btn-approve").click(); }
  if (e.key === "r" || e.key === "R") { document.getElementById("btn-reject").click(); }
  if (e.key === "z" || e.key === "Z") { toggleLoupe(); }
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
    if (target === "batch") {
      renderBatchTable();
      updatePaginationUI();
    }
    if (target === "audit") renderGlobalAudit();
  });
});

// Batch table
function renderBatchTable() {
  const tbody = document.getElementById("batch-tbody");
  if (!allBills || allBills.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 40px;">Không tìm thấy hóa đơn nào phù hợp với bộ lọc</td></tr>`;
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

// Upload Modal Logic & Requirement 5: Duplicate Warning Handling
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
    formData.append("actor", getCurrentUser());
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

    // Requirement 5: Duplicate alert handling on UI
    if (data.is_duplicate && data.duplicate_info) {
      modalUpload.style.display = "none";
      showDuplicateModal(data);
      return;
    }

    uploadStatusBox.style.borderColor = "var(--success)";
    uploadStatusBox.style.color = "var(--success)";
    uploadStatusBox.innerHTML = `✅ <b>Thành công!</b> Đã bóc tách xong bill <b>#${data.bill_id}</b>. Đang chuyển sang màn hình soi duyệt...`;

    // Nạp lại danh sách hóa đơn và nhảy trực tiếp đến bill vừa upload
    setTimeout(async () => {
      modalUpload.style.display = "none";
      await loadStats();
      await loadBills();
      
      const newIdx = allBills.findIndex(b => b.BillId === data.bill_id);
      if (newIdx !== -1) {
        switchToInspector(newIdx);
      } else {
        switchToInspector(0);
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

// Duplicate Warning Modal Actions
function showDuplicateModal(data) {
  lastDupData = data;
  const dup = data.duplicate_info;
  const body = document.getElementById("dup-warning-body");
  body.innerHTML = `
    <div style="font-size:13px; font-weight:700; color:#fde68a; margin-bottom:6px;">
      ⚠️ Hệ thống phát hiện ảnh hóa đơn này giống 100% với hóa đơn đã có trên CSDL:
    </div>
    <ul style="margin: 0; padding-left: 20px; font-size: 12px; line-height: 1.8;">
      <li><b>Mã hóa đơn cũ:</b> <span style="color:var(--accent); font-weight:700;">#${dup.BillId}</span></li>
      <li><b>Tên file cũ:</b> ${dup.Filename}</li>
      <li><b>Trạng thái duyệt cũ:</b> <span class="status-tag ${dup.Status}" style="font-size:10px; padding:2px 6px;">${dup.Status}</span></li>
      <li><b>Thời gian tải lên trước:</b> ${dup.CreatedAt}</li>
      <li><b>Mã hóa đơn mới vừa tạo:</b> #${data.bill_id}</li>
    </ul>
  `;
  modalDupWarning.style.display = "flex";
}

document.getElementById("btn-dup-view-old").addEventListener("click", async () => {
  modalDupWarning.style.display = "none";
  if (!lastDupData || !lastDupData.duplicate_info) return;
  const oldId = lastDupData.duplicate_info.BillId;
  await loadBills();
  const idx = allBills.findIndex(b => b.BillId === oldId);
  if (idx !== -1) {
    switchToInspector(idx);
  } else {
    // If not found in current page, load it
    try {
      const res = await fetch(`/api/bills/${oldId}`);
      const oldBill = await res.json();
      allBills = [oldBill, ...allBills];
      switchToInspector(0);
    } catch(e) {
      alert(`Đã có hóa đơn #${oldId} trên hệ thống.`);
    }
  }
});

document.getElementById("btn-dup-keep-new").addEventListener("click", async () => {
  modalDupWarning.style.display = "none";
  if (!lastDupData) return;
  await loadBills();
  const idx = allBills.findIndex(b => b.BillId === lastDupData.bill_id);
  if (idx !== -1) {
    switchToInspector(idx);
  } else {
    switchToInspector(0);
  }
});

document.getElementById("btn-dup-reject-new").addEventListener("click", async () => {
  if (!lastDupData) return;
  const newId = lastDupData.bill_id;
  const oldId = lastDupData.duplicate_info ? lastDupData.duplicate_info.BillId : "cũ";
  modalDupWarning.style.display = "none";
  
  const currentUser = getCurrentUser();
  await fetch(`/api/bills/${newId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Actor": currentUser },
    body: JSON.stringify({
      status: "REJECTED",
      actor: currentUser,
      reject_reason: `Từ chối do ảnh trùng lặp 100% với Bill #${oldId}`
    })
  });
  alert(`✅ Đã từ chối hóa đơn #${newId} do trùng lặp với Bill #${oldId}.`);
  await loadStats();
  await loadBills();
  if (allBills.length > 0) switchToInspector(0);
});

init();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_review:app", host="0.0.0.0", port=8000, reload=True)
