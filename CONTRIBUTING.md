# Contribuindo para a API Arduus DB

Obrigado pelo interesse em contribuir com a API Arduus DB! Este documento fornece diretrizes e instruções para contribuir com o projeto.

## Índice

1. [Configuração do Ambiente de Desenvolvimento](#configuração-do-ambiente-de-desenvolvimento)
2. [Estrutura do Código](#estrutura-do-código)
3. [Estilo de Código](#estilo-de-código)
4. [Processo de Desenvolvimento](#processo-de-desenvolvimento)
5. [Testes](#testes)
6. [Documentação](#documentação)
7. [Submissão de Pull Requests](#submissão-de-pull-requests)

## Configuração do Ambiente de Desenvolvimento

### Pré-requisitos

- Python 3.11+
- MongoDB (local ou remoto)
- Git

### Passos para Configuração

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/api-arduus-db.git
   cd api-arduus-db
   ```

2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   
   # Linux/Mac:
   source venv/bin/activate
   
   # Windows:
   venv\Scripts\activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Crie um arquivo `.env` na raiz do projeto:
   ```
   MONGO_URI=mongodb://localhost:27017
   CORS_ORIGINS=*
   API_KEY=dev_api_key
   ```

5. Execute a aplicação:
   ```bash
   uvicorn main:app --reload
   ```

## Estrutura do Código

```
api-arduus-db/
├── main.py                # Arquivo principal da aplicação
├── test_main.py           # Testes automatizados
├── requirements.txt       # Dependências do projeto
├── Dockerfile             # Configuração para build da imagem Docker
├── cloudbuild.yaml        # Configuração para deploy no Google Cloud
├── .env                   # Variáveis de ambiente (não versionado)
├── .gitignore             # Arquivos ignorados pelo git
├── README.md              # Documentação do projeto
└── CONTRIBUTING.md        # Guia de contribuição (este arquivo)
```

### Componentes Principais

- **Settings**: Classe para configurações da aplicação
- **FormSubmission**: Modelo Pydantic para validação de dados
- **RateLimiter**: Implementação de rate limiting
- **Endpoints**: Funções para manipulação de requisições HTTP

## Estilo de Código

Este projeto segue as convenções de estilo do PEP 8 para Python. Algumas diretrizes específicas:

- Use 4 espaços para indentação (não tabs)
- Limite as linhas a 88 caracteres
- Use docstrings no formato Google para documentar classes e funções
- Use nomes descritivos para variáveis e funções
- Escreva testes para todas as novas funcionalidades

Recomendamos o uso de ferramentas como `black`, `flake8` e `isort` para manter a consistência do código.

## Processo de Desenvolvimento

1. **Planejamento**: Discuta novas funcionalidades ou correções de bugs nos issues do GitHub
2. **Desenvolvimento**: Implemente as mudanças em uma branch separada
3. **Testes**: Escreva testes para as novas funcionalidades
4. **Documentação**: Atualize a documentação conforme necessário
5. **Revisão**: Submeta um Pull Request para revisão
6. **Merge**: Após aprovação, as mudanças serão mescladas à branch principal

## Testes

Este projeto utiliza `pytest` para testes automatizados. Para executar os testes:

```bash
python -m pytest test_main.py -v
```

### Escrevendo Novos Testes

- Coloque os novos testes no arquivo `test_main.py`
- Use fixtures para configurar o ambiente de teste
- Siga o padrão de nomenclatura `test_[funcionalidade]_[cenário]`
- Utilize mocks para evitar dependências externas

## Documentação

A documentação é uma parte crucial deste projeto. Ao contribuir, certifique-se de:

- Adicionar docstrings a todas as novas funções e classes
- Atualizar o README.md com informações sobre novas funcionalidades
- Documentar novos endpoints na seção de API do README
- Manter este guia de contribuição atualizado

## Submissão de Pull Requests

1. Certifique-se de que seu código passa em todos os testes
2. Atualize a documentação conforme necessário
3. Descreva as mudanças feitas no Pull Request
4. Referencie issues relacionados no Pull Request
5. Aguarde a revisão e feedback da equipe

## Dúvidas?

Se você tiver dúvidas sobre o processo de contribuição, entre em contato com a equipe da Arduus através do email [contato@arduus.tech](mailto:contato@arduus.tech).

Agradecemos sua contribuição para tornar a API Arduus DB ainda melhor! 