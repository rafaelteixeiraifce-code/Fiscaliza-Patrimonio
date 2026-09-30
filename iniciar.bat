@echo off
title Fiscaliza - Nucleo de Patrimonio
cd /d "%~dp0"
echo Pasta do app: %CD%
echo.

set PY=
where py >nul 2>nul && set PY=py
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale o Python 3.10+ marcando "Add python.exe to PATH" ou rode pelo VS Code.
  goto fim
)
%PY% --version
if errorlevel 1 (
  echo [ERRO] O comando "%PY%" existe mas nao executa. Pode ser o atalho da Microsoft Store.
  goto fim
)

if not exist .venv (
  echo Criando ambiente virtual...
  %PY% -m venv .venv || goto erro
  echo Instalando dependencias ^(pode demorar alguns minutos^)...
  .venv\Scripts\python -m pip install -r requirements.txt || goto erro
)

echo.
echo Abrindo o sistema em http://localhost:8501  (feche esta janela para encerrar)
.venv\Scripts\python -m streamlit run app.py
goto fim

:erro
echo.
echo [ERRO] Algo falhou acima. Tire um print desta janela.

:fim
echo.
pause
