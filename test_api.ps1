# Script PowerShell para testar a API Arduus DB
# Autor: Claude
# Data: $(Get-Date -Format "yyyy-MM-dd")

# Configurações
$apiUrl = "http://localhost:8000"
$apiKey = "ARci43B+1cYfm+5XY82YJ8ME8g3paWyT7AoUnO7VrGw=" # Substitua pela sua chave API real

# Função para exibir mensagens formatadas
function Write-ColorMessage {
    param (
        [string]$Message,
        [string]$Type = "INFO"
    )
    
    switch ($Type) {
        "SUCCESS" { Write-Host "[SUCESSO] $Message" -ForegroundColor Green }
        "ERROR" { Write-Host "[ERRO] $Message" -ForegroundColor Red }
        "INFO" { Write-Host "[INFO] $Message" -ForegroundColor Blue }
        "HEADER" { 
            Write-Host "`n===== $Message =====" -ForegroundColor Yellow
            Write-Host ""
        }
    }
}

# Função para testar o health check
function Test-HealthCheck {
    Write-ColorMessage "TESTANDO HEALTH CHECK" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição GET para $apiUrl/health"
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get -ErrorAction Stop
        Write-ColorMessage "Health check retornou status 200 OK" -Type "SUCCESS"
        Write-ColorMessage "Resposta: $($response | ConvertTo-Json -Compress)"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-ColorMessage "Health check falhou com status $statusCode" -Type "ERROR"
        Write-ColorMessage "Erro: $($_.Exception.Message)"
    }
}

# Função para testar o envio de formulário com dados válidos
function Test-ValidFormSubmission {
    Write-ColorMessage "TESTANDO ENVIO DE FORMULÁRIO VÁLIDO" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST para $apiUrl/submit-form/"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "teste@empresa.com"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "1-5 milhões"
        job_title = "Diretor"
        api_key = $apiKey
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Formulário enviado com sucesso (status 201 Created)" -Type "SUCCESS"
        Write-ColorMessage "Resposta: $($response | ConvertTo-Json -Compress)"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-ColorMessage "Envio de formulário falhou com status $statusCode" -Type "ERROR"
        Write-ColorMessage "Erro: $($_.Exception.Message)"
    }
}

# Função para testar o envio de formulário com API key inválida
function Test-InvalidApiKey {
    Write-ColorMessage "TESTANDO API KEY INVÁLIDA" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST com API key inválida"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "teste@empresa.com"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "1-5 milhões"
        job_title = "Diretor"
        api_key = "chave_invalida"
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Teste falhou: Deveria ter retornado erro 401" -Type "ERROR"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 401) {
            Write-ColorMessage "Teste de API key inválida passou (status 401 Unauthorized)" -Type "SUCCESS"
        }
        else {
            Write-ColorMessage "Teste de API key inválida falhou com status $statusCode (esperado 401)" -Type "ERROR"
        }
    }
}

# Função para testar o envio de formulário com dados inválidos
function Test-InvalidFormData {
    Write-ColorMessage "TESTANDO DADOS DE FORMULÁRIO INVÁLIDOS" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST com email inválido"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "email_invalido"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "1-5 milhões"
        job_title = "Diretor"
        api_key = $apiKey
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Teste falhou: Deveria ter retornado erro 422" -Type "ERROR"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 422) {
            Write-ColorMessage "Teste de validação de dados passou (status 422 Unprocessable Entity)" -Type "SUCCESS"
        }
        else {
            Write-ColorMessage "Teste de validação de dados falhou com status $statusCode (esperado 422)" -Type "ERROR"
        }
    }
}

# Função para testar o envio de formulário com faturamento anteriormente inválido
function Test-InvalidRevenue {
    Write-ColorMessage "TESTANDO FATURAMENTO ANTERIORMENTE INVÁLIDO" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST com faturamento anteriormente inválido"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "teste@empresa.com"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "Valor Inválido"
        job_title = "Diretor"
        api_key = $apiKey
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Teste de faturamento anteriormente inválido passou (status 201 Created)" -Type "SUCCESS"
        Write-ColorMessage "Resposta: $($response | ConvertTo-Json -Compress)"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-ColorMessage "Teste de faturamento anteriormente inválido falhou com status $statusCode (esperado 201)" -Type "ERROR"
        Write-ColorMessage "Erro: $($_.Exception.Message)"
    }
}

# Função para testar o envio de formulário com valor personalizado de faturamento
function Test-CustomRevenueFormSubmission {
    Write-ColorMessage "TESTANDO ENVIO DE FORMULÁRIO COM VALOR PERSONALIZADO DE FATURAMENTO" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST para $apiUrl/submit-form/"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "teste@example.com"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "Valor Totalmente Personalizado"
        job_title = "Diretor"
        api_key = $apiKey
    }
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body ($body | ConvertTo-Json) -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Formulário com valor personalizado de faturamento enviado com sucesso (status 201)" -Type "SUCCESS"
        Write-ColorMessage "Resposta: $($response | ConvertTo-Json -Compress)"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-ColorMessage "Envio de formulário com valor personalizado de faturamento falhou com status $statusCode" -Type "ERROR"
        Write-ColorMessage "Erro: $($_.Exception.Message)"
        
        if ($statusCode -eq 422) {
            Write-ColorMessage "Detalhes da validação: $($_.ErrorDetails.Message)" -Type "ERROR"
        }
    }
}

# Função para testar o envio de formulário com faturamento personalizado
function Test-CustomRevenue {
    Write-ColorMessage "TESTANDO FATURAMENTO PERSONALIZADO" -Type "HEADER"
    
    Write-ColorMessage "Enviando requisição POST com faturamento personalizado"
    
    $body = @{
        full_name = "Teste da Silva"
        corporate_email = "teste@empresa.com"
        whatsapp = "+5511987654321"
        company = "Empresa Teste"
        revenue = "Valor Personalizado"
        job_title = "Diretor"
        api_key = $apiKey
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/submit-form/" -Method Post -Body $body -ContentType "application/json" -ErrorAction Stop
        Write-ColorMessage "Teste de faturamento personalizado passou (status 201 Created)" -Type "SUCCESS"
        Write-ColorMessage "Resposta: $($response | ConvertTo-Json -Compress)"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-ColorMessage "Teste de faturamento personalizado falhou com status $statusCode (esperado 201)" -Type "ERROR"
        Write-ColorMessage "Erro: $($_.Exception.Message)"
    }
}

# Menu principal
Write-ColorMessage "TESTE DA API ARDUUS DB" -Type "HEADER"
Write-ColorMessage "Este script testa os endpoints da API Arduus DB"
Write-ColorMessage "Certifique-se de que a API está rodando em $apiUrl"
Write-ColorMessage "Substitua a variável `$apiKey no script pela sua chave real antes de executar"

Write-Host "`nEscolha uma opção:"
Write-Host "1. Testar todos os endpoints"
Write-Host "2. Testar apenas health check"
Write-Host "3. Testar apenas envio de formulário válido"
Write-Host "4. Testar apenas API key inválida"
Write-Host "5. Testar apenas dados de formulário inválidos"
Write-Host "6. Testar apenas faturamento inválido"
Write-Host "7. Testar envio de formulário com valor personalizado de faturamento"
Write-Host "8. Testar faturamento personalizado"
Write-Host "0. Sair"

$option = Read-Host "Opção"

switch ($option) {
    "1" {
        Test-HealthCheck
        Test-ValidFormSubmission
        Test-InvalidApiKey
        Test-InvalidFormData
        Test-InvalidRevenue
        Test-CustomRevenueFormSubmission
        Test-CustomRevenue
    }
    "2" { Test-HealthCheck }
    "3" { Test-ValidFormSubmission }
    "4" { Test-InvalidApiKey }
    "5" { Test-InvalidFormData }
    "6" { Test-InvalidRevenue }
    "7" { Test-CustomRevenueFormSubmission }
    "8" { Test-CustomRevenue }
    "0" { 
        Write-ColorMessage "Saindo..."
        exit 
    }
    default {
        Write-ColorMessage "Opção inválida" -Type "ERROR"
        exit 1
    }
}

Write-ColorMessage "TESTES CONCLUÍDOS" -Type "HEADER" 