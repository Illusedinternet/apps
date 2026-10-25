# -*- coding: utf-8 -*-
import os
import re
import sys
import stat
import random
import ctypes
import subprocess

from textual.app import App, ComposeResult
from textual.containers import Container, Grid
from textual.widgets import Button, Header, Footer, Static, Label
from textual.screen import Screen

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
DOMAIN = "tr.rbxcdn.com"
RESOLVER = "9.9.9.9"

PROVIDERS = {
    "1": ("Amazon", "18.65.39.105"),
    "2": ("Akamai", "23.46.228.75"),
}

IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


# ---------- Administrator privileges ----------

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    if is_admin():
        return
    params = " ".join(f'"{a}"' for a in sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    if result > 32:  
        sys.exit(0)
    sys.exit(1)


# ---------- Hosts file helpers ----------

def read_lines():
    with open(HOSTS_PATH, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.readlines()


def write_lines(lines):
    if not os.access(HOSTS_PATH, os.W_OK):
        os.chmod(HOSTS_PATH, stat.S_IWRITE)
    with open(HOSTS_PATH, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.writelines(lines)


def get_entry():
    try:
        for line in read_lines():
            if DOMAIN in line:
                return line.strip()
    except Exception:
        pass
    return None


def set_entry(ip):
    lines = read_lines()
    eol = "\r\n" if (lines and lines[-1].endswith("\r\n")) else "\n"
    new_lines = [line for line in lines if DOMAIN not in line]
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines[-1] += eol
    new_lines.append(f"{ip} {DOMAIN}{eol}")
    write_lines(new_lines)
    flush_dns()


def flush_dns():
    try:
        subprocess.run(
            ["ipconfig", "/flushdns"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
    except Exception:
        pass


def resolve_ips():
    try:
        result = subprocess.run(
            ["nslookup", DOMAIN, RESOLVER],
            capture_output=True, timeout=20,
            creationflags=0x08000000,
        )
        output = result.stdout.decode(errors="replace") + "\n" + result.stderr.decode(errors="replace")
    except Exception:
        return []

    ips = []
    for ip in IPV4_RE.findall(output):
        if ip != RESOLVER and ip not in ips:
            ips.append(ip)
    return ips


# ---------- Textual UI Sub-screens & Dialogs ----------

class MessageScreen(Screen):
    """Центрированное модальное окно для сообщений."""

    CSS = """
    MessageScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #msg-container {
        width: 60;
        height: auto;
        background: #161b22;
        border: solid #388bfd;
        padding: 2;
        align: center middle;
    }
    #msg-title {
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
        text-align: center;
        width: 100%;
    }
    #msg-content {
        margin-bottom: 2;
        text-align: center;
        width: 100%;
    }
    Button {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self.dialog_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="msg-container"):
            yield Label(self.dialog_title, id="msg-title")
            yield Static(self.message, id="msg-content")
            yield Button("OK", id="btn-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ok":
            self.app.pop_screen()


class ProviderScreen(Screen):
    """Подменю выбора провайдера / Best IP."""

    CSS = """
    ProviderScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #prov-container {
        width: 60;
        height: auto;
        background: #161b22;
        border: solid #bb8009;
        padding: 2;
        align: center middle;
    }
    #prov-title {
        text-style: bold;
        color: #bb8009;
        margin-bottom: 1;
        text-align: center;
        width: 100%;
    }
    Button {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="prov-container"):
            yield Label("Select Provider / IP Source", id="prov-title")
            yield Button("1. Amazon (18.65.39.105)", id="prov-1", variant="warning")
            yield Button("2. Akamai (23.46.228.75)", id="prov-2", variant="warning")
            yield Button("3. Best IP (Auto nslookup)", id="prov-best", variant="success")
            yield Button("Back", id="prov-back", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prov-1":
            self.app.current_name, self.app.current_ip = PROVIDERS["1"]
            self._apply_provider()
        elif event.button.id == "prov-2":
            self.app.current_name, self.app.current_ip = PROVIDERS["2"]
            self._apply_provider()
        elif event.button.id == "prov-best":
            ips = resolve_ips()
            if not ips:
                msg = "[X] No addresses were returned by nslookup."
                self.app.pop_screen()
                self.app.push_screen(MessageScreen("Best IP Error", msg))
                return
            best = random.choice(ips)
            self.app.current_name = "Best IP (auto)"
            self.app.current_ip = best
            self._apply_provider()
        else:
            self.app.pop_screen()

    def _apply_provider(self):
        try:
            set_entry(self.app.current_ip)
            msg = f"[+] Provider set to: {self.app.current_name}\n[+] IP applied: {self.app.current_ip}"
        except Exception as e:
            msg = f"[X] Error: {e}"
        
        self.app.pop_screen()
        self.app.update_status()
        self.app.push_screen(MessageScreen("Provider Updated", msg))


# ---------- Main Application Screen ----------

class RobloxHostsApp(App):
    def __init__(self):
        super().__init__()
        self.current_ip = PROVIDERS["1"][1]
        self.current_name = PROVIDERS["1"][0]

    CSS = """
    Screen {
        background: #0d1117;
        color: #c9d1d9;
    }
    
    #header-box {
        dock: top;
        height: 5;
        content-align: center middle;
        background: #161b22;
        border-bottom: solid #30363d;
        color: #58a6ff;
        text-style: bold;
        text-align: center;
    }

    #main-container {
        align: center middle;
        padding: 2;
    }

    Grid {
        grid-size: 2 3;
        grid-gutter: 2 2;
        max-width: 80;
        max-height: 25;
        border: solid #388bfd;
        padding: 2;
        background: #161b22;
    }

    Button {
        width: 100%;
        height: 3;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self._get_status_text(), id="header-box")
        
        with Container(id="main-container"):
            with Grid():
                yield Button("1. Fix Roblox Images", id="btn-fix", variant="success")
                yield Button("2. Remove Link", id="btn-remove", variant="error")
                yield Button("3. Open Hosts", id="btn-hosts", variant="primary")
                yield Button("4. Provider / Best IP", id="btn-provider", variant="warning")
                yield Button("5. Quick Best IP", id="btn-generate", variant="primary")
                yield Button("6. About", id="btn-about", variant="default")
        yield Footer()

    def _get_status_text(self) -> str:
        entry = get_entry()
        return f"Roblox Hosts Tool — Active IP: {self.current_ip} ({self.current_name})\nHosts Entry: {entry if entry else 'none'}"

    def update_status(self):
        header_widget = self.query_one("#header-box", Static)
        header_widget.update(self._get_status_text())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        
        if btn_id == "btn-fix":
            try:
                set_entry(self.current_ip)
                msg = f"[+] Hosts successfully set to: {self.current_ip} {DOMAIN}"
            except Exception as e:
                msg = f"[X] Error: {e}"
            self.update_status()
            self.push_screen(MessageScreen("Fix Roblox Images", msg))
            
        elif btn_id == "btn-remove":
            try:
                lines = read_lines()
                new_lines = [line for line in lines if DOMAIN not in line]
                if len(new_lines) == len(lines):
                    msg = f"[!] Entry not found in hosts ({DOMAIN})."
                else:
                    write_lines(new_lines)
                    flush_dns()
                    msg = f"[+] Successfully removed from hosts: {DOMAIN}"
            except Exception as e:
                msg = f"[X] Error: {e}"
            self.update_status()
            self.push_screen(MessageScreen("Remove Link", msg))
            
        elif btn_id == "btn-hosts":
            try:
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "notepad.exe", f'"{HOSTS_PATH}"', None, 1
                )
                msg = "[+] Notepad opened as administrator."
            except Exception as e:
                msg = f"[X] Failed to open Notepad: {e}"
            self.push_screen(MessageScreen("Open Hosts File", msg))
            
        elif btn_id == "btn-provider":
            self.push_screen(ProviderScreen())
            
        elif btn_id == "btn-generate":
            ips = resolve_ips()
            if not ips:
                msg = "[X] No addresses were returned by nslookup."
            else:
                best = random.choice(ips)
                self.current_ip = best
                self.current_name = "Best IP (auto)"
                try:
                    set_entry(best)
                    msg = f"[+] Found {len(ips)} IPs.\nPicked & applied best IP: {best}"
                except Exception as e:
                    msg = f"[X] Error applying IP: {e}"
            self.update_status()
            self.push_screen(MessageScreen("Generate Best IP", msg))
            
        elif btn_id == "btn-about":
            about_text = (
                "Roblox Hosts Tool (Textual TUI)\n"
                "Done by illusedinternet\n"
                "https://github.com/Illusedinternet"
            )
            self.push_screen(MessageScreen("About", about_text))


if __name__ == "__main__":
    ensure_admin()
    app = RobloxHostsApp()
    app.run()
