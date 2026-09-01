# Auto_Post_Page

Tự động đọc Google Sheet, tải video từ Telegram bằng tài khoản đã tham gia
channel, đăng video công khai lên Facebook Page với nút **Gửi tin nhắn**, sau
đó ghi `Post Link`, `FB_UPLOAD_ID` và `POST_STATUS` ngược lại Sheet.

## Cột Google Sheet

Tên cột nằm ở hàng 1; vị trí A, B, C... không quan trọng.

| Cột | Loại | Công dụng |
|---|---|---|
| `PAGE_ID` | bắt buộc | Page cần đăng bài |
| `SP_Description` | không bắt buộc | Tiêu đề/mô tả nội bộ |
| `Text_Content` | bắt buộc | Nội dung bài đăng |
| `Telegram_video_link` | bắt buộc | Link `t.me/c/.../...` hoặc `t.me/username/...` |
| `ID Video` | công thức Sheet | Tự tách ID từ `Post Link`; chương trình không ghi vào cột này |
| `Post Link` | tự ghi | Link gửi nhân viên |
| `FB_UPLOAD_ID` | bắt buộc, tự ghi | ID upload kỹ thuật, giúp chạy lại không đăng trùng |
| `POST_STATUS` | bắt buộc, tự ghi | Tiến độ hoặc lỗi đăng bài |

Bạn cần tạo đầy đủ các cột trên ở hàng 1. Chương trình không tự thêm, xóa hoặc
di chuyển cột. Nếu thiếu cột, chương trình dừng và báo tên cột bị thiếu.
Dòng đã có `Post Link` sẽ được bỏ qua.

## Repository secrets

Vào **Settings → Secrets and variables → Actions** và thêm:

```text
FB_ACCESS_TOKEN
GOOGLE_CREDENTIALS
GOOGLE_SHEET_ID
GOOGLE_SHEET_TAB
TELEGRAM_API_ID
TELEGRAM_API_HASH
TELEGRAM_SESSION
```

`FB_ACCESS_TOKEN` cần quyền quản lý/đăng bài trên tất cả Page được dùng.
Service Account trong `GOOGLE_CREDENTIALS` cần được share Sheet với quyền Editor.

## Tạo TELEGRAM_SESSION

1. Tạo Telegram application tại <https://my.telegram.org/apps> để lấy API ID và API Hash.
2. Chạy trên máy cá nhân (không chạy trong GitHub Actions):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_API_ID="..."
export TELEGRAM_API_HASH="..."
python scripts/generate_telegram_session.py
```

3. Đăng nhập Telegram theo hướng dẫn và lưu chuỗi in ra vào secret
   `TELEGRAM_SESSION`. Không commit chuỗi session vào repository.

Tài khoản Telegram tạo session phải đang tham gia channel chứa video.

## Chạy

Vào tab **Actions → Đăng bài lên Facebook Page → Run workflow**.

Nên chạy lần đầu với:

```text
dry_run = true
limit = 1
```

Sau khi dữ liệu được nhận đúng, chạy thật:

```text
dry_run = false
limit = 1
```

## Cơ chế chống đăng trùng

Ngay sau khi upload xong, chương trình ghi `FB_UPLOAD_ID`. Nếu Meta vẫn đang xử
lý video hoặc CTA chưa xác minh được, lần chạy tiếp theo dùng lại Video ID đó
để kiểm tra, không tải và đăng video lần nữa.

Khi Meta trả về `permalink_url`, chương trình ghi URL đó vào cả `Post Link` và
`POST_STATUS`. Chương trình không đọc hoặc xác minh CTA sau khi đăng.
