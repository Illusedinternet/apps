# -*- coding: utf-8 -*-
import os
import re
import sys
import stat
import random
import ctypes
import subprocess

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
DOMAIN = "tr.rbxcdn.com"
RESOLVER = "9.9.9.9"

PROVIDERS = {
    "1": ("Amazon", "18.65.39.105"),
    "2": ("Akamai", "23.46.228.75"),
}

current_ip = PROVIDERS["1"][1]
current_name = PROVIDERS["1"][0]

IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


# ---------- Console helpers ----------

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def pause():
    input("Press Enter to continue...")


# ---------- Administrator privileges ----------

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    if is_admin():
        return
    print("Administrator privileges required. Requesting elevation...")
    params = " ".join(f'"{a}"' for a in sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1)
    if result > 32:  
        sys.exit(0)
    print("[X] Administrator privileges were not granted.")
    input("Press Enter to exit...")
    sys.exit(1)


# ---------- Hosts file helpers ----------

def read_lines():
    with open(HOSTS_PATH, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.readlines()


def write_lines(lines):
    if not os.access(HOSTS_PATH, os.W_OK):  # remove "read only" attribute if set
        os.chmod(HOSTS_PATH, stat.S_IWRITE)
    with open(HOSTS_PATH, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.writelines(lines)


def get_entry():
    """Return the current hosts line with our domain (or None)."""
    try:
        for line in read_lines():
            if DOMAIN in line:
                return line.strip()
    except Exception:
        pass
    return None


def set_entry(ip):
    """Replace any existing entry with '<ip> <domain>' (single line, no duplicates)."""
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
        print("[i] DNS cache flushed.")
    except Exception:
        pass


# ---------- Menu actions ----------

def fix_roblox_images():
    try:
        entry = get_entry()
        if entry == f"{current_ip} {DOMAIN}":
            print(f"[!] Already in hosts: {entry}")
            return
        set_entry(current_ip)
        print(f"[+] Hosts set to: {current_ip} {DOMAIN}")
    except PermissionError:
        print("[X] Access to hosts denied. Administrator rights are required.")
    except Exception as e:
        print(f"[X] Error: {e}")


def remove_link():
    try:
        lines = read_lines()
        new_lines = [line for line in lines if DOMAIN not in line]
        if len(new_lines) == len(lines):
            print(f"[!] Entry not found in hosts ({DOMAIN}).")
            return
        write_lines(new_lines)
        print(f"[+] Removed from hosts: {DOMAIN}")
        flush_dns()
    except PermissionError:
        print("[X] Access to hosts denied. Administrator rights are required.")
    except Exception as e:
        print(f"[X] Error: {e}")


def open_hosts():
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "notepad.exe", f'"{HOSTS_PATH}"', None, 1
    )
    if result > 32:
        print("[+] Notepad opened as administrator.")
    else:
        print("[X] Failed to open Notepad.")


def choose_provider():
    global current_ip, current_name
    print()
    print("Select provider:")
    print(f"  1  Amazon (default)   {PROVIDERS['1'][1]}")
    print(f"  2  Akamai             {PROVIDERS['2'][1]}")
    print("  0  Back")
    choice = input("> ").strip()
    if choice not in PROVIDERS:
        if choice != "0":
            print("[?] Unknown option.")
            pause()
        return
    current_name, current_ip = PROVIDERS[choice]
    print(f"[+] Provider set to: {current_name} ({current_ip})")
    entry = get_entry()
    if entry is None:
        print("[i] No hosts entry yet - press 1 to apply it.")
    elif entry != f"{current_ip} {DOMAIN}":
        try:
            set_entry(current_ip)
            print(f"[+] Hosts entry updated to: {current_ip} {DOMAIN}")
        except Exception as e:
            print(f"[X] Error: {e}")
    else:
        print("[!] Hosts entry is already up to date.")


def resolve_ips():
    """Run 'nslookup DOMAIN RESOLVER' and return the list of answer IPs."""
    try:
        result = subprocess.run(
            ["nslookup", DOMAIN, RESOLVER],
            capture_output=True, timeout=20,
            creationflags=0x08000000,
        )
        output = result.stdout.decode(errors="replace")
        output += "\n" + result.stderr.decode(errors="replace")
    except subprocess.TimeoutExpired:
        print("[X] nslookup timed out. Check your internet connection.")
        return []
    except Exception as e:
        print(f"[X] nslookup failed: {e}")
        return []

    ips = []
    for ip in IPV4_RE.findall(output):
        if ip != RESOLVER and ip not in ips:
            ips.append(ip)
    return ips


def generate_best_ip():
    global current_ip, current_name
    print(f"[*] Running: nslookup {DOMAIN} {RESOLVER} ...")
    ips = resolve_ips()
    if not ips:
        print("[X] No addresses were returned.")
        return
    print(f"[i] Found {len(ips)} address(es):")
    for ip in ips:
        print(f"      {ip}")
    best = random.choice(ips)
    print(f"[+] Picked: {best}")
    current_ip = best
    current_name = "Best IP (auto)"
    answer = input("Apply this IP to hosts now? [Y/n] > ").strip().lower()
    if answer in ("", "y", "yes"):
        try:
            set_entry(best)
            print(f"[+] Hosts set to: {best} {DOMAIN}")
        except Exception as e:
            print(f"[X] Error: {e}")
    else:
        print("[i] Not applied. Press 1 later to apply it manually.")


def about():
    print()
    print("=" * 44)
    print("  Done by illusedinternet")
    print("  https://github.com/Illusedinternet")
    print("  IP: google")
    print("=" * 44)


# ---------- Main menu ----------

def main():
    ensure_admin()

    while True:
        clear_screen()
        entry = get_entry()
        print("=" * 44)
        print("  Roblox Hosts Tool")
        print("=" * 44)
        print(f"  Active IP : {current_ip}  ({current_name})")
        print(f"  Hosts     : {entry if entry else 'none'}")
        print()
        print("  1  Fix Roblox Images")
        print("  2  Remove link")
        print("  3  Open hosts")
        print(f"  4  Provider: {current_name}")
        print("  5  Generate a best IP")
        print("  6  About")
        print("  0  Exit")
        choice = input("> ").strip()

        # Every option clears the screen first
        clear_screen()

        if choice == "1":
            fix_roblox_images()
            pause()
        elif choice == "2":
            remove_link()
            pause()
        elif choice == "3":
            open_hosts()
            pause()
        elif choice == "4":
            choose_provider()
        elif choice == "5":
            generate_best_ip()
            pause()
        elif choice == "6":
            about()
            pause()
        elif choice == "0":
            clear_screen()
            break
        else:
            print("[?] Unknown option. Enter 0-6.")
            pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
