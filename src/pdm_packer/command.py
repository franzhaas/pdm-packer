import argparse
import importlib.resources
import io
import os
import stat
import zipapp
from pathlib import Path

from pdm import BaseCommand, Project, termui
from pdm.models.in_process import get_architecture
from pip._vendor.pkg_resources import to_filename

from .env import PackEnvironment


class PackCommand(BaseCommand):
    """Pack the packages into a zipapp"""

    name = "pack"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-m", "--main", help="Specify the console script entry point for the zipapp"
        )
        parser.add_argument(
            "-o",
            "--output",
            help="Specify the output filename, default: the project name",
            type=Path,
        )
        parser.add_argument(
            "-c",
            "--compress",
            action="store_true",
            help="Compress files with the deflate method, no compress by default",
        )
        parser.add_argument(
            "-i",
            "--interpreter",
            help="The Python interpreter path, default: the project interpreter",
        )
        parser.add_argument(
            "--exe",
            action="store_true",
            help="Create an executable file. If the output file isn't given, "
            "the file name will end with .exe(Windows) or no suffix(Posix)",
        )

    @staticmethod
    def _write_zipapp(
        stream: io.BytesIO, project: Project, options: argparse.Namespace
    ) -> Path:
        bytes = stream.getvalue()
        if options.exe and (
            os.name == "nt" or (os.name == "java" and os._name == "nt")
        ):
            interpreter = options.interpreter or project.python.executable
            arch = get_architecture(interpreter)
            bits = "32" if "32bit" in arch else "64"
            kind = "w" if "pythonw" in Path(interpreter).name else "t"
            launcher = importlib.resources.read_binary("distlib", f"{kind}{bits}.exe")
            bytes = launcher + bytes

        if options.output:
            output = options.output
        else:
            name = project.meta.name or project.root.name
            name = to_filename(name)
            suffix = ".pyz" if not options.exe else ".exe" if os.name == "nt" else ""
            output = Path(name + suffix)

        output.write_bytes(bytes)
        if options.exe:
            output.chmod(output.stat().st_mode | stat.S_IEXEC)
        return output

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        def file_filter(name: str) -> bool:
            first = Path(name).parts[0]
            last = Path(name).name
            return not (
                first.endswith(".dist-info")
                or first.endswith(".egg")
                or last.endswith(".egg-link")
                or last.endswith(".pyc")
            )

        main = None
        if options.main:
            main = options.main
        else:
            scripts = project.meta.get("scripts", {})
            if scripts:
                main = str(scripts[next(iter(scripts))])

        target_stream = io.BytesIO()

        with PackEnvironment(project) as pack_env:
            project.core.ui.echo("Packing packages...")
            lib = pack_env.prepare_lib_for_pack()
            project.core.ui.echo(f"Packages are prepared at {lib}")
            project.core.ui.echo("Creating zipapp...")
            zipapp.create_archive(
                lib,
                target_stream,
                interpreter=options.interpreter or project.python.executable,
                main=main,
                compressed=options.compress,
                filter=file_filter,
            )
            output = self._write_zipapp(target_stream, project, options)
            project.core.ui.echo(f"Zipapp is generated at {termui.green(output)}")
