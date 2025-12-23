# Sử dụng Python 3.10 bản nhẹ
FROM python:3.10-slim

# Ngăn Python tạo file cache .pyc và chạy log trực tiếp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Thiết lập thư mục làm việc
WORKDIR /app

# --- ĐOẠN QUAN TRỌNG ĐÃ SỬA ---
# Cài đặt các thư viện hệ thống cần thiết cho MySQL (pkg-config, gcc, libmysqlclient-dev)
RUN apt-get update && apt-get install -y \
    pkg-config \
    gcc \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
# -----------------------------

# Copy file thư viện vào
COPY requirements.txt /app/

# Nâng cấp pip và cài đặt thư viện
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào
COPY . /app/

# Mở cổng 8000
EXPOSE 8000

# Lệnh chạy server (Nhớ đảm bảo config.wsgi là đúng tên thư mục của bạn)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]