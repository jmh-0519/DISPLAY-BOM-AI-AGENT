from __future__ import annotations

from dotenv import load_dotenv

from core.observability import (
    LangfuseObservability,
    summarize_text,
)


def main() -> int:
    load_dotenv()

    observability = LangfuseObservability()

    if not observability.enabled:
        print("Langfuse configuration: disabled or unavailable")
        return 1

    try:
        authenticated = observability.client.auth_check()
    except Exception as error:
        print(
            "Langfuse authentication: failed "
            f"({type(error).__name__})"
        )
        return 1

    if not authenticated:
        print("Langfuse authentication: failed")
        return 1

    print("Langfuse authentication: success")

    try:
        with observability.observe(
            "display-bom-agent-connection-test",
            input_summary=summarize_text(
                "synthetic connection test"
            ),
            metadata={
                "test": True,
                "contains_business_data": False,
            },
        ) as observation:
            if observation.delegate is None:
                print("Langfuse test trace: creation failed")
                return 1

            observation.finish(
                output={
                    "status": "SUCCESS",
                    "synthetic": True,
                }
            )

        observability.client.flush()
    except Exception as error:
        print(
            "Langfuse test trace: failed "
            f"({type(error).__name__})"
        )
        return 1

    print("Langfuse test trace: submitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())