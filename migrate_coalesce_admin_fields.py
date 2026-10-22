#!/usr/bin/env python3
"""
Migration script: Bổ sung các cột Admin_* (Admin Override) vào bảng OcrBills
và khởi tạo SQL View v_OcrBillsFinal theo nguyên tắc Coalesce Pattern:
Final = COALESCE(Admin, AI)
"""
import db

def run_migration():
    conn = db.get_connection()
    cursor = conn.cursor(as_dict=True)
    try:
        print("[*] Kiểm tra các cột trong bảng OcrBills...")
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'OcrBills'")
        existing_cols = set(r['COLUMN_NAME'] for r in cursor.fetchall())
        
        new_cols = [
            ("AdminBrand", "NVARCHAR(100) NULL"),
            ("AdminOutletNumber", "NVARCHAR(50) NULL"),
            ("AdminOutletName", "NVARCHAR(250) NULL"),
            ("AdminBillNumber", "NVARCHAR(100) NULL"),
            ("AdminDateTime", "DATETIME NULL"),
            ("AdminTotal", "BIGINT NULL"),
            ("AdminNote", "NVARCHAR(500) NULL"),
        ]

        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                sql = f"ALTER TABLE OcrBills ADD {col_name} {col_def}"
                print(f"  + Thêm cột: {col_name}...")
                cursor.execute(sql)
                conn.commit()
            else:
                print(f"  ✓ Cột {col_name} đã tồn tại.")

        # Đồng bộ dữ liệu cũ: nếu IsManualEdited = 1, chuyển dữ liệu Final sang Admin nếu có sự khác biệt
        print("[*] Đồng bộ dữ liệu hiện tại sang các cột Admin_*...")
        sync_sql = """
        UPDATE OcrBills
        SET 
            AdminTotal = CASE WHEN FinalTotal IS NOT NULL AND (OcrTotal IS NULL OR FinalTotal != OcrTotal) THEN FinalTotal ELSE NULL END,
            AdminOutletName = CASE WHEN FinalOutletName IS NOT NULL AND (OcrOutletName IS NULL OR FinalOutletName != OcrOutletName) THEN FinalOutletName ELSE NULL END,
            AdminBillNumber = CASE WHEN FinalBillNumber IS NOT NULL AND (OcrBillNumber IS NULL OR FinalBillNumber != OcrBillNumber) THEN FinalBillNumber ELSE NULL END,
            AdminDateTime = CASE WHEN FinalDateTime IS NOT NULL AND (OcrDateTime IS NULL OR FinalDateTime != OcrDateTime) THEN FinalDateTime ELSE NULL END,
            AdminOutletNumber = CASE WHEN FinalOutletNumber IS NOT NULL AND (OcrOutletNumber IS NULL OR FinalOutletNumber != OcrOutletNumber) THEN FinalOutletNumber ELSE NULL END
        WHERE IsManualEdited = 1;
        """
        cursor.execute(sync_sql)
        conn.commit()

        # Tạo hoặc cập nhật SQL View v_OcrBillsFinal
        print("[*] Tạo hoặc cập nhật SQL View v_OcrBillsFinal...")
        view_sql = """
        IF EXISTS (SELECT * FROM sys.views WHERE name = 'v_OcrBillsFinal')
            DROP VIEW v_OcrBillsFinal;
        """
        cursor.execute(view_sql)
        conn.commit()

        create_view_sql = """
        CREATE VIEW v_OcrBillsFinal AS
        SELECT 
            BillId, Filename, ImagePath, Status,
            -- Dữ liệu AI gốc (Raw AI Evidence)
            OcrBrand, OcrOutletRaw, OcrOutletNumber, OcrOutletName, OcrMatchScore,
            OcrBillNumber, OcrDateTime, OcrTotal, OcrIsValid, OcrLatency,
            -- Dữ liệu Admin sửa (Admin Override - NULL nếu không sửa)
            AdminBrand, AdminOutletNumber, AdminOutletName, AdminBillNumber, AdminDateTime, AdminTotal, AdminNote,
            -- Dữ liệu Chốt (COALESCE: Ưu tiên Admin sửa, nếu không lấy AI)
            COALESCE(AdminOutletNumber, OcrOutletNumber) AS FinalOutletNumber,
            COALESCE(AdminOutletName, OcrOutletName) AS FinalOutletName,
            COALESCE(AdminBillNumber, OcrBillNumber) AS FinalBillNumber,
            COALESCE(AdminDateTime, OcrDateTime) AS FinalDateTime,
            COALESCE(AdminTotal, OcrTotal) AS FinalTotal,
            -- Cờ đánh dấu có can thiệp thủ công
            CASE WHEN (AdminTotal IS NOT NULL OR AdminOutletName IS NOT NULL OR AdminBillNumber IS NOT NULL OR AdminDateTime IS NOT NULL OR AdminBrand IS NOT NULL) 
                 THEN 1 ELSE 0 END AS IsManualEdited,
            ReviewedBy, ReviewedAt, RejectReason, FileHash, CreatedAt, UpdatedAt
        FROM OcrBills;
        """
        cursor.execute(create_view_sql)
        conn.commit()
        print("  ✓ Đã tạo View v_OcrBillsFinal thành công!")

        # Kiểm tra thử View
        cursor.execute("SELECT TOP 3 BillId, OcrTotal, AdminTotal, FinalTotal, IsManualEdited FROM v_OcrBillsFinal ORDER BY BillId DESC")
        rows = cursor.fetchall()
        print("[*] Xem thử 3 bản ghi đầu tiên qua View v_OcrBillsFinal:")
        for r in rows:
            print(f"  Bill #{r['BillId']}: AI Total = {r['OcrTotal']} | Admin Total = {r['AdminTotal']} | Final = {r['FinalTotal']} | IsManualEdited = {r['IsManualEdited']}")

        print("[+] Migration hoàn tất thành công!")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
