/opt/homebrew/Library/Homebrew/cmd/shellenv.sh: line 27: /bin/ps: Operation not permitted
from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.facebook_client import FacebookPagePublisher
from src.settings import Settings
from src.sheet_client import (
    COL_POST_ID,
    COL_POST_LINK,
    COL_STATUS,
    COL_VIDEO_ID,
    SheetRepository,
)
from src.telegram_client import TelegramDownloader, parse_message_link


async def run(*, dry_run: bool = False, limit: int | None = None) -> None:
    load_dotenv()
    settings = Settings.from_env(dry_run=dry_run)
    sheet = SheetRepository(
        settings.google_sheet_id,
        settings.google_sheet_tab,
        settings.google_credentials,
    )
    rows = sheet.pending_rows()
    if limit is not None:
        rows = rows[:limit]

    if not rows:
        print("Không có dòng nào cần đăng bài.")
        return

    print(f"Tìm thấy {len(rows)} dòng cần xử lý.")
    if dry_run:
        for row in rows:
            ref = parse_message_link(row.telegram_link)
            print(
                f"[DRY-RUN] Dòng {row.row_number}: Page {row.page_id}, "
                f"Telegram entity={ref.entity}, message={ref.message_id}"
            )
        return

    publisher = FacebookPagePublisher(
        settings.fb_access_token,
        settings.fb_graph_version,
    )
    async with TelegramDownloader(
        settings.telegram_api_id,
        settings.telegram_api_hash,
        settings.telegram_session,
    ) as telegram:
        for row in rows:
            try:
                sheet.update(row.row_number, **{COL_STATUS: "Đang xử lý"})
                video_id = row.video_id
                if not video_id:
                    with tempfile.TemporaryDirectory(prefix="auto-post-page-") as temp_dir:
                        video_path = await telegram.download_video(
                            row.telegram_link,
                            Path(temp_dir),
                        )
                        video_id = publisher.upload_video(
                            row.page_id,
                            video_path,
                            row.text_content,
                            title=row.description,
                        )
                    sheet.update(
                        row.row_number,
                        **{
                            COL_VIDEO_ID: video_id,
                            COL_STATUS: "Đã upload, đang chờ Meta xử lý",
                        },
                    )

                post = publisher.wait_for_post(row.page_id, video_id)
                sheet.update(
                    row.row_number,
                    **{
                        COL_VIDEO_ID: post.video_id,
                        COL_POST_ID: post.post_id,
                        COL_POST_LINK: post.permalink_url,
                        COL_STATUS: "Thành công - CTA MESSAGE_PAGE",
                    },
                )
                print(f"Dòng {row.row_number}: {post.permalink_url}")
            except Exception as exc:  # noqa: BLE001
                message = f"Lỗi: {exc}"
                sheet.update(row.row_number, **{COL_STATUS: message[:500]})
                print(f"Dòng {row.row_number}: {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tự động đăng video lên Facebook Page")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra dữ liệu")
    parser.add_argument("--limit", type=int, help="Giới hạn số dòng xử lý")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
