from dataclasses import dataclass
from uiya.utils.config import load_config


@dataclass
class ConfigParser:
    config = load_config()

    batch_size_s: int = int(config["batch_size_s"])
    cut_line: int = int(config["cut_line"])
    combine_line: int = int(config["combine_line"])
    punctuation_list: str = str(config["punctuation_list"])
    base_model: str = str(config["base_model"])
    vad_model: str = str(config["vad_model"])
    punc_model: str = str(config["punc_model"])
    device: str = str(config["device"])
    FFMPEG_PATH: str = str(config["FFMPEG_PATH"])
    max_workers: int = int(config["max_workers"])
    need_punc: bool = bool(config["need_punc"])
    max_sentence_length: int = int(config["max_sentence_length"])
