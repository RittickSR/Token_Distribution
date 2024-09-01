from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_host:str
    redis_port:int
    token_expiry:int = 300
    active_expiry: int = 60
    keep_alive_interval:int = 300
    log_file_name:str = "app"

    model_config = ConfigDict(env_file="../.env")

settings = Settings()