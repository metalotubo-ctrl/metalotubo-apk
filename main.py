"""
MetaloTubo Mobile — APK para encarregados de obra.
Comunicação via Google Apps Script webhook (sem dependências pesadas).
"""

from __future__ import annotations

import os
import json
import uuid
import time
import tempfile
import traceback
import urllib.request
import urllib.error
from datetime import datetime

import flet as ft

APP_TITLE = "MetaloTubo Mobile"
COR_PRIMARIA = "#1A237E"
COR_SECUNDARIA = "#0D47A1"
COR_OK = "#2E7D32"
COR_ERRO = "#C62828"
COR_URG = "#D32F2F"


# ---------------------------------------------------------------------
# Paths — tudo gravado em FLET_APP_STORAGE_DATA (privado da APK)
# ---------------------------------------------------------------------

def _storage_dir() -> str:
    base = os.environ.get("FLET_APP_STORAGE_DATA") or ""
    if not base or not os.path.isdir(os.path.dirname(base) or base):
        home = os.path.expanduser("~")
        if not home or home in ("/", "~") or not os.path.isdir(home):
            home = tempfile.gettempdir()
        base = os.path.join(home, ".metalotubo_mobile")
    try:
        os.makedirs(base, exist_ok=True)
    except PermissionError:
        base = os.path.join(tempfile.gettempdir(), "metalotubo_mobile")
        os.makedirs(base, exist_ok=True)
    return base


def _login_file() -> str:
    return os.path.join(_storage_dir(), "login.json")


def _assets_path(*parts) -> str:
    """Devolve caminho de assets (bundled no APK)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in [
        os.path.join(here, "assets"),
        os.path.join(os.getcwd(), "assets"),
    ]:
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(here, "assets", *parts)


def load_login() -> dict:
    p = _login_file()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_login(data: dict) -> None:
    try:
        with open(_login_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_login failed:", e)


def _load_bundled_webhook() -> str:
    try:
        p = _assets_path("webhook_url.txt")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------
# Cliente Apps Script
# ---------------------------------------------------------------------
class WebhookClient:
    def __init__(self):
        self.url: str = ""
        self._cache: dict = {}

    def connect(self, url: str):
        if not url or not url.startswith("https://"):
            raise RuntimeError("URL do Apps Script inválida.")
        self.url = url.rstrip("/")
        # Testa ligação
        r = self.call("ping", {}, ttl=0)
        if not r.get("ok"):
            raise RuntimeError("Resposta inesperada do webhook: " + str(r))

    def call(self, action: str, params: dict = None, ttl: int = 30):
        if not self.url:
            raise RuntimeError("Webhook não configurado.")
        payload = {"action": action}
        payload.update(params or {})

        # Cache só para leituras
        cache_key = None
        if action.startswith("get_") and ttl > 0:
            cache_key = json.dumps(payload, sort_keys=True)
            cached = self._cache.get(cache_key)
            if cached and time.time() - cached[0] < ttl:
                return cached[1]

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
            except Exception:
                raw = str(e)
            raise RuntimeError(f"HTTP {e.code}: {raw[:200]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ligação falhou: {e.reason}")

        try:
            data = json.loads(raw)
        except Exception:
            raise RuntimeError(f"Resposta inválida: {raw[:200]}")

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(data["error"])

        if cache_key:
            self._cache[cache_key] = (time.time(), data)
        return data


# ---------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------
def main(page: ft.Page):
    page.title = APP_TITLE
    page.bgcolor = "#F0F2F5"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.window_min_width = 360

    client = WebhookClient()
    state = {"user": None}

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

    # -------- SETUP --------
    def mostrar_setup():
        page.clean()
        login = load_login()
        default_url = login.get("webhook_url") or _load_bundled_webhook()

        tf_url = ft.TextField(
            label="URL do Apps Script",
            value=default_url,
            hint_text="https://script.google.com/macros/s/.../exec",
            multiline=True, min_lines=1, max_lines=3,
        )
        err = ft.Text("", color=COR_ERRO, size=12)

        def continuar(_=None):
            try:
                url = (tf_url.value or "").strip()
                client.connect(url)
                login["webhook_url"] = url
                save_login(login)
                snack("Ligação OK!", COR_OK)
                mostrar_login()
            except Exception as e:
                err.value = f"Falha: {e}"
                page.update()

        page.add(
            top_bar("Configuração inicial"),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("Primeira utilização", size=18, weight="bold"),
                ft.Text("Cola a URL do Apps Script partilhada pelo escritório.",
                        size=12, color="grey"),
                ft.Container(height=10),
                tf_url,
                err,
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
        if not login.get("webhook_url"):
            return mostrar_setup()
        if not client.url:
            try:
                client.connect(login["webhook_url"])
            except Exception as e:
                snack(f"Falha: {e}", COR_ERRO)
                return mostrar_setup()

        page.clean()
        tf_user = ft.TextField(label="Utilizador", autofocus=True)
        tf_pass = ft.TextField(label="Password", password=True,
                                can_reveal_password=True)
        err = ft.Text("", color=COR_ERRO)

        def entrar(_=None):
            nome = (tf_user.value or "").strip()
            if not nome:
                err.value = "Preenche o utilizador."
                page.update()
                return
            try:
                users = client.call("get_users", ttl=10)
            except Exception as e:
                err.value = f"Erro: {e}"
                page.update()
                return

            match = None
            for u in users:
                if str(u.get("nome") or "").strip().lower() == nome.lower():
                    match = u
                    break
            if not match:
                err.value = "Utilizador não existe."
                page.update()
                return
            if str(match.get("ativo") or "True") not in ("True", "true", "1"):
                err.value = "Utilizador desativado."
                page.update()
                return
            state["user"] = nome
            mostrar_portal()

        logo_widget = ft.Image(
            src=_assets_path("logo.png"),
            width=220, height=150, fit=ft.ImageFit.CONTAIN,
            error_content=ft.Text("METALOTUBO", size=28, weight="bold",
                                    color=COR_PRIMARIA),
        )

        page.add(
            ft.Container(padding=30, content=ft.Column([
                ft.Container(height=10),
                logo_widget,
                ft.Text("App de Obra", size=14, color="grey"),
                ft.Container(height=25),
                tf_user, tf_pass, err,
                ft.Container(height=10),
                ft.ElevatedButton("ENTRAR", icon=ft.icons.LOGIN,
                                  on_click=entrar, height=55,
                                  bgcolor=COR_PRIMARIA, color="white"),
                ft.TextButton("Reconfigurar", on_click=lambda e: mostrar_setup()),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)),
        )
        page.update()

    # -------- PORTAL --------
    def mostrar_portal():
        page.clean()
        page.add(
            top_bar(f"Olá, {state['user']}"),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("O que queres fazer?", size=18, weight="bold"),
                ft.Container(height=10),
                ft.ElevatedButton("NOVO PEDIDO", icon=ft.icons.ADD_SHOPPING_CART,
                                  height=80, bgcolor=COR_SECUNDARIA, color="white",
                                  on_click=lambda e: mostrar_pedido()),
                ft.ElevatedButton("HISTÓRICO", icon=ft.icons.HISTORY,
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
            obras_rows = client.call("get_obras", ttl=60)
            cons_rows = client.call("get_consumiveis", ttl=60)
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
            label="Subcategoria",
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

        tf_qtd = ft.TextField(label="Qtd", value="1",
                               keyboard_type=ft.KeyboardType.NUMBER)
        tf_det = ft.TextField(label="Detalhes (opcional)",
                               hint_text="ex: urgente para amanhã")
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

            row = {
                "uuid": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "utilizador": state["user"] or "mobile",
                "obra": dd_obra.value,
                "tipo": "Consumíveis",
                "subcategoria": dd_sub.value or "",
                "item": dd_item.value,
                "detalhes": tf_det.value or "",
                "qtd": str(qtd_i),
                "urgente": "TRUE" if sw_urg.value else "FALSE",
                "notas": "",
                "processado": "FALSE",
            }
            try:
                client.call("post_pedido", {"row": row}, ttl=0)
                snack("Pedido enviado!", COR_OK)
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
                                  on_click=enviar, height=55,
                                  bgcolor=COR_OK, color="white"),
                ft.Container(height=5),
                ft.Text(f"{len(cons_rows)} consumíveis em {len(subs)} subcategorias",
                         size=11, italic=True, color="grey"),
            ], spacing=12, scroll=ft.ScrollMode.AUTO)),
        )
        page.update()

    # -------- HISTÓRICO --------
    def mostrar_historico():
        page.clean()
        try:
            rows = client.call("get_historico",
                                {"user": state["user"] or ""}, ttl=10)
        except Exception as e:
            snack(f"Erro: {e}", COR_ERRO)
            return mostrar_portal()

        if not rows:
            body = ft.Text("Sem pedidos.", italic=True)
        else:
            body_items = []
            for r in rows:
                proc = str(r.get("processado") or "").lower() in ("true", "1")
                urg = str(r.get("urgente") or "").lower() in ("true", "1")
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
                        ft.Text(f"{obra}", size=12, color="grey"),
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
