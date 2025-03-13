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
        if settings:
            # Usar configurações da aplicação principal
            self.evo_subdomain = settings.EVO_SUBDOMAIN
            self.evo_instance = settings.EVO_INSTANCE
            self.evo_token = settings.EVO_TOKEN
        else:
            # Carregar das variáveis de ambiente
            self.evo_subdomain = os.getenv("EVO_SUBDOMAIN")
            self.evo_instance = os.getenv("EVO_INSTANCE")
            self.evo_token = os.getenv("EVO_TOKEN")
            
            # Log para depuração
            logging.info(f"Configurações da Evolution API: subdomain={self.evo_subdomain}, instance={self.evo_instance}")
            
            # Verificar se as configurações estão presentes
            if not all([self.evo_subdomain, self.evo_instance, self.evo_token]):
                missing = []
                if not self.evo_subdomain: missing.append("EVO_SUBDOMAIN")
                if not self.evo_instance: missing.append("EVO_INSTANCE")
                if not self.evo_token: missing.append("EVO_TOKEN")
                logging.error(f"Variáveis de ambiente da Evolution API ausentes: {', '.join(missing)}")
        
        try:
            self.client = OpenAI()
        except Exception as e:
            logging.error(f"Erro ao inicializar o cliente OpenAI: {e}")
            
        self.headers = {
            "apikey": self.evo_token,
            "Content-Type": "application/json"
        }


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

        payload = {
            "number": number,
            "text": text,
            "delay": self.estimate_typing_time(text, typing_speed=207),
        }

        for key, value in kwargs.items():
            payload[key] = value

        try:
            logging.info(f"[EVO_API] Enviando mensagem para {number}: '{text[:50]}...'")
            logging.debug(f"[EVO_API] URL: {url}, Payload: {json.dumps(payload)[:200]}...")
            
            response = requests.post(url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logging.info(f"[EVO_API] Mensagem enviada com sucesso para {number}. Status: {response.status_code}")
                response_data = response.json()
                logging.debug(f"[EVO_API] Resposta: {json.dumps(response_data)[:200]}...")
                return response_data
            else:
                logging.error(f"[EVO_API] Falha ao enviar mensagem. Status: {response.status_code}, Resposta: {response.text[:200]}...")
                response.raise_for_status()
                return None
                
        except requests.exceptions.RequestException as e:
            logging.error(f"[EVO_API] Erro na requisição: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"[EVO_API] Erro inesperado: {str(e)}")
            return None


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