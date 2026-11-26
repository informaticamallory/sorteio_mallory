# Ponto de restauração — versão estável v1.0

| Item | Valor |
| --- | --- |
| Data e hora | 26/11/2026, 10:49 (horário de Brasília, UTC-3) |
| Commit do código estável | `a0b5b04` — *Telao: "Imagem meramente ilustrativa" abaixo das imagens dos premios* (é a versão que está em produção) |
| Commit do checkpoint | o commit `Checkpoint - Versão estável do sistema`, que só acrescenta este arquivo ao `a0b5b04` |
| Tag | `checkpoint-estavel-v1.0` (aponta para o commit do checkpoint) |
| Branch de segurança | `backup/versao-estavel-v1.0` (mesmo commit da tag) |
| Repositório | `https://github.com/informaticamallory/sorteio_mallory` (branch `main`) |
| Banco | revisão de migração **`0017`** (Alembic) |
| Validação | backend: **439 testes passando** (pytest, 26/11/2026); frontend: checagem de tipos (`tsc -b`) sem erros |

> O hash do commit do checkpoint não pode estar escrito dentro do próprio commit. Para vê-lo:
> `git rev-parse checkpoint-estavel-v1.0`.

---

## 1. O que este ponto preserva (no Git)

- **Código-fonte completo:** `backend/` (FastAPI) e `frontend/` (React + TypeScript + Tailwind).
- **Componentes, layouts, estilos e identidade visual:** `frontend/src/` (páginas, componentes,
  `index.css`, `tailwind.config.js`, logos e ícones).
- **Integrações e APIs:** rotas em `backend/app/routers/`, serviços em `backend/app/services/`,
  tempo real por SSE (`bus.py`, `useTelao.ts`, `useCanalPrivado.ts`), Web Push (`pywebpush`).
- **Dependências com versões fixas:** `backend/requirements.txt`, `frontend/package.json` e
  `frontend/package-lock.json`.
- **Estrutura do banco:** `backend/app/models.py` e as migrações `backend/migrations/versions/`
  (`0001` a `0017`).
- **Configuração de execução e publicação:** `Dockerfile`, `backend/.env.example`,
  `scripts/*.ps1`, `docs/publicar-easypanel.md`.
- **Testes:** `backend/tests/` (33 arquivos).

## 2. O que NÃO está no Git (de propósito) e como guardar

| Item | Onde fica | Por que não vai para o Git | Como guardar |
| --- | --- | --- | --- |
| **Banco de produção** (dados reais) | servidor do Easypanel, volume `/data` (no host: `/srv/sorteio/dados/sorteio.db`) | dados pessoais (LGPD) | procedimento da seção 4 |
| **Fotos e imagens enviadas** | `/data/uploads` no servidor | dados pessoais | junto com o banco (seção 4) |
| **Chave de identificação** (`chave-identificacao.key`) | `/data` no servidor | segredo: sem ela os códigos de CPF/nascimento deixam de conferir | cópia fora do servidor, em local seguro (seção 4) |
| **Chaves do push** (`vapid.json`) | `/data` no servidor | segredo | junto com a chave de identificação |
| **Variáveis do Easypanel** (`SECRET_KEY`, `ADMIN_*`, `URL_PUBLICA`...) | painel do Easypanel | segredos | anotar em cofre de senhas; os nomes estão em `backend/.env.example` |
| `backend/.env` desta máquina | local | segredos | não versionar; recriar a partir do `.env.example` |
| Bancos locais de desenvolvimento | `%LOCALAPPDATA%\sorteio-confraternizacao\` e `backend/data/` (antigo) | dados locais | não fazem parte do sistema em produção |
| Capturas de tela de testes | `docs/telas-*/` | podem mostrar nomes reais | não necessárias para restaurar |
| `node_modules/`, `.venv/`, `dist/` | local | gerados pela instalação/build | recriados pelos comandos da seção 5 |

**Regra:** banco, fotos e zips de exportação com dados pessoais **nunca** vão para o Git, para o
OneDrive nem por e-mail.

## 3. Configurações e dependências necessárias

- **Python 3.11+** (produção: imagem `python:3.13-slim-bookworm`) e **Node.js 20+** (build:
  `node:22-bookworm-slim`).
- Backend: FastAPI 0.115.6, Uvicorn 0.34.0, SQLAlchemy 2.0.36, Alembic 1.14.0, Pydantic 2.10.4,
  PyJWT 2.10.1, openpyxl 3.1.5, Pillow 11.1.0, pywebpush 2.5.0, segno 1.6.6, cryptography 50.0.2.
- Frontend: React 18.3.1, React Router 6.28.1, jsQR 1.4.0, Vite 6.0.7, TypeScript 5.7.2,
  Tailwind 3.4.17.
- Banco: SQLite (WAL), em `/data` na produção. Migrações aplicadas sozinhas ao iniciar, com
  backup automático antes.
- Produção (Easypanel): imagem do `Dockerfile` da raiz, porta 8000, **uma única réplica**,
  zero downtime desligado, volume persistente montado em `/data`.
- Variáveis de ambiente: ver a tabela em `README.md` → *Configuração* e `backend/.env.example`.

## 4. Backup do banco de produção (separado do Git)

Feito **no servidor**, por quem tem acesso a ele. O `.backup` do SQLite é seguro com o sistema
rodando e não altera o banco. Os caminhos abaixo são os do guia `docs/publicar-easypanel.md`
(pasta do host montada em `/data`); se a montagem no Easypanel usar outra pasta, troque
`/srv/sorteio/dados` por ela.

```bash
mkdir -p /srv/sorteio/backups/checkpoint-v1.0
sqlite3 /srv/sorteio/dados/sorteio.db ".backup '/srv/sorteio/backups/checkpoint-v1.0/sorteio.db'"
cp -a /srv/sorteio/dados/uploads /srv/sorteio/backups/checkpoint-v1.0/
cp -a /srv/sorteio/dados/chave-identificacao.key /srv/sorteio/dados/vapid.json /srv/sorteio/backups/checkpoint-v1.0/ 2>/dev/null
sqlite3 /srv/sorteio/backups/checkpoint-v1.0/sorteio.db "PRAGMA integrity_check; SELECT version_num FROM alembic_version;"
```

O último comando deve responder `ok` e `0017`. Guarde uma cópia da `chave-identificacao.key`
fora do servidor (cofre de senhas ou mídia criptografada), **nunca** no OneDrive ou por e-mail.
O backup diário automático está descrito em `docs/publicar-easypanel.md`, seção 5.

## 5. Como restaurar esta versão

### Ver o que mudou desde o checkpoint

```bash
git fetch --tags origin
git log --oneline checkpoint-estavel-v1.0..main
```

### Voltar o código para o checkpoint (sem perder o histórico)

Cria um commit novo que desfaz o que veio depois, sem reescrever a `main`:

```bash
git switch main
git revert --no-edit checkpoint-estavel-v1.0..HEAD
git push origin main
```

Depois, **Deploy** no Easypanel.

### Alternativa: só olhar ou testar o checkpoint

```bash
git switch --detach checkpoint-estavel-v1.0
```

ou trabalhar a partir da branch de segurança:

```bash
git switch backup/versao-estavel-v1.0
```

### Reinstalar e rodar localmente

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\instalar.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\testar.ps1
```

### Atenção ao banco ao voltar a versão

- O código deste checkpoint espera o banco na revisão **`0017`**. Se uma versão futura tiver
  aplicado migrações novas (`0018` em diante), **não basta voltar o código**: o banco precisa
  voltar junto.
- Antes de cada migração, o sistema guarda um backup automático em `/data/backups/`
  (`...-antes-da-migracao-00XX.db`). Para voltar o banco: pare o serviço no Easypanel, copie o
  backup certo (ou o da seção 4) para `/srv/sorteio/dados/sorteio.db`, apague os arquivos
  `sorteio.db-wal` e `sorteio.db-shm` que estiverem ao lado e inicie o serviço com o código
  deste checkpoint.
- Alternativa para desfazer migrações novas mantendo os dados atuais (na pasta `backend`, com
  o serviço parado): `alembic downgrade 0017`. Confira antes o `downgrade()` de cada migração.
- **Nunca** apague o banco para resolver erro de migração.

## 6. Funcionalidades existentes neste ponto

- **Eventos:** criar, editar e excluir (só o admin; apagar de vez só sem sorteios); identidade
  visual (logo, cores), mensagens, regras de participação, som, fuso, animações reduzidas.
- **Participantes:** cadastro manual (com ajuste de enquadramento da foto), importação CSV/XLSX
  com prévia (zeros à esquerda preservados; CPF e nascimento só como HMAC), presença e
  participação com motivo, zerar participantes.
- **Prêmios:** lista ou colunas, imagem, descrição, quantidade, ordem, duplicar, importação
  CSV/XLSX (cabeçalhos variados de quantidade, aviso quando a quantidade não é lida, atualizar
  quantidade dos existentes), excluir (admin, inclusive com sorteio).
- **Blocos:** distribuição automática (nova ou nos blocos criados), organização manual com
  arrastar, misturar (dado) e exportar, numeração que recomeça do 01, excluir bloco (admin).
- **Regras e modos:** número da sorte ou faixa de matrículas; vitória única/múltipla; presença;
  ganhador ausente; histórico de regras.
- **Sorteio:** por bloco ou prêmio a prêmio, semiautomático e automático (pausa de 0,5 a 60 s),
  conferência de elegíveis, anulação com motivo e resorteio, sorteio aleatório uniforme
  (`secrets.randbelow`) com snapshot dos elegíveis e idempotência.
- **Telão:** espera, prêmio, suspense (0,5 a 20 s), ganhador com foto e setor, carrossel dos
  ganhadores (0,5 a 30 s por ganhador), encerramento; "imagem meramente ilustrativa"; som;
  sincronização em tempo real pelo relógio do servidor.
- **Recepção e Credenciamento:** check-in público (`/recepcao`) quando aberto; credenciamento
  (confirmar e desfazer presença; pulseira e liberar novo cadastro só admin); atalhos entre
  evento e check-in.
- **Central de Entregas:** busca e QR Code, abas por situação com contagem, filtros em chips,
  lista com setor, entrega em lote, foto opcional da entrega, desfazer (com justificativa),
  anular sorteio pendente (admin), histórico de atendimentos e exportação.
- **Portal do Colaborador:** autocadastro pelo QR Code (CPF/nascimento conferidos por HMAC),
  Cartão da Sorte, prêmios, notificações (SSE e push), perfil com foto ajustável.
- **Usuários e perfis:** Admin, Organizador — RH, Sorteador, Recepção, Equipe de Entregas,
  Colaborador; sessões, bloqueio por tentativas, senha temporária, auditoria.
- **Histórico, relatório e auditoria:** pesquisa sem acento, filtros, exportação CSV/XLSX.
