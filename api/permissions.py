from rest_framework import permissions

class IsOwnerUser(permissions.BasePermission):
    """Quyền cao nhất: Chỉ dành cho CHỦ CỬA HÀNG (Superuser)"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)

class IsStaffOrOwner(permissions.BasePermission):
    """Quyền quản lý: Dành cho cả NHÂN VIÊN và CHỦ"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)