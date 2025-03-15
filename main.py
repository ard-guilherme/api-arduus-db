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
import json
from bson.objectid import ObjectId

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
    
    # Criar collection para fila de requisições se não existir
    app.request_queue = app.db["request_queue"]
    
    # Criar índices para a fila de requisições
    await app.request_queue.create_index([("created_at", 1)])
    await app.request_queue.create_index([("status", 1)])
    await app.request_queue.create_index([("task_id", 1)], unique=True, sparse=True)
    await app.request_queue.create_index([("whatsapp_prospect", 1)])
    
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
    
    # Log detalhado da URL e configurações
    print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - URL: {api_url}")
    
    if not api_key:
        logger.warning("Chave da API do Sales Builder não configurada. Pulando chamada à API.")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - ERRO: API key não configurada")
        return {"error": "API key not configured"}
    
    # Máscara para log (mostra apenas os primeiros e últimos 5 caracteres)
    masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
    
    # Criar uma cópia do payload para log com dados sensíveis mascarados
    log_payload = lead_data.copy()
    if "email_prospect" in log_payload:
        email = log_payload["email_prospect"]
        if "@" in email:
            username, domain = email.split("@", 1)
            if len(username) > 3:
                log_payload["email_prospect"] = f"{username[:2]}***@{domain}"
    
    if "whatsapp_prospect" in log_payload:
        whatsapp = log_payload["whatsapp_prospect"]
        if len(whatsapp) > 6:
            log_payload["whatsapp_prospect"] = f"{whatsapp[:4]}***{whatsapp[-2:]}"
    
    # Log detalhado do payload completo (sem mascaramento para debug)
    print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - PAYLOAD COMPLETO: {json.dumps(lead_data, ensure_ascii=False)}")
    
    logger.info(
        "Iniciando chamada à API Sales Builder",
        url=api_url,
        api_key_masked=masked_key,
        payload=log_payload
    )
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Log detalhado dos headers (com API key mascarada)
    headers_log = headers.copy()
    if "Authorization" in headers_log:
        auth_parts = headers_log["Authorization"].split(" ")
        if len(auth_parts) > 1:
            headers_log["Authorization"] = f"{auth_parts[0]} {masked_key}"
    
    print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - HEADERS: {json.dumps(headers_log)}")
    
    try:
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - INICIANDO REQUISIÇÃO HTTP")
        start_time = datetime.utcnow()
        
        # Log do timeout configurado
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TIMEOUT CONFIGURADO: 30.0 segundos")
        
        async with httpx.AsyncClient() as client:
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - CLIENTE HTTP CRIADO")
            
            # Log antes de enviar a requisição
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - ENVIANDO REQUISIÇÃO POST")
            
            response = await client.post(
                api_url,
                json=lead_data,
                headers=headers,
                timeout=30.0
            )
            
            # Log após receber a resposta
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - RESPOSTA RECEBIDA: Status {response.status_code}")
        
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TEMPO DE RESPOSTA: {elapsed_time:.2f} segundos")
            
        if response.status_code == 200:
            response_data = response.json()
            
            # Log detalhado da resposta
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - RESPOSTA COMPLETA: {json.dumps(response_data, ensure_ascii=False)}")
            
            logger.info(
                "Chamada à API Sales Builder bem-sucedida",
                status_code=response.status_code,
                elapsed_time_seconds=elapsed_time,
                response_data=response_data
            )
            return response_data
        else:
            # Log detalhado do erro
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - ERRO HTTP: Status {response.status_code}")
            print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - CORPO DA RESPOSTA DE ERRO: {response.text}")
            
            logger.error(
                "Erro na chamada à API Sales Builder",
                status_code=response.status_code,
                elapsed_time_seconds=elapsed_time,
                response_text=response.text,
                payload=log_payload
            )
            return {"error": f"API error: {response.status_code}", "details": response.text}
            
    except httpx.TimeoutException as e:
        elapsed_time = (datetime.utcnow() - start_time).total_seconds() if 'start_time' in locals() else 0
        
        # Log detalhado do timeout
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TIMEOUT APÓS {elapsed_time:.2f} SEGUNDOS")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - DETALHES DO TIMEOUT: {str(e)}")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TIPO DE EXCEÇÃO: {type(e).__name__}")
        
        logger.error(
            "Timeout ao chamar API Sales Builder",
            error=str(e),
            timeout_seconds=30.0,
            elapsed_time_seconds=elapsed_time,
            payload=log_payload
        )
        return {"error": f"Timeout: {str(e)}"}
    except httpx.RequestError as e:
        elapsed_time = (datetime.utcnow() - start_time).total_seconds() if 'start_time' in locals() else 0
        
        # Log detalhado do erro de requisição
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - ERRO DE REQUISIÇÃO APÓS {elapsed_time:.2f} SEGUNDOS")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - DETALHES DO ERRO: {str(e)}")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TIPO DE EXCEÇÃO: {type(e).__name__}")
        
        logger.error(
            "Erro de requisição ao chamar API Sales Builder",
            error=str(e),
            error_type=type(e).__name__,
            elapsed_time_seconds=elapsed_time,
            payload=log_payload
        )
        return {"error": f"Request error: {str(e)}"}
    except Exception as e:
        elapsed_time = (datetime.utcnow() - start_time).total_seconds() if 'start_time' in locals() else 0
        
        # Log detalhado da exceção genérica
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - EXCEÇÃO INESPERADA APÓS {elapsed_time:.2f} SEGUNDOS")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - DETALHES DA EXCEÇÃO: {str(e)}")
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TIPO DE EXCEÇÃO: {type(e).__name__}")
        import traceback
        print(f"[{datetime.now().isoformat()}] SALES BUILDER DEBUG - TRACEBACK: {traceback.format_exc()}")
        
        logger.error(
            "Exceção ao chamar API Sales Builder",
            error=str(e),
            error_type=type(e).__name__,
            elapsed_time_seconds=elapsed_time,
            traceback=traceback.format_exc(),
            payload=log_payload
        )
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
        
        # Criar um registro na fila de requisições
        request_id = await app.request_queue.insert_one({
            "whatsapp_prospect": clean_number,
            "nome_prospect": form_data.nome_prospect,
            "created_at": datetime.utcnow(),
            "status": "received",
            "steps": [
                {
                    "step": "received",
                    "timestamp": datetime.utcnow(),
                    "success": True,
                    "message": "Requisição recebida"
                }
            ]
        })
        
        # Verificar se o número de WhatsApp já existe na coleção
        existing_lead = await app.collection.find_one({"whatsapp_prospect": clean_number})
        
        if existing_lead:
            logger.info(
                "Lead already exists, skipping insertion", 
                whatsapp=clean_number,
                existing_id=str(existing_lead["_id"]),
                request_id=str(request_id.inserted_id)
            )
            
            # Log no console
            print(f"[{datetime.now().isoformat()}] LEAD DUPLICADO: Número {clean_number} já existe no banco com ID {str(existing_lead['_id'])}")
            
            # Atualizar status na fila
            await app.request_queue.update_one(
                {"_id": request_id.inserted_id},
                {
                    "$set": {"status": "duplicate"},
                    "$push": {
                        "steps": {
                            "step": "duplicate_check",
                            "timestamp": datetime.utcnow(),
                            "success": True,
                            "message": "Lead já existe no banco de dados",
                            "document_id": str(existing_lead["_id"])
                        }
                    }
                }
            )
            
            return {
                "message": "Lead já existe no banco de dados",
                "document_id": str(existing_lead["_id"]),
                "is_duplicate": True,
                "request_id": str(request_id.inserted_id)
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
        
        # Log no console antes da inserção
        print(f"[{datetime.now().isoformat()}] INICIANDO ARMAZENAMENTO: Salvando lead {document['nome_prospect']} no MongoDB")
        
        # Inserir o lead no MongoDB
        result = await app.collection.insert_one(document)
        
        # Atualizar status na fila
        await app.request_queue.update_one(
            {"_id": request_id.inserted_id},
            {
                "$set": {"status": "stored"},
                "$push": {
                    "steps": {
                        "step": "mongodb_storage",
                        "timestamp": datetime.utcnow(),
                        "success": True,
                        "message": "Lead armazenado no MongoDB",
                        "document_id": str(result.inserted_id)
                    }
                }
            }
        )
        
        # Log no console após a inserção
        print(f"[{datetime.now().isoformat()}] ARMAZENAMENTO CONCLUÍDO: Lead salvo com ID {str(result.inserted_id)}")
        
        logger.info("Form submitted", document_id=str(result.inserted_id), request_id=str(request_id.inserted_id))
        
        # Log no console antes de chamar a API Sales Builder
        print(f"[{datetime.now().isoformat()}] INICIANDO INTEGRAÇÃO: Preparando chamada para Sales Builder API")
        
        # Chamar a API Sales Builder
        try:
            # Preparar os dados para a API Sales Builder
            sales_builder_payload = {
                "nome_prospect": document["nome_prospect"],
                "empresa_prospect": document["empresa_prospect"],
                "cargo_prospect": document["cargo_prospect"],
                "email_prospect": document["email_prospect"],
                "whatsapp_prospect": document["whatsapp_prospect"],
                "faturamento_prospect": document["faturamento_empresa"],
                "nome_vendedor": "Vagner Campos",
                "interacao": "Iniciar a conversa com lead à partir do P1"
            }
            
            # Log no console com o payload
            print(f"[{datetime.now().isoformat()}] PAYLOAD SALES BUILDER: {json.dumps(sales_builder_payload, ensure_ascii=False)}")
            
            # Atualizar status na fila
            await app.request_queue.update_one(
                {"_id": request_id.inserted_id},
                {
                    "$set": {"status": "calling_sales_builder"},
                    "$push": {
                        "steps": {
                            "step": "calling_sales_builder",
                            "timestamp": datetime.utcnow(),
                            "success": True,
                            "message": "Chamando API Sales Builder",
                            "payload": sales_builder_payload
                        }
                    }
                }
            )
            
            sales_builder_response = await call_sales_builder_api(sales_builder_payload, settings)
            
            # Log no console após a chamada
            print(f"[{datetime.now().isoformat()}] RESPOSTA SALES BUILDER: {json.dumps(sales_builder_response, ensure_ascii=False)}")
            
            # Atualizar status na fila
            await app.request_queue.update_one(
                {"_id": request_id.inserted_id},
                {
                    "$set": {
                        "status": "sales_builder_response_received",
                        "sales_builder_response": sales_builder_response
                    },
                    "$push": {
                        "steps": {
                            "step": "sales_builder_response",
                            "timestamp": datetime.utcnow(),
                            "success": "error" not in sales_builder_response,
                            "message": "Resposta recebida do Sales Builder",
                            "response": sales_builder_response
                        }
                    }
                }
            )
            
            logger.info(
                "Sales Builder API called successfully", 
                response=sales_builder_response,
                task_id=sales_builder_response.get("task_id"),
                request_id=str(request_id.inserted_id)
            )
            
            # Iniciar o processamento da task em segundo plano
            task_id = sales_builder_response.get("task_id")
            if task_id:
                # Atualizar task_id na fila
                await app.request_queue.update_one(
                    {"_id": request_id.inserted_id},
                    {
                        "$set": {"task_id": task_id},
                        "$push": {
                            "steps": {
                                "step": "task_id_received",
                                "timestamp": datetime.utcnow(),
                                "success": True,
                                "message": "Task ID recebido",
                                "task_id": task_id
                            }
                        }
                    }
                )
                
                # Log no console para o task_id
                print(f"[{datetime.now().isoformat()}] TASK ID RECEBIDO: {task_id} para o lead {document['nome_prospect']}")
                
                logger.info(
                    "Task ID recebido do Sales Builder",
                    task_id=task_id,
                    document_id=str(result.inserted_id),
                    whatsapp=clean_number,
                    request_id=str(request_id.inserted_id)
                )
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
                        # Atualizar status na fila
                        await app.request_queue.update_one(
                            {"_id": request_id.inserted_id},
                            {
                                "$set": {"status": "evolution_api_config_missing"},
                                "$push": {
                                    "steps": {
                                        "step": "evolution_api_check",
                                        "timestamp": datetime.utcnow(),
                                        "success": False,
                                        "message": "Configurações da Evolution API incompletas"
                                    }
                                }
                            }
                        )
                        
                        logger.warning(
                            "Configurações da Evolution API incompletas. Pulando processamento da task.",
                            subdomain=settings.EVO_SUBDOMAIN,
                            instance=settings.EVO_INSTANCE,
                            token_present=bool(settings.EVO_TOKEN),
                            request_id=str(request_id.inserted_id)
                        )
                        return {
                            "message": "Formulário recebido com sucesso",
                            "document_id": str(result.inserted_id),
                            "sales_builder_task_id": task_id,
                            "request_id": str(request_id.inserted_id),
                            "warning": "Processamento da task pulado devido a configurações incompletas da Evolution API"
                        }
                    
                    # Log para depuração
                    logger.info(
                        "Configurações da Evolution API",
                        subdomain=settings.EVO_SUBDOMAIN,
                        instance=settings.EVO_INSTANCE,
                        token_present=bool(settings.EVO_TOKEN),
                        request_id=str(request_id.inserted_id)
                    )
                    
                    # Atualizar status na fila
                    await app.request_queue.update_one(
                        {"_id": request_id.inserted_id},
                        {
                            "$set": {"status": "processing_task"},
                            "$push": {
                                "steps": {
                                    "step": "evolution_api_check",
                                    "timestamp": datetime.utcnow(),
                                    "success": True,
                                    "message": "Configurações da Evolution API verificadas"
                                }
                            }
                        }
                    )
                    
                    from sales_builder_status_checker import process_sales_builder_task
                    # Criar uma task em segundo plano para processar a resposta, passando as configurações e o request_id
                    process_task_with_settings = partial(
                        process_sales_builder_task, 
                        settings=settings,
                        request_id=str(request_id.inserted_id),
                        mongodb_uri=settings.MONGO_URI,
                        db_name=settings.DB_NAME
                    )
                    
                    # Criar a task em segundo plano
                    print(f"[{datetime.now().isoformat()}] INICIANDO PROCESSAMENTO ASSÍNCRONO: Task {task_id} para o número {clean_number}")
                    asyncio.create_task(process_task_with_settings(task_id))
                    
                    # Atualizar status na fila
                    await app.request_queue.update_one(
                        {"_id": request_id.inserted_id},
                        {
                            "$push": {
                                "steps": {
                                    "step": "task_processing_started",
                                    "timestamp": datetime.utcnow(),
                                    "success": True,
                                    "message": "Processamento da task iniciado em segundo plano"
                                }
                            }
                        }
                    )
                except ImportError as e:
                    # Atualizar status na fila
                    await app.request_queue.update_one(
                        {"_id": request_id.inserted_id},
                        {
                            "$set": {"status": "import_error"},
                            "$push": {
                                "steps": {
                                    "step": "import_error",
                                    "timestamp": datetime.utcnow(),
                                    "success": False,
                                    "message": f"Erro ao importar módulo: {str(e)}"
                                }
                            }
                        }
                    )
                    
                    logger.error(f"Erro ao importar módulo sales_builder_status_checker: {str(e)}", request_id=str(request_id.inserted_id))
                    logger.info(f"PYTHONPATH atual: {sys.path}", request_id=str(request_id.inserted_id))
                except Exception as e:
                    # Atualizar status na fila
                    await app.request_queue.update_one(
                        {"_id": request_id.inserted_id},
                        {
                            "$set": {"status": "task_processing_error"},
                            "$push": {
                                "steps": {
                                    "step": "task_processing_error",
                                    "timestamp": datetime.utcnow(),
                                    "success": False,
                                    "message": f"Erro ao iniciar processamento da task: {str(e)}"
                                }
                            }
                        }
                    )
                    
                    logger.error(f"Erro ao iniciar processamento da task: {str(e)}", request_id=str(request_id.inserted_id))
            
            return {
                "message": "Formulário recebido com sucesso",
                "document_id": str(result.inserted_id),
                "sales_builder_task_id": task_id,
                "request_id": str(request_id.inserted_id)
            }
        except Exception as api_error:
            # Registrar o erro, mas não falhar a requisição
            error_message = str(api_error)
            
            # Atualizar status na fila
            await app.request_queue.update_one(
                {"_id": request_id.inserted_id},
                {
                    "$set": {"status": "sales_builder_api_error"},
                    "$push": {
                        "steps": {
                            "step": "sales_builder_api_error",
                            "timestamp": datetime.utcnow(),
                            "success": False,
                            "message": f"Erro ao chamar API Sales Builder: {error_message}",
                            "error_type": type(api_error).__name__
                        }
                    }
                }
            )
            
            # Log no console para o erro
            print(f"[{datetime.now().isoformat()}] ERRO NA INTEGRAÇÃO SALES BUILDER: {error_message}")
            
            logger.error(
                "Error calling Sales Builder API", 
                error=error_message,
                error_type=type(api_error).__name__,
                error_details=repr(api_error),
                document_id=str(result.inserted_id),
                whatsapp=clean_number,
                nome_prospect=document["nome_prospect"],
                empresa_prospect=document["empresa_prospect"],
                request_id=str(request_id.inserted_id)
            )
        
            return {
                "message": "Formulário recebido com sucesso, mas houve um erro ao iniciar o processo de interação",
                "document_id": str(result.inserted_id),
                "sales_builder_error": error_message,
                "request_id": str(request_id.inserted_id)
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

# Endpoint para consultar o status de uma requisição específica
@app.get(
    "/request-status/{request_id}",
    summary="Consulta o status de uma requisição",
    response_description="Detalhes da requisição",
    tags=["Monitoramento"]
)
async def get_request_status(request_id: str):
    """
    Consulta o status de uma requisição específica.
    
    Args:
        request_id: ID da requisição
        
    Returns:
        dict: Detalhes da requisição
        
    Raises:
        HTTPException 404: Se a requisição não for encontrada
    """
    try:
        # Buscar a requisição no MongoDB
        request = await app.request_queue.find_one({"_id": ObjectId(request_id)})
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requisição não encontrada"
            )
        
        # Converter ObjectId para string
        request["_id"] = str(request["_id"])
        
        # Converter timestamps para string ISO
        if "created_at" in request:
            request["created_at"] = request["created_at"].isoformat()
        
        if "steps" in request:
            for step in request["steps"]:
                if "timestamp" in step:
                    step["timestamp"] = step["timestamp"].isoformat()
        
        return request
    except Exception as e:
        logger.error(f"Erro ao consultar status da requisição: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar status da requisição: {str(e)}"
        )

# Endpoint para listar requisições com filtros
@app.get(
    "/request-queue/",
    summary="Lista requisições na fila",
    response_description="Lista de requisições",
    tags=["Monitoramento"]
)
async def list_requests(
    status: Optional[str] = None,
    whatsapp: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """
    Lista requisições na fila com filtros opcionais.
    
    Args:
        status: Filtrar por status
        whatsapp: Filtrar por número de WhatsApp
        task_id: Filtrar por ID da task
        limit: Limite de resultados (máximo 100)
        skip: Número de resultados para pular
        
    Returns:
        dict: Lista de requisições e contagem total
    """
    try:
        # Limitar o número máximo de resultados
        if limit > 100:
            limit = 100
        
        # Construir o filtro
        filter_query = {}
        if status:
            filter_query["status"] = status
        if whatsapp:
            filter_query["whatsapp_prospect"] = whatsapp
        if task_id:
            filter_query["task_id"] = task_id
        
        # Contar o total de requisições
        total = await app.request_queue.count_documents(filter_query)
        
        # Buscar as requisições
        cursor = app.request_queue.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
        
        # Converter para lista
        requests = []
        async for request in cursor:
            # Converter ObjectId para string
            request["_id"] = str(request["_id"])
            
            # Converter timestamps para string ISO
            if "created_at" in request:
                request["created_at"] = request["created_at"].isoformat()
            
            # Simplificar a resposta para não sobrecarregar
            if "steps" in request:
                request["step_count"] = len(request["steps"])
                request["last_step"] = request["steps"][-1] if request["steps"] else None
                if request["last_step"] and "timestamp" in request["last_step"]:
                    request["last_step"]["timestamp"] = request["last_step"]["timestamp"].isoformat()
                # Remover os steps completos para reduzir o tamanho da resposta
                del request["steps"]
            
            requests.append(request)
        
        return {
            "total": total,
            "limit": limit,
            "skip": skip,
            "requests": requests
        }
    except Exception as e:
        logger.error(f"Erro ao listar requisições: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar requisições: {str(e)}"
        )

# Endpoint para obter estatísticas das requisições
@app.get(
    "/request-queue/stats",
    summary="Estatísticas das requisições",
    response_description="Estatísticas agrupadas por status",
    tags=["Monitoramento"]
)
async def get_request_stats():
    """
    Obtém estatísticas das requisições agrupadas por status.
    
    Returns:
        dict: Estatísticas das requisições
    """
    try:
        # Obter contagem por status
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        status_counts = []
        async for doc in app.request_queue.aggregate(pipeline):
            status_counts.append({
                "status": doc["_id"],
                "count": doc["count"]
            })
        
        # Obter contagem total
        total = await app.request_queue.count_documents({})
        
        # Obter contagem de erros
        error_count = await app.request_queue.count_documents({
            "status": {"$regex": "error", "$options": "i"}
        })
        
        # Obter contagem de requisições recentes (últimas 24h)
        recent_count = await app.request_queue.count_documents({
            "created_at": {"$gte": datetime.utcnow() - timedelta(days=1)}
        })
        
        return {
            "total": total,
            "error_count": error_count,
            "recent_count": recent_count,
            "by_status": status_counts
        }
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter estatísticas: {str(e)}"
        )
