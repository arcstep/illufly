from statemachine import StateMachine, State

class ContentState(StateMachine):
    """实现基于有限状态机的内容管理"""

    # 定义有限状态机的状态
    #
    # 初始化扩写指南
    s_init = State("init", value="init", initial=True)
    # 已有扩写指南，生成内容结果
    s_todo = State("todo", value="todo")
    # 已生成内容结果
    s_done = State("done", value="done")
    # 已有扩写指南，重新修改内容结果
    s_modi = State("modi", value="modi")

    @property
    def state(self):
        return self.current_state.value
    
    @property
    def is_complete(self):
        return self.state == 'done'
    
    # command: ok
    init_todo = s_init.to(s_todo, on="on_init_todo")
    todo_done = s_todo.to(s_done, on="on_todo_done")
    modi_done = s_modi.to(s_done, on="on_modi_done")
    ok = init_todo | todo_done | modi_done
    
    # 不需要处理事件，而是直接转移状态
    edit = s_init.to(s_todo) | s_done.to(s_todo) | s_modi.to(s_todo)

    def on_init_todo(self):
        """<#init> ok"""
        print("<#init> ok")

    def on_todo_done(self):
        """<#todo> ok"""
        print("<#todo> ok")

    def on_modi_done(self):
        """<#modi> ok"""
        print("<#modi> ok")

    # command: todo
    done_todo = s_done.to(s_todo, on="on_done_todo", cond=["existing_howto"])
    
    # command: modi
    done_modi = s_done.to(s_modi, on="on_done_modi", cond=["existing_howto"])

    # command: clear
    modi_todo = s_modi.to(s_todo, on="on_modi_todo")

    def on_done_todo(self):
        """<#done> todo"""
        print("<#done> todo")

    def on_done_modi(self):
        """<#modi> todo"""
        print("<#modi> todo")
    
    def on_modi_todo(self):
        """<#done> modi"""
        print("<#done> modi")

    # conditions
    def existing_howto(self):
        """存在扩写指南"""
        print("存在扩写指南")
        return True

    
