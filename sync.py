import os
import subprocess
import argparse

# Порт ESP32 по умолчанию (можно переопределить через --port)
ESP_PORT = "com3"
AMPY = f"ampy --port {ESP_PORT}"

def run_cmd(cmd):
    """Запуск команды ampy"""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:
        print(f"[ERR] {cmd}\n{e.output.decode()}")
        return ""

def esp_ls(path=""):
    """Получить список (не рекурсивно) объектов на ESP"""
    files = []
    out = run_cmd(f"{AMPY} ls {path}".strip())
    for line in out.splitlines():
        f = line.strip()
        if f:
            files.append(f)
    return files

def esp_ls_recursive(path=""):
    """Рекурсивный список путей на ESP (файлы и каталоги)."""
    cmd = f"{AMPY} ls -r {path}".strip() if path else f"{AMPY} ls -r"
    out = run_cmd(cmd)
    if not out.strip():
        # Фоллбек: без -r (вернёт только верхний уровень)
        out = run_cmd(f"{AMPY} ls {path}".strip())
    items = []
    for line in out.splitlines():
        p = line.strip()
        if p:
            items.append(p)
    return items

def esp_put(local, remote):
    """Залить файл на ESP"""
    print(f"[PUT] {local} -> {remote}")
    run_cmd(f'{AMPY} put "{local}" "{remote}"')

def esp_get(remote, local):
    """Скачать файл с ESP на локальный диск (создаёт папки при необходимости)."""
    d = os.path.dirname(local)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    print(f"[GET] {remote} -> {local}")
    run_cmd(f'{AMPY} get "{remote}" "{local}"')

def esp_rm_recursive(path=""):
    """Удалить всё содержимое в папке на ESP (рекурсивно)."""
    items = esp_ls_recursive(path)
    if not items:
        return
    # Сначала удаляем файлы
    for p in items:
        if not p.endswith('/'):
            print(f"[DEL] {p}")
            run_cmd(f'{AMPY} rm "{p}"')
    # Потом удаляем папки (с конца, чтобы удалять пустые)
    for p in sorted(items, reverse=True):
        if p.endswith('/'):
            print(f"[RMDIR] {p}")
            run_cmd(f'{AMPY} rmdir "{p}"')

def sync(local_dir="flash", remote_dir=""):
    """Синхронизация локальной папки с ESP (заливка).
       Перед этим полностью очищает папку назначения.
    """
    print(f"[CLEAN] Очистка {remote_dir or '/'} на ESP...")
    esp_rm_recursive(remote_dir)

    for root, dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir)
        if rel == '.':
            rel = ''
        esp_path = os.path.join(remote_dir, rel).replace("\\", "/")
        if esp_path == ".":
            esp_path = ""

        for f in files:
            local_path = os.path.join(root, f)
            remote_path = os.path.join(esp_path, f).replace("\\", "/")
            esp_put(local_path.replace('\\', '/'), remote_path)

def sync_down(remote_dir="", local_dir="flash_from_esp"):
    """Скачивание всего содержимого с ESP на локальный диск."""
    items = esp_ls_recursive(remote_dir)
    if not items:
        print("[WARN] На устройстве ничего не найдено (или недоступен список).")
        return

    for p in items:
        p = p.strip()
        if not p:
            continue
        if p.endswith('/'):
            continue
        remote_path = p
        rel = p
        if remote_dir:
            prefix = remote_dir.rstrip('/') + '/'
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
        rel = rel.lstrip('/')
        local_path = os.path.join(local_dir, rel)
        esp_get(remote_path, local_path)

if __name__ == "__main__":
    # пример: очистка /flash и загрузка локальной папки
    #sync(local_dir="src", remote_dir="/flash")
    sync_down(remote_dir='/flash', local_dir='src')
