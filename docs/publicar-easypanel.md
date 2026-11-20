# Publicar no Easypanel (VPS Hostinger)

O sistema vai como **um contêiner Docker** (frontend e backend juntos), com HTTPS pelo
próprio Easypanel e todos os dados numa pasta do servidor montada em `/data`.

> **Regras que não podem ser quebradas**
> 1. **Uma única réplica.** O tempo real (telão, carrossel, notificações) e o limite de
>    tentativas de login ficam na memória do processo. Duas réplicas = telão sem atualizar.
>    Deixe *zero downtime* desligado: ele sobe o contêiner novo antes de derrubar o antigo.
> 2. **`/data` sempre montado numa pasta do servidor.** Sem isso, cada deploy apaga o banco.
> 3. **Levar a `chave-identificacao.key`.** Sem ela, o autocadastro não reconhece nenhum CPF
>    já importado (seria preciso reimportar a planilha).

Os nomes de botões e abas abaixo podem variar um pouco conforme a versão do Easypanel.

---

## 0. Antes de começar

- VPS da Hostinger com o Easypanel instalado e acesso SSH (`ssh root@IP-DA-VPS`).
- Um domínio ou subdomínio (ex.: `sorteio.mallory.com.br`) com registro **A** apontando para
  o IP da VPS. O certificado HTTPS só é emitido depois que o DNS propagar.
- O código num repositório Git **privado** (GitHub). O `.gitignore` já deixa de fora `.env`,
  banco e imagens; o `.dockerignore` impede que entrem na imagem.

## 1. Pasta dos dados no servidor

```bash
mkdir -p /srv/sorteio/dados /srv/sorteio/backups
chown -R 1000:1000 /srv/sorteio/dados
```

O contêiner roda com o usuário de uid 1000 (sem privilégios); por isso o `chown`.

## 2. Levar os dados desta máquina

1. **Pare o servidor do evento** (o que for feito depois da exportação não vai junto).
2. Exporte:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\exportar-dados.ps1
   ```

   O script mostra onde salvou `sorteio-dados-AAAAMMDD-HHMM.zip` e confere se a chave de
   identificação foi junto. O zip tem nomes, fotos e códigos de identificação: não deixe no
   OneDrive nem mande por e-mail.
3. Envie e descompacte no servidor:

   ```powershell
   scp C:\caminho\sorteio-dados-AAAAMMDD-HHMM.zip root@IP-DA-VPS:/srv/sorteio/
   ```

   ```bash
   apt-get install -y unzip sqlite3
   cd /srv/sorteio && unzip sorteio-dados-*.zip -d dados && chown -R 1000:1000 dados
   sqlite3 dados/sorteio.db "pragma integrity_check;"   # deve responder: ok
   ```

   Depois de conferir, apague o zip do servidor e do computador.

## 3. Criar o serviço no Easypanel

1. **Projeto** novo (ex.: `sorteio`) → **+ Serviço → App** (ex.: `app`).
2. **Origem (Source):** o repositório GitHub, branch principal.
3. **Build:** **Dockerfile**, caminho `Dockerfile` (raiz do repositório).
4. **Ambiente (Environment):**

   | Variável | Valor |
   |---|---|
   | `SECRET_KEY` | aleatória e longa. Gere com `openssl rand -base64 48` |
   | `URL_PUBLICA` | `https://sorteio.mallory.com.br` (vai no QR Code do cadastro e ativa o push) |
   | `ADMIN_USUARIO` | `admin` (o login de administrador que já existe no banco) |
   | `ADMIN_SENHA` | senha forte. Só é usada se essa conta **não** existir no banco |
   | `CORS_ORIGINS` | `https://sorteio.mallory.com.br` |
   | `EVENT_TIMEZONE` | `America/Sao_Paulo` |

   Não defina `DATABASE_URL` nem `DATA_DIR`: a imagem já usa `/data`.
   Trocar a `SECRET_KEY` desconecta quem estiver logado (basta entrar de novo).
5. **Montagens (Mounts):** **Bind mount**, caminho no servidor `/srv/sorteio/dados` →
   caminho no contêiner `/data`.
6. **Domínios (Domains):** o domínio, **HTTPS ligado**, porta do contêiner **8000**.
7. **Deploy:** réplicas **1**; *zero downtime* **desligado**.
8. **Deploy.**

## 4. Conferir

- `https://SEU-DOMINIO/api/saude` → `{"ok":true}`.
- Nos logs do serviço:
  - `[sorteio] banco: /data/sorteio.db (revisao 0011)`;
  - `push no celular: ativo`;
  - **nenhuma** linha `ATENCAO` (se aparecer “SECRET_KEY ainda é a de exemplo”, a variável não foi lida).
- Entre como `admin` com a senha **atual** (a do banco que foi copiado) e troque-a em **Senha**.
- Participantes, prêmios, blocos e fotos aparecem como estavam.
- **Configuração → QR Code do cadastro** mostra o endereço `https://`.
- Faça um autocadastro de teste com um CPF real da planilha: se falhar com “dados não
  conferem” para todo mundo, a `chave-identificacao.key` não foi copiada.
- Abra o telão num computador e o painel em outro: sortear precisa refletir no telão na hora.

## 5. Backup diário

No servidor (`crontab -e`):

```cron
30 3 * * * sqlite3 /srv/sorteio/dados/sorteio.db ".backup '/srv/sorteio/backups/sorteio-$(date +\%F).db'" && find /srv/sorteio/backups -name 'sorteio-*.db' -mtime +30 -delete
```

O `.backup` do SQLite é seguro com o sistema rodando. Guarde também uma cópia da
`chave-identificacao.key` fora do servidor, em local seguro.

## 6. Atualizar o sistema

Envie as mudanças para o repositório e clique em **Deploy** (ou ative o deploy automático).
Se a versão nova tiver migração de banco, o sistema faz um backup sozinho antes, em
`/srv/sorteio/dados/backups/`, e aplica a migração ao iniciar. Nunca apague
`/srv/sorteio/dados` para “resolver” erro de migração.
