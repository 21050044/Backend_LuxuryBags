from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Sum
from django.db import transaction

# ========================================================
# 1. CORE SERIALIZERS (Dùng chung cho cả hệ thống)
# ========================================================
class MyTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # 1. Gọi hàm gốc để lấy access/refresh token chuẩn
        data = super().validate(attrs)

        # 2. Lấy thông tin User hiện tại
        user = self.user

        # 3. XÁC ĐỊNH QUYỀN (ROLE)
        # Logic: Superuser là Admin, Staff là Nhân viên, còn lại là Khách
        role = 'CUSTOMER' # Mặc định
        if user.is_superuser:
            role = 'ADMIN'
        elif user.is_staff:
            role = 'STAFF'

        # 4. Thêm các thông tin bổ sung vào response JSON
        data['id'] = user.id
        data['username'] = user.username
        data['role'] = role  # <--- QUAN TRỌNG: Trả về quyền ở đây
        
        # 5. Lấy họ tên hiển thị (Tuỳ chọn: Nếu là khách thì lấy tên trong bảng KhachHang)
        full_name = user.username # Mặc định lấy username
        if role == 'CUSTOMER':
            try:
                khach = KhachHang.objects.get(user=user)
                full_name = khach.ho_ten
                data['avatar'] = "" # Nếu có avatar thì thêm vào đây
            except KhachHang.DoesNotExist:
                pass
        elif role in ['ADMIN', 'STAFF']:
            # Nếu admin/staff có đặt first_name/last_name
            if user.first_name or user.last_name:
                full_name = f"{user.last_name} {user.first_name}".strip()

        data['full_name'] = full_name
        return data
    
class DanhMucSerializer(serializers.ModelSerializer):
    class Meta:
        model = DanhMuc
        fields = '__all__'

class TuiXachSerializer(serializers.ModelSerializer):
    """ Dùng cho Admin quản lý CRUD Túi xách """
    hinh_anh = serializers.CharField(required=False, allow_blank=True) # Xử lý ảnh base64/url
    class Meta:
        model = TuiXach
        fields = '__all__'
        read_only_fields = ['ngay_tao']

class TuiXachPublicSerializer(serializers.ModelSerializer):
    """ Dùng để hiển thị ra Web (Có nested Danh mục) """
    danh_muc = DanhMucSerializer(read_only=True)
    
    class Meta:
        model = TuiXach
        fields = ['id', 'ten_tui', 'gia_tien', 'so_luong_ton', 
                  'mo_ta', 'hinh_anh', 'danh_muc']

class BanThietKeSerializer(serializers.ModelSerializer):
    """ [MỚI] Dùng cho tính năng AI Design """
    trang_thai_text = serializers.CharField(source='get_trang_thai_display', read_only=True)
    
    class Meta:
        model = BanThietKe
        fields = ['id', 'drive_url', 'ghi_chu', 'phan_hoi_admin', 
                  'trang_thai', 'trang_thai_text', 'created_at']
        read_only_fields = ['phan_hoi_admin', 'created_at']


# 2. AUTH SERIALIZERS (Đăng nhập, Đăng ký, Profile)
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """ Custom Login để trả về thêm info user """
    def validate(self, attrs):
        data = super().validate(attrs)
        # Nhét thêm thông tin vào response login
        data['user_id'] = self.user.id
        data['username'] = self.user.username
        data['role'] = 'ADMIN' if self.user.is_staff else 'CUSTOMER' # Phân quyền đơn giản frontend
        return data

class RegisterSerializer(serializers.Serializer):
    """ Xử lý đăng ký tạo cùng lúc User và KhachHang """
    ho_ten = serializers.CharField()
    email = serializers.EmailField()
    so_dien_thoai = serializers.CharField()
    password = serializers.CharField(write_only=True)
    dia_chi = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        with transaction.atomic():
            # Tạo User Django
            user = User.objects.create_user(
                username=validated_data['email'], 
                email=validated_data['email'],
                password=validated_data['password']
            )
            # Tạo Profile Khách
            khach = KhachHang.objects.create(
                user=user,
                ho_ten=validated_data['ho_ten'],
                so_dien_thoai=validated_data['so_dien_thoai'],
                email=validated_data['email'],
                dia_chi=validated_data.get('dia_chi', '')
            )
        return khach

class KhachHangSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    hang_thanh_vien = serializers.CharField(source='get_hang_thanh_vien', read_only=True)
    muc_giam_gia = serializers.IntegerField(source='get_muc_giam_gia', read_only=True)
    
    class Meta:
        model = KhachHang
        fields = ['id', 'username', 'ho_ten', 'so_dien_thoai', 'email', 
                  'dia_chi', 'tong_chi_tieu', 'ngay_tham_gia', 
                  'hang_thanh_vien', 'muc_giam_gia'] # Thêm 2 trường này
        read_only_fields = ['id', 'username', 'tong_chi_tieu', 'ngay_tham_gia']


# 3. ORDER MANAGEMENT (Dành cho Admin/Staff)
class ChiTietHoaDonSerializer(serializers.ModelSerializer):
    # Lấy tên và ảnh túi xách từ quan hệ tui_xach
    ten_san_pham = serializers.ReadOnlyField(source='tui_xach.ten_tui')
    anh_dai_dien = serializers.SerializerMethodField()
    thanh_tien = serializers.ReadOnlyField(source='thanh_tien_item')

    class Meta:
        model = ChiTietHoaDon
        fields = ['id', 'tui_xach', 'ten_san_pham', 'anh_dai_dien', 
                  'so_luong', 'don_gia_luc_ban', 'thanh_tien']

    def get_anh_dai_dien(self, obj):
        request = self.context.get('request')
        # Lấy dữ liệu từ trường hinh_anh
        img_field = obj.tui_xach.hinh_anh

        if not img_field:
            return None
        if hasattr(img_field, 'url'):
            url_path = img_field.url
            return request.build_absolute_uri(url_path) if request else url_path
        url_str = str(img_field)
        
        # Nếu là link online (http://...) hoặc link drive -> Trả về luôn
        if url_str.startswith('http'):
            return url_str
        if request:
            if not url_str.startswith('/'):
                url_str = f"/media/{url_str}" 
            return request.build_absolute_uri(url_str)
            
        return url_str

class QuanLyHoaDonSerializer(serializers.ModelSerializer):
    trang_thai_text = serializers.CharField(source='get_trang_thai_display', read_only=True)
    loai_hoa_don_text = serializers.CharField(source='get_loai_hoa_don_display', read_only=True)
    ten_khach_hang = serializers.ReadOnlyField(source='khach_hang.ho_ten')
    sdt_khach_hang = serializers.ReadOnlyField(source='khach_hang.so_dien_thoai')
    ten_nhan_vien = serializers.ReadOnlyField(source='nhan_vien.username')
    chi_tiet = ChiTietHoaDonSerializer(many=True, read_only=True)

    class Meta:
        model = HoaDon
        fields = [
            'id', 'ma_hoa_don', 
            'loai_hoa_don', 'loai_hoa_don_text',
            'trang_thai', 'trang_thai_text',
            'phuong_thuc_tt',
            'khach_hang', 'ten_khach_hang', 'sdt_khach_hang',
            'nhan_vien', 'ten_nhan_vien',
            'ho_ten_nguoi_nhan', 'sdt_nguoi_nhan', 'dia_chi_giao_hang',
            'tong_tien_hang', 
            'giam_gia',     
            'thanh_tien',    
            'ghi_chu', 'ngay_tao', 
            'chi_tiet'
        ]
        read_only_fields = ['ma_hoa_don', 'ngay_tao', 'thanh_tien', 'giam_gia']

class OrderItemInputSerializer(serializers.Serializer):
    id = serializers.IntegerField() 
    quantity = serializers.IntegerField(min_value=1)

class AdminCreateOrderSerializer(serializers.Serializer):
    loai_hoa_don = serializers.ChoiceField(choices=['ONLINE', 'OFFLINE'], default='OFFLINE')
    khach_hang_id = serializers.IntegerField(required=False, allow_null=True)
    ho_ten_nguoi_nhan = serializers.CharField(required=False, allow_blank=True)
    sdt_nguoi_nhan = serializers.CharField(required=False, allow_blank=True)
    dia_chi_giao_hang = serializers.CharField(required=False, allow_blank=True)
    
    ghi_chu = serializers.CharField(required=False, allow_blank=True)
    cart_items = OrderItemInputSerializer(many=True)


# 4. CLIENT FEATURES (Dành cho Khách hàng Online)
class HoaDonSerializer(serializers.ModelSerializer):
    chi_tiet = ChiTietHoaDonSerializer(many=True, read_only=True)
    class Meta:
        model = HoaDon
        fields = [
            'id', 'ma_hoa_don', 'ngay_tao', 'trang_thai',
            'ho_ten_nguoi_nhan', 'sdt_nguoi_nhan', 'dia_chi_giao_hang',
            'tong_tien_hang', 'giam_gia', 'thanh_tien',
            'phuong_thuc_tt', 'ghi_chu', 
            'chi_tiet'
        ]


# Lưu dữ liệu lên drive
class BanThietKeSerializer(serializers.ModelSerializer):
    nguoi_tao = serializers.CharField(source='nguoi_so_huu.username', read_only=True)

    class Meta:
        model = BanThietKe
        fields = ['id', 'drive_url', 'ghi_chu', 'trang_thai', 'created_at', 'nguoi_tao']
        read_only_fields = ['id', 'drive_url', 'trang_thai', 'created_at', 'nguoi_tao']