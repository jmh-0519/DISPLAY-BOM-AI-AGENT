import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    애플리케이션 환경설정을 관리합니다.

    API Key와 같은 민감정보는 코드에 직접 작성하지 않고
    .env 파일 또는 운영환경의 환경변수에서 읽습니다.
    """

    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_api_version: str
    azure_openai_deployment: str

    @classmethod
    def from_env(cls) -> "Settings":
        """
        환경변수에서 설정값을 읽고 Settings 객체를 생성합니다.

        Raises:
            ValueError: 필수 환경변수가 없거나 비어 있는 경우
        """

        values = {
            "azure_openai_api_key": os.getenv(
                "AZURE_OPENAI_API_KEY",
                "",
            ).strip(),
            "azure_openai_endpoint": os.getenv(
                "AZURE_OPENAI_ENDPOINT",
                "",
            ).strip(),
            "azure_openai_api_version": os.getenv(
                "AZURE_OPENAI_API_VERSION",
                "",
            ).strip(),
            "azure_openai_deployment": os.getenv(
                "AZURE_OPENAI_DEPLOYMENT",
                "",
            ).strip(),
        }

        missing_names = [
            name
            for name, value in values.items()
            if not value
        ]

        if missing_names:
            formatted_names = ", ".join(missing_names)

            raise ValueError(
                "필수 환경설정이 누락되었습니다: "
                f"{formatted_names}"
            )

        endpoint = values["azure_openai_endpoint"].rstrip("/")

        return cls(
            azure_openai_api_key=values[
                "azure_openai_api_key"
            ],
            azure_openai_endpoint=endpoint,
            azure_openai_api_version=values[
                "azure_openai_api_version"
            ],
            azure_openai_deployment=values[
                "azure_openai_deployment"
            ],
        )