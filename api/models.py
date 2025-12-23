from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

# 1. Bảng Danh Mục (Ví dụ: Túi da, Balo...)
class DanhMuc(models.Model):
    ten_danh_muc = models.CharField(max_length=100)
    slug = models.SlugField(unique=True) # Đường dẫn thân thiện SEO

    def __str__(self):
        return self.ten_danh_muc

# 2. Bảng Túi Xách (Sản phẩm)
class TuiXach(models.Model):
    danh_muc = models.ForeignKey(DanhMuc, related_name='ds_tui_xach', on_delete=models.CASCADE)
    ten_tui = models.CharField(max_length=250)
    mo_ta = models.TextField(blank=True)
    gia_tien = models.DecimalField(max_digits=12, decimal_places=0) # Giá tiền thường không lẻ ở VN
    so_luong_ton = models.IntegerField(default=0)
    hinh_anh = models.CharField(max_length=800)
    
    ngay_tao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.ten_tui

class KhachHang(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile',null=True, blank=True)
    ho_ten = models.CharField(max_length=255)
    so_dien_thoai = models.CharField(max_length=15)
    email = models.EmailField(max_length=255, null=True, blank=True)
    dia_chi = models.TextField(blank=True, null=True)
    tong_chi_tieu = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    ngay_tham_gia = models.DateTimeField(auto_now_add=True)

    def get_muc_giam_gia(self):
        """ Trả về % giảm giá (0, 10, hoặc 15) """
        if self.tong_chi_tieu >= 100000000: # >= 100 triệu
            return 15
        elif self.tong_chi_tieu >= 10000000: # >= 10 triệu
            return 10
        return 0

    def get_hang_thanh_vien(self):
        """ Trả về tên hạng để hiển thị """
        if self.tong_chi_tieu >= 100000000:
            return "VIP Kim Cương (Giảm 15%)"
        elif self.tong_chi_tieu >= 10000000:
            return "VIP Vàng (Giảm 10%)"
        return "Thành viên Mới"

    def __str__(self):
        return f"{self.ho_ten} - {self.get_hang_thanh_vien()}"


class HoaDon(models.Model):
    # 1. PHÂN LOẠI ĐƠN HÀNG
    LOAI_HOA_DON_CHOICES = [
        ('ONLINE', 'Web Online'),   # Khách tự đặt
        ('OFFLINE', 'Tại quầy'),    # Nhân viên tạo
    ]
    # 2. QUY TRÌNH TRẠNG THÁI (State Machine)
    TRANG_THAI_CHOICES = [
        ('CHO_XAC_NHAN', 'Chờ xác nhận'),       # Đơn mới (Online)
        ('DA_XAC_NHAN', 'Đã xác nhận/Đóng gói'),# Admin đã xem và đang gói
        ('DANG_GIAO', 'Đang vận chuyển'),       # Shipper đang đi giao
        ('HOAN_THANH', 'Đã hoàn thành'),        # Khách đã nhận & Trả tiền
        ('DA_HUY', 'Đã hủy'),                   # Hết hàng hoặc Khách hủy
    ]
    # 3. HÌNH THỨC THANH TOÁN (Demo)
    PHUONG_THUC_TT_CHOICES = [
        ('COD', 'Thanh toán khi nhận hàng'),
        ('CK', 'Chuyển khoản ngân hàng'),
        ('TIEN_MAT', 'Tiền mặt (Tại quầy)'),
    ]
    ma_hoa_don = models.CharField(max_length=20, unique=True)
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.SET_NULL, null=True, blank=True)
    nhan_vien = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # --- PHÂN LOẠI & TRẠNG THÁI MỚI ---
    loai_hoa_don = models.CharField(max_length=10, choices=LOAI_HOA_DON_CHOICES, default='ONLINE')
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_CHOICES, default='CHO_XAC_NHAN')
    phuong_thuc_tt = models.CharField(max_length=20, choices=PHUONG_THUC_TT_CHOICES, default='COD')
    # --- SNAPSHOT THÔNG TIN GIAO HÀNG (Quan trọng cho đơn Online) ---
    # Lý do: Để giữ lại địa chỉ lúc đặt, kể cả khi khách chuyển nhà đổi profile.
    ho_ten_nguoi_nhan = models.CharField(max_length=200, null=True, blank=True)
    sdt_nguoi_nhan = models.CharField(max_length=15, null=True, blank=True)
    dia_chi_giao_hang = models.TextField(null=True, blank=True)
    # --- TIỀN NONG ---
    tong_tien_hang = models.DecimalField(max_digits=15, decimal_places=0)
    giam_gia = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    thanh_tien = models.DecimalField(max_digits=15, decimal_places=0) 
    
    ghi_chu = models.TextField(null=True, blank=True)
    ngay_tao = models.DateTimeField(auto_now_add=True, db_index=True)
    ngay_cap_nhat = models.DateTimeField(auto_now=True) # Để biết đơn chuyển trạng thái lúc nào

    def __str__(self):
        return f"{self.ma_hoa_don} - {self.get_trang_thai_display()}"

class ChiTietHoaDon(models.Model):
    hoa_don = models.ForeignKey(HoaDon, related_name='chi_tiet', on_delete=models.CASCADE)
    tui_xach = models.ForeignKey(TuiXach, on_delete=models.PROTECT)
    so_luong = models.IntegerField(default=1)
    don_gia_luc_ban = models.DecimalField(max_digits=12, decimal_places=0) 
    
    def thanh_tien_item(self):
        return self.so_luong * self.don_gia_luc_ban

class BanThietKe(models.Model):
    # Thêm trạng thái BO_SUU_TAP cho nhu cầu "Lưu riêng"
    TRANG_THAI_CHOICES = [
        ('BO_SUU_TAP', 'Lưu bộ sưu tập riêng'),   # Mặc định khi Nhân viên/Khách lưu chơi
        ('CHO_XET_DUYET', 'Gửi yêu cầu gia công'), # Khách gửi đi chờ duyệt
        ('XAC_NHAN_GIA_CONG', 'Xác nhận gia công'), 
        ('TU_CHOI', 'Từ chối'),
    ]

    # THAY ĐỔI LỚN: Liên kết với User thay vì KhachHang
    # Để cả Nhân viên (Staff) và Khách (Customer) đều có thể đứng tên bản vẽ này
    nguoi_so_huu = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='thiet_ke_so_huu',
        verbose_name="Người tạo"
    )

    drive_url = models.URLField(max_length=500, verbose_name="Link ảnh thiết kế")
    
    # Ghi chú này dùng chung:
    # - Nếu là Khách: Ghi yêu cầu gia công.
    # - Nếu là Nhân viên: Ghi chú về mẫu túi (VD: "Mẫu demo cho khách VIP").
    ghi_chu = models.TextField(null=True, blank=True, verbose_name="Ghi chú/Yêu cầu")
    phan_hoi_admin = models.TextField(null=True, blank=True, verbose_name="Phản hồi Admin")
    trang_thai = models.CharField(
        max_length=20, 
        choices=TRANG_THAI_CHOICES, 
        default='BO_SUU_TAP' 
    )
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Design {self.id} | {self.nguoi_so_huu.username} | {self.get_trang_thai_display()}"