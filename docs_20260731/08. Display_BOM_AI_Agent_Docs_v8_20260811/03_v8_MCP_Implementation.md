# v8 MCP Implementation

## 1. 구현 결과
Python `mcp[cli]`를 설치하고 Display BOM MCP Server/Client를 구성했다.

### 개발 과정에서 확인한 사항
- MCP 자체 사용에 Node.js는 필수가 아니다.
- `mcp dev`의 Inspector 실행에는 Node.js/npx가 필요하지만 프로젝트 Runtime에는 필요하지 않아 설치하지 않았다.
- 프로젝트에서는 Python MCP SDK + stdio 통신을 사용한다.

## 2. 현재 호출 흐름
```text
Agent
 ↓
DisplayBomMcpClient
 ↓
stdio_client
 ↓
ClientSession.initialize()
 ↓
session.call_tool()
 ↓
MCP Server Tool
 ↓
BomService
```

## 3. 검증된 Capability
- BOM 조회
- 제품 검색/목록
- 자재 검색/목록

MCP Tool 결과를 Python list/dict 형태로 Agent가 사용할 수 있도록 Client 계층을 구성했다.

## 4. 구현 중 해결한 주요 이슈
- 프로젝트 package import 경로 문제
- MCP SDK의 `inputSchema`가 아닌 `input_schema` 속성 사용
- MCP Tool argument와 Service method parameter 불일치 수정
- MCP Inspector를 Runtime 필수 구성으로 오해하지 않도록 개발/실행 경로 분리

## 5. 설계 원칙
MCP Tool 내부에 Business Rule을 새로 만들지 않는다.

```text
MCP = 무엇을 호출할 수 있는가
Service = 실제로 어떻게 처리하는가
Skill = 언제/어떤 순서로 호출하는가
```
