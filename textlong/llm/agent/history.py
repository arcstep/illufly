class History():
    def __init__(self):
        self.history = []

    def append(self, messages: list, **kwargs):
        self.history.append({
            'messages': messages,
            **kwargs
        })
    
    def get(self, index: int=-1):
        return self.history[index]
    