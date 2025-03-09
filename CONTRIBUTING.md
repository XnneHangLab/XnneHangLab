# 如何快速参与开发 (`・ω・´) ~

非常高兴你能参与到我们的项目中来，我们欢迎任何形式的贡献，包括但不限于提交问题、修复代码、改进文档等等。<br>

如果是希望的改进方向以及 bug，直接提到 issue 中即可。<br>

这里主要讲一下我们的开发流程，以及如何快速参与开发。<br>

# 工作流以及需要的工具。

## pre-commit:

我们使用 `pre-commit` 进行代码风格检查，以及一些代码规范检查。<br>

主要使用了 black 用于格式化，ruff 用于检查代码规范, typos 用于检查拼写。<br>

快速安装:<br>

```shell
pip install pre-commit
pre-commit install
```

这样你在 git 提交的时候会自动运行检查。<br>

或者可以对已经提交的代码进行检查:<br>

```shell
pre-commit run --all-files
```

## uv:

这是本地构建项目非常快速的工具，因为有了它你就不必自己配置环境了。并且也能够和我保持一致的环境。<br>

安装:<br>

mac&linux:<br>

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

windows:<br>

```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

详细参见:<br>

[install uv](https://docs.astral.sh/uv/getting-started/installation/)<br>


当你有了 uv , 你可以这样运行项目:<br>

```shell
git clone https://github.com/MrXnneHang/Auto-Caption-Generate-Offline@你要开发的分支
cd Auto-Caption-Generate-Offline
uv run acgo -i test.wav -o test.srt
```

之后你可以直接修改代码，运行然后进行测试。<br>

当你实现了你想要的功能或者修复了 bug 之后，你可以提交 PR 到我们的仓库。<br>

非常感谢你的参与~ (`・ω・´) ~<br>

另外也非常欢迎你提供建议让我改进工作流。<br>

比如，我现在就不会写 github ci test.<br>