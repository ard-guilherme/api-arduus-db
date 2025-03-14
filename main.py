from fastapi import FastAPI, HTTPException, status, Depends, Request
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from pydantic_settings import BaseSettings
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Annotated, Optional, Dict, Any, List
import os
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import structlog
from datetime import datetime, timedelta
import re
import httpx
import asyncio
from functools import partial
from dotenv import load_dotenv

"""
API Arduus DB - Interface para o banco de dados MongoDB da Arduus

Esta API fornece endpoints para interagir com o banco de dados MongoDB da Arduus.
Atualmente, ela inclui funcionalidades para coleta de dados de formulários com
validação rigorosa, autenticação via chave API, rate limiting e logs estruturados.
"""

# 1. Configurações e modelos primeiro
class Settings(BaseSettings):
    """
    Configurações da aplicação.
    """
    MONGO_URI: str = Field(..., env="MONGO_URI")
    CORS_ORIGINS: str = Field(..., env="CORS_ORIGINS")
    API_KEY: str = Field(..., env="API_KEY")
    
    # Configurações do banco de dados
    DB_NAME: str = "arduus_db"
    COLLECTION_NAME: str = "crm_db"
    
    # Configurações da Evolution API
    EVO_SUBDOMAIN: str = Field(..., env="EVO_SUBDOMAIN")
    EVO_TOKEN: str = Field(..., env="EVO_TOKEN")
    EVO_INSTANCE: str = Field(..., env="EVO_INSTANCE")
    
    # Configurações do OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    
    # Configurações do Sales Builder
    SALES_BUILDER_API_KEY: Optional[str] = Field(default=None, env="SALES_BUILDER_API_KEY")
    SALES_BUILDER_API_URL: str = "https://sales-builder.ornexus.com/kickoff"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

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
    Configura o sistema de logging
    
    Utiliza a biblioteca structlog para gerar logs em formato JSON,
    facilitando a integração com ferramentas de monitoramento.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
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

# Função para chamar a API Sales Builder
async def call_sales_builder_api(lead_data: dict, settings: Settings) -> dict:
    """
    Chama a API do Sales Builder para processar um lead.
    
    Args:
        lead_data: Dados do lead a serem enviados
        settings: Configurações da aplicação
        
    Returns:
        dict: Resposta da API
    """
    api_url = settings.SALES_BUILDER_API_URL
    api_key = settings.SALES_BUILDER_API_KEY
    
    if not api_key:
        logger.warning("Chave da API do Sales Builder não configurada. Pulando chamada à API.")
        return {"error": "API key not configured"}
    
    # Máscara para log (mostra apenas os primeiros e últimos 5 caracteres)
    masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
    logger.info(f"Chamando API Sales Builder: {api_url} com chave: {masked_key}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                json=lead_data,
                headers=headers,
                timeout=30.0
            )
            
        if response.status_code == 200:
            logger.info("Chamada à API Sales Builder bem-sucedida")
            return response.json()
        else:
            logger.error(f"Erro na chamada à API Sales Builder: {response.status_code} - {response.text}")
            return {"error": f"API error: {response.status_code}", "details": response.text}
            
    except Exception as e:
        logger.error(f"Exceção ao chamar API Sales Builder: {str(e)}")
        return {"error": f"Exception: {str(e)}"}

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
    e armazena os dados no MongoDB. Se o número de WhatsApp já existir
    na coleção, retorna uma mensagem informando que o lead já existe
    e não insere um novo documento nem chama a API Sales Builder.
    
    Após inserir os dados no MongoDB e chamar a API Sales Builder,
    inicia o processamento da task para envio de mensagens via WhatsApp.
    
    Args:
        form_data: Dados do formulário validados pelo modelo FormSubmission
        
    Returns:
        dict: Mensagem de sucesso e ID do documento criado, ou mensagem
              informando que o lead já existe e seu ID
        
    Raises:
        HTTPException 401: Se a API key for inválida
        HTTPException 422: Se o número de WhatsApp for inválido
        HTTPException 500: Se ocorrer um erro ao processar o formulário
    """
    settings = Settings()
    
    if form_data.api_key != settings.API_KEY:
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
        
        # Verificar se o número de WhatsApp já existe na coleção
        existing_lead = await app.collection.find_one({"whatsapp_prospect": clean_number})
        
        if existing_lead:
            logger.info(
                "Lead already exists, skipping insertion", 
                whatsapp=clean_number,
                existing_id=str(existing_lead["_id"])
            )
            
            return {
                "message": "Lead já existe no banco de dados",
                "document_id": str(existing_lead["_id"]),
                "is_duplicate": True
            }
        
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
        
        # Inserir o lead no MongoDB
        result = await app.collection.insert_one(document)
        
        logger.info("Form submitted", document_id=str(result.inserted_id))
        
        # Chamar a API Sales Builder
        try:
            # Preparar os dados para a API Sales Builder
            sales_builder_payload = {
                "nome_prospect": document["nome_prospect"],
                "empresa_prospect": document["empresa_prospect"],
                "cargo_prospect": document["cargo_prospect"],
                "email_prospect": document["email_prospect"],
                "whatsapp_prospect": document["whatsapp_prospect"],
                "faturamento_empresa": document["faturamento_empresa"],
                "nome_vendedor": "Vagner Campos",
                "interacao": "Iniciar a conversa com lead à partir do P1"
            }
            
            sales_builder_response = await call_sales_builder_api(sales_builder_payload, settings)
            logger.info(
                "Sales Builder API called successfully", 
                response=sales_builder_response,
                task_id=sales_builder_response.get("task_id")
            )
            
            # Iniciar o processamento da task em segundo plano
            task_id = sales_builder_response.get("task_id")
            if task_id:
                logger.info(f"Iniciando processamento da task {task_id} em segundo plano")
                # Importar o módulo apenas quando necessário
                try:
                    import sys
                    import os
                    # Garantir que o diretório atual esteja no PYTHONPATH
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    if current_dir not in sys.path:
                        sys.path.append(current_dir)
                    
                    # Verificar se as configurações da Evolution API estão presentes
                    evo_config_present = all([
                        settings.EVO_SUBDOMAIN,
                        settings.EVO_TOKEN,
                        settings.EVO_INSTANCE
                    ])
                    
                    if not evo_config_present:
                        logger.warning(
                            "Configurações da Evolution API incompletas. Pulando processamento da task.",
                            subdomain=settings.EVO_SUBDOMAIN,
                            instance=settings.EVO_INSTANCE,
                            token_present=bool(settings.EVO_TOKEN)
                        )
                        return {
                            "message": "Formulário recebido com sucesso",
                            "document_id": str(result.inserted_id),
                            "sales_builder_task_id": task_id,
                            "warning": "Processamento da task pulado devido a configurações incompletas da Evolution API"
                        }
                    
                    # Log para depuração
                    logger.info(
                        "Configurações da Evolution API",
                        subdomain=settings.EVO_SUBDOMAIN,
                        instance=settings.EVO_INSTANCE,
                        token_present=bool(settings.EVO_TOKEN)
                    )
                    
                    from sales_builder_status_checker import process_sales_builder_task
                    # Criar uma task em segundo plano para processar a resposta, passando as configurações
                    process_task_with_settings = partial(process_sales_builder_task, settings=settings)
                    
                    # Criar a task em segundo plano
                    asyncio.create_task(process_task_with_settings(task_id))
                except ImportError as e:
                    logger.error(f"Erro ao importar módulo sales_builder_status_checker: {str(e)}")
                    logger.info(f"PYTHONPATH atual: {sys.path}")
                except Exception as e:
                    logger.error(f"Erro ao iniciar processamento da task: {str(e)}")
            
            return {
                "message": "Formulário recebido com sucesso",
                "document_id": str(result.inserted_id),
                "sales_builder_task_id": task_id
            }
        except Exception as api_error:
            # Registrar o erro, mas não falhar a requisição
            error_message = str(api_error)
            logger.error(
                "Error calling Sales Builder API", 
                error=error_message,
                error_type=type(api_error).__name__,
                error_details=repr(api_error)
            )
        
            return {
                "message": "Formulário recebido com sucesso, mas houve um erro ao iniciar o processo de interação",
                "document_id": str(result.inserted_id),
                "sales_builder_error": error_message
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
