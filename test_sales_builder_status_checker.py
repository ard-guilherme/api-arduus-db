import unittest
import asyncio
from unittest.mock import Mock, patch, call, MagicMock
from sales_builder_status_checker import SalesBuilderStatusChecker
from unittest.mock import AsyncMock
from bson.objectid import ObjectId
from datetime import datetime

class TestSalesBuilderStatusChecker(unittest.TestCase):
    def setUp(self):
        """Configuração inicial para cada teste"""
        self.checker = SalesBuilderStatusChecker(
            api_key="test_key",
            max_retries=20,  # Número atualizado de tentativas
            retry_delay=15,  # Intervalo atualizado entre tentativas
            timeout=60
        )
        # Mock da Evolution API
        self.checker.evo_api = Mock()
        self.checker.evo_api.is_configured = True
        self.checker.evo_api.send_text_message = Mock(return_value={"status": "success"})

    def tearDown(self):
        """Limpa os mocks após cada teste"""
        self.checker.evo_api.send_text_message.reset_mock()

    async def test_fallback_messages_on_empty_response(self):
        """Testa se as mensagens de fallback são enviadas quando a API retorna uma lista vazia"""
        # Mock da resposta da API com lista vazia
        mock_response = {
            "task_id": "test-task",
            "status_code": 200,
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": []
            },
            "fallback_messages_used": True
        }

        # Verificar se as mensagens de fallback são enviadas
        success = await self.checker.process_task_response(mock_response)
        self.assertTrue(success)

        # Verificar se o método send_text_message foi chamado com as mensagens corretas
        expected_messages = [
            "Oi, tudo bem? Aqui é o Vagner Campos, fundador da Arduus. Vi seu interesse em inovação e transformação digital no LinkedIn, especialmente na área de IA.",
            "Percebi que você entrou em contato conosco para conhecer mais sobre nossas soluções de IA generativa. Gostaria de saber mais sobre como podemos impulsionar sua transformação digital?"
        ]

        self.assertEqual(self.checker.evo_api.send_text_message.call_count, 2)
        calls = self.checker.evo_api.send_text_message.call_args_list
        for i, call in enumerate(calls):
            args, kwargs = call
            self.assertEqual(kwargs['text'], expected_messages[i])
            self.assertEqual(kwargs['number'], "5511999999999")

    async def test_normal_flow_with_messages(self):
        """Testa o fluxo normal quando a API retorna mensagens"""
        # Mock da resposta da API com mensagens
        mock_response = {
            "task_id": "test-task",
            "status_code": 200,
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": ["Mensagem de teste 1", "Mensagem de teste 2"]
            }
        }

        # Verificar se as mensagens originais são enviadas
        success = await self.checker.process_task_response(mock_response)
        self.assertTrue(success)

        # Verificar se o método send_text_message foi chamado com as mensagens corretas
        self.assertEqual(self.checker.evo_api.send_text_message.call_count, 2)
        calls = self.checker.evo_api.send_text_message.call_args_list
        expected_messages = ["Mensagem de teste 1", "Mensagem de teste 2"]
        for i, call in enumerate(calls):
            args, kwargs = call
            self.assertEqual(kwargs['text'], expected_messages[i])
            self.assertEqual(kwargs['number'], "5511999999999")

    async def test_mongodb_update_in_check_and_process_task(self):
        """Testa se o MongoDB é atualizado corretamente durante o processamento da task"""
        # Mock da resposta da API com mensagens
        mock_response = {
            "task_id": "test-task",
            "status_code": 200,
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": ["Mensagem de teste 1", "Mensagem de teste 2"]
            }
        }

        # Mock do MongoDB
        mock_request_queue = MagicMock()
        mock_request_queue.update_one = AsyncMock()
        mock_request_id = "65f1a3b5c89a7f5d6e1234ab"  # ID válido no formato ObjectId

        # Patch da função check_task_status para retornar diretamente o resultado mockado
        async def mock_check_task_status(task_id):
            return mock_response

        # Aplicar o patch
        with patch.object(self.checker, 'check_task_status', mock_check_task_status), \
             patch.object(self.checker, 'process_task_response', return_value=True):
            # Executar o teste
            success = await self.checker.check_and_process_task("test-task", mock_request_queue, mock_request_id)
            
            # Verificar se o processamento foi bem-sucedido
            self.assertTrue(success)
            
            # Verificar se o método update_one do MongoDB foi chamado
            mock_request_queue.update_one.assert_called()
            
            # Verificar os argumentos da chamada
            call_args = mock_request_queue.update_one.call_args
            filter_arg = call_args[0][0]  # Primeiro argumento da chamada (filtro)
            update_arg = call_args[0][1]  # Segundo argumento da chamada (update)
            
            # Verificar o filtro
            self.assertEqual(filter_arg, {"_id": ObjectId(mock_request_id)})
            
            # Verificar a estrutura do comando de atualização
            self.assertIn("$set", update_arg)
            self.assertIn("messages", update_arg["$set"])
            self.assertEqual(update_arg["$set"]["messages"], ["Mensagem de teste 1", "Mensagem de teste 2"])
            self.assertEqual(update_arg["$set"]["message_count"], 2)
            
            # Verificar o operador $push
            self.assertIn("$push", update_arg)
            self.assertIn("steps", update_arg["$push"])
            
            # Verificar se o passo é "messages_stored"
            step_data = update_arg["$push"]["steps"]
            self.assertEqual(step_data["step"], "messages_stored")
            self.assertIn("timestamp", step_data)
            self.assertIn("success", step_data)
            self.assertTrue(step_data["success"])
            self.assertIn("message", step_data)
            self.assertIn("message_preview", step_data)

    async def test_long_running_task(self):
        """Testa o comportamento com uma task que demora muito tempo para concluir (cerca de 200 segundos)"""
        # Vamos simplificar o teste e focar apenas na verificação de que o sistema
        # pode lidar com tarefas que demoram muito tempo para completar
        
        # Criar uma resposta final com mensagens
        final_response = {
            "task_id": "test-task",
            "status_code": 200,
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": ["Mensagem após longa espera 1", "Mensagem após longa espera 2"]
            }
        }
        
        # Mock do MongoDB
        mock_request_queue = MagicMock()
        mock_request_queue.update_one = AsyncMock()
        mock_request_id = "65f1a3b5c89a7f5d6e1234ab"
        
        # Verificar se o sistema pode processar corretamente a resposta
        with patch.object(self.checker, 'check_task_status', return_value=final_response), \
             patch.object(self.checker, 'process_task_response', return_value=True):
            
            # Executar o teste
            success = await self.checker.check_and_process_task("test-task", mock_request_queue, mock_request_id)
            
            # Verificar se o processamento foi bem-sucedido
            self.assertTrue(success)
            
            # Verificar se o método update_one do MongoDB foi chamado
            mock_request_queue.update_one.assert_called_once()
            
            # Verificar os argumentos da chamada
            call_args = mock_request_queue.update_one.call_args
            filter_arg = call_args[0][0]  # Primeiro argumento da chamada (filtro)
            update_arg = call_args[0][1]  # Segundo argumento da chamada (update)
            
            # Verificar o filtro
            self.assertEqual(filter_arg, {"_id": ObjectId(mock_request_id)})
            
            # Verificar a estrutura do comando de atualização
            self.assertIn("$set", update_arg)
            self.assertIn("messages", update_arg["$set"])
            self.assertEqual(update_arg["$set"]["messages"], ["Mensagem após longa espera 1", "Mensagem após longa espera 2"])
            self.assertEqual(update_arg["$set"]["message_count"], 2)
            
            # Verificar o operador $push
            self.assertIn("$push", update_arg)
            self.assertIn("steps", update_arg["$push"])
            
            # Verificar se o passo é "messages_stored"
            step_data = update_arg["$push"]["steps"]
            self.assertEqual(step_data["step"], "messages_stored")
            self.assertIn("timestamp", step_data)
            self.assertIn("success", step_data)
            self.assertTrue(step_data["success"])
            self.assertIn("message", step_data)
            self.assertIn("message_preview", step_data)
        
        # Agora vamos testar o comportamento do método check_task_status com múltiplas tentativas
        print("\nTestando comportamento do método check_task_status com múltiplas tentativas...")
        
        # Contador para controlar quando retornar a resposta final
        call_count = 0
        
        # Criar um cliente HTTP mock que retorna diferentes respostas
        mock_client = MagicMock()
        
        # Criar respostas mock para simular o comportamento do método
        empty_response_mock = MagicMock()
        empty_response_mock.status_code = 200
        empty_response_mock.json.return_value = {
            "task_id": "test-task-retries",
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": []
            }
        }
        
        final_response_mock = MagicMock()
        final_response_mock.status_code = 200
        final_response_mock.json.return_value = {
            "task_id": "test-task-retries",
            "result": {
                "whatsapp_prospect": "5511999999999",
                "msg_resposta": ["Mensagem final 1", "Mensagem final 2"]
            }
        }
        
        # Configurar o mock do cliente HTTP para retornar diferentes respostas
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            print(f"Chamada {call_count} para mock_get")
            
            # Retornar resposta vazia nas primeiras chamadas
            if call_count < 3:
                return empty_response_mock
            else:
                return final_response_mock
        
        mock_client.get = mock_get
        
        # Criar um verificador com o cliente mock
        test_checker = SalesBuilderStatusChecker(
            api_key="test_key",
            max_retries=5,
            retry_delay=0.1  # Usar um valor pequeno para o teste
        )
        test_checker.client = mock_client
        
        # Mock para asyncio.sleep para não esperar realmente
        async def fake_sleep(seconds):
            print(f"Aguardando {seconds} segundos (simulado)")
            return
        
        # Aplicar o patch para asyncio.sleep
        with patch('asyncio.sleep', fake_sleep):
            # Executar o teste
            result = await test_checker.check_task_status("test-task-retries")
            
            # Verificar se foram feitas múltiplas chamadas
            self.assertEqual(call_count, 3, "Deveria ter feito exatamente 3 chamadas")
            
            # Verificar se a resposta final contém mensagens
            self.assertIn("result", result)
            self.assertIn("msg_resposta", result["result"])
            self.assertEqual(len(result["result"]["msg_resposta"]), 2)
            self.assertEqual(result["result"]["msg_resposta"][0], "Mensagem final 1")
        
        print("✓ Teste de múltiplas tentativas passou!")

def run_tests():
    """Executa os testes de forma assíncrona"""
    async def run_async_tests():
        # Criar uma instância da classe de teste
        test_case = TestSalesBuilderStatusChecker()
        
        try:
            # Configurar o ambiente de teste
            test_case.setUp()
            
            # Executar os testes
            print("\nExecutando teste de fallback com lista vazia...")
            await test_case.test_fallback_messages_on_empty_response()
            print("✓ Teste de fallback passou!")
            
            # Limpar mocks entre os testes
            test_case.tearDown()
            test_case.setUp()
            
            print("\nExecutando teste de fluxo normal...")
            await test_case.test_normal_flow_with_messages()
            print("✓ Teste de fluxo normal passou!")
            
            # Limpar mocks entre os testes
            test_case.tearDown()
            test_case.setUp()
            
            print("\nExecutando teste de atualização do MongoDB...")
            await test_case.test_mongodb_update_in_check_and_process_task()
            print("✓ Teste de atualização do MongoDB passou!")
            
            # Limpar mocks entre os testes
            test_case.tearDown()
            test_case.setUp()
            
            print("\nExecutando teste de task de longa duração...")
            await test_case.test_long_running_task()
            print("✓ Teste de task de longa duração passou!")
            
            print("\n✓ Todos os testes foram executados com sucesso!")
        finally:
            # Limpar mocks após os testes
            test_case.tearDown()

    # Executar os testes no loop de eventos
    asyncio.run(run_async_tests())

if __name__ == '__main__':
    run_tests() 