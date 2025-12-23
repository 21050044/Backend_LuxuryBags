
from django.contrib import admin
from django.urls import path, include  # <--- BẠN CẦN THÊM 'include' Ở ĐÂY

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- THÊM DÒNG NÀY VÀO ---
    path('api/', include('api.urls')), 
    # Nghĩa là: Mọi thứ bắt đầu bằng "api/" sẽ chuyển sang file api/urls.py xử lý
]