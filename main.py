from fastapi import FastAPI, HTTPException, status, Depends, Request
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from pydantic_settings import BaseSettings
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Annotated, Optional
import os
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import structlog
from datetime import datetime, timedelta
import re

"""
API Arduus DB - Interface para o banco de dados MongoDB da Arduus

Esta API fornece endpoints para interagir com o banco de dados MongoDB da Arduus.
Atualmente, ela inclui funcionalidades para coleta de dados de formulários com
validação rigorosa, autenticação via chave API, rate limiting e logs estruturados.
"""

# 1. Configurações e modelos primeiro
class Settings(BaseSettings):
    """
    Configurações da aplicação carregadas de variáveis de ambiente ou arquivo .env
    
    Attributes:
        MONGO_URI: URI de conexão com o MongoDB
        DB_NAME: Nome do banco de dados
        COLLECTION_NAME: Nome da coleção principal
        CORS_ORIGINS: Origens permitidas para CORS (separadas por vírgula)
        GCP_PROJECT: ID do projeto GCP (auto detectado no Cloud Run)
        API_KEY: Chave de API para autenticação
    """
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
    """
    Modelo para validação dos dados do formulário
    
    Attributes:
        nome_prospect: Nome completo do prospect (alias: full_name)
        email_prospect: Email corporativo do prospect (alias: corporate_email)
        whatsapp_prospect: Número de WhatsApp no formato internacional (alias: whatsapp)
        empresa_prospect: Nome da empresa do prospect (alias: company)
        faturamento_empresa: Faturamento da empresa (alias: revenue)
        cargo_prospect: Cargo do prospect (alias: job_title)
        api_key: Chave de API para autenticação
    """
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
        Field(examples=["+554799019123"], alias="whatsapp")
    ]
    empresa_prospect: Annotated[
        str, 
        Field(min_length=2, max_length=50, examples=["Arduus"], alias="company")
    ]
    faturamento_empresa: Annotated[
        str,
        Field(
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
    """
    Gerencia o ciclo de vida da aplicação
    
    Esta função é executada na inicialização e encerramento da aplicação.
    Ela configura a conexão com o MongoDB e cria índices necessários.
    
    Args:
        app: Instância da aplicação FastAPI
    """
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
    
    # Fechar conexão com o MongoDB ao encerrar a aplicação
    app.mongodb_client.close()

# 3. Criação da instância app
app = FastAPI(
    title="API Arduus DB",
    description="Interface para o banco de dados MongoDB da Arduus",
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

# Configuração de logging
def setup_logging():
    """
    Configura o sistema de logging estruturado
    
    Utiliza a biblioteca structlog para gerar logs em formato JSON,
    facilitando a integração com ferramentas de monitoramento.
    """
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

# Rate Limiter para proteção contra abusos
class RateLimiter:
    """
    Implementa rate limiting baseado em IP
    
    Limita o número de requisições que um IP pode fazer a um endpoint
    em um determinado período de tempo.
    
    Attributes:
        times: Número máximo de requisições permitidas
        minutes: Período de tempo em minutos
    """
    def __init__(self, times: int, minutes: int):
        self.times = times
        self.minutes = minutes
        self.window = timedelta(minutes=minutes)
    
    async def __call__(self, request: Request):
        """
        Verifica se o IP excedeu o limite de requisições
        
        Args:
            request: Objeto Request do FastAPI
            
        Raises:
            HTTPException: Se o limite de requisições for excedido
        """
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

# Função para limpar o número de WhatsApp
def clean_whatsapp_number(number: str) -> str:
    """
    Remove caracteres não numéricos do número de WhatsApp
    
    Esta função remove espaços, hífens, o sinal de + e outros caracteres não numéricos
    do número de WhatsApp, mantendo apenas os dígitos.
    
    Args:
        number: Número de WhatsApp com possível formatação
        
    Returns:
        str: Número de WhatsApp limpo, contendo apenas dígitos
    """
    # Remove todos os caracteres não numéricos, incluindo o sinal de +
    return re.sub(r'\D', '', number)

# Endpoint principal para submissão de formulário
@app.post(
    "/submit-form/",
    dependencies=[Depends(RateLimiter(times=200, minutes=1))],
    status_code=status.HTTP_201_CREATED,
    summary="Envia dados do formulário",
    response_description="ID do documento criado no MongoDB",
    tags=["Formulários"]
)
async def submit_form(form_data: FormSubmission):
    """
    Recebe dados de um formulário e armazena no MongoDB
    
    Este endpoint valida os dados recebidos, verifica a API key
    e armazena os dados no MongoDB.
    
    Args:
        form_data: Dados do formulário validados pelo modelo FormSubmission
        
    Returns:
        dict: Mensagem de sucesso e ID do documento criado
        
    Raises:
        HTTPException 401: Se a API key for inválida
        HTTPException 500: Se ocorrer um erro ao processar o formulário
    """
    if form_data.api_key != Settings().API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave API inválida"
        )
    
    try:
        # Limpa e valida o número de WhatsApp
        clean_number = clean_whatsapp_number(form_data.whatsapp_prospect)
        
        # Verifica se o número limpo está em um formato válido
        if not re.match(r'^[1-9]\d{1,14}$', clean_number):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Número de WhatsApp inválido mesmo após limpeza. Deve conter apenas dígitos."
            )
        
        document = {
            "whatsapp_prospect": clean_number,
            "nome_prospect": form_data.nome_prospect,
            "empresa_prospect": form_data.empresa_prospect,
            "email_prospect": form_data.email_prospect,
            "cargo_prospect": form_data.cargo_prospect,
            "faturamento_empresa": form_data.faturamento_empresa,
            "pipe_stage": "fit_to_rapport",
            "spiced_stage": "P1"
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

# Health Check para monitoramento
@app.get(
    "/health",
    tags=["Monitoramento"],
    summary="Verifica status da API",
    response_description="Status online"
)
async def health_check() -> dict[str, str]:
    """
    Verifica se a API está online
    
    Este endpoint é utilizado para monitoramento da saúde da aplicação.
    
    Returns:
        dict: Status da API
    """
    return {"status": "online"}
