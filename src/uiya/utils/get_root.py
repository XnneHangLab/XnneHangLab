from uiya._dataclass import RootAbsDir
from uiya.utils.config import load_settings_file, write_settings_file
from pathlib import Path


def main():
    ROOT_DIR = Path(__file__).parent.parent.parent.parent
    settings = load_settings_file("root.toml", RootAbsDir)
    settings.root_dir = str(ROOT_DIR)
    write_settings_file("root.toml", settings)
