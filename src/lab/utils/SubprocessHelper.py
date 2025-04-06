from __future__ import annotations

import logging
import subprocess


def run_shell_command(
    command: list[str],
    log_level_stdout: int = logging.DEBUG,
    log_level_stderr: int = logging.WARNING,
    logger_name: str = "",
    check_returncode: bool = False,
):
    """
    运行 shell 命令并记录输出，可以控制日志级别和是否检查返回码。

    参数:
        command (list[str]): 要运行的命令。
        log_level_stdout (int): 标准输出的日志级别，默认为 DEBUG。
        log_level_stderr (int): 标准错误的日志级别，默认为 WARNING。
        check_returncode (bool): 是否检查返回码，如果为 True 且返回码非零，则抛出异常。 默认为 False。

    返回:
        subprocess.CompletedProcess: 包含命令执行结果的对象。

    抛出:
        subprocess.CalledProcessError: 如果 check_returncode=True 且命令返回非零返回码。
    """
    command_str = " ".join(command)
    if logger_name:
        logger = logging.getLogger(logger_name + " - " + __name__)
    else:
        logger = logging.getLogger(__name__)

    logger.debug(f"执行命令: {command_str}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check_returncode,  # 根据参数决定是否检查返回码
        )

        if result.stdout:
            logger.log(log_level_stdout, result.stdout)  # 使用可配置的日志级别
        if result.stderr:
            logger.log(log_level_stderr, result.stderr)  # 使用可配置的日志级别

        return result

    except FileNotFoundError as e:
        logger.error(f"命令未找到错误: {e}")
        return subprocess.CompletedProcess(args=command, returncode=-1, stdout="", stderr=str(e))
    except subprocess.CalledProcessError as e:  # 只在 check_returncode=True 时可能抛出
        logger.error(f"子进程调用错误: {e}")
        logger.error(f"错误输出:\n{e.stderr}")
        raise e  # 重新抛出异常，让调用者处理
    except Exception as e:
        logger.exception(f"发生未知错误: {e}")
        return subprocess.CompletedProcess(args=command, returncode=-1, stdout="", stderr=str(e))
