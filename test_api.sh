#!/bin/bash
# Script para testar a API Arduus DB
# Autor: Claude
# Data: $(date +%Y-%m-%d)

# Cores para melhor visualização
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Configurações
API_URL="http://localhost:8000"
API_KEY="sua_chave_api" # Substitua pela sua chave API real

# Função para exibir mensagens formatadas
print_message() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCESSO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRO]${NC} $1"
}

print_header() {
    echo -e "\n${YELLOW}===== $1 =====${NC}\n"
}

# Função para testar o health check
test_health_check() {
    print_header "TESTANDO HEALTH CHECK"
    
    print_message "Enviando requisição GET para $API_URL/health"
    
    response=$(curl -s -w "\n%{http_code}" $API_URL/health)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ]; then
        print_success "Health check retornou status 200 OK"
        print_message "Resposta: $body"
    else
        print_error "Health check falhou com status $http_code"
        print_message "Resposta: $body"
    fi
}

# Função para testar o envio de formulário com dados válidos
test_valid_form_submission() {
    print_header "TESTANDO ENVIO DE FORMULÁRIO VÁLIDO"
    
    print_message "Enviando requisição POST para $API_URL/submit-form/"
    
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{
            "full_name": "Teste da Silva",
            "corporate_email": "teste@empresa.com",
            "whatsapp": "+5511987654321",
            "company": "Empresa Teste",
            "revenue": "1-5 milhões",
            "job_title": "Diretor",
            "api_key": "'$API_KEY'"
        }' \
        $API_URL/submit-form/)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 201 ]; then
        print_success "Formulário enviado com sucesso (status 201 Created)"
        print_message "Resposta: $body"
    else
        print_error "Envio de formulário falhou com status $http_code"
        print_message "Resposta: $body"
    fi
}

# Função para testar o envio de formulário com API key inválida
test_invalid_api_key() {
    print_header "TESTANDO API KEY INVÁLIDA"
    
    print_message "Enviando requisição POST com API key inválida"
    
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
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
        $API_URL/submit-form/)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 401 ]; then
        print_success "Teste de API key inválida passou (status 401 Unauthorized)"
        print_message "Resposta: $body"
    else
        print_error "Teste de API key inválida falhou com status $http_code (esperado 401)"
        print_message "Resposta: $body"
    fi
}

# Função para testar o envio de formulário com dados inválidos
test_invalid_form_data() {
    print_header "TESTANDO DADOS DE FORMULÁRIO INVÁLIDOS"
    
    print_message "Enviando requisição POST com email inválido"
    
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{
            "full_name": "Teste da Silva",
            "corporate_email": "email_invalido",
            "whatsapp": "+5511987654321",
            "company": "Empresa Teste",
            "revenue": "1-5 milhões",
            "job_title": "Diretor",
            "api_key": "'$API_KEY'"
        }' \
        $API_URL/submit-form/)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 422 ]; then
        print_success "Teste de validação de dados passou (status 422 Unprocessable Entity)"
        print_message "Resposta: $body"
    else
        print_error "Teste de validação de dados falhou com status $http_code (esperado 422)"
        print_message "Resposta: $body"
    fi
}

# Função para testar o envio de formulário com faturamento inválido
test_invalid_revenue() {
    print_header "TESTANDO FATURAMENTO INVÁLIDO"
    
    print_message "Enviando requisição POST com faturamento inválido"
    
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{
            "full_name": "Teste da Silva",
            "corporate_email": "teste@empresa.com",
            "whatsapp": "+5511987654321",
            "company": "Empresa Teste",
            "revenue": "Valor Inválido",
            "job_title": "Diretor",
            "api_key": "'$API_KEY'"
        }' \
        $API_URL/submit-form/)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 422 ]; then
        print_success "Teste de faturamento inválido passou (status 422 Unprocessable Entity)"
        print_message "Resposta: $body"
    else
        print_error "Teste de faturamento inválido falhou com status $http_code (esperado 422)"
        print_message "Resposta: $body"
    fi
}

# Menu principal
print_header "TESTE DA API ARDUUS DB"
print_message "Este script testa os endpoints da API Arduus DB"
print_message "Certifique-se de que a API está rodando em $API_URL"
print_message "Substitua a API_KEY no script pela sua chave real antes de executar"

echo -e "\nEscolha uma opção:"
echo "1. Testar todos os endpoints"
echo "2. Testar apenas health check"
echo "3. Testar apenas envio de formulário válido"
echo "4. Testar apenas API key inválida"
echo "5. Testar apenas dados de formulário inválidos"
echo "6. Testar apenas faturamento inválido"
echo "0. Sair"

read -p "Opção: " option

case $option in
    1)
        test_health_check
        test_valid_form_submission
        test_invalid_api_key
        test_invalid_form_data
        test_invalid_revenue
        ;;
    2)
        test_health_check
        ;;
    3)
        test_valid_form_submission
        ;;
    4)
        test_invalid_api_key
        ;;
    5)
        test_invalid_form_data
        ;;
    6)
        test_invalid_revenue
        ;;
    0)
        print_message "Saindo..."
        exit 0
        ;;
    *)
        print_error "Opção inválida"
        exit 1
        ;;
esac

print_header "TESTES CONCLUÍDOS" 