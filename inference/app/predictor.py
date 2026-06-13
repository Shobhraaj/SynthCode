from __future__ import annotations

import hashlib
import time

from inference.app.schemas import FileInput, FileScore, PredictResponse


class Predictor:
    def __init__(self, model, tokenizer, settings):
        self.model = model
        self.tokenizer = tokenizer
        self.settings = settings
        self.max_tokens = settings.MAX_TOKENS
        self.overlap = settings.CHUNK_OVERLAP

    def predict_batch(self, files: list[FileInput]) -> PredictResponse:
        started = time.perf_counter()
        if self.model is not None and self.tokenizer is not None:
            scores = self._predict_with_model(files)
        else:
            scores = [self._heuristic_score(file) for file in files]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return PredictResponse(scores=scores, model_version=self.settings.MODEL_VERSION, inference_time_ms=elapsed_ms)

    def warmup(self) -> None:
        if self.model is None or self.tokenizer is None:
            return
        try:
            import torch

            tokens = self.tokenizer("def hello(): pass", return_tensors="pt", truncation=True).to(self.model.device)
            with torch.no_grad():
                self.model(**tokens)
        except Exception:
            return

    def _predict_with_model(self, files: list[FileInput]) -> list[FileScore]:
        import torch

        results: list[FileScore] = []
        for file in files:
            chunks = self._chunk_file(file.content)
            if not chunks:
                results.append(FileScore(path=file.path, score=0.0, chunks_analyzed=0))
                continue
            probs: list[float] = []
            for batch_start in range(0, len(chunks), self.settings.MAX_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + self.settings.MAX_BATCH_SIZE]
                padded = torch.nn.utils.rnn.pad_sequence(batch, batch_first=True, padding_value=self.tokenizer.pad_token_id)
                padded = padded.to(self.model.device)
                attention_mask = (padded != self.tokenizer.pad_token_id).long().to(self.model.device)
                with torch.no_grad():
                    logits = self.model(input_ids=padded, attention_mask=attention_mask).logits
                    values = torch.sigmoid(logits).squeeze(-1).detach().cpu().tolist()
                probs.extend(values if isinstance(values, list) else [values])
            results.append(FileScore(path=file.path, score=round(sum(probs) / len(probs), 4), chunks_analyzed=len(chunks)))
        return results

    def _chunk_file(self, content: str):
        tokens = self.tokenizer(content, truncation=False, return_tensors="pt")
        input_ids = tokens["input_ids"][0]
        if len(input_ids) <= self.max_tokens:
            return [input_ids]
        chunks = []
        start = 0
        stride = max(1, self.max_tokens - self.overlap)
        while start < len(input_ids):
            end = min(start + self.max_tokens, len(input_ids))
            chunks.append(input_ids[start:end])
            if end >= len(input_ids):
                break
            start += stride
        return chunks

    def _heuristic_score(self, file: FileInput) -> FileScore:
        digest = hashlib.sha256(file.content.encode("utf-8", errors="ignore")).hexdigest()
        base = int(digest[:8], 16) / 0xFFFFFFFF
        comment_density = file.content.count("//") + file.content.count("#")
        line_count = max(1, len(file.content.splitlines()))
        density_signal = min(0.25, comment_density / line_count)
        score = min(0.97, max(0.03, (base * 0.55) + density_signal + 0.15))
        chunks = max(1, len(file.content) // 2500)
        return FileScore(path=file.path, score=round(score, 4), chunks_analyzed=chunks)

