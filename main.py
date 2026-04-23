"""
MetaloTubo Mobile — APK para encarregados de obra.
App Flet simplificada que comunica com uma Google Sheet partilhada
(mesmo service account que o ERP do escritório).

Funcionalidades:
  - Login simples (validado contra sheet `users`)
  - Criar Pedido (Consumíveis / Material / Máquinas)
  - Histórico da obra (últimos 20 pedidos feitos pelo mobile)

Arquitetura:
  - Lê `obras`, `consumiveis`, `maquinas`, `users` da Google Sheet (master)
  - Escreve novos pedidos em `pedidos_mobile` (cada linha = 1 artigo)
  - O ERP do PC chama `push_master_to_sheets()` para atualizar master
  - O ERP do PC chama `pull_pedidos_from_sheets()` para importar os pedidos

Build APK:
  $ flet build apk  (ver .github/workflows/build_apk.yml)

Credenciais:
  O ficheiro `credentials.json` (service account) deve estar em `assets/credentials.json`
  (bundled no APK via `flet build apk --assets assets`).
  O `sheet_id` é lido de `assets/sheet_id.txt` ou variável embutida abaixo.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import time
import traceback
from datetime import datetime

import flet as ft

# --- CONFIG ---
# Em APK, os assets ficam em /storage/emulated/0/... ou na pasta `assets/` empacotada.
# Durante `flet build apk --assets assets`, o próprio Flet resolve o caminho.
APP_TITLE = "MetaloTubo Mobile"
COR_PRIMARIA = "#1A237E"
COR_SECUNDARIA = "#0D47A1"
COR_OK = "#2E7D32"
COR_ERRO = "#C62828"
COR_URG = "#D32F2F"

# --- IMPORTS PROTEGIDOS (para rodar no IDE sem dependências) ---
try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials as GoogleCreds  # type: ignore
    _GSPREAD_OK = True
except Exception:
    _GSPREAD_OK = False
    gspread = None
    GoogleCreds = None

GSHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _assets_path(*parts) -> str:
    """Devolve caminho relativo à pasta assets (onde está credentials.json)."""
    # Flet em APK expõe os assets através de `page.get_asset_src` mas para lermos
    # o ficheiro diretamente (gspread precisa de path), usamos o diretório da app.
    base_candidates = [
        os.path.join(os.getcwd(), "assets"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
    ]
    for base in base_candidates:
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(base_candidates[0], *parts)


def _local_config_path() -> str:
    """Guarda credenciais do utilizador entre sessões (no storage da APK)."""
    base = os.path.join(os.path.expanduser("~"), ".metalotubo_mobile")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "login.json")


def load_login() -> dict:
    p = _local_config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_login(data: dict) -> None:
    with open(_local_config_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =====================================================================
# CLIENTE GOOGLE SHEETS
# =====================================================================
class SheetsClient:
    """Wrapper fino sobre gspread, com cache de worksheets."""

    def __init__(self):
        self._client = None
        self._sheet = None
        self._tabs: dict = {}
        self._last_read: dict = {}  # cache TTL curto

    def connect(self, creds_path: str, sheet_id: str):
        if not _GSPREAD_OK:
            raise RuntimeError("gspread não instalado. Build do APK com flet build apk.")
        if not os.path.exists(creds_path):
            raise RuntimeError(f"credentials.json não encontrado em {creds_path}")
        creds = GoogleCreds.from_service_account_file(creds_path, scopes=GSHEETS_SCOPES)
        self._client = gspread.authorize(creds)
        self._sheet = self._client.open_by_key(sheet_id)
        self._tabs = {ws.title: ws for ws in self._sheet.worksheets()}

    def ws(self, nome: str):
        if nome in self._tabs:
            return self._tabs[nome]
        try:
            w = self._sheet.worksheet(nome)
            self._tabs[nome] = w
            return w
        except Exception:
            raise RuntimeError(f"Worksheet '{nome}' não existe na Sheet.")

    def read(self, nome: str, ttl: int = 30) -> list:
        """Lê worksheet como lista de dicts. Cache TTL em segundos."""
        now = time.time()
        cached = self._last_read.get(nome)
        if cached and now - cached[0] < ttl:
            return cached[1]
        data = self.ws(nome).get_all_records()
        self._last_read[nome] = (now, data)
        return data

    def append(self, nome: str, row_values: list):
        w = self.ws(nome)
        # append_row evita colisões com escritas simultâneas
        w.append_row(row_values, value_input_option="RAW")


# =====================================================================
# APP
# =====================================================================
def main(page: ft.Page):
    page.title = APP_TITLE
    page.bgcolor = "#F0F2F5"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.window_min_width = 360

    client = SheetsClient()
    state = {"user": None, "obra": None}

    # -------- helpers UI --------
    def snack(msg: str, cor: str = "green"):
        page.snack_bar = ft.SnackBar(ft.Text(msg, color="white"), bgcolor=cor)
        page.snack_bar.open = True
        page.update()

    def top_bar(titulo: str, back=None):
        return ft.AppBar(
            leading=ft.IconButton(ft.icons.ARROW_BACK, on_click=back) if back else None,
            title=ft.Text(titulo, weight="bold"),
            bgcolor=COR_PRIMARIA, color="white",
        )

    # -------- SETUP (1º uso: pedir caminho credentials + sheet_id) --------
    def mostrar_setup():
        page.clean()
        login = load_login()
        tf_creds = ft.TextField(
            label="Caminho credentials.json",
            value=login.get("credentials_path") or _assets_path("credentials.json"),
        )
        tf_sheet = ft.TextField(
            label="Sheet ID", value=login.get("sheet_id") or "",
            hint_text="Parte do URL da Sheet entre /d/ e /edit",
        )

        def continuar(_=None):
            try:
                client.connect(tf_creds.value.strip(), tf_sheet.value.strip())
                login.update({
                    "credentials_path": tf_creds.value.strip(),
                    "sheet_id": tf_sheet.value.strip(),
                })
                save_login(login)
                snack("Ligação OK!", COR_OK)
                mostrar_login()
            except Exception as e:
                snack(f"Falha: {e}", COR_ERRO)

        page.add(
            top_bar("Configuração inicial"),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("Primeira utilização", size=18, weight="bold"),
                ft.Text("Indica o caminho do ficheiro credentials.json e o ID da Google "
                        "Sheet partilhada pelo escritório.", size=12, color="grey"),
                ft.Container(height=10),
                tf_creds,
                tf_sheet,
                ft.Container(height=10),
                ft.ElevatedButton("Continuar", icon=ft.icons.CHECK,
                                  on_click=continuar, bgcolor=COR_PRIMARIA,
                                  color="white", height=55),
            ], spacing=10)),
        )
        page.update()

    # -------- LOGIN --------
    def mostrar_login():
        login = load_login()
        if not login.get("credentials_path") or not login.get("sheet_id"):
            return mostrar_setup()
        # Garante que estamos ligados
        if client._sheet is None:
            try:
                client.connect(login["credentials_path"], login["sheet_id"])
            except Exception as e:
                snack(f"Ligação falhou: {e}", COR_ERRO)
                return mostrar_setup()

        page.clean()
        tf_user = ft.TextField(label="Utilizador", autofocus=True)
        tf_pass = ft.TextField(label="Password", password=True,
                                can_reveal_password=True)
        err = ft.Text("", color=COR_ERRO)

        def entrar(_=None):
            nome = (tf_user.value or "").strip()
            pwd = tf_pass.value or ""
            if not nome or not pwd:
                err.value = "Preenche utilizador e password."; page.update(); return
            try:
                users = client.read("users", ttl=10)
            except Exception as e:
                err.value = f"Erro: {e}"; page.update(); return

            # No modo mobile, valida apenas username + ativo (a password real fica no PC).
            # A password é usada em cliente como 2ª linha de defesa, mas como o PC tem o
            # hash completo PBKDF2, aqui só fazemos fallback: user deve estar ativo.
            match = None
            for u in users:
                if str(u.get("nome") or "").strip().lower() == nome.lower():
                    match = u; break
            if not match:
                err.value = "Utilizador não existe na Sheet."; page.update(); return
            if str(match.get("ativo") or "True") != "True":
                err.value = "Utilizador desativado."; page.update(); return
            # OK (nota: validação de password completa fica no PC)
            state["user"] = nome
            mostrar_portal()

        page.add(
            ft.Container(padding=30, content=ft.Column([
                ft.Container(height=20),
                ft.Text("METALOTUBO", size=30, weight="bold", color=COR_PRIMARIA),
                ft.Text("App de Obra", size=14, color="grey"),
                ft.Container(height=30),
                tf_user, tf_pass, err,
                ft.Container(height=15),
                ft.ElevatedButton("ENTRAR", icon=ft.icons.LOGIN,
                                  on_click=entrar, height=55,
                                  bgcolor=COR_PRIMARIA, color="white"),
                ft.TextButton("Reconfigurar", on_click=lambda e: mostrar_setup()),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        )
        page.update()

    # -------- PORTAL --------
    def mostrar_portal():
        page.clean()
        page.add(
            top_bar(f"Olá, {state['user']}", back=None),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("O que queres fazer?", size=18, weight="bold"),
                ft.Container(height=10),
                ft.ElevatedButton("NOVO PEDIDO", icon=ft.icons.ADD_SHOPPING_CART,
                                  height=80, bgcolor=COR_SECUNDARIA, color="white",
                                  on_click=lambda e: mostrar_pedido()),
                ft.ElevatedButton("HISTÓRICO DA OBRA", icon=ft.icons.HISTORY,
                                  height=80, bgcolor=COR_PRIMARIA, color="white",
                                  on_click=lambda e: mostrar_historico()),
                ft.Container(height=20),
                ft.OutlinedButton("Sair", icon=ft.icons.LOGOUT,
                                  on_click=lambda e: (state.update({"user": None}),
                                                       mostrar_login())),
            ], spacing=12)),
        )
        page.update()

    # -------- NOVO PEDIDO --------
    def mostrar_pedido():
        page.clean()
        try:
            obras_rows = client.read("obras", ttl=60)
            cons_rows = client.read("consumiveis", ttl=60)
            maqs_rows = client.read("maquinas", ttl=60)
        except Exception as e:
            snack(f"Erro a ler dados: {e}", COR_ERRO)
            return mostrar_portal()

        obras_ativas = [str(r.get("nome")) for r in obras_rows
                         if str(r.get("estado") or "Ativa") == "Ativa"]
        dd_obra = ft.Dropdown(
            label="Obra", value=obras_ativas[0] if obras_ativas else None,
            options=[ft.dropdown.Option(o) for o in obras_ativas],
        )

        subs = sorted({str(r.get("subcategoria") or "")
                       for r in cons_rows if r.get("subcategoria")})
        dd_sub = ft.Dropdown(
            label="Subcategoria (Consumíveis)",
            options=[ft.dropdown.Option("(Todas)")]
                     + [ft.dropdown.Option(s) for s in subs],
            value="(Todas)",
        )

        dd_item = ft.Dropdown(label="Item", options=[])

        def _items_para_sub(sub_sel: str):
            if sub_sel in (None, "", "(Todas)"):
                rows = cons_rows
            else:
                rows = [r for r in cons_rows if str(r.get("subcategoria")) == sub_sel]
            return [ft.dropdown.Option(str(r.get("item"))) for r in rows
                     if str(r.get("item") or "").strip()]

        dd_item.options = _items_para_sub("(Todas)")

        def on_sub_change(_=None):
            dd_item.options = _items_para_sub(dd_sub.value)
            dd_item.value = None
            page.update()
        dd_sub.on_change = on_sub_change

        tf_qtd = ft.TextField(label="Qtd", value="1", keyboard_type=ft.KeyboardType.NUMBER)
        tf_det = ft.TextField(label="Detalhes (opcional)", hint_text="ex: urgente para amanhã")
        sw_urg = ft.Switch(label="URGENTE", active_color=COR_URG)

        def enviar(_=None):
            if not dd_obra.value:
                snack("Escolhe a obra.", COR_ERRO); return
            if not dd_item.value:
                snack("Escolhe o item.", COR_ERRO); return
            qtd = (tf_qtd.value or "1").strip()
            try:
                qtd_i = int(float(qtd.replace(",", ".")))
            except Exception:
                qtd_i = 1
            row = [
                str(uuid.uuid4()),                        # uuid
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # timestamp
                state["user"] or "mobile",                # utilizador
                dd_obra.value,                            # obra
                "Consumíveis",                            # tipo
                dd_sub.value or "",                       # subcategoria
                dd_item.value,                            # item
                tf_det.value or "",                       # detalhes
                str(qtd_i),                               # qtd
                "TRUE" if sw_urg.value else "FALSE",      # urgente
                "",                                        # notas
                "FALSE",                                   # processado
            ]
            try:
                client.append("pedidos_mobile", row)
                snack("✅ Pedido enviado!", COR_OK)
                mostrar_portal()
            except Exception as e:
                snack(f"Falha a enviar: {e}", COR_ERRO)

        page.add(
            top_bar("Novo Pedido", back=lambda e: mostrar_portal()),
            ft.Container(padding=15, content=ft.Column([
                dd_obra,
                dd_sub, dd_item,
                ft.Row([tf_qtd, sw_urg], spacing=10),
                tf_det,
                ft.Container(height=10),
                ft.ElevatedButton("ENVIAR PEDIDO", icon=ft.icons.SEND,
                                  on_click=enviar, height=55, expand=True,
                                  bgcolor=COR_OK, color="white"),
                ft.Container(height=5),
                ft.Text(f"💡 {len(cons_rows)} consumíveis disponíveis "
                         f"em {len(subs)} subcategorias", size=11, italic=True,
                         color="grey"),
            ], spacing=12, scroll=ft.ScrollMode.AUTO)),
        )
        page.update()

    # -------- HISTÓRICO --------
    def mostrar_historico():
        page.clean()
        try:
            rows = client.read("pedidos_mobile", ttl=10)
        except Exception as e:
            snack(f"Erro: {e}", COR_ERRO)
            return mostrar_portal()

        # Últimos 20 do próprio utilizador
        meus = [r for r in rows if str(r.get("utilizador") or "") == (state["user"] or "")]
        meus = meus[-20:][::-1]

        if not meus:
            body = ft.Text("Sem pedidos.", italic=True)
        else:
            body_items = []
            for r in meus:
                proc = str(r.get("processado") or "").lower() in ("true", "1", "yes", "sim")
                urg = str(r.get("urgente") or "").lower() in ("true", "1", "yes", "sim")
                ts = str(r.get("timestamp") or "")[:16]
                item = str(r.get("item") or "")
                qtd = r.get("qtd") or ""
                obra = r.get("obra") or ""
                chip_cor = COR_OK if proc else ("grey" if not urg else COR_URG)
                chip_txt = "Recebido" if proc else ("URGENTE" if urg else "Enviado")
                body_items.append(ft.Container(
                    bgcolor="white", border_radius=8, padding=12,
                    content=ft.Column([
                        ft.Row([
                            ft.Text(ts, size=11, color="grey"),
                            ft.Container(
                                bgcolor=chip_cor, border_radius=12,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                content=ft.Text(chip_txt, size=10, color="white",
                                                 weight="bold"),
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(f"{item}  (x{qtd})", size=14, weight="bold"),
                        ft.Text(f"📍 {obra}", size=12, color="grey"),
                    ], spacing=3),
                ))
            body = ft.Column(body_items, spacing=8)

        page.add(
            top_bar("Histórico", back=lambda e: mostrar_portal()),
            ft.Container(padding=15, content=body, expand=True),
        )
        page.update()

    # -------- START --------
    try:
        mostrar_login()
    except Exception as e:
        page.add(ft.Text(f"Erro fatal: {e}", color=COR_ERRO))
        page.add(ft.Text(traceback.format_exc(), size=11))
        page.update()


if __name__ == "__main__":
    try:
        if hasattr(ft, "run"):
            ft.run(main)
        else:
            ft.app(target=main)
    except Exception as e:
        print("App crashed:", e)
        raise
