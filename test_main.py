import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import os
import json
from main import app, RateLimiter, call_sales_builder_api

"""
Testes automatizados para a API Arduus DB

Este módulo contém testes para verificar o funcionamento correto da API,
incluindo validação de dados, autenticação e tratamento de erros.
"""

# Mock para o RateLimiter para evitar a dependência do MongoDB
@pytest.fixture(autouse=True)
def mock_rate_limiter():
    """
    Mock para o RateLimiter
    
    Este fixture substitui temporariamente o método __call__ do RateLimiter
    para evitar a dependência do MongoDB durante os testes.
    """
    original_call = RateLimiter.__call__
    
    async def mock_call(self, request):
        # Não faz nada, apenas retorna
        return None
    
    # Substituir o método __call__ pelo mock
    RateLimiter.__call__ = mock_call
    
    yield
    
    # Restaurar o método original
    RateLimiter.__call__ = original_call

# Mock para configurações
@pytest.fixture
def mock_settings():
    """
    Mock para as configurações da aplicação
    
    Este fixture configura variáveis de ambiente temporárias para os testes,
    incluindo a API key e a URI do MongoDB.
    """
    # Salvar variáveis de ambiente originais
    original_env = os.environ.copy()
    
    # Configurar variáveis de ambiente para teste
    os.environ["API_KEY"] = "test_api_key"
    os.environ["MONGO_URI"] = "mongodb://testdb:27017"
    
    yield
    
    # Restaurar variáveis de ambiente originais
    os.environ.clear()
    os.environ.update(original_env)

# Mock para o MongoDB
@pytest.fixture
def mock_mongodb():
    """
    Mock para o MongoDB
    
    Este fixture cria um mock para o cliente MongoDB e configura
    a aplicação para usar esse mock durante os testes.
    
    Returns:
        AsyncMock: Mock da coleção do MongoDB
    """
    with patch("main.AsyncIOMotorClient") as mock_client:
        # Configurar o mock para o MongoDB
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="mock_id")
        
        # Por padrão, find_one retorna None (nenhum lead existente)
        mock_collection.find_one.return_value = None
        
        # Configurar o app para usar o mock
        app.mongodb_client = mock_client
        app.db = MagicMock()
        app.collection = mock_collection
        
        yield mock_collection

# Mock para a API Sales Builder
@pytest.fixture
def mock_sales_builder_api():
    """
    Mock para a API Sales Builder
    
    Este fixture cria um mock para a função call_sales_builder_api
    para evitar chamadas reais à API durante os testes.
    
    Returns:
        AsyncMock: Mock da função call_sales_builder_api
    """
    with patch("main.call_sales_builder_api") as mock_api:
        # Configurar o mock para retornar um valor padrão
        mock_api.return_value = {"task_id": "mock_task_id"}
        
        yield mock_api

# Cliente de teste
@pytest.fixture
def client():
    """
    Cliente de teste para a API
    
    Este fixture cria um cliente de teste para fazer requisições
    à API durante os testes.
    
    Returns:
        TestClient: Cliente de teste para a API
    """
    with TestClient(app) as test_client:
        yield test_client

# Teste do endpoint de health check
def test_health_check(client):
    """
    Testa o endpoint de health check
    
    Verifica se o endpoint /health retorna status 200 e
    a mensagem correta indicando que a API está online.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "online"}

# Teste do endpoint de submissão de formulário com API key válida
def test_submit_form_valid(client, mock_mongodb, mock_settings, mock_sales_builder_api):
    """
    Testa a submissão de formulário com dados válidos
    
    Verifica se o endpoint /submit-form/ aceita dados válidos,
    retorna status 201 e a mensagem correta, e se os dados são
    corretamente enviados para o MongoDB e à API Sales Builder.
    """
    # Dados de teste
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "teste@example.com",
        "whatsapp": "+5511987654321",
        "company": "Empresa Teste",
        "revenue": "1-5 milhões",
        "job_title": "Diretor",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 201
    assert "document_id" in response.json()
    assert "sales_builder_task_id" in response.json()
    assert response.json()["message"] == "Formulário recebido com sucesso"
    assert response.json()["sales_builder_task_id"] == "mock_task_id"
    
    # Verificar se o MongoDB foi chamado corretamente
    mock_mongodb.insert_one.assert_called_once()
    
    # Verificar documento enviado
    called_args = mock_mongodb.insert_one.call_args[0][0]
    assert called_args["nome_prospect"] == "Teste da Silva"
    assert called_args["email_prospect"] == "teste@example.com"
    assert called_args["whatsapp_prospect"] == "5511987654321"
    assert called_args["empresa_prospect"] == "Empresa Teste"
    assert called_args["faturamento_empresa"] == "1-5 milhões"
    assert called_args["cargo_prospect"] == "Diretor"
    assert called_args["pipe_stage"] == "fit_to_rapport"
    assert called_args["spiced_stage"] == "P1"
    
    # Verificar se a API Sales Builder foi chamada corretamente
    mock_sales_builder_api.assert_called_once()
    api_call_args = mock_sales_builder_api.call_args[0][0]
    assert api_call_args["nome_prospect"] == "Teste da Silva"
    assert api_call_args["email_prospect"] == "teste@example.com"
    assert api_call_args["whatsapp_prospect"] == "5511987654321"
    assert api_call_args["empresa_prospect"] == "Empresa Teste"
    assert api_call_args["faturamento_prospect"] == "1-5 milhões"
    assert api_call_args["cargo_prospect"] == "Diretor"

# Teste com API key inválida
def test_submit_form_invalid_api_key(client, mock_mongodb, mock_settings):
    """
    Testa a submissão de formulário com API key inválida
    
    Verifica se o endpoint /submit-form/ rejeita requisições
    com API key inválida, retornando status 401.
    """
    # Dados de teste com API key inválida
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "teste@example.com",
        "whatsapp": "+5511987654321",
        "company": "Empresa Teste",
        "revenue": "1-5 milhões",
        "job_title": "Diretor",
        "api_key": "invalid_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 401
    assert response.json()["detail"] == "Chave API inválida"
    
    # Verificar que o MongoDB não foi chamado
    mock_mongodb.insert_one.assert_not_called()

# Teste com dados inválidos
def test_submit_form_invalid_data(client, mock_mongodb, mock_settings):
    """
    Testa a submissão de formulário com dados inválidos
    
    Verifica se o endpoint /submit-form/ rejeita requisições
    com dados inválidos, retornando status 422.
    """
    # Dados de teste inválidos (email incorreto)
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "email_invalido",  # Email inválido
        "whatsapp": "+5511987654321",
        "company": "Empresa Teste",
        "revenue": "1-5 milhões",
        "job_title": "Diretor",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 422  # Erro de validação
    
    # Verificar que o MongoDB não foi chamado
    mock_mongodb.insert_one.assert_not_called()

# Teste com faturamento inválido
def test_submit_form_any_revenue(client, mock_mongodb, mock_settings, mock_sales_builder_api):
    """
    Testa a submissão de formulário com qualquer valor de faturamento
    
    Verifica se o endpoint /submit-form/ aceita requisições
    com qualquer valor de faturamento, retornando status 201.
    """
    # Dados de teste com faturamento personalizado
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "teste@example.com",
        "whatsapp": "+5511987654321",
        "company": "Empresa Teste",
        "revenue": "Valor Personalizado",  # Faturamento personalizado
        "job_title": "Diretor",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 201
    assert "document_id" in response.json()
    assert "sales_builder_task_id" in response.json()
    assert response.json()["message"] == "Formulário recebido com sucesso"
    assert response.json()["sales_builder_task_id"] == "mock_task_id"
    
    # Verificar se o MongoDB foi chamado corretamente
    mock_mongodb.insert_one.assert_called_once()
    
    # Verificar documento enviado
    called_args = mock_mongodb.insert_one.call_args[0][0]
    assert called_args["faturamento_empresa"] == "Valor Personalizado"
    assert called_args["pipe_stage"] == "fit_to_rapport"
    assert called_args["spiced_stage"] == "P1"
    
    # Verificar se a API Sales Builder foi chamada corretamente
    mock_sales_builder_api.assert_called_once()
    api_call_args = mock_sales_builder_api.call_args[0][0]
    assert api_call_args["faturamento_prospect"] == "Valor Personalizado"

# Teste com número de WhatsApp formatado
def test_submit_form_formatted_whatsapp(client, mock_mongodb, mock_settings, mock_sales_builder_api):
    """
    Testa a submissão de formulário com número de WhatsApp formatado
    
    Verifica se o endpoint /submit-form/ aceita requisições
    com número de WhatsApp contendo formatação (espaços, hífens),
    limpa o número corretamente e retorna status 201.
    """
    # Dados de teste com número de WhatsApp formatado
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "teste@example.com",
        "whatsapp": "+55 11 98765-4321",  # Número formatado
        "company": "Empresa Teste",
        "revenue": "1-5 milhões",
        "job_title": "Diretor",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 201
    assert "document_id" in response.json()
    assert "sales_builder_task_id" in response.json()
    assert response.json()["message"] == "Formulário recebido com sucesso"
    assert response.json()["sales_builder_task_id"] == "mock_task_id"
    
    # Verificar se o MongoDB foi chamado corretamente
    mock_mongodb.insert_one.assert_called_once()
    
    # Verificar documento enviado
    called_args = mock_mongodb.insert_one.call_args[0][0]
    assert called_args["nome_prospect"] == "Teste da Silva"
    assert called_args["email_prospect"] == "teste@example.com"
    assert called_args["whatsapp_prospect"] == "5511987654321"  # Número limpo sem o +
    assert called_args["empresa_prospect"] == "Empresa Teste"
    assert called_args["faturamento_empresa"] == "1-5 milhões"
    assert called_args["cargo_prospect"] == "Diretor"
    assert called_args["pipe_stage"] == "fit_to_rapport"
    assert called_args["spiced_stage"] == "P1"
    
    # Verificar se a API Sales Builder foi chamada corretamente
    mock_sales_builder_api.assert_called_once()
    api_call_args = mock_sales_builder_api.call_args[0][0]
    assert api_call_args["whatsapp_prospect"] == "5511987654321" 

# Teste com falha na chamada à API Sales Builder
def test_submit_form_sales_builder_api_failure(client, mock_mongodb, mock_settings, mock_sales_builder_api):
    """
    Testa a submissão de formulário quando a chamada à API Sales Builder falha
    
    Verifica se o endpoint /submit-form/ ainda retorna status 201 mesmo quando
    a chamada à API Sales Builder falha, incluindo uma mensagem de erro na resposta.
    """
    # Configurar o mock para lançar uma exceção
    mock_sales_builder_api.side_effect = Exception("API Sales Builder indisponível")
    
    # Dados de teste
    test_data = {
        "full_name": "Teste da Silva",
        "corporate_email": "teste@example.com",
        "whatsapp": "+5511987654321",
        "company": "Empresa Teste",
        "revenue": "1-5 milhões",
        "job_title": "Diretor",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 201
    assert "document_id" in response.json()
    assert "sales_builder_error" in response.json()
    assert "Formulário recebido com sucesso" in response.json()["message"]
    assert "API Sales Builder indisponível" in response.json()["sales_builder_error"]
    
    # Verificar se o MongoDB foi chamado corretamente
    mock_mongodb.insert_one.assert_called_once()
    
    # Verificar se a API Sales Builder foi chamada
    mock_sales_builder_api.assert_called_once() 

# Teste para verificar detecção de leads duplicados
def test_submit_form_duplicate_whatsapp(client, mock_mongodb, mock_settings, mock_sales_builder_api):
    """
    Testa a submissão de formulário com número de WhatsApp duplicado
    
    Verifica se o endpoint /submit-form/ detecta corretamente quando um número
    de WhatsApp já existe na coleção e retorna uma resposta apropriada sem
    inserir um novo documento ou chamar a API Sales Builder.
    """
    # Configurar o mock para simular um lead existente
    existing_lead = {
        "_id": "existing_id",
        "nome_prospect": "Lead Existente",
        "email_prospect": "existente@example.com",
        "whatsapp_prospect": "5511987654321",
        "empresa_prospect": "Empresa Existente",
        "faturamento_empresa": "1-5 milhões",
        "cargo_prospect": "CEO",
        "pipe_stage": "fit_to_rapport",
        "spiced_stage": "P1"
    }
    
    # Configurar o mock para retornar o lead existente quando find_one for chamado
    mock_mongodb.find_one.return_value = existing_lead
    
    # Dados de teste com o mesmo número de WhatsApp
    test_data = {
        "full_name": "Novo Lead",
        "corporate_email": "novo@example.com",
        "whatsapp": "+5511987654321",  # Mesmo número do lead existente
        "company": "Nova Empresa",
        "revenue": "5-10 milhões",
        "job_title": "CTO",
        "api_key": "test_api_key"
    }
    
    # Enviar requisição
    response = client.post("/submit-form/", json=test_data)
    
    # Verificar resposta
    assert response.status_code == 201  # Created
    assert "document_id" in response.json()
    assert response.json()["document_id"] == "existing_id"
    assert "is_duplicate" in response.json()
    assert response.json()["is_duplicate"] == True
    assert "Lead já existe" in response.json()["message"]
    
    # Verificar que o MongoDB.find_one foi chamado com o número de WhatsApp correto
    mock_mongodb.find_one.assert_called_once_with({"whatsapp_prospect": "5511987654321"})
    
    # Verificar que o MongoDB.insert_one não foi chamado
    mock_mongodb.insert_one.assert_not_called()
    
    # Verificar que a API Sales Builder não foi chamada
    mock_sales_builder_api.assert_not_called() 