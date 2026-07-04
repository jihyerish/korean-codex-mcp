from __future__ import annotations

from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from .client import KoreanLawClient, LawApiError
from .normalize import filter_articles, trim_article
from .settings import get_settings


DocumentType = Literal["law", "administrative_rule", "local_ordinance"]
QuestionScope = Literal["law", "administrative_rule", "local_ordinance", "all"]
KeyType = Literal["mst", "id"]

TARGETS: dict[str, str] = {
    "law": "eflaw",
    "administrative_rule": "admrul",
    "local_ordinance": "ordin",
}

SCOPE_TARGETS: dict[str, list[str]] = {
    "law": ["eflaw"],
    "administrative_rule": ["admrul"],
    "local_ordinance": ["ordin"],
    "all": ["eflaw", "admrul", "ordin"],
}

TARGET_NAMES: dict[str, str] = {
    "eflaw": "현행법령",
    "admrul": "행정규칙",
    "ordin": "자치법규",
}


def create_mcp() -> FastMCP:
    settings = get_settings()
    auth = None
    if settings.mcp_auth_token:
        auth = StaticTokenVerifier(
            tokens={settings.mcp_auth_token: {"sub": "law-mcp-user", "client_id": "law-mcp"}}
        )

    mcp = FastMCP(
        "Korean Law Open API",
        instructions=(
            "Use this server to search Korean statutes, administrative rules, and local ordinances "
            "from the Ministry of Government Legislation Open API. Return answers with cited source "
            "articles and remind users that results are for reference, not legal advice."
        ),
        auth=auth,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        current_settings = get_settings()
        return JSONResponse(
            {
                "status": "ok",
                "service": "korean-law-mcp",
                "law_api_configured": bool(current_settings.law_api_oc),
            }
        )

    @mcp.tool
    async def search_legal_documents(
        query: Annotated[str, Field(description="Korean keyword or law title to search.")],
        document_type: Annotated[
            DocumentType,
            Field(description="Document category to search."),
        ] = "law",
        page: Annotated[int, Field(ge=1, le=100, description="Search page number.")] = 1,
        limit: Annotated[int, Field(ge=1, le=100, description="Maximum items to return.")] = 10,
        effective_date: Annotated[
            str | None,
            Field(description="Optional effective date as YYYYMMDD for current law search."),
        ] = None,
    ) -> dict[str, Any]:
        """Search Korean legal documents and return IDs that can be used for detail lookup."""
        client = KoreanLawClient()
        target = TARGETS[document_type]
        try:
            return await client.search_documents(
                query=query,
                target=target,
                page=page,
                limit=limit,
                effective_date=effective_date,
            )
        except LawApiError as exc:
            return {"error": str(exc), "query": query, "document_type": document_type}

    @mcp.tool
    async def get_legal_document_detail(
        document_key: Annotated[
            str,
            Field(description="Document MST or ID value returned by search_legal_documents."),
        ],
        document_type: Annotated[
            DocumentType,
            Field(description="Document category for the key."),
        ] = "law",
        key_type: Annotated[
            KeyType,
            Field(description="Use 'mst' for serial number, or 'id' for document ID."),
        ] = "mst",
        article_query: Annotated[
            str | None,
            Field(description="Optional keywords to return only relevant articles."),
        ] = None,
        max_articles: Annotated[
            int,
            Field(ge=1, le=100, description="Maximum articles to include in the response."),
        ] = 30,
        include_raw: Annotated[
            bool,
            Field(description="Include original parsed XML payload. Usually false because it can be large."),
        ] = False,
    ) -> dict[str, Any]:
        """Fetch a legal document body and return normalized article text."""
        client = KoreanLawClient()
        target = TARGETS[document_type]
        try:
            detail = await client.get_document_detail(
                target=target,
                document_key=document_key,
                key_type=key_type,
            )
            articles = filter_articles(detail.get("articles", []), article_query, max_articles)
            detail["articles"] = [trim_article(article) for article in articles]
            detail["article_count_returned"] = len(detail["articles"])
            if not include_raw:
                detail.pop("raw", None)
            return detail
        except LawApiError as exc:
            return {
                "error": str(exc),
                "document_key": document_key,
                "document_type": document_type,
                "key_type": key_type,
            }

    async def find_relevant_articles_impl(
        question_or_keywords: str,
        law_name: str | None = None,
        scope: QuestionScope = "all",
        max_documents: int = 3,
        max_articles: int = 6,
    ) -> dict[str, Any]:
        client = KoreanLawClient()
        query = law_name or question_or_keywords
        found: list[dict[str, Any]] = []
        errors: list[str] = []

        for target in SCOPE_TARGETS[scope]:
            try:
                search_result = await client.search_documents(query=query, target=target, limit=max_documents)
            except LawApiError as exc:
                errors.append(f"{TARGET_NAMES.get(target, target)}: {exc}")
                continue

            for item in search_result.get("items", [])[:max_documents]:
                document_key = item.get("document_key")
                key_type = item.get("key_type") or "mst"
                if not document_key:
                    continue
                try:
                    detail = await client.get_document_detail(
                        target=target,
                        document_key=document_key,
                        key_type=key_type,
                    )
                except LawApiError as exc:
                    errors.append(f"{item.get('title') or document_key}: {exc}")
                    continue

                articles = filter_articles(
                    detail.get("articles", []),
                    question_or_keywords,
                    max_articles,
                )
                if articles:
                    found.append(
                        {
                            "document_type": TARGET_NAMES.get(target, target),
                            "title": detail.get("title") or item.get("title"),
                            "document_key": document_key,
                            "key_type": key_type,
                            "ministry": detail.get("ministry") or item.get("ministry"),
                            "effective_date": detail.get("effective_date") or item.get("effective_date"),
                            "detail_url": item.get("detail_url"),
                            "articles": [trim_article(article) for article in articles],
                        }
                    )

        return {
            "question": question_or_keywords,
            "search_query": query,
            "scope": scope,
            "results": found[:max_documents],
            "errors": errors,
            "notice": "This is source retrieval for reference and is not legal advice.",
        }

    @mcp.tool
    async def find_relevant_articles(
        question_or_keywords: Annotated[
            str,
            Field(description="User question or keywords to match against article text."),
        ],
        law_name: Annotated[
            str | None,
            Field(description="Optional law or regulation title. If omitted, the question is searched."),
        ] = None,
        scope: Annotated[
            QuestionScope,
            Field(description="Search statutes, regulations, ordinances, or all categories."),
        ] = "all",
        max_documents: Annotated[
            int,
            Field(ge=1, le=5, description="Maximum documents to inspect."),
        ] = 3,
        max_articles: Annotated[
            int,
            Field(ge=1, le=20, description="Maximum relevant articles to return."),
        ] = 6,
    ) -> dict[str, Any]:
        """Search documents and return article snippets that look relevant to the user's question."""
        return await find_relevant_articles_impl(
            question_or_keywords=question_or_keywords,
            law_name=law_name,
            scope=scope,
            max_documents=max_documents,
            max_articles=max_articles,
        )

    @mcp.tool
    async def answer_legal_question(
        question: Annotated[
            str,
            Field(description="User's Korean legal or regulatory question."),
        ],
        law_name: Annotated[
            str | None,
            Field(description="Optional known law/regulation title, e.g. 근로기준법."),
        ] = None,
        scope: Annotated[
            QuestionScope,
            Field(description="Search statutes, administrative rules, local ordinances, or all."),
        ] = "all",
        max_sources: Annotated[
            int,
            Field(ge=1, le=8, description="Maximum article sources to include in the answer draft."),
        ] = 5,
    ) -> dict[str, Any]:
        """Return a concise Korean answer draft with source article excerpts."""
        article_result = await find_relevant_articles_impl(
            question_or_keywords=question,
            law_name=law_name,
            scope=scope,
            max_documents=3,
            max_articles=max_sources,
        )

        sources: list[dict[str, Any]] = []
        for document in article_result.get("results", []):
            for article in document.get("articles", []):
                sources.append(
                    {
                        "document_type": document.get("document_type"),
                        "title": document.get("title"),
                        "article": article.get("label"),
                        "effective_date": article.get("effective_date") or document.get("effective_date"),
                        "content": article.get("content"),
                        "detail_url": document.get("detail_url"),
                    }
                )
                if len(sources) >= max_sources:
                    break
            if len(sources) >= max_sources:
                break

        if not sources:
            return {
                "question": question,
                "answer": (
                    "관련 법령 조문을 찾지 못했습니다. 법령명이나 규제명을 더 구체적으로 입력하면 "
                    "다시 검색할 수 있습니다."
                ),
                "sources": [],
                "notice": "법률 자문이 아닌 참고용 응답입니다.",
                "retrieval": article_result,
            }

        source_lines = []
        for index, source in enumerate(sources, start=1):
            title = source.get("title") or "문서명 미상"
            article = source.get("article") or "관련 조문"
            content = source.get("content") or ""
            source_lines.append(f"{index}. {title} {article}: {content}")

        answer = (
            "아래 조문들이 질문과 가장 관련 있어 보입니다. 정확한 적용 여부는 사실관계, 시행일, "
            "예외 조항에 따라 달라질 수 있습니다.\n\n"
            + "\n\n".join(source_lines)
            + "\n\n정리하면, 위 근거 조문을 중심으로 답해야 하며 최종 판단은 최신 원문과 "
            "구체적 사실관계를 함께 확인해야 합니다."
        )

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
            "notice": "법률 자문이 아닌 참고용 응답입니다.",
        }

    @mcp.tool
    async def call_law_open_api_raw(
        endpoint: Annotated[
            Literal["lawSearch.do", "lawService.do"],
            Field(description="Open Law API endpoint to call."),
        ],
        params: Annotated[
            dict[str, Any],
            Field(description="Request parameters except OC and type. They are added by the server."),
        ],
    ) -> dict[str, Any]:
        """Low-level read-only access to supported Open Law API endpoints."""
        client = KoreanLawClient()
        try:
            return await client.raw_call(endpoint=endpoint, params=params)
        except LawApiError as exc:
            return {"error": str(exc), "endpoint": endpoint, "params": params}

    return mcp


mcp = create_mcp()
app = mcp.http_app(stateless_http=get_settings().stateless_http)
