import json
from pathlib import Path
from datasets import load_dataset

def main():
    print("Downloading the basakdemirok/AIGCodeSet dataset...")
    # Load the dataset
    ds = load_dataset("basakdemirok/AIGCodeSet")
    
    # Check splits
    splits = ds.keys()
    print(f"Available splits: {list(splits)}")
    
    output_path = Path("dataset/aigcodeset.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for split_name in splits:
            split_data = ds[split_name]
            for row in split_data:
                code_content = row.get("code", "")
                label = row.get("label", 0)
                
                if not code_content:
                    continue
                    
                json_row = {
                    "content": code_content,
                    "label": int(label)
                }
                f.write(json.dumps(json_row) + "\n")
                count += 1
                
    print(f"Dataset formatting complete. Saved {count} rows to {output_path.resolve()}")

if __name__ == "__main__":
    main()
