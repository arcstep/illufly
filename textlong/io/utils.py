import json
from typing import List, Dict, Any

def merge_json_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_result = {}

    for block in blocks:
        for key, value in block.items():
            if key not in merged_result:
                merged_result[key] = value
            else:
                if isinstance(value, dict) and isinstance(merged_result[key], dict):
                    merged_result[key] = merge_json_blocks([merged_result[key], value])
                elif key not in ['type'] and isinstance(value, str) and isinstance(merged_result[key], str):
                    merged_result[key] += value
                elif value != merged_result[key]:
                    merged_result[key] = value

    return merged_result

def merge_blocks_by_index(blocks: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    index_groups = {}
    for block in blocks:
        index = block.get('index')
        if index is not None:
            if index not in index_groups:
                index_groups[index] = []
            index_groups[index].append(block)
    
    merged_results = {index: merge_json_blocks(group) for index, group in index_groups.items()}
    return merged_results
