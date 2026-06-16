@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
REM Mikanarr 完整环境发行包(Windows)：镜像已打包在 mikanarr-image.tar.gz,无需联网构建/拉取。

where docker >nul 2>&1
if errorlevel 1 ( echo [X] 未找到 docker,请先安装并启动 Docker Desktop。 & pause & exit /b 1 )

if /i "%~1"=="down" ( docker compose -f docker-compose.release.yml down & pause & exit /b 0 )
if /i "%~1"=="logs" ( docker compose -f docker-compose.release.yml logs -f mikanarr & exit /b 0 )

REM 1) 载入完整环境镜像(若本机尚无)
docker image inspect mikanarr:latest >nul 2>&1
if errorlevel 1 (
  echo ^> 正在载入镜像 mikanarr:latest（约 1GB,首次稍慢,无需联网）...
  docker load -i "mikanarr-image.tar.gz"
  if errorlevel 1 ( echo [X] 镜像载入失败,请确认 mikanarr-image.tar.gz 与本脚本同目录。 & pause & exit /b 1 )
)

REM 2) 首次生成 .env
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo [!] 已生成 .env —— 即将打开记事本,请填写 NAS 路径/凭据后保存,再重新运行本脚本。
  notepad ".env"
  pause & exit /b 1
)

REM 3) 启动(用预载镜像,不构建、不连 Docker Hub)
echo ^> 启动 Mikanarr（预载镜像,无需联网构建）...
docker compose -f docker-compose.release.yml up -d
if errorlevel 1 ( echo [X] 启动失败,请检查 .env 与上方错误（多为 NAS 凭据/路径不对）。 & pause & exit /b 1 )
echo.
echo [OK] 已启动。WebUI:  http://localhost:8008
echo      查看日志:        deploy-win.bat logs
echo      停止:            deploy-win.bat down
pause
