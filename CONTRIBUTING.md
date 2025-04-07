## 如何快速参与开发 (`・ω・´) ~

非常高兴你能参与到我们的项目中来，我们欢迎任何形式的贡献，包括但不限于提交问题、修复代码、改进文档等等。<br>

如果是希望的改进方向以及 bug，直接提到 issue 中即可。<br>

这里主要讲一下我们的开发流程，以及如何快速参与开发。<br>

## 工作流以及需要的工具。

### just

[just](https://github.com/casey/just) 是一款用 rust 编写的简单易用的命令执行工具，通过它可以方便地执行一些开发时常用的命令。安装方法请参考[它的文档](https://github.com/casey/just#installation)

> 替代方案（不方便安装或者 Windows 上无法运行这些命令时建议使用）：自行查看 justfile 中对应的详细命令。

### 项目管理工具 uv

[uv](https://docs.astral.sh/uv/) 是 yutto 用来进行项目管理的工具，你可以从[安装指南](https://docs.astral.sh/uv/getting-started/installation/)找到合适的安装方式～

## 如何使用

运行代码：

```shell
git clone https://github.com/XnneHangLab/XnneHangLab.git
cd XnneHangLab
git submodule update --init --recursive
just start
```

然后你可以修改代码来实现你想要的功能，或者修复 bug。

最后你只需要在你 commit 之前对你的代码进行检查和格式化:

```shell
just fmt
just lint
just test
```

之后就可以直接向我提交 PR 啦～
