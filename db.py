"""
Module quản lý kết nối và thao tác CSDL MS-SQL (CLMHQ4GIGA)
Phục vụ 3 User Story:
- US 1: Review workflow (PENDING -> APPROVED / REJECTED)
- US 2: Inline edit (Chỉnh sửa số tiền, outlet, bill number, datetime)
- US 3: Audit trail (Ghi vết lịch sử mọi thay đổi)
"""
import os
import json
import pymssql
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent
FREETDS_CONF_PATH = BASE_DIR / "freetds.conf"
DB_CONFIG_PATH = BASE_DIR / "db_config.json"

# Thiết lập FreeTDS config để tương thích SQL Server 2012 không lỗi TLS handshake
os.environ["FREETDSCONF"] = str(FREETDS_CONF_PATH)


def load_db_config() -> dict:
    if not DB_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {DB_CONFIG_PATH}")
    with open(DB_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    
    # Nếu file cấu hình có chứa các profile môi trường (dev, pilot, prod)
    if "environments" in raw:
        # Ưu tiên biến môi trường hệ thống OCR_ENV, nếu không thì lấy current_environment trong file
        env_name = os.environ.get("OCR_ENV") or raw.get("current_environment") or "dev"
        env_name = env_name.lower().strip()
        envs = raw["environments"]
        if env_name not in envs:
            raise ValueError(f"Môi trường '{env_name}' không tồn tại trong db_config.json. Các môi trường hợp lệ: {list(envs.keys())}")
        active_cfg = dict(envs[env_name])
        active_cfg["_active_env"] = env_name
        return active_cfg
    
    # Cấu hình phẳng truyền thống
    raw["_active_env"] = "custom"
    return raw


def get_connection():
    cfg = load_db_config()
    return pymssql.connect(
        server=cfg.get("server", "CLMHQ4GIGA"),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        port=cfg.get("port", 1433),
        autocommit=False,
        timeout=10,
    )


def init_db():
    """Khởi tạo 2 bảng OcrBills và OcrBillAuditLogs nếu chưa có."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Bảng OcrBills
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OcrBills')
        BEGIN
            CREATE TABLE OcrBills (
                BillId INT IDENTITY(1,1) PRIMARY KEY,
                Filename NVARCHAR(255) NOT NULL UNIQUE,
                ImagePath NVARCHAR(500) NOT NULL,
                Status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                
                -- OCR RAW / INITIAL
                OcrBrand NVARCHAR(100) NULL,
                OcrOutletRaw NVARCHAR(255) NULL,
                OcrOutletNumber NVARCHAR(50) NULL,
                OcrOutletName NVARCHAR(255) NULL,
                OcrMatchScore FLOAT NULL,
                OcrBillNumber NVARCHAR(100) NULL,
                OcrDateTime DATETIME NULL,
                OcrTotal BIGINT NULL,
                OcrIsValid BIT NOT NULL DEFAULT 0,
                OcrLatency FLOAT NULL,
                OcrRawOutput NVARCHAR(MAX) NULL,
                
                -- FINAL / APPROVED
                FinalOutletNumber NVARCHAR(50) NULL,
                FinalOutletName NVARCHAR(255) NULL,
                FinalBillNumber NVARCHAR(100) NULL,
                FinalDateTime DATETIME NULL,
                FinalTotal BIGINT NULL,
                
                -- REVIEW AUDIT META
                IsManualEdited BIT NOT NULL DEFAULT 0,
                ReviewedBy NVARCHAR(100) NULL,
                ReviewedAt DATETIME NULL,
                RejectReason NVARCHAR(500) NULL,
                CreatedAt DATETIME DEFAULT GETDATE(),
                UpdatedAt DATETIME DEFAULT GETDATE()
            );
            CREATE NONCLUSTERED INDEX IX_OcrBills_Status ON OcrBills(Status);
        END
        """)

        # 2. Bảng OcrBillAuditLogs (US 3)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OcrBillAuditLogs')
        BEGIN
            CREATE TABLE OcrBillAuditLogs (
                AuditId INT IDENTITY(1,1) PRIMARY KEY,
                BillId INT NOT NULL,
                Action VARCHAR(30) NOT NULL,
                FieldName NVARCHAR(50) NULL,
                OldValue NVARCHAR(MAX) NULL,
                NewValue NVARCHAR(MAX) NULL,
                Actor NVARCHAR(100) NOT NULL,
                Note NVARCHAR(500) NULL,
                CreatedAt DATETIME DEFAULT GETDATE(),
                CONSTRAINT FK_OcrBillAuditLogs_Bills FOREIGN KEY (BillId) REFERENCES OcrBills(BillId)
            );
            CREATE NONCLUSTERED INDEX IX_OcrBillAuditLogs_BillId ON OcrBillAuditLogs(BillId);
        END
        """)

        conn.commit()
        print("[+] Khởi tạo bảng CSDL OcrBills và OcrBillAuditLogs thành công!")
    finally:
        conn.close()


def seed_from_csv(csv_path=None):
    """Nạp dữ liệu từ results.csv vào OcrBills nếu chưa có."""
    import pandas as pd

    if csv_path is None:
        csv_path = BASE_DIR / "results.csv"
    if not Path(csv_path).exists():
        print(f"[!] Không tìm thấy file {csv_path}")
        return 0

    df = pd.read_csv(csv_path)
    conn = get_connection()
    cursor = conn.cursor()
    inserted = 0

    try:
        for _, row in df.iterrows():
            fname = str(row["filename"]).strip()
            # Kiểm tra xem bill đã có trong DB chưa
            cursor.execute("SELECT BillId FROM OcrBills WHERE Filename = %s", (fname,))
            if cursor.fetchone():
                continue

            # Parse datetime an toàn
            dt_val = None
            if pd.notna(row.get("bill_datetime")) and str(row.get("bill_datetime")).strip():
                try:
                    dt_val = datetime.fromisoformat(str(row["bill_datetime"]).strip())
                except Exception:
                    dt_val = None

            total_val = int(row["bill_total"]) if pd.notna(row.get("bill_total")) else 0
            is_valid = 1 if str(row.get("is_valid")).lower() in ("true", "1") else 0
            score = float(row["match_score"]) if pd.notna(row.get("match_score")) else 0.0
            lat = float(row["latency"]) if pd.notna(row.get("latency")) else 0.0

            out_num = str(row["outlet_number"]).strip() if pd.notna(row.get("outlet_number")) else None
            out_name = str(row["resolved_outlet"]).strip() if pd.notna(row.get("resolved_outlet")) else None
            bill_num = str(row["bill_number"]).strip() if pd.notna(row.get("bill_number")) else ""
            brand = str(row["raw_brand"]).strip() if pd.notna(row.get("raw_brand")) else ""
            outlet_raw = str(row["raw_outlet"]).strip() if pd.notna(row.get("raw_outlet")) else ""
            raw_out = str(row["raw_output"]).strip() if pd.notna(row.get("raw_output")) else ""

            # Khởi tạo giá trị Final mặc định bằng giá trị OCR gợi ý
            cursor.execute("""
            INSERT INTO OcrBills (
                Filename, ImagePath, Status,
                OcrBrand, OcrOutletRaw, OcrOutletNumber, OcrOutletName, OcrMatchScore,
                OcrBillNumber, OcrDateTime, OcrTotal, OcrIsValid, OcrLatency, OcrRawOutput,
                FinalOutletNumber, FinalOutletName, FinalBillNumber, FinalDateTime, FinalTotal,
                IsManualEdited
            ) VALUES (
                %s, %s, 'PENDING',
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                0
            )
            """, (
                fname, f"TEST_IMAGES/{fname}",
                brand, outlet_raw, out_num, out_name, score,
                bill_num, dt_val, total_val, is_valid, lat, raw_out,
                out_num, out_name, bill_num, dt_val, total_val
            ))
            inserted += 1

        conn.commit()
        print(f"[+] Đã import {inserted} hóa đơn mới vào bảng OcrBills!")
        return inserted
    finally:
        conn.close()


def get_bill_stats():
    """Lấy thống kê số lượng bill theo trạng thái."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN Status = 'PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN Status = 'APPROVED' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN Status = 'REJECTED' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN IsManualEdited = 1 THEN 1 ELSE 0 END) as manual_edited
        FROM OcrBills
        """)
        row = cursor.fetchone()
        return row or {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "manual_edited": 0}
    finally:
        conn.close()


def get_bills(
    status=None,
    search=None,
    edit_status=None,
    brand=None,
    outlet=None,
    page=1,
    limit=50
):
    """Lấy danh sách hóa đơn kèm phân trang, bộ lọc đa chiều (trạng thái duyệt, sửa tay, brand, outlet) và tìm kiếm."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        clauses = []
        params = []
        
        # 1. Lọc theo trạng thái duyệt (Status: PENDING, APPROVED, REJECTED)
        if status and status != "ALL":
            clauses.append("Status = %s")
            params.append(status)

        # 2. Lọc theo trạng thái sửa tay (IsManualEdited: 1 / 0)
        if edit_status is not None and str(edit_status) != "ALL":
            if str(edit_status).lower() in ("1", "true", "edited"):
                clauses.append("IsManualEdited = 1")
            elif str(edit_status).lower() in ("0", "false", "unedited"):
                clauses.append("IsManualEdited = 0")

        # 3. Lọc theo Brand
        if brand and brand != "ALL":
            clauses.append("(OcrBrand LIKE %s)")
            params.append(f"%{brand}%")

        # 4. Lọc theo Cửa hàng / Gian hàng (Outlet)
        if outlet and outlet != "ALL":
            clauses.append("(FinalOutletName LIKE %s OR OcrOutletName LIKE %s OR FinalOutletNumber = %s)")
            params.extend([f"%{outlet}%", f"%{outlet}%", outlet])

        # 5. Tìm kiếm toàn văn theo các trường text (Số hóa đơn, Cửa hàng, Brand, Tên file)
        if search and search.strip():
            kw = f"%{search.strip()}%"
            clauses.append("""(
                Filename LIKE %s OR 
                FinalBillNumber LIKE %s OR 
                OcrBillNumber LIKE %s OR 
                FinalOutletName LIKE %s OR 
                OcrOutletName LIKE %s OR 
                OcrBrand LIKE %s OR 
                FinalOutletNumber LIKE %s
            )""")
            params.extend([kw, kw, kw, kw, kw, kw, kw])

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        # Đếm tổng
        count_sql = f"SELECT COUNT(*) as total FROM OcrBills {where_sql}"
        cursor.execute(count_sql, tuple(params))
        total = cursor.fetchone()["total"]

        # Lấy trang dữ liệu (T-SQL pagination với OFFSET / FETCH NEXT trong SQL 2012)
        offset = (page - 1) * limit
        query_sql = f"""
        SELECT 
            BillId, Filename, ImagePath, Status,
            OcrBrand, OcrOutletName, OcrBillNumber, OcrTotal, OcrIsValid, OcrMatchScore, OcrLatency,
            FinalOutletNumber, FinalOutletName, FinalBillNumber, FinalDateTime, FinalTotal,
            IsManualEdited, ReviewedBy, ReviewedAt, RejectReason, FileHash
        FROM OcrBills
        {where_sql}
        ORDER BY BillId DESC
        OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """
        cursor.execute(query_sql, tuple(params))
        items = cursor.fetchall()
        return {"total": total, "page": page, "limit": limit, "items": items}
    finally:
        conn.close()


def get_bill_detail(bill_id):
    """Lấy chi tiết 1 hóa đơn cùng toàn bộ lịch sử kiểm toán của nó."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("SELECT * FROM OcrBills WHERE BillId = %s", (bill_id,))
        bill = cursor.fetchone()
        if not bill:
            return None

        # Lấy audit logs
        cursor.execute("""
        SELECT AuditId, BillId, Action, FieldName, OldValue, NewValue, Actor, Note, CreatedAt
        FROM OcrBillAuditLogs
        WHERE BillId = %s
        ORDER BY CreatedAt DESC
        """, (bill_id,))
        logs = cursor.fetchall()
        bill["audit_logs"] = logs
        return bill
    finally:
        conn.close()


def update_bill_review(bill_id, status, actor="CRM Admin", reject_reason=None):
    """Xác nhận duyệt (APPROVED) hoặc từ chối (REJECTED) - US 1."""
    if status not in ("APPROVED", "REJECTED"):
        raise ValueError("Status chỉ được là APPROVED hoặc REJECTED")

    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("SELECT Status FROM OcrBills WHERE BillId = %s", (bill_id,))
        old = cursor.fetchone()
        if not old:
            raise ValueError(f"Không tìm thấy hóa đơn ID {bill_id}")

        old_status = old["Status"]
        now = datetime.now()

        cursor.execute("""
        UPDATE OcrBills 
        SET Status = %s, ReviewedBy = %s, ReviewedAt = %s, RejectReason = %s, UpdatedAt = %s
        WHERE BillId = %s
        """, (status, actor, now, reject_reason, now, bill_id))

        # Ghi log kiểm toán (US 3)
        cursor.execute("""
        INSERT INTO OcrBillAuditLogs (BillId, Action, FieldName, OldValue, NewValue, Actor, Note, CreatedAt)
        VALUES (%s, %s, 'Status', %s, %s, %s, %s, %s)
        """, (bill_id, status, old_status, status, actor, reject_reason or "", now))

        conn.commit()
        return True
    finally:
        conn.close()


def update_bill_fields(bill_id, updates: dict, actor="CRM Admin", note=None):
    """Chỉnh sửa thông tin hóa đơn (US 2) và tự động ghi vết kiểm toán (US 3)."""
    allowed_fields = {
        "final_outlet_number": "FinalOutletNumber",
        "final_outlet_name": "FinalOutletName",
        "final_bill_number": "FinalBillNumber",
        "final_datetime": "FinalDateTime",
        "final_total": "FinalTotal",
    }

    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("SELECT * FROM OcrBills WHERE BillId = %s", (bill_id,))
        current = cursor.fetchone()
        if not current:
            raise ValueError(f"Không tìm thấy hóa đơn ID {bill_id}")

        set_clauses = []
        set_params = []
        audit_entries = []
        now = datetime.now()

        for k, v in updates.items():
            col = allowed_fields.get(k.lower())
            if not col:
                continue

            old_val = current.get(col)
            # Chuẩn hóa để so sánh
            old_str = "" if old_val is None else str(old_val)
            new_str = "" if v is None else str(v)

            if old_str != new_str:
                set_clauses.append(f"{col} = %s")
                set_params.append(v)
                audit_entries.append((
                    bill_id, "UPDATE_FIELD", col, old_str, new_str, actor, note or "", now
                ))

        if audit_entries:
            set_clauses.append("IsManualEdited = 1")
            set_clauses.append("UpdatedAt = %s")
            set_params.append(now)
            set_params.append(bill_id)

            sql = f"UPDATE OcrBills SET {', '.join(set_clauses)} WHERE BillId = %s"
            cursor.execute(sql, tuple(set_params))

            # Ghi nhật ký kiểm toán cho từng trường thay đổi
            for entry in audit_entries:
                cursor.execute("""
                INSERT INTO OcrBillAuditLogs (BillId, Action, FieldName, OldValue, NewValue, Actor, Note, CreatedAt)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, entry)

            conn.commit()
            return len(audit_entries)
        return 0
    finally:
        conn.close()


def get_all_audit_logs(limit=200):
    """Dành cho Auditor: Lấy danh sách toàn bộ các thay đổi trong hệ thống."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(f"""
        SELECT TOP {limit} 
            a.AuditId, a.BillId, b.Filename, a.Action, a.FieldName, 
            a.OldValue, a.NewValue, a.Actor, a.Note, a.CreatedAt
        FROM OcrBillAuditLogs a
        JOIN OcrBills b ON a.BillId = b.BillId
        ORDER BY a.CreatedAt DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def find_duplicate_bill(file_hash: str) -> Optional[dict]:
    """Tìm hóa đơn đã tồn tại trong CSDL có cùng hash nội dung ảnh (trùng lặp)."""
    if not file_hash:
        return None
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
        SELECT TOP 1 BillId, Filename, ImagePath, Status, FinalBillNumber, FinalTotal, CreatedAt
        FROM OcrBills
        WHERE FileHash = %s
        ORDER BY BillId DESC
        """, (file_hash,))
        return cursor.fetchone()
    finally:
        conn.close()


def insert_ocr_bill(data: dict) -> int:
    """Thêm một hóa đơn mới vào bảng OcrBills sau khi nhận ảnh hoặc chạy OCR."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now()
        dt_val = None
        if data.get("bill_datetime"):
            try:
                dt_val = datetime.fromisoformat(str(data["bill_datetime"]).strip())
            except Exception:
                dt_val = None

        total_val = int(data.get("bill_total") or 0)
        is_valid = 1 if data.get("is_valid_bill") else 0
        score = float(data.get("match_score") or 0.0)
        lat = float(data.get("latency") or 0.0)

        out_num = data.get("outlet_number")
        out_name = data.get("resolved_outlet")
        bill_num = data.get("bill_number") or ""
        brand = data.get("raw_brand") or ""
        outlet_raw = data.get("raw_outlet") or ""
        raw_out = data.get("raw_output") or ""
        status = data.get("status") or "PENDING"
        filename = data["filename"]
        image_path = data.get("image_path") or f"uploads/{filename}"
        file_hash = data.get("file_hash")

        cursor.execute("""
        INSERT INTO OcrBills (
            Filename, ImagePath, Status,
            OcrBrand, OcrOutletRaw, OcrOutletNumber, OcrOutletName, OcrMatchScore,
            OcrBillNumber, OcrDateTime, OcrTotal, OcrIsValid, OcrLatency, OcrRawOutput,
            FinalOutletNumber, FinalOutletName, FinalBillNumber, FinalDateTime, FinalTotal,
            IsManualEdited, FileHash, CreatedAt, UpdatedAt
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            0, %s, %s, %s
        );
        SELECT @@IDENTITY;
        """, (
            filename, image_path, status,
            brand, outlet_raw, out_num, out_name, score,
            bill_num, dt_val, total_val, is_valid, lat, raw_out,
            out_num, out_name, bill_num, dt_val, total_val,
            file_hash, now, now
        ))
        row = cursor.fetchone()
        bill_id = int(row[0]) if row and row[0] is not None else None

        actor = data.get("actor", "CRM Mobile")
        note = data.get("note", "Tải lên từ Mobile qua API")
        if bill_id:
            cursor.execute("""
            INSERT INTO OcrBillAuditLogs (BillId, Action, FieldName, OldValue, NewValue, Actor, Note, CreatedAt)
            VALUES (%s, 'UPLOAD', 'Status', '', %s, %s, %s, %s)
            """, (bill_id, status, actor, note, now))

        conn.commit()
        return bill_id
    finally:
        conn.close()


def update_bill_ocr_result(bill_id: int, ocr_data: dict):
    """Cập nhật kết quả OCR sau khi background worker bóc tách xong."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now()
        dt_val = None
        if ocr_data.get("bill_datetime"):
            try:
                dt_val = datetime.fromisoformat(str(ocr_data["bill_datetime"]).strip())
            except Exception:
                dt_val = None

        total_val = int(ocr_data.get("bill_total") or 0)
        is_valid = 1 if ocr_data.get("is_valid_bill") else 0
        score = float(ocr_data.get("match_score") or 0.0)
        lat = float(ocr_data.get("latency") or 0.0)
        out_num = ocr_data.get("outlet_number")
        out_name = ocr_data.get("resolved_outlet")
        bill_num = ocr_data.get("bill_number") or ""
        brand = ocr_data.get("raw_brand") or ""
        outlet_raw = ocr_data.get("raw_outlet") or ""
        raw_out = ocr_data.get("raw_output") or ""

        cursor.execute("""
        UPDATE OcrBills
        SET 
            OcrBrand = %s,
            OcrOutletRaw = %s,
            OcrOutletNumber = %s,
            OcrOutletName = %s,
            OcrMatchScore = %s,
            OcrBillNumber = %s,
            OcrDateTime = %s,
            OcrTotal = %s,
            OcrIsValid = %s,
            OcrLatency = %s,
            OcrRawOutput = %s,
            FinalOutletNumber = CASE WHEN IsManualEdited = 0 THEN %s ELSE FinalOutletNumber END,
            FinalOutletName = CASE WHEN IsManualEdited = 0 THEN %s ELSE FinalOutletName END,
            FinalBillNumber = CASE WHEN IsManualEdited = 0 THEN %s ELSE FinalBillNumber END,
            FinalDateTime = CASE WHEN IsManualEdited = 0 THEN %s ELSE FinalDateTime END,
            FinalTotal = CASE WHEN IsManualEdited = 0 THEN %s ELSE FinalTotal END,
            UpdatedAt = %s
        WHERE BillId = %s
        """, (
            brand, outlet_raw, out_num, out_name, score,
            bill_num, dt_val, total_val, is_valid, lat, raw_out,
            out_num, out_name, bill_num, dt_val, total_val,
            now, bill_id
        ))

        action_name = "OCR_SUCCESS" if is_valid else "OCR_FAILED"
        total_fmt = f"{total_val:,}".replace(",", ".")
        note = f"Bóc tách ngầm ({lat}s). Quán: {out_name or 'Chưa khớp'}, Tiền: {total_fmt} đ"
        cursor.execute("""
        INSERT INTO OcrBillAuditLogs (BillId, Action, FieldName, OldValue, NewValue, Actor, Note, CreatedAt)
        VALUES (%s, %s, 'OcrStatus', 'QUEUED', 'PROCESSED', 'AI Worker', %s, %s)
        """, (bill_id, action_name, note, now))

        conn.commit()
    finally:
        conn.close()


def get_unprocessed_bills(limit=50):
    """Lấy danh sách các hóa đơn PENDING chưa từng được bóc tách OCR."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(f"""
        SELECT TOP {int(limit)}
            BillId, Filename, ImagePath, Status, CreatedAt
        FROM OcrBills
        WHERE Status = 'PENDING' 
          AND (OcrLatency IS NULL OR OcrLatency = 0)
        ORDER BY BillId ASC
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def get_bills_by_ids(bill_ids: list):
    """Lấy danh sách hóa đơn theo danh sách ID cụ thể."""
    if not bill_ids:
        return []
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        placeholders = ", ".join(["%s"] * len(bill_ids))
        cursor.execute(f"""
        SELECT BillId, Filename, ImagePath, Status, CreatedAt
        FROM OcrBills
        WHERE BillId IN ({placeholders})
        ORDER BY BillId ASC
        """, tuple(bill_ids))
        return cursor.fetchall()
    finally:
        conn.close()


def fetch_master_outlets_from_db():
    """Truy vấn danh mục cửa hàng đang hoạt động từ bảng G_Outlet và G_Brand trong MS-SQL."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute("""
        SELECT 
            o.ID AS outlet_id,
            o.Number AS outlet_number,
            o.OutletName AS outlet_name,
            b.ID AS brand_id,
            b.Number AS brand_number,
            b.BrandName AS brand_name,
            o.Address AS outlet_address
        FROM G_Outlet o WITH (NOLOCK)
        INNER JOIN G_Brand b WITH (NOLOCK) ON o.BrandID = b.ID
        WHERE o.IsActive = 1 AND o.IsUsed = 1
        ORDER BY o.OutletName
        """)
        return cursor.fetchall()
    finally:
        conn.close()


def sync_master_outlets_file(target_file=None):
    """Đồng bộ từ CSDL và ghi đè file master_outlets.json chuẩn UTF-8."""
    if target_file is None:
        target_file = BASE_DIR / "master_outlets.json"
    outlets = fetch_master_outlets_from_db()
    if outlets:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(outlets, f, ensure_ascii=False, indent=2)
        return len(outlets)
    return 0


if __name__ == "__main__":
    init_db()
    seed_from_csv()
    stats = get_bill_stats()
    print("Thống kê CSDL hiện tại:", stats)
    synced = sync_master_outlets_file()
    print(f"Đã đồng bộ {synced} cửa hàng từ MS-SQL vào master_outlets.json!")
