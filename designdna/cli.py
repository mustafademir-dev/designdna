"""DesignDNA komut satırı arayüzü (CONTRACTS §6)."""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TaskProgressColumn
from rich.table import Table

from designdna import __version__
from designdna.cache import CacheStore, load_capture_file
from designdna.errors import CacheMissError, DesignDNAError
from designdna.models import BlendReport, RawCapture, SourceSpec
from designdna.sources import is_capture_file, parse_source, source_to_path

app = typer.Typer(
    name="designdna",
    help="Birden çok web sitesinin tasarım DNA'sını çıkarır ve ağırlıklı olarak harmanlar.",
    no_args_is_help=True,
    add_completion=False,
)

SourceOpt = typer.Option(
    ...,
    "--source",
    "-s",
    help='Kaynak: URL veya dosya yolu, isteğe bağlı ağırlıkla. Örn: "https://site.com@0.7"',
)
OutputOpt = typer.Option(Path("dist"), "--output", "-o", help="Çıktı klasörü.")
CacheOpt = typer.Option(
    None, "--cache-dir", help="Cache klasörü (varsayılan: ./.designdna/cache)."
)
RefreshOpt = typer.Option(False, "--refresh", help="Cache'i yok sayıp yeniden tara.")


def _console(stderr: bool = False) -> Console:
    return Console(stderr=stderr, highlight=False)


def _fail(message: str, code: int = 1) -> "typer.Exit":
    _console(stderr=True).print(f"[bold red]Hata:[/bold red] [red]{message}[/red]", soft_wrap=True)
    return typer.Exit(code=code)


def _guarded(func: Callable[[], None]) -> None:
    try:
        func()
    except typer.Exit:
        raise
    except DesignDNAError as exc:
        raise _fail(str(exc), exc.exit_code or 1) from exc
    except KeyboardInterrupt as exc:
        raise _fail("İşlem kullanıcı tarafından iptal edildi.", 130) from exc
    except Exception as exc:  # noqa: BLE001 - kullanıcıya anlaşılır mesaj
        raise _fail(
            f"Beklenmeyen bir hata oluştu ({type(exc).__name__}): {exc}", 1
        ) from exc


def _parse_all(sources: list[str]) -> list[SourceSpec]:
    return [parse_source(s) for s in sources]


def _resolve_weights(specs: list[SourceSpec]) -> list[float | None]:
    """Ağırlıksız kaynaklar, verilenlerin ortalamasını alır; hiçbiri verilmediyse hepsi None (eşit)."""
    given = [s.weight for s in specs if s.weight is not None]
    if not given:
        return [None] * len(specs)
    mean = sum(given) / len(given)
    return [s.weight if s.weight is not None else mean for s in specs]


def _check_local(specs: list[SourceSpec]) -> None:
    for spec in specs:
        path = source_to_path(spec)
        if path is not None and not path.is_file():
            raise DesignDNAError(f"Dosya bulunamadı: {path}")


def _extract(specs: list[SourceSpec], store: CacheStore, refresh: bool, console: Console) -> None:
    from designdna.extractor import dom_scanner  # tarayıcı modülü yalnızca extract'te yüklenir

    _check_local(specs)
    table = Table(title="Çıkarım özeti")
    table.add_column("Kaynak", overflow="fold")
    table.add_column("Durum")
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Kaynaklar taranıyor", total=len(specs))
        for spec in specs:
            progress.update(task, description=f"Taranıyor: {spec.location}")
            if is_capture_file(spec):
                status = "atlandı (hazır çıkarım .json)"
            elif not refresh and store.has(spec.location):
                status = "cache'ten"
            else:
                capture = dom_scanner.capture_source(spec.location)
                if capture.source != spec.location:
                    capture = capture.model_copy(update={"source": spec.location})
                store.save_capture(capture)
                status = "tarandı"
            table.add_row(spec.location, status)
            progress.advance(task)
    console.print(table)


def _load_captures(specs: list[SourceSpec], store: CacheStore) -> list[RawCapture]:
    captures: list[RawCapture] = []
    for spec in specs:
        if is_capture_file(spec):
            path = source_to_path(spec)
            assert path is not None
            captures.append(load_capture_file(path))
            continue
        capture = store.load_capture(spec.location)
        if capture is None:
            raise CacheMissError(
                f"{spec.location} için cache bulunamadı, önce `designdna extract` çalıştırın."
            )
        captures.append(capture)
    return captures


def _blend(specs: list[SourceSpec], store: CacheStore, output: Path, console: Console) -> None:
    # Bilinçli olarak tarayıcı modülleri import edilmez: blend yalnızca cache/JSON okur.
    from designdna.extractor.pipeline import build_site_extraction
    from designdna.generators import generate_all, write_blend_report
    from designdna.synthesizer.blender import blend

    captures = _load_captures(specs, store)
    weights = _resolve_weights(specs)
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Tasarım DNA'sı çıkarılıyor", total=len(captures) + 2)
        extractions = []
        for capture in captures:
            extractions.append(build_site_extraction(capture))
            progress.advance(task)
        progress.update(task, description="Harmanlanıyor")
        design_system, report = blend(extractions, weights)
        progress.advance(task)
        progress.update(task, description="Dosyalar yazılıyor")
        files = generate_all(design_system, output)
        files.append(write_blend_report(report, output))
        progress.advance(task)
    _print_summary(report, files, output, console)


def _print_summary(report: BlendReport, files: list[Path], output: Path, console: Console) -> None:
    sources = Table(title="Kaynaklar")
    sources.add_column("Kaynak", overflow="fold")
    sources.add_column("Girilen ağırlık", justify="right")
    sources.add_column("Normalize", justify="right")
    sources.add_column("Rol alabilir")
    for s in report.sources:
        given = "-" if s.input_weight is None else f"{s.input_weight:g}"
        sources.add_row(s.source, given, f"{s.normalized_weight:.2f}", "evet" if s.eligible else "hayır")
    console.print(sources)

    roles = Table(title="Roller")
    roles.add_column("Rol")
    roles.add_column("Kaynak", overflow="fold")
    roles.add_column("Gerekçe", overflow="fold")
    for r in report.roles:
        roles.add_row(r.role, r.source, r.reason)
    console.print(roles)

    if report.contrast_fixes:
        fixes = Table(title="Kontrast düzeltmeleri")
        for col in ("Tema", "Rol", "Karşı", "Önce", "Sonra", "Oran", "Hedef", "Sağlandı"):
            fixes.add_column(col)
        for f in report.contrast_fixes:
            fixes.add_row(
                f.theme, f.role, f.against, f.original, f.adjusted,
                f"{f.ratio_before:.2f} -> {f.ratio_after:.2f}", f"{f.target:g}",
                "evet" if f.achieved else "hayır",
            )
        console.print(fixes)
    else:
        console.print("Kontrast düzeltmesi gerekmedi.")

    console.print(f"Karşı tema: {'çıkarımdan' if report.counter_theme == 'captured' else 'türetildi'}")
    for warning in report.warnings:
        console.print(f"[yellow]Uyarı:[/yellow] {warning}", soft_wrap=True)
    console.print(f"[green]{len(files)} dosya yazıldı:[/green] {output}", soft_wrap=True)


def _setup() -> None:
    # Eski Windows konsollarında kodlama hatasını önle.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"designdna {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_cb, is_eager=True, help="Sürümü göster."
    ),
) -> None:
    """DesignDNA: web sitelerinden tasarım sistemi çıkarır ve harmanlar."""
    _setup()


@app.command()
def extract(
    source: list[str] = SourceOpt,
    refresh: bool = RefreshOpt,
    cache_dir: Optional[Path] = CacheOpt,
) -> None:
    """Kaynakların ham çıkarımını yapıp cache'e yazar."""

    def work() -> None:
        _extract(_parse_all(source), CacheStore(cache_dir), refresh, _console())

    _guarded(work)


@app.command()
def blend(
    source: list[str] = SourceOpt,
    output: Path = OutputOpt,
    cache_dir: Optional[Path] = CacheOpt,
) -> None:
    """Cache'teki (veya .json) çıkarımları harmanlayıp tasarım dosyalarını üretir."""

    def work() -> None:
        _blend(_parse_all(source), CacheStore(cache_dir), output, _console())

    _guarded(work)


@app.command()
def run(
    source: list[str] = SourceOpt,
    output: Path = OutputOpt,
    refresh: bool = RefreshOpt,
    cache_dir: Optional[Path] = CacheOpt,
) -> None:
    """extract + blend adımlarını art arda çalıştırır."""

    def work() -> None:
        specs = _parse_all(source)
        store = CacheStore(cache_dir)
        console = _console()
        _extract(specs, store, refresh, console)
        _blend(specs, store, output, console)

    _guarded(work)


@app.command()
def preview(
    directory: Path = typer.Argument(..., help="designdna çıktı klasörü."),
) -> None:
    """Çıktı klasöründeki preview.html dosyasını tarayıcıda açar."""

    def work() -> None:
        target = Path(directory) / "preview.html"
        if not target.is_file():
            raise DesignDNAError(
                f"preview.html bulunamadı: {target}. Önce `designdna blend` veya `designdna run` çalıştırın."
            )
        webbrowser.open(target.resolve().as_uri())
        _console().print(f"Önizleme açıldı: {target}", soft_wrap=True)

    _guarded(work)


if __name__ == "__main__":  # pragma: no cover
    app()
