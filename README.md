# Sorteio da Confraternização

Sistema web para conduzir o sorteio de prêmios da confraternização de fim de ano, com
**painel do organizador** e **telão do evento** sincronizados em tempo real.

O organizador pode operar pelo celular ou por outro computador enquanto o telão, ligado ao
projetor, se atualiza sozinho.

---

## Índice

- [Como rodar](#como-rodar)
- [Primeiro uso](#primeiro-uso)
- [No dia do evento](#no-dia-do-evento)
- [Configuração](#configuração)
- [Arquitetura](#arquitetura)
- [Garantias de confiabilidade](#garantias-de-confiabilidade)
- [O que foi implementado](#o-que-foi-implementado)
- [Testes](#testes)
- [Limitações conhecidas](#limitações-conhecidas)

---

## Como rodar

Requisitos: **Python 3.11+** e **Node.js 20+**. Não é preciso Docker nem PostgreSQL.

### Instalação (uma vez)

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\instalar.ps1
```

Cria o ambiente virtual do Python, instala as dependências do backend e do frontend e copia
`backend/.env.example` para `backend/.env`.

### Dados de demonstração (opcional)

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\carregar-demo.ps1
```

Cria um evento com 60 participantes e 8 prêmios fictícios. Tudo marcado com `demo = true`,
exibido com uma faixa de demonstração no painel e na Recepção — nunca se mistura a um evento
real. O nome do evento não leva prefixo (o telão mostra o nome como está cadastrado).
Para remover: `.\scripts\carregar-demo.ps1 -Limpar`.

### Desenvolvimento

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\iniciar-dev.ps1
```

Backend em `http://localhost:8000` (documentação interativa em `/docs`), frontend em
`http://localhost:5173` com recarga automática.

### Modo evento (produção)

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\iniciar-evento.ps1
```

Gera o build do frontend e sobe **um único servidor na porta 8000, em HTTPS**, que serve a API e a
interface. O script imprime os endereços de acesso pela rede local (`https://<ip>:8000`).

**HTTPS na rede local.** O navegador só libera a câmera ao vivo (scanner de QR Code da Central de
Entregas, foto do perfil) em HTTPS. O script cria, em `DATA_DIR/https/`, uma autoridade
certificadora própria (`ca.crt` / `ca.cer`, 10 anos) e o certificado do servidor (397 dias) para
`localhost`, o nome do computador e os IPs da rede. O certificado do servidor é refeito sozinho
quando o IP muda ou está para vencer; a autoridade é mantida.

- Na primeira vez, cada aparelho mostra "Sua conexão não é particular": toque em **Avançado →
  Continuar**. A página funciona normalmente depois disso, inclusive o scanner.
- Para tirar o aviso de vez, instale `ca.cer` como autoridade confiável no aparelho (Android:
  Configurações → Segurança → Instalar certificado CA; iPhone: abrir o arquivo, instalar o perfil e
  ativar em Ajustes → Geral → Sobre → Confiança de certificados; Windows: abrir `ca.cer` →
  Instalar → "Autoridades de Certificação Raiz Confiáveis"). Não compartilhe `ca.key`.
- O push no celular continua desligado: ele precisa de um endereço com certificado confiável em
  todos os aparelhos (a publicação final em HTTPS) e de `URL_PUBLICA`/`VAPID_SUBJECT`.
- Endereços `http://` antigos deixam de abrir (a porta agora fala HTTPS). Para voltar ao HTTP:
  `iniciar-evento.ps1 -SemHttps`.

Se outro aparelho não conseguir conectar, libere a porta no firewall:

```bash
New-NetFirewallRule -DisplayName "Sorteio" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Publicar na internet (Docker / Easypanel)

O `Dockerfile` da raiz gera uma imagem única (frontend + backend) que serve em HTTP na porta
8000, atrás do HTTPS do Easypanel. Os dados ficam em `/data`, que precisa ser uma pasta
persistente do servidor, e o serviço precisa rodar com **uma única réplica**.
`scripts\exportar-dados.ps1` empacota banco, chave de identificação, chaves do push e imagens
para levar ao servidor. Passo a passo completo: [docs/publicar-easypanel.md](docs/publicar-easypanel.md).

---

## Primeiro uso

Credenciais iniciais (definidas em `backend/.env` — **troque antes do evento**):

```
usuário: *********
senha:   *********
```

1. **Entrar** e criar um evento.
2. **Configuração** — nome, logo, cores, mensagens de boas-vindas e encerramento, regras de
   participação, som, duração da animação e fuso horário. Nessa aba também está o **link do
   telão**, que é o endereço a abrir no computador do projetor.
3. **Participantes** — cadastro manual ou importação de planilha (CSV/XLSX, com modelo para
   download, prévia e apontamento de erros antes de confirmar).
4. **Prêmios** — nome, imagem, descrição, quantidade de unidades e ordem de apresentação.
5. **Regras** — escolher o **modo do sorteio**, definir elegibilidade e **confirmar as regras**
   antes do primeiro sorteio. Modos (por evento, admin ou Organizador — RH):
   - **Número da sorte** (padrão): todos os elegíveis concorrem com a mesma chance.
   - **Faixa de matrículas**: só concorrem os elegíveis com matrícula numérica entre a inicial e a
     final (zeros à esquerda não contam; matrícula com letras nunca concorre neste modo). A tela
     mostra quantos ficam dentro e fora da faixa antes de salvar. O ganhador é sorteado de forma
     uniforme entre os elegíveis da faixa — mesma distribuição de "sortear um número na faixa e
     repetir até cair em alguém". Presença e demais regras continuam valendo, cada resultado grava
     o modo e a faixa na auditoria e toda troca de modo ou faixa fica no histórico de regras.
     Neste modo **a matrícula é o número da sorte exibido**: aparece no Cartão da Sorte (cadastro
     e área pessoal), na consulta da Recepção e no telão (resultado, carrossel e encerramento) —
     exceção à regra "matrícula fora do telão", por decisão do evento. O número aleatório continua
     existindo por trás (QR Code do cartão e busca da Central de Entregas). Voltando ao modo
     padrão, tudo volta a mostrar o número aleatório e o telão volta a não receber matrícula.

---

## No dia do evento

**Antes de abrir as portas**
1. Nos computadores ou tablets da recepção, abra o endereço do sistema. O botão
   **Recepção** da tela inicial entra **sem senha**, em qualquer aparelho (ou abra direto
   `/recepcao`).
2. Em **Blocos**, distribua os prêmios (padrão: 25 unidades por bloco).
3. Abra o **link do telão** no computador do projetor e acione **Tela cheia**. Se o som
   estiver ativado, clique uma vez em **Ativar som** (navegadores exigem interação do
   usuário para liberar áudio).
4. (Opcional) Para o **Portal do Colaborador**, importe a planilha com **data de nascimento e
   CPF**, ligue **Cadastro pelo celular aberto** em Configuração e divulgue o **QR Code**
   (baixar PNG ou imprimir) — ver [Portal do Colaborador](#portal-do-colaborador).

**Chegada (Recepção)**
5. Na tela inicial, **Recepção** → **Check-in**: digite a **matrícula**; aparecem matrícula,
   nome e **número do sorteio**; confira e clique em **Confirmar check-in**. A presença é
   o que habilita a pessoa a concorrer.
6. **Consultar**: pelo nome (sem acento, qualquer parte) ou pela matrícula, mostra o número
   do sorteio, se o check-in já foi feito e **se a pessoa já foi sorteada** (prêmio, bloco e
   se já retirou — só depois que o telão revelou).
7. O **organizador** acompanha em **Credenciamento** quem chegou, entrega/troca pulseiras e,
   se usar o autocadastro, libera novo cadastro (com motivo, fica na auditoria).

**Sorteio**
8. O **sorteador**, na aba **Sorteio**: inicia o bloco, confere os elegíveis, clica em
   **Iniciar sorteio** e acompanha a animação. Na revelação, o celular do ganhador recebe o
   aviso.
9. Ao **finalizar o bloco**, o telão apresenta sozinho o **carrossel dos ganhadores** do
   bloco. O cartão **Apresentação dos ganhadores** controla pausar, continuar, anterior,
   próximo, repetir e encerrar. O próximo bloco **só pode ser sorteado depois de encerrar a
   apresentação** — nada começa sozinho.

**Entrega**
10. O **organizador**, em **Entregas**, busca o ganhador por nome, matrícula ou pulseira,
    confere a pulseira apresentada e confirma a entrega. Em **Visão geral** ele acompanha os
    ganhadores (atualiza a cada 10 s) e as pendências de entrega.
11. Ao final, **Ir para o encerramento** exibe a galeria de todos os ganhadores.

O painel mostra um indicador de **Sincronizado / Reconectando / Sem conexão**. Atualizar a
página ou reconectar o telão nunca refaz um sorteio nem perde o slide do carrossel: o estado
é recuperado do servidor.

---

## Configuração

Todas as opções ficam em `backend/.env` (veja `backend/.env.example`).

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `SECRET_KEY` | *(exemplo)* | Assinatura dos tokens de sessão. **Troque.** |
| `TOKEN_EXPIRA_MINUTOS` | `720` | Validade da sessão do organizador. |
| `DATABASE_URL` | SQLite em `DATA_DIR` | **Deixe sem definir** para usar o padrão. Para PostgreSQL: `postgresql+psycopg://user:senha@host:5432/sorteio`. |
| `DATA_DIR` | ver abaixo | Pasta do banco, dos backups de migração e dos uploads. |
| `EVENT_TIMEZONE` | `America/Sao_Paulo` | Fuso usado na exibição e nas exportações. |
| `ADMIN_USUARIO` / `ADMIN_SENHA` / `ADMIN_NOME` | `organizador` / `sorteio2026` | Organizador criado no primeiro boot. **Troque a senha.** |
| `MAX_UPLOAD_BYTES` | `5242880` | Limite por imagem (5 MB). |
| `MAX_PLANILHA_BYTES` | `10485760` | Limite da planilha (10 MB). |
| `CORS_ORIGINS` | `*` | Origens permitidas, separadas por vírgula. |
| `AUTOCADASTRO_MAX_FALHAS_MATRICULA` | `5` | Tentativas erradas de identificação por matrícula (com ou sem zeros), a cada 15 min. |
| `URL_PUBLICA` | *(vazio)* | Endereço que os celulares usam (vai no QR Code). Ex.: `https://sorteio.mallory.com.br`. Vazio: o painel sugere o IP da rede local deste computador. |
| `CHAVE_IDENTIFICACAO` | *(arquivo)* | Chave dos códigos de CPF/nascimento. Vazia: criada em `DATA_DIR/chave-identificacao.key`. **Não perca nem troque** (os códigos importados deixam de conferir; basta reimportar). |
| `CADASTRO_PASSE_MINUTOS` | `20` | Validade do passe entre identificar e confirmar o cadastro. |
| `VAPID_SUBJECT` | *(vazio)* | Contato para o Web Push (`mailto:...` ou `https://...`). Vazio: usa `URL_PUBLICA` se for https; sem nenhum dos dois, o push fica desligado. Chaves VAPID em `DATA_DIR/vapid.json`. |

Por evento (aba **Configuração**): cadastro pelo celular aberto/fechado, período opcional,
QR Code e o tempo de cada ganhador no carrossel (mínimo 5 s).

### Onde ficam os dados

Por padrão em `backend/data/`. **Exceção importante:** se o projeto estiver dentro de uma
pasta sincronizada (OneDrive, Dropbox, Google Drive, iCloud), o sistema grava em
`%LOCALAPPDATA%\sorteio-confraternizacao` e avisa no console durante o boot.

O motivo é concreto: o serviço de sincronização trava o arquivo do banco durante o upload e
provoca `database is locked` em plena operação — isso aconteceu de verdade durante o
desenvolvimento. Se quiser escolher a pasta, defina `DATA_DIR`.

> **Atenção para quem instalou antes de 13/11/2026:** o `.env.example` antigo trazia
> `DATABASE_URL=sqlite:///./data/sorteio.db`, que coloca o banco **dentro do OneDrive** e
> anula a proteção acima. Se o seu `.env` tem essa linha, o boot avisa. Para corrigir, pare o
> servidor, mova `backend/data/sorteio.db` para `%LOCALAPPDATA%\sorteio-confraternizacao\` e
> apague a linha `DATABASE_URL` do `.env`.

**Faça backup da pasta de dados** (banco + imagens) antes e depois do evento.

### Migrações do banco

O schema é versionado com **Alembic** (`backend/migrations/`). O servidor aplica as migrações
pendentes **sozinho, no boot**, e antes disso:

- faz um **backup** do SQLite em `<pasta do banco>/backups/`;
- se o banco for da versão 1 (criado antes das migrações), o **adota** na revisão `0001`
  dentro da mesma transação — mas só se o schema for exatamente o da v1; qualquer outro
  caso é recusado sem alterar nada;
- roda tudo em uma única transação, com as FKs desligadas durante a migração e
  `PRAGMA foreign_key_check` antes do commit.

Comandos manuais (na pasta `backend`, com o ambiente virtual):

```bash
python -m app.migracoes --status
```

```bash
python -m app.migracoes
```

Para criar uma nova revisão: `alembic revision --autogenerate -m "descricao"` e revise o
arquivo gerado — no SQLite, colunas com FK devem ser adicionadas com `ALTER TABLE` como em
`0002`, para não recriar tabelas com histórico.

| Revisão | Conteúdo |
| --- | --- |
| `0001` | Schema da v1 (baseline, idêntico ao antigo `create_all`). |
| `0002` | Fase 1: `blocos_sorteio`, `notificacoes`, `users.papel`, `participants.pulseira` e `usuario_id`, `prize_units.bloco_id`, `draws.bloco_id`. |
| `0003` | Fase 2: `events.capacidade_bloco_padrao` (25), `prize_units.ordem_bloco` e índice que permite um único bloco `EM_ANDAMENTO` por evento. |
| `0004` | Fase 3: `participants.nome_busca` e `prizes.nome_busca` (nome sem acento, para a pesquisa), preenchidas para os registros existentes. |
| `0005` | Fase 4: em `users`, versão da sessão, último acesso, tentativas de login, bloqueio temporário e senha temporária pendente. Contas existentes preservadas. |
| `0006` | Fases 5 a 8: em `events`, `autocadastro_ativo` (desligado), `autocadastro_confirma_presenca` e `carrossel_segundos` (padrão 6, CHECK ≥ 5; a `0016` baixou o mínimo para 1 e a `0017` para 0,5, com a coluna passando a decimal); em `notificacoes`, `prize_id` e `disponivel_em`; em `display_states`, o estado oficial do carrossel. Só acréscimos. |
| `0007` | Perfis: `RECEPCAO` (entregas) vira `ORGANIZADOR` e `CHECKIN` vira a nova `RECEPCAO`; as contas afetadas têm a sessão encerrada. Para trocar o CHECK do papel sem recriar `users`, a coluna é copiada, removida (`DROP COLUMN` nativo) e recriada. `participants.numero_sorteio` (aleatório, único por evento; os existentes recebem o seu). O downgrade devolve os papéis antigos. |
| `0008` | Portal do Colaborador: `participants.matricula_normalizada` (preenchida para os existentes; a original não muda), `identificacao_hash` e `cpf_hash` (códigos HMAC, vazios até a próxima importação; índice único de CPF por evento), `events.autocadastro_inicio/fim`, `notificacoes.push_enviado_em` e a tabela `push_inscricoes`. Só acréscimos. |
| `0009` | Gerenciador de Blocos: `blocos_sorteio.descricao` (opcional, vazia nos blocos existentes). Só acréscimo. |
| `0010` | Perfis: `users.papel` aceita `ENTREGAS` (CHECK trocado como na 0007); contas `ORGANIZADOR` existentes viram `ENTREGAS` (sessão encerrada); `users.setor` e `users.pode_sortear`. O downgrade devolve `ENTREGAS` para `ORGANIZADOR`. |
| `0011` | Modo de sorteio por evento: `events.modo_sorteio` (`numero_sorte` nos eventos existentes — nada muda), `events.matricula_faixa_inicio` e `events.matricula_faixa_fim` (vazias). |
| `0012` | `events.recepcao_publica_ativa`: Recepção sem login (check-in e consulta) só com a chave ligada. Desligada, inclusive nos eventos existentes. |
| `0018` | `events.tema_telao` (`classico` ou `mallory_claro`, CHECK): visual do telão por evento. Os eventos existentes ficam no `classico`. Só acréscimo. |
| `0019` | `events.claro_cor_fundo`, `claro_cor_painel`, `claro_cor_destaque` e `claro_cor_texto`: cores próprias do tema `mallory_claro`, começando na paleta Mallory. Só acréscimos. |
| `0020` | `events.telao_subtitulo` (até 80 caracteres, opcional): texto ao lado da logo no telão claro. Vazio nos eventos existentes (mostra "Sorteios internos"). Só acréscimo. |
| `0021` | `events.evento_teste` (desligado nos existentes): evento de teste, que some do portal do colaborador (aba, prêmios e notificações), não manda aviso nem push e sai da lista de cadastro. Só o admin marca. Só acréscimo. |

### Histórico com pesquisa

A aba **Histórico** pesquisa por nome (completo ou parcial), matrícula, pulseira ou nome do
prêmio, sem diferenciar maiúsculas, minúsculas e acentos — "jose conceicao" encontra "José
da Conceição". Cada palavra digitada precisa aparecer em algum desses campos. A matrícula é
comparada como texto: "00042" não encontra "10042", e "42" encontra as duas.

Filtros combináveis: evento (ou todos), bloco (ou "sem bloco"), intervalo de datas, situação
do sorteio, entrega (pendente, entregue, estornada) e operador. As datas valem no fuso do
evento: um sorteio às 22h30 de 12/12 em São Paulo aparece em 12/12, embora já seja 13/12 em
UTC. Os filtros ficam na URL, então F5, voltar e links compartilhados mantêm a pesquisa.

Tudo é resolvido no banco — filtragem, contagem, ordenação e paginação (`GET /api/sorteios`)
—, e o navegador recebe só a página pedida. **Detalhes** abre a rodada completa: ganhador,
prêmio, bloco, operador, elegíveis, entrega, anulação, a cadeia de anulações e resorteios da
mesma unidade e a auditoria; entrega e anulação continuam disponíveis ali.

As exportações (`/api/sorteios/export.csv` e `.xlsx`) aplicam os mesmos filtros, sem
paginação, e ficam registradas na auditoria com os filtros usados. As exportações por evento
continuam como antes e ganharam, **no fim**, as colunas pulseira, bloco e evento.

### Sorteio por blocos

Aba **Blocos**. A distribuição automática divide as **unidades** (não os tipos de prêmio) em
blocos da capacidade escolhida, na ordem cadastrada dos prêmios — 107 unidades com 25 por
bloco geram blocos de 25, 25, 25, 25 e 7. O botão **Organizar manualmente** abre um quadro
para arrastar prêmios entre blocos e reordená-los; no celular, toque no prêmio e use
"Mover para" e as setas. Nada é gravado até **Salvar distribuição**, e o servidor valida tudo
de uma vez: se uma regra falhar, nenhuma mudança é aplicada.

Regras (aplicadas no backend):

| Situação | Comportamento |
| --- | --- |
| Evento sem blocos | Modo simples, prêmio a prêmio, como antes. |
| Evento com blocos | Só se sorteia unidade do bloco `EM_ANDAMENTO`. |
| Blocos em andamento | No máximo um por evento (índice único no banco). |
| Novo sorteio durante a revelação no telão | Recusado até a animação terminar — impede que dois operadores sobrescrevam a revelação um do outro. A mesma requisição repetida continua devolvendo o resultado original. |
| Distribuição automática | Refaz apenas blocos `PLANEJADO` e unidades sem bloco. |
| Bloco `PLANEJADO` | Aceita qualquer reorganização. |
| Bloco `EM_ANDAMENTO` / `PAUSADO` | Congelado: não ganha, não perde, não reordena. |
| Bloco `FINALIZADO` | Só libera unidades disponíveis (ex.: após uma anulação). |
| Unidade já sorteada | Nunca muda de bloco. O resultado guarda o bloco em que aconteceu. |
| Finalizar | Ação do operador. Com unidades pendentes, exige confirmação. |
| Remanescentes | Novo bloco com as unidades disponíveis sem bloco ou deixadas em blocos finalizados. |

**Por que o bloco não é finalizado automaticamente:** logo após o último sorteio, o caso mais
comum é o ganhador estar ausente → anular → sortear de novo. Encerrar sozinho atropelaria
esse fluxo. Quando restam 0 prêmios, o painel destaca **Finalizar bloco**.

**Gerenciamento de Blocos (tela).** Quatro indicadores em **unidades** (cadastradas,
distribuídas, sem bloco e blocos criados), atualizados após cada operação. Ações:

| Ação | Como funciona |
| --- | --- |
| Novo bloco | Nome (único no evento, sem diferenciar maiúsculas), descrição opcional e capacidade. Nasce **Planejado** e no fim da sequência; o número (`BLOCO 03`) é automático e nunca muda. Bloco vazio existe, mas não pode ser iniciado. |
| Distribuir automaticamente | Abre uma **prévia** (`POST .../blocos/distribuir/previa`, nada é gravado): blocos e unidades de cada um, e quais blocos planejados serão recriados. Só grava em **Confirmar distribuição**. |
| Organizar manualmente | Cada unidade se move sozinha: arrastar e soltar, ou tocar para selecionar (várias de uma vez, "Selecionar todas") e escolher o destino. Pesquisa por produto, filtro por bloco e por situação, subir/descer na ordem do bloco, capacidade com "livres / completo / excedida" (excedida não salva). "Cancelar alterações" desfaz; sair com mudanças pede confirmação. No celular as colunas ficam empilhadas e a barra "Mover para" fica presa no rodapé. |
| Edição simultânea | `GET .../distribuicao` devolve uma `versao`; o salvamento a envia e, se outra pessoa mudou os blocos nesse meio-tempo, recebe 409 e nada é gravado. |
| Reordenar | Setas nos cartões dos blocos planejados (`POST .../blocos/reordenar`). Planejados trocam entre si as posições que já ocupavam; iniciados, pausados e finalizados não se movem. A Central de Sorteio segue essa ordem. |
| Excluir | Só bloco **Planejado sem nenhum sorteio** (conferido de novo na transação). Confirmação mostra o bloco e quantas unidades voltam para "sem bloco". Prêmios, ganhadores e histórico nunca são apagados. Auditoria `bloco_removido` com as unidades liberadas. |
| Remanescentes | Prévia (`POST .../blocos/remanescentes/previa`) e criação respeitando a capacidade: 30 remanescentes com 25 por bloco viram "Prêmios remanescentes 1" (25) e "2" (5). |
| Ver prêmios | Ordem do sorteio, imagem, unidade, situação (aguardando, sorteada, entregue) e pesquisa. Só leitura. |

Permissões inalteradas: criar, editar, distribuir, organizar, reordenar e excluir são do
administrador (`configurar_blocos`); o Sorteador vê os blocos e os conduz (iniciar, pausar,
finalizar). Telas em `docs/telas-blocos/`.

`GET /api/events/{id}/blocos/{bloco}/premiados` devolve os resultados válidos do bloco na
ordem dos sorteios, sem matrícula nem pulseira — é a base do carrossel.

### Recepção: check-in e número do sorteio

A Recepção sem login nasce **fechada** em todo evento. O admin ou o organizador abre em
**Configuração → Recepção sem login → Recepção aberta** (no dia do evento) e fecha do mesmo
jeito. Fechada, a tela inicial não mostra o botão **Recepção** e o servidor recusa check-in e
consulta (403); a equipe logada continua marcando presença em **Credenciamento**. Abrir e fechar
fica na auditoria (`evento_configurado`).

Com ela aberta, a tela inicial tem o botão **Recepção** e, ao lado, usuário e senha para a
equipe. A Recepção (`/recepcao`) **não exige login, em nenhum aparelho**, e tem dois botões: **Check-in**
(matrícula → confere matrícula, nome e número → **Confirmar check-in**) e **Consultar**
(nome ou matrícula). Com mais de um evento cadastrado, pergunta qual (e lembra no aparelho).
Telas em `docs/telas-recepcao-mallory/` (desktop, tablet e celular).

**Visual das telas públicas (identidade Mallory).** Login, Recepção e cadastro do colaborador
(`/cadastro`) usam as mesmas peças de `frontend/src/componentes/Mallory.tsx` (cabeçalho, faixa
de demonstração, boas-vindas, títulos, cartões e rodapé). No cadastro: as 3 etapas com barra de
progresso laranja, campos grandes e a captura de foto no mesmo estilo. No login: cartão laranja **Recepção** (sem senha) e cartão **Equipe do evento** com
usuário e senha. Na Recepção: cabeçalho preto com a logomarca, "Recepção" e o
nome do evento; faixa de demonstração só em eventos de demonstração; cartões **Realizar
Check-in** e **Consultar Participante**. Cores na escala `mallory` do `tailwind.config.js`
(preto `#111111`, laranja `#F16425`, tirado da logomarca oficial). O laranja puro fica nos
detalhes; onde há texto branco sobre laranja, usa-se um tom mais fechado (`#C94A00`) para
manter contraste AA. Desde 18/11/2026 o painel inteiro também segue a identidade: a escala
`marca` do `tailwind.config.js` passou do azul provisório para o laranja Mallory (botões
principais em `#C94A00`), o menu lateral é grafite com o item ativo em laranja e cada página
tem o cabeçalho preto com a logo e o detalhe curvo laranja (`componentes/Casca.tsx`).

**Logomarca:** `frontend/public/marca/mallory-branca.png` é a logo oficial completa (com o
slogan), em branco com fundo transparente, extraída do arquivo enviado
(`original-laranja.png`, mantido ao lado). Um `mallory-branca.svg` na mesma pasta tem
prioridade sobre o PNG (fica mais nítido). Sem nenhum dos dois, o cabeçalho mostra só o
texto "Sorteios Mallory".

| Regra | Como funciona |
| --- | --- |
| Número do sorteio | Todo participante recebe, ao ser incluído (importação, cadastro manual, demonstração), um número **aleatório** (`secrets`) e **único no evento** (índice único no banco): 1000–9999 até 4.500 pessoas; acima disso, 5 dígitos. É identificação: **não interfere na escolha do ganhador**. Aparece no telão junto ao nome do ganhador (resultado, carrossel e encerramento); matrícula e pulseira continuam fora do telão — exceto no modo **Faixa de matrículas**, em que a matrícula é exibida como número da sorte. |
| Check-in | Mostra os dados antes de confirmar; confirmar só **marca** presença (nunca desmarca). Repetir não duplica. Auditoria `presenca_alterada` com origem `recepcao` e o IP. Avisa se a pessoa não está participando. |
| Consulta | Até 20 resultados: matrícula, nome, número, check-in e prêmios sorteados (nome do prêmio, bloco, retirado ou não). Sem foto, setor, pulseira ou dados de conta. |
| Surpresa do palco | Um prêmio só aparece na consulta depois que o telão revelou o ganhador. |
| Conta Recepção | Quem entrar com usuário e senha de perfil Recepção cai no **Credenciamento** do evento e também tem a **Central de Entregas** (localizar, confirmar e histórico; não desfaz nem exporta). |

> **Risco aceito:** como a Recepção é aberta, qualquer pessoa com o endereço do sistema
> consegue confirmar presenças e consultar nome, matrícula, número e prêmios. Mantenha o
> sistema só na rede do evento.

### Ambiente de teste

Para ensaiar os sorteios sem tocar no evento real, o admin usa **Eventos → Ambiente de teste**.
O sistema cria "TESTE — <nome do evento>", marcado como **evento de teste**:

- copia configuração, cores, tema do telão, regras e modo do sorteio, prêmios (imagens e
  quantidades) e blocos com a mesma distribuição — tudo zerado (unidades disponíveis, blocos
  planejados);
- copia os participantes com o **mesmo RE/matrícula e setor**, mas com o **nome trocado por
  "Participante 001…"** (LGPD) e com a presença já confirmada;
- **não copia** sorteios, entregas, notificações, contas, códigos de CPF/nascimento, pulseiras
  nem fotos dos colaboradores.

Evento de teste não aparece no portal do colaborador, não manda aviso nem push ao celular e sai
da lista de cadastro pelo QR Code. Dentro dele, a faixa cinza tem **Recomeçar teste**: apaga os
sorteios e entregas do teste e devolve as unidades aos blocos, para ensaiar de novo. Quando não
precisar mais, exclua o evento de teste em Eventos (vale mesmo com sorteios, com o nome digitado e
a confirmação de que os sorteios vão junto; a auditoria é mantida). Evento real com sorteios
continua sem poder ser apagado.

### Portal do Colaborador

Opcional (desligado por padrão); o caminho principal continua sendo o check-in na Recepção.
O QR Code (Configuração → **Portal do Colaborador**: ver, baixar PNG, imprimir, copiar link,
abrir/fechar e período) leva a `/evento/<id>/cadastro`. Não contém dado pessoal. Telas em
`docs/telas-portal-colaborador/`.

1. **Cadastro para o Sorteio** — matrícula, data de nascimento e 5 primeiros dígitos do CPF.
2. **Confirme seus dados** — nome e matrícula; foto opcional (câmera, galeria, trocar ou
   remover a atual). Não há passo de criar senha: **a senha é os 5 primeiros dígitos do CPF**
   (decisão do cliente, 18/11/2026). O aparelho reenvia nascimento e os 5 dígitos, o servidor
   confere de novo com o código importado e grava só o hash (PBKDF2). Um alerta avisa isso na
   confirmação, no cartão, no login e em Meu Perfil.
3. **Cadastro realizado!** — Meu Cartão da Sorte: número da sorte (o do banco; nunca gerado no
   acesso), nome, foto, matrícula, evento e situação do check-in.

Depois, `/minha-area` (login com a matrícula — "26" também entra como "00026" — e os 5 primeiros
dígitos do CPF como senha; o colaborador pode trocá-la em Meu Perfil) tem
**Meu Cartão**, **Meus Prêmios** (imagem, bloco, rodada, situação real da entrega — só
consulta), **Notificações** (com contador de não lidas) e **Meu Perfil** (trocar/remover foto,
notificações no celular, trocar senha, encerrar sessão). Matrícula, CPF e número não mudam.

| Regra | Como funciona |
| --- | --- |
| Importação | Colunas novas `data_nascimento` e `cpf` (opcionais). CPF validado pelos dígitos verificadores (aceita pontuação e o número que o Excel guardou sem o zero); data em dd/mm/aaaa, aaaa-mm-dd ou célula de data. Duplicidades: matrícula (normalizada) e CPF repetidos na planilha ou já usados por outra matrícula no evento. Quem já existe só recebe CPF/nascimento se marcar **Completar CPF e nascimento**. O resultado mostra criados, atualizados, completados e ignorados. |
| LGPD | O CPF e a data **nunca** são gravados, devolvidos ao navegador nem registrados na auditoria: só dois códigos HMAC-SHA256 com chave secreta (`nascimento + 5 dígitos` e `CPF completo`, este para impedir CPF repetido — índice único no banco). |
| Matrícula | `00026`, `026` e `26` são a mesma (coluna `matricula_normalizada`); a original é preservada. Vale para cadastro, importação, pesquisa, Recepção e login. |
| Identificação | Mensagem única para qualquer dado errado, matrícula inexistente ou participante sem CPF importado. Limites: 5 erros por matrícula (com ou sem zeros) e 20 por IP a cada 15 min. Depois de conferir, só um **passe** de 20 min para concluir — não é sessão e não abre a área pessoal. |
| Primeiro cadastro | Só o primeiro vale; refazer só com **Liberar novo cadastro** (Credenciamento, com motivo). |
| Presença e pulseira | O cadastro **não** confirma presença nem registra pulseira: isso é do check-in da Recepção e do Credenciamento. |
| Foto | Opcional. Validada no backend (Pillow, até 5 MB). A foto trocada ou removida tem o arquivo apagado se ninguém mais a usa. |
| Auditoria | `autocadastro_concluido` (origem `portal_qrcode`), `foto_alterada`, `push_ativado/desativado`, `participantes_importados` (só contagens). |

**Notificações.** Reaproveitam as da Fase 6: criadas na mesma transação do sorteio, uma por
resultado (garantido no banco), visíveis só quando o telão revela o ganhador. O título agora é
"🎉 Parabéns! Você foi sorteado!". Com o portal aberto, o canal SSE privado atualiza cartão,
prêmios e contador e mostra um alerta de premiação.

**Push no celular (PWA).** Manifesto `manifest-portal.json` e service worker `sw-portal.js`
(só recebe push; não intercepta requisições nem guarda cache — o resto do sistema não muda).
O colaborador ativa em Meu Perfil (a permissão só é pedida depois do toque). O servidor envia
o push de `PREMIO_GANHO` assim que a revelação libera a notificação, se o resultado continuar
válido; a marca `push_enviado_em` é gravada antes do envio, então reapresentar no telão ou
reiniciar o servidor não reenvia. O texto não traz prêmio nem dado pessoal. Inscrições vencidas
(404/410) são apagadas. **Exige HTTPS** (`URL_PUBLICA` https ou `VAPID_SUBJECT`) e internet; no
iPhone, iOS 16.4+ com o portal adicionado à Tela de Início. Sem isso, o portal funciona normalmente
com os avisos em tempo real. Entrega não é garantida.

> **Risco aceito pelo cliente:** data de nascimento e início do CPF são previsíveis para quem
> conhece a pessoa, e a senha (5 dígitos do CPF) dispensa até a data de nascimento nos acessos
> seguintes — o começo do CPF aparece em holerites, crachás e sistemas de RH. Barreiras: 5
> erros bloqueiam a conta por 15 min e 20 erros por IP bloqueiam o IP. Não há canal de verificação adicional (o sistema não tem telefone nem
> e-mail dos colaboradores): a validação assistida é a Recepção conferir o crachá e liberar
> novo cadastro.

### Notificações

Quando um sorteio é registrado, o backend cria, **na mesma transação**, uma notificação
persistente ligada ao participante, evento, prêmio e sorteio — no máximo uma por sorteio e
tipo (índice único), então cliques repetidos e reconexões não duplicam. Ela só fica visível
quando o telão revela o ganhador (o celular não estraga a surpresa do palco).

- **Canal privado em tempo real**: `GET /api/minha-area/stream` (SSE), com o token no
  cabeçalho `Authorization` (nunca na URL). A mensagem só diz "mudou"; os dados vêm da API
  autenticada. A cada 20 s sem mensagem, a sessão é reconferida — conta desativada derruba o
  canal. O canal público do telão nunca recebe notificações.
- **Na área pessoal**: sino com contador de não lidas, central com imagem do prêmio, bloco,
  situação atual (aguardando retirada, retirado, anulado), marcar como lida e marcar todas.
- **Anulação**: gera um aviso próprio ao colaborador afetado, com a categoria (ausência,
  desistência, erro operacional), sem o texto escrito pelo admin.
- **Entrega**: a situação muda na área do colaborador na hora.
- Quem ganhou antes de se cadastrar vê a notificação ao concluir o cadastro.

### Anúncio do ganhador no telão

Resultado e carrossel usam o mesmo anúncio (`frontend/src/componentes/AnuncioGanhador.tsx`):
faixa dourada **GANHADOR(A) DO SORTEIO** (no carrossel, **DO BLOCO NN**), cartão do prêmio
com imagem, nome e descrição, e cartão do ganhador com foto (ou ícone), **PARABÉNS!**, nome e
**Número Sorteado** com 4 dígitos. Ao fundo, arcos, brilhos e caixas de presente. As cores
vêm das cores do evento (Configuração); **Reduzir animações** desliga brilhos e entradas.
Testado em 1920×1080 e 1366×768 (`docs/telas-recepcao/`). A segunda linha do prêmio é a
**descrição** cadastrada em Prêmios.

### Carrossel dos ganhadores

Novo estado do telão, `carrossel_ganhadores`. Ao **finalizar um bloco** com ganhadores, o
telão apresenta cada ganhador do bloco (foto, nome, imagem e nome do prêmio, número do bloco)
e termina num slide-resumo. Sem foto ou sem imagem do prêmio, usa iniciais nas cores do
evento ou o ícone de presente.

- **Tempo por ganhador**: configurável em Configuração, **nunca menos de 5 s** (validado no
  formulário, na API e por CHECK no banco; o servidor também aplica o mínimo ao calcular).
- **Estado oficial no servidor**: bloco, posição, início da reprodução e duração. Telão e
  painel calculam o slide pelo relógio do servidor; F5, reconexão ou dois telões mostram o
  mesmo slide.
- **Controles** (Admin e Operador): iniciar (escolhendo o bloco), pausar, continuar, anterior,
  próximo, repetir e encerrar. Tudo auditado.
- **Fim de bloco durante a animação** do último sorteio: a revelação não é cortada; o
  carrossel começa 5 s depois, sozinho.
- O carrossel **só lê resultados**. Enquanto ele está no telão, um novo sorteio é recusado
  ("Encerre a apresentação dos ganhadores…"); iniciar o próximo bloco é permitido, sortear não.
- Um resultado anulado sai do carrossel na próxima atualização.

### Perfis de acesso

O que cada perfil pode fazer está em `backend/app/permissoes.py`, a única fonte dessa
regra. Cada rota declara a permissão que exige, e `tests/test_acesso.py` confere a matriz
rota a rota, perfil a perfil. Uma rota nova sem decisão de acesso faz o teste falhar.

| Área | Admin | Organizador — RH | Sorteador | Recepção | Entregas | Colaborador |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Ver eventos e resumo | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| Check-in e consulta (públicos, sem login) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Criar eventos, usuários, anular resultado, auditoria | ✔ | — | — | — | — | — |
| Configurar o evento (identidade, QR Code, telão, regras) | ✔ | ✔ | — | — | — | — |
| Participantes, prêmios, blocos (distribuir, organizar) | ✔ | ✔ | — | — | — | — |
| Iniciar/pausar/finalizar blocos, sortear, telão | ✔ | se autorizado | ✔ | — | — | — |
| Consultar resultados e histórico de sorteios | ✔ | ✔ | ✔ | — | — | — |
| Visão geral, relatório e exportações | ✔ | ✔ | — | — | — | — |
| Credenciamento: confirmar e desfazer presença | ✔ | ✔ | — | ✔ | — | — |
| Credenciamento: pulseira e liberar novo cadastro | ✔ | — | — | — | — | — |
| Central de Entregas: localizar, confirmar, histórico | ✔ | ✔ | — | ✔ | ✔ | — |
| Desfazer entrega (com justificativa) | ✔ | ✔ | — | — | — | — |
| Exportar histórico de entregas | ✔ | ✔ | — | — | — | — |
| Própria área pessoal e notificações | ✔ | — | — | — | — | ✔ |

**Perfil × setor.** O perfil define o acesso; o **setor** (TI, RH...) só identifica a área da
pessoa e nunca dá permissão. Cada conta tem um perfil, válido em todos os eventos (decisão de
18/11/2026: com um evento por vez, perfis por evento não mudariam nada). O Organizador — RH só
sorteia com **"Pode operar sorteios"** marcado pelo admin em Usuários (`users.pode_sortear`);
mudar o perfil tira a autorização. Toda mudança de perfil, setor ou autorização fica na
auditoria (`usuario_alterado`) e encerra as sessões da conta quando muda o acesso.

**Promover um colaborador** (ex.: alguém do RH que se cadastrou pelo QR Code). Em Usuários →
Editar, o admin troca o perfil de Colaborador para um perfil da equipe. Como a senha do portal
são os 5 dígitos do CPF, a promoção gera uma **senha temporária** (exibida uma vez; a pessoa
cria uma senha forte no primeiro acesso). O login continua a matrícula e o vínculo com o
participante fica: a pessoa segue concorrendo e vê o próprio Cartão da Sorte (atalho "Meu
Cartão da Sorte" no menu). Toda a equipe pode abrir a "Minha área", que só mostra os cadastros
da própria conta. Contas da equipe não voltam a ser Colaborador (use outro perfil ou desative).

No código, o Sorteador é o papel `SORTEIO` e a Equipe de Entregas, `ENTREGAS`. A migração 0007
converteu Recepção (entregas) → Organizador e Check-in → Recepção; a 0010 transformou o
Organizador no "Organizador — RH" e passou as contas que existiam nele (de entregas) para
`ENTREGAS`, sem ninguém ganhar permissão. Em 18/11/2026 o login do administrador passou de
`organizador` para **`admin`** (mesma conta, senha e histórico; `ADMIN_USUARIO=admin` no `.env`).

**Central de Entregas** (aba Entregas). Indicadores (sorteados válidos, entregues, pendentes e
percentual — anulados nunca contam), busca com espera de 300 ms por nome sem acento, matrícula
com ou sem zeros, pulseira, número da sorte ou QR Code do Cartão da Sorte (`MALLORY-SORTE:<evento>:<número>`,
lido por leitor USB, pelo scanner em tela cheia com a câmera ao vivo — HTTPS ou localhost; usa o
leitor nativo do navegador ou o `jsqr` no Windows — ou por foto quando a câmera ao vivo não está
disponível; nunca prova identidade), seleção por teclado
(↑ ↓ e Enter), cartão do ganhador com todos os prêmios, entrega de uma unidade ou de várias
do mesmo ganhador num lote **tudo ou nada** (`POST .../recepcao/entregar`), com conferência da
pulseira e resumo antes de confirmar. Entrega repetida é recusada (409), inclusive com dois
atendentes ao mesmo tempo. Desfazer exige justificativa e guarda a entrega original, quem
desfez, o motivo e o estado antes/depois; o registro original nunca é apagado. Filtros por
situação (padrão: pendentes), bloco, prêmio, período e operador; histórico paginado com
filtros e exportação CSV (admin e RH). O Portal do Colaborador atualiza "Meus Prêmios" na hora.
Registros de entrega anteriores a 13/11/2026 que apontavam para resultados apagados na limpeza
da demonstração aparecem como "Resultado removido" (o id foi reaproveitado; o histórico não
empresta o nome de outra pessoa). Telas em `docs/telas-entregas/`.

O **cadastro pelo QR Code** (`/evento/<id>/cadastro`) não exige login, mas só avança com
matrícula, nascimento e 5 dígitos do CPF conferindo (ver [Portal do Colaborador](#portal-do-colaborador)).
O link e o QR Code no painel são do admin (`GET /api/events/{id}/portal` e `/portal/qrcode.png`).

> **Anulação só pelo admin.** É o que pede a especificação ("o operador não altera
> resultados"). Na prática, com a regra "ausente → anula e sorteia de novo", o operador
> precisa chamar um admin a cada ausência. Para liberar, acrescente `ANULAR_RESULTADO` ao
> papel `SORTEIO` em `permissoes.py`.

**Depois do login** cada perfil vai para a sua tela: admin e organizador → Visão geral;
sorteador → Sorteio; recepção → `/recepcao` (check-in e consulta); colaborador → Minha área. Com um
único evento, a equipe entra direto nele. Os menus mostram só o que o perfil pode usar, mas
**quem decide é o backend**: chamar uma rota sem permissão devolve 403.

**Sessão e senhas.**
- O perfil é lido do banco a cada requisição. Desativar a conta, mudar o perfil, redefinir a
  senha ou "encerrar sessões" invalida na hora os tokens já emitidos.
- 5 senhas erradas seguidas bloqueiam a conta por 15 minutos. Há também um limite por IP,
  somando todas as contas. Usuário inexistente, senha errada e conta inativa recebem a mesma
  resposta, e o bloqueio vale igual para contas inexistentes — a tela de login não revela
  quais contas existem. Ajustável em `LOGIN_MAX_FALHAS_CONTA`, `LOGIN_BLOQUEIO_MINUTOS` e
  `LOGIN_MAX_FALHAS_IP`.
- O admin cria contas e redefine senhas sem escolher nem ver a senha definitiva. O sistema
  gera uma senha temporária, exibida uma única vez, e a pessoa precisa criar a própria no
  primeiro acesso; até lá, todas as outras rotas recusam.
- **Excluir** usuário só vale para contas **sem histórico operacional** (não realizaram, entregaram
  ou anularam sorteios, não finalizaram bloco, não mudaram regra nem fizeram ação de gestão). As
  demais só podem ser desativadas, preservando o histórico. Na exclusão, o participante ligado à
  conta continua na lista (sem conta), os registros pessoais (login, troca de senha, autocadastro)
  ficam na auditoria com o usuário anotado e a ação `usuario_excluido` registra quem excluiu.
  Ninguém exclui, desativa ou rebaixa a si mesmo, e o último administrador ativo é protegido.
  A tela **Usuários** mostra o último acesso e a auditoria de cada conta.
- As contas que já existiam continuam entrando com a mesma senha, sem troca obrigatória.

### Identidade visual

Padrão corporativo, sem efeitos decorativos: fundo `#F7F8FA`, superfícies brancas com borda
`#E5E7EB`, menu lateral grafite `#25282D` (gaveta no celular), cantos de 6–8 px, sem sombras
nos cartões, controles com altura padrão (36 px no painel, 44 px nas telas do colaborador),
ícones lineares próprios (`componentes/Icone.tsx`, sem biblioteca) e fonte Inter quando
instalada, senão Segoe UI.

- **Cor institucional:** escala `marca` em `frontend/tailwind.config.js`. Hoje é um azul
  sóbrio **provisório**; quando a cor oficial da Mallory for definida, troque só essa escala.
- **Classes base** em `frontend/src/index.css`: `cartao`, `campo`, `btn-primario`,
  `btn-neutro`, `btn-perigo`, `btn-sutil`, `btn-icone`, `etiqueta`, `tabela`, `titulo-secao`.
- **Visão geral** (tela inicial do admin): faixa compacta de indicadores, próximo sorteio,
  últimos ganhadores, pendências de entrega e blocos; atualiza a cada 10 s.
- **Telão:** usa as cores e o logotipo configurados no evento. Revelação curta, uma salva
  discreta de confete só no ganhador e carrossel sem efeitos.

Capturas em `docs/telas-sistema/` e `docs/telas-checkin/`.

### Fuso horário

Todos os horários são gravados em **UTC** no banco e convertidos para o fuso do evento
apenas na exibição e na exportação. O fuso é configurável por evento.

---

## Arquitetura

```
sorteio/
├── backend/                    FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py             Aplicação, CORS, arquivos estáticos, SPA
│   │   ├── config.py           Configuração e avisos de ambiente
│   │   ├── database.py         Engine, WAL, BEGIN IMMEDIATE
│   │   ├── migracoes.py        Migrações no boot, backup e adoção da v1
│   │   ├── models.py           Tabelas
│   │   ├── permissoes.py       Papéis e permissões (RBAC)
│   │   ├── schemas.py          Contratos de entrada e saída (Pydantic)
│   │   ├── security.py         PBKDF2 + JWT
│   │   ├── bus.py              Barramento de eventos para o SSE
│   │   ├── seed.py             Dados de demonstração
│   │   ├── texto.py            Normalização de nomes para a pesquisa
│   │   ├── routers/            auth, eventos, participantes, premios, blocos,
│   │   │                       sorteios, historico, relatorios, publico, uploads,
│   │   │                       usuarios, recepcao, credenciamento, minha_area,
│   │   │                       autocadastro
│   │   └── services/           elegibilidade, sorteio, blocos, historico, telao,
│   │                           carrossel, notificacoes, autocadastro, autenticacao,
│   │                           consultas, erros, importacao, exportacao, imagens
│   ├── migrations/             Alembic: env.py e revisões versionadas (0001–0007)
│   └── tests/                  pytest (ver Testes)
├── frontend/                   React + TypeScript + Tailwind (Vite)
│   └── src/
│       ├── api.ts              Cliente HTTP, token, downloads, idempotência
│       ├── useTelao.ts         Assinatura SSE e sincronismo de relógio
│       ├── useCanalPrivado.ts  SSE privado e autenticado da área pessoal
│       ├── carrossel.ts        Slide atual do carrossel pelo relógio do servidor
│       ├── som.ts              Áudio gerado via Web Audio API
│       ├── componentes/        UI, captura de foto, controle do carrossel, confetes
│       └── paginas/            Login, Autocadastro, Minha área, Eventos, Painel, Telão
└── scripts/                    instalar, dev, evento, demo, testar
```

### Stack

| Camada | Escolha | Motivo |
| --- | --- | --- |
| Backend | FastAPI + SQLAlchemy 2 | Conforme especificado. |
| Banco | **SQLite** (padrão) | Zero instalação; não havia PostgreSQL nem Docker na máquina. O código é portável — trocar `DATABASE_URL` basta. |
| Sincronismo | **SSE** | Unidirecional servidor→cliente, que é exatamente o caso de uso; reconecta sozinho, atravessa proxies melhor que WebSocket. |
| Senhas | PBKDF2-SHA256 (stdlib) | Evita dependência nativa (bcrypt/argon2) que costuma falhar ao compilar no Windows. |
| Confetes e som | Canvas e Web Audio próprios | Sem CDN nem arquivos de mídia: funciona offline no dia do evento. |

### Fluxo de um sorteio

```
Organizador               Backend                          Telão
    │                        │                               │
    ├─ POST /sorteio ───────►│                               │
    │  (chave idempotência)  ├─ BEGIN IMMEDIATE              │
    │                        ├─ chave já usada? → devolve    │
    │                        ├─ unidade disponível?          │
    │                        ├─ calcula elegíveis            │
    │                        ├─ secrets.randbelow(n)         │
    │                        ├─ GRAVA resultado + snapshot   │
    │                        ├─ GRAVA notificação do ganhador│
    │                        │  (visível em revelar_em)      │
    │                        ├─ telão = "sorteando",         │
    │                        │  revelar_em = agora+6s        │
    │                        ├─ COMMIT ────────────────┐     │
    │◄── resultado ──────────┤                         ├─SSE►│ animação
    │   (oculto na tela)     │                               │
    │                        │◄── GET /estado (fim) ─────────┤
    │                        ├─ estado = "resultado" ──SSE──►│ 🎉 ganhador
    │                        ├─ aviso privado ──SSE──► celular do ganhador
```

O vencedor é **escolhido e persistido antes** de qualquer comunicação ao telão. A animação
apenas apresenta um resultado que já está gravado. O estado "sorteando" do telão é gravado
**na mesma transação** do resultado: é ele que impede um segundo sorteio durante a revelação,
e gravá-lo depois do commit (como era até a Fase 4) deixava uma janela para dois sorteios
simultâneos passarem.

---

## Garantias de confiabilidade

| Risco | Como é tratado | Teste |
| --- | --- | --- |
| Clique duplo | Chave de idempotência por tentativa, com índice único no banco. A 2ª chamada devolve o mesmo resultado, marcado como `reaproveitado`. | `test_clique_duplicado_nao_cria_dois_resultados` |
| Sorteios simultâneos | `BEGIN IMMEDIATE` serializa as transações; índice único parcial impede dois resultados válidos para a mesma unidade. | `test_sorteios_concorrentes_na_mesma_unidade`, `test_transacao_imediata_serializa_sorteios_no_banco` |
| Dois ganhadores iguais em paralelo | A regra de elegibilidade é avaliada dentro da transação exclusiva. | `test_duas_unidades_em_paralelo_geram_ganhadores_distintos` |
| F5 / reconexão | O estado do telão é persistido. A transição "sorteando → resultado" é **preguiçosa**: qualquer leitura após `revelar_em` promove o estado. Não existe timer no servidor. | `test_reconexao_recupera_resultado_sem_novo_sorteio` |
| Sem elegíveis | Bloqueado na conferência e novamente no backend (HTTP 409). | `test_bloqueia_sem_participantes_elegiveis` |
| Ganhador repetido | Quem já tem resultado válido sai da lista quando a regra proíbe repetição. | `test_ganhador_nao_repete_quando_regra_proibe` |
| Anulação e resorteio | Resultado anterior preservado como `anulado` com motivo; nova rodada vinculada por `draw_anterior_id`; elegíveis recalculados. | `test_anulacao_exige_justificativa_e_permite_novo_sorteio` |
| Anular prêmio entregue | Exige confirmação explícita de estorno (HTTP 409 sem ela). | `test_anular_entregue_exige_confirmacao_de_estorno` |
| Vazamento de dados no telão | O telão recebe apenas nome, setor, foto e número do sorteio do ganhador, e no máximo 60 nomes para a animação. Nunca matrícula nem a lista completa. | `test_telao_nunca_recebe_matricula_nem_lista_completa` |
| Favorecimento | Não existe rota para editar o vencedor; a seleção usa `secrets.randbelow` (CSPRNG, sem viés de módulo). | `test_nao_existe_rota_para_editar_ganhador`, `test_distribuicao_uniforme_do_sorteio` |
| Conferência posterior | Cada rodada grava a lista de IDs elegíveis e o índice sorteado. | `test_snapshot_de_elegiveis_e_gravado` |
| Dois sorteios durante a mesma revelação | O estado "sorteando" é gravado na transação do sorteio. | `test_dois_operadores_sorteando_no_mesmo_bloco_ao_mesmo_tempo` (repetido 15×) |
| Notificação duplicada | Índice único (sorteio, tipo) e criação na mesma transação do resultado. | `test_clique_duplicado_nao_duplica_a_notificacao` |
| Notificação vazando | Canal privado por conta, com token; canal público só transmite o estado do telão. | `test_aviso_vai_so_pelo_canal_privado_e_na_hora_da_revelacao`, `test_notificacoes_sao_privadas` |
| Carrossel fora de sincronia | Estado oficial no servidor; clientes calculam pelo relógio do servidor. | `test_reconexao_recupera_o_mesmo_slide` |
| Carrossel interrompido por sorteio | Sorteio recusado enquanto a apresentação está no telão. | `test_proximo_bloco_nao_sorteia_com_o_carrossel_na_tela` |
| Dois celulares, mesma matrícula | Transação exclusiva; o segundo é recusado. | `test_dois_aparelhos_com_a_mesma_matricula_so_um_conclui` |

### Segurança

- Painel, cadastros, sorteios, anulações e exportações exigem autenticação (JWT Bearer).
- O telão usa um **token próprio**, somente leitura, sem acesso a rotas administrativas.
  O token pode ser regerado a qualquer momento na aba Configuração.
- Uploads de imagem são abertos e reescritos pelo Pillow — a extensão e o `Content-Type`
  não são considerados confiáveis. Metadados são descartados e o tamanho é limitado.
- Planilhas têm o tamanho limitado e passam por prévia validada antes de qualquer gravação.
- Registro de auditoria para sorteios, anulações, entregas, presença, importações e
  exportações, com usuário e horário.

---

## O que foi implementado

**Evento** — nome, empresa, logo, 4 cores configuráveis com prévia, mensagens de boas-vindas
e encerramento, texto de regras, som, duração da animação, modo de animações reduzidas,
fuso horário e link do telão (regerável). Cada evento mantém seus próprios participantes,
prêmios e resultados.

**Participantes** — cadastro manual com nome, matrícula, setor e foto opcional; importação
CSV/XLSX com modelo para download, prévia com erros e duplicadas apontados linha a linha;
**zeros à esquerda preservados**; detecção de matrícula duplicada no evento; busca por nome
ou matrícula; filtros por setor, presença e participação; confirmação de presença individual;
inclusão/exclusão da participação com motivo obrigatório registrado.

**Prêmios** — nome, imagem, descrição, quantidade e ordem de apresentação com reordenação.
Cada unidade é sorteada numa rodada própria, com situação (disponível/sorteado/entregue) e
ganhador identificado. Sem imagem, o telão exibe um espaço visual adequado.

**Regras** — vitória única ou múltipla; exigência de presença; tratamento do ganhador ausente
(bloquear, resortear ou manter pendente); se o ausente volta a concorrer. Resumo legível para
conferir com a plateia e confirmação explícita antes do primeiro sorteio. Alterações
posteriores ficam no histórico, marcadas como "após o 1º sorteio".

**Sorteio** — seleção da unidade, conferência de elegíveis, bloqueios explicados em texto,
botão de início, animação no telão, resultado, confirmação de entrega ou pendência.

**Autocadastro, notificações e carrossel** — ver as seções próprias em
[Configuração](#configuração).

**Telão** — seis estados (aguardando, prêmio, sorteando, resultado, encerramento e carrossel
dos ganhadores), animação
de nomes com desaceleração, confetes, som opcional (rufar de tambores denso e contínuo, com leve
subida, durante a animação; bumbo, prato e fanfarra na revelação; tudo sintetizado, sem arquivos de
áudio; ouça em `docs/som-rufar-tambores.wav`), modo tela cheia, opção de reduzir
animações e indicador discreto de conexão. Visual azul-escuro com detalhes dourados e
tipografia grande.

**Histórico e relatório** — rodada, unidade, ganhador, data/hora, organizador responsável,
situação da entrega, anulações com motivo e vínculo entre resorteios; filtros por válidos,
pendentes, entregues e anulados; exportação CSV e XLSX; resumo com participantes, presentes,
elegíveis, unidades sorteadas, disponíveis e entregues; registro de auditoria.

---

## Testes

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\testar.ps1
```

**299 testes, todos passando.** Cobrem os cenários críticos listados em
[Garantias de confiabilidade](#garantias-de-confiabilidade), além de importação de planilhas
(zeros à esquerda, erros, duplicadas, coluna faltante), filtros, exportações, resumo do
evento, histórico de regras e auditoria.

O banco de cada teste é montado **pelas migrações**, não por `create_all` — os testes rodam
sobre o mesmo schema que o app usa. Arquivos da Fase 1:

- `test_migracoes.py` — banco novo igual aos modelos; adoção de banco v1 com todos os dados
  preservados; backup; idempotência; ida e volta; recusa de schemas desconhecidos;
- `test_integridade_fase1.py` — unicidade de pulseira e de vínculo conta↔participante por
  evento, papéis, blocos, notificações sem duplicata, bloco gravado no sorteio;
- `test_permissoes.py` — mapa de permissões e varredura de todas as rotas.

Fase 2 — `test_blocos.py` (47 testes): distribuições de 25, 26, 100 e 107 unidades (inclusive
107 espalhadas em 4 tipos de prêmio), capacidade personalizada, redistribuição sem tocar em
bloco iniciado, movimentação manual e atomicidade, ciclo de vida, sorteio restrito ao bloco
em andamento, concorrência (dois operadores iniciando blocos ou sorteando ao mesmo tempo;
pausa disputando com sorteio), anulação dentro do bloco e em bloco finalizado,
remanescentes, premiados sem dados pessoais e reconexão. As proteções principais foram
conferidas por **mutação**: desligando cada uma, os testes correspondentes falham.

Fase 3 — `test_historico.py` (59 testes): nome parcial, sem acento e sem caixa; várias
palavras; matrícula com zeros à esquerda e parcial; pulseira; nome do prêmio; `%` e `_`
tratados como texto; cada filtro isolado e combinado; datas no fuso do evento; ordenação;
paginação sem repetir nem pular linhas; parâmetros inválidos; anulação e resorteio
preservados na busca e no detalhe; exportações filtradas (CSV e XLSX, com zeros e pulseira),
com fuso por evento e registro na auditoria; permissões; telão sem dados pessoais. Também
verificados por mutação: sem o escape do `LIKE`, sem a normalização, com datas em UTC ou
sem desempate na ordenação, os testes correspondentes falham.

Fase 4 — `test_acesso.py`: a **matriz completa** (cada rota × cada perfil: quem deve passar
passa, quem não deve recebe 403, nada responde 500, e toda rota do app precisa estar na
matriz); sem token tudo responde 401; login informa perfil e permissões; último acesso e
auditoria; sessão derrubada ao desativar, mudar perfil, redefinir senha ou encerrar sessões;
tokens anteriores à fase continuam válidos; tokens expirados ou adulterados são recusados;
bloqueio por conta e por IP; mesma resposta para conta inexistente, senha errada e conta
inativa; senha temporária obrigatoriamente trocada; regras do gerenciamento de usuários;
operador sem acesso a regras, anulação e entrega; organizador conferindo pulseira; credenciamento
marcando presença e trocando pulseira com motivo; colaborador vendo só a própria área.
Por mutação: liberar anulação ao operador, liberar sorteio à recepção, ignorar a versão da
sessão, desligar o bloqueio de login, desligar o limite por IP ou dispensar a troca de senha
temporária fazem os testes correspondentes falharem.

Recepção e perfis (migração 0007):

- `test_recepcao.py` (10): número no telão sem matrícula nem pulseira; faixa de números;
  número aleatório e único em importação e cadastro manual (71 pessoas), único por evento
  mas repetível em outro, também em evento criado junto com os participantes; check-in sem
  login mostra os dados antes de confirmar, audita com IP, não duplica e não alcança outro
  evento; consulta sem acento e por matrícula; lista de eventos pública; prêmio só aparece
  depois da revelação no telão.
- `test_migracoes.py`: a 0007 converte Recepção → Organizador e Check-in → Recepção (sessões
  encerradas), numera os participantes existentes sem repetir, o CHECK novo recusa papéis
  antigos, e o downgrade devolve os papéis.

Fases 5 a 8:

- `test_autocadastro.py` (30): conferência de nome e sobrenome (acentos, caixa, nome do meio
  opcional, sobrenome obrigatório); só a matrícula não basta e o erro não revela o que
  falhou; matrícula fora da lista; evento fechado; limites por IP e por matrícula; fluxo
  completo (conta, foto, pulseira, presença, login pela matrícula); regra de presença; só o
  primeiro cadastro vale; pulseira duplicada, já entregue e obrigatória; senha validada no
  backend; foto JPEG da câmera, PNG da galeria, arquivo falso, tamanho e foto já existente;
  check-in libera novo cadastro (sessão antiga cai, motivo na auditoria); conta desativada;
  login de outra pessoa preservado; mesma pessoa em dois eventos; dois celulares ao mesmo
  tempo; matrícula duplicada; limpeza da demonstração.
- `test_notificacoes.py` (11): notificação persistente ligada a evento, participante,
  prêmio e sorteio, visível só após a revelação; criada antes da conta e vista depois;
  clique duplicado; privacidade entre colaboradores; marcar lida e todas; anulação (inclusive
  durante a animação); entrega; aviso só no canal privado e no instante da revelação;
  gerador do canal privado encerrando sessão inválida; token, conta e perfil conferidos.
- `test_carrossel.py` (13): carrossel com **1 e 25 ganhadores**, sem dados pessoais;
  bloco sem ganhadores; fim de bloco durante a animação; **mínimo de 5 s** (API, banco e
  cálculo); avanço automático e slide-resumo; **pausa e retomada**; anterior, próximo, repetir
  e encerrar; não altera resultados; próximo bloco bloqueado com o carrossel na tela;
  anulação some do carrossel; **reconexão** recuperando o mesmo slide; transmissão por SSE.
- `test_fluxo_completo.py`: os 16 passos do evento, cada um com a conta do perfil que o
  executa (admin, colaboradores, operador, recepção), terminando no histórico e nas
  exportações CSV/XLSX.

Além dos testes, uma **simulação ponta a ponta** sobre um banco de demonstração isolado
(servidor real na porta 8010) escutou de verdade os canais SSE: 12 autocadastros, 9
sorteios em 2 blocos com clique duplo, carrossel com pausa e reconexão, anulação, entregas
com conferência de pulseira e exportações — 0 falhas. O aviso ao ganhador chegou 2,0 s após
o sorteio, exatamente na revelação.

Verificação manual no navegador, com painel e telão abertos lado a lado:

- sincronização painel → telão na seleção de prêmio;
- duplo clique em "Iniciar sorteio" gerando **um único** resultado;
- animação e revelação do ganhador;
- F5 no telão durante o resultado, recuperando o mesmo ganhador;
- anulação justificada e novo sorteio, com elegíveis recalculados (47 → 45);
- exportação CSV com o resultado anulado preservado e o novo vinculado ao anterior;
- tela de encerramento com a galeria apenas dos resultados válidos;
- prêmio sem imagem exibindo o espaço visual de fallback;
- layout em formato de projeção (1366×768) e em largura de celular.

---

## Limitações conhecidas

- **Um único processo.** O `BEGIN IMMEDIATE` do SQLite serializa escritas dentro do processo
  e entre processos na mesma máquina, mas não há suporte a múltiplos servidores. Para isso,
  migre para PostgreSQL (`DATABASE_URL`) — o código já está preparado.
- **SSE é unidirecional.** O telão só recebe; todo comando parte do painel autenticado. Foi
  uma escolha deliberada, mas significa que o telão não reporta nada de volta.
- **Sem "esqueci minha senha" por e-mail.** A recuperação é feita pelo admin, em Usuários →
  Redefinir senha, que gera uma senha temporária.
- **Limite de login por IP fica em memória** e zera ao reiniciar o servidor. O bloqueio por
  conta fica no banco e não zera. Em rede com proxy, todos chegam com o mesmo IP; nesse caso,
  aumente `LOGIN_MAX_FALHAS_IP`.
- **Identificação do portal não é autenticação forte**: quem conhece matrícula, nascimento e
  início do CPF de um colega pode fazer o primeiro cadastro no lugar dele. Mitigação: só vale o
  primeiro cadastro, limites de tentativa e "Liberar novo cadastro" no Credenciamento. A senha
  padrão (5 dígitos do CPF) é fraca por decisão do cliente; quem quiser pode trocá-la em Meu Perfil.
- **Participantes sem CPF e nascimento importados** não conseguem usar o QR Code (o painel
  mostra quantos são). Reimporte a planilha marcando "Completar CPF e nascimento".
- **Push no celular não testado em aparelho real**: o envio foi testado no servidor com um
  serviço de push simulado; o Chrome sem janela usado nos testes não tem serviço de push. Em
  HTTP pela rede local, o navegador não permite push nem a câmera ao vivo.
- **Câmera ao vivo exige HTTPS.** O modo evento já sobe em HTTPS com certificado da rede local
  (aviso de segurança na primeira vez em cada aparelho). Com `-SemHttps`, pelo IP da rede o
  navegador não libera a câmera dentro da página; o scanner cai para "Fotografar QR Code" e a
  foto do perfil para "Tirar foto com o celular", que abrem a câmera nativa.
- **Fotos e imagens** ficam em `/uploads/` com nomes aleatórios, acessíveis a quem tiver o
  endereço (o telão precisa delas sem login).
- **O aviso em tempo real é agendado em memória.** Se o servidor reiniciar entre o sorteio e
  a revelação, o celular não recebe o empurrão, mas vê a notificação na próxima atualização
  (ela está no banco).
- **Sorteios anteriores à Fase 6** não geraram notificação; os prêmios aparecem normalmente
  em "Meus prêmios".
- **A animação do telão usa até 60 nomes**, sorteados entre os elegíveis. Com um público
  muito maior, nem todos aparecerão no rolo — o que não afeta o sorteio, feito no backend
  sobre a lista completa.
