@echo off
chcp 65001 >nul
title pdf2epub - Conversor PDF para EPUB
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

if "%~1"=="" (
  echo.
  echo   Conversor de PDF para EPUB
  echo   ==========================
  echo.
  echo   Arraste um ou mais ficheiros PDF para cima deste ficheiro e
  echo   solte-os aqui para os converter.
  echo.
  echo   Tambem pode usar a linha de comandos:
  echo     converter.bat livro.pdf
  echo     converter.bat livro.pdf --titulo "Titulo" --autor "Autor"
  echo.
  pause
  exit /b 0
)

:loop
%PY% "%~dp0pdf2epub.py" "%~1"
if errorlevel 1 (
  echo.
  echo Falha ao converter: "%~1"
) else (
  echo Convertido: "%~1"
)
echo.
shift
if not "%~1"=="" goto loop

pause
endlocal
