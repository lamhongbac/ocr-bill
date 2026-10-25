-- =======================================================================
-- SCRIPT KHỞI TẠO CSDL CHO DEMO DUYỆT HÓA ĐƠN & VẾT KIỂM TOÁN (GATE 1/2)
-- Database: CLMHQ4GIGA
-- Phục vụ: US 1 (Review), US 2 (Inline Edit), US 3 (Audit Trail)
-- =======================================================================

USE [CLMHQ4GIGA]
GO

-- 1. BẢNG OcrBills (Quản lý hóa đơn & Kết quả duyệt)
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OcrBills')
BEGIN
    CREATE TABLE OcrBills (
        BillId INT IDENTITY(1,1) PRIMARY KEY,
        Filename NVARCHAR(255) NOT NULL UNIQUE,
        ImagePath NVARCHAR(500) NOT NULL,
        Status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
        
        -- Dữ liệu OCR AI đọc ban đầu (Bất biến làm đối chứng)
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
        
        -- Dữ liệu duyệt chính thức (CRM Admin sửa hoặc xác nhận)
        FinalOutletNumber NVARCHAR(50) NULL,
        FinalOutletName NVARCHAR(255) NULL,
        FinalBillNumber NVARCHAR(100) NULL,
        FinalDateTime DATETIME NULL,
        FinalTotal BIGINT NULL,
        
        -- Thông tin phiên duyệt
        IsManualEdited BIT NOT NULL DEFAULT 0,
        ReviewedBy NVARCHAR(100) NULL,
        ReviewedAt DATETIME NULL,
        -- Kiểm soát trùng lặp ảnh (Anti-duplicate)
        FileHash VARCHAR(64) NULL,
        CreatedAt DATETIME DEFAULT GETDATE(),
        UpdatedAt DATETIME DEFAULT GETDATE()
    );

    CREATE NONCLUSTERED INDEX IX_OcrBills_Status ON OcrBills(Status);
    CREATE NONCLUSTERED INDEX IX_OcrBills_FileHash ON OcrBills(FileHash);
    PRINT 'Đã tạo bảng OcrBills thành công!';
END
ELSE
BEGIN
    PRINT 'Bảng OcrBills đã tồn tại.';
END
GO

-- 2. BẢNG OcrBillAuditLogs (Vết kiểm toán chi tiết cho Auditor - US 3)
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OcrBillAuditLogs')
BEGIN
    CREATE TABLE OcrBillAuditLogs (
        AuditId INT IDENTITY(1,1) PRIMARY KEY,
        BillId INT NOT NULL,
        Action VARCHAR(30) NOT NULL,               -- 'APPROVE', 'REJECT', 'UPDATE_FIELD'
        FieldName NVARCHAR(50) NULL,               -- 'FinalTotal', 'FinalOutletName',...
        OldValue NVARCHAR(MAX) NULL,               -- Giá trị trước khi sửa
        NewValue NVARCHAR(MAX) NULL,               -- Giá trị sau khi sửa
        Actor NVARCHAR(100) NOT NULL,              -- Người thực hiện (Username/Email)
        Note NVARCHAR(500) NULL,                   -- Lý do điều chỉnh
        CreatedAt DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_OcrBillAuditLogs_Bills FOREIGN KEY (BillId) REFERENCES OcrBills(BillId)
    );

    CREATE NONCLUSTERED INDEX IX_OcrBillAuditLogs_BillId ON OcrBillAuditLogs(BillId);
    PRINT 'Đã tạo bảng OcrBillAuditLogs thành công!';
END
ELSE
BEGIN
    PRINT 'Bảng OcrBillAuditLogs đã tồn tại.';
END
GO

-- 3. CẤP QUYỀN THAO TÁC DỮ LIỆU CHO USER crmapp1
GRANT SELECT, INSERT, UPDATE, DELETE ON OcrBills TO crmapp1;
GRANT SELECT, INSERT, UPDATE, DELETE ON OcrBillAuditLogs TO crmapp1;
PRINT 'Đã cấp quyền SELECT, INSERT, UPDATE, DELETE cho crmapp1 thành công!';
GO
