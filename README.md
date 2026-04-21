# Provecta NF-e — Distribuição DFe

Sistema desktop em Python para consulta e gestão de Notas Fiscais Eletrônicas diretamente da SEFAZ, via API de Distribuição DFe (DF-e).

---

## Funcionalidades

- Consulta de NF-e por CNPJ diretamente na SEFAZ
- Download automático dos XMLs (NF-e completa, resumos e eventos)
- Identificação e marcação automática de **notas canceladas**
- Controle de status de cada documento:
  - `Pendente` — recebida, aguardando processamento
  - `Entrada OK` — entrada confirmada no sistema
  - `Cancelada` — cancelamento detectado automaticamente via evento SEFAZ
  - `Ignorada` — descartada pelo usuário
- Exportação individual (`.xml`) ou em lote (`.zip`)
- Filtro por status e busca por emitente, CNPJ ou chave de acesso
- Banco de dados local (SQLite) — histórico persistente entre sessões
- Sistema de **licença offline** com chave de ativação
- Suporte a ambiente de **homologação** e **produção**

---

## Tecnologias

| Tecnologia | Uso |
|---|---|
| Python 3.14 | Linguagem principal |
| tkinter | Interface gráfica desktop |
| pynfe | Comunicação com a SEFAZ |
| lxml | Parsing de XML |
| signxml | Assinatura digital XML |
| SQLite | Banco de dados local |
| HMAC-SHA256 | Geração e validação de licenças |

---

## Estrutura do Projeto

```
provecta/
├── main.py          # Interface gráfica (tkinter)
├── sefaz.py         # Comunicação com a SEFAZ via pynfe
├── database.py      # Persistência local (SQLite)
├── licenca.py       # Validação de chave de ativação
├── keygen.py        # Gerador de chaves de ativação (CLI)
├── requirements.txt # Dependências
└── secret.key       # Segredo HMAC — NÃO commitar (ver .gitignore)
```

---

## Instalação

**Pré-requisitos:** Python 3.14+

```bash
# Clone o repositório
git clone https://github.com/MateusDosReisF/provectaDFE.git
cd provectaDFE

# Instale as dependências
pip install -r requirements.txt
```

> **Atenção:** o arquivo `secret.key` não está incluso no repositório por segurança.
> Para uso em produção, crie o arquivo com o segredo fornecido pelo desenvolvedor.

---

## Como Usar

### 1. Gerar uma chave de ativação

```bash
python keygen.py
```

Ou via argumentos:

```bash
# 1 chave com 365 dias de validade
python keygen.py --dias 365 --qtd 1

# 5 chaves com 180 dias
python keygen.py --dias 180 --qtd 5

# Ativações ilimitadas
python keygen.py --dias 365 --ilimitado

# Inspecionar uma chave existente
python keygen.py --inspecionar AAAAA-BBBBB-CCCCC-DDDDD-EEEEE
```

### 2. Rodar o sistema

```bash
python main.py
```

Na primeira execução, o sistema solicitará a chave de ativação.

### 3. Configurar a consulta

Preencha no painel lateral:

- **Certificado (.pfx)** — certificado digital A1 da empresa
- **Senha** — senha do certificado
- **CNPJ** — CNPJ do destinatário (formatação automática)
- **UF** — estado da empresa
- **NSU Inicial** — número sequencial de onde iniciar a busca (0 = início)
- **Ambiente** — marque "Homologação" para testes

Clique em **Iniciar Consulta** e acompanhe o log em tempo real.

---

## Tipos de Documento Recebidos

| Schema | Tipo |
|---|---|
| `procNFe_v4.00.xsd` | NF-e Completa |
| `resNFe_v1.01.xsd` | Resumo NF-e |
| `procEventoNFe_v1.00.xsd` | Evento (cancelamento, CC-e, manifestação) |

### Eventos tratados automaticamente

| Código | Evento |
|---|---|
| 110111 | Cancelamento |
| 110112 | Cancelamento por substituição |
| 110110 | Carta de Correção (CC-e) |
| 210200 | Confirmação da Operação |
| 210210 | Ciência da Operação |
| 210220 | Desconhecimento da Operação |
| 210240 | Operação não Realizada |

---

## Sistema de Licença

As chaves de ativação são geradas offline via HMAC-SHA256 e contêm:

- Data de expiração
- Número máximo de ativações (ou ilimitado)

A chave ativada é armazenada localmente em `.license` e validada a cada inicialização do sistema.

> O arquivo `secret.key` é o segredo usado para assinar e validar as chaves. **Mantenha-o em segurança e nunca o compartilhe.**

---

## Segurança e Privacidade

Os seguintes arquivos são ignorados pelo Git (`.gitignore`) e **nunca devem ser commitados:**

| Arquivo | Motivo |
|---|---|
| `secret.key` | Segredo de geração de chaves |
| `.license` | Chave de ativação local |
| `chaves_*.txt` | Chaves geradas para clientes |
| `provecta.db` | Banco com XMLs e dados fiscais |
| `*.pfx` / `*.p12` | Certificados digitais |

---

## Licença

Projeto proprietário — todos os direitos reservados.
Uso permitido apenas mediante chave de ativação válida.
