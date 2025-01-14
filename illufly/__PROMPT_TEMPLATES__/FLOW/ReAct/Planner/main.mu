{{! 这是一个基于「Plans 语法」行动解析的 ReAct 提示语模板 }}
尽你所能解决问题和完成任务。

你可以从 ** {{tools_name}} ** 中选择一个工具来解决问题，这些工具的详细描述如下:
{{{tools_desc}}}

**你要解决的问题是: ** {{{task}}}

{{#completed_work}}

{{{completed_work}}}
{{/completed_work}}

(现在不要急于解决问题，而是继续按照如下步骤一步一步输出你的推理过程。)

**思考** 
对当前情况进行反思, 然后说明你现在的决策：当前就结束任务并输出包含`<final_answer>`标签的**最终答案**，还是继续考虑下一步行动的应当如何执行。
如果你认为问题模糊或思考过程陷入循环，请直接输出最终答案为：问题模糊，无法解决问题。

在你反思的过程中，请基于给定的事实思考，从如下几个方面进行反思：
 1. 如果概念和子任务清晰，就针对问题将其拆解为合理的思考步骤，并输出你的思考过程。
 2. 任务中是否包含关键概念: 任务中涉及的组合型概念或实体。已经明确获得取值的关键概念，将其取值完整备注在概念后。
 3. 将任务中的关键概念拆解为一系列待查询的子要素：每个关键概念一行，后接这个概念的子要素，每个子要素一行，行前以' -'开始。
 4. 观察以前的执行记录：思考概念拆解是否完整、准确？每个关键概念或要素的查询都得到了准确的结果？从当前的信息中还不能得到哪些要素/概念？
 5. 在反思过程中，如果要使用工具解决问题，请严格核对可用的工具列表，并严格按照工具的参数格式调用。
 6. 你不可以为了完成任务而给出假设性、演示性的工具回调提示，这将导致任务失败。
 7. 如果反思过程任务，你因为没有工具可用而无法解决问题，请直接输出最终答案为：缺少工具，无法解决问题。
 8. **观察**中的「上述行动结果」部份不能为空，否则就说明上一步工具回调执行失败，此时你应当重新审视工具是否存在或是参数调用是否错误。

**最终答案**
<final_answer>
(在此输出你的最终答案)
</final_answer>

如果输出最终答案，就结束任务，停止所有输出。

**行动** 
如果你没有任何工具可用或者没有合适工具可用，又或者你认为不需要使用工具，就可以尝试直接输出解决问题的详细过程；
否则，请你按如下格式整理行动的详细工具调用的计划，其中 #E{n} 时用于保存计划执行后的变量名，n 是子任务的序号:
Step{n}: (子任务描述) #E{n} = function_name[kwargs_with_json]

例如：
Step1: 查看天气状况. #E1 = get_weather[{"city": "北京"}]

...你必须按照 **思考-行动-观察** 的循环过程输出，可以重复N次，直到结束。
