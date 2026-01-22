# Server Deployment Guide

## Perubahan yang Dilakukan

`app.py` telah dikonfigurasi untuk berjalan di server host dengan perubahan berikut:

### 1. **Host Binding**
- **Sebelum**: `host='127.0.0.1'` (default, hanya localhost)
- **Sesudah**: `host='0.0.0.0'` (semua network interfaces)

Dengan `0.0.0.0`, aplikasi dapat diakses dari:
- Localhost: `http://localhost:5500`
- IP lokal: `http://192.168.x.x:5500`
- IP publik: `http://your-server-ip:5500`

### 2. **Environment Variables**
Aplikasi sekarang menggunakan environment variables untuk konfigurasi:

- **PORT**: Port yang digunakan (default: 5500)
- **DEBUG**: Mode debug (default: False untuk produksi)

## Cara Menjalankan

### Development (Lokal)
```bash
# Dengan debug mode
DEBUG=true python app.py

# Tanpa debug mode
python app.py
```

### Production (Server)
```bash
# Dengan port default (5500)
python app.py

# Dengan port custom
PORT=8080 python app.py

# Dengan environment file
# Buat file .env dengan:
# PORT=8080
# DEBUG=False
python app.py
```

### Deployment dengan Gunicorn (Recommended untuk Production)
```bash
# Install gunicorn
pip install gunicorn

# Jalankan dengan gunicorn
gunicorn -w 4 -b 0.0.0.0:5500 app:app

# Dengan custom port
gunicorn -w 4 -b 0.0.0.0:8080 app:app
```

### Deployment dengan Docker
```dockerfile
# Dockerfile example
FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5500
CMD ["python", "app.py"]
```

## Konfigurasi Firewall

Pastikan port yang digunakan terbuka di firewall server:

```bash
# Ubuntu/Debian
sudo ufw allow 5500/tcp

# CentOS/RHEL
sudo firewall-cmd --add-port=5500/tcp --permanent
sudo firewall-cmd --reload
```

## Catatan Penting

1. **Security**: Debug mode dimatikan secara default untuk production
2. **HTTPS**: Untuk production, gunakan reverse proxy (nginx/apache) dengan SSL
3. **Monitoring**: Gunakan tools seperti supervisor atau systemd untuk monitoring
4. **Environment Variables**: Simpan konfigurasi sensitif di `.env` file (jangan commit ke git)

## Troubleshooting

### Port sudah digunakan
```bash
# Cek port yang sedang digunakan
sudo netstat -tlnp | grep 5500

# Atau gunakan port lain
PORT=8080 python app.py
```

### Cannot bind to 0.0.0.0
- Pastikan tidak ada aplikasi lain yang menggunakan port yang sama
- Periksa permission (beberapa port memerlukan sudo)

### Tidak bisa diakses dari luar
- Periksa firewall settings
- Periksa security group (jika di cloud provider)
- Pastikan server IP publik sudah benar
