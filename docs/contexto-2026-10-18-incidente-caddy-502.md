# Contexto · LuasCondo fora do ar (502 no Caddy) — 2026-10-18

> Documento de handoff para retomar o contexto do incidente e do deploy do LuasCondo na VM.
> Ambiente: Oracle Cloud, VM `vcn-20260908-1519` (Ubuntu, E2.1.Micro ~1 GB RAM), IP `147.15.76.139`.

## Panorama da VM (3 stacks convivendo)

| Stack | Pasta | Containers | Domínio |
|---|---|---|---|
| ApitaCerto (produção, NÃO TOCAR) | `/opt/apitacerto` | `apitacerto-caddy-1` (Caddy, ponto de entrada de TODOS os sites), `apitacerto-app-1`, `apitacerto-postgres-1`, etc. | `147-15-76-139.sslip.io` |
| Luas Social (produção, NÃO TOCAR) | `/opt/luas` | `luas_api`, `luas_worker` (imagem `luas-social:latest`) | `luas.147-15-76-139.sslip.io` |
| LuasCondo | `/opt/luas-condo` | `luas_condo_frontend` (Vite, porta 5173), `luas_condo_backend` (8000), `luas_condo_db` (postgres), grafana, prometheus, mock_bitrix | `condo.147-15-76-139.sslip.io` |

Roteamento (em `/opt/caddy-sites/*.caddy`, importado pelo Caddyfile do ApitaCerto):
- `luas.…` → `reverse_proxy luas_api:8010`
- `condo.…` → `/api*` e `/docs*`, `/openapi.json` → `luas_condo_backend:8000`; resto → `luas_condo_frontend:5173`

## Sintoma

`https://condo.147-15-76-139.sslip.io/` e `/api/health` devolviam **HTTP 502** (`server: Caddy`), tanto na raiz quanto na API. O Luas funcionava (200).

## Diagnóstico (o que encontramos)

1. **Definição de site duplicada** — o bloco `condo.147-15-76-139.sslip.io` existia em DOIS lugares:
   - `/opt/caddy-sites/condo.caddy` (arquivo de site correto, upstream na porta **5173**)
   - `/opt/apitacerto/Caddyfile` (bloco inline antigo, upstream na porta **80** — errado)
   - `caddy validate` falhava com `ambiguous site definition: condo.147-15-76-139.sslip.io`, então **nenhum reload era aplicado** — o Caddy continuava rodando a config antiga (porta 80) → `dial tcp 172.19.0.7:80: connection refused` → 502.
2. **Edição do Caddyfile não chegava ao container** — a montagem é **bind de arquivo único** (`/opt/apitacerto/Caddyfile -> /etc/caddy/Caddyfile`):
   - `sed -i` corrigiu o arquivo no HOST (cria inode novo), mas o container continuou preso ao **inode antigo** (com o bloco do condo) → `docker cp` falhou com `RemoveAll: device or resource busy` (não se pode des-linkar bind de arquivo único) e `docker exec sh -c 'cat > /etc/caddy/Caddyfile'` falhou com **Read-only file system** (montagem `:ro`).
3. **Carga na VM agravava tudo** — `snapd` + `oracle-cloud-agent` consumiam ~88%+32%+16% de CPU numa VM de 1 vCPU com 82% de *steal time*; load average 23–32. 604 processos zumbis (sintoma, não causa). Disco OK (30%).

## Correção aplicada (2026-10-18, zero downtime)

1. Remover o bloco duplicado do host: `sudo sed -i '/condo\.147-15-76-139\.sslip\.io/,$d' /opt/apitacerto/Caddyfile` (o host ficou limpo, mas o container continuou vendo o inode antigo — ver item 2 do diagnóstico).
2. **Plano B que funcionou**: copiar o Caddyfile limpo do host para DENTRO da montagem de DIRETÓRIO (que reflete arquivos novos) com nome `.txt` para não entrar no `import /etc/caddy/sites/*.caddy`:
   ```bash
   sudo cp /opt/apitacerto/Caddyfile /opt/caddy-sites/clean-main.txt
   docker exec apitacerto-caddy-1 caddy validate --config /etc/caddy/sites/clean-main.txt --adapter caddyfile
   docker exec apitacerto-caddy-1 caddy reload   --config /etc/caddy/sites/clean-main.txt --adapter caddyfile
   ```
   - `--adapter caddyfile` é obrigatório para arquivos com nome arbitrário (o Caddy só auto-adapta quando o arquivo se chama `Caddyfile`).
   - Reload é graceful — o ApitaCerto não saiu do ar em nenhum momento.
3. Removido o container órfão `silly_banach` (cópia manual do luas_api, na rede errada — `bridge` —, inalcançável e inútil).

## Resultado

- `condo /api/health`: **200** · `condo /`: **200** · `luas health`: **200**
- `silly_banach`: removido
- Load da VM: 32 → ~2 (fora deste incidente: `snapd`/`oracle-cloud-agent` foram parados e `disable`-ados — reversível com `systemctl enable --now`)

## Ressalvas e armadilhas para o futuro

1. **Regra de ouro do Caddy nesta VM**: um site = UM bloco, só em `/opt/caddy-sites/{dominio}.caddy`. Nunca definir sites inline no `/opt/apitacerto/Caddyfile` (além de duplicar, é o arquivo montado `:ro` que engessa edições).
2. **Se o Caddy reiniciar**, ele lê `/etc/caddy/Caddyfile` pelo host path → aí sim re-bind no inode novo (limpo, sem o bloco do condo) → boota normal. O `clean-main.txt` em `/opt/caddy-sites/` é só a muleta do reload atual; pode ser removido quando um restart do Caddy for feito em janela de manutenção (breve downtime de TODOS os sites — combinar antes, o apitacerto é produção).
3. **Nunca usar `sed -i`/`docker cp` no `/opt/apitacerto/Caddyfile` esperando efeito no container**: arquivo único bind-mounted + `:ro` = nem editável por dentro, nem substituível por fora. O caminho é sempre: editar no host → copiar para `/opt/caddy-sites/*.txt` → `caddy reload --config … --adapter caddyfile`.
4. **Nomes de container como upstream exigem rede compartilhada** — o Caddy resolve `luas_api`/`luas_condo_*` porque os stacks compartilham a rede docker `web` (rede externa declarada nos composes). Ao subir um stack novo, conectá-lo à mesma rede.
5. **Porta real ≠ porta publicada**: o Caddy fala com a porta INTERNA do container (5173 do Vite), não a publicada no host (`0.0.0.0:5173->5173`). Os 502 antigos vieram justamente do bloco antigo apontando para `:80`.

## Comandos de diagnóstico que funcionaram

```bash
docker logs apitacerto-caddy-1 --tail 40                  # dial tcp …: connection refused
docker ps -a --format "table {{.Names}}\t{{.Status}}"
docker inspect apitacerto-caddy-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker exec apitacerto-caddy-1 wget -qO- --timeout=5 http://luas_api:8010/api/v1/health
curl -sS -o /dev/null -w "%{http_code}\n" https://condo.147-15-76-139.sslip.io/api/health
```

## Estado do LuasCondo em si (fora do incidente de rede)

- Stack de containers saudável: frontend (Vite dev), backend, postgres (healthy), grafana, prometheus, mock_bitrix.
- `docker compose restart frontend` chega a demorar ~25s — não interpretar demora como falha; conferir `docker ps` antes.
- **Vite em modo dev no "deploy"** é peso para uma VM de 1 vCPU — avaliar trocar para build de produção quando o condo for para uso real.

## Resolução permanente (2026-10-18, aplicada)

Fechamento do incidente, com aprovação do dono dos projetos:

1. **Restart do `apitacerto-caddy-1` executado** (janela combinada; ~segundos de downtime nos 4 sites). Pré-flight `caddy validate` da config de boot passou antes do restart. Com isso o inode antigo foi descartado: `caddy validate --config /etc/caddy/Caddyfile` dentro do container agora passa limpa, sem ambiguidade. A muleta `clean-main.txt` não é mais necessária.
2. **`/opt/caddy-sites/condo.caddy` sincronizado com o repo** (commit `d8e1dc5`, com `lb_try_duration`/`dial_timeout` que faltavam na VM; backup `condo.caddy.bak-20261018`).
3. **Portas do condo saíram de `0.0.0.0`**: `docker-compose.yml` passou a bindar em loopback (127.0.0.1) com portas parametrizadas por `.env` (`*_HOST_IP`/`*_HOST_PORT`, ver `.env.example`). Acesso web via Caddy não muda; acesso externo direto por IP:porta já era bloqueado pelo Security List da Oracle; SSH tunnel continua funcionando.
4. **`docker-compose.prod.yml` ganhou a rede `web` externa** no backend/frontend — um futuro deploy de produção não vai mais reproducir o 502 por falta de roteamento, e as portas publicadas também são loopback. Atenção: em prod o frontend é nginx na porta interna 80 (dev é Vite 5173) — `deploy/condo.caddy` precisa apontar para a porta correta no dia da troca.
5. **Runbook novo**: [vm-port-allocation-runbook.md](vm-port-allocation-runbook.md) — mapa de portas das 4 stacks (apitacerto, luas, soutes, condo) e os procedimentos de reload/restart do Caddy. As "ressalvas" acima viraram regra operacional nele.
6. **`apitacerto-app-1` unhealthy (NÃO corrigido — prod, aguardando janela)**: a app serve 200 normalmente; o healthcheck falha porque o runtime OCI do container não consegue executar NENHUM processo novo (`docker exec` trivial falha com `procReady not received`) — estado de runc/containerd travado, provável sequelas da sobrecarga de ontem (load 23-32). Reparo quando autorizado: `docker restart apitacerto-app-1` (segundos) e, se persistir, recriar o container.
