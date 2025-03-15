from evo_api_v2 import EvolutionAPI
from dotenv import load_dotenv
import time

def test_send_messages():
    """
    Teste específico para enviar mensagens para o número 5524999887888
    """
    # Carregar variáveis de ambiente
    load_dotenv()
    
    # Inicializar a API
    api = EvolutionAPI()
    
    # Número de teste
    test_number = "5524999887888"
    
    print(f"\n=== Teste de envio de mensagens para {test_number} ===\n")
    
    # Teste 1: Mensagem de texto simples
    print("1. Enviando mensagem de texto simples...")
    result1 = api.send_text_message(
        number=test_number,
        text="Teste de mensagem simples da Evolution API. Hora: " + time.strftime("%H:%M:%S")
    )
    
    if result1.get("status") == "error":
        print(f"❌ ERRO: {result1.get('message')}")
    else:
        print("✅ Mensagem de texto enviada com sucesso!")
    
    # Aguardar 2 segundos
    time.sleep(2)
    
    # Teste 2: Mensagem com mídia
    print("\n2. Enviando mensagem com imagem...")
    result2 = api.send_media_message(
        number=test_number,
        mediatype="image",
        media="https://picsum.photos/300/200",
        caption="Esta é uma imagem de teste enviada pela Evolution API. Hora: " + time.strftime("%H:%M:%S")
    )
    
    if result2.get("status") == "error":
        print(f"❌ ERRO: {result2.get('message')}")
    else:
        print("✅ Mensagem com imagem enviada com sucesso!")
    
    # Aguardar 2 segundos
    time.sleep(2)
    
    # Teste 3: Mensagem de localização
    print("\n3. Enviando mensagem de localização...")
    result3 = api.send_location_message(
        number=test_number,
        latitude="-22.9068",
        longitude="-43.1729",
        address="Cristo Redentor, Rio de Janeiro, Brasil"
    )
    
    if result3 is None:
        print("❌ ERRO: A API retornou None. Provavelmente o endpoint não está disponível.")
    elif result3.get("status") == "error":
        print(f"❌ ERRO: {result3.get('message')}")
    else:
        print("✅ Mensagem de localização enviada com sucesso!")
    
    print("\n=== Teste concluído ===")

if __name__ == "__main__":
    test_send_messages() 