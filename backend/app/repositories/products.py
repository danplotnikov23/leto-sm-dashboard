from app.core.config import get_settings
from app.db.sqlite import SQLiteStore

repository = SQLiteStore(get_settings().database_url)

