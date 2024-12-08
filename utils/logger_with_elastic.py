# utils/logger.py
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from contextvars import ContextVar
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from elasticsearch import AsyncElasticsearch  # elasticsearch-py 라이브러리 필요

@dataclass
class RequestContext:
    """요청 관련 컨텍스트 정보를 담는 클래스"""
    timestamp: str = None
    request_id: str = '-'
    user_id: str = '-'
    service: str = '-'  # 서비스/앱 이름
    environment: str = 'development'  # 환경 (dev/prod)
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

class ElasticsearchHandler(logging.Handler):
    """Elasticsearch 로그 핸들러"""
    def __init__(self, es_client: AsyncElasticsearch, index_prefix: str = "fastapi-logs"):
        super().__init__()
        self.es_client = es_client
        self.index_prefix = index_prefix
        print("ElasticsearchHandler initialized!")  # 초기화 확인

    async def emit(self, record: logging.LogRecord):
        try:
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'message': record.getMessage(),
                **record.__dict__.get('extra', {})
            }
            
            index_name = f"{self.index_prefix}-{datetime.utcnow().strftime('%Y.%m.%d')}"
            print(f"Attempting to send log to Elasticsearch: {index_name}")  # 로그 전송 시도 확인
            print(f"Log entry: {log_entry}")  # 로그 내용 확인
            
            await self.es_client.index(index=index_name, document=log_entry)
            print("Log successfully sent to Elasticsearch")  # 전송 성공 확인
            
        except Exception as e:
            print(f"Detailed error in sending log to Elasticsearch: {str(e)}")  # 자세한 에러 메시지
            sys.stderr.write(f"Error sending log to Elasticsearch: {str(e)}\n")

class FastAPILogger:
    """FastAPI를 위한 확장 가능한 로깅 클래스"""
    
    _context_var = ContextVar[RequestContext]('request_context', default=RequestContext())
    
    def __init__(
        self,
        name: str = None,
        log_dir: str = "var/logs",
        elastic_config: Optional[Dict] = None,
        service_name: str = "fastapi-service",
        environment: str = "development"
    ):
        self.name = name or __name__
        self.log_dir = Path(log_dir)
        self.service_name = service_name
        self.environment = environment
        self.elastic_config = elastic_config
        self._es_client = None  # Elasticsearch 클라이언트 초기화
        self.logger = self._configure_logger()

    async def _setup_elasticsearch(self):
        """Elasticsearch 클라이언트 설정"""
        if self.elastic_config:
            self._es_client = AsyncElasticsearch(**self.elastic_config)  # 클라이언트 저장
            handler = ElasticsearchHandler(self._es_client)
            handler.setFormatter(self.get_formatter())
            self.logger.addHandler(handler)
            return self._es_client
        return None

    def get_formatter(self):
        """로그 포맷터 생성"""
        return logging.Formatter(
            '%(asctime)s - %(levelname)s - '
            '[SERVICE:%(service)s][ENV:%(environment)s]'
            '[REQ:%(request_id)s][USER:%(user_id)s] - '
            '%(name)s - %(message)s'
        )

    def _configure_logger(self) -> logging.Logger:
        """로거 기본 설정"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)

        if not logger.handlers:
            # 파일 핸들러
            file_handler = TimedRotatingFileHandler(
                filename=self.log_dir / "app.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8"
            )
            file_handler.setFormatter(self.get_formatter())
            file_handler.setLevel(logging.INFO)
            
            # JSON 파일 핸들러 (ELK 스택 통합을 위한)
            json_handler = TimedRotatingFileHandler(
                filename=self.log_dir / "app.json.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8"
            )
            json_handler.setFormatter(JsonFormatter())
            json_handler.setLevel(logging.INFO)
            
            # 콘솔 핸들러
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(self.get_formatter())
            console_handler.setLevel(logging.DEBUG)
            
            logger.addHandler(file_handler)
            logger.addHandler(json_handler)
            logger.addHandler(console_handler)

        return logger

    def set_context(self, **kwargs):
        """컨텍스트 설정"""
        context = RequestContext(
            service=self.service_name,
            environment=self.environment,
            **kwargs
        )
        self._context_var.set(context)

    def _get_log_args(self, message: str, *args, **kwargs) -> tuple:
        """로그 인자 준비"""
        extra = kwargs.pop('extra', {})
        context = self._context_var.get()
        extra.update(context.as_dict())
        return message, args, extra, kwargs

    async def log(self, level: str, message: str, *args, **kwargs):
        """비동기 로깅"""
        message, args, extra, kwargs = self._get_log_args(message, *args, **kwargs)
        getattr(self.logger, level)(message, *args, extra=extra, **kwargs)

    async def info(self, message: str, *args, **kwargs):
        await self.log('info', message, *args, **kwargs)

    async def error(self, message: str, *args, **kwargs):
        await self.log('error', message, *args, **kwargs)

    async def debug(self, message: str, *args, **kwargs):
        await self.log('debug', message, *args, **kwargs)

class JsonFormatter(logging.Formatter):
    """JSON 형식의 로그 포맷터"""
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name
        }
        
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
            
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)

# 로거 인스턴스 생성
logger = FastAPILogger(
    service_name="your-service-name",
    environment="development",
    elastic_config={
        'hosts': ['http://localhost:9200'],
        'basic_auth': ('elastic', 'cHLk3W8Fec1Hch4PeKQK')
        # 필요한 경우 인증 정보 추가
        # 'api_key': ('id', 'api_key'),
        # 'basic_auth': ('user', 'password')
    }
)