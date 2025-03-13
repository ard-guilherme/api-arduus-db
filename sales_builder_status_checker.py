import httpx
import asyncio
import logging
import time
import sys
import os
from typing import Dict, List, Optional, Any

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
            def __init__(self):
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
                 max_retries: int = 5, retry_delay: int = 10, timeout: int = 60):
        """
        Inicializa o verificador de status do Sales Builder.
        
        Args:
            api_url: URL base da API Sales Builder
            api_key: Chave de API para autenticação (opcional)
            max_retries: Número máximo de tentativas em caso de erro
            retry_delay: Tempo de espera entre tentativas (em segundos)
            timeout: Timeout da requisição HTTP (em segundos)
        """
        self.api_url = api_url
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.evo_api = EvolutionAPI()
        
        # Configurar headers para as requisições
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
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
        logger.info(f"Verificando status da task {task_id}")
        
        retries = 0
        while retries < self.max_retries:
            try:
                logger.info(f"Tentativa {retries+1} de {self.max_retries} para verificar task {task_id}")
                response = await self.client.get(url, timeout=self.timeout)
                
                if response.status_code == 200:
                    logger.info(f"Task {task_id} completada com sucesso")
                    return response.json()
                
                logger.warning(f"Resposta inesperada: Status {response.status_code}")
                
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
        return None
    
    async def process_task_response(self, task_data: Dict[str, Any]) -> bool:
        """
        Processa a resposta da task e envia as mensagens via WhatsApp.
        
        Args:
            task_data: Dados da resposta da task
            
        Returns:
            bool: True se o processamento foi bem-sucedido, False caso contrário
        """
        try:
            # Verificar se a task foi completada com sucesso
            state = task_data.get("state")
            if state != "COMPLETED":
                logger.warning(f"Task não foi completada. Estado: {state}")
                return False
            
            # Extrair dados da resposta
            result = task_data.get("result", {})
            messages = result.get("msg_resposta", [])
            whatsapp_number = result.get("whatsapp_prospect")
            
            if not messages:
                logger.warning("Nenhuma mensagem encontrada na resposta")
                return False
            
            if not whatsapp_number:
                logger.warning("Número de WhatsApp não encontrado na resposta")
                return False
            
            logger.info(f"Enviando {len(messages)} mensagens para o número {whatsapp_number}")
            
            # Enviar mensagens via WhatsApp
            for i, message in enumerate(messages):
                logger.info(f"Enviando mensagem {i+1}/{len(messages)}: {message[:50]}...")
                response = self.evo_api.send_text_message(number=whatsapp_number, text=message)
                
                if response:
                    logger.info(f"Mensagem {i+1} enviada com sucesso")
                else:
                    logger.error(f"Falha ao enviar mensagem {i+1}")
                
                # Pequena pausa entre o envio de mensagens para evitar flood
                if i < len(messages) - 1:
                    await asyncio.sleep(1)
            
            logger.info(f"Todas as mensagens foram enviadas para {whatsapp_number}")
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
        logger.info(f"Iniciando verificação e processamento da task {task_id}")
        
        try:
            # Verificar status da task
            task_data = await self.check_task_status(task_id)
            
            if not task_data:
                logger.error(f"Não foi possível obter dados da task {task_id}")
                return False
            
            # Processar resposta da task
            success = await self.process_task_response(task_data)
            return success
            
        except Exception as e:
            logger.error(f"Erro ao verificar e processar task {task_id}: {str(e)}")
            return False


async def process_sales_builder_task(task_id: str) -> bool:
    """
    Função principal para processar uma task do Sales Builder.
    
    Args:
        task_id: ID da task a ser processada
        
    Returns:
        bool: True se o processamento foi bem-sucedido, False caso contrário
    """
    logger.info(f"Processando task {task_id} do Sales Builder")
    
    checker = SalesBuilderStatusChecker()
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