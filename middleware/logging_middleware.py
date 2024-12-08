# middleware/logging_middleware.py
from fastapi import Request
from utils.logger_with_elastic import logger
import uuid

async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    
    # 새로운 요청의 컨텍스트 설정
    logger.set_context(
        request_id=request_id,
        extra={
        'path': request.url.path,
        'method': request.method
        }
    )
    
    try:
        await logger.info(f"Request started - {request.method} {request.url.path}")
        response = await call_next(request)

        logger.set_context(
            request_id=request_id,
            extra={
                'path': request.url.path,
                'method': request.method,
                'status_code': response.status_code
            }
        )

        await logger.info(f"Request completed - {request.method} {request.url.path}- Status: {response.status_code}")
        return response
    except Exception as e:
        await logger.error(
            f"Request failed - {request.method} {request.url.path}",
            exc_info=True
        )
        raise