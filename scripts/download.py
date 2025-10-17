from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm

# 确保安装了 requests 库: pip install requests


def download_file_with_path(url: str, output_dir: Path, filename: str | None = None):
    """
    使用 Path 对象从 URL 下载文件并保存到指定目录。

    Args:
        url (str): 要下载的文件的 URL。
        output_dir (Path): 文件保存的目标目录 (Path 对象)。
    """
    try:
        # 1. 从 URL 提取文件名
        # 使用 urlparse 来确保正确解析 URL 路径
        if filename is None:
            parsed_url = urlparse(url)
            # 获取路径的最后一部分作为文件名
            filename = Path(parsed_url.path).name

        if not filename:
            print(f"警告: 无法从 URL 提取文件名，跳过: {url}", file=sys.stderr)
            return

        # 2. 构造完整的保存路径
        save_path: Path = output_dir / filename

        # 3. 创建输出目录 (如果不存在)
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"开始下载: {url}")
        print(f"保存到: {save_path.resolve()}")  # resolve() 打印完整的绝对路径

        # 4. 执行下载
        # 使用 requests 库进行流式下载，处理大文件
        with requests.get(url, stream=True) as r:
            r.raise_for_status()  # 检查 HTTP 状态码，非 200 则抛出异常

            total_size = int(r.headers.get("content-length", 0))
            chunk_size = 8192  # 8KB

            # 5. 写入文件
            with save_path.open("wb") as f:
                downloaded_size = 0
                for chunk in tqdm(r.iter_content(chunk_size=chunk_size), total=total_size // chunk_size, unit="KB"):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 简单的进度显示
                        if total_size > 0:
                            percent = (downloaded_size / total_size) * 100
                            sys.stdout.write(
                                f"\r进度: {downloaded_size / (1024 * 1024):.2f}MB / {total_size / (1024 * 1024):.2f}MB ({percent:.2f}%)"
                            )
                            sys.stdout.flush()

            print(f"\n文件 '{filename}' 下载完成。")

    except requests.exceptions.RequestException as e:
        print(f"\n下载 '{url}' 失败: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\n处理 '{url}' 时发生错误: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="下载 Whisper 模型文件。")

    # 允许传入一个或多个 URL
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="要下载的文件的 URL 地址。",
    )

    # 允许用户指定输出目录，默认是当前脚本目录下的 'models' 文件夹
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "models",
        help='文件保存的目录。默认为当前目录下的 "models" 文件夹。',
    )
    # 允许用户指定文件名，默认使用 URL 中的文件名
    parser.add_argument(
        "--filename",
        type=str,
        default=None,
        help="指定保存的文件名。如果不指定，将使用 URL 中的文件名。",
    )

    args = parser.parse_args()

    # 遍历所有传入的 URL 并下载
    download_file_with_path(args.url, args.output_dir, args.filename)
