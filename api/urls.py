from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
# 1. NHÓM QUẢN LÝ (ADMIN / STAFF)
router.register(r'danh-muc', DanhMucViewSet) 
router.register(r'tui-xach', TuiXachViewSet) 
router.register(r'khach-hang', KhachHangViewSet)
router.register(r'thong-ke', ThongKeViewSet, basename='thong-ke')
router.register(r'quan-ly-don-hang', QuanLyDonHangViewSet, basename='admin-orders')
# 2. NHÓM PUBLIC (KHÁCH VÃNG LAI)
router.register(r'products', PublicProductViewSet, basename='public-products')
router.register(r'categories', PublicCategoryViewSet, basename='public-categories')
# 3. NHÓM CLIENT (KHÁCH ĐÃ ĐĂNG NHẬP)
router.register(r'my-orders', ClientOrderViewSet, basename='orders') 

# 4. API cho phần thiết kế AI
router.register(r'staff-collection', StaffCollectionViewSet, basename='staff-collection')

urlpatterns = [
    path('', include(router.urls)),
    # --- B. AUTHENTICATION (Đăng nhập/ký/Profile) ---
    path('login/', MyTokenObtainPairView.as_view(), name='dang-nhap'),
    path('logout/', LogoutView.as_view(), name='dang-xuat'),
    path('register/', RegisterView.as_view(), name='auth-register'), # Gom về 1 đường dẫn này
    
    # Profile: Dùng KhachHangProfileView mới (Update & Get info chuẩn)
    path('profile/', KhachHangProfileView.as_view(), name='user-profile'), 

    # --- D. CHỨC NĂNG QUẢN LÝ RIÊNG (ADMIN) ---
    path('tuixach/them-moi/', CreateTuiXachView.as_view(), name='add-tuixach'),
    
    # --- E. THỐNG KÊ & DASHBOARD ---
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'), # API Tổng quan trang chủ
    path('thong-ke-don-hang/', ThongKeDonHangView.as_view(), name='thong-ke-don'),
]