import httpx
import asyncio
import logging
import time
import sys
import os
import re
import pytz
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import structlog
from datetime import datetime, timezone
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
import requests
import json

# Carregar variáveis de ambiente
load_dotenv()

# Garantir que o diretório atual esteja no PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from evo_api_v2 import EvolutionAPI
except ImportError:
    # Log detalhado em caso de erro de importação
    logging.error(f"Erro ao importar EvolutionAPI. PYTHONPATH atual: {sys.path}")
    # Caminho alternativo para importação, tentando encontrar o módulo em locais diferentes
    try:
        # Tenta importar de forma relativa ao diretório do script
        module_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, module_dir)
        from evo_api_v2 import EvolutionAPI
        logging.info(f"EvolutionAPI importado com sucesso do diretório {module_dir}")
    except ImportError as e:
        logging.error(f"Falha ao importar EvolutionAPI mesmo após ajustar PYTHONPATH: {str(e)}")
        # Fornecer uma classe stub para não quebrar a execução
        class EvolutionAPI:
            def __init__(self, settings=None):
                logging.warning("Usando versão stub da EvolutionAPI porque o módulo não pôde ser importado")
            
            def send_text_message(self, number, text, **kwargs):
                url = f"https://{self.evo_subdomain}/message/sendText/{self.evo_instance}"
                
                # Log no console
                print(f"[{datetime.now().isoformat()}] EVOLUTION API - PREPARANDO MENSAGEM: Para {number}")
                
                # Verificar se a API está configurada
                if not self.is_configured:
                    error_msg = "Evolution API não está configurada corretamente. Não é possível enviar mensagens."
                    logging.error(error_msg)
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: Configuração incompleta")
                    return {"status": "error", "message": error_msg}
                
                # Calcular o tempo de digitação
                typing_time = self.estimate_typing_time(text, typing_speed=207)
                
                payload = {
                    "number": number,
                    "text": text,
                    "delay": typing_time
                }
                
                # Adicionar opções adicionais
                for key, value in kwargs.items():
                    payload[key] = value
                
                # Configurar sessão com retry para problemas de SSL
                retry_strategy = requests.adapters.Retry(
                    total=3,  # número total de tentativas
                    backoff_factor=1,  # fator de espera entre tentativas
                    status_forcelist=[429, 500, 502, 503, 504],  # códigos de status para retry
                    allowed_methods=["POST"],  # métodos permitidos para retry
                )
                
                # Criar sessão com timeout maior e configuração de retry
                session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
                session.mount("https://", adapter)
                
                try:
                    # Log no console antes de enviar
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ENVIANDO: Mensagem para {number} (tempo de digitação: {typing_time}ms)")
                    
                    logging.info(f"[EVO_API] Enviando mensagem para {number}: '{text[:50]}...'")
                    logging.debug(f"[EVO_API] URL: {url}, Payload: {json.dumps(payload)[:200]}...")
                    
                    # Usar a sessão com retry e timeout maior
                    response = session.post(
                        url, 
                        json=payload, 
                        headers=self.headers, 
                        timeout=60  # aumentar timeout para 60 segundos
                    )
                    
                    # Tratar status 200 e 201 como sucesso (201 = Created)
                    if response.status_code in [200, 201]:
                        # Log no console após enviar com sucesso
                        print(f"[{datetime.now().isoformat()}] EVOLUTION API - ENVIADO: Status {response.status_code} para {number}")
                        
                        logging.info(f"[EVO_API] Mensagem enviada com sucesso para {number}. Status: {response.status_code}")
                        try:
                            response_data = response.json()
                            logging.debug(f"[EVO_API] Resposta: {json.dumps(response_data)[:200]}...")
                            
                            # Verificar se a resposta contém algum indicador de erro
                            if isinstance(response_data, dict) and response_data.get("error"):
                                error_msg = response_data.get("error", {}).get("message", "Erro desconhecido na resposta")
                                logging.error(f"[EVO_API] Erro na resposta: {error_msg}")
                                print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                                return {"status": "error", "message": error_msg}
                            
                            return response_data
                        except ValueError:
                            # Se não conseguir parsear JSON, retorna um dicionário com a resposta em texto
                            logging.warning(f"[EVO_API] Resposta não é um JSON válido: {response.text[:200]}...")
                            return {"status": "success", "raw_response": response.text[:200]}
                    else:
                        error_msg = f"Falha ao enviar mensagem. Status: {response.status_code}, Resposta: {response.text[:200]}"
                        logging.error(f"[EVO_API] {error_msg}")
                        print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: Resposta com status {response.status_code}")
                        # Não chamar raise_for_status() aqui para evitar exceção
                        return {"status": "error", "status_code": response.status_code, "message": error_msg}
                except requests.exceptions.Timeout:
                    error_msg = f"Timeout ao enviar mensagem para {number} após 60 segundos"
                    logging.error(f"[EVO_API] {error_msg}")
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                    return {"status": "error", "message": error_msg}
                except requests.exceptions.SSLError as e:
                    error_msg = f"Erro SSL ao enviar mensagem para {number}: {str(e)}"
                    logging.error(f"[EVO_API] {error_msg}")
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                    return {"status": "error", "message": error_msg}
                except requests.exceptions.ConnectionError as e:
                    error_msg = f"Erro de conexão ao enviar mensagem para {number}: {str(e)}"
                    logging.error(f"[EVO_API] {error_msg}")
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                    return {"status": "error", "message": error_msg}
                except requests.exceptions.RequestException as e:
                    error_msg = f"Erro na requisição ao enviar mensagem para {number}: {str(e)}"
                    logging.error(f"[EVO_API] {error_msg}")
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                    return {"status": "error", "message": error_msg}
                except Exception as e:
                    error_msg = f"Erro inesperado ao enviar mensagem para {number}: {str(e)}"
                    logging.error(f"[EVO_API] {error_msg}")
                    print(f"[{datetime.now().isoformat()}] EVOLUTION API - ERRO: {error_msg}")
                    return {"status": "error", "message": error_msg}
                finally:
                    # Fechar a sessão
                    session.close()

# Configuração de logging com structlog
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
logger = structlog.get_logger("sales_builder_status_checker")

class SalesBuilderStatusChecker:
    """
    Classe responsável por verificar o status de tasks do Sales Builder
    e enviar mensagens para os leads via WhatsApp.
    """
    
    def __init__(self, api_url: str = "https://sales-builder.ornexus.com", api_key: str = None, 
                 max_retries: int = 20, retry_delay: int = 15, timeout: int = 60, settings=None):
        """
        Inicializa o verificador de status do Sales Builder.
        
        Args:
            api_url: URL base da API Sales Builder
            api_key: Chave de API para autenticação (opcional)
            max_retries: Número máximo de tentativas em caso de erro (padrão: 20)
            retry_delay: Tempo de espera entre tentativas em segundos (padrão: 15)
            timeout: Timeout da requisição HTTP (em segundos)
            settings: Configurações da aplicação principal (opcional)
        """
        self.api_url = api_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.settings = settings
        
        # Obter a chave de API do Sales Builder
        # Prioridade: 1. Parâmetro api_key, 2. Settings, 3. Variável de ambiente
        if api_key:
            self.api_key = api_key
        elif settings and hasattr(settings, 'SALES_BUILDER_API_KEY'):
            self.api_key = settings.SALES_BUILDER_API_KEY
        else:
            # Carregar do .env via python-dotenv
            self.api_key = os.getenv("SALES_BUILDER_API_KEY")
            if not self.api_key:
                logger.warning("Chave de API do Sales Builder não encontrada. Algumas funcionalidades podem não estar disponíveis.")
        
        logger.info(f"Usando chave de API do Sales Builder: {self.api_key[:5]}...{self.api_key[-5:] if self.api_key else 'None'}")
        
        # Inicializar a Evolution API com as configurações fornecidas
        self.evo_api = EvolutionAPI(settings=settings)
        
        # Log para garantir que as configurações da Evolution API estão corretas
        logger.info(
            f"Evolution API inicializada - subdomain: {self.evo_api.evo_subdomain}, instance: {self.evo_api.evo_instance}"
        )
        
        # Configurar headers para as requisições
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Cliente HTTP
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=self.headers
        )
        
        # Referência para o MongoDB (será definida durante o processamento)
        self.mongodb = None
    
    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()
    
    async def check_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Verifica o status de uma task do Sales Builder.
        
        Args:
            task_id: ID da task a ser verificada
            
        Returns:
            Dict contendo os dados da resposta ou None em caso de erro
        """
        # Log no console
        print(f"[{datetime.now().isoformat()}] CONSULTANDO STATUS: Verificando status da task {task_id}")
        
        url = f"{self.api_url}/status/{task_id}"
        
        # Máscara para log (mostra apenas os primeiros e últimos 5 caracteres)
        masked_key = "Não definido"
        if self.api_key:
            masked_key = f"{self.api_key[:5]}...{self.api_key[-5:]}" if len(self.api_key) > 10 else "***"
        
        logger.info(
            "Verificando status da task",
            task_id=task_id,
            url=url,
            api_key_masked=masked_key
        )
        
        retries = 0
        start_time_total = datetime.utcnow()
        
        while retries < self.max_retries:
            try:
                # Log detalhado da tentativa atual
                elapsed_total = (datetime.utcnow() - start_time_total).total_seconds()
                print(f"[{datetime.now().isoformat()}] TENTATIVA {retries+1}/{self.max_retries}: Verificando status da task {task_id} (tempo total: {elapsed_total:.2f}s)")
                
                start_time = datetime.utcnow()
                logger.info(
                    "Iniciando requisição para verificar status",
                    task_id=task_id,
                    attempt=retries+1,
                    max_attempts=self.max_retries,
                    elapsed_total_seconds=elapsed_total
                )
                
                response = await self.client.get(url, timeout=self.timeout)
                elapsed_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Log da resposta para depuração
                logger.info(
                    "Resposta recebida da API Sales Builder",
                    task_id=task_id,
                    status_code=response.status_code,
                    elapsed_time_seconds=elapsed_time,
                    elapsed_total_seconds=elapsed_total
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # Verificar se o campo msg_resposta existe e não está vazio
                    has_messages = False
                    if "result" in response_data and response_data["result"]:
                        if "msg_resposta" in response_data["result"] and response_data["result"]["msg_resposta"]:
                            has_messages = True
                    
                    if has_messages:
                        logger.info(
                            "Task completada com sucesso e contém mensagens",
                            task_id=task_id,
                            status_code=response.status_code,
                            response_data=response_data,
                            elapsed_total_seconds=elapsed_total
                        )
                        print(f"[{datetime.now().isoformat()}] STATUS OBTIDO: Task {task_id} completada com sucesso após {elapsed_total:.2f}s")
                        # Incluir status_code na resposta
                        response_data["status_code"] = response.status_code
                        return response_data
                    else:
                        logger.warning(
                            "Task retornou status 200 mas não contém mensagens. Aguardando...",
                            task_id=task_id,
                            status_code=response.status_code,
                            elapsed_total_seconds=elapsed_total
                        )
                        print(f"[{datetime.now().isoformat()}] AGUARDANDO MENSAGENS: Task {task_id} retornou status 200 mas não contém mensagens. Aguardando {self.retry_delay}s para nova tentativa.")
                        
                        # Incrementar contador de tentativas
                        retries += 1
                        
                        # Verificar se atingimos o limite de tentativas
                        if retries >= self.max_retries:
                            logger.error(
                                "Número máximo de tentativas excedido aguardando mensagens",
                                task_id=task_id,
                                max_attempts=self.max_retries,
                                elapsed_total_seconds=elapsed_total
                            )
                            print(f"[{datetime.now().isoformat()}] MÁXIMO DE TENTATIVAS: {self.max_retries} tentativas de verificação da task {task_id} falharam após {elapsed_total:.2f}s")
                            # Retornar resposta com status_code para acionar o fallback
                            response_data["status_code"] = response.status_code
                            return response_data
                        
                        # Aguardar antes da próxima tentativa
                        await asyncio.sleep(self.retry_delay)
                        continue
                elif response.status_code == 403:
                    try:
                        error_data = response.json()
                        logger.error(
                            "Erro de autorização",
                            task_id=task_id,
                            status_code=response.status_code,
                            error_details=error_data,
                            elapsed_total_seconds=elapsed_total
                        )
                    except:
                        logger.error(
                            "Erro de autorização",
                            task_id=task_id,
                            status_code=response.status_code,
                            response_text=response.text,
                            elapsed_total_seconds=elapsed_total
                        )
                    print(f"[{datetime.now().isoformat()}] ERRO DE AUTORIZAÇÃO: Status 403 ao verificar task {task_id}")
                    return {"error": f"{response.status_code}: Erro de autorização", "task_id": task_id}
                else:
                    try:
                        error_data = response.json()
                        logger.warning(
                            "Resposta inesperada da API",
                            task_id=task_id,
                            status_code=response.status_code,
                            error_details=error_data,
                            elapsed_total_seconds=elapsed_total
                        )
                    except:
                        logger.warning(
                            "Resposta inesperada da API",
                            task_id=task_id,
                            status_code=response.status_code,
                            response_text=response.text,
                            elapsed_total_seconds=elapsed_total
                        )
                    print(f"[{datetime.now().isoformat()}] RESPOSTA INESPERADA: Status {response.status_code} ao verificar task {task_id}")
                
            except httpx.TimeoutException:
                elapsed_total = (datetime.utcnow() - start_time_total).total_seconds()
                logger.warning(
                    "Timeout ao verificar status da task",
                    task_id=task_id,
                    attempt=retries+1,
                    max_attempts=self.max_retries,
                    timeout_seconds=self.timeout,
                    elapsed_total_seconds=elapsed_total
                )
                retries += 1
                if retries < self.max_retries:
                    print(f"[{datetime.now().isoformat()}] TIMEOUT: Tentativa {retries}/{self.max_retries} falhou após {self.timeout}s. Aguardando {self.retry_delay}s para nova tentativa. Tempo total: {elapsed_total:.2f}s")
                    logger.info(
                        "Aguardando para nova tentativa",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay,
                        current_retry=retries,
                        elapsed_total_seconds=elapsed_total
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"[{datetime.now().isoformat()}] MÁXIMO DE TENTATIVAS: {self.max_retries} tentativas de verificação da task {task_id} falharam após {elapsed_total:.2f}s")
                    logger.error(
                        "Número máximo de tentativas excedido",
                        task_id=task_id,
                        max_attempts=self.max_retries,
                        elapsed_total_seconds=elapsed_total
                    )
                    return {"error": "Timeout ao verificar status da task", "task_id": task_id}
            
            except httpx.RequestError as e:
                elapsed_total = (datetime.utcnow() - start_time_total).total_seconds()
                logger.error(
                    "Erro de requisição ao verificar status da task",
                    task_id=task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=retries+1,
                    max_attempts=self.max_retries,
                    elapsed_total_seconds=elapsed_total
                )
                retries += 1
                if retries < self.max_retries:
                    print(f"[{datetime.now().isoformat()}] ERRO DE REQUISIÇÃO: {str(e)}. Tentativa {retries}/{self.max_retries}. Aguardando {self.retry_delay}s para nova tentativa. Tempo total: {elapsed_total:.2f}s")
                    logger.info(
                        "Aguardando para nova tentativa após erro de requisição",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay,
                        current_retry=retries,
                        elapsed_total_seconds=elapsed_total
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"[{datetime.now().isoformat()}] MÁXIMO DE TENTATIVAS: {self.max_retries} tentativas de verificação da task {task_id} falharam com erro de requisição após {elapsed_total:.2f}s")
                    logger.error(
                        "Número máximo de tentativas excedido após erros de requisição",
                        task_id=task_id,
                        max_attempts=self.max_retries,
                        error=str(e),
                        elapsed_total_seconds=elapsed_total
                    )
                    return {"error": f"Erro de requisição: {str(e)}", "task_id": task_id}
            
            except Exception as e:
                elapsed_total = (datetime.utcnow() - start_time_total).total_seconds()
                logger.error(
                    "Exceção inesperada ao verificar status da task",
                    task_id=task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=retries+1,
                    max_attempts=self.max_retries,
                    elapsed_total_seconds=elapsed_total
                )
                retries += 1
                if retries < self.max_retries:
                    print(f"[{datetime.now().isoformat()}] EXCEÇÃO INESPERADA: {str(e)}. Tentativa {retries}/{self.max_retries}. Aguardando {self.retry_delay}s para nova tentativa. Tempo total: {elapsed_total:.2f}s")
                    logger.info(
                        "Aguardando para nova tentativa após exceção",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay,
                        current_retry=retries,
                        elapsed_total_seconds=elapsed_total
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"[{datetime.now().isoformat()}] MÁXIMO DE TENTATIVAS: {self.max_retries} tentativas de verificação da task {task_id} falharam com exceção inesperada após {elapsed_total:.2f}s")
                    logger.error(
                        "Número máximo de tentativas excedido após exceções",
                        task_id=task_id,
                        max_attempts=self.max_retries,
                        error=str(e),
                        elapsed_total_seconds=elapsed_total
                    )
                    return {"error": f"Exceção: {str(e)}", "task_id": task_id}
        
        # Este código não deve ser alcançado devido aos retornos nos blocos de exceção
        return {"error": "Falha ao verificar status da task após múltiplas tentativas", "task_id": task_id}
    
    async def insert_chat_history(self, whatsapp: str, message: str, task_data: Dict[str, Any]) -> Dict:
        """
        Insere o histórico de mensagens no MongoDB.
        
        Args:
            whatsapp: Número de WhatsApp do destinatário
            message: Mensagem enviada
            task_data: Dados da task do Sales Builder
            
        Returns:
            Dict com ID do documento inserido ou erro
        """
        try:
            # Verificar se temos acesso ao MongoDB
            mongodb_initialized = hasattr(self, 'mongodb') and self.mongodb is not None
            if not mongodb_initialized:
                # Tentar obter configurações do MongoDB de diferentes fontes
                mongo_uri = None
                db_name = None
                
                # 1. Verificar se as configurações estão disponíveis no objeto settings
                if self.settings:
                    if hasattr(self.settings, 'MONGO_URI'):
                        mongo_uri = self.settings.MONGO_URI
                    if hasattr(self.settings, 'DB_NAME'):
                        db_name = self.settings.DB_NAME
                
                # 2. Se não encontrou nas configurações, tentar variáveis de ambiente
                if not mongo_uri:
                    mongo_uri = os.getenv('MONGO_URI')
                if not db_name:
                    db_name = os.getenv('DB_NAME')
                
                # Verificar se temos as informações necessárias
                if not mongo_uri or not db_name:
                    logger.warning(
                        "Configurações do MongoDB não disponíveis. Histórico não será salvo.",
                        whatsapp=whatsapp,
                        message_preview=message[:50] + "..." if len(message) > 50 else message
                    )
                    print(f"[{datetime.now().isoformat()}] AVISO: Configurações do MongoDB não disponíveis. Histórico não será salvo.")
                    return {"warning": "MongoDB não configurado. Histórico não foi salvo."}
                
                # Inicializar conexão com MongoDB
                try:
                    logger.info(
                        "Inicializando conexão com MongoDB",
                        mongo_uri_masked=f"{mongo_uri[:15]}...{mongo_uri[-5:]}" if len(mongo_uri) > 20 else "***",
                        db_name=db_name
                    )
                    self.mongodb_client = AsyncIOMotorClient(mongo_uri)
                    self.mongodb = self.mongodb_client[db_name]
                except Exception as e:
                    logger.error(
                        "Erro ao conectar ao MongoDB",
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    print(f"[{datetime.now().isoformat()}] ERRO DE CONEXÃO: Falha ao conectar ao MongoDB: {str(e)}")
                    return {"error": f"Falha ao conectar ao MongoDB: {str(e)}"}
            
            # Extrair dados relevantes da task
            result = task_data.get("result", {})
            
            # Converter UTC para São Paulo (UTC-3)
            TIMEZONE_SP = pytz.timezone('America/Sao_Paulo')
            data_hora_sp = datetime.now(timezone.utc).astimezone(TIMEZONE_SP)
            
            # Preparar documento para inserção
            document = {
                'session_id': whatsapp,
                'status': result.get('status', ''),
                'data_hora': data_hora_sp.isoformat(),  # Horário de São Paulo
                'p_atual': result.get('p_atual', ''),
                'p_proxima': result.get('p_proxima', ''),
                'interacao': result.get('interacao', ''),
                'tipo_interacao': result.get('tipo_interacao', 'whatsapp'),
                'msg_resposta': [message],  # Mensagem que acabou de ser enviada
                'periodo_agendamento': result.get('periodo_agendamento', ''),
                'horario_agendamento': result.get('horario_agendamento', ''),
                'dia_agendamento': result.get('dia_agendamento', ''),
                'link_agendamento_google_calendar': result.get('link_agendamento_google_calendar', 'NULL'),
                'link_meet_google': result.get('link_meet_google', 'NULL')
            }
            
            # Log para depuração
            logger.info(
                "Inserindo histórico de chat no MongoDB",
                session_id=whatsapp,
                message_preview=message[:50] + "..." if len(message) > 50 else message
            )
            print(f"[{datetime.now().isoformat()}] INSERINDO HISTÓRICO: Salvando mensagem para {whatsapp} no MongoDB")
            
            # Inserir documento na collection sdr_chat_histories
            try:
                result = await self.mongodb.sdr_chat_histories.insert_one(document)
                
                # Log de sucesso
                logger.info(
                    "Histórico de chat inserido com sucesso",
                    session_id=whatsapp,
                    document_id=str(result.inserted_id)
                )
                print(f"[{datetime.now().isoformat()}] HISTÓRICO SALVO: ID do documento {str(result.inserted_id)}")
                
                return {"inserted_id": str(result.inserted_id)}
            except Exception as e:
                logger.error(
                    "Erro ao inserir documento no MongoDB",
                    error=str(e),
                    error_type=type(e).__name__,
                    whatsapp=whatsapp
                )
                print(f"[{datetime.now().isoformat()}] ERRO AO INSERIR: Falha ao salvar histórico no MongoDB: {str(e)}")
                return {"error": f"Falha ao inserir documento: {str(e)}"}
            
        except Exception as e:
            # Log de erro
            logger.error(
                "Erro ao inserir histórico de chat",
                error=str(e),
                error_type=type(e).__name__,
                whatsapp=whatsapp
            )
            print(f"[{datetime.now().isoformat()}] ERRO AO SALVAR HISTÓRICO: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            return {"error": f"Falha ao inserir histórico: {str(e)}"}

    async def process_task_response(self, task_data: Dict[str, Any]) -> bool:
        """
        Processa a resposta de uma task do Sales Builder.
        
        Args:
            task_data: Dados da task a ser processada
            
        Returns:
            bool: True se o processamento foi bem-sucedido, False caso contrário
        """
        try:
            # Verificar se há erro na resposta
            if "error" in task_data:
                logger.error(f"Erro na resposta da API: {task_data.get('error')}")
                print(f"[{datetime.now().isoformat()}] ERRO NA RESPOSTA: {task_data.get('error')}")
                return False
                
            # Verificar se a Evolution API está configurada
            if not hasattr(self.evo_api, 'is_configured') or not self.evo_api.is_configured:
                logger.warning("Evolution API não está configurada corretamente. Não é possível enviar mensagens.")
                print(f"[{datetime.now().isoformat()}] CONFIGURAÇÃO INCOMPLETA: Evolution API não está configurada corretamente")
                return False
                
            # Extrair dados da task
            task_id = task_data.get("task_id")
            result = task_data.get("result", {})
            
            # Verificar se temos os dados necessários
            if not task_id or not result:
                logger.error(f"Dados incompletos na task: {task_data}")
                print(f"[{datetime.now().isoformat()}] DADOS INCOMPLETOS: Faltam informações na resposta da task {task_id}")
                return False
            
            # Extrair o número de WhatsApp e as mensagens
            whatsapp = result.get("whatsapp_prospect")
            messages = result.get("msg_resposta", [])
            
            # Fallback: Se a task retornou 200 e msg_resposta está vazia, usar mensagens padrão
            if task_data.get("status_code") == 200 and isinstance(messages, list) and len(messages) == 0:
                logger.info("Task retornou 200 com lista de mensagens vazia. Usando mensagens padrão de fallback.")
                print(f"[{datetime.now().isoformat()}] FALLBACK: Task retornou 200 com msg_resposta vazia. Usando mensagens padrão.")
                messages = [
                    "Oi, tudo bem? Aqui é o Vagner Campos, fundador da Arduus. Vi seu interesse em inovação e transformação digital no LinkedIn, especialmente na área de IA.",
                    "Percebi que você entrou em contato conosco para conhecer mais sobre nossas soluções de IA generativa. Gostaria de saber mais sobre como podemos impulsionar sua transformação digital?"
                ]
                
                # Atualizar o task_data com as mensagens de fallback para que sejam armazenadas na fila
                if "result" in task_data:
                    task_data["result"]["msg_resposta"] = messages
                    task_data["fallback_messages_used"] = True
            elif not messages:
                logger.error(f"Dados incompletos na task: {task_data}")
                print(f"[{datetime.now().isoformat()}] DADOS INCOMPLETOS: Faltam mensagens na task {task_id}")
                return False
            
            if not whatsapp:
                logger.error(f"Dados incompletos na task: {task_data}")
                print(f"[{datetime.now().isoformat()}] DADOS INCOMPLETOS: Falta número de WhatsApp na task {task_id}")
                return False
            
            # Verificar se o número de WhatsApp está em um formato válido
            if not whatsapp.isdigit():
                logger.warning(f"Número de WhatsApp inválido: {whatsapp}. Tentando limpar...")
                print(f"[{datetime.now().isoformat()}] NÚMERO INVÁLIDO: Tentando limpar o número {whatsapp}")
                # Tentar limpar o número
                whatsapp = re.sub(r'\D', '', whatsapp)
                if not whatsapp.isdigit():
                    logger.error(f"Número de WhatsApp ainda inválido após limpeza: {whatsapp}")
                    print(f"[{datetime.now().isoformat()}] NÚMERO INVÁLIDO: Número {whatsapp} ainda inválido após limpeza")
                    return False
            
            # Log no console antes de enviar mensagens
            print(f"[{datetime.now().isoformat()}] INICIANDO ENVIO: Preparando para enviar {len(messages)} mensagens para {whatsapp}")
            
            # Rastrear o sucesso do envio de mensagens
            all_messages_sent_successfully = True
            successful_messages_count = 0
            
            # Enviar cada mensagem para o WhatsApp
            for i, message in enumerate(messages, 1):
                if message and isinstance(message, str):
                    # Log no console antes de enviar cada mensagem
                    print(f"[{datetime.now().isoformat()}] ENVIANDO MENSAGEM {i}/{len(messages)}: Para {whatsapp} - '{message[:50]}...'")
                    
                    # Enviar mensagem e capturar o resultado
                    result_send = self.evo_api.send_text_message(
                        number=whatsapp,
                        text=message
                    )
                    
                    # Verificar se o resultado indica erro
                    if isinstance(result_send, dict) and result_send.get("status") == "error":
                        error_message = result_send.get('message', 'Erro desconhecido')
                        logger.error(f"Erro ao enviar mensagem para {whatsapp}: {error_message}")
                        print(f"[{datetime.now().isoformat()}] ERRO AO ENVIAR MENSAGEM: {error_message}")
                        all_messages_sent_successfully = False
                        # Continuar tentando enviar as próximas mensagens
                        continue
                    
                    # Log no console após enviar cada mensagem com sucesso
                    print(f"[{datetime.now().isoformat()}] MENSAGEM ENVIADA {i}/{len(messages)}: Para {whatsapp}")
                    successful_messages_count += 1
                    
                    # Inserir histórico de chat no MongoDB
                    await self.insert_chat_history(whatsapp, message, task_data)
                    
                    logger.info(f"Mensagem enviada para {whatsapp}: {message[:50]}...")
            
            # Log no console após tentar enviar todas as mensagens
            if all_messages_sent_successfully:
                print(f"[{datetime.now().isoformat()}] ENVIO CONCLUÍDO: Todas as {len(messages)} mensagens foram enviadas para {whatsapp}")
                logger.info(f"Processamento da task {task_id} concluído com sucesso")
                return True
            else:
                print(f"[{datetime.now().isoformat()}] ENVIO PARCIAL: Apenas {successful_messages_count} de {len(messages)} mensagens foram enviadas para {whatsapp}")
                logger.warning(f"Processamento da task {task_id} concluído parcialmente. Apenas {successful_messages_count} de {len(messages)} mensagens foram enviadas.")
                return False
            
        except Exception as e:
            logger.error(f"Erro ao processar resposta da task: {str(e)}")
            print(f"[{datetime.now().isoformat()}] ERRO NO PROCESSAMENTO: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"[{datetime.now().isoformat()}] TRACEBACK: {traceback.format_exc()}")
            return False
    
    async def check_and_process_task(self, task_id: str, request_queue=None, request_id=None) -> bool:
        """
        Verifica o status de uma task e processa a resposta.
        
        Args:
            task_id: ID da task a ser verificada e processada
            request_queue: Referência à coleção de fila de requisições (opcional)
            request_id: ID da requisição na fila (opcional)
            
        Returns:
            bool: True se o processamento foi bem-sucedido, False caso contrário
        """
        logger.info(
            "Iniciando verificação e processamento da task",
            task_id=task_id
        )
        
        start_time = datetime.utcnow()
        
        try:
            # Verificar status da task
            task_data = await self.check_task_status(task_id)
            
            if not task_data:
                logger.error(
                    "Não foi possível obter dados da task",
                    task_id=task_id,
                    elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                )
                
                # Atualizar status na fila se disponível
                if request_queue is not None and request_id is not None:
                    await request_queue.update_one(
                        {"_id": ObjectId(request_id)},
                        {
                            "$set": {"status": "task_check_failed"},
                            "$push": {
                                "steps": {
                                    "step": "task_check_failed",
                                    "timestamp": datetime.utcnow(),
                                    "success": False,
                                    "message": "Não foi possível obter dados da task"
                                }
                            }
                        }
                    )
                
                return False
            
            # Verificar se há erro na resposta
            if "error" in task_data:
                error_message = task_data.get('error', 'Erro desconhecido')
                logger.error(
                    "Erro ao verificar status da task",
                    task_id=task_id,
                    error=error_message,
                    elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                )
                
                # Verificar se é um erro de autorização (403) e tentar atualizar a chave de API
                if "403" in task_data.get('error', ''):
                    logger.warning(
                        "Erro de autorização (403). Tentando atualizar a chave de API.",
                        task_id=task_id
                    )
                    
                    # Tentar obter uma chave de API alternativa do .env
                    alt_api_key = os.getenv("SALES_BUILDER_API_KEY_ALT")
                    if alt_api_key:
                        logger.info(
                            "Chave de API alternativa encontrada. Tentando novamente.",
                            task_id=task_id
                        )
                        
                        # Atualizar a chave de API do verificador
                        self.api_key = alt_api_key
                        self.headers["Authorization"] = f"Bearer {alt_api_key}"
                        
                        # Recriar o cliente HTTP com os novos headers
                        await self.client.aclose()
                        self.client = httpx.AsyncClient(
                            timeout=self.timeout,
                            headers=self.headers
                        )
                        
                        # Tentar verificar o status novamente
                        logger.info(
                            "Tentando verificar status novamente com a nova chave de API",
                            task_id=task_id
                        )
                        task_data = await self.check_task_status(task_id)
                        
                        if "error" in task_data:
                            logger.error(
                                "Falha mesmo após atualizar a chave de API",
                                task_id=task_id,
                                error=task_data.get('error'),
                                elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                            )
                            
                            # Atualizar status na fila se disponível
                            if request_queue is not None and request_id is not None:
                                await request_queue.update_one(
                                    {"_id": ObjectId(request_id)},
                                    {
                                        "$set": {"status": "api_key_error"},
                                        "$push": {
                                            "steps": {
                                                "step": "api_key_error",
                                                "timestamp": datetime.utcnow(),
                                                "success": False,
                                                "message": f"Erro de autorização persistente: {task_data.get('error')}"
                                            }
                                        }
                                    }
                                )
                            
                            return False
                    else:
                        logger.error(
                            "Não foi possível encontrar uma chave de API alternativa no .env",
                            task_id=task_id,
                            elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                        )
                        
                        # Atualizar status na fila se disponível
                        if request_queue is not None and request_id is not None:
                            await request_queue.update_one(
                                {"_id": ObjectId(request_id)},
                                {
                                    "$set": {"status": "api_key_error"},
                                    "$push": {
                                        "steps": {
                                            "step": "api_key_error",
                                            "timestamp": datetime.utcnow(),
                                            "success": False,
                                            "message": "Não foi possível encontrar uma chave de API alternativa"
                                        }
                                    }
                                }
                            )
                        
                        return False
                else:
                    # Atualizar status na fila se disponível
                    if request_queue is not None and request_id is not None:
                        await request_queue.update_one(
                            {"_id": ObjectId(request_id)},
                            {
                                "$set": {"status": "task_check_error"},
                                "$push": {
                                    "steps": {
                                        "step": "task_check_error",
                                        "timestamp": datetime.utcnow(),
                                        "success": False,
                                        "message": f"Erro ao verificar status: {error_message}"
                                    }
                                }
                            }
                        )
                    
                    return False
            
            # Armazenar a msg_resposta na tabela da fila de processamento se disponível
            if request_queue is not None and request_id is not None and "result" in task_data and task_data["result"]:
                # Extrair as mensagens da resposta
                messages = []
                if "msg_resposta" in task_data["result"] and task_data["result"]["msg_resposta"]:
                    messages = task_data["result"]["msg_resposta"]
                
                # Atualizar a fila com as mensagens
                if messages:
                    logger.info(
                        "Armazenando mensagens na fila de processamento",
                        task_id=task_id,
                        request_id=request_id,
                        message_count=len(messages)
                    )
                    print(f"[{datetime.now().isoformat()}] ARMAZENANDO MENSAGENS: Salvando {len(messages)} mensagens na fila para o task_id {task_id}")
                    
                    try:
                        await request_queue.update_one(
                            {"_id": ObjectId(request_id)},
                            {
                                "$set": {
                                    "messages": messages,
                                    "message_count": len(messages)
                                },
                                "$push": {
                                    "steps": {
                                        "step": "messages_stored",
                                        "timestamp": datetime.utcnow(),
                                        "success": True,
                                        "message": f"Armazenadas {len(messages)} mensagens da resposta",
                                        "message_preview": messages[0][:50] + "..." if len(messages[0]) > 50 else messages[0]
                                    }
                                }
                            }
                        )
                    except Exception as e:
                        logger.error(
                            "Erro ao armazenar mensagens na fila",
                            task_id=task_id,
                            request_id=request_id,
                            error=str(e),
                            error_type=type(e).__name__
                        )
                        print(f"[{datetime.now().isoformat()}] ERRO AO ARMAZENAR MENSAGENS: {str(e)}")
            
            # Processar resposta da task
            success = await self.process_task_response(task_data)
            
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Atualizar status na fila com base no resultado do processamento
            if request_queue is not None and request_id is not None:
                if success:
                    await request_queue.update_one(
                        {"_id": ObjectId(request_id)},
                        {
                            "$set": {"status": "completed"},
                            "$push": {
                                "steps": {
                                    "step": "messages_sent",
                                    "timestamp": datetime.utcnow(),
                                    "success": True,
                                    "message": f"Todas as mensagens foram enviadas com sucesso",
                                    "elapsed_time_seconds": elapsed_time
                                }
                            }
                        }
                    )
                else:
                    await request_queue.update_one(
                        {"_id": ObjectId(request_id)},
                        {
                            "$set": {"status": "message_send_failed"},
                            "$push": {
                                "steps": {
                                    "step": "message_send_failed",
                                    "timestamp": datetime.utcnow(),
                                    "success": False,
                                    "message": "Falha ao enviar uma ou mais mensagens",
                                    "elapsed_time_seconds": elapsed_time
                                }
                            }
                        }
                    )
            
            logger.info(
                "Processamento da task concluído",
                task_id=task_id,
                success=success,
                elapsed_time_seconds=elapsed_time
            )
            
            return success
            
        except Exception as e:
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(
                "Erro ao verificar e processar task",
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
                elapsed_time_seconds=elapsed_time
            )
            
            # Atualizar status na fila em caso de exceção
            if request_queue is not None and request_id is not None:
                await request_queue.update_one(
                    {"_id": ObjectId(request_id)},
                    {
                        "$set": {"status": "processing_exception"},
                        "$push": {
                            "steps": {
                                "step": "processing_exception",
                                "timestamp": datetime.utcnow(),
                                "success": False,
                                "message": f"Exceção durante o processamento: {str(e)}",
                                "elapsed_time_seconds": elapsed_time
                            }
                        }
                    }
                )
            
            return False


async def process_sales_builder_task(task_id: str, settings=None, request_id=None, mongodb_uri=None, db_name=None) -> bool:
    """
    Função principal para processar uma task do Sales Builder.
    
    Args:
        task_id: ID da task a ser processada
        settings: Configurações da aplicação principal (opcional)
        request_id: ID da requisição na fila (opcional)
        mongodb_uri: URI de conexão com o MongoDB (opcional)
        db_name: Nome do banco de dados (opcional)
        
    Returns:
        bool: True se o processamento foi bem-sucedido, False caso contrário
    """
    logger.info(
        "Iniciando processamento de task do Sales Builder",
        task_id=task_id,
        settings_provided=settings is not None,
        request_id=request_id
    )
    
    # Log no console
    print(f"[{datetime.now().isoformat()}] VERIFICAÇÃO INICIADA: Processando task {task_id} do Sales Builder")
    
    start_time = datetime.utcnow()
    
    # Inicializar conexão com MongoDB para atualizar a fila se request_id for fornecido
    request_queue = None
    if request_id and mongodb_uri and db_name:
        try:
            mongodb_client = AsyncIOMotorClient(mongodb_uri)
            db = mongodb_client[db_name]
            request_queue = db["request_queue"]
            
            # Atualizar status na fila
            await request_queue.update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {"status": "task_processing_started"},
                    "$push": {
                        "steps": {
                            "step": "task_processing_started",
                            "timestamp": datetime.utcnow(),
                            "success": True,
                            "message": "Processamento da task iniciado"
                        }
                    }
                }
            )
        except Exception as e:
            logger.error(
                "Erro ao conectar ao MongoDB para atualizar fila",
                error=str(e),
                error_type=type(e).__name__,
                request_id=request_id
            )
    
    # Criar o verificador com as configurações fornecidas
    checker = SalesBuilderStatusChecker(settings=settings)
    try:
        # Atualizar status na fila
        if request_queue is not None and request_id is not None:
            await request_queue.update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {"status": "checking_task_status"},
                    "$push": {
                        "steps": {
                            "step": "checking_task_status",
                            "timestamp": datetime.utcnow(),
                            "success": True,
                            "message": "Verificando status da task"
                        }
                    }
                }
            )
        
        # Chamar check_and_process_task com os parâmetros da fila
        result = await checker.check_and_process_task(task_id, request_queue, request_id)
        
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            "Processamento de task do Sales Builder concluído",
            task_id=task_id,
            result=result,
            elapsed_time_seconds=elapsed_time,
            request_id=request_id
        )
        
        # Log no console
        print(f"[{datetime.now().isoformat()}] VERIFICAÇÃO CONCLUÍDA: Task {task_id} processada {'com sucesso' if result else 'com falha'} em {elapsed_time:.2f} segundos")
        
        # Atualizar status na fila
        if request_queue is not None and request_id is not None:
            await request_queue.update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {"status": "task_processing_completed", "task_result": result},
                    "$push": {
                        "steps": {
                            "step": "task_processing_completed",
                            "timestamp": datetime.utcnow(),
                            "success": result,
                            "message": f"Processamento da task concluído {'com sucesso' if result else 'com falha'}",
                            "elapsed_time_seconds": elapsed_time
                        }
                    }
                }
            )
        
        return result
    except Exception as e:
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            "Erro durante o processamento de task do Sales Builder",
            task_id=task_id,
            error=str(e),
            error_type=type(e).__name__,
            elapsed_time_seconds=elapsed_time,
            request_id=request_id
        )
        
        # Log no console
        print(f"[{datetime.now().isoformat()}] ERRO NA VERIFICAÇÃO: Falha ao processar task {task_id}: {str(e)}")
        
        # Atualizar status na fila
        if request_queue is not None:
            await request_queue.update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {"status": "task_processing_error"},
                    "$push": {
                        "steps": {
                            "step": "task_processing_error",
                            "timestamp": datetime.utcnow(),
                            "success": False,
                            "message": f"Erro durante o processamento: {str(e)}",
                            "error_type": type(e).__name__,
                            "elapsed_time_seconds": elapsed_time
                        }
                    }
                }
            )
        
        return False
    finally:
        await checker.close()
        
        # Fechar conexão com MongoDB
        if request_queue is not None and 'mongodb_client' in locals():
            mongodb_client.close()


# Exemplo de uso
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python sales_builder_status_checker.py <task_id>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    
    async def main():
        success = await process_sales_builder_task(task_id)
        if success:
            print(f"Task {task_id} processada com sucesso")
        else:
            print(f"Falha ao processar task {task_id}")
    
    asyncio.run(main()) 