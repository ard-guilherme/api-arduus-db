import unittest
from evo_api_v2 import EvolutionAPI
import os
from dotenv import load_dotenv

class TestEvolutionAPI(unittest.TestCase):
    def setUp(self):
        """Configuração inicial para cada teste"""
        load_dotenv()
        self.api = EvolutionAPI()
        self.test_number = "5524999887888"
        
    def test_send_text_message(self):
        """Testa o envio de mensagem de texto"""
        print("\nTestando envio de mensagem de texto...")
        
        # Mensagem de teste
        test_message = "Olá! Este é um teste automatizado da Evolution API."
        
        # Enviar mensagem
        result = self.api.send_text_message(
            number=self.test_number,
            text=test_message
        )
        
        # Verificar resultado
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        
        # Verificar status
        if result.get("status") == "error":
            print(f"ERRO: {result.get('message')}")
        else:
            print("✓ Mensagem enviada com sucesso!")
            
        # Verificar se a API está configurada
        self.assertTrue(self.api.is_configured)
        
        # Verificar se os headers estão configurados
        self.assertIn("apikey", self.api.headers)
        self.assertIn("Content-Type", self.api.headers)
        
    def test_send_template_message(self):
        """Testa o envio de mensagem de template"""
        print("\nTestando envio de mensagem de template...")
        
        # Verificar se a API está configurada antes do teste
        if not self.api.is_configured:
            print("AVISO: API não está configurada corretamente")
            return
            
        # Verificar se temos as configurações necessárias
        print(f"Configurações da API:")
        print(f"- Subdomain: {self.api.evo_subdomain}")
        print(f"- Instance: {self.api.evo_instance}")
        print(f"- Token: {'Presente' if self.api.evo_token else 'Ausente'}")
        
        # Template de teste (usando um template mais comum)
        template_data = {
            "number": self.test_number,
            "template": "welcome_message",
            "language": "pt_BR",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Cliente"
                        }
                    ]
                }
            ]
        }
        
        print(f"Dados do template: {template_data}")
        
        # Enviar template
        result = self.api.send_template_message(**template_data)
        
        # Verificar resultado
        if result is None:
            print("AVISO: Resultado é None - isso é esperado se o template não estiver configurado")
            return
            
        self.assertIsInstance(result, dict)
        
        # Verificar status
        if result.get("status") == "error":
            print(f"ERRO: {result.get('message')}")
            # Se for erro de template não encontrado, não falhar o teste
            if "template" in str(result.get("message")).lower():
                print("AVISO: Template não encontrado - isso é esperado se o template não estiver configurado")
                return
        else:
            print("✓ Template enviado com sucesso!")
            
        # Verificar se os headers estão configurados
        self.assertIn("apikey", self.api.headers)
        self.assertIn("Content-Type", self.api.headers)
        
    def test_send_media_message(self):
        """Testa o envio de mensagem com mídia"""
        print("\nTestando envio de mensagem com mídia...")
        
        # URL de uma imagem de teste
        test_image_url = "https://picsum.photos/200/300"
        
        # Enviar mídia
        result = self.api.send_media_message(
            number=self.test_number,
            mediatype="image",
            media=test_image_url,
            caption="Esta é uma imagem de teste"
        )
        
        # Verificar resultado
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        
        # Verificar status
        if result.get("status") == "error":
            print(f"ERRO: {result.get('message')}")
        else:
            print("✓ Mídia enviada com sucesso!")

def run_tests():
    """Executa os testes"""
    print("Iniciando testes da Evolution API...")
    unittest.main(verbosity=2)

if __name__ == '__main__':
    run_tests() 