# 용어 사전

## Agent

사용자 목표를 해석하고 필요한 Tool을 선택하며 실행 결과를 바탕으로 답변을 만드는 시스템 구성 요소.

## LLM

Large Language Model. 자연어 이해와 생성에 사용하는 대규모 언어 모델.

## Tool Calling

LLM이 미리 정의된 함수 또는 Tool의 이름과 인자를 구조화된 형태로 요청하는 방식.

## Tool

Agent가 사용할 수 있도록 공개된 명시적인 업무 기능. 이름, 설명, 입력 스키마, 실행 로직을 가진다.

## Tool Registry

사용 가능한 Tool을 등록하고 이름으로 조회하며, Tool 메타데이터를 제공하는 구성 요소.

## Tool Executor

Tool 호출을 검증하고 실행하며, 로깅과 예외 처리를 공통 적용하는 구성 요소.

## Service Layer

도메인 조회와 데이터 가공을 담당하며 상위 계층과 실제 데이터 소스를 분리하는 계층.

## Repository Pattern

도메인 로직이 DB나 파일 접근 구현에 직접 의존하지 않도록 저장소 접근 인터페이스를 분리하는 패턴.

## Dependency Injection

객체가 필요한 의존성을 내부에서 직접 만들지 않고 외부에서 전달받는 설계 방법.

## DTO

Data Transfer Object. 계층 사이에서 데이터를 구조화해 전달하기 위한 객체.

## Schema

입력 또는 출력 데이터의 필드, 타입, 필수 여부와 제약조건을 정의한 구조.

## Hallucination

LLM이 제공된 근거나 데이터에 없는 내용을 사실처럼 생성하는 현상.

## RAG

Retrieval-Augmented Generation. 외부 문서를 검색한 결과를 LLM의 문맥에 제공해 답변 정확도를 높이는 방식.

## Embedding

텍스트의 의미를 숫자 벡터로 표현하는 기법.

## MCP

Model Context Protocol. 모델과 외부 데이터 및 Tool을 표준화된 방식으로 연결하기 위한 프로토콜.

## BOM

Bill of Materials. 제품을 구성하는 조립품, 부품, 수량, 버전 등의 구조 정보.

## BOM Explosion

상위 제품부터 모든 하위 조립품과 부품을 다단계로 전개하는 조회.

## Where-Used

특정 자재가 어떤 상위 제품 또는 조립품에서 사용되는지 역방향으로 조회하는 기능.

## Lifecycle Status

자재의 개발, 승인, 양산, 단종 등의 생명주기 상태.

## ADR

Architecture Decision Record. 중요한 설계 결정의 배경, 대안, 선택, 결과를 기록한 문서.
