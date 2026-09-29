@echo off
REM Executa o preenchimento e grava. Usado pelo Agendador de Tarefas do Windows.
cd /d "%~dp0"
if not exist logs mkdir logs
python preencher_interacao.py --gravar --canal msedge >> logs\execucoes.log 2>&1
