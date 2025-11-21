# server/utils/config.py

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from openai import AzureOpenAI

# server/.env 를 우선 로드하되, 기존처럼 상위 디렉터리(.env)도 함께 로드
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SERVER_ENV_PATH = BASE_DIR / ".env"
ROOT_ENV_PATH = PROJECT_ROOT / ".env"

# 기존 load_dotenv() 기본 검색 경로 → 프로젝트 루트 → server 디렉터리 순으로 병합
load_dotenv(override=False)
load_dotenv(dotenv_path=ROOT_ENV_PATH, override=False)
load_dotenv(dotenv_path=SERVER_ENV_PATH, override=False)

# SSL 검증 비활성화 (Langfuse 연결 시 SSL 인증서 검증 오류 방지)
# OpenTelemetry exporter가 사용하는 모든 레벨에서 SSL 검증 비활성화
import urllib3
import ssl
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL 검증 비활성화를 위한 전역 설정
ssl._create_default_https_context = ssl._create_unverified_context

# urllib3의 HTTPSConnection.connect() 메서드를 직접 패치 (가장 확실한 방법)
original_HTTPSConnection_connect = urllib3.connection.HTTPSConnection.connect

def patched_HTTPSConnection_connect(self):
    # cert_reqs와 check_hostname을 강제로 비활성화
    self.cert_reqs = ssl.CERT_NONE
    self.check_hostname = False
    return original_HTTPSConnection_connect(self)

urllib3.connection.HTTPSConnection.connect = patched_HTTPSConnection_connect

# urllib3의 _ssl_wrap_socket_impl 함수를 직접 패치
if hasattr(urllib3.util.ssl_, '_ssl_wrap_socket_impl'):
    original_ssl_wrap_socket_impl = urllib3.util.ssl_._ssl_wrap_socket_impl

    def patched_ssl_wrap_socket_impl(
        sock,
        ssl_context,
        tls_in_tls,
        server_hostname=None,
    ):
        # SSL 컨텍스트를 강제로 검증 비활성화로 설정
        if ssl_context is None:
            ssl_context = ssl._create_unverified_context()
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        return original_ssl_wrap_socket_impl(
            sock=sock,
            ssl_context=ssl_context,
            tls_in_tls=tls_in_tls,
            server_hostname=server_hostname,
        )

    urllib3.util.ssl_._ssl_wrap_socket_impl = patched_ssl_wrap_socket_impl

# urllib3의 ssl_wrap_socket 함수도 패치
if hasattr(urllib3.util.ssl_, 'ssl_wrap_socket'):
    original_ssl_wrap_socket = urllib3.util.ssl_.ssl_wrap_socket

    def patched_ssl_wrap_socket(
        sock,
        keyfile=None,
        certfile=None,
        cert_reqs=None,
        ca_certs=None,
        server_hostname=None,
        ssl_version=None,
        ciphers=None,
        ssl_context=None,
        ca_cert_dir=None,
        key_password=None,
        ca_cert_data=None,
        tls_in_tls=False,
    ):
        # SSL 검증을 강제로 비활성화
        if ssl_context is None:
            ssl_context = ssl._create_unverified_context()
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        return original_ssl_wrap_socket(
            sock=sock,
            keyfile=keyfile,
            certfile=certfile,
            cert_reqs=ssl.CERT_NONE,
            ca_certs=ca_certs,
            server_hostname=server_hostname,
            ssl_version=ssl_version,
            ciphers=ciphers,
            ssl_context=ssl_context,
            ca_cert_dir=ca_cert_dir,
            key_password=key_password,
            ca_cert_data=ca_cert_data,
            tls_in_tls=tls_in_tls,
        )

    urllib3.util.ssl_.ssl_wrap_socket = patched_ssl_wrap_socket

# requests의 Session 클래스도 패치하여 모든 세션에 verify=False 적용
original_session_init = requests.Session.__init__

def patched_session_init(self, *args, **kwargs):
    original_session_init(self, *args, **kwargs)
    # 모든 어댑터에 SSL 검증 비활성화 적용
    for prefix in list(self.adapters.keys()):
        adapter = self.adapters[prefix]
        if hasattr(adapter, 'init_poolmanager'):
            original_init_poolmanager = adapter.init_poolmanager
            def patched_init_poolmanager(*args, **kwargs):
                kwargs['ssl_context'] = ssl._create_unverified_context()
                return original_init_poolmanager(*args, **kwargs)
            adapter.init_poolmanager = patched_init_poolmanager

requests.Session.__init__ = patched_session_init


class Settings(BaseSettings):
    """
    프로젝트 전체에서 사용할 공용 설정 값.
    .env에 정의된 값을 읽어옵니다.
    """

    # ---------- Azure OpenAI ----------
    AOAI_API_KEY: str
    AOAI_ENDPOINT: str
    AOAI_API_VERSION: str

    # 기본 LLM (gpt-4o)
    AOAI_DEPLOY_GPT4O: str

    # 경량 LLM (gpt-4o-mini 등)
    AOAI_DEPLOY_GPT4O_MINI: str | None = None

    # Embedding 모델 배포명
    AOAI_EMBEDDING_DEPLOYMENT: str

    # ---------- Langfuse (선택) ----------
    LANGFUSE_ENABLED: bool = True  # Langfuse 활성/비활성 플래그 (기본값: True)
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str | None = None

    # ---------- API & 프로젝트 ----------
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI Interview Agent API"

    # ---------- CORS ----------
    # 실제 배포 시에는 허용 Origin을 제한하는 것이 좋습니다.
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # ---------- DB ----------
    DB_PATH: str = "interview_history.db"
    SQLALCHEMY_DATABASE_URI: str | None = None

    model_config = SettingsConfigDict(
        env_file=[str(SERVER_ENV_PATH), str(ROOT_ENV_PATH)],
        case_sensitive=True,
        extra="ignore",
    )

    def __init__(self, **data):
        super().__init__(**data)
        # SQLALCHEMY_DATABASE_URI가 명시되지 않았다면 DB_PATH 기준으로 생성
        if not self.SQLALCHEMY_DATABASE_URI:
            # SQLite 로컬 파일 사용
            self.SQLALCHEMY_DATABASE_URI = f"sqlite:///./{self.DB_PATH}"
        # Langfuse 클라이언트 캐시용
        self._langfuse_client: Langfuse | None = None

    # ========= LLM / Embedding 팩토리 메서드 ========= #

    def get_llm(self, *, use_mini: bool = False, streaming: bool = True) -> AzureChatOpenAI:
        """
        Azure OpenAI LLM 인스턴스를 반환합니다.
        - use_mini=True  : 경량 모델 (gpt-4o-mini 등)
        - use_mini=False : 기본 모델 (gpt-4o)
        """
        deployment = self.AOAI_DEPLOY_GPT4O
        if use_mini and self.AOAI_DEPLOY_GPT4O_MINI:
            deployment = self.AOAI_DEPLOY_GPT4O_MINI

        return AzureChatOpenAI(
            openai_api_key=self.AOAI_API_KEY,
            azure_endpoint=self.AOAI_ENDPOINT,
            azure_deployment=deployment,
            api_version=self.AOAI_API_VERSION,
            temperature=0.7,
            streaming=streaming,
        )

    def get_embeddings(self) -> AzureOpenAIEmbeddings:
        """
        Azure OpenAI Embeddings 인스턴스를 반환합니다.
        """
        return AzureOpenAIEmbeddings(
            model=self.AOAI_EMBEDDING_DEPLOYMENT,
            openai_api_version=self.AOAI_API_VERSION,
            api_key=self.AOAI_API_KEY,
            azure_endpoint=self.AOAI_ENDPOINT,
        )

    # ========= Langfuse ========= #

    @property
    def langfuse(self) -> Langfuse | None:
        """
        Langfuse 클라이언트를 반환합니다.
        환경변수가 설정되지 않았으면 None 을 반환합니다.
        """
        if self._langfuse_client is not None:
            return self._langfuse_client
        
        if not (self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY and self.LANGFUSE_HOST):
            return None

        self._langfuse_client = Langfuse(
            public_key=self.LANGFUSE_PUBLIC_KEY,
            secret_key=self.LANGFUSE_SECRET_KEY,
            host=self.LANGFUSE_HOST,
        )
        return self._langfuse_client

    def get_langfuse_handler(self, session_id: str | None = None) -> CallbackHandler | None:
        """
        Langfuse CallbackHandler 반환.
        - session_id 는 LangGraph / LangChain run 의 config에 전달해야 함.
        - Langfuse 설정이 없거나 LANGFUSE_ENABLED=False 이면 None 반환.
        """
        # Langfuse가 비활성화되어 있으면 None 반환
        if not self.LANGFUSE_ENABLED:
            return None
        
        if not (self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY and self.LANGFUSE_HOST):
            return None

        # 최신 langfuse에서는 환경 변수를 자동으로 읽도록 설정
        # 환경 변수를 명시적으로 설정 (setdefault 대신 직접 할당하여 확실히 설정)
        os.environ["LANGFUSE_PUBLIC_KEY"] = self.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = self.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = self.LANGFUSE_HOST
        
        # session_id가 있으면 환경 변수로 설정 (Langfuse가 이를 사용)
        if session_id:
            os.environ["LANGFUSE_SESSION_ID"] = session_id
        
        # Langfuse 클라이언트를 먼저 초기화하여 CallbackHandler가 이를 찾을 수 있도록 함
        # 이렇게 하면 CallbackHandler가 내부적으로 싱글톤 클라이언트를 찾을 수 있음
        langfuse_client = self.langfuse
        if langfuse_client is None:
            return None
        
        # CallbackHandler는 환경 변수를 자동으로 읽도록 초기화
        # public_key를 명시적으로 전달하여 확실히 초기화
        # SSL 검증은 모듈 레벨에서 이미 비활성화되어 있음
        try:
            handler = CallbackHandler(public_key=self.LANGFUSE_PUBLIC_KEY)
            
            # 디버깅: CallbackHandler가 제대로 생성되었는지 확인
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Langfuse CallbackHandler 생성 완료. Session ID: {session_id}, Public Key: {self.LANGFUSE_PUBLIC_KEY[:20]}...")
            
            return handler
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Langfuse CallbackHandler 생성 실패: {e}")
            return None


# 전역 Settings 인스턴스
settings = Settings()


# ========== 하위 호환 및 편의용 함수들 ========== #

def get_settings() -> Settings:
    """
    DI 또는 다른 모듈에서 settings 를 가져다 쓸 때 사용.
    예) from utils.config import get_settings
    """
    return settings


def get_llm(*, use_mini: bool = False, streaming: bool = True) -> AzureChatOpenAI:
    """
    하위 호환 / 간단 사용을 위한 래퍼.
    예) from utils.config import get_llm
    """
    return settings.get_llm(use_mini=use_mini, streaming=streaming)


def get_embeddings() -> AzureOpenAIEmbeddings:
    """
    하위 호환 / 간단 사용을 위한 래퍼.
    """
    return settings.get_embeddings()


def get_langfuse_handler(session_id: str | None = None) -> CallbackHandler | None:
    """
    LangGraph / Agent 에서 바로 import 하여 사용하기 좋은 헬퍼.
    """
    return settings.get_langfuse_handler(session_id=session_id)


def get_client() -> AzureOpenAI:
    """
    OpenAI SDK(Azure) 클라이언트를 반환합니다.
    - InsightsAgent에서 Responses / Embeddings API를 직접 호출할 때 사용
    """
    return AzureOpenAI(
        api_key=settings.AOAI_API_KEY,
        api_version=settings.AOAI_API_VERSION,
        azure_endpoint=settings.AOAI_ENDPOINT,
    )
