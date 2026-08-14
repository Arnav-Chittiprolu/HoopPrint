from __future__ import annotations

import certifi
import httpx

from app.config import Settings

STORAGE_BUCKET = "clips"
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase URL and service role key must be configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }

    async def upload_clip_file(self, storage_path: str, content: bytes, content_type: str) -> None:
        url = f"{self.base_url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"},
                content=content,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Storage upload failed: {response.status_code} {response.text}")

    async def delete_clip_file(self, storage_path: str) -> None:
        url = f"{self.base_url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            await client.delete(url, headers=self.headers)

    async def insert_clip(self, row: dict) -> dict:
        url = f"{self.base_url}/rest/v1/clips"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=row,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Clip insert failed: {response.status_code} {response.text}")
            data = response.json()
            return data[0] if isinstance(data, list) else data

    async def list_clips(self, user_id: str) -> list[dict]:
        url = (
            f"{self.base_url}/rest/v1/clips"
            f"?user_id=eq.{user_id}&order=created_at.desc"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Clip list failed: {response.status_code} {response.text}")
            return response.json()

    async def get_clip(self, clip_id: str, user_id: str) -> dict | None:
        url = f"{self.base_url}/rest/v1/clips?id=eq.{clip_id}&user_id=eq.{user_id}&limit=1"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Clip fetch failed: {response.status_code} {response.text}")
            rows = response.json()
            return rows[0] if rows else None

    async def get_clip_by_id(self, clip_id: str) -> dict | None:
        url = f"{self.base_url}/rest/v1/clips?id=eq.{clip_id}&limit=1"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Clip fetch failed: {response.status_code} {response.text}")
            rows = response.json()
            return rows[0] if rows else None

    async def update_clip(self, clip_id: str, patch: dict) -> dict:
        url = f"{self.base_url}/rest/v1/clips?id=eq.{clip_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.patch(
                url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=patch,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Clip update failed: {response.status_code} {response.text}")
            data = response.json()
            return data[0] if isinstance(data, list) else data

    async def download_clip_file(self, storage_path: str) -> bytes:
        url = f"{self.base_url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Storage download failed: {response.status_code} {response.text}")
            return response.content

    async def delete_keypoints_for_clip(self, clip_id: str) -> None:
        url = f"{self.base_url}/rest/v1/keypoints?clip_id=eq.{clip_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.delete(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Keypoint delete failed: {response.status_code} {response.text}")

    async def insert_keypoints(self, rows: list[dict]) -> None:
        if not rows:
            return
        url = f"{self.base_url}/rest/v1/keypoints"
        async with httpx.AsyncClient(timeout=60.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Prefer": "return=minimal"},
                json=rows,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Keypoint insert failed: {response.status_code} {response.text}")

    async def list_keypoints(self, clip_id: str) -> list[dict]:
        url = (
            f"{self.base_url}/rest/v1/keypoints"
            f"?clip_id=eq.{clip_id}&order=frame_index.asc"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Keypoint list failed: {response.status_code} {response.text}")
            return response.json()
