@echo off
chcp 65001 >nul
title pdf2epub - Interface grafica
setlocal

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Erro: Python nao encontrado. Instale Python 3 em https://python.org
    pause
    exit /b 1
  )
  set PY=py -3
) else (
  set PY=python
)

%PY% "%~dp0pdf2epub_gui.py" %*
if errorlevel 1 (
  echo.
  echo A GUI terminou com erro.
  pause
)
endlocal
