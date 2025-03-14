import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from sales_builder_status_checker import SalesBuilderStatusChecker, process_sales_builder_task

# Exemplo de resposta da API Sales Builder
SAMPLE_RESPONSE = {
    "task_id": "1741882913572_8470f029",
    "queue": "sales-builder",
    "state": "COMPLETED",
    "result": {
        "analise_icp": None,
        "atendimento": {
            "interacao": "Iniciar a conversa com lead à partir do P1",
            "status": "primeiro_contato",
            "p_atual": "P1",
            "tipo_interacao": "positivo",
            "p_proxima": "P2",
            "msg_resposta": [
                "Oi Guilherme, tudo bem? Aqui é o Vagner Campos da Arduus! Vi suas discussões interessantes sobre liderança em tecnologia no LinkedIn",
                "Percebi que temos visões alinhadas sobre como a inovação pode transformar ciclos de trabalho. Gostaria de saber mais sobre seus objetivos com IA?"
            ],
            "periodo_agendamento": "NULL",
            "horario_agendamento": "NULL",
            "dia_agendamento": "NULL",
            "link_agendamento_google_calendar": "NULL",
            "link_meet_google": "NULL"
        },
        "msg_resposta": [
            "Oi Guilherme, tudo bem? Aqui é o Vagner Campos da Arduus! Vi suas discussões interessantes sobre liderança em tecnologia no LinkedIn",
            "Percebi que temos visões alinhadas sobre como a inovação pode transformar ciclos de trabalho. Gostaria de saber mais sobre seus objetivos com IA?"
        ],
        "nome_prospect": "Guilherme Moura",
        "whatsapp_prospect": "5524999887888"
    },
    "timestamp": "2025-03-13T16:30:17.336866+00:00"
}

# Teste da classe SalesBuilderStatusChecker
@pytest.mark.asyncio
async def test_check_task_status():
    # Mock para o cliente httpx
    with patch("sales_builder_status_checker.httpx.AsyncClient") as mock_client_class:
        # Configurar o mock do cliente
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Configurar o mock da resposta com mensagens
        mock_response_with_messages = MagicMock()
        mock_response_with_messages.status_code = 200
        mock_response_with_messages.json.return_value = SAMPLE_RESPONSE
        
        # Configurar o mock da resposta sem mensagens
        response_without_messages = {
            "task_id": "1741882913572_8470f029",
            "queue": "sales-builder",
            "state": "COMPLETED",
            "result": {
                "analise_icp": None,
                "atendimento": {
                    "interacao": "Iniciar a conversa com lead à partir do P1",
                    "status": "primeiro_contato",
                    "p_atual": "P1",
                    "tipo_interacao": "positivo",
                    "p_proxima": "P2",
                    "msg_resposta": [],  # Lista vazia
                    "periodo_agendamento": "NULL",
                    "horario_agendamento": "NULL",
                    "dia_agendamento": "NULL",
                    "link_agendamento_google_calendar": "NULL",
                    "link_meet_google": "NULL"
                },
                "msg_resposta": [],  # Lista vazia
                "nome_prospect": "Guilherme Moura",
                "whatsapp_prospect": "5524999887888"
            },
            "timestamp": "2025-03-13T16:30:17.336866+00:00"
        }
        mock_response_without_messages = MagicMock()
        mock_response_without_messages.status_code = 200
        mock_response_without_messages.json.return_value = response_without_messages
        
        # Configurar o mock para retornar primeiro a resposta sem mensagens e depois com mensagens
        mock_client.get.side_effect = [mock_response_without_messages, mock_response_with_messages]
        
        # Mock para asyncio.sleep para não esperar realmente
        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            # Inicializar o checker com retry_delay reduzido para o teste
            checker = SalesBuilderStatusChecker(api_url="https://test-api.com", retry_delay=1)
            
            # Testar a verificação de status
            result = await checker.check_task_status("test_task_id")
            
            # Verificar se o método get foi chamado duas vezes
            assert mock_client.get.call_count == 2
            
            # Verificar se sleep foi chamado com 30 segundos
            mock_sleep.assert_called_once_with(30)
            
            # Verificar se o resultado é o esperado (a resposta com mensagens)
            assert result == SAMPLE_RESPONSE
            
            # Fechar o cliente
            await checker.close()

@pytest.mark.asyncio
async def test_check_task_status_with_messages_immediately():
    # Mock para o cliente httpx
    with patch("sales_builder_status_checker.httpx.AsyncClient") as mock_client_class:
        # Configurar o mock do cliente
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Configurar o mock da resposta com mensagens imediatamente
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_RESPONSE
        mock_client.get.return_value = mock_response
        
        # Inicializar o checker
        checker = SalesBuilderStatusChecker(api_url="https://test-api.com")
        
        # Testar a verificação de status
        result = await checker.check_task_status("test_task_id")
        
        # Verificar se o método get foi chamado corretamente
        mock_client.get.assert_called_once_with(
            "https://test-api.com/status/test_task_id", 
            timeout=checker.timeout
        )
        
        # Verificar se o resultado é o esperado
        assert result == SAMPLE_RESPONSE
        
        # Fechar o cliente
        await checker.close()

@pytest.mark.asyncio
async def test_process_task_response():
    # Mock para a classe EvolutionAPI
    with patch("sales_builder_status_checker.EvolutionAPI") as mock_evo_api_class:
        # Mock para o método insert_chat_history
        with patch.object(SalesBuilderStatusChecker, "insert_chat_history") as mock_insert_history:
            # Configurar o mock da classe EvolutionAPI
            mock_evo_api = MagicMock()
            mock_evo_api.send_text_message = AsyncMock(return_value={"status": "success"})
            mock_evo_api.is_configured = True
            mock_evo_api_class.return_value = mock_evo_api
            
            # Configurar o mock do método insert_chat_history
            mock_insert_history.return_value = {"inserted_id": "mock_id"}
            
            # Inicializar o checker
            checker = SalesBuilderStatusChecker()
            
            # Testar o processamento da resposta
            result = await checker.process_task_response(SAMPLE_RESPONSE)
            
            # Verificar se o método send_text_message foi chamado corretamente
            assert mock_evo_api.send_text_message.call_count == 2
            
            # Verificar a primeira chamada
            mock_evo_api.send_text_message.assert_any_call(
                number="5524999887888",
                text="Oi Guilherme, tudo bem? Aqui é o Vagner Campos da Arduus! Vi suas discussões interessantes sobre liderança em tecnologia no LinkedIn"
            )
            
            # Verificar a segunda chamada
            mock_evo_api.send_text_message.assert_any_call(
                number="5524999887888",
                text="Percebi que temos visões alinhadas sobre como a inovação pode transformar ciclos de trabalho. Gostaria de saber mais sobre seus objetivos com IA?"
            )
            
            # Verificar se o método insert_chat_history foi chamado corretamente
            assert mock_insert_history.call_count == 2
            
            # Verificar a primeira chamada ao insert_chat_history
            mock_insert_history.assert_any_call(
                "5524999887888",
                "Oi Guilherme, tudo bem? Aqui é o Vagner Campos da Arduus! Vi suas discussões interessantes sobre liderança em tecnologia no LinkedIn",
                SAMPLE_RESPONSE
            )
            
            # Verificar a segunda chamada ao insert_chat_history
            mock_insert_history.assert_any_call(
                "5524999887888",
                "Percebi que temos visões alinhadas sobre como a inovação pode transformar ciclos de trabalho. Gostaria de saber mais sobre seus objetivos com IA?",
                SAMPLE_RESPONSE
            )
            
            # Verificar se o resultado é o esperado
            assert result is True
            
            # Fechar o cliente
            await checker.close()

@pytest.mark.asyncio
async def test_check_and_process_task():
    # Mock para o método check_task_status
    with patch.object(SalesBuilderStatusChecker, "check_task_status") as mock_check_status:
        # Mock para o método process_task_response
        with patch.object(SalesBuilderStatusChecker, "process_task_response") as mock_process_response:
            # Configurar os mocks
            mock_check_status.return_value = SAMPLE_RESPONSE
            mock_process_response.return_value = True
            
            # Inicializar o checker
            checker = SalesBuilderStatusChecker()
            
            # Testar o processamento completo
            result = await checker.check_and_process_task("test_task_id")
            
            # Verificar se os métodos foram chamados corretamente
            mock_check_status.assert_called_once_with("test_task_id")
            mock_process_response.assert_called_once_with(SAMPLE_RESPONSE)
            
            # Verificar se o resultado é o esperado
            assert result is True
            
            # Fechar o cliente
            await checker.close()

@pytest.mark.asyncio
async def test_process_sales_builder_task():
    # Mock para o método check_and_process_task
    with patch.object(SalesBuilderStatusChecker, "check_and_process_task") as mock_check_process:
        # Configurar o mock
        mock_check_process.return_value = True
        
        # Testar a função principal
        result = await process_sales_builder_task("test_task_id")
        
        # Verificar se o método foi chamado corretamente
        mock_check_process.assert_called_once_with("test_task_id")
        
        # Verificar se o resultado é o esperado
        assert result is True

if __name__ == "__main__":
    pytest.main(["-v", "test_sales_builder_status.py"]) 