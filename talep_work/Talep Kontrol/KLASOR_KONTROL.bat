@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "DATA="
for /f "usebackq delims=" %%A in ("VERI_KLASORU.txt") do if not defined DATA set "DATA=%%A"
echo.
echo Oncelikli CSV veri klasoru:
echo %DATA%
echo.
if defined DATA if exist "%DATA%\" (
  echo [OK] Dis veri klasoru bulundu.
  echo.
  echo CSV dosyalari - dosya isimleri serbesttir:
  dir /b "%DATA%\*.csv" 2>nul
) else (
  echo [UYARI] Dis veri klasoru bulunamadi.
  echo Paket icindeki csv klasoru kontrol edilir:
  echo %~dp0csv
  echo.
  dir /b "%~dp0csv\*.csv" 2>nul
)
echo.
echo Kaynak eslesmesini ayrintili gormek icin uygulama acikken TEST_ET.bat calistirin.
pause
