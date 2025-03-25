# Copyright (c) 2023 Chenyme

import subprocess
from pathlib import Path
import re
import torch
import base64
import pandas as pd
import platform
import os


def check_cuda_installed():
    if torch.cuda.is_available():
        return True
    else:
        return False


def parse_srt_file(srt_content: str) -> pd.DataFrame:
    """
    Parses SRT content string and converts it into a Pandas DataFrame.

    Args:
        srt_content: A string containing the SRT subtitle content.

    Returns:
        A Pandas DataFrame with columns '索引', '起始', '结束', and '字幕'.
    """
    lines = srt_content.strip().split("\n")
    subtitles: list[dict[str, str]] = []
    current_subtitle = {"索引": "", "起始": "", "结束": "", "字幕": ""}
    state = 0  # 0: Expect Index, 1: Expect Time, 2: Expect Text, 3: Expect Blank Line
    subtitle_text_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if state == 0:  # Expect Index
            if line.isdigit():
                current_subtitle["索引"] = line
                state = 1
        elif state == 1:  # Expect Time
            if "-->" in line:
                parts = line.split("-->")
                if len(parts) == 2:
                    current_subtitle["起始"] = parts[0].strip()
                    current_subtitle["结束"] = parts[1].strip()
                    state = 2
        elif state == 2:  # Expect Text
            if line:
                subtitle_text_lines.append(line)
            else:  # Blank line indicates end of subtitle entry
                current_subtitle["字幕"] = "\n".join(subtitle_text_lines)
                subtitles.append(current_subtitle.copy())  # Append a copy!
                current_subtitle = {
                    "索引": "",
                    "起始": "",
                    "结束": "",
                    "字幕": "",
                }  # Reset for next subtitle
                subtitle_text_lines = []
                state = 0  # Expect next index

    # Handle the last subtitle if the file doesn't end with a blank line
    if state == 2 and subtitle_text_lines:
        current_subtitle["字幕"] = "\n".join(subtitle_text_lines)
        subtitles.append(current_subtitle.copy())

    df = pd.DataFrame(subtitles)
    return df


def open_folder_in_explorer(folder_path: Path):
    """跨平台打开指定目录。"""
    if platform.system() == "Windows":
        try:
            os.startfile(str(folder_path))  # type: ignore
        except Exception as e:
            print(f"Windows 打开目录失败: {e}")
            return False
    elif platform.system() == "Darwin":  # macOS
        try:
            subprocess.run(
                ["open", str(folder_path)], check=True
            )  # macOS 使用 open 命令
        except subprocess.CalledProcessError as e:
            print(f"macOS 打开目录失败: {e}")
            return False
    elif platform.system() == "Linux":
        try:
            subprocess.run(
                ["xdg-open", str(folder_path)], check=True
            )  # Linux 优先使用 xdg-open
        except subprocess.CalledProcessError as e:
            print(f"Linux xdg-open 打开目录失败: {e}")
            try:
                subprocess.run(
                    ["gnome-open", str(folder_path)], check=True
                )  # 尝试 gnome-open
            except subprocess.CalledProcessError as e:
                print(f"Linux gnome-open 打开目录失败: {e}")
                try:
                    subprocess.run(
                        ["kde-open", str(folder_path)], check=True
                    )  # 尝试 kde-open
                except subprocess.CalledProcessError as e:
                    print(f"Linux kde-open 打开目录失败: {e}")
                    try:
                        subprocess.run(
                            ["nautilus", str(folder_path)], check=True
                        )  # 尝试 nautilus (GNOME 文件管理器)
                    except subprocess.CalledProcessError as e:
                        print(f"Linux nautilus 打开目录失败: {e}")
                        try:
                            subprocess.run(
                                ["dolphin", str(folder_path)], check=True
                            )  # 尝试 dolphin (KDE 文件管理器)
                        except subprocess.CalledProcessError as e:
                            print(f"Linux dolphin 打开目录失败: {e}")
                            try:
                                subprocess.run(
                                    ["thunar", str(folder_path)], check=True
                                )  # 尝试 thunar (XFCE 文件管理器)
                            except subprocess.CalledProcessError as e:
                                print(f"Linux thunar 打开目录失败: {e}")
                                return False  # Linux 多种尝试失败
    else:
        print(f"不支持的操作系统: {platform.system()}")
        return False
    return True  # 打开成功


# def srt_mv(
#     log, name, crf, quality, setting, path, font, font_size, font_color, subtitle_model
# ):  # 视频合成字幕
#     font_color = font_color.lstrip("#")  # 去掉 '#' 符号
#     bb = font_color[4:6]
#     gg = font_color[2:4]
#     rr = font_color[0:2]
#     font_color = f"&H{bb}{gg}{rr}&"
#     cuda_installed = check_cuda_installed()
#     cuda_supported = check_ffmpeg_hwaccel() if cuda_installed else False

#     if subtitle_model == "硬字幕":
#         if cuda_supported:
#             command = f"""ffmpeg -loglevel {log} -hwaccel cuda -i {name} -lavfi "subtitles=output.srt:force_style='FontName={font},FontSize={font_size},PrimaryColour={font_color},Outline=1,Shadow=0,BackColour=&H9C9C9C&,Bold=-1,Alignment=2'" -preset {quality} -c:v {setting} -crf {crf} -y -c:a copy output.mp4"""
#         else:
#             command = f"""ffmpeg -loglevel {log} -i {name} -lavfi "subtitles=output.srt:force_style='FontName={font},FontSize={font_size},PrimaryColour={font_color},Outline=1,Shadow=0,BackColour=&H9C9C9C&,Bold=-1,Alignment=2'" -preset {quality} -c:v libx264 -crf {crf} -y -c:a copy output.mp4"""
#     else:
#         if cuda_supported:
#             command = f"""ffmpeg -loglevel {log} -hwaccel cuda -i {name} -i output_with_style.srt -c:v {setting} -crf {crf} -y -c:a copy -c:s mov_text -preset {quality} output.mp4"""
#         else:
#             command = f"""ffmpeg -loglevel {log} -i {name} -i output_with_style.srt -c:v libx264 -crf {crf} -y -c:a copy -c:s mov_text -preset {quality} output.mp4"""

#     subprocess.run(command, shell=True, cwd=path)


def show_video(path, name):
    video_file = open(path + "/" + name, "rb")
    video_bytes = video_file.read()
    return video_bytes


def srt_to_vtt(srt_content):

    blocks = srt_content.strip().split("\n\n")
    vtt_lines = ["WEBVTT\n"]

    for block in blocks:
        lines = block.strip().split("\n")

        if len(lines) >= 2:
            time_range = lines[1].replace(",", ".")
            text = "\n".join(lines[2:])
            vtt_lines.append(f"{time_range}\n{text}\n")
    vtt_content = "\n".join(vtt_lines)

    return vtt_content


def srt_to_ass(srt_content, fontname="Arial", size=20, color="&H00FFFFFF"):

    lines = srt_content.strip().split("\n\n")
    ass_header = (
        "[Script Info]\n"
        "Title: Converted from SRT\n"
        "ScriptType: v4.00+\n"
        "Collisions: Normal\n"
        "PlayDepth: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{fontname},{size},{color},&H000000FF,&H00000000,-1,0,0,1,1.0,0.0,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ass_content = ass_header

    for line in lines:
        parts = line.strip().split("\n")
        start, end = parts[1].split(" --> ")
        start = start.replace(",", ".")
        end = end.replace(",", ".")
        text = "\\N".join(parts[2:])
        ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"

    return ass_content


def srt_to_sbv(srt_content):

    lines = srt_content.strip().split("\n\n")
    sbv_content = ""

    for block in lines:
        parts = block.strip().split("\n")
        start, end = parts[1].split(" --> ")
        start = convert_srt_time_to_sbv(start)
        end = convert_srt_time_to_sbv(end)
        text = "\n".join(parts[2:])
        sbv_content += f"{start},{end}\n{text}\n\n"

    return sbv_content


def convert_srt_time_to_sbv(time_str):

    hours, minutes, seconds = time_str.split(":")
    seconds, milliseconds = seconds.split(",")
    milliseconds = int(milliseconds) / 10
    sbv_time = f"{hours}:{minutes}:{seconds}.{int(milliseconds):02d}"

    return sbv_time


def read_srt_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        srt = file.read().split("\n\n")
        timestamp_pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})"
        )
        subtitles = []

        for block in srt:
            lines = block.split("\n")
            if len(lines) >= 3:
                num = lines[0]
                times = lines[1]
                text = "\n".join(lines[2:])

                if timestamp_pattern.match(times):
                    subtitles.append({"number": num, "time": times, "text": text})
    return subtitles


# def extract_frames(video_path, output_dir, time_interval=1):
#     if not os.path.exists(output_dir):
#         os.makedirs(output_dir)

#     video = cv2.VideoCapture(video_path)
#     if not video.isOpened():
#         print(
#             f"\033[1;31m❌ 无法读取视频关键帧，请检查此目录是否存在:\033[0m\033[1;34m {video_path} \033[0m"
#         )
#         st.toast("无法读取视频关键帧", icon=":material/release_alert:")
#         st.stop()

#     timestamp = 0
#     while True:
#         ret, frame = video.read()
#         if not ret:
#             break

#         current_timestamp = video.get(cv2.CAP_PROP_POS_MSEC) / 1000
#         if current_timestamp >= timestamp + time_interval:
#             timestamp = current_timestamp
#             frame_filename = os.path.join(output_dir, f"frame_{int(timestamp)}.png")
#             cv2.imwrite(frame_filename, frame)
#     video.release()


def encode_image(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
