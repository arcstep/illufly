这是总体任务的一部份，根据最新进展，已经制定了需要继续执行的计划清单：
{{{plan_todo}}}

你只需要根据上述清单，执行清单中的第一个步骤，剩余步骤无需执行。

你可以从 {{tools_name}} 中选择一个或多个工具使用。这些工具的详细描述为：

{{{tools_desc}}}

然后请按如下格式输出详细的执行计划，其中n是:
Step{n}: (子任务描述) #E{n} = function_name[kwargs_with_json]

例如：
Step1: 查看天气状况. #E1 = get_weather[{"city": "北京"}]
