# API ARDUUS DB

API para interface com o banco de dados MongoDB da Arduus. Este projeto serve como um ponto centralizado para todas as APIs que interagem com o banco de dados da empresa.

## VISÃO GERAL

A API Arduus DB é uma aplicação FastAPI que fornece endpoints para interagir com o banco de dados MongoDB da Arduus. Atualmente, ela inclui funcionalidades para:

- Coleta de dados de formulários com validação rigorosa
- Autenticação via chave API
- Rate limiting para proteção contra abusos
- Logs estruturados para monitoramento
- Testes automatizados para garantir a qualidade do código

## TECNOLOGIAS

- **Backend**: Python 3.11+, FastAPI 0.115.8
- **Banco de Dados**: MongoDB Atlas
- **Validação de Dados**: Pydantic 2.10.6
- **Testes**: Pytest 8.0.0, Pytest-asyncio 0.23.5
- **Logging**: Structlog 25.1.0
- **Deploy**: Docker, Google Cloud Run

## REQUISITOS

- Python 3.11+
- Cluster no MongoDB Atlas
- Conta no Google Cloud Platform (para deploy)
- Docker (opcional, para desenvolvimento local com contêineres)

## ESTRUTURA DO PROJETO

```
api-arduus-db/
├── main.py                # Arquivo principal da aplicação
├── test_main.py           # Testes automatizados
├── requirements.txt       # Dependências do projeto
├── Dockerfile             # Configuração para build da imagem Docker
├── cloudbuild.yaml        # Configuração para deploy no Google Cloud
├── .env                   # Variáveis de ambiente (não versionado)
├── .gitignore             # Arquivos ignorados pelo git
└── README.md              # Documentação do projeto
```

## CONFIGURAÇÃO INICIAL

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/api-arduus-db.git
cd api-arduus-db
```

2. Crie um arquivo `.env` na raiz do projeto com:
```
MONGO_URI=mongodb+srv://<usuario>:<senha>@<cluster>.mongodb.net/?retryWrites=true&w=majority
CORS_ORIGINS=*
API_KEY=sua_chave_api
```

3. Instale as dependências:
```bash
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

## EXECUÇÃO LOCAL

```bash
uvicorn main:app --reload
```

Acesse a documentação interativa em:
http://localhost:8000/docs

## TESTES

O projeto inclui testes automatizados para garantir a qualidade do código. Para executar os testes:

```bash
python -m pytest test_main.py -v
```

Os testes cobrem:
- Verificação do endpoint de health check
- Submissão de formulário com dados válidos
- Validação de API key
- Validação de dados de entrada
- Tratamento de erros

## DEPLOY NO GOOGLE CLOUD RUN

1. Ative os serviços no Console GCP:
   - Cloud Build
   - Cloud Run
   - Artifact Registry

2. Execute o deploy:
```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_MONGO_URI="sua-uri-mongodb",_CORS_ORIGINS="https://seu-frontend.com",_API_KEY="sua-chave-api"
```

3. Acesse a URL gerada pelo Cloud Run

## ENDPOINTS DA API

### Submissão de Formulário

**Endpoint**: `POST /submit-form/`

**Descrição**: Recebe dados de um formulário e armazena no MongoDB.

**Autenticação**: Requer API key no corpo da requisição.

**Rate Limiting**: 200 requisições por minuto por IP.

**Corpo da Requisição**:
```json
{
  "full_name": "João Silva",
  "corporate_email": "joao@empresa.com",
  "whatsapp": "+5511999999999",
  "company": "Tech Ltda",
  "revenue": "1-5 milhões",
  "job_title": "CTO",
  "api_key": "sua_chave_api"
}
```

**Campos**:
- `full_name`: Nome completo do prospect (3-100 caracteres)
- `corporate_email`: Email corporativo válido
- `whatsapp`: Número de WhatsApp no formato internacional
- `company`: Nome da empresa (2-50 caracteres)
- `revenue`: Faturamento da empresa (valores aceitos: "Até 1 milhão", "1-5 milhões", "5-10 milhões", "Acima de 10 milhões")
- `job_title`: Cargo do prospect (opcional, máx 50 caracteres)
- `api_key`: Chave de API para autenticação

**Resposta de Sucesso (201 Created)**:
```json
{
  "message": "Formulário recebido com sucesso",
  "document_id": "60f1b5b3e4b0b2b5b8b5b5b5"
}
```

**Erros Possíveis**:
- `401 Unauthorized`: API key inválida
- `422 Unprocessable Entity`: Dados inválidos
- `429 Too Many Requests`: Rate limit excedido
- `500 Internal Server Error`: Erro no servidor

### Health Check

**Endpoint**: `GET /health`

**Descrição**: Verifica se a API está online.

**Resposta de Sucesso (200 OK)**:
```json
{
  "status": "online"
}
```

## ESTRUTURA DO BANCO DE DADOS

### Coleção: `crm_db`

**Documento**:
```json
{
  "_id": ObjectId("60f1b5b3e4b0b2b5b8b5b5b5"),
  "nome_prospect": "João Silva",
  "email_prospect": "joao@empresa.com",
  "whatsapp_prospect": "+5511999999999",
  "empresa_prospect": "Tech Ltda",
  "faturamento_empresa": "1-5 milhões",
  "cargo_prospect": "CTO"
}
```

## SEGURANÇA

- **Autenticação**: Via chave API no corpo da requisição
- **Rate Limiting**: 200 requisições/minuto por IP
- **Validação de Dados**: Rigorosa validação via Pydantic
- **CORS**: Configurável via variáveis de ambiente
- **Logs**: Estruturados para facilitar auditoria

## MONITORAMENTO

- **Logs Estruturados**: Via structlog no Cloud Logging
- **Health Check**: Endpoint `/health` para verificação de status
- **Rastreamento de Erros**: Detalhado para facilitar depuração

## ROADMAP

- [ ] Adicionar autenticação JWT para endpoints administrativos
- [ ] Implementar dashboard para visualização de dados
- [ ] Adicionar mais endpoints para consulta de dados
- [ ] Implementar cache para melhorar performance
- [ ] Adicionar suporte a webhooks para integrações

## CONTRIBUIÇÃO

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## LICENÇA

Este projeto é propriedade da Arduus e seu uso é restrito conforme os termos da empresa.