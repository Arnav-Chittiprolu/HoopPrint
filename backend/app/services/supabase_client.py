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

    async def upload_clip_file(
        self,
        storage_path: str,
        content: bytes,
        content_type: str,
        *,
        upsert: bool = False,
    ) -> None:
        url = f"{self.base_url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={
                    **self.headers,
                    "Content-Type": content_type,
                    "x-upsert": "true" if upsert else "false",
                },
                content=content,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Storage upload failed: {response.status_code} {response.text}")

    async def create_signed_url(self, storage_path: str, *, expires_in: int = 3600) -> str:
        url = f"{self.base_url}/storage/v1/object/sign/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Content-Type": "application/json"},
                json={"expiresIn": expires_in},
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Signed URL failed: {response.status_code} {response.text}")
            payload = response.json()
            signed = payload.get("signedURL") or payload.get("signedUrl")
            if not signed:
                raise RuntimeError(f"Signed URL missing in response: {payload}")
            if signed.startswith("http"):
                return signed
            return f"{self.base_url}/storage/v1{signed}"

    async def storage_object_exists(self, storage_path: str) -> bool:
        url = f"{self.base_url}/storage/v1/object/info/{STORAGE_BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            return response.status_code < 400

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

    async def get_player_box(self, clip_id: str) -> dict | None:
        url = f"{self.base_url}/rest/v1/player_boxes?clip_id=eq.{clip_id}&limit=1"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Player box fetch failed: {response.status_code} {response.text}")
            rows = response.json()
            return rows[0] if rows else None

    async def upsert_player_box(self, clip_id: str, x: float, y: float, w: float, h: float) -> dict:
        url = f"{self.base_url}/rest/v1/player_boxes?on_conflict=clip_id"
        payload = {"clip_id": clip_id, "x": x, "y": y, "w": w, "h": h}
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={
                    **self.headers,
                    "Prefer": "resolution=merge-duplicates,return=representation",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Player box upsert failed: {response.status_code} {response.text}")
            data = response.json()
            return data[0] if isinstance(data, list) else data

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

    async def get_profile(self, user_id: str) -> dict | None:
        url = (
            f"{self.base_url}/rest/v1/profiles"
            f"?id=eq.{user_id}"
            f"&select=id,display_name,height_in,height_z,position,"
            f"dominant_hand,primary_skill,created_at,updated_at"
            f"&limit=1"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Profile fetch failed: {response.status_code} {response.text}")
            rows = response.json()
            return rows[0] if rows else None

    async def update_profile(self, user_id: str, patch: dict) -> dict:
        url = f"{self.base_url}/rest/v1/profiles?id=eq.{user_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.patch(
                url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=patch,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Profile update failed: {response.status_code} {response.text}")
            data = response.json()
            return data[0] if isinstance(data, list) else data

    async def list_done_clip_features_for_user(self, user_id: str) -> list[dict]:
        """Join done clips → clip_features for aggregation."""
        clips_url = (
            f"{self.base_url}/rest/v1/clips"
            f"?user_id=eq.{user_id}&status=eq.done&select=id"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            clips_resp = await client.get(clips_url, headers=self.headers)
            if clips_resp.status_code >= 400:
                raise RuntimeError(
                    f"Clip list for agg failed: {clips_resp.status_code} {clips_resp.text}"
                )
            clips = clips_resp.json()
            if not clips:
                return []

            ids = ",".join(f'"{c["id"]}"' for c in clips)
            feats_url = (
                f"{self.base_url}/rest/v1/clip_features"
                f"?clip_id=in.({ids})&select=clip_id,feature_name,value,created_at"
            )
            feats_resp = await client.get(feats_url, headers=self.headers)
            if feats_resp.status_code >= 400:
                raise RuntimeError(
                    f"Feature list for agg failed: {feats_resp.status_code} {feats_resp.text}"
                )
            return feats_resp.json()

    async def list_feature_history_for_user(self, user_id: str) -> list[dict]:
        """Per-clip feature rows with clip metadata for history charts."""
        clips_url = (
            f"{self.base_url}/rest/v1/clips"
            f"?user_id=eq.{user_id}&status=eq.done"
            f"&select=id,clip_type,created_at&order=created_at.asc"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            clips_resp = await client.get(clips_url, headers=self.headers)
            if clips_resp.status_code >= 400:
                raise RuntimeError(
                    f"History clip list failed: {clips_resp.status_code} {clips_resp.text}"
                )
            clips = clips_resp.json()
            if not clips:
                return []

            clip_meta = {c["id"]: c for c in clips}
            ids = ",".join(f'"{c["id"]}"' for c in clips)
            feats_url = (
                f"{self.base_url}/rest/v1/clip_features"
                f"?clip_id=in.({ids})"
                f"&select=clip_id,feature_name,value,created_at"
                f"&order=created_at.asc"
            )
            feats_resp = await client.get(feats_url, headers=self.headers)
            if feats_resp.status_code >= 400:
                raise RuntimeError(
                    f"History feature list failed: {feats_resp.status_code} {feats_resp.text}"
                )
            rows = []
            for feat in feats_resp.json():
                meta = clip_meta.get(feat["clip_id"], {})
                rows.append(
                    {
                        "clip_id": feat["clip_id"],
                        "clip_type": meta.get("clip_type", "unknown"),
                        "feature_name": feat["feature_name"],
                        "value": feat["value"],
                        "created_at": meta.get("created_at") or feat["created_at"],
                    }
                )
            return rows

    async def replace_user_profile_agg(self, user_id: str, rows: list[dict]) -> list[dict]:
        delete_url = f"{self.base_url}/rest/v1/user_profiles_agg?user_id=eq.{user_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            delete_resp = await client.delete(delete_url, headers=self.headers)
            if delete_resp.status_code >= 400:
                raise RuntimeError(
                    f"Agg delete failed: {delete_resp.status_code} {delete_resp.text}"
                )
            if not rows:
                return []
            payload = [
                {
                    "user_id": user_id,
                    "feature_name": row["feature_name"],
                    "value": row["value"],
                    "clip_count": row["clip_count"],
                }
                for row in rows
            ]
            insert_url = f"{self.base_url}/rest/v1/user_profiles_agg"
            insert_resp = await client.post(
                insert_url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=payload,
            )
            if insert_resp.status_code >= 400:
                raise RuntimeError(
                    f"Agg insert failed: {insert_resp.status_code} {insert_resp.text}"
                )
            data = insert_resp.json()
            return data if isinstance(data, list) else [data]

    async def list_user_profile_agg(self, user_id: str) -> list[dict]:
        url = (
            f"{self.base_url}/rest/v1/user_profiles_agg"
            f"?user_id=eq.{user_id}&order=feature_name.asc"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(f"Agg list failed: {response.status_code} {response.text}")
            return response.json()

    async def delete_clip_features(self, clip_id: str) -> None:
        url = f"{self.base_url}/rest/v1/clip_features?clip_id=eq.{clip_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.delete(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip feature delete failed: {response.status_code} {response.text}"
                )

    async def insert_clip_features(self, rows: list[dict]) -> None:
        if not rows:
            return
        url = f"{self.base_url}/rest/v1/clip_features"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Prefer": "return=minimal"},
                json=rows,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip feature insert failed: {response.status_code} {response.text}"
                )

    async def list_clip_features(self, clip_id: str) -> list[dict]:
        url = (
            f"{self.base_url}/rest/v1/clip_features"
            f"?clip_id=eq.{clip_id}&order=feature_name.asc"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip feature list failed: {response.status_code} {response.text}"
                )
            return response.json()

    async def insert_clip_events(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        url = f"{self.base_url}/rest/v1/clip_events"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=rows,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip event insert failed: {response.status_code} {response.text}"
                )
            data = response.json()
            return data if isinstance(data, list) else [data]

    async def delete_clip_events(self, clip_id: str) -> None:
        url = f"{self.base_url}/rest/v1/clip_events?clip_id=eq.{clip_id}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.delete(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip event delete failed: {response.status_code} {response.text}"
                )

    async def list_clip_events(
        self,
        clip_id: str | None = None,
        *,
        user_id: str | None = None,
        gate_passed: bool | None = None,
    ) -> list[dict]:
        url = f"{self.base_url}/rest/v1/clip_events?select=*&order=created_at.asc"
        if clip_id:
            url += f"&clip_id=eq.{clip_id}"
        if user_id:
            url += f"&user_id=eq.{user_id}"
        if gate_passed is not None:
            url += f"&gate_passed=eq.{str(gate_passed).lower()}"
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Clip event list failed: {response.status_code} {response.text}"
                )
            return response.json()

    async def upsert_user_role_profile(self, row: dict) -> dict:
        url = (
            f"{self.base_url}/rest/v1/user_role_profile"
            f"?on_conflict=user_id"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={
                    **self.headers,
                    "Prefer": "return=representation,resolution=merge-duplicates",
                },
                json=row,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"User role profile upsert failed: {response.status_code} {response.text}"
                )
            data = response.json()
            return data[0] if isinstance(data, list) else data

    async def get_user_role_profile(self, user_id: str) -> dict | None:
        url = (
            f"{self.base_url}/rest/v1/user_role_profile"
            f"?user_id=eq.{user_id}&limit=1"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"User role profile fetch failed: {response.status_code} {response.text}"
                )
            rows = response.json()
            return rows[0] if rows else None

    async def list_nba_players(self, season: str | None = None) -> list[dict]:
        url = (
            f"{self.base_url}/rest/v1/nba_players"
            f"?select=id,player_id,name,season,season_type,position,position_group,height_in,"
            f"style_vector,role_vector,raw_stats,raw_source,cohort_percentiles,"
            f"catch_shoot_fga,pull_up_fga,catch_shoot_share,drives,touches,drives_per_touch,"
            f"rim_attempt_share,passes,potential_assists,passes_per_touch,"
            f"potential_assists_per_pass,potential_assists_per_touch,assist_pct,"
            f"minutes,possessions,meets_min_sample,transform_version,seeded_at,created_at"
            f"&order=name.asc"
        )
        if season:
            url += f"&season=eq.{season}"
        async with httpx.AsyncClient(timeout=60.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"NBA player list failed: {response.status_code} {response.text}"
                )
            return response.json()

    async def replace_nba_players_for_season(self, season: str, rows: list[dict]) -> list[dict]:
        delete_url = f"{self.base_url}/rest/v1/nba_players?season=eq.{season}"
        async with httpx.AsyncClient(timeout=120.0, verify=certifi.where()) as client:
            delete_resp = await client.delete(delete_url, headers=self.headers)
            if delete_resp.status_code >= 400:
                raise RuntimeError(
                    f"NBA player delete failed: {delete_resp.status_code} {delete_resp.text}"
                )
            if not rows:
                return []

            payload = [
                {
                    "player_id": row["player_id"],
                    "name": row["name"],
                    "season": season,
                    "season_type": row.get("season_type") or "Regular Season",
                    "position": row["position"],
                    "position_group": row.get("position_group") or row["position"],
                    "height_in": row["height_in"],
                    "style_vector": {},
                    "role_vector": row.get("role_vector") or {},
                    "raw_stats": row.get("raw_stats") or {},
                    "raw_source": row.get("raw_source") or {},
                    "cohort_percentiles": row.get("cohort_percentiles") or {},
                    "catch_shoot_fga": row.get("catch_shoot_fga"),
                    "pull_up_fga": row.get("pull_up_fga"),
                    "catch_shoot_share": row.get("catch_shoot_share"),
                    "drives": row.get("drives"),
                    "touches": row.get("touches"),
                    "drives_per_touch": row.get("drives_per_touch"),
                    "rim_attempt_share": row.get("rim_attempt_share"),
                    "passes": row.get("passes"),
                    "potential_assists": row.get("potential_assists"),
                    "passes_per_touch": row.get("passes_per_touch"),
                    "potential_assists_per_pass": row.get("potential_assists_per_pass"),
                    "potential_assists_per_touch": row.get("potential_assists_per_touch"),
                    "assist_pct": row.get("assist_pct"),
                    "minutes": row.get("minutes"),
                    "possessions": row.get("possessions"),
                    "meets_min_sample": bool(row.get("meets_min_sample")),
                    "transform_version": row.get("transform_version"),
                    "seeded_at": row.get("seeded_at"),
                }
                for row in rows
            ]
            # PostgREST prefers chunked inserts for large payloads
            saved: list[dict] = []
            chunk_size = 100
            insert_url = f"{self.base_url}/rest/v1/nba_players"
            for i in range(0, len(payload), chunk_size):
                chunk = payload[i : i + chunk_size]
                insert_resp = await client.post(
                    insert_url,
                    headers={**self.headers, "Prefer": "return=representation"},
                    json=chunk,
                )
                if insert_resp.status_code >= 400:
                    raise RuntimeError(
                        f"NBA player insert failed: {insert_resp.status_code} {insert_resp.text}"
                    )
                data = insert_resp.json()
                if isinstance(data, list):
                    saved.extend(data)
                else:
                    saved.append(data)
            return saved

    async def insert_comp_result(
        self,
        user_id: str,
        matches: dict,
        summary: str | None = None,
        *,
        audit: dict | None = None,
    ) -> dict:
        url = f"{self.base_url}/rest/v1/comp_results"
        payload: dict = {
            "user_id": user_id,
            "matches": matches,
            "summary": summary,
        }
        if audit:
            payload.update({k: v for k, v in audit.items() if v is not None})
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.post(
                url,
                headers={**self.headers, "Prefer": "return=representation"},
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Comp result insert failed: {response.status_code} {response.text}"
                )
            data = response.json()
            return data[0] if isinstance(data, list) else data

    async def get_latest_comp_result(self, user_id: str) -> dict | None:
        url = (
            f"{self.base_url}/rest/v1/comp_results"
            f"?user_id=eq.{user_id}"
            f"&select=id,user_id,matches,summary,created_at,"
            f"comparison_mode,evidence_tier,profile_version,nba_seed_version,"
            f"mechanics_recs,role_recs,archetype_result,candidate_results"
            f"&order=created_at.desc&limit=1"
        )
        async with httpx.AsyncClient(timeout=30.0, verify=certifi.where()) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Comp result fetch failed: {response.status_code} {response.text}"
                )
            rows = response.json()
            return rows[0] if rows else None
