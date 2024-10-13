For the following task, make plans that can solve the problem step by step. 
For each plan, indicate which external tool together with tool input to retrieve evidence. 
You can store the evidence into a variable #E that can be called by later tools. 
(Plan, #E1, Plan, #E2, Plan, ...)

Tools can be one of the following:
{{tools_desc}}

For example,
Task: Thomas, Toby, and Rebecca worked a total of 157 hours in one week. 
Thomas worked xhours. 
Toby worked 10 hours less than twice what Thomas worked, and Rebecca worked 8 hoursless than Toby. 
How many hours did Rebecca work?

Plan: Given Thomas worked x hours, translate the problem into algebraic expressions and solvewith Wolfram Alpha. 

#E1 = WolframAlpha({"prompt":"Solve x + (2x − 10) + ((2x − 10) − 8) = 157"})

Plan: Find out the number of hours Thomas worked. 
#E2 = LLM({"prompt": "What is x, given #E1"})

Plan: Calculate the number of hours Rebecca worked. 
#E3 = Calculator({"expr": "(2 ∗ #E2 − 10) − 8"})

Begin! 
Describe your plans with rich details. Each Plan should be followed by only one #E.

Task: {{task}}