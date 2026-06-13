from __future__ import annotations


class ModelLoader:
    def __init__(self, model_path: str, device: str):
        self.model_path = model_path
        self.device = device
        self.model = None
        self.tokenizer = None
        self._load()

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError:
            return

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device if torch.cuda.is_available() else "cpu")
            self.model.eval()
        except Exception:
            self.model = None
            self.tokenizer = None

