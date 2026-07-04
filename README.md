# Korean Law MCP Server

국가법령정보 공동활용(Open Law API)을 이용해 사용자의 법령/규제 질문에 필요한 근거 조문을 찾아 주는 FastMCP 서버입니다. Render에 바로 배포할 수 있도록 `render.yaml`, `Procfile`, `Dockerfile`을 함께 넣어 두었습니다.

공식 가이드 기준으로 목록 조회는 `lawSearch.do`, 본문 조회는 `lawService.do` 흐름을 사용합니다. MCP 엔드포인트는 `/mcp/`, 상태 확인은 `/health`입니다.

## 제공 도구

- `search_legal_documents`: 법령, 행정규칙, 자치법규 목록 검색
- `get_legal_document_detail`: 검색 결과의 `document_key`로 본문과 조문 조회
- `find_relevant_articles`: 질문과 관련 있어 보이는 조문 추출
- `answer_legal_question`: 관련 조문을 근거로 한국어 답변 초안 생성
- `call_law_open_api_raw`: `lawSearch.do`, `lawService.do`에 대한 저수준 조회

이 서버는 법률 자문을 대신하지 않습니다. MCP 클라이언트가 답변할 때도 반드시 원문, 시행일, 사실관계를 함께 확인해야 합니다.

## 1. API 키 준비

Open Law API 신청 후 받은 OC 코드를 환경변수로 넣습니다.

```bash
LAW_API_OC=신청한_OC_코드
```

원격 MCP 서버를 공개 URL에 올릴 때는 `MCP_AUTH_TOKEN`도 설정하는 것을 권장합니다.

```bash
MCP_AUTH_TOKEN=원하는_긴_토큰
```

토큰을 설정하면 MCP 클라이언트에서 `Authorization: Bearer <토큰>` 형태로 접속해야 합니다.

## 2. 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` 파일에 `LAW_API_OC` 값을 넣은 뒤 실행합니다.

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

확인:

```bash
curl http://localhost:8000/health
```

MCP URL:

```text
http://localhost:8000/mcp/
```

## 3. Render 배포

1. 이 폴더를 GitHub 저장소로 올립니다.
2. Render에서 **New +** → **Blueprint**를 선택하고 저장소를 연결합니다.
3. `render.yaml`이 자동으로 읽히면 환경변수를 설정합니다.

필수 환경변수:

```text
LAW_API_OC=신청한_OC_코드
```

권장 환경변수:

```text
MCP_AUTH_TOKEN=원하는_긴_토큰
```

배포 후 상태 확인:

```text
https://<render-service-name>.onrender.com/health
```

MCP 접속 URL:

```text
https://<render-service-name>.onrender.com/mcp/
```

## 4. MCP 클라이언트 연결 예시

원격 HTTP MCP를 지원하는 클라이언트에서 아래처럼 등록합니다.

```json
{
  "mcpServers": {
    "korean-law": {
      "url": "https://<render-service-name>.onrender.com/mcp/",
      "headers": {
        "Authorization": "Bearer <MCP_AUTH_TOKEN>"
      }
    }
  }
}
```

`MCP_AUTH_TOKEN`을 설정하지 않았다면 `headers` 부분은 생략할 수 있습니다. 다만 공개 배포에서는 토큰을 꼭 쓰는 편이 좋습니다.

## 5. 사용 예시

MCP 클라이언트에서 다음처럼 물어볼 수 있습니다.

```text
근로기준법상 연차유급휴가는 어떻게 계산해?
```

또는 법령명을 명시하면 검색 정확도가 더 좋아집니다.

```text
근로기준법에서 연차유급휴가 관련 조문 찾아줘.
```

행정규칙이나 자치법규까지 넓게 보고 싶다면 `answer_legal_question`의 `scope`를 `all`로 둡니다. 특정 범위만 보려면 `law`, `administrative_rule`, `local_ordinance` 중 하나를 사용합니다.

## 6. 주요 환경변수

| 이름 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `LAW_API_OC` | 예 | 없음 | Open Law API 신청 후 받은 OC 코드 |
| `LAW_API_BASE_URL` | 아니오 | `https://www.law.go.kr/DRF` | Open Law API 기본 주소 |
| `LAW_API_TIMEOUT_SECONDS` | 아니오 | `20` | API 요청 제한 시간 |
| `MCP_AUTH_TOKEN` | 아니오 | 없음 | 원격 MCP 접속 보호용 Bearer 토큰 |
| `FASTMCP_STATELESS_HTTP` | 아니오 | `true` | Render/확장 배포에 맞춘 Stateless HTTP 모드 |

## 7. 참고한 공식 문서

- [국가법령정보 공동활용 OPEN API 활용가이드](https://open.law.go.kr/LSO/openApi/guideList.do)
- [국가법령정보 공동활용 OPEN API 활용방법](https://open.law.go.kr/LSO/openApi/openApiManual.do)
- [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http)

