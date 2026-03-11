import{_ as a,o as n,c as p,ag as e}from"./chunks/framework.ePeAWSvT.js";const h=JSON.parse('{"title":"System Prompt 分层架构","description":"","frontmatter":{},"headers":[],"relativePath":"guide/architecture/system-prompt-layers.md","filePath":"guide/architecture/system-prompt-layers.md"}'),l={name:"guide/architecture/system-prompt-layers.md"};function t(i,s,o,r,c,d){return n(),p("div",null,[...s[0]||(s[0]=[e(`<h1 id="system-prompt-分层架构" tabindex="-1">System Prompt 分层架构 <a class="header-anchor" href="#system-prompt-分层架构" aria-label="Permalink to &quot;System Prompt 分层架构&quot;">​</a></h1><blockquote><p>描述 <code>src/lab</code> 中 system prompt 的分层组织方式。 关联：#262（Tool/Skill/Plugin 共存架构）、#278（Profile 配置系统）、#281（Plugin 系统）</p></blockquote><h2 id="设计原则" tabindex="-1">设计原则 <a class="header-anchor" href="#设计原则" aria-label="Permalink to &quot;设计原则&quot;">​</a></h2><ol><li><strong>分层</strong> — 每层职责单一，不混杂</li><li><strong>可组合</strong> — 通过 Profile 配置选择加载哪些层</li><li><strong>可切换</strong> — 同一层可以有多个实现（不同角色、不同输出格式）</li><li><strong>自动生成优先</strong> — 工具说明由运行时生成，不手写</li><li><strong>Context 不污染 System</strong> — 动态上下文注入 user prompt，避免幻觉</li></ol><h2 id="五层模型" tabindex="-1">五层模型 <a class="header-anchor" href="#五层模型" aria-label="Permalink to &quot;五层模型&quot;">​</a></h2><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>System Prompt（启动时拼接，固定不变）</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>├── Layer 1: Persona（角色核心）         [固定，启动时加载]</span></span>
<span class="line"><span>│   &quot;你是谁、性格怎样、说话风格&quot;</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>├── Layer 2: Format（输出格式）          [固定，启动时加载]</span></span>
<span class="line"><span>│   &quot;回复的结构化格式要求&quot;</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>├── Layer 3: Skills（技能目录）          [固定，启动时注入 description+路径]</span></span>
<span class="line"><span>│   &quot;你有哪些技能、它们在哪里&quot;</span></span>
<span class="line"><span>│   └── 只注入一句话描述 + 文件路径，不展开内容</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>└── Layer 4: Tools（工具说明）           [运行时自动生成]</span></span>
<span class="line"><span>    &quot;可用工具的 schema 和使用时机&quot;</span></span>
<span class="line"><span>    └── ToolManager.build_system_prompt() 自动生成</span></span>
<span class="line"><span></span></span>
<span class="line"><span>─────────────────────────────────────────────────────────</span></span>
<span class="line"><span>User Prompt（每轮请求动态注入）</span></span>
<span class="line"><span></span></span>
<span class="line"><span>└── Layer 5: Context（动态上下文）       [每次请求，注入 user prompt]</span></span>
<span class="line"><span>    &quot;记忆召回结果、日记摘要&quot;</span></span>
<span class="line"><span>    └── 标签块格式：[memory context]...[/memory context]</span></span></code></pre></div><h2 id="各层详解" tabindex="-1">各层详解 <a class="header-anchor" href="#各层详解" aria-label="Permalink to &quot;各层详解&quot;">​</a></h2><h3 id="layer-1-persona" tabindex="-1">Layer 1: Persona <a class="header-anchor" href="#layer-1-persona" aria-label="Permalink to &quot;Layer 1: Persona&quot;">​</a></h3><p>角色核心身份。一个文件定义一个角色，Profile 指定加载哪个。</p><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>prompts/characters/</span></span>
<span class="line"><span>├── satone.md       # Satone（さとね）— 写小说的女孩</span></span>
<span class="line"><span>├── elaina.txt      # 伊蕾娜 — 灰之魔女（VTuber 管线使用）</span></span>
<span class="line"><span>└── ...</span></span></code></pre></div><ul><li>纯文本，描述&quot;谁是谁&quot;，不涉及&quot;怎么输出&quot;</li><li>一个 session 只加载一个 persona</li><li>全量注入，是 system prompt 权重最高的部分</li></ul><h3 id="layer-2-format" tabindex="-1">Layer 2: Format <a class="header-anchor" href="#layer-2-format" aria-label="Permalink to &quot;Layer 2: Format&quot;">​</a></h3><p>输出格式约束。不同前端需要不同格式。</p><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>prompts/formats/</span></span>
<span class="line"><span>├── emotion_pipe.md         # AIChat 格式：[Emotion] ||| TEXT</span></span>
<span class="line"><span>├── emotion_bracket.md      # VTuber 格式：[expression] 内联在文本中</span></span>
<span class="line"><span>├── plain.md                # 纯文本（无 emotion tag）</span></span>
<span class="line"><span>└── ...</span></span></code></pre></div><ul><li>约束回复的结构，不约束内容</li><li>全量注入</li></ul><p><strong>emotion_pipe.md 示例：</strong></p><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>【回复格式】</span></span>
<span class="line"><span>你必须严格按照以下格式回复：</span></span>
<span class="line"><span>[Emotion] ||| TEXT</span></span>
<span class="line"><span></span></span>
<span class="line"><span>可用情感：[Happy] [Sad] [Think] [Wave] ...</span></span></code></pre></div><h3 id="layer-3-skills-懒加载" tabindex="-1">Layer 3: Skills（懒加载） <a class="header-anchor" href="#layer-3-skills-懒加载" aria-label="Permalink to &quot;Layer 3: Skills（懒加载）&quot;">​</a></h3><p>技能是 AI 的行为策略和知识。<strong>System prompt 只注入描述和路径，不展开内容。</strong></p><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>System Prompt 里注入的内容示例：</span></span>
<span class="line"><span>你有以下技能可按需调用：</span></span>
<span class="line"><span>- diary_writing: 日记写作风格与结构指南 → prompts/skills/diary_writing.md</span></span>
<span class="line"><span>- file_navigation: 在复杂目录中定位文件的策略 → prompts/skills/file_navigation.md</span></span>
<span class="line"><span>需要时读取对应文件获取详细指引。</span></span></code></pre></div><p><strong>为什么懒加载？</strong></p><p>把所有技能文件全量展开注入 system prompt 会导致：</p><ul><li>Persona / Format 等核心信息权重被稀释</li><li>System prompt 膨胀，成本上升</li><li>LLM 注意力分散</li></ul><p>懒加载让 LLM 按需读取，在 token 预算有限时优先保证核心身份正确。</p><p>技能文件存放在 <code>src/lab/plugins/</code> 下，每个 skill plugin 的 <code>plugin.toml</code> 里的 <code>description</code> 字段就是注入 system prompt 的那一句话。</p><h3 id="layer-4-tools" tabindex="-1">Layer 4: Tools <a class="header-anchor" href="#layer-4-tools" aria-label="Permalink to &quot;Layer 4: Tools&quot;">​</a></h3><p>由 <code>ToolManager.build_system_prompt()</code> 运行时自动生成，不手写。</p><p>工具注册到 ToolManager 后，<code>schema</code> 和 <code>usage_hint</code> 自动拼接成工具说明段。</p><h3 id="layer-5-context-注入-user-prompt" tabindex="-1">Layer 5: Context（注入 user prompt） <a class="header-anchor" href="#layer-5-context-注入-user-prompt" aria-label="Permalink to &quot;Layer 5: Context（注入 user prompt）&quot;">​</a></h3><p>每次请求动态生成，<strong>注入 user prompt，不进 system prompt</strong>。</p><p><strong>为什么不进 system prompt？</strong></p><p>System prompt 有&quot;永久性&quot;语义，LLM 会把里面的信息当成不变的事实。把记忆注入 system prompt 会导致：</p><ul><li>过期记忆被当成当前事实，产生幻觉</li><li>System prompt 随每轮对话膨胀</li></ul><p>注入 user prompt 的语义是&quot;这是本轮的新信息&quot;，更准确，也方便多轮更新。</p><p><strong>格式（标签块）：</strong></p><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>[memory context]</span></span>
<span class="line"><span>今天和聪音聊了关于天气的话题...</span></span>
<span class="line"><span>上次提到想去图书馆...</span></span>
<span class="line"><span>[/memory context]</span></span>
<span class="line"><span></span></span>
<span class="line"><span>[diary context]</span></span>
<span class="line"><span>3月11日日记摘要：今天阳光很好...</span></span>
<span class="line"><span>[/diary context]</span></span>
<span class="line"><span></span></span>
<span class="line"><span>（正文）用户发的消息</span></span></code></pre></div><p>哪些 context 块被注入由 Profile 的 <code>[context]</code> 配置决定：</p><div class="language-toml vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">toml</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">[</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;">context</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">]</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">memory_search = </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">true</span><span style="--shiki-light:#6A737D;--shiki-dark:#6A737D;">   # 注入 [memory context]</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">diary_summary = </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">false</span><span style="--shiki-light:#6A737D;--shiki-dark:#6A737D;">  # 不注入 [diary context]</span></span></code></pre></div><hr><h2 id="拼接实现" tabindex="-1">拼接实现 <a class="header-anchor" href="#拼接实现" aria-label="Permalink to &quot;拼接实现&quot;">​</a></h2><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>Profile.from_toml(&quot;profiles/songyin.toml&quot;)</span></span>
<span class="line"><span>    ↓</span></span>
<span class="line"><span>PluginLoader.load_many(profile.plugins.enabled)</span></span>
<span class="line"><span>    → tool_plugins, skill_descriptors</span></span>
<span class="line"><span>    ↓</span></span>
<span class="line"><span>SystemPromptBuilder.build(</span></span>
<span class="line"><span>    persona_path  = profile.prompt.persona,    # Layer 1</span></span>
<span class="line"><span>    format_path   = profile.prompt.format,     # Layer 2</span></span>
<span class="line"><span>    skills        = skill_descriptors,         # Layer 3（只注入 description+路径）</span></span>
<span class="line"><span>    tool_manager  = tool_manager,              # Layer 4（自动生成）</span></span>
<span class="line"><span>)</span></span>
<span class="line"><span>    ↓</span></span>
<span class="line"><span>ContextInjector.build_context_prompt(</span></span>
<span class="line"><span>    memory_context = &quot;...&quot;,   # Layer 5（注入 user prompt）</span></span>
<span class="line"><span>    diary_context  = &quot;...&quot;,</span></span>
<span class="line"><span>)</span></span></code></pre></div><p>核心类：</p><ul><li><code>src/lab/profile/system_prompt_builder.py</code> — 拼接 Layer 1-4</li><li><code>src/lab/profile/context_injector.py</code> — 生成 Layer 5 标签块</li><li><code>src/lab/profile/schema.py</code> — Profile / ContextConfig Pydantic model</li></ul><hr><h2 id="与-profile-系统的关系" tabindex="-1">与 Profile 系统的关系 <a class="header-anchor" href="#与-profile-系统的关系" aria-label="Permalink to &quot;与 Profile 系统的关系&quot;">​</a></h2><p>Profile 是驱动五层架构的配置文件，决定：</p><ul><li>加载哪个 persona / format（Layer 1/2）</li><li>启用哪些 plugin（tool plugin → Layer 4，skill plugin → Layer 3）</li><li>开启哪些 context 注入（Layer 5）</li></ul><p>详见 <a href="./profile-system.html">Profile 系统</a>。</p>`,48)])])}const u=a(l,[["render",t]]);export{h as __pageData,u as default};
