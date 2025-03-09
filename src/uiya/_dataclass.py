from pathlib import Path
from dataclasses import dataclass
from uiya.utils.config import load_config


@dataclass
class ConfigParser:
    config = load_config()

    batch_size_s: int = int(config["batch_size_s"])
    max_workers: int = int(config["max_workers"])
    device: str = str(config["device"])

    need_punc: bool = bool(config["need_punc"])

    cut_line: int = int(config["cut_line"])
    cut: bool = bool(config["cut"])

    max_sentence_length: int = int(config["max_sentence_length"])
    combine_line: int = int(config["combine_line"])
    combine: bool = bool(config["combine"])

    punctuation_list: str = str(config["punctuation_list"])

    base_model: Path = Path(str(config["base_model"]))
    vad_model: Path = Path(str(config["vad_model"]))
    punc_model: Path = Path(str(config["punc_model"]))
    hot_words_path: Path = Path(str(config["hot_words_path"]))
    FFMPEG_PATH: Path = Path(str(config["FFMPEG_PATH"]))

    def __post_init__(self):
        if not self.base_model.exists():
            raise FileNotFoundError(f"{self.base_model} not found")
        if not self.vad_model.exists():
            raise FileNotFoundError(f"{self.vad_model} not found")
        if not self.punc_model.exists():
            raise FileNotFoundError(f"{self.punc_model} not found")
        if not self.hot_words_path.exists():
            # 创建空文件
            self.hot_words_path.touch()
            # TODO, 加上 Logger 告知用户没有检测到热词文件
        if not self.FFMPEG_PATH.exists():
            raise FileNotFoundError(f"{self.FFMPEG_PATH} not found")
