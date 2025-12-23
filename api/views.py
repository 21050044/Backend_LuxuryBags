# --- Standard Library Imports ---
from datetime import datetime, timedelta
from decimal import Decimal
# --- Django Core Imports ---
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count, Max, F, Q
from django.db.models.functions import TruncDate, TruncMonth, Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
# --- Third Party Imports (DRF, JWT, Filters) ---
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
# --- Local Application Imports ---
from .drive_service import upload_file_to_drive, delete_file_from_drive
from .models import *
from .permissions import *
from .serializers import *


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenSerializer

class LogoutView(APIView):
    # Người dùng phải đang đăng nhập mới logout được
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Lấy refresh_token từ body gửi lên
            refresh_token = request.data["refresh"]
            
            # Tạo đối tượng token và đưa vào blacklist
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "Đăng xuất thành công!"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Token không hợp lệ hoặc thiếu refresh token."}, status=status.HTTP_400_BAD_REQUEST)

class DashboardSummaryView(APIView):
    permission_classes = [IsOwnerUser]

    def get(self, request):
        today = timezone.now().date()
        current_month = timezone.now().month
        current_year = timezone.now().year

        # ============================================================
        # PHẦN 1: OVERVIEW HÔM NAY (REALTIME)
        # ============================================================
        doanh_thu_hom_nay = HoaDon.objects.filter(
            ngay_tao__date=today, 
            trang_thai='HOAN_THANH'
        ).aggregate(total=Sum('thanh_tien'))['total'] or 0

        don_cho_duyet = HoaDon.objects.filter(
            trang_thai='CHO_XAC_NHAN',
            loai_hoa_don='ONLINE'
        ).count()
        
        don_hom_nay = HoaDon.objects.filter(
            ngay_tao__date=today
        ).count()
        # ============================================================
        # PHẦN 2: BIỂU ĐỒ TĂNG TRƯỞNG (7 NGÀY GẦN NHẤT) 
        # ============================================================
        last_7_days_data = []
        labels = []
        data_values = []
        
        for i in range(6, -1, -1): # Từ 6 ngày trước đến hôm nay
            target_date = today - timedelta(days=i)
            labels.append(target_date.strftime("%d/%m")) # Format ngày: 25/12

            # Query doanh thu ngày đó
            daily_revenue = HoaDon.objects.filter(
                ngay_tao__date=target_date,
                trang_thai='HOAN_THANH'
            ).aggregate(total=Sum('thanh_tien'))['total'] or 0
            
            data_values.append(daily_revenue)
        # Tính toán độ tăng trưởng (Growth Rate) so với hôm qua
        # Ví dụ: Hôm nay 1tr, hôm qua 500k -> Tăng trưởng 100%
        today_rev = data_values[-1]
        yesterday_rev = data_values[-2] 
        
        growth_percent = 0
        if yesterday_rev > 0:
            growth_percent = ((today_rev - yesterday_rev) / yesterday_rev) * 100
        elif today_rev > 0:
            growth_percent = 100 # Hôm qua 0, nay có tiền là tăng 100%
        
        chart_data = {
            "labels": labels, # Trục hoành: ['20/12', '21/12', ...]
            "data": data_values, # Trục tung: [1000000, 0, 500000, ...]
            "growth_rate": round(growth_percent, 1) # +15.5% hoặc -10.2%
        }
        # ============================================================
        # PHẦN 3: PHÂN TÍCH NGUỒN THU (THÁNG NÀY)
        # ============================================================
        source_revenue = HoaDon.objects.filter(
            ngay_tao__month=current_month,
            ngay_tao__year=current_year,
            trang_thai='HOAN_THANH'
        ).values('loai_hoa_don').annotate(
            total_revenue=Sum('thanh_tien'),
            total_orders=Count('id')
        )
        revenue_split = {
            "ONLINE": {"revenue": 0, "orders": 0},
            "OFFLINE": {"revenue": 0, "orders": 0}
        }
        for item in source_revenue:
            revenue_split[item['loai_hoa_don']] = {
                "revenue": item['total_revenue'],
                "orders": item['total_orders']
            }
        # ============================================================
        # PHẦN 4: TOP SẢN PHẨM (BÁN CHẠY & BÁN Ế)
        # ============================================================
        # Top 5 Bán chạy
        top_selling = TuiXach.objects.filter(
            chitiethoadon__hoa_don__trang_thai='HOAN_THANH'
        ).annotate(
            total_sold=Sum('chitiethoadon__so_luong')
        ).order_by('-total_sold')[:5]

        best_sellers_data = [
            {
                "id": t.id,
                "ten_tui": t.ten_tui,
                "da_ban": t.total_sold,
                "ton_kho": t.so_luong_ton,
                # SỬA LẠI DÒNG NÀY: Dùng trực tiếp t.hinh_anh
                "anh_dai_dien": t.hinh_anh if t.hinh_anh else "" 
            }
            for t in top_selling
        ]

        # Top 5 Bán ế (Bán ít + Tồn nhiều)
        slow_selling = TuiXach.objects.annotate(
            total_sold=Coalesce(
                Sum('chitiethoadon__so_luong', filter=Q(chitiethoadon__hoa_don__trang_thai='HOAN_THANH')), 
                0
            )
        ).order_by('total_sold', '-so_luong_ton')[:5]

        slow_sellers_data = [
            {
                "id": t.id,
                "ten_tui": t.ten_tui,
                "da_ban": t.total_sold,
                "ton_kho": t.so_luong_ton,
                # SỬA LẠI DÒNG NÀY: Dùng trực tiếp t.hinh_anh
                "anh_dai_dien": t.hinh_anh if t.hinh_anh else ""
            }
            for t in slow_selling
        ]

        # ============================================================
        # TRẢ VỀ RESPONSE CUỐI CÙNG
        # ============================================================
        return Response({
            "overview_today": {
                "doanh_thu": doanh_thu_hom_nay,
                "don_moi_online": don_cho_duyet,
                "tong_don_hang": don_hom_nay
            },
            "growth_chart": chart_data, # Dữ liệu mới cho biểu đồ
            "revenue_analysis": revenue_split,
            "top_products": {
                "best_sellers": best_sellers_data,
                "slow_sellers": slow_sellers_data
            }
        })

class DanhMucViewSet(viewsets.ModelViewSet):
    queryset = DanhMuc.objects.all()
    serializer_class = DanhMucSerializer
    permission_classes = [AllowAny]

class TuiXachReadSerializer(TuiXachSerializer):
    class Meta(TuiXachSerializer.Meta):
        depth = 1 


class TuiXachViewSet(viewsets.ModelViewSet):
    queryset = TuiXach.objects.all().order_by('-id')
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return TuiXachReadSerializer
        return TuiXachSerializer
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data.copy()
        if 'hinh_anh' in request.FILES:
            image_file = request.FILES['hinh_anh']
            try:
                # Upload lên Drive
                new_link = upload_file_to_drive(image_file)
                
                if new_link:
                    data['hinh_anh'] = new_link
                else:
                    return Response(
                        {"error": "Lỗi upload ảnh: Không nhận được link từ hệ thống"}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            except Exception as e:
                return Response(
                    {"error": f"Lỗi ngoại lệ khi upload: {str(e)}"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            if 'hinh_anh' in data and not data['hinh_anh']:
                 del data['hinh_anh']

        serializer = self.get_serializer(instance, data=data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)
    def destroy(self, request, *args, **kwargs):
        tui_xach = self.get_object()
        is_used = tui_xach.chitiethoadon_set.exists()
        
        if is_used:
            return Response(
                {"error": f"Không thể xóa '{tui_xach.ten_tui}' vì đã có trong lịch sử đơn hàng. Hãy ẩn nó đi thay vì xóa."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        return super().destroy(request, *args, **kwargs)
    
class CreateTuiXachView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    def post(self, request):
        # 1. Kiểm tra xem người dùng có gửi file ảnh lên không
        if 'hinh_anh' not in request.FILES:
            return Response(
                {"error": "Bắt buộc phải có hình ảnh sản phẩm."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        data = request.data.copy()
        data['danh_muc'] = 1 
        # 2. Bắt đầu xử lý upload
        image_file = request.FILES['hinh_anh']
        
        try:
            # Gọi hàm upload
            drive_link = upload_file_to_drive(image_file)

            # --- KIỂM TRA CHẶT CHẼ KẾT QUẢ TRẢ VỀ ---
            # Nếu hàm trả về None, Rỗng, hoặc False -> Báo lỗi ngay
            if not drive_link:
                return Response(
                    {"error": "Lỗi hệ thống: Upload ảnh không thành công (Không nhận được link)."}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            # Nếu có link, gán vào data
            data['hinh_anh'] = drive_link

        except Exception as e:
            # Bắt lỗi crash trong quá trình upload (ví dụ sai token, mất mạng...)
            return Response(
                {"error": f"Lỗi ngoại lệ khi upload ảnh: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        # 3. Nếu upload thành công mới chạy xuống đây để lưu DB
        serializer = TuiXachSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        # Nếu dữ liệu khác bị sai (ví dụ thiếu tên, giá tiền...)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class KhachHangViewSet(viewsets.ModelViewSet):
    # Lấy tất cả khách hàng, sắp xếp người mới nhất lên đầu
    queryset = KhachHang.objects.all().order_by('-ngay_tham_gia')
    serializer_class = KhachHangSerializer
    permission_classes = [IsAuthenticated] # Bắt buộc đăng nhập
    # --- CẤU HÌNH TÌM KIẾM ---
    filter_backends = [filters.SearchFilter]
    # Cho phép tìm theo Tên hoặc Số điện thoại
    search_fields = ['ho_ten', 'so_dien_thoai']
    def destroy(self, request, *args, **kwargs):
        khach_hang = self.get_object()
        if khach_hang.hoadon_set.exists():
            return Response(
                {"error": f"Không thể xóa khách hàng '{khach_hang.ho_ten}' vì họ đã từng mua hàng."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)
    
# --- API 1: THỐNG KÊ 4 Ô VUÔNG ---
class ThongKeDonHangView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Tổng doanh thu (Lũy kế từ trước tới nay)
        tong_doanh_thu = HoaDon.objects.filter(trang_thai='HOAN_THANH').aggregate(Sum('thanh_tien'))['thanh_tien__sum'] or 0
        
        # 2. Tổng số đơn hàng
        tong_don_hang = HoaDon.objects.count()
        
        # --- CÁC CHỈ SỐ THEO THỜI GIAN ---
        now = timezone.now()

        # 3. Doanh thu HÔM NAY
        doanh_thu_hom_nay = HoaDon.objects.filter(
            ngay_tao__date=now.date(), 
            trang_thai='HOAN_THANH'
        ).aggregate(Sum('thanh_tien'))['thanh_tien__sum'] or 0
        
        # 4. Doanh thu THÁNG NÀY (Thay cho Khách hàng)
        doanh_thu_thang_nay = HoaDon.objects.filter(
            ngay_tao__month=now.month,
            ngay_tao__year=now.year,
            trang_thai='HOAN_THANH'
        ).aggregate(Sum('thanh_tien'))['thanh_tien__sum'] or 0

        return Response({
            "tong_doanh_thu": tong_doanh_thu,
            "doanh_thu_thang_nay": doanh_thu_thang_nay,
            "doanh_thu_hom_nay": doanh_thu_hom_nay,
            "tong_don_hang": tong_don_hang,
        })

# =========================================================
# 1. NHÓM PUBLIC (SẢN PHẨM & DANH MỤC) - AI CŨNG XEM ĐƯỢC
# =========================================================

class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ GET /api/categories/ """
    queryset = DanhMuc.objects.all()
    serializer_class = DanhMucSerializer
    permission_classes = [AllowAny]
    pagination_class = None

class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """ GET /api/products/ """
    # Chỉ lấy sản phẩm còn hàng
    queryset = TuiXach.objects.filter(so_luong_ton__gt=0).order_by('-ngay_tao')
    serializer_class = TuiXachSerializer
    permission_classes = [AllowAny]
    
    # Cấu hình bộ lọc, tìm kiếm, sắp xếp
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'danh_muc': ['exact'],       # ?danh_muc=1
        'gia_tien': ['gte', 'lte'],  # ?gia_tien__gte=100000
    }
    search_fields = ['ten_tui', 'mo_ta']         # ?search=Chanel
    ordering_fields = ['gia_tien', 'ngay_tao']   # ?ordering=-gia_tien

# =========================================================
# 2. NHÓM AUTH (ĐĂNG KÝ, ĐĂNG NHẬP, PROFILE)
# =========================================================
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # RegisterSerializer cần xử lý việc tạo User VÀ tạo KhachHang
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.save()
                return Response({"success": True, "message": "Đăng ký thành công"}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

class CustomTokenObtainPairView(TokenObtainPairView):
    """ Login trả về Token + Thông tin user cơ bản """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                # Tìm khách hàng dựa trên user vừa đăng nhập
                user = self.user # user được authenticate bởi simplejwt
                khach = KhachHang.objects.get(user__username=request.data['username'])
                
                response.data['user_info'] = {
                    'id': khach.id,
                    'ho_ten': khach.ho_ten,
                    'email': khach.email,
                    'avatar': khach.user.username # Hoặc trường avatar nếu có
                }
            except Exception:
                pass
        return response

class KhachHangProfileView(generics.RetrieveUpdateAPIView):
    """ Xem và sửa thông tin cá nhân """
    serializer_class = KhachHangSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Lấy profile của chính user đang login
        return get_object_or_404(KhachHang, user=self.request.user)

    def update(self, request, *args, **kwargs):
        # Custom response để trả về đẹp hơn
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            "success": True, 
            "message": "Cập nhật thành công!",
            "data": serializer.data
        })

class QuanLyDonHangViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffOrOwner]
    serializer_class = QuanLyHoaDonSerializer 

    # Cấu hình tìm kiếm
    filter_backends = [filters.SearchFilter]
    search_fields = ['ma_hoa_don', 'khach_hang__ho_ten', 'sdt_nguoi_nhan']

    def get_queryset(self):
        user = self.request.user
        queryset = HoaDon.objects.all().order_by('-ngay_tao')
        if user.is_superuser:
            pass 

        elif user.is_staff:
            queryset = queryset.filter(
                Q(loai_hoa_don='ONLINE') | 
                Q(loai_hoa_don='OFFLINE', nhan_vien=user)
            )
        else:
            return HoaDon.objects.none()
        loai = self.request.query_params.get('loai')
        if loai:
            queryset = queryset.filter(loai_hoa_don=loai)
        
        # Lọc theo trạng thái
        trang_thai = self.request.query_params.get('trang_thai')
        if trang_thai and trang_thai != 'ALL':
            queryset = queryset.filter(trang_thai=trang_thai)
        return queryset
    
    # API TẠO ĐƠN HÀNG & XỬ LÝ KHÁCH HÀNG (POS)
    def create(self, request, *args, **kwargs):
        # 1. Validate dữ liệu đầu vào
        serializer = AdminCreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        items = data['cart_items']

        # Lấy thông tin khách hàng từ request (nếu có)
        khach_id = data.get('khach_hang_id')      # Trường hợp khách cũ
        new_name = request.data.get('ho_ten_moi') # Trường hợp tạo mới
        new_phone = request.data.get('sdt_moi')
        new_address = request.data.get('dia_chi_moi')
        new_email = request.data.get('email_moi')
        with transaction.atomic():
            total_money = 0
            details_buffer = []
            for item in items:
                try:
                    # Khóa dòng dữ liệu để tránh xung đột (Concurrency)
                    tui = TuiXach.objects.select_for_update().get(pk=item['id'])
                except TuiXach.DoesNotExist:
                    return Response({"error": f"Sản phẩm ID {item['id']} không tồn tại"}, status=400)
                
                qty = item['quantity']
                if tui.so_luong_ton < qty:
                    return Response({"error": f"Sản phẩm '{tui.ten_tui}' hết hàng (Còn: {tui.so_luong_ton})"}, status=400)
                # Trừ kho
                tui.so_luong_ton -= qty
                tui.save()

                # Cộng tiền
                total_money += tui.gia_tien * qty
                details_buffer.append({'tui': tui, 'qty': qty, 'price': tui.gia_tien})

            # ---------------------------------------------------------
            # BƯỚC B: XỬ LÝ 3 TRƯỜNG HỢP KHÁCH HÀNG
            # ---------------------------------------------------------
            khach_hang = None
            if khach_id:
                khach_hang = get_object_or_404(KhachHang, pk=khach_id)
            elif new_phone and new_name:
                existing_khach = KhachHang.objects.filter(so_dien_thoai=new_phone).first()
                
                if existing_khach:
                    khach_hang = existing_khach # Nếu SĐT đã có -> Dùng lại khách cũ
                else:
                    email_to_save = new_email if new_email and new_email.strip() else None

                    khach_hang = KhachHang.objects.create(
                        ho_ten=new_name,
                        so_dien_thoai=new_phone,
                        dia_chi=new_address if new_address else "",
                        email=email_to_save,     
                        tong_chi_tieu=0,    # Mới tạo nên chưa tiêu gì
                        user=None           # Khách tại quầy chưa có tài khoản web
                    )
            giam_gia = 0
            muc_giam_percent = 0
            
            if khach_hang:
                # Gọi hàm get_muc_giam_gia() bạn đã viết trong Model
                muc_giam_percent = khach_hang.get_muc_giam_gia()
                
                if muc_giam_percent > 0:
                    giam_gia = (total_money * muc_giam_percent) / 100
            # Xác định thông tin người nhận để in lên hóa đơn
            final_name = khach_hang.ho_ten if khach_hang else "Khách vãng lai"
            final_phone = khach_hang.so_dien_thoai if khach_hang else ""

            hoa_don = HoaDon.objects.create(
                ma_hoa_don=f"LXB-{int(timezone.now().timestamp())}",
                loai_hoa_don='OFFLINE',
                trang_thai='CHO_THANH_TOAN', # Tạo xong chờ thu tiền
                nhan_vien=request.user,
                khach_hang=khach_hang, # Null nếu là khách lẻ
                
                ho_ten_nguoi_nhan=final_name,
                sdt_nguoi_nhan=final_phone,
                
                tong_tien_hang=total_money,
                giam_gia=giam_gia,
                thanh_tien=total_money - giam_gia,
                ghi_chu=data.get('ghi_chu', 'Bán hàng tại quầy')
            )
            for d in details_buffer:
                ChiTietHoaDon.objects.create(
                    hoa_don=hoa_don,
                    tui_xach=d['tui'],
                    so_luong=d['qty'],
                    don_gia_luc_ban=d['price']
                )
            response_data = QuanLyHoaDonSerializer(hoa_don).data
            # Gửi thêm thông tin khách hàng để Frontend hiển thị popup "Khách VIP"
            if khach_hang:
                response_data['customer_info'] = {
                    "id": khach_hang.id,
                    "ho_ten": khach_hang.ho_ten,
                    "hang_thanh_vien": khach_hang.get_hang_thanh_vien(),
                    "muc_giam_gia": muc_giam_percent
                }

            return Response(response_data, status=status.HTTP_201_CREATED)
    # 2. XỬ LÝ THANH TOÁN (Cho đơn Tại quầy)
    # =========================================================
    @action(detail=True, methods=['post'])
    def xac_nhan_thanh_toan(self, request, pk=None):
        """ Bước 2 (Option A): Khách đưa tiền -> Nhân viên xác nhận -> Xong """
        don_hang = self.get_object()
        # Chỉ áp dụng cho đơn chưa thanh toán
        if don_hang.trang_thai == 'CHO_THANH_TOAN':
            with transaction.atomic():
                # 1. Đổi trạng thái sang HOÀN THÀNH luôn (Không giao vận gì cả)
                don_hang.trang_thai = 'HOAN_THANH'
                don_hang.save()
                
                # 2. Cộng tích lũy doanh số cho khách (Nếu có thành viên)
                if don_hang.khach_hang:
                    don_hang.khach_hang.tong_chi_tieu += don_hang.thanh_tien
                    don_hang.khach_hang.save()
                    
            return Response({"msg": "Thanh toán thành công!", "status": "HOAN_THANH"})
            
        return Response({"error": "Đơn hàng này không ở trạng thái chờ thanh toán"}, status=400)
    # =========================================================
    # 3. HỦY ĐƠN (Dùng chung cho cả Online và Offline)
    # =========================================================
    @action(detail=True, methods=['post'])
    def huy_don(self, request, pk=None):
        """ Bước 2 (Option B): Khách không mua nữa -> Hủy & Trả hàng về kho """
        don_hang = self.get_object()
        # Các trạng thái được phép hủy
        allowed = ['CHO_THANH_TOAN', 'CHO_XAC_NHAN', 'DA_XAC_NHAN']
        
        if don_hang.trang_thai in allowed:
            ly_do = request.data.get('ly_do', 'Khách đổi ý')
            with transaction.atomic():
                # 1. Hoàn lại tồn kho (Vì lúc tạo đơn đã trừ rồi)
                for chi_tiet in don_hang.chi_tiet.all():
                    tui = chi_tiet.tui_xach
                    tui.so_luong_ton += chi_tiet.so_luong
                    tui.save()
                
                # 2. Cập nhật trạng thái
                don_hang.trang_thai = 'DA_HUY'
                don_hang.ghi_chu = f"{don_hang.ghi_chu or ''} | Hủy: {ly_do}"
                don_hang.nhan_vien = request.user
                don_hang.save()
                
            return Response({"msg": "Đã hủy đơn và hoàn kho", "status": "DA_HUY"}) 
        return Response({"error": "Đơn hàng đã hoàn thành hoặc đang giao, không thể hủy"}, status=400)
    # =========================================================
    # 4. DUYỆT ĐƠN HÀNG (Bước 1 của đơn Online)
    # =========================================================
    @action(detail=True, methods=['post'])
    def duyet_don(self, request, pk=None):
        """ 
        Từ 'CHO_XAC_NHAN' -> 'DA_XAC_NHAN'
        Admin xác nhận đơn hợp lệ và bắt đầu đóng gói.
        """
        don_hang = self.get_object()
        
        if don_hang.trang_thai == 'CHO_XAC_NHAN':
            # Cập nhật trạng thái
            don_hang.trang_thai = 'DA_XAC_NHAN'
            # Ghi nhận nhân viên nào duyệt đơn
            don_hang.nhan_vien = request.user 
            don_hang.save()
            
            return Response({
                "msg": "Đã duyệt đơn hàng, chuyển sang đóng gói.", 
                "status": "DA_XAC_NHAN"
            })
        
        return Response({"error": "Chỉ duyệt được đơn đang chờ xác nhận"}, status=400)

    # =========================================================
    # 5. BẮT ĐẦU GIAO HÀNG (Bước 2 của đơn Online)
    # =========================================================
    @action(detail=True, methods=['post'])
    def bat_dau_giao_hang(self, request, pk=None):
        """
        Từ 'DA_XAC_NHAN' -> 'DANG_GIAO'
        Đã đóng gói xong, giao cho Shipper.
        """
        don_hang = self.get_object()
        
        if don_hang.trang_thai == 'DA_XAC_NHAN':
            don_hang.trang_thai = 'DANG_GIAO'
            don_hang.save()
            
            return Response({
                "msg": "Đơn hàng đang được vận chuyển.", 
                "status": "DANG_GIAO"
            })
            
        return Response({"error": "Đơn hàng chưa được xác nhận hoặc đã đi giao"}, status=400)

    # =========================================================
    # 6. XÁC NHẬN GIAO THÀNH CÔNG (Bước 3 - Kết thúc đơn Online)
    # =========================================================
    @action(detail=True, methods=['post'])
    def xac_nhan_giao_thanh_cong(self, request, pk=None):
        """
        Từ 'DANG_GIAO' -> 'HOAN_THANH'
        Shipper báo đã giao và thu tiền xong -> Cộng điểm tích lũy.
        """
        don_hang = self.get_object()
        
        if don_hang.trang_thai == 'DANG_GIAO':
            with transaction.atomic():
                # 1. Đổi trạng thái
                don_hang.trang_thai = 'HOAN_THANH'
                don_hang.ngay_cap_nhat = timezone.now() # Cập nhật thời gian hoàn thành
                don_hang.save()
                
                # 2. Cộng điểm tích lũy (Tổng chi tiêu) cho khách
                if don_hang.khach_hang:
                    don_hang.khach_hang.tong_chi_tieu += don_hang.thanh_tien
                    don_hang.khach_hang.save()
            
            return Response({
                "msg": "Giao hàng thành công! Đã cộng điểm tích lũy.", 
                "status": "HOAN_THANH"
            })
            
        return Response({"error": "Đơn hàng chưa ở trạng thái đang giao"}, status=400)
# =========================================================
# 3. NHÓM ĐƠN HÀNG (CLIENT ORDER)
# =========================================================
class ClientOrderViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """ Lấy lịch sử mua hàng của tôi """
        try:
            khach = KhachHang.objects.get(user=request.user)
            orders = HoaDon.objects.filter(khach_hang=khach).order_by('-ngay_tao')
            
            # Truyền context để serializer render full URL ảnh
            serializer = HoaDonSerializer(orders, many=True, context={'request': request})
            return Response({"success": True, "data": serializer.data})
        except KhachHang.DoesNotExist:
            return Response({"success": True, "data": []})

    def retrieve(self, request, pk=None):
        """ Xem chi tiết 1 đơn hàng """
        try:
            khach = KhachHang.objects.get(user=request.user)
            order = get_object_or_404(HoaDon, pk=pk, khach_hang=khach)
            
            serializer = HoaDonSerializer(order, context={'request': request})
            return Response({"success": True, "data": serializer.data})
        except Exception as e:
            return Response({"error": "Không tìm thấy đơn hàng"}, status=404)

    def create(self, request):
        """ TẠO ĐƠN HÀNG (CHECKOUT) """
        user = request.user
        data = request.data
        
        # 1. Kiểm tra tài khoản khách hàng
        try:
            khach_hang = KhachHang.objects.get(user=user)
        except KhachHang.DoesNotExist:
            return Response({"error": "Tài khoản chưa có thông tin khách hàng"}, status=400)

        # 2. Kiểm tra giỏ hàng
        san_pham_list = data.get('cart_items', [])
        if not san_pham_list:
            return Response({"error": "Giỏ hàng trống"}, status=400)

        with transaction.atomic():
            total_money = 0
            details_buffer = []

            # --- BƯỚC 1: LOOP QUA GIỎ HÀNG ĐỂ TÍNH TIỀN & TRỪ KHO ---
            for item in san_pham_list:
                try:
                    # Khóa dòng dữ liệu để tránh race condition
                    tui = TuiXach.objects.select_for_update().get(pk=item['id'])
                except TuiXach.DoesNotExist:
                    return Response({"error": f"Sản phẩm ID {item['id']} không tồn tại"}, status=400)
                
                qty = int(item['quantity'])
                if tui.so_luong_ton < qty:
                    return Response({"error": f"Sản phẩm '{tui.ten_tui}' chỉ còn {tui.so_luong_ton} cái"}, status=400)
                
                # Trừ kho ngay lập tức
                tui.so_luong_ton -= qty
                tui.save()

                thanh_tien_item = tui.gia_tien * qty
                total_money += thanh_tien_item

                details_buffer.append({
                    'tui': tui,         # Object TuiXach
                    'qty': qty,
                    'price': tui.gia_tien # Lưu giá tại thời điểm bán
                })

            # --- BƯỚC 2: TÍNH GIẢM GIÁ ---
            # Giả sử trong model KhachHang có hàm get_muc_giam_gia()
            phan_tram_giam = getattr(khach_hang, 'get_muc_giam_gia', lambda: 0)() 
            tien_giam_gia = (total_money * phan_tram_giam) / 100
            tien_thanh_toan = total_money - tien_giam_gia

            # --- BƯỚC 3: TẠO HÓA ĐƠN (HEADER) ---
            ghi_chu_user = data.get('ghi_chu', '')
            ghi_chu_he_thong = f"VIP: Giảm {phan_tram_giam}%" if phan_tram_giam > 0 else ""
            
            hoa_don = HoaDon.objects.create(
                ma_hoa_don=f"LXB-{int(timezone.now().timestamp())}",
                khach_hang=khach_hang,
                loai_hoa_don='ONLINE',
                trang_thai='CHO_XAC_NHAN',
                phuong_thuc_tt=data.get('payment_method', 'COD'),
                
                # Snapshot thông tin giao hàng
                ho_ten_nguoi_nhan=data.get('ho_ten', khach_hang.ho_ten),
                sdt_nguoi_nhan=data.get('sdt', khach_hang.so_dien_thoai),
                dia_chi_giao_hang=data.get('dia_chi', khach_hang.dia_chi),
                
                # Tiền nong
                tong_tien_hang=total_money,
                giam_gia=tien_giam_gia,
                thanh_tien=tien_thanh_toan,
                
                ghi_chu=f"{ghi_chu_user} | {ghi_chu_he_thong}".strip(" | ")
            )

            # --- BƯỚC 4: TẠO CHI TIẾT HÓA ĐƠN (ITEMS) ---
            for detail in details_buffer:
                ChiTietHoaDon.objects.create(
                    hoa_don=hoa_don,               # Field name: hoa_don
                    tui_xach=detail['tui'],        # Field name: tui_xach
                    so_luong=detail['qty'],        # Field name: so_luong
                    don_gia_luc_ban=detail['price'] # Field name: don_gia_luc_ban (QUAN TRỌNG)
                )

            # --- BƯỚC 5: CẬP NHẬT TỔNG CHI TIÊU KHÁCH ---
            khach_hang.tong_chi_tieu += tien_thanh_toan
            khach_hang.save()

            return Response({
                "success": True,
                "message": "Đặt hàng thành công",
                "order_code": hoa_don.ma_hoa_don,
                "payment_info": {
                    "tong_tien_hang": total_money,
                    "giam_gia": tien_giam_gia,
                    "thanh_tien": tien_thanh_toan
                }
            }, status=201)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """ HỦY ĐƠN HÀNG """
        try:
            khach = KhachHang.objects.get(user=request.user)
            order = get_object_or_404(HoaDon, pk=pk, khach_hang=khach)
            
            if order.trang_thai == 'CHO_XAC_NHAN':
                with transaction.atomic():
                    # 1. Hoàn lại kho
                    for chi_tiet in order.chi_tiet.all():
                        tui = chi_tiet.tui_xach
                        tui.so_luong_ton += chi_tiet.so_luong
                        tui.save()
                    
                    # 2. Trừ lại điểm tích lũy
                    khach.tong_chi_tieu -= order.thanh_tien
                    if khach.tong_chi_tieu < 0: khach.tong_chi_tieu = 0
                    khach.save()
                    
                    # 3. Đổi trạng thái
                    order.trang_thai = 'DA_HUY'
                    order.ghi_chu = (order.ghi_chu or "") + " | Khách tự hủy"
                    order.save()
                    
                return Response({"success": True, "message": "Đã hủy đơn hàng"})
            else:
                return Response({"error": "Đơn hàng đang xử lý, không thể hủy"}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=400)



class ThongKeViewSet(viewsets.ViewSet):
    permission_classes = [IsOwnerUser]
    # --- HÀM PHỤ: Xử lý lọc ngày & Ngoại lệ E1 ---
    def _get_date_range(self, request):
        now = timezone.now()
        start_str = request.query_params.get('from_date')
        end_str = request.query_params.get('to_date')

        # Mặc định: 30 ngày gần nhất nếu không chọn ngày
        end_date = now
        start_date = now - timedelta(days=30)

        try:
            if start_str:
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
            if end_str:
                end_date = datetime.strptime(end_str, '%Y-%m-%d')
                # Chỉnh về cuối ngày (23:59:59) để lấy trọn vẹn dữ liệu ngày kết thúc
                end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass # Lỗi định dạng ngày thì dùng mặc định

        # NGOẠI LỆ E1: Ngày bắt đầu > Ngày kết thúc -> Báo lỗi
        if start_date > end_date:
            return None, None, "Ngày bắt đầu không được lớn hơn ngày kết thúc."

        return start_date, end_date, None
    @action(detail=False, methods=['get'])
    def tong_quan(self, request):
        start_date, end_date, error = self._get_date_range(request)
        if error: return Response({"error": error}, status=400)
        # 1. Tính doanh thu kỳ này (Chỉ tính đơn HOAN_THANH)
        current_revenue = HoaDon.objects.filter(
            ngay_tao__range=[start_date, end_date], 
            trang_thai='HOAN_THANH'
        ).aggregate(total=Sum('thanh_tien'))['total'] or 0
        # 2. Tính doanh thu kỳ trước (Để so sánh %)
        # Logic: Nếu lọc 10 ngày, thì lấy 10 ngày trước đó để so sánh
        duration = end_date - start_date
        prev_end = start_date - timedelta(seconds=1)
        prev_start = prev_end - duration
        
        prev_revenue = HoaDon.objects.filter(
            ngay_tao__range=[prev_start, prev_end], 
            trang_thai='HOAN_THANH'
        ).aggregate(total=Sum('thanh_tien'))['total'] or 0

        # 3. Tính % Tăng trưởng
        growth_percent = 0
        if prev_revenue > 0:
            growth_percent = ((current_revenue - prev_revenue) / prev_revenue) * 100
        elif current_revenue > 0:
            growth_percent = 100 # Trước đó 0, giờ có -> Tăng trưởng tuyệt đối

        return Response({
            "ky_nay": {
                "range": f"{start_date.date()} -> {end_date.date()}",
                "doanh_thu": current_revenue
            },
            "ky_truoc": {
                "range": f"{prev_start.date()} -> {prev_end.date()}",
                "doanh_thu": prev_revenue
            },
            "tang_truong": round(growth_percent, 2) # Làm tròn 2 số lẻ (Ví dụ: 12.55%)
        })
    @action(detail=False, methods=['get'])
    def bieu_do_cot(self, request):
        """ Trả về doanh thu của từng ngày trong khoảng thời gian chọn """
        start_date, end_date, error = self._get_date_range(request)
        if error: return Response({"error": error}, status=400)

        data = (
            HoaDon.objects
            .filter(ngay_tao__range=[start_date, end_date], trang_thai='HOAN_THANH')
            .annotate(date=TruncDate('ngay_tao')) # Gom nhóm theo ngày
            .values('date')
            .annotate(doanh_thu=Sum('thanh_tien'))
            .order_by('date')
        )

        return Response({"data": list(data)})
    @action(detail=False, methods=['get'])
    def bieu_do_tron(self, request):
        """ Thống kê xem mỗi Danh mục túi xách chiếm bao nhiêu % doanh thu """
        start_date, end_date, error = self._get_date_range(request)
        if error: return Response({"error": error}, status=400)

        # Join bảng: ChiTiet -> TuiXach -> DanhMuc -> Group by Tên danh mục
        data = (
            ChiTietHoaDon.objects
            .filter(
                hoa_don__ngay_tao__range=[start_date, end_date],
                hoa_don__trang_thai='HOAN_THANH'
            )
            .values('tui_xach__danh_muc__ten_danh_muc') 
            .annotate(value=Sum(F('so_luong') * F('don_gia_luc_ban')))
            .order_by('-value')
        )
        
        # Format dữ liệu chuẩn để Frontend vẽ
        formatted_data = [
            {"name": item['tui_xach__danh_muc__ten_danh_muc'], "value": item['value']}
            for item in data
        ]
        return Response({"data": formatted_data})
    @action(detail=False, methods=['get'])
    def du_lieu_xuat_excel(self, request):
        """ Trả về dữ liệu chi tiết để xuất file Excel """
        start_date, end_date, error = self._get_date_range(request)
        if error: return Response({"error": error}, status=400)

        # Lấy danh sách đơn hàng
        orders = HoaDon.objects.filter(
            ngay_tao__range=[start_date, end_date], 
            trang_thai='HOAN_THANH'
        ).select_related('khach_hang', 'nhan_vien').order_by('-ngay_tao')
        if not orders.exists():
            return Response({"error": "Không có dữ liệu đơn hàng nào để xuất báo cáo."}, status=404)
        export_data = []
        for o in orders:
            export_data.append({
                "Mã HĐ": o.ma_hoa_don,
                "Ngày GD": o.ngay_tao.strftime("%d/%m/%Y %H:%M"),
                "Khách Hàng": o.ho_ten_nguoi_nhan,
                "SĐT": o.sdt_nguoi_nhan,
                "Tổng Tiền": o.tong_tien_hang,
                "Giảm Giá": o.giam_gia,
                "Thực Thu": o.thanh_tien,
                "Loại Đơn": o.get_loai_hoa_don_display(),
                "Người Tạo": o.nhan_vien.username if o.nhan_vien else "Web Online"
            })

        return Response({
            "success": True, 
            "file_name": f"Bao_Cao_Doanh_Thu_{start_date.date()}_{end_date.date()}.xlsx",
            "data": export_data
        })





FOLDER_STAFF_COLLECTION_ID = '1E2NNS3kXOoRnu0q8S_QzK_p1DHRXwGiD'

class StaffCollectionViewSet(viewsets.ModelViewSet):
    """
    API Quản lý Bộ Sưu Tập (Dành cho Nhân viên/Admin).
    - Model: BanThietKe
    - Trạng thái cố định: 'BO_SUU_TAP'
    - Lưu ý: Ảnh sẽ được lưu vào PARENT_FOLDER_ID mặc định trong utils.py
    """
    serializer_class = BanThietKeSerializer
    permission_classes = [IsStaffOrOwner] 
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return BanThietKe.objects.filter(
            trang_thai='BO_SUU_TAP',
            nguoi_so_huu__is_staff=True 
        ).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        # 1. Kiểm tra file
        file_obj = request.FILES.get('file_anh') 
        if not file_obj:
            return Response({"error": "Vui lòng chọn file hình ảnh."}, status=400)

        # 2. Upload lên Drive
        # --- SỬA LẠI ĐOẠN NÀY ---
        # Vì hàm upload cũ không nhận tham số folder_id, ta chỉ truyền file_obj
        try:
            drive_link = upload_file_to_drive(file_obj)
        except TypeError:
            # Phòng hờ trường hợp hàm utils vẫn sai
            return Response({"error": "Lỗi hàm upload không tương thích."}, status=500)
        
        if not drive_link:
            return Response({"error": "Lỗi kết nối Google Drive, không thể upload."}, status=500)

        # 3. Lưu vào Database
        try:
            ban_thiet_ke = BanThietKe.objects.create(
                nguoi_so_huu=request.user,    
                drive_url=drive_link,         
                ghi_chu=request.data.get('ghi_chu', ''),
                trang_thai='BO_SUU_TAP'       
            )
        except Exception as e:
            return Response({"error": f"Lỗi lưu Database: {str(e)}"}, status=500)

        # 4. Trả về kết quả
        return Response(
            BanThietKeSerializer(ban_thiet_ke).data, 
            status=status.HTTP_201_CREATED
        )
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            drive_url = instance.drive_url
            
            # --- Logic tách ID từ Link ---
            # Link thường có dạng: https://drive.google.com/file/d/1A2B3C.../view?usp=drivesdk
            # Ta cần lấy chuỗi "1A2B3C..." nằm giữa "/d/" và "/view"
            file_id = None
            if '/d/' in drive_url:
                try:
                    # Tách chuỗi dựa vào '/d/'
                    parts = drive_url.split('/d/')
                    if len(parts) > 1:
                        # Lấy phần sau '/d/', rồi cắt bỏ phần sau '/' tiếp theo (nếu có)
                        file_id = parts[1].split('/')[0]
                except:
                    pass
            
            # --- Gọi lệnh xóa trên Drive ---
            if file_id:
                delete_file_from_drive(file_id)
            else:
                print("Không tìm thấy File ID hợp lệ để xóa trên Drive, chỉ xóa DB.")

            # --- Xóa trong Database ---
            return super().destroy(request, *args, **kwargs)
            
        except Exception as e:
            return Response({"error": f"Lỗi khi xóa: {str(e)}"}, status=500)