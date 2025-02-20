# API ARDUUS DB

API para coleta de dados de formulários da Arduus com autenticação e rate limiting.

## TECNOLOGIAS
- Python 3.11
- FastAPI
- MongoDB Atlas
- Google Cloud Run (para deploy)

## REQUISITOS
- Python 3.11+
- Cluster no MongoDB Atlas
- Conta no Google Cloud Platform

## CONFIGURAÇÃO INICIAL

1. Crie um arquivo .env na raiz do projeto com:
```
MONGO_URI=mongodb+srv://<usuario>:<senha>@<cluster>.mongodb.net/?retryWrites=true&w=majority
CORS_ORIGINS=*
API_KEY=sua_chave_api
```

2. Instale as dependências:
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

## ENDPOINTS PRINCIPAIS

### [POST] /submit-form
Envia dados do formulário

Exemplo de corpo da requisição:
```json
{
  "full_name": "João Silva",
  "corporate_email": "joao@empresa.com",
  "whatsapp": "+5511999999999",
  "company": "Tech Ltda",
  "revenue": "1-5 milhões",
  "api_key": "seu_segredo_super_secreto"
}
```

### [GET] /health
Verifica status da API

## SEGURANÇA
- Autenticação via chave API no corpo da requisição
- Rate limiting de 200 requisições/minuto por IP
- Validação rigorosa de dados
- CORS configurável via variáveis de ambiente

## MONITORAMENTO
- Logs estruturados no Cloud Logging
- Métricas de performance
- Endpoint de health check
- Rastreamento de erros detalhado

## CONTRIBUIÇÃO
1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request