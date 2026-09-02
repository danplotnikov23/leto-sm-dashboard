from app.core.config import Settings
from app.services.ozon_client import OzonClientFactory, OzonPerformanceClientFactory


def test_ozon_status_masks_missing_credentials() -> None:
    status = OzonClientFactory(Settings(ozon_client_id=None, ozon_api_key=None)).status()

    assert status.configured is False
    assert status.client_id_masked is None
    assert status.account_label == "Аллея мебели"
    assert status.usage_mode == "benchmark_account"
    assert "OZON_CLIENT_ID" in status.message


def test_ozon_status_masks_configured_client_id() -> None:
    status = OzonClientFactory(Settings(ozon_client_id="12345678", ozon_api_key="secret")).status()

    assert status.configured is True
    assert status.client_id_masked == "12***78"
    assert "Аллея мебели" in status.data_scope_warning


def test_ozon_factory_refuses_missing_credentials() -> None:
    factory = OzonClientFactory(Settings(ozon_client_id="", ozon_api_key=""))

    try:
        factory.create()
    except RuntimeError as error:
        assert "Ozon API не настроен" in str(error)
    else:
        raise AssertionError("factory.create() must fail without credentials")


def test_ozon_client_builds_product_list_payload() -> None:
    client = OzonClientFactory(Settings(ozon_client_id="12345678", ozon_api_key="secret")).create()

    assert client.base_url == "https://api-seller.ozon.ru"


def test_ozon_performance_status_masks_configured_client_id() -> None:
    status = OzonPerformanceClientFactory(
        Settings(
            ozon_performance_client_id="abcd-12345678",
            ozon_performance_client_secret="secret",
        )
    ).status()

    assert status.configured is True
    assert status.client_id_masked == "abcd***5678"
