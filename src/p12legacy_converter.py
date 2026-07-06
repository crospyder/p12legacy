import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "P12 Legacy Converter"
APP_VERSION = "1.0.2"
FOOTER_TEXT = "P12 Legacy Converter v1.0.2 | Izradio Neven Pausić / Spine ICT Solutions d.o.o. 2026"

SELECT_W = 34
CERT_W = 520
PASS_W = 170
STATUS_W = 150
PFX_W = 270
TABLE_W = SELECT_W + CERT_W + PASS_W + STATUS_W + PFX_W + 40


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_openssl() -> Path | None:
    base = app_dir()
    candidates = [
        base / "openssl" / "openssl.exe",
        base / "openssl" / "bin" / "openssl.exe",
        Path(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"),
        Path(r"C:\Program Files\OpenSSL\bin\openssl.exe"),
    ]
    for item in candidates:
        if item.exists():
            return item
    found = shutil.which("openssl")
    return Path(found) if found else None


def find_provider_path(openssl_path: Path) -> Path:
    candidates = [
        openssl_path.parent,
        openssl_path.parent / "ossl-modules",
        openssl_path.parent.parent / "lib" / "ossl-modules",
        app_dir() / "openssl",
        app_dir() / "openssl" / "bin",
        app_dir() / "openssl" / "lib" / "ossl-modules",
    ]
    for item in candidates:
        if (item / "legacy.dll").exists():
            return item
    return openssl_path.parent


@dataclass
class CertItem:
    path: Path
    secret: tk.StringVar
    status: tk.StringVar
    output: tk.StringVar


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1220x680")
        self.minsize(1220, 620)
        self.resizable(True, True)

        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=("Segoe UI", 11))
        self.style.configure("TButton", font=("Segoe UI", 10))
        self.style.configure("TCheckbutton", font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        self.style.configure("Column.TLabel", font=("Segoe UI", 11, "bold"))

        self.openssl = find_openssl()
        self.provider_path = find_provider_path(self.openssl) if self.openssl else None
        self.output_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.items: list[CertItem] = []
        self.show = tk.BooleanVar(value=False)
        self.running = False
        self.selected: list[tk.BooleanVar] = []
        self.context_index: int | None = None

        self.build_ui()
        self.build_context_menu()
        self.log_startup()

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Konverzija .p12/.pfx certifikata u legacy PFX format za starije Windows sustave.").grid(row=1, column=0, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(buttons, text="Dodaj certifikate", command=self.add_files).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Ukloni označene", command=self.remove_selected).grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="Očisti listu", command=self.clear_items).grid(row=0, column=2, padx=4)

        body = ttk.Frame(self, padding=(14, 0, 14, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        table = ttk.Frame(body)
        table.grid(row=0, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(1, weight=1)

        columns = tk.Frame(table)
        columns.grid(row=0, column=0, sticky="w")
        self.set_table_columns(columns)
        ttk.Label(columns, text="Certifikat", style="Column.TLabel").grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(columns, text="Lozinka", style="Column.TLabel").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Label(columns, text="Status", style="Column.TLabel").grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(columns, text="Legacy PFX", style="Column.TLabel").grid(row=0, column=4, sticky="w", padx=4)

        self.canvas = tk.Canvas(table, highlightthickness=1, highlightbackground="#cccccc", width=TABLE_W)
        self.rows = ttk.Frame(self.canvas)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=max(e.width, TABLE_W)))

        options = ttk.Frame(body, padding=(0, 10, 0, 0))
        options.grid(row=1, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Ovdje spremamo konvertirani certifikat:").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(options, text="Odaberi", command=self.choose_output).grid(row=0, column=2)
        ttk.Button(options, text="Otvori folder", command=self.open_output_folder).grid(row=0, column=3, padx=(8, 0))
        ttk.Checkbutton(options, text="Prikaži lozinke", variable=self.show, command=self.refresh).grid(row=0, column=4, padx=(12, 0))

        action = ttk.Frame(body, padding=(0, 10, 0, 0))
        action.grid(row=2, column=0, sticky="ew")
        action.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(action, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.convert_button = ttk.Button(action, text="Konvertiraj", command=self.convert_selected)
        self.convert_button.grid(row=0, column=1)

        log_box = ttk.LabelFrame(body, text="Log", padding=8)
        log_box.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        log_box.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_box, height=9, wrap="word", state="disabled", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(self, padding=(14, 4, 14, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Separator(footer).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(footer, text=FOOTER_TEXT, anchor="center").grid(row=1, column=0, sticky="ew")

    @staticmethod
    def set_table_columns(frame: tk.Misc) -> None:
        widths = [SELECT_W, CERT_W, PASS_W, STATUS_W, PFX_W]
        for i, width in enumerate(widths):
            frame.grid_columnconfigure(i, minsize=width, weight=0)

    def build_context_menu(self) -> None:
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Otvori lokaciju certifikata", command=self.open_input_location)
        self.menu.add_command(label="Otvori output folder", command=self.open_output_folder)
        self.menu.add_separator()
        self.menu.add_command(label="Ponovi konverziju", command=self.convert_context_item)
        self.menu.add_command(label="Ukloni iz liste", command=self.remove_context_item)

    def log_startup(self) -> None:
        if self.openssl:
            self.log(f"OpenSSL: {self.openssl}")
            self.log(f"Provider path: {self.provider_path}")
        else:
            self.log("GREŠKA: Portable OpenSSL nije pronađen. Provjerite postoji li mapa openssl u direktoriju aplikacije.")

    def log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def add_files(self) -> None:
        files = filedialog.askopenfilenames(title="Odaberi certifikate", filetypes=[("PKCS12", "*.p12 *.pfx"), ("Sve datoteke", "*.*")])
        known = {str(item.path).lower() for item in self.items}
        first_added: Path | None = None
        for name in files:
            path = Path(name)
            if str(path).lower() not in known:
                self.items.append(CertItem(path=path, secret=tk.StringVar(), status=tk.StringVar(value="Spreman"), output=tk.StringVar(value="")))
                if first_added is None:
                    first_added = path
        if first_added is not None:
            self.output_dir.set(str(first_added.parent))
        self.refresh()

    def remove_selected(self) -> None:
        for idx in reversed([i for i, var in enumerate(self.selected) if var.get()]):
            del self.items[idx]
        self.refresh()

    def clear_items(self) -> None:
        self.items.clear()
        self.refresh()

    def refresh(self) -> None:
        for widget in self.rows.winfo_children():
            widget.destroy()
        self.selected = []
        mask = "" if self.show.get() else "*"
        for idx, item in enumerate(self.items):
            selected = tk.BooleanVar(value=True)
            self.selected.append(selected)
            frame = ttk.Frame(self.rows, padding=(4, 4, 4, 4))
            frame.grid(row=idx, column=0, sticky="w")
            self.set_table_columns(frame)
            frame.bind("<Button-3>", lambda e, i=idx: self.show_context_menu(e, i))

            check = ttk.Checkbutton(frame, variable=selected)
            cert_label = ttk.Label(frame, text=str(item.path), anchor="w")
            password_entry = ttk.Entry(frame, textvariable=item.secret, show=mask)
            status_label = ttk.Label(frame, textvariable=item.status, anchor="w")
            output_button = ttk.Button(frame, textvariable=item.output, command=lambda i=idx: self.open_output_file(i))

            check.grid(row=0, column=0, sticky="w", padx=(0, 6))
            cert_label.grid(row=0, column=1, sticky="ew", padx=(0, 6))
            password_entry.grid(row=0, column=2, sticky="ew", padx=4)
            status_label.grid(row=0, column=3, sticky="w", padx=4)
            output_button.grid(row=0, column=4, sticky="ew", padx=4)

            for widget in (frame, check, cert_label, password_entry, status_label, output_button):
                widget.bind("<Button-3>", lambda e, i=idx: self.show_context_menu(e, i))

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Odaberi folder za konvertirane certifikate")
        if folder:
            self.output_dir.set(folder)

    def open_output_folder(self) -> None:
        folder = Path(self.output_dir.get())
        if folder.exists():
            os.startfile(str(folder))
        else:
            messagebox.showerror(APP_NAME, "Folder za konvertirane certifikate ne postoji.")

    def open_input_location(self) -> None:
        if self.context_index is None:
            return
        path = self.items[self.context_index].path
        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])

    def open_output_file(self, index: int) -> None:
        output_name = self.items[index].output.get()
        if not output_name or output_name == "-":
            return
        output_file = Path(self.output_dir.get()) / output_name
        if output_file.exists():
            subprocess.Popen(["explorer", "/select,", str(output_file)])

    def show_context_menu(self, event: tk.Event, index: int) -> None:
        self.context_index = index
        self.menu.tk_popup(event.x_root, event.y_root)

    def remove_context_item(self) -> None:
        if self.context_index is not None:
            del self.items[self.context_index]
            self.context_index = None
            self.refresh()

    def convert_context_item(self) -> None:
        if self.context_index is None or self.running:
            return
        output = Path(self.output_dir.get())
        threading.Thread(target=self.worker, args=([self.items[self.context_index]], output), daemon=True).start()

    def convert_selected(self) -> None:
        if self.running:
            return
        if not self.openssl:
            messagebox.showerror(APP_NAME, "Portable OpenSSL nije pronađen. Provjerite postoji li mapa openssl u direktoriju aplikacije.")
            return
        selected = [item for item, flag in zip(self.items, self.selected) if flag.get()]
        if not selected:
            messagebox.showwarning(APP_NAME, "Nema odabranih certifikata.")
            return
        output = Path(self.output_dir.get())
        if not output.exists():
            messagebox.showerror(APP_NAME, "Folder za konvertirane certifikate ne postoji.")
            return
        self.running = True
        self.convert_button.configure(state="disabled")
        self.progress.configure(maximum=len(selected), value=0)
        threading.Thread(target=self.worker, args=(selected, output), daemon=True).start()

    def worker(self, selected: list[CertItem], output: Path) -> None:
        try:
            for idx, item in enumerate(selected, start=1):
                self.after(0, item.status.set, "Obrada")
                try:
                    output_file = self.convert_one(item, output)
                    self.after(0, item.status.set, "Uspješno")
                    self.after(0, item.output.set, output_file.name)
                    self.after(0, self.log, f"OK: {item.path.name} -> {output_file.name}")
                except Exception as exc:
                    self.after(0, item.status.set, "Greška")
                    self.after(0, self.log, f"GREŠKA: {item.path.name}: {exc}")
                self.after(0, self.progress.configure, {"value": idx})
        finally:
            self.after(0, self.finish)

    def finish(self) -> None:
        self.running = False
        self.convert_button.configure(state="normal")
        self.log("Gotovo.")

    def convert_one(self, item: CertItem, output: Path) -> Path:
        pwd = item.secret.get()
        if not pwd:
            raise RuntimeError("lozinka nije upisana")
        if not item.path.exists():
            raise RuntimeError("ulazna datoteka ne postoji")

        out_file = output / f"{item.path.stem}.legacy.pfx"
        env = os.environ.copy()
        env["OPENSSL_CONF"] = ""
        env["OPENSSL_MODULES"] = str(self.provider_path)

        with tempfile.TemporaryDirectory(prefix="p12legacy_") as temp_dir:
            pem_file = Path(temp_dir) / f"{item.path.stem}.pem"
            self.run_openssl([
                "pkcs12", "-legacy", "-provider-path", str(self.provider_path),
                "-provider", "default", "-provider", "legacy",
                "-in", str(item.path), "-out", str(pem_file), "-nodes",
            ], env, pwd + "\n")
            self.run_openssl([
                "pkcs12", "-export", "-legacy", "-provider-path", str(self.provider_path),
                "-provider", "default", "-provider", "legacy",
                "-out", str(out_file), "-inkey", str(pem_file), "-in", str(pem_file),
            ], env, pwd + "\n" + pwd + "\n")
        return out_file

    def run_openssl(self, args: list[str], env: dict[str, str], stdin_text: str) -> None:
        assert self.openssl is not None
        result = subprocess.run([str(self.openssl), *args], input=stdin_text, capture_output=True, text=True, env=env, timeout=60)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "OpenSSL greška").strip()
            lower = msg.lower()
            if "verify" in lower or "password" in lower:
                raise RuntimeError("pogrešna lozinka ili neispravan certifikat")
            raise RuntimeError(msg.splitlines()[-1] if msg else "OpenSSL greška")


if __name__ == "__main__":
    App().mainloop()
