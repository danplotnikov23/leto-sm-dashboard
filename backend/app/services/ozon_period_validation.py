from datetime import date, datetime
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def get_moscow_today() -> date:
    return datetime.now(tz=MOSCOW_TZ).date()


def validate_ozon_report_period(date_from: str, date_to: str) -> None:
    try:
        parsed_date_from = date.fromisoformat(date_from)
        parsed_date_to = date.fromisoformat(date_to)
    except ValueError as exc:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD") from exc

    if parsed_date_from > parsed_date_to:
        raise ValueError("Дата начала не может быть позже даты окончания")

    today = get_moscow_today()
    if parsed_date_from > today or parsed_date_to > today:
        formatted_today = today.strftime("%d.%m.%Y")
        raise ValueError(
            "Нельзя строить Ozon-отчёт за будущие даты. "
            f"Выбери период не позже {formatted_today}."
        )
