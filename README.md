# Fiscaliza — Sistema de Fiscalização de Contratos (Núcleo de Patrimônio/ALECE)

MVP para o contrato do PE 001/2026 (manutenção, higienização e reestofamento de mobiliário — BMS).
Python + Streamlit + SQLite. Sem servidor: roda na máquina do fiscal.

## Como rodar (Windows)
1. Instale o Python 3.10+ (marcar "Add to PATH").
2. Dê dois cliques em `iniciar.bat`. Na primeira vez ele cria o ambiente e instala as dependências.
3. O navegador abre em `http://localhost:8501`.

No VS Code: `pip install -r requirements.txt` e depois `streamlit run app.py`.

## Onde ficam os dados
Padrão: pasta `dados/` ao lado do app (banco `fiscaliza.db` + `evidencias/OS-AAAA-NNN/`).
Para gravar as evidências na pasta de rede do Patrimônio, defina antes de rodar:

    set FISCALIZA_EVID=\\servidor\patrimonio\Fiscalizacao\PE-001-2026\evidencias

Recomendação: deixe o **banco** no disco local (SQLite não gosta de pasta de rede com vários
usuários gravando) e as **evidências** na rede. Faça cópia diária do `fiscaliza.db` para a rede.

## O que o MVP faz
- **OS**: emissão, bens (tombo/TAG), linha do tempo de eventos (avaliação, retirada 1ª via,
  aviso de atraso, devolução 2ª via, aceite/rejeição, reincidência em garantia).
- **Prazos calculados**, nunca digitados: 2 dias úteis (avaliação) / 24 h (urgente),
  1 dia útil (retirada), 10 dias úteis (devolução), 90 dias de garantia. Tudo configurável
  em *Contrato e prazos*, com feriados.
- **Evidências** com hash SHA-256 (prova de integridade) e organização automática por OS.
- **Ocorrências** com status e **minuta de notificação** (.docx).
- **Dossiê da OS** (.docx) no padrão institucional verde — pronto para instruir processo.
- **Painel**: OS atrasadas, bens fora da Casa, saldo por item (R$ 147k / 25k / 45k).
- **Trilha de auditoria** de todas as ações.

## Próximos passos
- Medição mensal (consolidar OS atestadas → termo de recebimento provisório).
- Checklist mensal de regularidade (SICAF / 5 certidões).
- Importar tombos do SIGA/base patrimonial para validar o que sai e volta.
- Login com senha (hash) e perfis fiscal/gestor.
