-- =======================================================================
-- SCRIPT KHỞI TẠO TOÀN DIỆN CSDL CHO HỆ THỐNG OCR BILL & REVIEW (MÔI TRƯỜNG DEV / MỚI)
-- Phục vụ: 
--   1. US 1: Review workflow (PENDING -> APPROVED / REJECTED)
--   2. US 2: Inline edit & Khóa hóa đơn đã chốt
--   3. US 3: Audit trail (Vết kiểm toán chi tiết)
--   4. Danh mục Master: G_Brand & G_Outlet (So khớp AI & Bộ lọc đa chiều)
--   5. Kiểm soát trùng lặp: FileHash (SHA-256)
-- =======================================================================

-- 0. TẠO CSDL NẾU CHƯA CÓ (TÙY CHỌN, ĐỔI TÊN NẾU CẦN)
-- IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'CLMHQ_DEV')
-- BEGIN
--     CREATE DATABASE [CLMHQ_DEV];
--     PRINT N'Đã tạo mới Database CLMHQ_DEV thành công!';
-- END
-- GO
-- USE [CLMHQ_DEV];
-- GO

SET NOCOUNT ON;
PRINT N'Bắt đầu cấu hình Database...';
GO

-- =======================================================================
-- 1. BẢNG G_Brand (Danh mục Thương hiệu - Master Brand)
-- =======================================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'G_Brand')
BEGIN
    CREATE TABLE G_Brand (
        ID INT NOT NULL PRIMARY KEY,
        CompanyID INT NOT NULL DEFAULT 1,
        Number VARCHAR(20) NOT NULL,
        BrandName NVARCHAR(50) NULL,
        ConceptName NVARCHAR(50) NULL,
        ConceptIndex INT NULL,
        Logo VARCHAR(250) NULL,
        PriceFrom DECIMAL(18,2) NULL,
        PriceTo DECIMAL(18,2) NULL,
        Tags NVARCHAR(100) NULL,
        Description NVARCHAR(MAX) NULL,
        CreatedOn DATETIME DEFAULT GETDATE(),
        CreatedBy VARCHAR(20) NULL,
        ModifiedOn DATETIME NULL,
        ModifiedBy VARCHAR(20) NULL,
        About NVARCHAR(500) NULL,
        ibeaconID INT NULL
    );

    CREATE NONCLUSTERED INDEX IX_G_Brand_Number ON G_Brand(Number);
    PRINT N'1. Đã tạo bảng G_Brand thành công!';
END
ELSE
BEGIN
    PRINT N'1. Bảng G_Brand đã tồn tại.';
END
GO

-- =======================================================================
-- 2. BẢNG G_Outlet (Danh mục Cửa hàng / Gian hàng - Master Outlet)
-- =======================================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'G_Outlet')
BEGIN
    CREATE TABLE G_Outlet (
        ID INT NOT NULL PRIMARY KEY,
        CardWHID INT NULL,
        BrandID INT NOT NULL,
        RegionID INT NULL,
        ProvinceID VARCHAR(20) NULL,
        DistrictID VARCHAR(20) NULL,
        Number VARCHAR(20) NOT NULL,
        OutletName NVARCHAR(250) NULL,
        Description NVARCHAR(500) NULL,
        Address NVARCHAR(500) NULL,
        Email VARCHAR(100) NULL,
        Tel NVARCHAR(20) NULL,
        Website NVARCHAR(100) NULL,
        Tags NVARCHAR(250) NULL,
        Nps DECIMAL(18,2) NULL,
        Latitude FLOAT NULL,
        Longitude FLOAT NULL,
        OpenTime VARCHAR(20) NULL,
        CloseTime VARCHAR(20) NULL,
        Parking BIT NULL,
        Picture VARCHAR(250) NULL,
        IsCDC BIT NULL,
        IsUsed BIT NOT NULL DEFAULT 1,
        CreatedBy VARCHAR(20) NULL,
        CreatedOn DATETIME DEFAULT GETDATE(),
        ModifiedBy VARCHAR(20) NULL,
        ModifiedOn DATETIME NULL,
        AccCode VARCHAR(20) NULL,
        Merchant VARCHAR(20) NULL,
        MerchantG VARCHAR(20) NULL,
        Merchant2G VARCHAR(20) NULL,
        Merchant3G VARCHAR(20) NULL,
        MerchantID VARCHAR(20) NULL,
        LicenseQuantity INT NULL,
        FloorID INT NULL,
        CategoryID INT NULL,
        FloorPosition VARCHAR(20) NULL,
        ImagesList NVARCHAR(250) NULL,
        FloorImage NVARCHAR(250) NULL,
        Image NVARCHAR(250) NULL,
        BranchID INT NULL,
        RedeemCode VARCHAR(20) NULL,
        PwdCode VARCHAR(20) NULL,
        IsAccPoint BIT NULL,
        IsShowMobileApp BIT NULL,
        IsActive BIT NOT NULL DEFAULT 1,

        CONSTRAINT FK_G_Outlet_Brand FOREIGN KEY (BrandID) REFERENCES G_Brand(ID)
    );

    CREATE NONCLUSTERED INDEX IX_G_Outlet_Number ON G_Outlet(Number);
    CREATE NONCLUSTERED INDEX IX_G_Outlet_Active_Used ON G_Outlet(IsActive, IsUsed);
    PRINT N'2. Đã tạo bảng G_Outlet thành công!';
END
ELSE
BEGIN
    PRINT N'2. Bảng G_Outlet đã tồn tại.';
END
GO

-- =======================================================================
-- 3. NẠP DỮ LIỆU DANH MỤC MASTER (81 GIAN HÀNG & 70 BRAND HOẠT ĐỘNG)
-- =======================================================================
PRINT N'3. Đang nạp danh mục Master Brand & Outlet...';
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1032) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1032, 1, 'GG', N'_GoldenGate_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1033) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1033, 1, 'SSC', N'_Sense City_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1034) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1034, 1, 'AEON', N'_AEON_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1037) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1037, 1, 'DIENMAYCHOLON', N'Điện Máy Chợ Lớn');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1039) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1039, 1, 'JOLLIBEE', N'JOLLIBEE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1040) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1040, 1, 'KOHNAN', N'KOHNAN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1041) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1041, 1, 'TEXAS', N'TEXAS CHICKEN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1044) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1044, 1, 'CALIFONIA', N'CALIFONIA & FITNESS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1051) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1051, 1, 'ILA', N'ILA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1060) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1060, 1, 'PHUCLONG', N'PHUC LONG');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1064) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1064, 1, 'SUKIYA', N'SUKIYA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1072) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1072, 1, 'CHANGKANGKUNG', N'CHANG KANG KUNG');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1094) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1094, 1, 'KFC', N'KFC');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1103) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1103, 1, 'TINIWORLD', N'TINIWORLD');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1106) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1106, 1, 'CGV', N'CGV');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1108) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1108, 1, 'JP BOWLING', N'_JP BOWLING GAME CENTER_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1115) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1115, 1, 'ADIDAS', N'ADIDAS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1116) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1116, 1, 'ALDO', N'ALDO');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1117) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1117, 1, 'ANPHUOC', N'AN PHƯỚC');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1119) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1119, 1, 'CANIFA', N'CANIFA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1124) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1124, 1, 'GUARDIAN', N'GUARDIAN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1125) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1125, 1, 'HIGHLANDS', N'HIGHLANDS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1127) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1127, 1, 'LEVIS', N'LEVIS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1130) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1130, 1, 'MATVIET', N'MẮT VIỆT');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1131) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1131, 1, 'NIKE', N'NIKE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1133) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1133, 1, 'PNJ', N'PNJ GOLD & SILVER');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1136) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1136, 1, 'SAMSONITE', N'SAMSONITE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1137) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1137, 1, 'SJC', N'SJC');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1139) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1139, 1, 'SKETCHER', N'SKETCHER');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1141) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1141, 1, 'STARBUCKS', N'STARBUCKS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1145) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1145, 1, 'THEGIOIKIMCUONG', N'THẾ GIỚI KIM CƯƠNG');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1153) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1153, 1, 'BELLUNI', N'BELLUNI');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1155) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1155, 1, 'BREADTALK', N'BREADTALK');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1156) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1156, 1, 'COOPXTRA', N'COOP.XTRA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1157) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1157, 1, 'COUPLE TX', N'COUPLE TX');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1158) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1158, 1, 'DAIRYQUEEN', N'DAIRY QUEEN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1170) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1170, 1, 'MINISO', N'MINISO');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1172) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1172, 1, 'NINOMAXX', N'NINOMAXX');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1178) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1178, 1, 'RABITY', N'RABITY');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1180) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1180, 1, 'SLINE', N'SLINE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1181) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1181, 1, 'SONKIMMODE', N'SƠN KIM MODE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1182) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1182, 1, 'SUNDAY', N'SUNDAY');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1188) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1188, 1, 'AKAHOUSE', N'AKA HOUSE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1189) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1189, 1, 'ASIANA', N'_ASIANA FOOD TOWN_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1191) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1191, 1, 'FAHASA', N'FAHASA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 1194) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (1194, 1, 'PIZZACOMPANY', N'PIZZA COMPANY');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2168) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2168, 1, 'REDSUN', N'_Redsun ITI Corporation_');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2174) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2174, 1, 'MYKINGDOM', N'MY KINGDOM');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2194) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2194, 1, 'SPICYBOX', N'SPICY BOX');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2195) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2195, 1, 'Passio', N'Passio');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2197) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2197, 1, 'McDonald', N'McDonald');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2201) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2201, 1, 'BAA Baby', N'BAA Baby');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2202) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2202, 1, 'CHEERS', N'CHEERS');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2203) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2203, 1, 'VIETTIEN', N'Việt Tiến');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2211) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2211, 1, 'GRILLANDCHER', N'GRILL AND CHEER');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2225) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2225, 1, 'MEGANEPRINCE', N'MEGANE PRINCE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2234) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2234, 1, 'WRAP&ROLL', N'WRAP & ROLL');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2238) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2238, 1, 'GALBI HOUSE', N'GALBI HOUSE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2244) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2244, 1, 'DO0KKI ', N'DO0KKI VIETNAM');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2265) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2265, 1, 'HAIDILAO', N'HAIDILAO');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2277) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2277, 1, 'KYMDAN', N'KYMDAN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2283) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2283, 1, 'SUSHI WA', N'SUSHI WA');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2292) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2292, 1, 'Pizza 4P''s', N'Pizza 4P''s');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2293) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2293, 1, 'PIERRE CARDIN', N'PIERRE CARDIN');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2294) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2294, 1, 'BEAUTYBOX', N'BEAUTYBOX');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2353) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2353, 1, 'DATXANH', N'DATXANH');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 2360) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (2360, 1, 'CARE', N'CARE');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 3446) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (3446, 1, 'GGM', N'GIGAMALL');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 3479) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (3479, 1, 'TISSOT', N'TISSOT');
IF NOT EXISTS (SELECT 1 FROM G_Brand WHERE ID = 3480) INSERT INTO G_Brand (ID, CompanyID, Number, BrandName) VALUES (3480, 1, 'TAJ', N'TAJ');

IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3164) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3164, 1115, 'ADIDAS', N'ADIDAS', N'L1-12', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3, 1034, 'AEONBICYCLE', N'AEON BICYCLE', N'B1-05', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 2) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (2, 1034, 'AEONGL', N'AEON Glam Beautique', N'B1-04', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 2124) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (2124, 1034, 'AEONPET', N'AEON PET', N'L4-13', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3233) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3233, 1188, 'AKAHOUSE', N'AKAHOUSE', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3175) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3175, 1116, 'ALDO', N'ALDO', N'L1-11', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3180) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3180, 1117, 'ANPHUOC', N'AN PHƯỚC ', N'L1-26', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3266) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3266, 1189, 'ASIANA', N'ASIANA FOOD TOWN', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4242) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4242, 2201, 'BAA', N'BAA BABY', N'L2', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4310) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4310, 2294, 'BEAUTYBOX', N'BEAUTY BOX', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3206) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3206, 1153, 'BELLUNI', N'BELLUNI', N'L2-09-19', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3230) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3230, 1155, 'BREADTALK', N'BREADTALK', N'L2-02', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 21) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (21, 1044, 'CALIFORNIA', N'CALIFORNIA FITNESS & YOGA', N'L4-01', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3176) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3176, 1119, 'CANIFA', N'CANIFA', N'L2-16', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3253) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3253, 2360, 'CARE', N'CARE', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1072) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1072, 1106, 'CGV', N'CGV', N'L6-08', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1052) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1052, 1072, 'CHANGKANGKUNG', N'CHANG KANG KUNG', N'L5-06', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3260) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3260, 2202, 'CHEERS', N'CHEERS', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1118) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1118, 1156, 'COOPXTRA', N'CO.OPXTRA', N'L2-01, L3-01', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3196) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3196, 1157, 'COUPLETX', N'COUPLE TX', N'L2-08-5', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3263) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3263, 1158, 'DAIRYQUEEN', N'DAIRY QUEEN', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3252) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3252, 2353, 'DATXANH', N'ĐẤT XANH', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 15) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (15, 1037, 'DIENMAYCHOLON', N'ĐIỆN MÁY CHỢ LỚN', N'B1-06', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4255) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4255, 2244, 'DOOKKI', N'DOOKKI', N'B1', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3163) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3163, 1191, 'FAHASA', N'FAHASA', N'L3-05', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3148) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3148, 1032, 'FRICO', N'FRICO', N'L3-08', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4248) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4248, 2238, 'GALBIHOUSE', N'GALBI HOUSE', N'L4-09B L4-09C', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1055) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1055, 1032, 'GOGIHOUSE', N'GOGI HOUSE', N'L5-14', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3267) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3267, 2211, 'GRILLNCHEER', N'GRILL & CHEER', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3152) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3152, 1124, 'GUARDIAN', N'GUARDIAN', N'L1-19', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3215) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3215, 1033, 'GUMAC', N'GUMAC', N'L2-09-07', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4276) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4276, 2265, 'HDL', N'HAIDILAO', N'L5_07', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3226) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3226, 1125, 'HIGHLANDS', N'HIGHLANDS COFFEE', N'L1-22', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3198) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3198, 1033, 'IBASIC', N'IBASIC', N'L2-09-10', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 32) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (32, 1051, 'ILA', N'ILA VIỆT NAM', N'L4-07', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 16) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (16, 1039, 'JOLLIBEE', N'JOLLIBEE', N'B1-01B3', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1073) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1073, 1108, 'JP', N'JP GAME & BOWLING', N'L6', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1059) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1059, 1094, 'KFC', N'KFC', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1060) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1060, 1032, 'KICHIKICHI', N'KICHI KICHI', N'L5-15', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1061) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1061, 2168, 'KINGBBQ', N'KINGBBQ', N'L5-05', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 17) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (17, 1040, 'KOHNAN', N'KOHNAN', N'B1-02', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4286) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4286, 2277, 'KYMDAN', N'KYMDAN', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3179) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3179, 1127, 'LEVIS', N'LEVI''S', N'L1-25', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1063) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1063, 1032, 'MANWAH', N'MANWAH', N'L5-13', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3181) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3181, 1130, 'MATVIET', N'MẮT VIỆT', N'L1-28', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3259) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3259, 2197, 'MCDONALDS', N'MCDONALDS', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3172) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3172, 2225, 'MEGANEPRINCE', N'MEGANE PRINCE', N'L1-07', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3150) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3150, 1170, 'SPM', N'MINISO', N'L2-03', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3134) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3134, 2174, 'MYKINGDOM', N'MY KINGDOM', N'L4-12', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3165) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3165, 1131, 'NIKE', N'NIKE', N'L1-14', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3213) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3213, 1172, 'NINOMAXX', N'NINOMAXX', N'L2-09-05', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3237) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3237, 2195, 'PASSIO', N'PASSIO', N'L1', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1041) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1041, 1060, 'PHUCLONG', N'PHUC LONG', N'L4-08B', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4309) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4309, 2293, 'PIERRECARDIN', N'PIERRE CARDIN', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4308) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4308, 2292, 'PP4', N'Pizza 4P''s', N'L4', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3183) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3183, 1133, 'PNJGOLDSILVER', N'PNJ GOLD & SILVER', N'L1-30', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3182) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3182, 1133, 'PNJWATCH', N'PNJ WATCH', N'L1-29', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3274) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3274, 3446, 'GIGAMALL', N'QUẦY INFORMATION GIGAMALL', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3219) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3219, 1178, 'RABITY', N'RABITY', N'L2-18', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1075) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1075, 1108, 'RAINBOWFUN', N'RAINBOW FUN', N'L6-03-04', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3177) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3177, 1136, 'SAMSONITE', N'SAMSONITE', N'L1-18', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3127) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3127, 1033, 'SENSECITY', N'SENSE CITY', N'L1 L2 L3', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3187) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3187, 1137, 'SJC', N'SJC', N'L1-37', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3166) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3166, 1139, 'SKECHERS', N'SKECHERS', N'L1-17', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3202) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3202, 1180, 'SLINE', N'SLINE', N'L2-09-14', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3205) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3205, 1181, 'SONKIMMODE', N'SƠN KIM MODE', N'L2-09-18', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3238) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3238, 2194, 'SPICYBOX', N'SPICY BOX', N'L5', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3227) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3227, 1141, 'STARBUCKS', N'STARBUCKS', N'L1-23', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1045) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1045, 1064, 'SUKIYA', N'SUKIYA', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1066) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1066, 1032, 'SUMOBBQ', N'SUMO BBQ', N'L5-16-17', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3207) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3207, 1182, 'SUNDAYSHOES', N'SUNDAY', N'L4', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4299) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4299, 2283, 'SUSHIWA', N'SUSHI WA', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3222) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3222, 3480, 'TAJ', N'TAJ', N'L4-28', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 18) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (18, 1041, 'TEXASCHICKEN', N'TEXAS CHICKEN', N'L1-02', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3184) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3184, 1145, 'THEGIOIKIMCUONG', N'THẾ GIỚI KIM CƯƠNG ', N'L1-34', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3255) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3255, 1194, 'THEPIZZACOMPANY', N'THE PIZZA COMPANY', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 1068) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (1068, 1103, 'TINIWORLD', N'TINIWORLD', N'L5-01', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3190) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3190, 3479, 'TISSOT', N'TISSOT', N'L1-40', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 4257) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (4257, 2203, 'VietTien', N'Việt Tiến', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3251) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3251, 1032, 'VPGOLDENGATE', N'VP GOLDEN GATE', N'', 1, 1);
IF NOT EXISTS (SELECT 1 FROM G_Outlet WHERE ID = 3270) INSERT INTO G_Outlet (ID, BrandID, Number, OutletName, Address, IsActive, IsUsed) VALUES (3270, 2234, 'WRAPNROLL', N'WRAP & ROLL', N'L3', 1, 1);
PRINT N'   -> Nạp danh mục Master Brand & Outlet hoàn tất!';
GO

-- =======================================================================
-- 4. BẢNG OcrBills (Quản lý hóa đơn & Kết quả duyệt)
-- =======================================================================
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

        -- Dữ liệu Admin điều chỉnh (Admin Override - Mặc định NULL nếu không sửa)
        AdminBrand NVARCHAR(100) NULL,
        AdminOutletNumber NVARCHAR(50) NULL,
        AdminOutletName NVARCHAR(250) NULL,
        AdminBillNumber NVARCHAR(100) NULL,
        AdminDateTime DATETIME NULL,
        AdminTotal BIGINT NULL,
        AdminNote NVARCHAR(500) NULL,
        
        -- Dữ liệu duyệt chính thức (COALESCE: Có sửa lấy Admin, không sửa lấy AI)
        FinalOutletNumber NVARCHAR(50) NULL,
        FinalOutletName NVARCHAR(255) NULL,
        FinalBillNumber NVARCHAR(100) NULL,
        FinalDateTime DATETIME NULL,
        FinalTotal BIGINT NULL,
        
        -- Thông tin phiên duyệt & Kiểm soát
        IsManualEdited BIT NOT NULL DEFAULT 0,
        ReviewedBy NVARCHAR(100) NULL,
        ReviewedAt DATETIME NULL,
        FileHash VARCHAR(64) NULL, -- SHA-256 mã hóa ảnh chống upload trùng
        
        CreatedAt DATETIME DEFAULT GETDATE(),
        UpdatedAt DATETIME DEFAULT GETDATE()
    );

    CREATE NONCLUSTERED INDEX IX_OcrBills_Status ON OcrBills(Status);
    CREATE NONCLUSTERED INDEX IX_OcrBills_FileHash ON OcrBills(FileHash);
    CREATE NONCLUSTERED INDEX IX_OcrBills_FinalOutlet ON OcrBills(FinalOutletName);
    CREATE NONCLUSTERED INDEX IX_OcrBills_FinalBillNo ON OcrBills(FinalBillNumber);
    PRINT N'4. Đã tạo bảng OcrBills thành công!';
END
ELSE
BEGIN
    -- Đảm bảo có cột FileHash nếu bảng đã tồn tại từ trước
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'OcrBills' AND COLUMN_NAME = 'FileHash')
    BEGIN
        ALTER TABLE OcrBills ADD FileHash VARCHAR(64) NULL;
        CREATE NONCLUSTERED INDEX IX_OcrBills_FileHash ON OcrBills(FileHash);
        PRINT N'4. Đã bổ sung cột FileHash vào bảng OcrBills.';
    END
    PRINT N'4. Bảng OcrBills đã tồn tại.';
END
GO

-- =======================================================================
-- 4.1 VIEW v_OcrBillsFinal (Chuẩn hóa COALESCE cho CRM Query)
-- =======================================================================
IF EXISTS (SELECT * FROM sys.views WHERE name = 'v_OcrBillsFinal')
    DROP VIEW v_OcrBillsFinal;
GO

CREATE VIEW v_OcrBillsFinal AS
SELECT 
    BillId, Filename, ImagePath, Status,
    -- 1. AI Evidence (Bất biến)
    OcrBrand, OcrOutletRaw, OcrOutletNumber, OcrOutletName, OcrMatchScore,
    OcrBillNumber, OcrDateTime, OcrTotal, OcrIsValid, OcrLatency,
    -- 2. Admin Override (NULL nếu không sửa)
    AdminBrand, AdminOutletNumber, AdminOutletName, AdminBillNumber, AdminDateTime, AdminTotal, AdminNote,
    -- 3. Final Computed (COALESCE: Ưu tiên Admin sửa, nếu không lấy AI)
    COALESCE(AdminOutletNumber, FinalOutletNumber, OcrOutletNumber) AS FinalOutletNumber,
    COALESCE(AdminOutletName, FinalOutletName, OcrOutletName) AS FinalOutletName,
    COALESCE(AdminBillNumber, FinalBillNumber, OcrBillNumber) AS FinalBillNumber,
    COALESCE(AdminDateTime, FinalDateTime, OcrDateTime) AS FinalDateTime,
    COALESCE(AdminTotal, FinalTotal, OcrTotal) AS FinalTotal,
    -- Cờ đánh dấu có can thiệp thủ công
    CASE WHEN (AdminTotal IS NOT NULL OR AdminOutletName IS NOT NULL OR AdminBillNumber IS NOT NULL OR AdminDateTime IS NOT NULL OR IsManualEdited = 1) 
         THEN 1 ELSE 0 END AS IsManualEdited,
    ReviewedBy, ReviewedAt, RejectReason, FileHash, CreatedAt, UpdatedAt
FROM OcrBills;
GO

-- =======================================================================
-- 5. BẢNG OcrBillAuditLogs (Vết kiểm toán chi tiết cho Auditor - US 3)
-- =======================================================================
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
    CREATE NONCLUSTERED INDEX IX_OcrBillAuditLogs_CreatedAt ON OcrBillAuditLogs(CreatedAt);
    PRINT N'5. Đã tạo bảng OcrBillAuditLogs thành công!';
END
ELSE
BEGIN
    PRINT N'5. Bảng OcrBillAuditLogs đã tồn tại.';
END
GO

-- =======================================================================
-- 6. KIỂM TRA TỔNG QUAN DỮ LIỆU SAU KHI SETUP
-- =======================================================================
PRINT N'=======================================================================';
PRINT N'TỔNG KẾT BẢNG & SỐ LƯỢNG BẢN GHI ĐÃ KHỞI TẠO:';
SELECT 'G_Brand' AS TableName, COUNT(*) AS RecordCount FROM G_Brand
UNION ALL
SELECT 'G_Outlet' AS TableName, COUNT(*) AS RecordCount FROM G_Outlet
UNION ALL
SELECT 'OcrBills' AS TableName, COUNT(*) AS RecordCount FROM OcrBills
UNION ALL
SELECT 'OcrBillAuditLogs' AS TableName, COUNT(*) AS RecordCount FROM OcrBillAuditLogs;
PRINT N'=======================================================================';
PRINT N'CÀI ĐẶT CSDL DEV HOÀN TẤT THÀNH CÔNG!';
GO
