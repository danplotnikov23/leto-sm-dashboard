from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent


def _read_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value

    return None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    upload_dir: Path
    database_path: Path
    unit_economy_workbook_path: Path
    unit_economy_workbook_versions: str | None
    unit_economy_versions_dir: Path
    ozon_accruals_report_path: Path
    cors_origins: list[str]
    ozon_seller_base_url: str
    ozon_seller_client_id: str | None
    ozon_seller_api_key: str | None
    ozon_performance_base_url: str
    ozon_performance_client_id: str | None
    ozon_performance_client_secret: str | None
    request_timeout_seconds: float
    health_timeout_seconds: float
    request_retry_count: int
    ozon_report_wait_attempts: int
    ozon_report_wait_interval_seconds: float
    ozon_report_job_timeout_seconds: float

    @property
    def seller_credentials_configured(self) -> bool:
        return bool(self.ozon_seller_client_id and self.ozon_seller_api_key)

    @property
    def performance_credentials_configured(self) -> bool:
        return bool(
            self.ozon_performance_client_id and self.ozon_performance_client_secret
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _read_env_file(BASE_DIR / ".env")

    default_unit_workbook = PROJECT_DIR / "uploads" / "Юнит экономика 29.07.26.xlsx"
    default_unit_versions = ",".join(
        (
            (
                "2026-05-12="
                f"{PROJECT_DIR / 'uploads' / 'Юнит экономика 12.05.2026.xlsx'}="
                "12.05.2026"
            ),
            (
                "2026-06-17="
                f"{PROJECT_DIR / 'uploads' / 'Юнит экономика 15.06.26.xlsx'}="
                "15.06.26"
            ),
            f"2026-07-31={default_unit_workbook}=31.07.26",
        )
    )

    return Settings(
        upload_dir=Path(os.getenv("UPLOAD_DIR", str(PROJECT_DIR / "uploads"))),
        database_path=Path(
            os.getenv("DATABASE_PATH", str(PROJECT_DIR / "data" / "leto_sm.sqlite3"))
        ),
        unit_economy_workbook_path=Path(
            os.getenv(
                "UNIT_ECONOMY_WORKBOOK_PATH",
                str(default_unit_workbook),
            )
        ),
        unit_economy_workbook_versions=os.getenv(
            "UNIT_ECONOMY_WORKBOOK_VERSIONS",
            default_unit_versions,
        ),
        unit_economy_versions_dir=Path(
            os.getenv(
                "UNIT_ECONOMY_VERSIONS_DIR",
                str(PROJECT_DIR / "uploads" / "unit-economy-versions"),
            )
        ),
        ozon_accruals_report_path=Path(
            os.getenv(
                "OZON_ACCRUALS_REPORT_PATH",
                str(PROJECT_DIR / "uploads" / "Отчет по начислениям_01.04.2026-30.04.2026.xlsx"),
            )
        ),
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS", "*")) or ["*"],
        ozon_seller_base_url=os.getenv(
            "OZON_SELLER_BASE_URL", "https://api-seller.ozon.ru"
        ).rstrip("/"),
        ozon_seller_client_id=_first_env("OZON_SELLER_CLIENT_ID", "OZON_CLIENT_ID"),
        ozon_seller_api_key=_first_env("OZON_SELLER_API_KEY", "OZON_API_KEY"),
        ozon_performance_base_url=os.getenv(
            "OZON_PERFORMANCE_BASE_URL", "https://api-performance.ozon.ru"
        ).rstrip("/"),
        ozon_performance_client_id=os.getenv("OZON_PERFORMANCE_CLIENT_ID"),
        ozon_performance_client_secret=os.getenv("OZON_PERFORMANCE_CLIENT_SECRET"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        health_timeout_seconds=float(os.getenv("HEALTH_TIMEOUT_SECONDS", "5")),
        request_retry_count=int(os.getenv("REQUEST_RETRY_COUNT", "2")),
        ozon_report_wait_attempts=int(os.getenv("OZON_REPORT_WAIT_ATTEMPTS", "90")),
        ozon_report_wait_interval_seconds=float(
            os.getenv("OZON_REPORT_WAIT_INTERVAL_SECONDS", "10")
        ),
        ozon_report_job_timeout_seconds=float(
            os.getenv("OZON_REPORT_JOB_TIMEOUT_SECONDS", "3600")
        ),
    )
