from __future__ import annotations

from typing import Any

import httpx
import xmltodict

from .normalize import normalize_detail_response, normalize_search_response
from .settings import Settings, get_settings


class LawApiError(RuntimeError):
    """Raised when the Korean Law Open API cannot return usable data."""


class KoreanLawClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _require_oc(self) -> str:
        if not self.settings.law_api_oc:
            raise LawApiError(
                "LAW_OPEN_API_OC is not set. Add your Open Law API OC code as an environment variable. "
                "LAW_API_OC is also supported for backward compatibility."
            )
        return self.settings.law_api_oc

    async def _get_xml(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = {
            "OC": self._require_oc(),
            "type": "XML",
            **{key: value for key, value in params.items() if value not in (None, "")},
        }
        url = f"{self.settings.law_api_base_url}/{endpoint.lstrip('/')}"
        timeout = httpx.Timeout(self.settings.law_api_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=request_params)

        if response.status_code >= 400:
            raise LawApiError(
                f"Open Law API request failed with HTTP {response.status_code}: {response.text[:300]}"
            )

        content = response.content.strip()
        if not content:
            raise LawApiError("Open Law API returned an empty response.")
        if b"<html" in content[:500].lower():
            raise LawApiError(
                "Open Law API returned an HTML page instead of XML. Check LAW_API_OC and requested API access."
            )

        try:
            parsed = xmltodict.parse(content)
        except Exception as exc:  # pragma: no cover - defensive for remote XML variants
            raise LawApiError(f"Open Law API returned invalid XML: {exc}") from exc

        if not isinstance(parsed, dict):
            raise LawApiError("Open Law API response could not be parsed as an XML document.")
        return parsed

    @staticmethod
    def _xml_error_message(parsed: dict[str, Any]) -> str | None:
        if len(parsed) != 1:
            return None
        body = next(iter(parsed.values()))
        if isinstance(body, str) and body.strip():
            return body.strip()
        return None

    async def search_documents(
        self,
        query: str,
        target: str = "eflaw",
        page: int = 1,
        limit: int = 10,
        effective_date: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "target": target,
            "query": query,
            "page": page,
            "display": limit,
            "efYd": effective_date,
        }
        parsed = await self._get_xml("lawSearch.do", params)
        return normalize_search_response(parsed, target=target, query=query, page=page, limit=limit)

    async def get_document_detail(
        self,
        target: str,
        document_key: str,
        key_type: str = "mst",
    ) -> dict[str, Any]:
        attempts: list[tuple[str, str]] = [(target, key_type)]
        if target == "eflaw" and key_type.lower() == "mst":
            attempts.append(("law", "mst"))
        if target == "admrul" and key_type.lower() == "mst":
            attempts.append(("admrul", "id"))

        last_error: str | None = None
        for attempt_target, attempt_key_type in attempts:
            try:
                return await self._get_document_detail_once(
                    target=attempt_target,
                    document_key=document_key,
                    key_type=attempt_key_type,
                )
            except LawApiError as exc:
                last_error = str(exc)

        raise LawApiError(last_error or "Open Law API detail lookup failed.")

    async def _get_document_detail_once(
        self,
        target: str,
        document_key: str,
        key_type: str = "mst",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"target": target}
        if key_type.lower() == "id":
            params["ID"] = document_key
        else:
            params["MST"] = document_key

        parsed = await self._get_xml("lawService.do", params)
        error_message = self._xml_error_message(parsed)
        if error_message:
            raise LawApiError(error_message)
        return normalize_detail_response(parsed, target=target)

    async def raw_call(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_endpoint = endpoint
        if normalized_endpoint not in {"lawSearch.do", "lawService.do"}:
            raise LawApiError("Only lawSearch.do and lawService.do are exposed by this MCP server.")
        return await self._get_xml(normalized_endpoint, params)
