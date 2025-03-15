import json
import requests
import os
import base64
import logging
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydub import AudioSegment
from datetime import datetime, timedelta

# Carregar variáveis de ambiente
load_dotenv()

class EvolutionAPI:
    def __init__(self, settings=None):
        """
        Inicializa a API de Evolução com configurações.
        
        Args:
            settings: Opcional. Instância de Settings da aplicação principal.
                     Se não fornecido, carrega as configurações das variáveis de ambiente.
        """
        # Inicializar com valores padrão
        self.evo_subdomain = None
        self.evo_instance = None
        self.evo_token = None
        
        if settings:
            # Usar configurações da aplicação principal
            self.evo_subdomain = settings.EVO_SUBDOMAIN
            self.evo_instance = settings.EVO_INSTANCE
            self.evo_token = settings.EVO_TOKEN
        else:
            # Carregar das variáveis de ambiente
            load_dotenv()  # Garantir que as variáveis de ambiente sejam carregadas
            self.evo_subdomain = os.getenv("EVO_SUBDOMAIN")
            self.evo_instance = os.getenv("EVO_INSTANCE")
            self.evo_token = os.getenv("EVO_TOKEN")
            
        # Log para depuração
        logging.info(f"Configurações da Evolution API: subdomain={self.evo_subdomain}, instance={self.evo_instance}")
        
        # Verificar se as configurações estão presentes
        self.is_configured = all([self.evo_subdomain, self.evo_instance, self.evo_token])
        if not self.is_configured:
            missing = []
            if not self.evo_subdomain: missing.append("EVO_SUBDOMAIN")
            if not self.evo_instance: missing.append("EVO_INSTANCE")
            if not self.evo_token: missing.append("EVO_TOKEN")
            logging.warning(f"Variáveis de ambiente da Evolution API ausentes: {', '.join(missing)}. Algumas funcionalidades podem não estar disponíveis.")
        
        try:
            # Definir uma chave de API OpenAI padrão se não estiver definida
            if not os.getenv("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-initialization"
                logging.warning("Usando chave de API OpenAI fictícia. Algumas funcionalidades podem não estar disponíveis.")
            
            self.client = OpenAI()
        except Exception as e:
            logging.error(f"Erro ao inicializar o cliente OpenAI: {e}")
            self.client = None
            
        # Configurar headers apenas se tivermos um token
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.evo_token:
            self.headers["apikey"] = self.evo_token


    def estimate_typing_time(self, text, typing_speed=41.4):
        num_words = len(text.split())
        num_characters = len(text)
        characters_per_word = num_characters / num_words
        typing_time_seconds = num_characters / (typing_speed * characters_per_word) * 60
        typing_time_ms = int(typing_time_seconds * 1000)        
        return typing_time_ms


    def send_template_message(self, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendTemplate/{self.evo_instance}"
        
        payload = {}
        
        for key, value in kwargs.items():
            payload[key] = value
        
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


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
        
        try:
            # Log no console antes de enviar
            print(f"[{datetime.now().isoformat()}] EVOLUTION API - ENVIANDO: Mensagem para {number} (tempo de digitação: {typing_time}ms)")
            
            logging.info(f"[EVO_API] Enviando mensagem para {number}: '{text[:50]}...'")
            logging.debug(f"[EVO_API] URL: {url}, Payload: {json.dumps(payload)[:200]}...")
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
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
            error_msg = f"Timeout ao enviar mensagem para {number} após 30 segundos"
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


    def send_status_message(self, type_content, content, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendStatus/{self.evo_instance}"

        payload = {
            "type": type_content,
            "content": content,
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_media_message(self, number, mediatype, media, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendMedia/{self.evo_instance}"

        payload = {
            "number": number,
            "mediatype": mediatype,
            "media": media,
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_whatsapp_audio_message(self, number, audio, delay, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendWhatsAppAudio/{self.evo_instance}"

        payload = {
            "number": number,
            "audio": audio,
            "delay": delay,
        }

        for key, value in kwargs.items():
            payload[key] = value
            
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_sticker_message(self, number, sticker, delay, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendSticker/{self.evo_instance}"

        payload = {
            "number": number,
            "sticker": sticker,
            "delay": delay,
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_location_message(self, number, latitude, longitude, address=None, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendLocation/{self.evo_instance}"

        payload = {
            "number": number,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "delay": self.estimate_typing_time(address if address else "", typing_speed=207),
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_contact_message(self, number: str, contact: list):
        url = f"https://{self.evo_subdomain}/message/sendContact/{self.evo_instance}"

        payload = {
            "number": number,
            "contact": contact
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_reaction_message(self, remote_jid, message_id, reaction):
        url = f"https://{self.evo_subdomain}/message/sendReaction/{self.evo_instance}"

        payload = {
            "reactionMessage": {
                "key": {
                    "remoteJid": remote_jid,
                    "fromMe": True,
                    "id": message_id
                },
                "reaction": reaction
            }
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_poll_message(self, number, name, selectable_count, values, delay, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendPoll/{self.evo_instance}"

        payload = {
            "number": number,
            "name": name,
            "selectableCount": selectable_count,
            "values": values,
            "delay": delay,
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_list_message(self, number, title, buttonText, sections, delay, **kwargs):
        url = f"https://{self.evo_subdomain}/message/sendList/{self.evo_instance}"

        payload = {
            "number": number,
            "title": title,
            "buttonText": buttonText,
            "sections": sections,
            "delay": delay,
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} com dados {payload} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None


    def send_webhook_request(self):
        url = f"https://{self.evo_subdomain}/webhook/find/{self.evo_instance}"
        headers = {"apikey": self.evo_token}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} retornou status {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro: {e}")
            return None



    def fetch_all_groups(self) -> list:
        """
        Busca todos os grupos associados à instância.

        Returns:
            list: Uma lista contendo informações sobre todos os grupos.
        """
        url = f"https://{self.evo_subdomain}/group/fetchAllGroups/{self.evo_instance}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Requisição para {url} retornou status {response.status_code}")
                return response.json().get('groups', [])
            else:
                logging.warning(f"Requisição para {url} retornou status inesperado: {response.status_code}")
                return []
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao buscar grupos: {e}")
            return []

if __name__ == "__main__":
    evo_api = EvolutionAPI()
    evo_api.send_text_message(number="5547999019008", text="Olá, tudo bem?")