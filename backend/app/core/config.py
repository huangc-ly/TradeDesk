from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "TradeDesk API"
    debug: bool = True

    # Data paths — relative to project root
    project_root: Path = Path(__file__).resolve().parent.parent.parent.parent

    # Consolidated parquet files
    stock_daily: Path = project_root / "stocks" / "stock_daily.parquet"
    stock_basic: Path = project_root / "stocks" / "stock_basic_data.parquet"
    index_basic: Path = project_root / "indexes" / "index_basic.parquet"
    indexes_dir: Path = project_root / "indexes"

    # DuckDB
    duckdb_database: str = ":memory:"  # in-memory by default

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        env_prefix = "TD_"


settings = Settings()
