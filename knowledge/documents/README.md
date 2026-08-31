# General RAG Knowledge Documents

설계변경 Rule/Reason 이외의 비정형 지식 문서를 관리하는 위치입니다.

지원 형식:

- Markdown (`.md`)
- Text (`.txt`)
- Word (`.docx`)
- text-based PDF (`.pdf`)

## Markdown metadata

Markdown 문서는 파일 맨 앞에 TOML Front Matter를 둡니다.

```toml
+++
document_id = "DG-001"
document_title = "Drive IC Replacement Design Guide"
document_type = "DESIGN_GUIDE"
version = "1.0"
effective_date = "2026-08-31"
status = "ACTIVE"
language = "KO"
product_families = ["LCD"]
material_types = ["DRIVE-IC"]
tags = ["DESIGN_CHANGE", "DRIVE-IC"]

[attributes]
owner = "DISPLAY_ENGINEERING"
+++
```

## TXT / DOCX / PDF metadata

원본 파일을 수정하지 않기 위해 동일한 파일명 stem의 `.meta.toml` sidecar를 사용합니다.

예:

```text
supplier_qualification.pdf
supplier_qualification.meta.toml
```

`.meta.toml`에는 Markdown Front Matter와 동일한 metadata 필드를 작성합니다.

## Document types

- `DESIGN_GUIDE`
- `MATERIAL_SPEC`
- `PROCESS_GUIDE`
- `CHANGE_POLICY`
- `SUPPLIER_TECHNICAL`
- `FAQ`

`CHANGE_RULE`, `CHANGE_REASON`은 각각 `knowledge/rules`, `knowledge/reasons`에서 자동으로 RAG corpus에 포함됩니다.

실제 사내/보안 문서는 `knowledge/documents/private/`에 두며 Git에 commit하지 않습니다.
스캔 이미지 PDF OCR은 현재 범위에 포함하지 않습니다.
