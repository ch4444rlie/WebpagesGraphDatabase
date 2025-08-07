# Brad's Simplified Kùzu Database

## Setup
1. Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/
2. Free disk space (ensure 10–20 GB free):
   ```powershell
   cleanmgr
   docker system prune -a --volumes
   docker builder prune -a