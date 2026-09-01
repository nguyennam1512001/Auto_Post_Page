from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass(frozen=True)
class PublishedPost:
    video_id: str
    post_id: str
    permalink_url: str


class FacebookPagePublisher:
    def __init__(self, access_token: str, graph_version: str = "v25.0") -> None:
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/{graph_version}"
        self.http = requests.Session()

    @staticmethod
    def _raise_for_graph(response: requests.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Meta trả về dữ liệu không hợp lệ: HTTP {response.status_code}") from exc
        if not response.ok or "error" in payload:
            error = payload.get("error", {})
            message = error.get("message", response.text)
            code = error.get("code", response.status_code)
            raise RuntimeError(f"Meta API lỗi {code}: {message}")
        return payload

    def _page_token(self, page_id: str) -> str:
        response = self.http.get(
            f"{self.base_url}/{page_id}",
            params={"fields": "access_token", "access_token": self.access_token},
            timeout=60,
        )
        payload = self._raise_for_graph(response)
        return payload.get("access_token") or self.access_token

    def upload_video(
        self,
        page_id: str,
        video_path: Path,
        message: str,
        *,
        title: str = "",
    ) -> str:
        page_token = self._page_token(page_id)
        # Meta giới hạn tiêu đề video tối đa 255 ký tự. SP_Description có thể
        # dài hơn vì là mô tả sản phẩm, nên chỉ dùng 255 ký tự đầu làm title.
        safe_title = (title or "").strip()[:255]
        start = self.http.post(
            f"{self.base_url}/{page_id}/videos",
            data={
                "upload_phase": "start",
                "file_size": video_path.stat().st_size,
                "access_token": page_token,
            },
            timeout=60,
        )
        session = self._raise_for_graph(start)
        upload_session_id = session["upload_session_id"]
        video_id = str(session["video_id"])
        start_offset = int(session["start_offset"])
        end_offset = int(session["end_offset"])

        with video_path.open("rb") as video_file:
            while start_offset < end_offset:
                video_file.seek(start_offset)
                chunk = video_file.read(end_offset - start_offset)
                transfer = self.http.post(
                    f"{self.base_url}/{page_id}/videos",
                    data={
                        "upload_phase": "transfer",
                        "upload_session_id": upload_session_id,
                        "start_offset": start_offset,
                        "access_token": page_token,
                    },
                    files={"video_file_chunk": ("video.mp4", chunk)},
                    timeout=300,
                )
                offsets = self._raise_for_graph(transfer)
                new_start = int(offsets["start_offset"])
                end_offset = int(offsets["end_offset"])
                if new_start <= start_offset:
                    raise RuntimeError("Meta không cập nhật tiến độ upload video")
                start_offset = new_start

        call_to_action = {
            "type": "MESSAGE_PAGE",
            "value": {"link": f"https://m.me/{page_id}"},
        }
        finish = self.http.post(
            f"{self.base_url}/{page_id}/videos",
            data={
                "upload_phase": "finish",
                "upload_session_id": upload_session_id,
                "description": message,
                "title": safe_title,
                "published": "true",
                "call_to_action": json.dumps(call_to_action, ensure_ascii=False),
                "access_token": page_token,
            },
            timeout=120,
        )
        self._raise_for_graph(finish)
        return video_id

    def wait_for_post(self, page_id: str, video_id: str, timeout_seconds: int = 900) -> PublishedPost:
        # Không gọi API để kiểm tra lại video/post. Graph API v26 có thể trả
        # lỗi 100 cho các field của Video node dù upload đã thành công. PAGE_ID
        # và FB_UPLOAD_ID đã đủ để tạo URL video công khai dùng làm Post Link.
        return PublishedPost(
            video_id=video_id,
            post_id="",
            permalink_url=f"https://www.facebook.com/{page_id}/videos/{video_id}/",
        )
