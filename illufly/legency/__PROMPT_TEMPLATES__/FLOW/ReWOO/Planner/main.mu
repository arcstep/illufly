尽你所能解决问题和完成任务。
请基于给定的事实和工具规划任务，不要额外发挥。

**你要解决的问题是: ** {{{task}}}

你可以制定可以逐步解决问题的计划。
对于每个计划，指明使用哪个外部工具以及工具输入来获取证据。

工具可以是以下之一：
{{{tools_desc}}}

你可以将具体计划的执行结果存储在一个变量 #E{n} 中，后续工具可以调用该变量。
(Step1, #E1, Step2, #E2, Step3, ...)

其中 #E{n} 用于保存计划执行后的变量名，n 是子任务的序号，格式为:
Step{n}: (子任务描述) #E{n} = function_name[kwargs_with_json]

例如：
Step1: 假设 Thomas 工作了 x 小时，将问题转化为代数表达式并使用 Wolfram Alpha 解决。#E1 = WolframAlpha[{"prompt":"Solve x + (2x − 10) + ((2x − 10) − 8) = 157"}]
Step2: 找出 Thomas 工作的小时数。#E2 = LLM[{"prompt": "What is x, given #E1"}]
Step3: 计算 Rebecca 工作的小时数。#E3 = Calculator[{"expr": "(2 ∗ #E2 − 10) − 8"}]

开始！
详细描述你的步骤。每个步骤后面应只跟一个 #E{n}。
