def to_tensor(data, device=None):
    """通用数据转换工具"""
    if isinstance(data, torch.Tensor):
        tensor = data
    elif isinstance(data, (list, tuple)):
        tensor = torch.tensor(data)
    elif isinstance(data, np.ndarray):
        tensor = torch.from_numpy(data)
    else:
        raise TypeError(f"不支持的数据类型: {type(data)}")
    
    return tensor.to(device) if device else tensor 