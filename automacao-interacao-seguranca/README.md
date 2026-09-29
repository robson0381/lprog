# Automação – Registro de Interação de Segurança (SAP Fiori)

Preenche periodicamente o app **Registro de Interação** (`ZGEEHS_REG_ABRD`) com
**Descrição**, **Ação Imediata** e **"A interação foi feita baseada em algum dos
Grandes Riscos?"** a partir de modelos definidos em `modelos.yaml`, e clica em **Gravar**.

O app só preenche sozinho o **Responsável Principal** e o **Método Coach** ("Não").
Os demais campos obrigatórios (Tipo, Data, Unidade, Empresa, Área, Local da Instalação,
Houve Desvio, Evento, Houve Violação, Instante) vêm vazios e precisam estar em
`campos_fixos` (ou no modelo) no `modelos.yaml`; senão o SAP recusa a gravação.

> O SAP fica na rede interna da ArcelorMittal, então o script deve rodar **no seu
> computador de trabalho** (Windows), conectado à rede/VPN.

## Como funciona

- Abre o navegador com um **perfil próprio** (`perfil_navegador/`), que guarda a
  sessão do login SSO entre execuções.
- Localiza cada campo pelo **texto do rótulo** e define o valor pela API do SAPUI5
  (o mesmo que o app faz quando você digita/seleciona), disparando os eventos de
  alteração para o app registrar o valor.
- Escolhe o modelo em **rodízio** (um diferente a cada execução, guardado em
  `estado.json`) ou **aleatório** (`selecao: aleatorio`).
- Se algum valor não existir no combo, **não grava** e lista as opções válidas.
- Salva prints em `logs/` (preenchido e após gravar) e o histórico em `logs/execucoes.log`.

## Instalação (uma vez)

```bat
cd automacao-interacao-seguranca
pip install -r requirements.txt
python -m playwright install chromium
```

Se preferir usar o Edge/Chrome já instalado, acrescente `--canal msedge` (ou `--canal chrome`)
nos comandos; nesse caso o `playwright install` não é necessário.

## Primeiro uso

1. **Login** (abre o navegador; faça o login normalmente até o formulário aparecer):
   ```bat
   python preencher_interacao.py --login --canal msedge
   ```
2. **Veja as opções dos combos** (principalmente a lista de *Grandes Riscos*):
   ```bat
   python preencher_interacao.py --listar-opcoes --canal msedge
   ```
3. **Edite `modelos.yaml`** com seus textos, usando o texto exato das opções listadas.
4. **Teste sem gravar** (preenche e deixa a janela aberta para você conferir):
   ```bat
   python preencher_interacao.py --canal msedge
   python preencher_interacao.py --canal msedge --modelo energias-perigosas
   ```
5. **Gravar de verdade**:
   ```bat
   python preencher_interacao.py --gravar --canal msedge
   ```

### Opções

| Opção | Descrição |
|---|---|
| `--gravar` | Clica em "Gravar" (sem ela, só preenche para conferência) |
| `--modelo NOME` | Usa um modelo específico em vez do rodízio |
| `--data dd/mm/aaaa` | Altera a data da interação (padrão: mantém a sugerida pelo app) |
| `--listar-opcoes` | Lista campos e opções dos combos |
| `--login` | Abre o navegador para login manual e salva a sessão |
| `--canal msedge\|chrome` | Usa o navegador instalado |
| `--headless` | Executa sem janela (pode não funcionar com o SSO corporativo) |
| `--config arquivo.yaml` | Usa outro arquivo de modelos |

## Agendamento periódico (Windows)

O `executar.bat` roda `--gravar` e grava o log em `logs\execucoes.log`.
Exemplo: toda segunda, quarta e sexta às 08:30 (rode no Prompt de Comando, na pasta do projeto):

```bat
schtasks /Create /TN "Registro Interacao SAP" /TR "\"%CD%\executar.bat\"" /SC WEEKLY /D MON,WED,FRI /ST 08:30
```

Outros exemplos: diário → `/SC DAILY /ST 08:30`; semanal → `/SC WEEKLY /D MON /ST 08:30`.
Para remover: `schtasks /Delete /TN "Registro Interacao SAP" /F`.

A tarefa precisa rodar **com o usuário logado** (padrão do `schtasks` acima), pois abre o navegador.

Se a sessão SSO expirar, a execução falha com a mensagem
"O formulário não carregou..." e um print em `logs/`; basta rodar `--login` de novo.

## Observações

- Confira as regras internas de SSMA sobre o registro de interações: a automação
  apenas agiliza o preenchimento; as interações registradas devem corresponder a
  interações realmente realizadas.
- Se o app mudar o texto de algum rótulo, ajuste a chave correspondente em `modelos.yaml`.
