## prompt 结构重构 ing...

character setting 里存放的是那些大概率只出现一次不会复用的 system prompt，不同角色不同 prompt。 虽然角色模版的方式也很不错，但是要细分很多层，我这里暂时 focus on elaina 为了省点脑力所以就搞太复杂。如果你喜欢一个角色，你应该愿意为她从头到尾写一个设定。

而 tools 里可能是一些用以引导模型回答的，或者与长期记忆和 MCP prompt 相关的功能。主要以 user prompt 出现，可能反复出现，不同角色同一逻辑。