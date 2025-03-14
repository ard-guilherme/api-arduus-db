import httpx
import asyncio
import logging
import time
import sys
import os
import re
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

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

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sales_builder_status_checker")

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
        if settings and hasattr(settings, 'SALES_BUILDER_API_KEY'):
            self.api_key = settings.SALES_BUILDER_API_KEY
        else:
            self.api_key = api_key or os.getenv("SALES_BUILDER_API_KEY", "7rQa9a0gGOz0jsG0EAlI3TxilYE2Y5pX")
        
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
        logger.info(f"Verificando status da task {task_id} na URL: {url}")
        logger.info(f"Headers de autorização: {self.headers.get('Authorization', 'Não definido').replace(self.api_key, '***')}")
        
        retries = 0
        while retries < self.max_retries:
            try:
                logger.info(f"Tentativa {retries+1} de {self.max_retries} para verificar task {task_id}")
                response = await self.client.get(url, timeout=self.timeout)
                
                # Log da resposta para depuração
                logger.info(f"Resposta da API: Status {response.status_code}")
                
                if response.status_code == 200:
                    logger.info(f"Task {task_id} completada com sucesso")
                    response_data = response.json()
                    logger.info(f"Dados da resposta: {response_data}")
                    return response_data
                elif response.status_code == 403:
                    logger.error(f"Erro de autorização (403): Verifique a chave de API do Sales Builder")
                    try:
                        error_data = response.json()
                        logger.error(f"Detalhes do erro: {error_data}")
                    except:
                        logger.error(f"Corpo da resposta: {response.text}")
                    return {"error": f"{response.status_code}: Erro de autorização", "task_id": task_id}
                else:
                    logger.warning(f"Resposta inesperada: Status {response.status_code}")
                    try:
                        error_data = response.json()
                        logger.warning(f"Detalhes da resposta: {error_data}")
                    except:
                        logger.warning(f"Corpo da resposta: {response.text}")
                
            except httpx.TimeoutException:
                logger.warning(f"Timeout ao verificar status da task {task_id}. Tentando novamente...")
            except httpx.RequestError as e:
                logger.error(f"Erro na requisição para verificar status da task {task_id}: {str(e)}")
            except Exception as e:
                logger.error(f"Erro inesperado ao verificar status da task {task_id}: {str(e)}")
            
            retries += 1
            if retries < self.max_retries:
                logger.info(f"Aguardando {self.retry_delay} segundos antes da próxima tentativa...")
                await asyncio.sleep(self.retry_delay)
        
        logger.error(f"Número máximo de tentativas excedido para a task {task_id}")
        return {"error": "Número máximo de tentativas excedido", "task_id": task_id}
    
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
            status = task_data.get("status")
            whatsapp = task_data.get("whatsapp")
            
            if not all([task_id, status, whatsapp]):
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
                    
            # Processar a task com base no status
            if status == "completed":
                # Enviar mensagem de sucesso
                message = "Olá! Sua solicitação foi processada com sucesso."
                await self.evo_api.send_text_message(whatsapp, message)
                logger.info(f"Mensagem de sucesso enviada para {whatsapp}")
                return True
            elif status == "failed":
                # Enviar mensagem de falha
                message = "Desculpe, houve um problema ao processar sua solicitação."
                await self.evo_api.send_text_message(whatsapp, message)
                logger.info(f"Mensagem de falha enviada para {whatsapp}")
                return True
            else:
                logger.warning(f"Status desconhecido: {status}")
                return False
                
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
        logger.info(f"Iniciando verificação e processamento da task {task_id}")
        
        try:
            # Verificar status da task
            task_data = await self.check_task_status(task_id)
            
            if not task_data:
                logger.error(f"Não foi possível obter dados da task {task_id}")
                return False
            
            # Verificar se há erro na resposta
            if "error" in task_data:
                logger.error(f"Erro ao verificar status da task {task_id}: {task_data.get('error')}")
                # Se for erro de autorização, tentar novamente com uma nova chave
                if "autorização" in task_data.get('error', '').lower() or "403" in task_data.get('error', ''):
                    logger.info("Tentando atualizar a chave de API e tentar novamente...")
                    # Usar a chave padrão do código
                    self.api_key = "7rQa9a0gGOz0jsG0EAlI3TxilYE2Y5pX"
                    self.headers["Authorization"] = f"Bearer {self.api_key}"
                    self.client = httpx.AsyncClient(
                        timeout=self.timeout,
                        headers=self.headers
                    )
                    # Tentar novamente
                    logger.info("Tentando verificar o status novamente com a nova chave...")
                    task_data = await self.check_task_status(task_id)
                    if "error" in task_data:
                        logger.error("Falha mesmo após atualizar a chave de API")
                        return False
                else:
                    return False
            
            # Processar resposta da task
            success = await self.process_task_response(task_data)
            return success
            
        except Exception as e:
            logger.error(f"Erro ao verificar e processar task {task_id}: {str(e)}")
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
    logger.info(f"Processando task {task_id} do Sales Builder")
    
    # Criar o verificador com as configurações fornecidas
    checker = SalesBuilderStatusChecker(settings=settings)
    try:
        result = await checker.check_and_process_task(task_id)
        return result
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