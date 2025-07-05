# 构建中可能碰到的问题:


## windows langsegment 构建失败

```shell
    import LangSegment
  File "D:\tmp\XnneHangLab\.venv\Lib\site-packages\LangSegment\__init__.py", line 1, in <module>
    from .LangSegment import LangSegment,getTexts,classify,getCounts,printList,setLangfilters,getLangfilters,setfilters,getfilters
ImportError: cannot import name 'setLangfilters' from 'LangSegment.LangSegment' (D:\tmp\XnneHangLab\.venv\Lib\site-packages\LangSegment\LangSegment.py)
```

原因参见: https://github.com/megaease/easevoice-trainer/issues/2

通过安装 dist 下的 whl 包解决, 我已经把 source 改为它了，所以应该不会再出现。

## nltk_data 需要额外下载。


```shell
LookupError:
**********************************************************************
  Resource averaged_perceptron_tagger_eng not found.
  Please use the NLTK Downloader to obtain the resource:

  >>> import nltk
  >>> nltk.download('averaged_perceptron_tagger_eng')

  For more information see: https://www.nltk.org/data.html

  Attempted to load taggers/averaged_perceptron_tagger_eng/

  Searched in:
    - 'C:\\Users\\zhouyuan/nltk_data'
    - 'D:\\tmp\\XnneHangLab\\.venv\\nltk_data'
    - 'D:\\tmp\\XnneHangLab\\.venv\\share\\nltk_data'
    - 'D:\\tmp\\XnneHangLab\\.venv\\lib\\nltk_data'
    - 'C:\\Users\\zhouyuan\\AppData\\Roaming\\nltk_data'
    - 'C:\\nltk_data'
    - 'D:\\nltk_data'
    - 'E:\\nltk_data'
**********************************************************************
```

按照说明运行即可解决。

你也可以运行 just install-nltk 来下载。


## 网络问题：

第一次运行请保证对 github 的终端可连接。因为会自动下载这个文件: `downloading: "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz"`