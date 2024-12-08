# uvicorn main:app --port=8081 --reload --host 0.0.0.0
# main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from middleware.logging_middleware import logging_middleware
from utils.logger_with_elastic import logger, RequestContext
from pydantic import BaseModel
from datetime import datetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Elasticsearch setup...")  # 시작 확인
    try:
        await logger._setup_elasticsearch()
        print("Elasticsearch setup completed successfully")  # 설정 성공 확인
    except Exception as e:
        print(f"Error setting up Elasticsearch: {str(e)}")  # 설정 실패 시 에러 확인
    yield

app = FastAPI(lifespan=lifespan)
app.middleware("http")(logging_middleware)


# Elasticsearch 설정을 위한 startup 이벤트 추가


class TestRequest(BaseModel):
    user_id: str
    message: str

@app.get("/test-es")
async def test_elasticsearch():
    """Elasticsearch 연결 테스트"""
    try:
        # 테스트 문서 생성
        test_doc = {
            "message": "test",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 직접 elasticsearch에 데이터 넣어보기
        result = await logger._es_client.index(
            index="test-index", 
            document=test_doc
        )
        
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/ping")
async def ping():
    """간단한 헬스체크 API"""
    await logger.info("ping 요청 받음")
    return {"status": "ok", "message": "pong"}

@app.post("/test-log")
async def test_logging(request: TestRequest):
    """로깅 테스트를 위한 API"""
    logger.set_context(user_id=request.user_id)
    
    try:
        await logger.info(f"테스트 메시지 수신: {request.message}")
        await logger.debug("디버그 레벨 로그 테스트")
        
        if request.message == "error":
            raise ValueError("테스트 에러 발생")
            
        return {
            "status": "success",
            "message": "로그 테스트 완료",
            "your_message": request.message
        }
    except Exception as e:
        await logger.error(f"에러 발생: {str(e)}", exc_info=True)
        raise