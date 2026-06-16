# Mikanarr 部署指南

一键部署到 **Windows Docker Desktop** 或 **Linux**。镜像在目标机现场构建(适配本机架构,无需镜像仓库),首次约 2–4 分钟。

> 前置:目标机装好并启动 **Docker**(Windows 用 Docker Desktop;Linux 用 Docker Engine + compose 插件)。

---

## 一、Windows Docker Desktop(NAS 在远程,走 SMB)

1. 解压发行包,进入目录。
2. 双击 **`deploy.bat`** —— 首次会生成 `.env` 并用记事本打开。
3. 在 `.env` 填:`NAS_SMB_PATH` / `NAS_USER` / `NAS_PASS`(下载根的 SMB 共享与凭据),按需填代理、下载器、导入源。保存。
4. 再次双击 **`deploy.bat`** → 自动构建并启动。
5. 浏览器开 **http://localhost:8008**。

- 看日志:`deploy.bat logs` ;停止:`deploy.bat down`
- 「播放 / 打开目录 / PowerDVD」按钮:在设置页填好「宿主机路径前缀」后,下载并双击运行协议处理器(JScript,无窗口闪),首次点击在浏览器勾「始终允许」即可。仅本机有效。

## 二、Linux + 远程 NAS(同样走 SMB)

```bash
chmod +x deploy.sh
./deploy.sh            # 首次生成 .env
nano .env             # 填 NAS_SMB_PATH / NAS_USER / NAS_PASS 等
./deploy.sh            # 构建并启动
```
要求 Docker 宿主内核支持 CIFS(多数发行版自带 `cifs` 模块)。WebUI:http://<服务器IP>:8008。

## 三、直接跑在 NAS / 本地盘(文件在本机,用绑定挂载)

适合把 Mikanarr 部署在 **NAS 自身的 Docker**(Synology/QNAP 等)或文件就在本地的 Linux。

```bash
./deploy.sh local      # 首次生成 .env
nano .env             # 填 LOCAL_DOWNLOADS_PATH(下载根本地绝对路径),可选 LOCAL_NAS_IMPORT_PATH / LOCAL_BD_OWNED_PATH
./deploy.sh local      # 用本地绑定挂载构建并启动
```
等价命令:`docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build`

---

## 常用操作

| 操作 | Windows | Linux |
|---|---|---|
| 启动/更新 | `deploy.bat` | `./deploy.sh` 或 `./deploy.sh local` |
| 日志 | `deploy.bat logs` | `./deploy.sh logs` |
| 停止 | `deploy.bat down` | `./deploy.sh down` |
| 改配置后重启 | 改 `.env` → 再跑 deploy | 同左 |

数据(SQLite、封面缓存、日志)落在 `./data/mikanarr`,迁移机器把它一起带走即可。

## 端口 / 卷一览

- **8008** → WebUI(改宿主端口:编辑 `docker-compose.yml` 的 `ports`)。
- `downloads` → 下载根(容器内 `/downloads`);`nas_import` → 旧番剧导入(`/import-nas`);`bd_owned` → 已购原盘(`/bd-owned`);`./data/mikanarr` → 运行时数据(`/config`)。
- 不用 `nas_import` / `bd_owned`:在 `docker-compose.yml` 删掉对应卷与挂载行即可。

## 排障

- **容器起不来**:`deploy.* logs` 看错误。多半是 NAS 凭据/路径不对(CIFS 挂载失败)或端口被占。
- **CIFS 挂载失败(Linux)**:确认宿主能 `mount -t cifs` 该共享、内核有 cifs 模块、`vers=3.0` 兼容你的 NAS。
- **改了 `.env` 不生效**:重新跑 deploy(会以新环境重建)。
