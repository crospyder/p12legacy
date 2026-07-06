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
APP_VERSION = "1.0.0"
FOOTER_TEXT = "Izradio Neven Pausić / Spine ICT Solutions d.o.o. 2026"


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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("980x620")
        self.minsize(900, 560)
        self.openssl = find_openssl()
        self.provider_path = find_provider_path(self.openssl) if self.openssl else None
        self.output_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.items: list[CertItem] = []
        self.show = tk.BooleanVar(value=False)
        self.running = False
        self.selected: list[tk.BooleanVar] = []
        self.build_ui()
        self.log_startup()

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
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

        columns = ttk.Frame(table)
        columns.grid(row=0, column=0, sticky="ew")
        columns.columnconfigure(0, weight=1)
        ttk.Label(columns, text="Certifikat", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(34, 4))
        ttk.Label(columns, text="Lozinka", font=("Segoe UI", 10, "bold"), width=22).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(columns, text="Status", font=("Segoe UI", 10, "bold"), width=22).grid(row=0, column=2, sticky="w", padx=4)

        self.canvas = tk.Canvas(table, highlightthickness=1, highlightbackground="#cccccc")
        self.rows = ttk.Frame(self.canvas)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))

        options = ttk.Frame(body, padding=(0, 10, 0, 0))
        options.grid(row=1, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Output folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(options, text="Odaberi", command=self.choose_output).grid(row=0, column=2)
        ttk.Checkbutton(options, text="Prikaži lozinke", variable=self.show, command=self.refresh).grid(row=0, column=3, padx=(12, 0))

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
        self.log_text = tk.Text(log_box, height=9, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(self, padding=(14, 4, 14, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Separator(footer).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(footer, text=FOOTER_TEXT, anchor="center").grid(row=1, column=0, sticky="ew")

    def log_startup(self) -> None:
        if self.openssl:
            self.log(f"OpenSSL: {self.openssl}")
            self.log(f"Provider path: {self.provider_path}")
        else:
            self.log("GREŠKA: OpenSSL nije pronađen. Dodaj portable OpenSSL u folder openssl uz aplikaciju.")

    def log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def add_files(self) -> None:
        files = filedialog.askopenfilenames(title="Odaberi certifikate", filetypes=[("PKCS12", "*.p12 *.pfx"), ("Sve datoteke", "*.*")])
        known = {str(item.path).lower() for item in self.items}
        for name in files:
            path = Path(name)
            if str(path).lower() not in known:
                self.items.append(CertItem(path=path, secret=tk.StringVar(), status=tk.StringVar(value="Spreman")))
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
            frame = ttk.Frame(self.rows, padding=(4, 3, 4, 3))
            frame.grid(row=idx, column=0, sticky="ew")
            frame.columnconfigure(1, weight=1)
            ttk.Checkbutton(frame, variable=selected).grid(row=0, column=0, padx=(0, 6))
            ttk.Label(frame, text=str(item.path), anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 6))
            ttk.Entry(frame, textvariable=item.secret, show=mask, width=24).grid(row=0, column=2, sticky="ew", padx=4)
            ttk.Label(frame, textvariable=item.status, width=22).grid(row=0, column=3, sticky="w", padx=4)

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Odaberi output folder")
        if folder:
            self.output_dir.set(folder)

    def convert_selected(self) -> None:
        if self.running:
            return
        if not self.openssl:
            messagebox.showerror(APP_NAME, "OpenSSL nije pronađen.")
            return
        selected = [item for item, flag in zip(self.items, self.selected) if flag.get()]
        if not selected:
            messagebox.showwarning(APP_NAME, "Nema odabranih certifikata.")
            return
        output = Path(self.output_dir.get())
        if not output.exists():
            messagebox.showerror(APP_NAME, "Output folder ne postoji.")
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
                    self.convert_one(item, output)
                    self.after(0, item.status.set, "Uspješno")
                    self.after(0, self.log, f"OK: {item.path.name}")
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

    def convert_one(self, item: CertItem, output: Path) -> None:
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
