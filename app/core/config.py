from pydantic import computed_field
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv


load_dotenv()


class Conf(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )


class AppConfig(Conf):
    IS_PROD: bool


class CORSConfig(Conf):
    CORS_ORIGINS: list[str]
    CORS_METHODS: list[str]
    CORS_HEADERS: list[str]


class PostgresConfig(Conf):
    DB_B2B_SERVICE_HOST: str
    DB_B2B_SERVICE_PORT: int
    DB_B2B_SERVICE_NAME: str
    DB_B2B_SERVICE_USER: str
    DB_B2B_SERVICE_PASSWORD: str
    ECHO: bool

    @computed_field
    @property
    def POSTGRES_URL_ASYNC(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="postgresql+asyncpg",
            username=self.DB_B2B_SERVICE_USER,
            password=self.DB_B2B_SERVICE_PASSWORD,
            host=self.DB_B2B_SERVICE_HOST,
            port=self.DB_B2B_SERVICE_PORT,
            path=self.DB_B2B_SERVICE_NAME,
        )


class MinioConfig(Conf):
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS: str
    MINIO_SECRET: str
    MINIO_BUCKET_NAME: str
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"
    MINIO_SECURE: bool = False


class RabbitConfig(Conf):
    RABBITMQ_URL: str
    PRODUCTS_RESERVE_ROUTING_KEY: str = "products.reserve"
    PRODUCTS_DELETE_ROUTING_KEY: str = "products.delete"
    REVIEWS_ROUTING_KEY: str = "reviews"
    ORDERS_RESERVED_ROUTING_KEY: str = "orders.reserved"


class JwtConfig(Conf):
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int


class ServiceConfig(Conf):
    SERVICE_KEY: str = "internal-service-key"
    MODERATION_URL: str = "http://moderation:8011"
    B2C_URL: str = "http://b2c:8012"
    NGINX_URL: str = "http://nginx_gateway"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    app: AppConfig = AppConfig()
    cors: CORSConfig = CORSConfig()
    minio: MinioConfig = MinioConfig()
    pg_database: PostgresConfig = PostgresConfig()
    rabbitmq: RabbitConfig = RabbitConfig()
    jwt: JwtConfig = JwtConfig()
    service: ServiceConfig = ServiceConfig()


settings = Settings()
