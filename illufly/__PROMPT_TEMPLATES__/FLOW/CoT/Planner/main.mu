尽你所能解决问题和完成任务。

**你要解决的问题是: ** {{{task}}}

{{#completed_work}}

{{{completed_work}}}
{{/completed_work}}

(现在不要急于解决问题，而是继续按照如下步骤一步一步输出你的推理过程。)

**思考** 
对当前情况进行反思, 然后说明你现在的决策：当前就结束任务并输出包含`<final_answer>`标签的**最终答案**，还是继续考虑下一步行动的应当如何执行。

在你反思的过程中，请基于给定的事实思考，从如下几个方面进行反思：
 1. 任务中是否包含关键概念: 任务中涉及的组合型概念或实体。已经明确获得取值的关键概念，将其取值完整备注在概念后。
 2. 将任务中的关键概念拆解为一系列待查询的子要素：每个关键概念一行，后接这个概念的子要素，每个子要素一行，行前以' -'开始。
 3. 观察以前的执行记录：思考概念拆解是否完整、准确？每个关键概念或要素的查询都得到了准确的结果？从当前的信息中还不能得到哪些要素/概念？

**最终答案**
<final_answer>
(在此输出你的最终答案)
</final_answer>
如果输出最终答案，就结束任务，停止所有输出。

**行动** 
请你在缜密思考下直接输出当前步骤问题的详细过程。

...你必须按照 **思考-行动-观察** 的循环过程输出，可以重复N次，直到结束。
