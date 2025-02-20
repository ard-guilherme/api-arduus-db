from fastapi import FastAPI, HTTPException, status, Depends, Request
from pydantic import BaseModel, EmailStr, Field, ConfigDict, validator
from pydantic_settings import BaseSettings
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Annotated, Optional
import os
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
import structlog
from datetime import datetime, timedelta

# 1. Configurações e modelos primeiro
class Settings(BaseSettings):
    MONGO_URI: str = Field(..., alias="MONGO_URI")
    DB_NAME: str = "arduus_db"
    COLLECTION_NAME: str = "crm_db"
    CORS_ORIGINS: str = Field(
        default="*",
        description="Origins permitidos separados por vírgula"
    )
    GCP_PROJECT: Optional[str] = Field(
        default=None,
        description="ID do projeto GCP (auto detectado no Cloud Run)"
    )
    API_KEY: str = Field(..., alias="API_KEY")

    model_config = ConfigDict(env_file=".env", extra='ignore')

class FormSubmission(BaseModel):
    nome_prospect: Annotated[
        str, 
        Field(min_length=3, max_length=100, examples=["Luan Detoni"], alias="full_name")
    ]
    email_prospect: Annotated[
        EmailStr,
        Field(examples=["luan.detoni@arduus.tech"], alias="corporate_email")
    ]
    whatsapp_prospect: Annotated[
        str, 
        Field(pattern=r'^\+?[1-9]\d{1,14}$', examples=["+554799019123"], alias="whatsapp")
    ]
    empresa_prospect: Annotated[
        str, 
        Field(min_length=2, max_length=50, examples=["Arduus"], alias="company")
    ]
    faturamento_empresa: Annotated[
        str,
        Field(
            pattern=r'^(Até 1 milhão|1-5 milhões|5-10 milhões|Acima de 10 milhões)$',
            examples=["1-5 milhões"],
            alias="revenue"
        )
    ]
    cargo_prospect: Annotated[
        str,
        Field(default="", max_length=50, examples=["CAIO"], alias="job_title")
    ]
    api_key: str = Field(
        examples=["sua_chave_secreta"],
        description="Chave de API fixa para autenticação"
    )

# 2. Função lifespan antes da criação do app
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    
    # Banco de dados
    app.mongodb_client = AsyncIOMotorClient(settings.MONGO_URI)
    app.db = app.mongodb_client[settings.DB_NAME]
    app.collection = app.db[settings.COLLECTION_NAME]
    
    # Criar índice para rate limiting
    await app.db.rate_limits.create_index(
        [("client_ip", 1), ("path", 1)],
        unique=True
    )
    
    yield
    
    app.mongodb_client.close()

# 3. Criação da instância app AGORA
app = FastAPI(
    title="Form Submission API",
    description="API para processamento de formulários corporativos",
    version="1.0.0",
    lifespan=lifespan
)

# 4. Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Settings().CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração de segurança
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuração de logging
def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

setup_logging()
logger = structlog.get_logger()

# Adicionar antes do endpoint
class RateLimiter:
    def __init__(self, times: int, minutes: int):
        self.times = times
        self.minutes = minutes
        self.window = timedelta(minutes=minutes)
    
    async def __call__(self, request: Request):
        client_ip = request.client.host
        now = datetime.utcnow()
        
        # Usar coleção rate_limits no MongoDB
        record = await request.app.db.rate_limits.find_one({
            "client_ip": client_ip,
            "path": request.url.path
        })
        
        if not record:
            await request.app.db.rate_limits.insert_one({
                "client_ip": client_ip,
                "path": request.url.path,
                "count": 1,
                "first_request": now,
                "last_request": now
            })
            return
        
        time_diff = now - record["first_request"]
        
        if time_diff < self.window and record["count"] >= self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas requisições"
            )
        
        if time_diff >= self.window:
            await request.app.db.rate_limits.update_one(
                {"_id": record["_id"]},
                {"$set": {
                    "count": 1,
                    "first_request": now,
                    "last_request": now
                }}
            )
        else:
            await request.app.db.rate_limits.update_one(
                {"_id": record["_id"]},
                {"$inc": {"count": 1}, "$set": {"last_request": now}}
            )

# Endpoint principal atualizado
@app.post(
    "/submit-form/",
    dependencies=[Depends(RateLimiter(times=200, minutes=1))],
    status_code=status.HTTP_201_CREATED,
    summary="Envia dados do formulário",
    response_description="ID do documento criado no MongoDB"
)
async def submit_form(form_data: FormSubmission):
    if form_data.api_key != Settings().API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave API inválida"
        )
    
    try:
        document = {
            "whatsapp_prospect": form_data.whatsapp_prospect,
            "nome_prospect": form_data.nome_prospect,
            "empresa_prospect": form_data.empresa_prospect,
            "email_prospect": form_data.email_prospect,
            "cargo_prospect": form_data.cargo_prospect,
            "faturamento_empresa": form_data.faturamento_empresa,
            "deal_id": "",
            "calendar_event_id": "",
            "calendar_event_datetimezone": "",
            "is_fit": False,
            "pipe_stage": "",
            "spiced_stage": ""
        }
        
        result = await app.collection.insert_one(document)
        
        logger.info("Form submitted", document_id=str(result.inserted_id))
        
        return {
            "message": "Formulário recebido com sucesso",
            "document_id": str(result.inserted_id)
        }
    
    except Exception as e:
        logger.error("Form submission error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar formulário: {str(e)}"
        )

# Health Check com documentação melhorada
@app.get(
    "/health",
    tags=["Monitoramento"],
    summary="Verifica status da API",
    response_description="Status online"
)
async def health_check() -> dict[str, str]:
    return {"status": "online"}

# Função para criar admin padrão
async def create_default_admin():
    admin_user = await app.db.users.find_one({"username": "admin"})
    if not admin_user:
        hashed_password = pwd_context.hash("admin123")
        await app.db.users.insert_one({
            "username": "admin",
            "hashed_password": hashed_password,
            "disabled": False
        })
        logger.info("Default admin user created")
