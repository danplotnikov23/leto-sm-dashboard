class OzonConfigurationError(RuntimeError):
    pass


class OzonApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OzonReportNotReadyError(RuntimeError):
    def __init__(self, report_uuid: str, state: str) -> None:
        super().__init__(f"Ozon statistics report {report_uuid} is not ready: {state}")
        self.report_uuid = report_uuid
        self.state = state
