# Exemplos de Comandos Curl para Testar a API Arduus DB

Este arquivo contém exemplos de comandos curl para testar os endpoints da API Arduus DB. Você pode copiar e colar estes comandos no terminal para executá-los.

## Configuração

Antes de executar os comandos, substitua `sua_chave_api` pela sua chave API real.

```bash
# Defina a URL base da API
API_URL="http://localhost:8000"

# Defina sua chave API
API_KEY="sua_chave_api"
```

## Health Check

```bash
# Verificar se a API está online
curl -X GET $API_URL/health
```

## Submissão de Formulário com Dados Válidos

```bash
# Enviar formulário com dados válidos
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Teste da Silva",
    "corporate_email": "teste@empresa.com",
    "whatsapp": "+5511987654321",
    "company": "Empresa Teste",
    "revenue": "1-5 milhões",
    "job_title": "Diretor",
    "api_key": "sua_chave_api"
  }' \
  $API_URL/submit-form/
```

## Teste de API Key Inválida

```bash
# Enviar formulário com API key inválida
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Teste da Silva",
    "corporate_email": "teste@empresa.com",
    "whatsapp": "+5511987654321",
    "company": "Empresa Teste",
    "revenue": "1-5 milhões",
    "job_title": "Diretor",
    "api_key": "chave_invalida"
  }' \
  $API_URL/submit-form/
```

## Teste de Dados Inválidos

```bash
# Enviar formulário com email inválido
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Teste da Silva",
    "corporate_email": "email_invalido",
    "whatsapp": "+5511987654321",
    "company": "Empresa Teste",
    "revenue": "1-5 milhões",
    "job_title": "Diretor",
    "api_key": "sua_chave_api"
  }' \
  $API_URL/submit-form/
```

## Teste de Faturamento Inválido

```bash
# Enviar formulário com faturamento inválido
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Teste da Silva",
    "corporate_email": "teste@empresa.com",
    "whatsapp": "+5511987654321",
    "company": "Empresa Teste",
    "revenue": "Valor Inválido",
    "job_title": "Diretor",
    "api_key": "sua_chave_api"
  }' \
  $API_URL/submit-form/
```

## Versão PowerShell

Para usuários do Windows, aqui estão os mesmos comandos em PowerShell:

```powershell
# Definir variáveis
$apiUrl = "http://localhost:8000"
$apiKey = "sua_chave_api"

# Health Check
Invoke-RestMethod -Uri "$apiUrl/health" -Method Get

# Submissão de Formulário com Dados Válidos
$validBody = @{
    full_name = "Teste da Silva"
    corporate_email = "teste@empresa.com"
    whatsapp = "+5511987654321"
    company = "Empresa Teste"
    revenue = "1-5 milhões"
    job_title = "Diretor"
    api_key = $apiKey
} | ConvertTo-Json

Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $validBody -ContentType "application/json"

# Teste de API Key Inválida
$invalidKeyBody = @{
    full_name = "Teste da Silva"
    corporate_email = "teste@empresa.com"
    whatsapp = "+5511987654321"
    company = "Empresa Teste"
    revenue = "1-5 milhões"
    job_title = "Diretor"
    api_key = "chave_invalida"
} | ConvertTo-Json

# Este comando vai falhar com erro 401, o que é esperado
try {
    Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $invalidKeyBody -ContentType "application/json"
} catch {
    Write-Host "Erro esperado: $($_.Exception.Message)"
}
``` 