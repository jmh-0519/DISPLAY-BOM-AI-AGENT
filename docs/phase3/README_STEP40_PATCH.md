# STEP40 Patch Apply

이 패치는 STEP39/STEP38-B 적용 기준이다.

## 중요

사용자가 `app/views/phase3_agent_view.py`의 APPLY 안내 문구를 직접 수정했으므로,
이 패치에는 해당 UI 파일 전체를 포함하지 않는다.

ZIP의 파일을 프로젝트 루트에 덮어쓴 뒤 다음 명령으로 STEP40 UI 변경만 병합한다.

```powershell
python -m scripts.apply_step40_ui_patch
```

스크립트는 idempotent하며 사용자가 수정한 APPLY 안내 문구를 변경하지 않는다.

그 다음:

```powershell
python -m scripts.run_tests -q
```
