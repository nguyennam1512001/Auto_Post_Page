/opt/homebrew/Library/Homebrew/cmd/shellenv.sh: line 27: /bin/ps: Operation not permitted
# Auto_Post_Page

Tự động đọc Google Sheet, tải video từ Telegram bằng tài khoản đã tham gia
channel, đăng video công khai lên Facebook Page với nút **Gửi tin nhắn**, sau
đó ghi `POST_ID`, `Post Link` và trạng thái ngược lại Sheet.

## Cột Google Sheet

Tên cột nằm ở hàng 1; vị trí A, B, C... không quan trọng.

| Cột | Loại | Công dụng |
|---|---|---|
| `PAGE_ID` | bắt buộc | Page cần đăng bài |
| `SP_Description` | không bắt buộc | Tiêu đề/mô tả nội bộ |
| `Text_Content` | bắt buộc | Nội dung bài đăng |
| `Telegram_video_link` | bắt buộc | Link `t.me/c/.../...` hoặc `t.me/username/...` |
| `ID Video` | tự ghi | Giúp chạy lại mà không upload trùng |
| `POST_ID` | tự ghi | ID dùng cho repo tạo Campaign |
| `Post Link` | tự ghi | Link gửi nhân viên |
| `POST_STATUS` | tự ghi | Tiến độ/lỗi đăng bài; tự thêm vì tab hiện chưa có |

Nếu các cột đầu ra chưa tồn tại, chương trình tự thêm chúng vào cuối hàng 1.
Dòng đã có `POST_ID` hoặc `Post Link` sẽ được bỏ qua.

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

Ngay sau khi upload xong, chương trình ghi `ID Video`. Nếu Meta vẫn đang xử
lý video hoặc CTA chưa xác minh được, lần chạy tiếp theo dùng lại Video ID đó
để kiểm tra, không tải và đăng video lần nữa.

Chỉ khi bài có `post_id`, `permalink_url` và CTA trả về là `MESSAGE_PAGE`, chương
trình mới ghi trạng thái `Thành công - CTA MESSAGE_PAGE`.
