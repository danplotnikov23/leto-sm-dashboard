# Ozon References Checked

Дата проверки: 2026-06-17.

Использованные публичные справочные источники:

- Бонусы продавца: https://docs.ozon.ru/common/aktsii-bally-i-bonusy/seller-bonuses/
- Аналитика акций: https://docs.ozon.ru/global/en/analytics/analytics-and-metrics/promo/
- Мультивалютность и методы Seller API с ценами: https://docs.ozon.ru/global/en/accounting/receiving-payments/multicurrency/
- Раздел комиссий и тарифов: https://docs.ozon.ru/global/am/commissions/ozon-fees/
- Калькулятор прибыли и расходов: https://docs.ozon.ru/global/tr/commissions/ozon-fees/online-calculator/
- Расходы на доставку FBS: https://seller-edu.ozon.ru/libra/commissions-tariffs/commissions-tariffs-ozon/rashody-na-dostavku-cherez-ozon-logistiku

Официальная выгрузка пользователя:

- `Таблица категорий для расчёта вознаграждения 01062026` — ставки FBS по типу товара и диапазонам цены до 100 ₽, 100–300 ₽ и свыше 300 ₽. В приложение включена нормализованная версия `backend/app/data/ozon_fbs_commissions_2026_06_01.json.gz`.

Вывод для архитектуры:

- Баллы за скидки считаются отдельно от обычной скидки и могут быть положительным начислением по отчету Ozon.
- Акции и промокоды должны хранить источник и период действия, потому что скидка может отличаться от видимой покупателю.
- Комиссия FBS берется из официальной выгрузки, когда тип товара сопоставлен. Несопоставленные типы и логистика помечаются как `estimate`.
- Для FBS хранение Ozon равно нулю. Упаковка и обработка внешним фулфилментом не относятся к услугам Ozon и считаются отдельно.
- Ozon сам описывает калькулятор как предварительный инструмент, поэтому production-расчеты должны сверяться с официальными тарифами, отчетами кабинета и фактическими начислениями.
