from statemachine import StateMachine, State

class ContentState(StateMachine):
    """实现基于有限状态机的内容管理"""

    # 定义有限状态机的状态
    #
    # 初始化扩写指南
    init = State("init", initial=True)
    # 已有扩写指南，生成内容结果
    todo = State("todo")
    # 已生成内容结果
    done = State("done")
    # 已有扩写指南，重新修改内容结果
    mod = State("mod")
    
    #
    init_todo = init.to(todo, on="cmd_ok_when_init")
    todo_done = todo.to(done, on="cmd_ok_when_todo")

    def cmd_ok_when_init(self):
        """<#init> ok"""
        print("<#init> ok")

    def cmd_ok_when_todo(self, event_data):
        """<#todo> ok"""
        print("<#todo> ok")
        pass

    #
    done_todo = done.to(todo, on="cmd_todo_when_done", cond=["howto_existing", "result_existing"])
    done_mod = done.to(mod, on="cmd_mod_when_done", cond=["howto_existing", "result_not_existing"])

    def cmd_todo_when_done(self, event_data):
        """<#done> todo"""
        print("<#done> todo")
    
    def cmd_mod_when_done(self):
        """<#done> mod"""
        print("<#done> mod")

    def howto_existing(self, event_data):
        """存在扩写指南"""
        print("存在扩写指南")
        return True

    def result_existing(self, event_data):
        """存在生成结果"""
        print("存在生成结果")
        return True

    def result_not_existing(self, event_data):
        """不存在生成结果"""
        print("不存在生成结果")
        return True

    #
    mod_done = mod.to(done, on="cmd_ok_when_mod")
    mod_todo = mod.to(todo, on="cmd_ok_when_todo")
    
    def cmd_ok_when_mod(self, event_data):
        """<#mod> ok"""
        print("<#mod> ok")

    def cmd_todo_when_mod(self, event_data):
        """<#mod> todo"""
        print("<#mod> todo")
    