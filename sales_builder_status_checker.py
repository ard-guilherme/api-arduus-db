import httpx
import asyncio
import logging
import time
import sys
import os
import re
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import structlog
from datetime import datetime

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
                logging.warning(f"Stub: Enviando mensagem para {number}: {text[:50]}...")
                return {"status": "error", "message": "EvolutionAPI não está disponível"}

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
                 max_retries: int = 5, retry_delay: int = 10, timeout: int = 60, settings=None):
        """
        Inicializa o verificador de status do Sales Builder.
        
        Args:
            api_url: URL base da API Sales Builder
            api_key: Chave de API para autenticação (opcional)
            max_retries: Número máximo de tentativas em caso de erro
            retry_delay: Tempo de espera entre tentativas (em segundos)
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
        while retries < self.max_retries:
            try:
                start_time = datetime.utcnow()
                logger.info(
                    "Iniciando requisição para verificar status",
                    task_id=task_id,
                    attempt=retries+1,
                    max_attempts=self.max_retries
                )
                
                response = await self.client.get(url, timeout=self.timeout)
                elapsed_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Log da resposta para depuração
                logger.info(
                    "Resposta recebida da API Sales Builder",
                    task_id=task_id,
                    status_code=response.status_code,
                    elapsed_time_seconds=elapsed_time
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info(
                        "Task completada com sucesso",
                        task_id=task_id,
                        status_code=response.status_code,
                        response_data=response_data
                    )
                    return response_data
                elif response.status_code == 403:
                    try:
                        error_data = response.json()
                        logger.error(
                            "Erro de autorização",
                            task_id=task_id,
                            status_code=response.status_code,
                            error_details=error_data
                        )
                    except:
                        logger.error(
                            "Erro de autorização",
                            task_id=task_id,
                            status_code=response.status_code,
                            response_text=response.text
                        )
                    return {"error": f"{response.status_code}: Erro de autorização", "task_id": task_id}
                else:
                    try:
                        error_data = response.json()
                        logger.warning(
                            "Resposta inesperada da API",
                            task_id=task_id,
                            status_code=response.status_code,
                            error_details=error_data
                        )
                    except:
                        logger.warning(
                            "Resposta inesperada da API",
                            task_id=task_id,
                            status_code=response.status_code,
                            response_text=response.text
                        )
                
            except httpx.TimeoutException:
                logger.warning(
                    "Timeout ao verificar status da task",
                    task_id=task_id,
                    attempt=retries+1,
                    max_attempts=self.max_retries,
                    timeout_seconds=self.timeout
                )
                retries += 1
                if retries < self.max_retries:
                    logger.info(
                        "Aguardando para nova tentativa",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(
                        "Número máximo de tentativas excedido",
                        task_id=task_id,
                        max_attempts=self.max_retries
                    )
                    return {"error": "Timeout ao verificar status da task", "task_id": task_id}
            
            except httpx.RequestError as e:
                logger.error(
                    "Erro de requisição ao verificar status da task",
                    task_id=task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=retries+1,
                    max_attempts=self.max_retries
                )
                retries += 1
                if retries < self.max_retries:
                    logger.info(
                        "Aguardando para nova tentativa após erro de requisição",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(
                        "Número máximo de tentativas excedido após erros de requisição",
                        task_id=task_id,
                        max_attempts=self.max_retries,
                        error=str(e)
                    )
                    return {"error": f"Erro de requisição: {str(e)}", "task_id": task_id}
            
            except Exception as e:
                logger.error(
                    "Exceção inesperada ao verificar status da task",
                    task_id=task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=retries+1,
                    max_attempts=self.max_retries
                )
                retries += 1
                if retries < self.max_retries:
                    logger.info(
                        "Aguardando para nova tentativa após exceção",
                        task_id=task_id,
                        retry_delay_seconds=self.retry_delay
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(
                        "Número máximo de tentativas excedido após exceções",
                        task_id=task_id,
                        max_attempts=self.max_retries,
                        error=str(e)
                    )
                    return {"error": f"Exceção: {str(e)}", "task_id": task_id}
        
        # Este código não deve ser alcançado devido aos retornos nos blocos de exceção
        return {"error": "Falha ao verificar status da task após múltiplas tentativas", "task_id": task_id}
    
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
                return False
                
            # Verificar se a Evolution API está configurada
            if not hasattr(self.evo_api, 'is_configured') or not self.evo_api.is_configured:
                logger.warning("Evolution API não está configurada corretamente. Não é possível enviar mensagens.")
                return False
                
            # Extrair dados da task
            task_id = task_data.get("task_id")
            result = task_data.get("result", {})
            
            # Verificar se temos os dados necessários
            if not task_id or not result:
                logger.error(f"Dados incompletos na task: {task_data}")
                return False
            
            # Extrair o número de WhatsApp e as mensagens
            whatsapp = result.get("whatsapp_prospect")
            messages = result.get("msg_resposta", [])
            
            if not whatsapp or not messages:
                logger.error(f"Dados incompletos na task: {task_data}")
                return False
                
            # Verificar se o número de WhatsApp está em um formato válido
            if not whatsapp.isdigit():
                logger.warning(f"Número de WhatsApp inválido: {whatsapp}. Tentando limpar...")
                # Tentar limpar o número
                whatsapp = re.sub(r'\D', '', whatsapp)
                if not whatsapp.isdigit():
                    logger.error(f"Número de WhatsApp ainda inválido após limpeza: {whatsapp}")
                    return False
            
            # Enviar cada mensagem para o WhatsApp
            for message in messages:
                if message and isinstance(message, str):
                    await self.evo_api.send_text_message(
                        number=whatsapp,
                        text=message
                    )
                    logger.info(f"Mensagem enviada para {whatsapp}: {message[:50]}...")
            
            logger.info(f"Processamento da task {task_id} concluído com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao processar resposta da task: {str(e)}")
            return False
    
    async def check_and_process_task(self, task_id: str) -> bool:
        """
        Verifica o status de uma task e processa a resposta.
        
        Args:
            task_id: ID da task a ser verificada e processada
            
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
                return False
            
            # Verificar se há erro na resposta
            if "error" in task_data:
                logger.error(
                    "Erro ao verificar status da task",
                    task_id=task_id,
                    error=task_data.get('error'),
                    elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                )
                
                # Se for erro de autorização, tentar recarregar a chave do .env
                if "autorização" in task_data.get('error', '').lower() or "403" in task_data.get('error', ''):
                    logger.info(
                        "Tentando recarregar a chave de API do .env",
                        task_id=task_id
                    )
                    
                    # Recarregar o .env para garantir que temos a chave mais recente
                    load_dotenv(override=True)
                    env_api_key = os.getenv("SALES_BUILDER_API_KEY")
                    
                    if env_api_key and env_api_key != self.api_key:
                        # Mascarar a chave para o log
                        masked_old_key = f"{self.api_key[:5]}...{self.api_key[-5:]}" if self.api_key and len(self.api_key) > 10 else "***"
                        masked_new_key = f"{env_api_key[:5]}...{env_api_key[-5:]}" if len(env_api_key) > 10 else "***"
                        
                        logger.info(
                            "Encontrada nova chave de API no .env",
                            task_id=task_id,
                            old_key_masked=masked_old_key,
                            new_key_masked=masked_new_key
                        )
                        
                        self.api_key = env_api_key
                        self.headers["Authorization"] = f"Bearer {self.api_key}"
                        self.client = httpx.AsyncClient(
                            timeout=self.timeout,
                            headers=self.headers
                        )
                        
                        # Tentar novamente
                        logger.info(
                            "Tentando verificar o status novamente com a nova chave",
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
                            return False
                    else:
                        logger.error(
                            "Não foi possível encontrar uma chave de API alternativa no .env",
                            task_id=task_id,
                            elapsed_time_seconds=(datetime.utcnow() - start_time).total_seconds()
                        )
                        return False
                else:
                    return False
            
            # Processar resposta da task
            success = await self.process_task_response(task_data)
            
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
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
            return False


async def process_sales_builder_task(task_id: str, settings=None) -> bool:
    """
    Função principal para processar uma task do Sales Builder.
    
    Args:
        task_id: ID da task a ser processada
        settings: Configurações da aplicação principal (opcional)
        
    Returns:
        bool: True se o processamento foi bem-sucedido, False caso contrário
    """
    logger.info(
        "Iniciando processamento de task do Sales Builder",
        task_id=task_id,
        settings_provided=settings is not None
    )
    
    start_time = datetime.utcnow()
    
    # Criar o verificador com as configurações fornecidas
    checker = SalesBuilderStatusChecker(settings=settings)
    try:
        result = await checker.check_and_process_task(task_id)
        
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            "Processamento de task do Sales Builder concluído",
            task_id=task_id,
            result=result,
            elapsed_time_seconds=elapsed_time
        )
        
        return result
    except Exception as e:
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            "Erro durante o processamento de task do Sales Builder",
            task_id=task_id,
            error=str(e),
            error_type=type(e).__name__,
            elapsed_time_seconds=elapsed_time
        )
        return False
    finally:
        await checker.close()


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