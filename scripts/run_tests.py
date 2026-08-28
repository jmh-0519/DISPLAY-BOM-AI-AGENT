from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from scripts.test_suite_manifest import get_suite_files


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    temp_root = project_root / ".pytest_tmp_runtime"
    basetemp = temp_root / f"run-{uuid.uuid4().hex}"

    temp_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Python과 pytest가 사용자 Temp 폴더를 사용하지 않도록 설정합니다.
    os.environ["TEMP"] = str(temp_root)
    os.environ["TMP"] = str(temp_root)
    os.environ["TMPDIR"] = str(temp_root)

    # 테스트 중 실제 Langfuse 전송을 차단합니다.
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

    # pytest는 임시 디렉터리에 POSIX 0700 mode를 적용합니다. Windows의
    # managed sandbox에서는 이 chmod가 현재 Process의 재접근까지 막을 수
    # 있으므로 테스트 Process 안에서만 no-op으로 처리합니다.
    original_chmod = os.chmod
    original_mkdir = Path.mkdir
    if os.name == "nt":
        os.chmod = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        def sandbox_safe_mkdir(path, mode=0o777, parents=False, exist_ok=False):
            return original_mkdir(
                path,
                mode=0o777 if mode == 0o700 else mode,
                parents=parents,
                exist_ok=exist_ok,
            )
        Path.mkdir = sandbox_safe_mkdir  # type: ignore[method-assign]

    import pytest

    pytest_arguments = sys.argv[1:]

    suite_name = None
    normalized_arguments: list[str] = []
    index = 0
    while index < len(pytest_arguments):
        argument = pytest_arguments[index]
        if argument == "--suite":
            if index + 1 >= len(pytest_arguments):
                raise SystemExit("--suite requires a value: quick, core, evaluation, legacy, full")
            suite_name = pytest_arguments[index + 1]
            index += 2
            continue
        if argument.startswith("--suite="):
            suite_name = argument.split("=", 1)[1]
            index += 1
            continue
        normalized_arguments.append(argument)
        index += 1

    pytest_arguments = normalized_arguments

    if suite_name is not None:
        try:
            suite_files = get_suite_files(project_root, suite_name)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if suite_files:
            pytest_arguments = [*suite_files, *pytest_arguments]

    if not pytest_arguments:
        pytest_arguments = ["-q"]

    if not any(
        argument.startswith("--basetemp")
        for argument in pytest_arguments
    ):
        pytest_arguments.append(
            f"--basetemp={basetemp}"
        )

    if "-p" not in pytest_arguments and "no:cacheprovider" not in pytest_arguments:
        pytest_arguments.extend(["-p", "no:cacheprovider"])

    try:
        return pytest.main(pytest_arguments)
    finally:
        os.chmod = original_chmod
        Path.mkdir = original_mkdir  # type: ignore[method-assign]


if __name__ == "__main__":
    raise SystemExit(main())
