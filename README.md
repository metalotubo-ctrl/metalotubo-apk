# MetaloTubo Mobile — APK Android

App Flet simplificada para encarregados de obra.

## Como construir o APK (100% gratuito, sem instalar nada no PC)

### Pré-requisitos
- Conta GitHub gratuita: https://github.com/signup
- Ficheiro `credentials.json` (service account Google)
- ID da Google Sheet

### Passos (10 minutos)

**1. Criar repo público novo no GitHub**
- Vai a https://github.com/new
- Repository name: `metalotubo-apk`
- Visibilidade: **Public** (MUITO IMPORTANTE — minutos de Actions ilimitados)
- NÃO marques "Add README"
- Clica **Create repository**

**2. Enviar os ficheiros (arrastar-e-largar)**
- No repo vazio, clica **"uploading an existing file"** (link azul no meio da página)
- Arrasta TODOS os ficheiros deste ZIP para a janela do browser
- Em baixo, clica **Commit changes** (botão verde)

**3. Configurar secrets**
- No teu repo: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Cria 2 secrets (instruções detalhadas em `SECRETS_GUIDE.md`):
  - `GOOGLE_CREDENTIALS_B64` → o credentials.json em base64
  - `GOOGLE_SHEET_ID` → o ID da Sheet

**4. Correr o workflow**
- Separador **Actions** → **Build APK Android** (barra lateral)
- **Run workflow** (botão azul direita) → **Run workflow** (verde)
- Aguardar ~15-20 min (primeira vez)

**5. Descarregar o APK**
- Quando acabar com ✅ verde, clica no run
- Em baixo: secção **Artifacts** → clica em **metalotubo-apk**
- Descarrega um ZIP → extrai → tens `app-release.apk`

**6. Instalar no telemóvel**
- Envia o `.apk` por email/WhatsApp/USB
- Abre no telemóvel → permite origem desconhecida → Instalar
